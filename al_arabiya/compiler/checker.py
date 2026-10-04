"""An optional, gradual static type checker.

It runs after parsing (e.g. from ``arabic check``) and reports type problems
as diagnostics *before* the program runs — it never changes runtime behavior.

Typing is **gradual**: anything without an annotation has the type ``أي``
(any), which is compatible with every type in both directions.  A mismatch is
only reported when both sides have concrete, incompatible types, so existing
un-annotated programs are never affected.
"""

from __future__ import annotations

from al_arabiya.compiler.ast.nodes import (
    Assignment,
    BinaryExpression,
    CallExpression,
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
    TypeName,
    UnaryExpression,
    VariableDeclaration,
    WhileStatement,
)
from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag
from al_arabiya.compiler.diagnostics.errors import ErrorCode
from al_arabiya.compiler.lexer.positions import Span

__all__ = ["TypeChecker", "check_types"]

# Type names (the surface words users write) --------------------------------
T_NUM = "رقم"
T_TEXT = "نص"
T_BOOL = "منطقي"
T_NULL = "فراغ"
T_LIST = "قائمة"
T_MAP = "قاموس"
T_FUNC = "دالة"
T_ANY = "أي"

KNOWN_TYPES = frozenset({T_NUM, T_TEXT, T_BOOL, T_NULL, T_LIST, T_MAP, T_FUNC, T_ANY})
_NUMERIC = frozenset({T_NUM, T_ANY})


class _FunctionSignature:
    __slots__ = ("parameters", "returns")

    def __init__(self, parameters: list[str], returns: str) -> None:
        self.parameters = parameters
        self.returns = returns


