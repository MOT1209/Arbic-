"""Compile the AST into bytecode for the stack VM.

Only the imperative core of the language is compiled.  Anything outside that
core (collections, ``لكل``, ``كرر``, exceptions, imports, nested functions)
is reported by :func:`unsupported_reason` so callers can fall back to the
tree-walking interpreter — the VM never silently changes behavior.
"""

from __future__ import annotations

from al_arabiya.compiler.ast.nodes import (
    Assignment,
    ASTNode,
    BinaryExpression,
    BreakStatement,
    CallExpression,
    ContinueStatement,
    Expression,
    ExpressionStatement,
    ForEachStatement,
    FunctionDeclaration,
    Identifier,
    IfStatement,
    ImportStatement,
    IndexAssignment,
    IndexExpression,
    ListLiteral,
    Literal,
    MapLiteral,
    NullLiteral,
    Parameter,
    PrintStatement,
    Program,
    RepeatStatement,
    ReturnStatement,
    Statement,
    ThrowStatement,
    TryStatement,
    UnaryExpression,
    VariableDeclaration,
    WhileStatement,
)
from al_arabiya.compiler.lexer.positions import Span
from al_arabiya.vm.chunk import Chunk, VMFunction
from al_arabiya.vm.opcodes import Op

__all__ = ["BytecodeCompiler", "UnsupportedFeature", "compile_program", "unsupported_reason"]

_COMPARISONS = {
    "==": Op.EQ,
    "!=": Op.NEQ,
    "<": Op.LT,
    ">": Op.GT,
    "<=": Op.LE,
    ">=": Op.GE,
}
_ARITHMETIC = {"+": Op.ADD, "-": Op.SUB, "*": Op.MUL, "/": Op.DIV, "%": Op.MOD}


class UnsupportedFeature(Exception):
    """Raised when the program uses something the VM compiler does not handle."""


def unsupported_reason(program: Program) -> str | None:
    """Return a human message if the VM can't run ``program``, else ``None``."""
    return _Supportability().visit_block(program.body, in_function=False)


class _Supportability:
    """Walks the AST looking for the first feature the VM does not support."""

    _REJECT: dict[type[ASTNode], str] = {
        RepeatStatement: "حلقة 'كرر'",
        ForEachStatement: "حلقة 'لكل'",
        ListLiteral: "القوائم []",
        MapLiteral: "القواميس {}",
        IndexExpression: "الفهرسة []",
        IndexAssignment: "الفهرسة بالكتابة",
        TryStatement: "'حاول/امسك'",
        ThrowStatement: "'ارم'",
        ImportStatement: "'استورد'",
    }

    def visit_block(self, body: list[Statement], *, in_function: bool) -> str | None:
        for statement in body:
            reason = self.visit(statement, in_function=in_function)
            if reason is not None:
                return reason
        return None

    def visit(self, node: ASTNode, *, in_function: bool) -> str | None:
        for rejected, label in self._REJECT.items():
            if isinstance(node, rejected):
                return label
        if isinstance(node, FunctionDeclaration):
            if in_function:
                return "الدوال المتداخلة/closures"
            return self.visit_block(node.body, in_function=True)
        if isinstance(node, IfStatement):
            return (
                self.visit(node.condition, in_function=in_function)
                or self.visit_block(node.then_body, in_function=in_function)
                or (
                    self.visit_block(node.else_body, in_function=in_function)
                    if node.else_body is not None
                    else None
                )
            )
        if isinstance(node, WhileStatement):
            return self.visit(node.condition, in_function=in_function) or self.visit_block(
                node.body, in_function=in_function
            )
        if isinstance(node, (PrintStatement, ExpressionStatement)):
            return self.visit(node.expression, in_function=in_function)
        if isinstance(node, VariableDeclaration):
            return self.visit(node.initializer, in_function=in_function)
        if isinstance(node, Assignment):
            return self.visit(node.value, in_function=in_function)
        if isinstance(node, ReturnStatement):
            return (
                self.visit(node.value, in_function=in_function)
                if node.value is not None
                else None
            )
        if isinstance(node, BinaryExpression):
            return self.visit(node.left, in_function=in_function) or self.visit(
                node.right, in_function=in_function
            )
        if isinstance(node, UnaryExpression):
            return self.visit(node.operand, in_function=in_function)
        if isinstance(node, CallExpression):
            reason = self.visit(node.callee, in_function=in_function)
            if reason is not None:
                return reason
            for argument in node.arguments:
                reason = self.visit(argument, in_function=in_function)
                if reason is not None:
                    return reason
            return None
        return None


