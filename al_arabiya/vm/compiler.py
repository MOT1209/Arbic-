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
from al_arabiya.vm.captures import captured_local_names
from al_arabiya.vm.chunk import Chunk, ImportSpec, VMFunction
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
    """Return a human message if the VM can't run ``program``, else ``None``.

    Only one thing still falls back to the interpreter: a ``حاول`` whose
    ``رجّع``/``اكسر``/``كمل`` would jump out across a ``أخيرا`` block.
    """
    for statement in program.body:
        reason = _unsupported(statement)
        if reason is not None:
            return reason
    return None


def _children(node: ASTNode) -> list[ASTNode]:
    """Direct AST children, including map keys/values (which ``fields`` skips)."""
    from al_arabiya.compiler.ast.nodes import iter_child_nodes

    if isinstance(node, MapLiteral):
        collected: list[ASTNode] = []
        for key, value in node.entries:
            collected.append(key)
            collected.append(value)
        return collected
    return iter_child_nodes(node)


def _unsupported(node: ASTNode) -> str | None:
    if isinstance(node, TryStatement) and _try_has_escaping_jump(node):
        return "'حاول' مع 'رجّع/اكسر/كمل' بيعدّي 'أخيرا'"
    for child in _children(node):
        reason = _unsupported(child)
        if reason is not None:
            return reason
    return None


def _try_has_escaping_jump(node: TryStatement) -> bool:
    bodies = [node.try_body]
    if node.catch_body is not None:
        bodies.append(node.catch_body)
    return any(_body_escapes(body, loop_depth=0) for body in bodies)


def _body_escapes(body: list[Statement], *, loop_depth: int) -> bool:
    return any(_stmt_escapes(statement, loop_depth=loop_depth) for statement in body)


def _stmt_escapes(node: Statement, *, loop_depth: int) -> bool:
    if isinstance(node, ReturnStatement):
        return True
    if isinstance(node, (BreakStatement, ContinueStatement)):
        return loop_depth == 0
    if isinstance(node, IfStatement):
        return _body_escapes(node.then_body, loop_depth=loop_depth) or (
            node.else_body is not None
            and _body_escapes(node.else_body, loop_depth=loop_depth)
        )
    if isinstance(node, (WhileStatement, RepeatStatement, ForEachStatement)):
        return _body_escapes(node.body, loop_depth=loop_depth + 1)
    if isinstance(node, TryStatement):
        inner = [node.try_body]
        if node.catch_body is not None:
            inner.append(node.catch_body)
        if node.finally_body is not None:
            inner.append(node.finally_body)
        return any(_body_escapes(b, loop_depth=loop_depth) for b in inner)
    return False