class TypeChecker:
    """Walks the AST, inferring types and reporting mismatches."""

    def __init__(self, bag: DiagnosticBag | None = None) -> None:
        self.bag = bag if bag is not None else DiagnosticBag()
        self._scopes: list[dict[str, str]] = [{}]
        self._functions: dict[str, _FunctionSignature] = {}
        self._return_types: list[str] = []  # stack of enclosing function return types

    def check(self, program: Program) -> DiagnosticBag:
        for statement in program.body:
            self._check_statement(statement)
        return self.bag

    # ----------------------------------------------------------- scope helpers

    def _define(self, name: str, type_name: str) -> None:
        self._scopes[-1][name] = type_name

    def _lookup(self, name: str) -> str:
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        return T_ANY  # unknown names are gradually typed

    def _resolve_annotation(self, annotation: TypeName | None) -> str:
        if annotation is None:
            return T_ANY
        if annotation.name not in KNOWN_TYPES:
            self.bag.error(
                ErrorCode.UNKNOWN_TYPE_NAME,
                f"نوع غير معروف: '{annotation.name}'",
                annotation.span,
                suggestion="الأنواع المتاحة: رقم، نص، منطقي، فراغ، قائمة، قاموس، دالة، أي",
            )
            return T_ANY
        return annotation.name

    @staticmethod
    def _compatible(expected: str, actual: str) -> bool:
        """Gradual compatibility: ``أي`` matches anything, else names must equal."""
        return expected == T_ANY or actual == T_ANY or expected == actual

    def _mismatch(self, expected: str, actual: str, span: Span, context: str) -> None:
        self.bag.error(
            ErrorCode.TYPE_MISMATCH,
            f"{context}: متوقّع {expected} لكن لقيت {actual}",
            span,
            suggestion="وحّد الأنواع، أو شيل التعليق النوعي لو مش محتاجه",
        )

    # ------------------------------------------------------------- statements

    def _check_block(self, body: list[Statement]) -> None:
        for statement in body:
            self._check_statement(statement)

    def _check_statement(self, node: Statement) -> None:
        if isinstance(node, VariableDeclaration):
            self._check_variable_declaration(node)
        elif isinstance(node, Assignment):
            self._check_assignment(node)
        elif isinstance(node, FunctionDeclaration):
            self._check_function(node)
        elif isinstance(node, ReturnStatement):
            self._check_return(node)
        elif isinstance(node, PrintStatement):
            self._infer(node.expression)
        elif isinstance(node, ExpressionStatement):
            self._infer(node.expression)
        elif isinstance(node, ThrowStatement):
            self._infer(node.value)
        elif isinstance(node, IfStatement):
            self._infer(node.condition)
            self._check_block(node.then_body)
            if node.else_body is not None:
                self._check_block(node.else_body)
        elif isinstance(node, WhileStatement):
            self._infer(node.condition)
            self._check_block(node.body)
        elif isinstance(node, RepeatStatement):
            count_type = self._infer(node.count)
            if count_type not in _NUMERIC:
                self._mismatch(T_NUM, count_type, node.count.span, "عدد التكرار")
            self._check_block(node.body)
        elif isinstance(node, ForEachStatement):
            self._infer(node.iterable)
            self._scopes.append({node.variable: T_ANY})
            self._check_block(node.body)
            self._scopes.pop()
        elif isinstance(node, IndexAssignment):
            self._infer(node.collection)
            self._infer(node.index)
            self._infer(node.value)
        elif isinstance(node, TryStatement):
            self._check_block(node.try_body)
            if node.catch_body is not None:
                self._scopes.append({})
                if node.catch_name is not None:
                    self._define(node.catch_name, T_ANY)
                self._check_block(node.catch_body)
                self._scopes.pop()
            if node.finally_body is not None:
                self._check_block(node.finally_body)
        elif isinstance(node, ImportStatement):
            pass  # module exports are not statically known

    def _check_variable_declaration(self, node: VariableDeclaration) -> None:
        value_type = self._infer(node.initializer)
        declared = self._resolve_annotation(node.declared_type)
        if node.declared_type is not None and not self._compatible(declared, value_type):
            self._mismatch(declared, value_type, node.initializer.span, "تعريف متغير")
        # the declared type wins when present, so later uses are checked against it
        self._define(node.name, declared if node.declared_type is not None else value_type)

    def _check_assignment(self, node: Assignment) -> None:
        value_type = self._infer(node.value)
        existing = self._lookup(node.target)
        if not self._compatible(existing, value_type):
            self._mismatch(existing, value_type, node.value.span, "إسناد لمتغير")
        else:
            # keep a concrete type if we learn one for a previously-any variable
            if existing == T_ANY:
                self._define(node.target, value_type)

    def _check_function(self, node: FunctionDeclaration) -> None:
        parameter_types = [self._resolve_annotation(p.declared_type) for p in node.parameters]
        return_type = self._resolve_annotation(node.return_type)
        self._functions[node.name] = _FunctionSignature(parameter_types, return_type)
        self._define(node.name, T_FUNC)

        self._scopes.append(
            {p.name: ptype for p, ptype in zip(node.parameters, parameter_types, strict=True)}
        )
        self._return_types.append(return_type)
        self._check_block(node.body)
        self._return_types.pop()
        self._scopes.pop()

    def _check_return(self, node: ReturnStatement) -> None:
        actual = self._infer(node.value) if node.value is not None else T_NULL
        if self._return_types:
            expected = self._return_types[-1]
            span = node.value.span if node.value is not None else node.span
            if not self._compatible(expected, actual):
                self._mismatch(expected, actual, span, "قيمة الإرجاع")

    # ------------------------------------------------------------ expressions

    def _infer(self, node: Expression) -> str:
        if isinstance(node, Literal):
            value = node.value
            if isinstance(value, bool):
                return T_BOOL
            if isinstance(value, (int, float)):
                return T_NUM
            return T_TEXT
        if isinstance(node, NullLiteral):
            return T_NULL
        if isinstance(node, ListLiteral):
            for element in node.elements:
                self._infer(element)
            return T_LIST
        if isinstance(node, MapLiteral):
            for key_node, value_node in node.entries:
                self._infer(key_node)
                self._infer(value_node)
            return T_MAP
        if isinstance(node, Identifier):
            return self._lookup(node.name)
        if isinstance(node, UnaryExpression):
            operand = self._infer(node.operand)
            if operand not in _NUMERIC:
                self._mismatch(T_NUM, operand, node.operand.span, "علامة الناقص")
            return T_NUM
        if isinstance(node, BinaryExpression):
            return self._infer_binary(node)
        if isinstance(node, CallExpression):
            return self._infer_call(node)
        if isinstance(node, IndexExpression):
            return self._infer_index(node)
        return T_ANY

    def _infer_binary(self, node: BinaryExpression) -> str:
        left = self._infer(node.left)
        right = self._infer(node.right)
        operator = node.operator

        if operator in ("و", "أو", "==", "!=", "<", ">", "<=", ">="):
            return T_BOOL
        if operator == "+":
            if left == T_TEXT or right == T_TEXT:
                return T_TEXT
            if left in _NUMERIC and right in _NUMERIC:
                return T_NUM
            self._mismatch(T_NUM, right if left in _NUMERIC else left, node.span, "الجمع")
            return T_ANY
        if operator in ("-", "*", "/", "%"):
            if left in _NUMERIC and right in _NUMERIC:
                return T_NUM
            bad = right if left in _NUMERIC else left
            self._mismatch(T_NUM, bad, node.span, f"العملية '{operator}'")
            return T_ANY
        return T_ANY

    def _infer_call(self, node: CallExpression) -> str:
        argument_types = [self._infer(argument) for argument in node.arguments]
        if isinstance(node.callee, Identifier) and node.callee.name in self._functions:
            signature = self._functions[node.callee.name]
            if len(node.arguments) != len(signature.parameters):
                self.bag.error(
                    ErrorCode.ARGUMENT_COUNT,
                    f"الدالة '{node.callee.name}' محتاجة {len(signature.parameters)} "
                    f"مدخل، بس وصلها {len(node.arguments)}",
                    node.span,
                    suggestion=f"نادِ '{node.callee.name}' بالعدد الصحيح من القيم",
                )
            else:
                for argument, actual, expected in zip(
                    node.arguments, argument_types, signature.parameters, strict=True
                ):
                    if not self._compatible(expected, actual):
                        self._mismatch(expected, actual, argument.span, "مدخل الدالة")
            return signature.returns
        self._infer(node.callee)
        return T_ANY

    def _infer_index(self, node: IndexExpression) -> str:
        target = self._infer(node.target)
        index = self._infer(node.index)
        if target in (T_LIST, T_TEXT) and index not in _NUMERIC:
            self._mismatch(T_NUM, index, node.index.span, "فهرس")
        if target == T_TEXT:
            return T_TEXT
        return T_ANY


def check_types(program: Program, bag: DiagnosticBag | None = None) -> DiagnosticBag:
    """Convenience wrapper: type-check ``program`` and return the bag."""
    return TypeChecker(bag).check(program)
