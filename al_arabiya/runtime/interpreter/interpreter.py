"""The AlArabiya interpreter: walks the AST and executes it.

Separated from the frontend: it only ever sees AST nodes, never tokens or
raw source text.  Runtime problems are raised as ``ArabiyaRuntimeError``
carrying a full diagnostic with source location.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Iterator
from typing import Any, TypeGuard, cast

from al_arabiya.compiler.ast.nodes import (
    Assignment,
    BinaryExpression,
    BreakStatement,
    CallExpression,
    ClassDeclaration,
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
    InterfaceDeclaration,
    LambdaExpression,
    ListLiteral,
    Literal,
    MapLiteral,
    MemberAssignment,
    MemberExpression,
    MethodDeclaration,
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
    YieldStatement,
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
    BoundMethod,
    BuiltinError,
    ClassValue,
    GeneratorValue,
    InstanceValue,
    InterfaceValue,
    LambdaFunction,
    NativeFunction,
    SuperValue,
    describe_value,
    format_value,
    is_truthy,
)

__all__ = ["Interpreter", "format_value", "is_truthy"]

_MAX_LOOP_ITERATIONS = 1_000_000

# Backwards-compatible alias (older call sites used ``_describe``).
_describe = describe_value


def _body_has_yield(body: list[Statement]) -> bool:
    """True when ``body`` contains ``انتج`` outside nested callables/classes."""
    for statement in body:
        if isinstance(statement, YieldStatement):
            return True
        if isinstance(statement, IfStatement):
            if _body_has_yield(statement.then_body):
                return True
            if statement.else_body is not None and _body_has_yield(statement.else_body):
                return True
        elif isinstance(statement, (RepeatStatement, WhileStatement, ForEachStatement)):
            if _body_has_yield(statement.body):
                return True
        elif isinstance(statement, TryStatement):
            if _body_has_yield(statement.try_body):
                return True
            if statement.catch_body is not None and _body_has_yield(statement.catch_body):
                return True
            if statement.finally_body is not None and _body_has_yield(statement.finally_body):
                return True
    return False


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
        self._method_classes: list[ClassValue] = []

    def _current_class(self) -> ClassValue | None:
        return self._method_classes[-1] if self._method_classes else None

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
        for _ in range(self._repeat_count(node)):
            try:
                for statement in node.body:
                    self.visit(statement)
            except _Continue:
                continue
            except _Break:
                break

    def visit_function_declaration(self, node: FunctionDeclaration) -> None:
        self.environment.define(node.name, ArabiyaFunction(node, self.environment))
        # Decorators apply closest-first: ``مزخرف أ`` then ``مزخرف ب``
        # means ``أ(ب(الدالة))``.
        for decorator in reversed(node.decorators):
            decorator_value = self._eval(decorator)
            decorated = self._call_value(
                decorator_value,
                [self.environment.get(node.name, node.name_span)],
                decorator.span,
            )
            self.environment.define(node.name, decorated)

    def visit_yield_statement(self, node: YieldStatement) -> None:
        raise self._control_error(
            ErrorCode.YIELD_OUTSIDE_GENERATOR,
            "'انتج' اتنفّذ برّه دالة مولّد",
            node.span,
            "'انتج' بيشتغل جوّه دالة عادية بس، مش جوّه طريقة صنف",
        )

    def visit_lambda_expression(self, node: LambdaExpression) -> Value:
        return LambdaFunction(node, self.environment)

    def visit_interface_declaration(self, node: InterfaceDeclaration) -> None:
        self.environment.define(
            node.name, InterfaceValue(node, self.environment)
        )

    def visit_class_declaration(self, node: ClassDeclaration) -> None:
        base: ClassValue | None = None
        if node.base_name is not None:
            span = node.base_span if node.base_span is not None else node.name_span
            if not self.environment.has(node.base_name):
                raise self._control_error(
                    ErrorCode.INVALID_BASE_CLASS,
                    f"الصنف الأب '{node.base_name}' مش معرّف",
                    span,
                    "عرّف الصنف الأب قبل الابن في نفس الملف",
                )
            candidate = self.environment.get(node.base_name, span)
            if not isinstance(candidate, ClassValue):
                raise self._control_error(
                    ErrorCode.INVALID_BASE_CLASS,
                    f"'{node.base_name}' مش صنف عشان يتورث منه",
                    span,
                    "الوراثة بتشتغل مع الأصناف بس",
                )
            base = candidate

        interfaces: list[InterfaceValue] = []
        for reference in node.interfaces:
            if not self.environment.has(reference.name):
                raise self._control_error(
                    ErrorCode.INVALID_INTERFACE,
                    f"الواجهة '{reference.name}' مش معرّفة",
                    reference.span,
                    "عرّف الواجهة قبل الصنف اللي بينفّذها",
                )
            candidate = self.environment.get(reference.name, reference.span)
            if not isinstance(candidate, InterfaceValue):
                raise self._control_error(
                    ErrorCode.INVALID_INTERFACE,
                    f"'{reference.name}' مش واجهة عشان الصنف ينفّذها",
                    reference.span,
                    "`ينفذ` بتشتغل مع 'واجهة' بس",
                )
            interfaces.append(candidate)

        self._validate_private_members(node, base)
        klass = ClassValue(
            node, self.environment, base=base, interfaces=tuple(interfaces)
        )
        for interface in interfaces:
            self._validate_interface(klass, interface)
        self.environment.define(node.name, klass)

    def _validate_private_members(
        self, node: ClassDeclaration, base: ClassValue | None
    ) -> None:
        inherited_fields: set[str] = set()
        inherited_methods: dict[str, Span] = {}
        klass = base
        while klass is not None:
            inherited_fields.update(
                field.name for field in klass.declaration.private_fields
            )
            inherited_methods.update(
                {method.name: method.name_span for method in klass.declaration.methods}
            )
            klass = klass.base

        own_fields: set[str] = set()
        own_methods = {method.name: method for method in node.methods}
        for field in node.private_fields:
            if field.name in own_fields:
                raise self._control_error(
                    ErrorCode.PRIVATE_MEMBER_CONFLICT,
                    f"الحقل الخاص '{field.name}' متكرر في نفس الصنف",
                    field.name_span,
                    "احتفظ بتعريف واحد لكل حقل خاص",
                )
            own_fields.add(field.name)
            if field.name in inherited_fields:
                raise self._control_error(
                    ErrorCode.PRIVATE_MEMBER_CONFLICT,
                    f"الحقل الخاص '{field.name}' موجود بالفعل في صنف أب",
                    field.name_span,
                    "اسم مختلف لكل حقل خاص على طول سلسلة الوراثة",
                )
            if field.name in own_methods:
                raise self._control_error(
                    ErrorCode.PRIVATE_MEMBER_CONFLICT,
                    f"الاسم '{field.name}' مستخدم كحقل وكطريقة في نفس الصنف",
                    field.name_span,
                    "غيّر اسم الحقل أو الطريقة",
                )

        for method in node.methods:
            if not method.is_private:
                continue
            if method.name == "__تهيئة__":
                raise self._control_error(
                    ErrorCode.PRIVATE_MEMBER_CONFLICT,
                    "'__تهيئة__' مينفعش تكون خاصة",
                    method.name_span,
                    "خلي التهيئة عامة عشان نداء الصنف يشتغل",
                )
            if method.name in inherited_methods:
                raise self._control_error(
                    ErrorCode.PRIVATE_MEMBER_CONFLICT,
                    f"الطريقة الخاصة '{method.name}' بتعارض عضوًا موروثًا",
                    method.name_span,
                    "الطريقة الخاصة لازم يكون اسمها جديد في سلسلة الوراثة",
                )
            if method.name in own_fields:
                raise self._control_error(
                    ErrorCode.PRIVATE_MEMBER_CONFLICT,
                    f"الاسم '{method.name}' مستخدم كحقل وكطريقة في نفس الصنف",
                    method.name_span,
                    "غيّر اسم الحقل أو الطريقة",
                )

    def _validate_interface(
        self, klass: ClassValue, interface: InterfaceValue
    ) -> None:
        for signature in interface.declaration.methods:
            resolved = (
                klass.resolve_static_method(signature.name)
                if signature.is_static
                else klass.resolve_instance_method(signature.name)
            )
            if resolved is None or resolved[1].is_private:
                raise self._control_error(
                    ErrorCode.MISSING_INTERFACE_MEMBER,
                    f"الصنف '{klass.name}' ناقص طريقة '{signature.name}' "
                    f"المطلوبة من واجهة '{interface.name}'",
                    signature.name_span,
                    "ضيف الطريقة بنفس الاسم والتوقيع",
                )
            implementation = resolved[1]
            if len(implementation.parameters) != len(signature.parameters):
                raise self._control_error(
                    ErrorCode.MISSING_INTERFACE_MEMBER,
                    f"طريقة '{signature.name}' في '{klass.name}' "
                    f"عدد معاملاتها مش مطابق لواجهة '{interface.name}'",
                    signature.name_span,
                    "وحّد عدد المعاملات مع الواجهة",
                )
            for expected, actual in zip(
                signature.parameters, implementation.parameters, strict=True
            ):
                if not self._types_match(
                    expected.declared_type, actual.declared_type
                ):
                    raise self._control_error(
                        ErrorCode.MISSING_INTERFACE_MEMBER,
                        f"طريقة '{signature.name}' في '{klass.name}' "
                        f"نوع معاملها مش مطابق لواجهة '{interface.name}'",
                        signature.name_span,
                        "وحّد أنواع المعاملات مع الواجهة",
                    )
            if not self._types_match(
                signature.return_type, implementation.return_type
            ):
                raise self._control_error(
                    ErrorCode.MISSING_INTERFACE_MEMBER,
                    f"طريقة '{signature.name}' في '{klass.name}' "
                    f"نوع إرجاعها مش مطابق لواجهة '{interface.name}'",
                    signature.name_span,
                    "وحّد نوع الإرجاع مع الواجهة",
                )

    @staticmethod
    def _types_match(
        expected: TypeName | None, actual: TypeName | None
    ) -> bool:
        if expected is None:
            return True
        return actual is not None and actual.name == expected.name

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

    def _iterate(self, value: Value, span: Span) -> Iterable[Value]:
        if isinstance(value, list):
            return list(value)
        if isinstance(value, str):
            return list(value)
        if isinstance(value, dict):
            return list(value.keys())
        if isinstance(value, GeneratorValue):
            return value.iterator
        raise self._control_error(
            ErrorCode.NOT_ITERABLE,
            f"مينفعش أدور على {describe_value(value)} بـ 'لكل'",
            span,
            "استخدم 'لكل' مع قائمة أو نص أو قاموس أو مولّد",
        )

    def _repeat_count(self, node: RepeatStatement) -> int:
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
        if isinstance(count, float) and not count.is_integer():
            raise ArabiyaRuntimeError(
                Diagnostic(
                    code=ErrorCode.INVALID_REPEAT_COUNT,
                    severity=Severity.ERROR,
                    message="عدد التكرار لازم يكون عدد صحيح",
                    span=node.count.span,
                    suggestion="مثال: كرر 3 مرات",
                )
            )
        if count < 0:
            raise ArabiyaRuntimeError(
                Diagnostic(
                    code=ErrorCode.INVALID_REPEAT_COUNT,
                    severity=Severity.ERROR,
                    message="عدد التكرار مينفعش يكون سالب",
                    span=node.count.span,
                    suggestion="استخدم صفر أو عدد موجب",
                )
            )
        return int(count)

    def visit_member_assignment(self, node: MemberAssignment) -> None:
        target = self._eval(node.target)
        value = self._eval(node.value)
        if not isinstance(target, InstanceValue):
            raise self._control_error(
                ErrorCode.INVALID_MEMBER_ACCESS,
                f"مينفعش أحط خاصية على {describe_value(target)}",
                node.target.span,
                "الخصائص بتتحدّد على كائن (مثال: شخص.سن = 30)",
            )
        owner = target.klass.private_field_owner(node.name)
        if owner is not None and self._current_class() is not owner:
            raise self._private_error(node.name, owner, node.name_span)
        target.fields[node.name] = value

    def _private_error(
        self, name: str, owner: ClassValue, span: Span
    ) -> ArabiyaRuntimeError:
        return self._control_error(
            ErrorCode.PRIVATE_MEMBER_ACCESS,
            f"'{name}' عضو خاص في '{owner.name}'",
            span,
            "الأعضاء الخاصة بتتستخدم من جوّه الصنف اللي عرّفها بس",
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
        abs_path = self.loader.locate(node.path, base, node.path_span)
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

    def visit_member_expression(self, node: MemberExpression) -> Value:
        target = self._eval(node.target)
        current = self._current_class()
        if isinstance(target, InstanceValue):
            owner = target.klass.private_field_owner(node.name)
            if owner is not None and current is not owner:
                raise self._private_error(node.name, owner, node.name_span)
            if node.name in target.fields:
                return target.fields[node.name]
            resolved = target.klass.resolve_instance_method_for(node.name, current)
            if resolved is not None:
                declaring, method = resolved
                return BoundMethod(target, method, declaring)
            private_owner = target.klass.private_method_owner(
                node.name, is_static=False
            )
            if private_owner is not None:
                raise self._private_error(
                    node.name, private_owner, node.name_span
                )
            raise self._control_error(
                ErrorCode.MEMBER_NOT_FOUND,
                f"الصنف '{target.klass.name}' مفيهوش عضو اسمه '{node.name}'",
                node.name_span,
                "تأكد من اسم الخاصية أو الطريقة، أو عرّفها جوّه 'صنف'",
            )
        if isinstance(target, SuperValue):
            resolved = target.start.resolve_instance_method_for(
                node.name, current
            )
            if resolved is not None:
                declaring, method = resolved
                return BoundMethod(target.instance, method, declaring)
            private_owner = target.start.private_method_owner(
                node.name, is_static=False
            )
            if private_owner is not None:
                raise self._private_error(
                    node.name, private_owner, node.name_span
                )
            raise self._control_error(
                ErrorCode.MEMBER_NOT_FOUND,
                f"أساس '{target.start.name}' مفيهوش طريقة اسمها '{node.name}'",
                node.name_span,
                "`الأساس` بيوصل لطرق الأب بس (مش الخصائص)",
            )
        if isinstance(target, ClassValue):
            resolved_static = target.resolve_static_method_for(
                node.name, current
            )
            if resolved_static is not None:
                declaring, method = resolved_static
                return BoundMethod(None, method, declaring)
            private_owner = target.private_method_owner(
                node.name, is_static=True
            ) or target.private_method_owner(node.name, is_static=False)
            if private_owner is not None:
                raise self._private_error(
                    node.name, private_owner, node.name_span
                )
            if target.resolve_instance_method(node.name) is not None:
                raise self._control_error(
                    ErrorCode.INVALID_MEMBER_ACCESS,
                    f"'{node.name}' طريقة كائن على '{target.name}' ومش طريقة ساكنة",
                    node.name_span,
                    f"ناديها على كائن: خلي ك = {target.name}(...)\nك.{node.name}(...)",
                )
            raise self._control_error(
                ErrorCode.MEMBER_NOT_FOUND,
                f"الصنف '{target.name}' مفيهوش طريقة ساكنة اسمها '{node.name}'",
                node.name_span,
                "الوصول بالصنف بيشتغل مع 'دالة ساكنة' بس",
            )
        raise self._control_error(
            ErrorCode.INVALID_MEMBER_ACCESS,
            f"مينفعش أوصل لعضو '{node.name}' على {describe_value(target)}",
            node.target.span,
            "الوصول بالنقطة بيشتغل على الكائنات والأصناف بس",
        )

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
        if isinstance(
            key,
            (
                list,
                dict,
                ArabiyaFunction,
                LambdaFunction,
                NativeFunction,
                BoundMethod,
                ClassValue,
                GeneratorValue,
                InstanceValue,
                SuperValue,
                InterfaceValue,
            ),
        ):
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
        return self._call_value(callee, arguments, node.span)

    def _call_value(
        self, callee: Value, arguments: list[Value], span: Span
    ) -> Value:
        """Call any callable value (used by calls and by decorator application)."""
        if isinstance(callee, NativeFunction):
            return self._call_native(callee, arguments, span)
        if isinstance(callee, (ArabiyaFunction, LambdaFunction)):
            return self._call_function(callee, arguments, span)
        if isinstance(callee, ClassValue):
            return self._instantiate(callee, arguments, span)
        if isinstance(callee, BoundMethod):
            return self._call_method(callee, arguments, span)
        raise self._control_error(
            ErrorCode.NOT_CALLABLE,
            f"{describe_value(callee)} مش دالة عشان تناديها",
            span,
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
        self,
        fn: ArabiyaFunction | LambdaFunction,
        arguments: list[Value],
        span: Span,
    ) -> Value:
        if len(arguments) != fn.arity:
            raise self._arity_error(fn.name, fn.arity, len(arguments), span)
        call_scope = fn.closure.child()
        for parameter, argument in zip(fn.declaration.parameters, arguments, strict=True):
            call_scope.define(parameter.name, argument)
        if _body_has_yield(fn.declaration.body):
            return GeneratorValue(
                self._generator_body(fn.declaration.body, call_scope)
            )
        return self._execute_body(fn.declaration, call_scope)

    def _call_method(
        self, bound: BoundMethod, arguments: list[Value], span: Span
    ) -> Value:
        if len(arguments) != bound.arity:
            display = f"{bound.declaring.name}.{bound.name}"
            raise self._arity_error(display, bound.arity, len(arguments), span)
        call_scope = bound.declaring.closure.child()
        self._method_classes.append(bound.declaring)
        try:
            if bound.instance is not None:
                call_scope.define("انا", bound.instance)
                if bound.declaring.base is not None:
                    call_scope.define(
                        "الأساس", SuperValue(bound.instance, bound.declaring.base)
                    )
            for parameter, argument in zip(
                bound.method.parameters, arguments, strict=True
            ):
                call_scope.define(parameter.name, argument)
            return self._execute_body(bound.method, call_scope)
        finally:
            self._method_classes.pop()

    def _execute_body(
        self,
        declaration: FunctionDeclaration | MethodDeclaration | LambdaExpression,
        scope: Environment,
    ) -> Value:
        previous = self.environment
        self.environment = scope
        try:
            for statement in declaration.body:
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

    def _generator_body(
        self, body: list[Statement], scope: Environment
    ) -> Iterator[Value]:
        """Run a function body lazily, suspending at every ``انتج``."""
        previous = self.environment
        self.environment = scope
        try:
            yield from self._generator_statements(body)
        except _Return:
            return
        except (_Break, _Continue) as signal:
            raise self._control_error(
                ErrorCode.LOOP_CONTROL_OUTSIDE_LOOP,
                "'اكسر'/'كمل' لازم تكون جوّه حلقة، مش بس جوّه دالة",
                signal.span,
                "استخدمهم داخل 'طالما' أو 'كرر'",
            ) from None
        finally:
            self.environment = previous

    def _generator_statements(self, body: list[Statement]) -> Iterator[Value]:
        for statement in body:
            if isinstance(statement, YieldStatement):
                yield self._eval(statement.value)
            elif isinstance(statement, IfStatement):
                if is_truthy(self._eval(statement.condition)):
                    yield from self._generator_statements(statement.then_body)
                elif statement.else_body is not None:
                    yield from self._generator_statements(statement.else_body)
            elif isinstance(statement, RepeatStatement):
                for _ in range(self._repeat_count(statement)):
                    try:
                        yield from self._generator_statements(statement.body)
                    except _Continue:
                        continue
                    except _Break:
                        break
            elif isinstance(statement, WhileStatement):
                iterations = 0
                while is_truthy(self._eval(statement.condition)):
                    try:
                        yield from self._generator_statements(statement.body)
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
                                message=(
                                    "التكرار مالوش نهاية "
                                    "(طالما فضلت صح مليون مرة)"
                                ),
                                span=statement.span,
                                suggestion=(
                                    "راجع الشرط وتأكد إن المتغيّر "
                                    "بيتأثر جوّا الحلقة"
                                ),
                            )
                        )
            elif isinstance(statement, ForEachStatement):
                iterable = self._eval(statement.iterable)
                for item in self._iterate(iterable, statement.iterable.span):
                    self.environment.define(statement.variable, item)
                    try:
                        yield from self._generator_statements(statement.body)
                    except _Continue:
                        continue
                    except _Break:
                        break
            elif isinstance(statement, TryStatement):
                try:
                    try:
                        yield from self._generator_statements(statement.try_body)
                    except (ArabiyaRuntimeError, _Raise) as exc:
                        if statement.catch_body is None:
                            raise
                        if statement.catch_name is not None:
                            self.environment.define(
                                statement.catch_name, self._exception_value(exc)
                            )
                        yield from self._generator_statements(statement.catch_body)
                finally:
                    if statement.finally_body is not None:
                        yield from self._generator_statements(
                            statement.finally_body
                        )
            else:
                self.visit(statement)

    def _instantiate(
        self, klass: ClassValue, arguments: list[Value], span: Span
    ) -> Value:
        instance = InstanceValue(klass, {})
        resolved = klass.resolve_instance_method("__تهيئة__")
        if resolved is not None:
            declaring, initializer = resolved
            bound = BoundMethod(instance, initializer, declaring)
            self._call_method(bound, arguments, span)
        elif arguments:
            raise self._arity_error(klass.name, 0, len(arguments), span)
        return instance

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