class _FunctionState:
    """Per-function compilation state (its chunk, locals, upvalues, loops)."""

    def __init__(self, *, is_script: bool) -> None:
        self.chunk = Chunk()
        self.is_script = is_script
        self.locals: list[str] = []
        # each loop: {"kind": str, "continue": target, "breaks": [positions]}
        self.loops: list[dict[str, object]] = []
        self.captured: set[str] = set()  # local names an inner function captures
        self.cell_slots: set[int] = set()  # slots boxed in a Cell
        self.upvalues: list[tuple[bool, int]] = []  # (is_local, index)

    def add_upvalue(self, is_local: bool, index: int) -> int:
        descriptor = (is_local, index)
        for existing, candidate in enumerate(self.upvalues):
            if candidate == descriptor:
                return existing
        self.upvalues.append(descriptor)
        return len(self.upvalues) - 1


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
        slot = len(self._state.locals) - 1
        if name in self._state.captured:
            self._state.cell_slots.add(slot)
        return slot

    def _resolve_upvalue(self, name: str, state_index: int) -> int | None:
        """Resolve ``name`` as an upvalue of the function at ``state_index``."""
        if state_index <= 0:
            return None
        enclosing_index = state_index - 1
        enclosing = self._states[enclosing_index]
        if enclosing.is_script:
            return None  # the outer scope is global, not a captured upvalue
        for slot in range(len(enclosing.locals) - 1, -1, -1):
            if enclosing.locals[slot] == name:
                enclosing.cell_slots.add(slot)  # must be boxed to be captured
                return self._states[state_index].add_upvalue(True, slot)
        outer = self._resolve_upvalue(name, enclosing_index)
        if outer is None:
            return None
        return self._states[state_index].add_upvalue(False, outer)

    # ------------------------------------------------------------ statements

    def _statement(self, node: Statement) -> None:
        if isinstance(node, VariableDeclaration):
            self._expression(node.initializer)
            if self._state.is_script:
                self._emit(Op.DEF_GLOBAL, node.span)
                self._emit_arg(self._constant(node.name))
            else:
                slot = self._declare_local(node.name)
                cell = slot in self._state.cell_slots
                self._emit(Op.SET_LOCAL_CELL if cell else Op.SET_LOCAL, node.span)
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
        elif isinstance(node, RepeatStatement):
            self._repeat(node)
        elif isinstance(node, ForEachStatement):
            self._for_each(node)
        elif isinstance(node, IndexAssignment):
            self._expression(node.collection)
            self._expression(node.index)
            self._expression(node.value)
            self._emit(Op.INDEX_SET, node.span)
        elif isinstance(node, ThrowStatement):
            self._expression(node.value)
            self._emit(Op.THROW, node.span)
        elif isinstance(node, TryStatement):
            self._try(node)
        elif isinstance(node, ImportStatement):
            spec = ImportSpec(node.path, alias=node.alias, names=node.names)
            self._emit(Op.IMPORT, node.span)
            self._emit_arg(self._constant(spec))
        else:  # pragma: no cover - guarded by unsupported_reason
            raise UnsupportedFeature(type(node).__name__)

    def _store(self, name: str, span: Span) -> None:
        if not self._state.is_script:
            slot = self._resolve_local(name)
            if slot is not None:
                cell = slot in self._state.cell_slots
                self._emit(Op.SET_LOCAL_CELL if cell else Op.SET_LOCAL, span)
                self._emit_arg(slot)
                return
            upvalue = self._resolve_upvalue(name, len(self._states) - 1)
            if upvalue is not None:
                self._emit(Op.SET_UPVALUE, span)
                self._emit_arg(upvalue)
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
        self._state.loops.append({"kind": "while", "continue": loop_start, "breaks": []})
        self._expression(node.condition)
        exit_jump = self._emit_jump(Op.JUMP_IF_FALSE, node.span)
        for statement in node.body:
            self._statement(statement)
        self._emit(Op.JUMP, node.span)
        self._emit_arg(loop_start)
        self._patch(exit_jump)
        self._end_loop()

    def _repeat(self, node: RepeatStatement) -> None:
        self._expression(node.count)
        self._emit(Op.REP_PREP, node.span)
        loop_start = self._here()
        self._state.loops.append({"kind": "repeat", "continue": loop_start, "breaks": []})
        exit_jump = self._emit_jump(Op.REP_NEXT, node.span)
        for statement in node.body:
            self._statement(statement)
        self._emit(Op.JUMP, node.span)
        self._emit_arg(loop_start)
        self._patch(exit_jump)
        self._end_loop()

    def _for_each(self, node: ForEachStatement) -> None:
        self._expression(node.iterable)
        self._emit(Op.FOR_PREP, node.span)
        loop_start = self._here()
        self._state.loops.append({"kind": "foreach", "continue": loop_start, "breaks": []})
        exit_jump = self._emit_jump(Op.FOR_NEXT, node.span)
        self._bind_name(node.variable, node.variable_span)  # store the item FOR_NEXT pushed
        for statement in node.body:
            self._statement(statement)
        self._emit(Op.JUMP, node.span)
        self._emit_arg(loop_start)
        self._patch(exit_jump)
        self._end_loop()

    def _bind_name(self, name: str, span: Span) -> None:
        if self._state.is_script:
            self._emit(Op.DEF_GLOBAL, span)
            self._emit_arg(self._constant(name))
        else:
            slot = self._declare_local(name)
            cell = slot in self._state.cell_slots
            self._emit(Op.SET_LOCAL_CELL if cell else Op.SET_LOCAL, span)
            self._emit_arg(slot)

    def _end_loop(self) -> None:
        loop = self._state.loops.pop()
        for position in loop["breaks"]:  # type: ignore[attr-defined]
            self._patch(position)

    def _loop_jump(self, node: Statement, *, is_break: bool) -> None:
        if not self._state.loops:
            raise UnsupportedFeature("break/continue خارج حلقة")
        loop = self._state.loops[-1]
        kind = loop["kind"]
        if is_break:
            if kind == "foreach":
                self._emit(Op.FOR_POP, node.span)
            elif kind == "repeat":
                self._emit(Op.REP_POP, node.span)
            position = self._emit_jump(Op.JUMP, node.span)
            loop["breaks"].append(position)  # type: ignore[attr-defined]
        else:
            self._emit(Op.JUMP, node.span)
            self._emit_arg(loop["continue"])  # type: ignore[arg-type]

    def _try(self, node: TryStatement) -> None:
        has_catch = node.catch_body is not None
        has_finally = node.finally_body is not None

        finally_operand = -1
        if has_finally:
            self._emit(Op.SETUP_FINALLY, node.span)
            finally_operand = self._here()
            self._emit_arg(0)
        catch_operand = -1
        if has_catch:
            self._emit(Op.SETUP_EXCEPT, node.span)
            catch_operand = self._here()
            self._emit_arg(0)

        for statement in node.try_body:
            self._statement(statement)
        if has_catch:
            self._emit(Op.POP_BLOCK, node.span)
        after_try = self._emit_jump(Op.JUMP, node.span)

        if has_catch:
            self._patch(catch_operand)
            # the VM pushed the caught error value on the stack
            if node.catch_name is not None:
                self._bind_name(node.catch_name, node.catch_name_span or node.span)
            else:
                self._emit(Op.POP, node.span)
            assert node.catch_body is not None
            for statement in node.catch_body:
                self._statement(statement)

        self._patch(after_try)

        if has_finally:
            self._emit(Op.POP_BLOCK, node.span)
            self._emit(Op.PUSH_FINALLY_OK, node.span)
            self._patch(finally_operand)  # exception path jumps straight here
            assert node.finally_body is not None
            for statement in node.finally_body:
                self._statement(statement)
            self._emit(Op.END_FINALLY, node.span)

    def _function(self, node: FunctionDeclaration) -> None:
        # Pre-declare the name in the enclosing scope so the body can refer to
        # itself (recursion) and resolve it as a local/upvalue, not a global.
        name_slot: int | None = None
        if not self._state.is_script:
            name_slot = self._declare_local(node.name)

        parameter_names = [parameter.name for parameter in node.parameters]
        function_state = _FunctionState(is_script=False)
        function_state.captured = captured_local_names(parameter_names, node.body)
        self._states.append(function_state)
        for index, name in enumerate(parameter_names):
            function_state.locals.append(name)
            if name in function_state.captured:
                function_state.cell_slots.add(index)
        for statement in node.body:
            self._statement(statement)
        self._emit(Op.NULL, node.span)
        self._emit(Op.RETURN, node.span)
        self._states.pop()

        function = VMFunction(
            node.name,
            len(node.parameters),
            function_state.chunk,
            len(function_state.locals),
            upvalues=function_state.upvalues,
            captured_slots=frozenset(function_state.cell_slots),
        )
        # a closure value captures this function's upvalues from the current frame
        self._emit(Op.CLOSURE, node.span)
        self._emit_arg(self._constant(function))
        if name_slot is None:
            self._emit(Op.DEF_GLOBAL, node.name_span)
            self._emit_arg(self._constant(node.name))
        else:
            cell = name_slot in self._state.cell_slots
            self._emit(Op.SET_LOCAL_CELL if cell else Op.SET_LOCAL, node.name_span)
            self._emit_arg(name_slot)

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
        elif isinstance(node, ListLiteral):
            for element in node.elements:
                self._expression(element)
            self._emit(Op.BUILD_LIST, node.span)
            self._emit_arg(len(node.elements))
        elif isinstance(node, MapLiteral):
            for key_node, value_node in node.entries:
                self._expression(key_node)
                self._expression(value_node)
            self._emit(Op.BUILD_MAP, node.span)
            self._emit_arg(len(node.entries))
        elif isinstance(node, IndexExpression):
            self._expression(node.target)
            self._expression(node.index)
            self._emit(Op.INDEX_GET, node.span)
        else:  # pragma: no cover - guarded by unsupported_reason
            raise UnsupportedFeature(type(node).__name__)

    def _load(self, name: str, span: Span) -> None:
        if not self._state.is_script:
            slot = self._resolve_local(name)
            if slot is not None:
                cell = slot in self._state.cell_slots
                self._emit(Op.GET_LOCAL_CELL if cell else Op.GET_LOCAL, span)
                self._emit_arg(slot)
                return
            upvalue = self._resolve_upvalue(name, len(self._states) - 1)
            if upvalue is not None:
                self._emit(Op.GET_UPVALUE, span)
                self._emit_arg(upvalue)
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
