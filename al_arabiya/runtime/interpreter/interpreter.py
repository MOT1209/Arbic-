"""The AlArabiya interpreter: walks the AST and executes it.

Separated from the frontend: it only ever sees AST nodes, never tokens or
raw source text.  Runtime problems are raised as ``ArabiyaRuntimeError``
carrying a full diagnostic with source location.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeGuard, cast

from al_arabiya.compiler.ast.nodes import (
    Assignment,
    BinaryExpression,
    BreakStatement,
    CallExpression,
    ContinueStatement,
    Expression,
    ExpressionStatement,
    FunctionDeclaration,
    Identifier,
    IfStatement,
    Literal,
    NullLiteral,
    PrintStatement,
    Program,
    RepeatStatement,
    ReturnStatement,
    UnaryExpression,
    VariableDeclaration,
    WhileStatement,
)
from al_arabiya.compiler.ast.visitor import ASTVisitor
from al_arabiya.compiler.diagnostics.diagnostics import Diagnostic, DiagnosticBag, Severity
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.lexer.positions import Span
from al_arabiya.runtime.builtins import make_global_env
from al_arabiya.runtime.interpreter.environment import Environment, Value
from al_arabiya.runtime.values import (
    NULL,
    ArabiyaFunction,
    BuiltinError,
    NativeFunction,
    describe_value,
    format_value,
    is_truthy,
)

__all__ = ["Interpreter", "format_value", "is_truthy"]

_MAX_LOOP_ITERATIONS = 1_000_000

# Backwards-compatible alias (older call sites used ``_describe``).
_describe = describe_value


def _is_number(value: Value) -> TypeGuard[int | float]:
    """True for numeric values (``bool`` counts, as in the original Masry)."""
    return isinstance(value, (int, float))


class _Return(Exception):  # noqa: N818 — internal control-flow signal, not an error
    """Unwinds a function call, carrying its return value."""

    def __init__(self, value: Value, span: Span) -> None:
        super().__init__()
        self.value = value
        self.span = span


class _Break(Exception):  # noqa: N818
    """Unwinds to the innermost loop and stops it."""

    def __init__(self, span: Span) -> None:
        super().__init__()
        self.span = span


class _Continue(Exception):  # noqa: N818
    """Unwinds to the innermost loop and starts the next iteration."""

    def __init__(self, span: Span) -> None:
        super().__init__()
        self.span = span


class Interpreter(ASTVisitor):
    """Tree-walking interpreter over the AlArabiya AST."""

    def __init__(
        self,
        environment: Environment | None = None,
        diagnostics: DiagnosticBag | None = None,
        write: Callable[[str], None] = print,
    ) -> None:
        self.environment = environment if environment is not None else make_global_env()
        self.diagnostics = diagnostics if diagnostics is not None else DiagnosticBag()
        self.write = write

    def run(self, program: Program) -> None:
        try:
            self.visit(program)
        except _Return as signal:
            raise self._control_error(
                ErrorCode.RETURN_OUTSIDE_FUNCTION,
                "'رجّع' لازم تكون جوّه دالة",
                signal.span,
                "استخدم 'رجّع' داخل 'دالة ... خلاص' بس",
            ) from None
        except (_Break, _Continue) as signal:
            raise self._control_error(
                ErrorCode.LOOP_CONTROL_OUTSIDE_LOOP,
                "'اكسر'/'كمل' لازم تكون جوّه حلقة",
                signal.span,
                "استخدمهم داخل 'طالما' أو 'كرر' بس",
            ) from None

    def _eval(self, expression: Expression) -> Value:
        return cast(Value, self.visit(expression))

    def _type_error(
        self, message: str, node_span: Span, suggestion: str | None = None
    ) -> ArabiyaRuntimeError:
        return self._control_error(ErrorCode.TYPE_ERROR, message, node_span, suggestion)

    def _control_error(
        self,
        code: ErrorCode,
        message: str,
        node_span: Span,
        suggestion: str | None = None,
    ) -> ArabiyaRuntimeError:
        return ArabiyaRuntimeError(
            Diagnostic(
                code=code,
                severity=Severity.ERROR,
                message=message,
                span=node_span,
                suggestion=suggestion,
            )
        )

    def _division_by_zero(self, message: str, node_span: Span) -> ArabiyaRuntimeError:
        return self._control_error(
            ErrorCode.DIVISION_BY_ZERO,
            message,
            node_span,
            "تأكد إن الطرف اليمين مش صفر",
        )

    # ------------------------------------------------------------- statements

    def visit_program(self, node: Program) -> None:
        for statement in node.body:
            self.visit(statement)

    def visit_print_statement(self, node: PrintStatement) -> None:
        self.write(format_value(self._eval(node.expression)))

    def visit_expression_statement(self, node: ExpressionStatement) -> None:
        self._eval(node.expression)

    def visit_variable_declaration(self, node: VariableDeclaration) -> None:
        self.environment.define(node.name, self._eval(node.initializer))

    def visit_assignment(self, node: Assignment) -> None:
        value = self._eval(node.value)
        if not self.environment.has(node.target):
            self.diagnostics.warning(
                ErrorCode.IMPLICIT_DECLARATION,
                f"المتغير '{node.target}' مش معلن — هيتعمل دلوقتي",
                node.target_span,
                suggestion=f"اكتب 'خلي {node.target} = ...' عشان الوضوح",
            )
            self.environment.define(node.target, value)
        else:
            self.environment.assign(node.target, value, node.target_span)

    def visit_if_statement(self, node: IfStatement) -> None:
        if is_truthy(self._eval(node.condition)):
            for statement in node.then_body:
                self.visit(statement)
        elif node.else_body is not None:
            for statement in node.else_body:
                self.visit(statement)

    def visit_while_statement(self, node: WhileStatement) -> None:
        iterations = 0
        while is_truthy(self._eval(node.condition)):
            try:
                for statement in node.body:
                    self.visit(statement)
            except _Continue:
                pass
            except _Break:
                break
            iterations += 1
            if iterations > _MAX_LOOP_ITERATIONS:
                raise ArabiyaRuntimeError(
                    Diagnostic(
                        code=ErrorCode.LOOP_LIMIT_EXCEEDED,
                        severity=Severity.ERROR,
                        message="التكرار مالوش نهاية (طالما فضلت صح مليون مرة)",
                        span=node.span,
                        suggestion="راجع الشرط وتأكد إن المتغيّر بيتأثر جوّا الحلقة",
                    )
                )

    def visit_repeat_statement(self, node: RepeatStatement) -> None:
        count = self._eval(node.count)
        if isinstance(count, bool) or not isinstance(count, (int, float)):
            raise ArabiyaRuntimeError(
                Diagnostic(
                    code=ErrorCode.INVALID_REPEAT_COUNT,
                    severity=Severity.ERROR,
                    message="عدد التكرار لازم يكون رقم",
                    span=node.count.span,
                    suggestion="مثال: كرر 3 مرات",
                )
            )
        for _ in range(int(count)):
            try:
                for statement in node.body:
                    self.visit(statement)
            except _Continue:
                continue
            except _Break:
                break

    def visit_function_declaration(self, node: FunctionDeclaration) -> None:
        self.environment.define(node.name, ArabiyaFunction(node, self.environment))

    def visit_return_statement(self, node: ReturnStatement) -> None:
        value = self._eval(node.value) if node.value is not None else NULL
        raise _Return(value, node.span)

    def visit_break_statement(self, node: BreakStatement) -> None:
        raise _Break(node.span)

    def visit_continue_statement(self, node: ContinueStatement) -> None:
        raise _Continue(node.span)

    # ------------------------------------------------------------ expressions

    def visit_literal(self, node: Literal) -> Value:
        return node.value

    def visit_null_literal(self, node: NullLiteral) -> Value:
        return NULL

    def visit_identifier(self, node: Identifier) -> Value:
        return self.environment.get(node.name, node.span)

    def visit_call_expression(self, node: CallExpression) -> Value:
        callee = self._eval(node.callee)
        arguments = [self._eval(argument) for argument in node.arguments]
        if isinstance(callee, NativeFunction):
            return self._call_native(callee, arguments, node.span)
        if isinstance(callee, ArabiyaFunction):
            return self._call_function(callee, arguments, node.span)
        raise self._control_error(
            ErrorCode.NOT_CALLABLE,
            f"{describe_value(callee)} مش دالة عشان تناديها",
            node.span,
            "نادِ دالة معرّفة بـ 'دالة' أو دالة مدمجة زي 'طول'",
        )

    def _call_native(
        self, fn: NativeFunction, arguments: list[Value], span: Span
    ) -> Value:
        if fn.arity >= 0 and len(arguments) != fn.arity:
            raise self._arity_error(fn.name, fn.arity, len(arguments), span)
        try:
            return fn.fn(*arguments)
        except BuiltinError as exc:
            raise self._control_error(
                ErrorCode.BUILTIN_ERROR, exc.message, span, exc.suggestion
            ) from None

    def _call_function(
        self, fn: ArabiyaFunction, arguments: list[Value], span: Span
    ) -> Value:
        if len(arguments) != fn.arity:
            raise self._arity_error(fn.name, fn.arity, len(arguments), span)
        call_scope = fn.closure.child()
        for parameter, argument in zip(fn.declaration.parameters, arguments, strict=True):
            call_scope.define(parameter.name, argument)

        previous = self.environment
        self.environment = call_scope
        try:
            for statement in fn.declaration.body:
                self.visit(statement)
            return NULL
        except _Return as signal:
            return signal.value
        except (_Break, _Continue) as signal:
            raise self._control_error(
                ErrorCode.LOOP_CONTROL_OUTSIDE_LOOP,
                "'اكسر'/'كمل' لازم تكون جوّه حلقة، مش بس جوّه دالة",
                signal.span,
                "استخدمهم داخل 'طالما' أو 'كرر'",
            ) from None
        finally:
            self.environment = previous

    def _arity_error(
        self, name: str, expected: int, got: int, span: Span
    ) -> ArabiyaRuntimeError:
        return self._control_error(
            ErrorCode.ARITY_MISMATCH,
            f"الدالة '{name}' محتاجة {expected} مدخل، بس وصلها {got}",
            span,
            f"نادِ '{name}' بـ {expected} قيمة",
        )

    def visit_unary_expression(self, node: UnaryExpression) -> Value:
        value = self._eval(node.operand)
        if not isinstance(value, (int, float)):
            raise self._type_error(
                "علامة الناقص بتشتغل على الأرقام بس", node.span, "اكتب رقم بعد الناقص"
            )
        return -value

    def visit_binary_expression(self, node: BinaryExpression) -> Value:
        operator = node.operator
        left = self._eval(node.left)

        # short-circuit exactly like the original Masry semantics
        if operator == "و":
            return is_truthy(left) and is_truthy(self._eval(node.right))
        if operator == "أو":
            return is_truthy(left) or is_truthy(self._eval(node.right))

        right = self._eval(node.right)

        if operator == "+":
            if isinstance(left, str) or isinstance(right, str):
                return format_value(left) + format_value(right)
            if _is_number(left) and _is_number(right):
                return left + right
            raise self._type_error(
                f"مينفعش أجمع {describe_value(left)} مع {describe_value(right)}",
                node.span,
                "الجمع بيشتغل بين رقمين، أو مع نص للدمج",
            )
        if operator in ("-", "*", "/", "%"):
            if _is_number(left) and _is_number(right):
                if operator == "/":
                    if right == 0:
                        raise self._division_by_zero(
                            "مينفعش تقسم على صفر", node.span
                        )
                    return left / right
                if operator == "%":
                    if right == 0:
                        raise self._division_by_zero(
                            "مينفعش أقسم باقي على صفر", node.span
                        )
                    return left % right
                if operator == "-":
                    return left - right
                return left * right
            raise self._type_error(
                f"مينفعش أعمل '{operator}' بين {describe_value(left)} و {describe_value(right)}",
                node.span,
                "العمليات الحسابية محتاجة رقمين",
            )

        if operator in ("==", "!="):
            return left == right if operator == "==" else left != right

        # ordering comparisons may mix incompatible types
        try:
            any_left: Any = left
            any_right: Any = right
            if operator == ">":
                return bool(any_left > any_right)
            if operator == "<":
                return bool(any_left < any_right)
            if operator == ">=":
                return bool(any_left >= any_right)
            if operator == "<=":
                return bool(any_left <= any_right)
        except TypeError:
            raise self._type_error(
                f"مش هينفع أقارن {_describe(left)} مع {_describe(right)}",
                node.span,
                "قارن نفس النوع مع بعض (رقم برقم، نص بنص)",
            ) from None
        raise self._type_error(f"عملية '{operator}' مش معروفة", node.span)
