"""The AlArabiya interpreter: walks the AST and executes it.

Separated from the frontend: it only ever sees AST nodes, never tokens or
raw source text.  Runtime problems are raised as ``ArabiyaRuntimeError``
carrying a full diagnostic with source location.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from al_arabiya.compiler.ast.nodes import (
    Assignment,
    BinaryExpression,
    Expression,
    Identifier,
    IfStatement,
    Literal,
    PrintStatement,
    Program,
    RepeatStatement,
    UnaryExpression,
    VariableDeclaration,
    WhileStatement,
)
from al_arabiya.compiler.ast.visitor import ASTVisitor
from al_arabiya.compiler.diagnostics.diagnostics import Diagnostic, DiagnosticBag, Severity
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.lexer.positions import Span
from al_arabiya.runtime.interpreter.environment import Environment, Value

__all__ = ["Interpreter", "format_value", "is_truthy"]

_MAX_LOOP_ITERATIONS = 1_000_000


def format_value(value: Value) -> str:
    """Render a runtime value the way AlArabiya prints it."""
    if isinstance(value, bool):
        return "صح" if value else "غلط"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def is_truthy(value: Value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return len(value) > 0


def _describe(value: Value) -> str:
    if isinstance(value, bool):
        return "منطقي (صح/غلط)"
    if isinstance(value, (int, float)):
        return "رقم"
    return "نص"


class Interpreter(ASTVisitor):
    """Tree-walking interpreter over the AlArabiya AST."""

    def __init__(
        self,
        environment: Environment | None = None,
        diagnostics: DiagnosticBag | None = None,
        write: Callable[[str], None] = print,
    ) -> None:
        self.environment = environment if environment is not None else Environment()
        self.diagnostics = diagnostics if diagnostics is not None else DiagnosticBag()
        self.write = write

    def run(self, program: Program) -> None:
        self.visit(program)

    def _eval(self, expression: Expression) -> Value:
        return cast(Value, self.visit(expression))

    def _type_error(
        self, message: str, node_span: Span, suggestion: str | None = None
    ) -> ArabiyaRuntimeError:
        return ArabiyaRuntimeError(
            Diagnostic(
                code=ErrorCode.TYPE_ERROR,
                severity=Severity.ERROR,
                message=message,
                span=node_span,
                suggestion=suggestion,
            )
        )

    # ------------------------------------------------------------- statements

    def visit_program(self, node: Program) -> None:
        for statement in node.body:
            self.visit(statement)

    def visit_print_statement(self, node: PrintStatement) -> None:
        self.write(format_value(self._eval(node.expression)))

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
            for statement in node.body:
                self.visit(statement)
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
        if not isinstance(count, (int, float)):
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
            for statement in node.body:
                self.visit(statement)

    # ------------------------------------------------------------ expressions

    def visit_literal(self, node: Literal) -> Value:
        return node.value

    def visit_identifier(self, node: Identifier) -> Value:
        return self.environment.get(node.name, node.span)

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
            return left + right
        if operator in ("-", "*", "/") or operator == "%":
            if isinstance(left, str) or isinstance(right, str):
                raise self._type_error(
                    f"مينفعش أعمل '{operator}' بين {_describe(left)} و {_describe(right)}",
                    node.span,
                    "العمليات الحسابية محتاجة رقمين",
                )
            if operator == "/":
                if right == 0:
                    raise ArabiyaRuntimeError(
                        Diagnostic(
                            code=ErrorCode.DIVISION_BY_ZERO,
                            severity=Severity.ERROR,
                            message="مينفعش تقسم على صفر",
                            span=node.span,
                            suggestion="تأكد إن الطرف اليمين مش صفر",
                        )
                    )
                return left / right
            if operator == "%":
                if right == 0:
                    raise ArabiyaRuntimeError(
                        Diagnostic(
                            code=ErrorCode.DIVISION_BY_ZERO,
                            severity=Severity.ERROR,
                            message="مينفعش أقسم باقي على صفر",
                            span=node.span,
                            suggestion="تأكد إن الطرف اليمين مش صفر",
                        )
                    )
                return left % right
            if operator == "-":
                return left - right
            return left * right

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
