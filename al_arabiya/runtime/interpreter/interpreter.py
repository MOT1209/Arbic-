"""The AlArabiya interpreter: walks the AST and executes it.

Separated from the frontend: it only ever sees AST nodes, never tokens or
raw source text.  Runtime problems are raised as ``ArabiyaRuntimeError``
carrying a full diagnostic with source location.
"""

from __future__ import annotations

import os
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
    ThrowStatement,
    TryStatement,
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
from al_arabiya.runtime.modules import ModuleLoader, module_exports
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


class _Raise(Exception):  # noqa: N818
    """A user-thrown value (``ارم``), catchable by ``حاول/امسك``."""

    def __init__(self, value: Value, span: Span) -> None:
        super().__init__()
        self.value = value
        self.span = span


class Interpreter(ASTVisitor):
    """Tree-walking interpreter over the AlArabiya AST."""

    def __init__(
        self,
        environment: Environment | None = None,
        diagnostics: DiagnosticBag | None = None,
        write: Callable[[str], None] = print,
        base_dir: str | None = None,
        loader: ModuleLoader | None = None,
    ) -> None:
        self.environment = environment if environment is not None else make_global_env()
        self.diagnostics = diagnostics if diagnostics is not None else DiagnosticBag()
        self.write = write
        self.base_dir = base_dir
        self.loader = loader if loader is not None else ModuleLoader(write=write)

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
        except _Raise as signal:
            raise self._control_error(
                ErrorCode.UNCAUGHT_ERROR,
                f"خطأ مرمي مش متمسك: {format_value(signal.value)}",
                signal.span,
                "لفّ الكود بـ 'حاول ... امسك ... خلاص' عشان تمسك الخطأ",
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

    def visit_throw_statement(self, node: ThrowStatement) -> None:
        raise _Raise(self._eval(node.value), node.span)

    def visit_try_statement(self, node: TryStatement) -> None:
        try:
            try:
                for statement in node.try_body:
                    self.visit(statement)
            except (ArabiyaRuntimeError, _Raise) as exc:
                if node.catch_body is None:
                    raise
                if node.catch_name is not None:
                    self.environment.define(node.catch_name, self._exception_value(exc))
                for statement in node.catch_body:
                    self.visit(statement)
        finally:
            if node.finally_body is not None:
                for statement in node.finally_body:
                    self.visit(statement)

    @staticmethod
    def _exception_value(exc: ArabiyaRuntimeError | _Raise) -> Value:
        """The value bound by ``امسك``: thrown values pass through; runtime
        errors become a map with the message, the code and the suggestion."""
        if isinstance(exc, _Raise):
            return exc.value
        diagnostic = exc.diagnostic
        error_map: dict[Value, Value] = {
            "الرسالة": diagnostic.message,
            "الكود": str(diagnostic.code),
        }
        if diagnostic.suggestion is not None:
            error_map["اقتراح"] = diagnostic.suggestion
        return error_map

    def visit_for_each_statement(self, node: ForEachStatement) -> None:
        iterable = self._eval(node.iterable)
        for item in self._iterate(iterable, node.iterable.span):
            self.environment.define(node.variable, item)
            try:
                for statement in node.body:
                    self.visit(statement)
            except _Continue:
                continue
            except _Break:
                break

    def _iterate(self, value: Value, span: Span) -> list[Value]:
        if isinstance(value, list):
            return list(value)
        if isinstance(value, str):
            return list(value)
        if isinstance(value, dict):
            return list(value.keys())
        raise self._control_error(
            ErrorCode.NOT_ITERABLE,
            f"مينفعش أدور على {describe_value(value)} بـ 'لكل'",
            span,
            "استخدم 'لكل' مع قائمة أو نص أو قاموس",
        )

    def visit_index_assignment(self, node: IndexAssignment) -> None:
        collection = self._eval(node.collection)
        index = self._eval(node.index)
        value = self._eval(node.value)
        if isinstance(collection, list):
            position = self._list_index(collection, index, node.index.span)
            collection[position] = value
            return
        if isinstance(collection, dict):
            key = self._hashable_key(index, node.index.span)
            collection[key] = value
            return
        raise self._control_error(
            ErrorCode.INVALID_INDEX,
            f"مينفعش أحط قيمة جوّه {describe_value(collection)}",
            node.collection.span,
            "الفهرسة بالكتابة بتشتغل مع القوائم والقواميس بس",
        )

    def visit_import_statement(self, node: ImportStatement) -> None:
        base = self.base_dir if self.base_dir is not None else os.getcwd()
        abs_path = self.loader.locate(node.path, base)
        module_env = self.loader.load(abs_path, node.path_span)
        exports = module_exports(module_env)

        if node.names is not None:
            for name in node.names:
                if name not in exports:
                    raise self._control_error(
                        ErrorCode.IMPORT_ERROR,
                        f"الاسم '{name}' مش موجود في الملف المستورد",
                        node.path_span,
                        "تأكد إن الاسم معرّف (دالة أو متغيّر) في الملف",
                    )
                self.environment.define(name, exports[name])
        elif node.alias is not None:
            namespace: dict[Value, Value] = {}
            for name, exported in exports.items():
                namespace[name] = exported
            self.environment.define(node.alias, namespace)
        else:
            for name, exported in exports.items():
                self.environment.define(name, exported)

    # ------------------------------------------------------------ expressions

    def visit_literal(self, node: Literal) -> Value:
        return node.value

    def visit_null_literal(self, node: NullLiteral) -> Value:
        return NULL

    def visit_identifier(self, node: Identifier) -> Value:
        return self.environment.get(node.name, node.span)

    def visit_list_literal(self, node: ListLiteral) -> Value:
        return [self._eval(element) for element in node.elements]

    def visit_map_literal(self, node: MapLiteral) -> Value:
        result: dict[Value, Value] = {}
        for key_node, value_node in node.entries:
            key = self._hashable_key(self._eval(key_node), key_node.span)
            result[key] = self._eval(value_node)
        return result

    def visit_index_expression(self, node: IndexExpression) -> Value:
        target = self._eval(node.target)
        index = self._eval(node.index)
        if isinstance(target, (list, str)):
            position = self._list_index(target, index, node.index.span)
            return target[position]
        if isinstance(target, dict):
            key = self._hashable_key(index, node.index.span)
            if key not in target:
                raise self._control_error(
                    ErrorCode.KEY_NOT_FOUND,
                    f"المفتاح {format_value(key)} مش موجود في القاموس",
                    node.index.span,
                    "تأكد إن المفتاح موجود، أو ضيفه الأول",
                )
            return target[key]
        raise self._control_error(
            ErrorCode.INVALID_INDEX,
            f"مينفعش أفهرس {describe_value(target)}",
            node.target.span,
            "الفهرسة بتشتغل مع القوائم والنصوص والقواميس",
        )

    def _list_index(self, sequence: list[Value] | str, index: Value, span: Span) -> int:
        if isinstance(index, bool) or not isinstance(index, int):
            raise self._control_error(
                ErrorCode.INVALID_INDEX,
                f"الفهرس لازم يكون رقم صحيح، مش {describe_value(index)}",
                span,
                "مثال: ق[0]",
            )
        length = len(sequence)
        position = index + length if index < 0 else index  # support negative indices
        if position < 0 or position >= length:
            raise self._control_error(
                ErrorCode.INDEX_OUT_OF_RANGE,
                f"الفهرس {index} بره حدود العنصر (الطول {length})",
                span,
                "استخدم فهرس بين 0 و (الطول ناقص 1)",
            )
        return position

    def _hashable_key(self, key: Value, span: Span) -> Value:
        if isinstance(key, (list, dict, ArabiyaFunction, NativeFunction)):
            raise self._control_error(
                ErrorCode.UNHASHABLE_KEY,
                f"مينفعش أستخدم {describe_value(key)} كمفتاح",
                span,
                "المفاتيح لازم تكون نص أو رقم أو منطقي",
            )
        return key

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