class _FunctionState:
    """Per-function compilation state (its chunk, locals and loop stack)."""

    def __init__(self, *, is_script: bool) -> None:
        self.chunk = Chunk()
        self.is_script = is_script
        self.locals: list[str] = []
        # each loop: {"continue": target, "breaks": [patch positions]}
        self.loops: list[dict[str, object]] = []


class BytecodeCompiler:
    """Compiles a whole program into a ``<main>`` :class:`VMFunction`."""

    def __init__(self) -> None:
        self._states: list[_FunctionState] = []

    # ----------------------------------------------------------- entry point

    def compile(self, program: Program) -> VMFunction:
        state = _FunctionState(is_script=True)
        self._states.append(state)
        for statement in program.body:
            self._statement(statement)
        self._emit(Op.NULL, program.span)
        self._emit(Op.RETURN, program.span)
        self._states.pop()
        return VMFunction("<الرئيسي>", 0, state.chunk, len(state.locals))

    # -------------------------------------------------------------- emitting

    @property
    def _state(self) -> _FunctionState:
        return self._states[-1]

    def _emit(self, op: Op, span: Span) -> None:
        self._state.chunk.code.append(int(op))
        self._state.chunk.spans.append(span)

    def _emit_arg(self, value: int) -> None:
        self._state.chunk.code.append(value)
        self._state.chunk.spans.append(None)

    def _here(self) -> int:
        return len(self._state.chunk.code)

    def _emit_jump(self, op: Op, span: Span) -> int:
        self._emit(op, span)
        position = self._here()
        self._emit_arg(0)  # placeholder, patched later
        return position

    def _patch(self, position: int) -> None:
        self._state.chunk.code[position] = self._here()

    def _constant(self, value: object) -> int:
        self._state.chunk.constants.append(value)  # type: ignore[arg-type]
        return len(self._state.chunk.constants) - 1

    def _resolve_local(self, name: str) -> int | None:
        locals_ = self._state.locals
        for index in range(len(locals_) - 1, -1, -1):
            if locals_[index] == name:
                return index
        return None

    def _declare_local(self, name: str) -> int:
        existing = self._resolve_local(name)
        if existing is not None:
            return existing
        self._state.locals.append(name)
        return len(self._state.locals) - 1

    # ------------------------------------------------------------ statements

    def _statement(self, node: Statement) -> None:
        if isinstance(node, VariableDeclaration):
            self._expression(node.initializer)
            if self._state.is_script:
                self._emit(Op.DEF_GLOBAL, node.span)
                self._emit_arg(self._constant(node.name))
            else:
                slot = self._declare_local(node.name)
                self._emit(Op.SET_LOCAL, node.span)
                self._emit_arg(slot)
        elif isinstance(node, Assignment):
            self._expression(node.value)
            self._store(node.target, node.span)
        elif isinstance(node, PrintStatement):
            self._expression(node.expression)
            self._emit(Op.PRINT, node.span)
        elif isinstance(node, ExpressionStatement):
            self._expression(node.expression)
            self._emit(Op.POP, node.span)
        elif isinstance(node, ReturnStatement):
            if node.value is not None:
                self._expression(node.value)
            else:
                self._emit(Op.NULL, node.span)
            self._emit(Op.RETURN, node.span)
        elif isinstance(node, IfStatement):
            self._if(node)
        elif isinstance(node, WhileStatement):
            self._while(node)
        elif isinstance(node, FunctionDeclaration):
            self._function(node)
        elif isinstance(node, BreakStatement):
            self._loop_jump(node, is_break=True)
        elif isinstance(node, ContinueStatement):
            self._loop_jump(node, is_break=False)
        else:  # pragma: no cover - guarded by unsupported_reason
            raise UnsupportedFeature(type(node).__name__)

    def _store(self, name: str, span: Span) -> None:
        if not self._state.is_script:
            slot = self._resolve_local(name)
            if slot is not None:
                self._emit(Op.SET_LOCAL, span)
                self._emit_arg(slot)
                return
        self._emit(Op.SET_GLOBAL, span)
        self._emit_arg(self._constant(name))

    def _if(self, node: IfStatement) -> None:
        self._expression(node.condition)
        else_jump = self._emit_jump(Op.JUMP_IF_FALSE, node.span)
        for statement in node.then_body:
            self._statement(statement)
        if node.else_body is not None:
            end_jump = self._emit_jump(Op.JUMP, node.span)
            self._patch(else_jump)
            for statement in node.else_body:
                self._statement(statement)
            self._patch(end_jump)
        else:
            self._patch(else_jump)

    def _while(self, node: WhileStatement) -> None:
        loop_start = self._here()
        self._state.loops.append({"continue": loop_start, "breaks": []})
        self._expression(node.condition)
        exit_jump = self._emit_jump(Op.JUMP_IF_FALSE, node.span)
        for statement in node.body:
            self._statement(statement)
        self._emit(Op.JUMP, node.span)
        self._emit_arg(loop_start)
        self._patch(exit_jump)
        loop = self._state.loops.pop()
        for position in loop["breaks"]:  # type: ignore[attr-defined]
            self._patch(position)

    def _loop_jump(self, node: Statement, *, is_break: bool) -> None:
        if not self._state.loops:
            raise UnsupportedFeature("break/continue خارج حلقة")
        loop = self._state.loops[-1]
        if is_break:
            position = self._emit_jump(Op.JUMP, node.span)
            loop["breaks"].append(position)  # type: ignore[attr-defined]
        else:
            self._emit(Op.JUMP, node.span)
            self._emit_arg(loop["continue"])  # type: ignore[arg-type]

    def _function(self, node: FunctionDeclaration) -> None:
        function_state = _FunctionState(is_script=False)
        self._states.append(function_state)
        for parameter in node.parameters:
            self._declare_param(parameter)
        for statement in node.body:
            self._statement(statement)
        self._emit(Op.NULL, node.span)
        self._emit(Op.RETURN, node.span)
        self._states.pop()
        function = VMFunction(
            node.name, len(node.parameters), function_state.chunk, len(function_state.locals)
        )
        self._emit(Op.CONST, node.span)
        self._emit_arg(self._constant(function))
        self._emit(Op.DEF_GLOBAL, node.span)
        self._emit_arg(self._constant(node.name))

    def _declare_param(self, parameter: Parameter) -> None:
        self._state.locals.append(parameter.name)

    # ------------------------------------------------------------ expressions

    def _expression(self, node: Expression) -> None:
        if isinstance(node, Literal):
            value = node.value
            if isinstance(value, bool):
                self._emit(Op.TRUE if value else Op.FALSE, node.span)
            else:
                self._emit(Op.CONST, node.span)
                self._emit_arg(self._constant(value))
        elif isinstance(node, NullLiteral):
            self._emit(Op.NULL, node.span)
        elif isinstance(node, Identifier):
            self._load(node.name, node.span)
        elif isinstance(node, UnaryExpression):
            self._expression(node.operand)
            self._emit(Op.NEG, node.span)
        elif isinstance(node, BinaryExpression):
            self._binary(node)
        elif isinstance(node, CallExpression):
            self._call(node)
        else:  # pragma: no cover - guarded by unsupported_reason
            raise UnsupportedFeature(type(node).__name__)

    def _load(self, name: str, span: Span) -> None:
        if not self._state.is_script:
            slot = self._resolve_local(name)
            if slot is not None:
                self._emit(Op.GET_LOCAL, span)
                self._emit_arg(slot)
                return
        self._emit(Op.GET_GLOBAL, span)
        self._emit_arg(self._constant(name))

    def _binary(self, node: BinaryExpression) -> None:
        operator = node.operator
        if operator == "و":
            self._logical(node, jump_when=Op.JUMP_IF_FALSE)
            return
        if operator == "أو":
            self._logical(node, jump_when=Op.JUMP_IF_TRUE)
            return
        self._expression(node.left)
        self._expression(node.right)
        if operator in _ARITHMETIC:
            self._emit(_ARITHMETIC[operator], node.span)
        elif operator in _COMPARISONS:
            self._emit(_COMPARISONS[operator], node.span)
        else:  # pragma: no cover
            raise UnsupportedFeature(f"عملية {operator}")

    def _logical(self, node: BinaryExpression, *, jump_when: Op) -> None:
        # Produce a boolean, short-circuiting like the interpreter.
        #   و  (JUMP_IF_FALSE): both truthy → صح, any falsy → غلط
        #   أو (JUMP_IF_TRUE) : any truthy → صح, both falsy → غلط
        is_and = jump_when is Op.JUMP_IF_FALSE
        fell_through = Op.TRUE if is_and else Op.FALSE
        short_value = Op.FALSE if is_and else Op.TRUE

        self._expression(node.left)
        short = self._emit_jump(jump_when, node.span)
        self._expression(node.right)
        short2 = self._emit_jump(jump_when, node.span)
        self._emit(fell_through, node.span)
        end = self._emit_jump(Op.JUMP, node.span)
        self._patch(short)
        self._patch(short2)
        self._emit(short_value, node.span)
        self._patch(end)

    def _call(self, node: CallExpression) -> None:
        self._expression(node.callee)
        for argument in node.arguments:
            self._expression(argument)
        self._emit(Op.CALL, node.span)
        self._emit_arg(len(node.arguments))


def compile_program(program: Program) -> VMFunction:
    """Compile ``program`` to a ``<main>`` function (raises if unsupported)."""
    return BytecodeCompiler().compile(program)
