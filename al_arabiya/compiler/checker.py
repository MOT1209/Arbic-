"""An optional, gradual static type checker with symbol tables.

It runs after parsing (e.g. from ``arabic check``) and reports type problems
as diagnostics *before* the program runs — it never changes runtime behavior.

Typing is **gradual** by default: anything without an annotation has the type
``أي`` (any), which is compatible with every type in both directions.  A
mismatch is only reported when both sides have concrete, incompatible types,
so existing un-annotated programs are never affected.

The checker keeps a real symbol table per scope (module, function) and can
analyse imports: it compiles each imported module, type-checks it once, and
binds its exported names with their inferred types.  It reuses the runtime's
:class:`~al_arabiya.runtime.modules.ModuleLoader` resolution rules, so static
analysis can never read a file the interpreter itself would refuse.

``strict`` switches the checker to the opt-in strict mode documented in
``docs/architecture/adr-05-static-typing.md``: every declaration must carry an
annotation and every referenced name must exist.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from al_arabiya.compiler.ast.nodes import (
    Assignment,
    BinaryExpression,
    CallExpression,
    ClassDeclaration,
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
    MatchStatement,
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
    WithStatement,
    YieldStatement,
)
from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.lexer.positions import Span
from al_arabiya.compiler.types import (
    ANY,
    BOOLEAN,
    CLASS,
    FUNCTION,
    NULL,
    NUMBER,
    TEXT,
    Type,
    is_assignable,
    is_numeric,
    is_textual,
    list_of,
    map_of,
    render,
    union,
)

__all__ = ["Scope", "Symbol", "TypeChecker", "check_types"]

#: The simple surface names that accept no generic arguments.
_SIMPLE_TYPES: dict[str, Type] = {
    "رقم": NUMBER,
    "نص": TEXT,
    "منطقي": BOOLEAN,
    "فراغ": NULL,
    "دالة": FUNCTION,
    "صنف": CLASS,
    "أي": ANY,
}

_TYPE_LIST = "قائمة"
_TYPE_MAP = "قاموس"
_TYPE_OPTIONAL = "اختياري"

#: Return types of the builtins.  Their arity is accepted as-is: the builtins
#: raise ``E4010`` at runtime, and guessing a static arity would reject valid
#: calls such as ``مدى`` with one or two arguments.
_BUILTIN_RETURNS: dict[str, Type] = {
    "طول": NUMBER,
    "نوع": TEXT,
    "رقم": NUMBER,
    "نص": TEXT,
    "منطقي": BOOLEAN,
    "اقرأ": TEXT,
    "مطلق": NUMBER,
    "قرّب": NUMBER,
    "جذر": NUMBER,
    "اس": NUMBER,
    "اضف": list_of(),
    "احذف": ANY,
    "مدى": list_of(NUMBER),
    "مجموع": NUMBER,
    "اكبر": NUMBER,
    "اصغر": NUMBER,
    "رتب": list_of(),
    "اعكس": ANY,
    "يحتوي": BOOLEAN,
    "مفاتيح": list_of(),
    "قيم": list_of(),
    "قسّم": list_of(TEXT),
    "ادمج": TEXT,
    "استبدل": TEXT,
}


@dataclass(slots=True)
class _FunctionSignature:
    """``parameters=None`` means "unknown arity" (builtins)."""

    parameters: list[Type] | None
    returns: Type


@dataclass(slots=True)
class Symbol:
    """One entry in a symbol table."""

    name: str
    type: Type
    kind: str = "variable"
    span: Span | None = None
    signature: _FunctionSignature | None = None


class Scope:
    """A symbol table with a parent link (functions nest, blocks do not).

    ``docs/architecture/adr-02-block-scope.md`` fixes the language rule: only
    functions introduce a scope, so ``لو``/``كرر``/``لكل`` bodies share their
    enclosing scope.  The checker mirrors that exactly.
    """

    __slots__ = ("parent", "label", "symbols")

    def __init__(self, parent: Scope | None = None, label: str = "block") -> None:
        self.parent = parent
        self.label = label
        self.symbols: dict[str, Symbol] = {}

    def define(self, symbol: Symbol) -> None:
        self.symbols[symbol.name] = symbol

    def lookup(self, name: str) -> Symbol | None:
        scope: Scope | None = self
        while scope is not None:
            if name in scope.symbols:
                return scope.symbols[name]
            scope = scope.parent
        return None

    def names(self) -> list[str]:
        return list(self.symbols)


class TypeChecker:
    """Walks the AST, maintaining scopes and reporting type mismatches."""

    def __init__(
        self,
        bag: DiagnosticBag | None = None,
        *,
        strict: bool = False,
        base_dir: str | None = None,
        filename: str | None = None,
        _module_cache: dict[str, dict[str, Symbol]] | None = None,
        _module_loading: set[str] | None = None,
    ) -> None:
        self.bag = bag if bag is not None else DiagnosticBag()
        self.strict = strict
        #: Directory used to resolve ``استورد`` during analysis.  ``None``
        #: disables module analysis (the historical single-file behaviour).
        self.base_dir = base_dir
        self.filename = filename
        self.scopes: list[Scope] = [Scope(label="module")]
        self._return_types: list[Type] = []
        self._interfaces: dict[str, list[MethodDeclaration]] = {}
        self._class_methods: dict[str, dict[tuple[str, bool], MethodDeclaration]] = {}
        self._namespaces: dict[str, dict[str, Symbol]] = {}
        self._module_cache: dict[str, dict[str, Symbol]] = (
            _module_cache if _module_cache is not None else {}
        )
        self._module_loading: set[str] = (
            _module_loading if _module_loading is not None else set()
        )

    def check(self, program: Program) -> DiagnosticBag:
        self._seed_builtins()
        for statement in program.body:
            self._check_statement(statement)
        return self.bag

    def exports(self) -> dict[str, Symbol]:
        """Top-level names a module makes available to importers."""
        module_scope = self.scopes[0]
        return {
            name: symbol
            for name, symbol in module_scope.symbols.items()
            if symbol.kind != "builtin"
        }

    # ----------------------------------------------------------- scope helpers

    def _seed_builtins(self) -> None:
        for name, returns in _BUILTIN_RETURNS.items():
            self.scopes[0].define(
                Symbol(
                    name,
                    FUNCTION,
                    "builtin",
                    signature=_FunctionSignature(None, returns),
                )
            )

    def _define(
        self,
        name: str,
        type_name: Type,
        *,
        kind: str = "variable",
        span: Span | None = None,
        signature: _FunctionSignature | None = None,
    ) -> None:
        self.scopes[-1].define(Symbol(name, type_name, kind, span, signature))

    def _lookup_symbol(self, name: str) -> Symbol | None:
        return self.scopes[-1].lookup(name)

    def _lookup(self, name: str, span: Span) -> Type:
        symbol = self._lookup_symbol(name)
        if symbol is not None:
            return symbol.type
        if self.strict:
            # Unknown names used to be silently ``أي``; the symbol table makes
            # them detectable, and strict mode turns that into an error.
            self.bag.error(
                ErrorCode.UNDEFINED_NAME,
                f"الاسم '{name}' مش معرّف",
                span,
                suggestion=f"عرّفه الأول: خلي {name} : رقم = ...",
            )
        return ANY

    # ------------------------------------------------------------- annotations

    def _resolve_annotation(self, annotation: TypeName | None) -> Type:
        if annotation is None:
            return ANY
        if annotation.members:
            return union(
                *(self._resolve_annotation(member) for member in annotation.members)
            )
        name = annotation.name
        arguments = annotation.arguments

        if name == _TYPE_OPTIONAL:
            if len(arguments) != 1:
                self._bad_type_arguments(annotation, name, "قيمة نوع واحدة")
                return ANY
            return union(self._resolve_annotation(arguments[0]), NULL)

        if name == _TYPE_LIST:
            if len(arguments) > 1:
                self._bad_type_arguments(annotation, name, "نوع عنصر واحد على الأكثر")
                return list_of()
            element = self._resolve_annotation(arguments[0]) if arguments else ANY
            return list_of(element)

        if name == _TYPE_MAP:
            if len(arguments) not in (0, 2):
                self._bad_type_arguments(
                    annotation, name, "نوعين (مفتاح وقيمة) أو مفيش"
                )
                return map_of()
            if not arguments:
                return map_of()
            return map_of(
                self._resolve_annotation(arguments[0]),
                self._resolve_annotation(arguments[1]),
            )

        if name not in _SIMPLE_TYPES:
            self.bag.error(
                ErrorCode.UNKNOWN_TYPE_NAME,
                f"نوع غير معروف: '{name}'",
                annotation.span,
                suggestion=(
                    "الأنواع المتاحة: رقم، نص، منطقي، فراغ، قائمة[T]، "
                    "قاموس[K، V]، اختياري[T]، دالة، صنف، أي (و'أو' للاتحاد)"
                ),
            )
            return ANY
        if arguments:
            self._bad_type_arguments(annotation, name, "مفيش أنواع فرعية")
        return _SIMPLE_TYPES[name]

    def _bad_type_arguments(self, annotation: TypeName, name: str, shape: str) -> None:
        self.bag.error(
            ErrorCode.INVALID_TYPE_ARGUMENT,
            f"النوع '{name}' محتاج {shape}، بس لقيت {len(annotation.arguments)}",
            annotation.span,
            suggestion="أمثلة: قائمة[رقم] · قاموس[نص، رقم] · اختياري[نص]",
        )

    @staticmethod
    def _same_annotation(left: TypeName | None, right: TypeName | None) -> bool:
        """Structural comparison used for interface signatures (no diagnostics)."""
        if left is None or right is None:
            return left is None and right is None
        if left.name != right.name:
            return False
        if len(left.arguments) != len(right.arguments):
            return False
        if len(left.members) != len(right.members):
            return False
        if not all(
            TypeChecker._same_annotation(a, b)
            for a, b in zip(left.arguments, right.arguments, strict=True)
        ):
            return False
        return all(
            TypeChecker._same_annotation(a, b)
            for a, b in zip(left.members, right.members, strict=True)
        )

    @staticmethod
    def _compatible(expected: Type, actual: Type) -> bool:
        return is_assignable(expected, actual)

    def _mismatch(self, expected: Type, actual: Type, span: Span, context: str) -> None:
        self.bag.error(
            ErrorCode.TYPE_MISMATCH,
            f"{context}: متوقّع {render(expected)} لكن لقيت {render(actual)}",
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
        elif isinstance(node, ClassDeclaration):
            self._check_class(node)
        elif isinstance(node, InterfaceDeclaration):
            self._check_interface(node)
        elif isinstance(node, ReturnStatement):
            self._check_return(node)
        elif isinstance(node, PrintStatement):
            self._infer(node.expression)
        elif isinstance(node, ExpressionStatement):
            self._infer(node.expression)
        elif isinstance(node, ThrowStatement):
            self._infer(node.value)
        elif isinstance(node, YieldStatement):
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
            if not is_numeric(count_type):
                self._mismatch(NUMBER, count_type, node.count.span, "عدد التكرار")
            self._check_block(node.body)
        elif isinstance(node, ForEachStatement):
            element = self._iterable_element(self._infer(node.iterable))
            self._define(node.variable, element, span=node.variable_span)
            self._check_block(node.body)
        elif isinstance(node, IndexAssignment):
            self._infer(node.collection)
            self._infer(node.index)
            self._infer(node.value)
        elif isinstance(node, MemberAssignment):
            self._infer(node.target)
            self._infer(node.value)
        elif isinstance(node, WithStatement):
            self._infer(node.value)
            self._define(node.name, ANY, span=node.name_span)
            self._check_block(node.body)
        elif isinstance(node, MatchStatement):
            self._check_match(node)
        elif isinstance(node, TryStatement):
            self._check_block(node.try_body)
            if node.catch_body is not None:
                if node.catch_name is not None:
                    self._define(node.catch_name, ANY)
                self._check_block(node.catch_body)
            if node.finally_body is not None:
                self._check_block(node.finally_body)
        elif isinstance(node, ImportStatement):
            self._check_import(node)

    def _check_variable_declaration(self, node: VariableDeclaration) -> None:
        value_type = self._infer(node.initializer)
        if node.declared_type is None:
            if self.strict:
                self.bag.error(
                    ErrorCode.MISSING_ANNOTATION,
                    f"المتغيّر '{node.name}' محتاج تعليق نوع في الوضع الصارم",
                    node.name_span,
                    suggestion=f"خلي {node.name} : رقم = ...",
                )
            self._define(node.name, value_type, span=node.name_span)
            return
        declared = self._resolve_annotation(node.declared_type)
        if not self._compatible(declared, value_type):
            self._mismatch(declared, value_type, node.initializer.span, "تعريف متغير")
        # the declared type wins when present, so later uses are checked against it
        self._define(node.name, declared, span=node.name_span)

    def _check_assignment(self, node: Assignment) -> None:
        value_type = self._infer(node.value)
        existing = self._lookup(node.target, node.target_span)
        if not self._compatible(existing, value_type):
            self._mismatch(existing, value_type, node.value.span, "إسناد لمتغير")
        elif existing == ANY:
            # keep a concrete type if we learn one for a previously-any variable
            self._define(node.target, value_type, span=node.target_span)

    def _check_function(self, node: FunctionDeclaration) -> None:
        for decorator in node.decorators:
            decorator_type = self._infer(decorator)
            if decorator_type not in (FUNCTION, ANY):
                self._mismatch(FUNCTION, decorator_type, decorator.span, "مزخرف")
        parameter_types = self._parameter_types(node, node.name, label="الدالة")
        return_type = self._return_type(
            node.return_type, node.name, "الدالة", node.name_span
        )
        self._define(
            node.name,
            FUNCTION,
            kind="function",
            span=node.name_span,
            signature=_FunctionSignature(parameter_types, return_type),
        )

        self.scopes.append(Scope(self.scopes[-1], label=f"function {node.name}"))
        for parameter, parameter_type in zip(
            node.parameters, parameter_types, strict=True
        ):
            self._define(parameter.name, parameter_type, kind="parameter")
        self._return_types.append(return_type)
        self._check_block(node.body)
        self._return_types.pop()
        self.scopes.pop()

    def _parameter_types(
        self,
        node: FunctionDeclaration | MethodDeclaration | LambdaExpression,
        name: str,
        *,
        label: str,
    ) -> list[Type]:
        types: list[Type] = []
        for parameter in node.parameters:
            if parameter.declared_type is None:
                if self.strict and not isinstance(node, LambdaExpression):
                    self.bag.error(
                        ErrorCode.MISSING_ANNOTATION,
                        f"المعامل '{parameter.name}' في {label} '{name}' "
                        "محتاج تعليق نوع",
                        parameter.span,
                        suggestion=f"{parameter.name} : رقم",
                    )
                types.append(ANY)
            else:
                types.append(self._resolve_annotation(parameter.declared_type))
        return types

    def _return_type(
        self,
        annotation: TypeName | None,
        name: str,
        label: str,
        span: Span,
    ) -> Type:
        if annotation is None:
            if self.strict:
                self.bag.error(
                    ErrorCode.MISSING_ANNOTATION,
                    f"{label} '{name}' محتاجة نوع إرجاع في الوضع الصارم",
                    span,
                    suggestion="حدّد نوع الإرجاع، مثال: : رقم (أو : فراغ)",
                )
            return ANY
        return self._resolve_annotation(annotation)

    def _check_class(self, node: ClassDeclaration) -> None:
        self._define(node.name, CLASS, kind="class", span=node.name_span)
        inherited = dict(self._class_methods.get(node.base_name or "", {}))
        for method in node.methods:
            inherited[(method.name, method.is_static)] = method
        self._class_methods[node.name] = inherited

        for method in node.methods:
            self._check_method(method, has_base=node.base_name is not None)
        for interface in node.interfaces:
            signatures = self._interfaces.get(interface.name)
            if signatures is None:
                continue  # imported interface: checked at runtime
            for signature in signatures:
                implementation = inherited.get((signature.name, signature.is_static))
                if implementation is None or implementation.is_private:
                    self.bag.error(
                        ErrorCode.MISSING_INTERFACE_MEMBER,
                        f"الصنف '{node.name}' ناقص طريقة "
                        f"'{signature.name}' المطلوبة من واجهة "
                        f"'{interface.name}'",
                        signature.name_span,
                        suggestion="ضيف الطريقة بنفس الاسم والتوقيع",
                    )
                    continue
                if not self._signature_matches(signature, implementation):
                    self.bag.error(
                        ErrorCode.MISSING_INTERFACE_MEMBER,
                        f"طريقة '{signature.name}' في '{node.name}' "
                        f"مش مطابقة لتوقيع واجهة '{interface.name}'",
                        signature.name_span,
                        suggestion="وحّد عدد المعاملات وأنواعها ونوع الإرجاع",
                    )

    def _check_interface(self, node: InterfaceDeclaration) -> None:
        self._define(node.name, CLASS, kind="interface", span=node.name_span)
        self._interfaces[node.name] = node.methods
        for method in node.methods:
            self._check_method(method, has_base=False, is_abstract=True)

    @classmethod
    def _signature_matches(
        cls, signature: MethodDeclaration, implementation: MethodDeclaration
    ) -> bool:
        if len(signature.parameters) != len(implementation.parameters):
            return False
        for expected, actual in zip(
            signature.parameters, implementation.parameters, strict=True
        ):
            if expected.declared_type is None:
                continue
            if not cls._same_annotation(expected.declared_type, actual.declared_type):
                return False
        expected_return = signature.return_type
        if expected_return is None:
            return True
        return cls._same_annotation(expected_return, implementation.return_type)

    def _check_method(
        self,
        node: MethodDeclaration,
        *,
        has_base: bool,
        is_abstract: bool = False,
    ) -> None:
        parameter_types = self._parameter_types(node, node.name, label="الطريقة")
        return_type = self._return_type(
            node.return_type, node.name, "الطريقة", node.name_span
        )
        self.scopes.append(Scope(self.scopes[-1], label=f"method {node.name}"))
        for parameter, parameter_type in zip(
            node.parameters, parameter_types, strict=True
        ):
            self._define(parameter.name, parameter_type, kind="parameter")
        if not node.is_static and not is_abstract:
            self._define("انا", CLASS, kind="parameter")
            if has_base:
                self._define("الأساس", CLASS, kind="parameter")
        self._return_types.append(return_type)
        self._check_block(node.body)
        self._return_types.pop()
        self.scopes.pop()

    def _check_return(self, node: ReturnStatement) -> None:
        actual = self._infer(node.value) if node.value is not None else NULL
        if self._return_types:
            expected = self._return_types[-1]
            span = node.value.span if node.value is not None else node.span
            if not self._compatible(expected, actual):
                self._mismatch(expected, actual, span, "قيمة الإرجاع")

    def _check_match(self, node: MatchStatement) -> None:
        subject = self._infer(node.subject)
        for case in node.cases:
            if case.pattern.literal is not None:
                literal = self._infer(case.pattern.literal)
                if subject != ANY and not is_assignable(subject, literal):
                    self._mismatch(
                        subject, literal, case.pattern.literal.span, "نمط لا يطابق"
                    )
            if case.guard is not None:
                self._infer(case.guard)
            if case.pattern.binding is not None:
                self._define(case.pattern.binding, subject)
            self._check_block(case.body)
        if node.else_body is not None:
            self._check_block(node.else_body)

    @staticmethod
    def _iterable_element(iterable: Type) -> Type:
        if iterable.kind == "قائمة":
            return iterable.arguments[0]
        if iterable.kind == "قاموس":
            return iterable.arguments[0]  # the interpreter iterates keys
        if iterable.kind == "نص":
            return TEXT
        return ANY

    # --------------------------------------------------------------- imports

    def _check_import(self, node: ImportStatement) -> None:
        if self.base_dir is None:
            return  # single-file analysis: exports are dynamically typed
        exports = self._load_module(node.path, node.path_span)
        if exports is None:
            return
        if node.names is not None:
            for name in node.names:
                symbol = exports.get(name)
                if symbol is None:
                    self.bag.error(
                        ErrorCode.UNKNOWN_IMPORTED_NAME,
                        f"الاسم '{name}' مش موجود في الوحدة '{node.path}'",
                        node.path_span,
                        suggestion="تأكد إن الاسم معرّف في الملف المستورد",
                    )
                    continue
                self._define(
                    name,
                    symbol.type,
                    kind=symbol.kind,
                    span=node.path_span,
                    signature=symbol.signature,
                )
        elif node.alias is not None:
            self._namespaces[node.alias] = exports
            self._define(
                node.alias, map_of(TEXT, ANY), kind="namespace", span=node.path_span
            )
        else:
            for name, symbol in exports.items():
                self._define(
                    name,
                    symbol.type,
                    kind=symbol.kind,
                    span=node.path_span,
                    signature=symbol.signature,
                )

    def _load_module(self, path: str, span: Span) -> dict[str, Symbol] | None:
        # Imported lazily: the runtime resolver is the single source of truth
        # for path rules (absolute paths and ``..`` escapes are refused there).
        from al_arabiya.runtime.modules import ModuleLoader

        try:
            abs_path = ModuleLoader(write=lambda _text: None).locate(
                path, self.base_dir or ".", span
            )
        except ArabiyaRuntimeError as exc:
            self.bag.add(exc.diagnostic)
            return None

        cached = self._module_cache.get(abs_path)
        if cached is not None:
            return cached
        name = os.path.basename(abs_path)
        if abs_path in self._module_loading:
            self.bag.error(
                ErrorCode.MODULE_UNRESOLVED,
                f"استيراد دائري: '{name}' بيستورد نفسه",
                span,
                suggestion="شيل الاستيراد الدائري بين الملفات",
            )
            return None
        try:
            with open(abs_path, encoding="utf-8-sig") as handle:
                text = handle.read()
        except OSError:
            self.bag.error(
                ErrorCode.MODULE_UNRESOLVED,
                f"مش لاقي الملف المستورد: {abs_path}",
                span,
                suggestion="تأكد إن اسم الملف ومكانه صح",
            )
            return None

        from al_arabiya.compiler.frontend import compile_source

        result = compile_source(text, abs_path)
        if result.program is None:
            first = next((d for d in result.diagnostics if d.is_error), None)
            detail = first.message if first is not None else "خطأ في الترجمة"
            self.bag.error(
                ErrorCode.MODULE_UNRESOLVED,
                f"فيه خطأ في الوحدة '{name}': {detail}",
                span,
                suggestion="صلّح أخطاء الملف المستورد الأول",
            )
            return None

        child = TypeChecker(
            strict=self.strict,
            base_dir=os.path.dirname(abs_path),
            filename=abs_path,
            _module_cache=self._module_cache,
            _module_loading=self._module_loading,
        )
        self._module_loading.add(abs_path)
        try:
            child.check(result.program)
        finally:
            self._module_loading.discard(abs_path)
        if child.bag.has_errors:
            first_error = next((d for d in child.bag if d.is_error), None)
            detail = first_error.message if first_error is not None else ""
            self.bag.error(
                ErrorCode.MODULE_UNRESOLVED,
                f"فيه أخطاء أنواع في الوحدة '{name}': {detail}",
                span,
                suggestion="صلّح أخطاء الأنواع في الملف المستورد الأول",
            )
        exports = child.exports()
        self._module_cache[abs_path] = exports
        return exports

    # ------------------------------------------------------------ expressions

    def _infer(self, node: Expression) -> Type:
        if isinstance(node, Literal):
            value = node.value
            if isinstance(value, bool):
                return BOOLEAN
            if isinstance(value, (int, float)):
                return NUMBER
            return TEXT
        if isinstance(node, NullLiteral):
            return NULL
        if isinstance(node, LambdaExpression):
            parameter_types = self._parameter_types(node, "<مجهولة>", label="الدالة")
            return_type = self._resolve_annotation(node.return_type)
            self.scopes.append(Scope(self.scopes[-1], label="lambda"))
            for parameter, parameter_type in zip(
                node.parameters, parameter_types, strict=True
            ):
                self._define(parameter.name, parameter_type, kind="parameter")
            self._return_types.append(return_type)
            self._check_block(node.body)
            self._return_types.pop()
            self.scopes.pop()
            return FUNCTION
        if isinstance(node, ListLiteral):
            element_types = [self._infer(element) for element in node.elements]
            return list_of(union(*element_types) if element_types else ANY)
        if isinstance(node, MapLiteral):
            key_types = [self._infer(key) for key, _ in node.entries]
            value_types = [self._infer(value) for _, value in node.entries]
            return map_of(
                union(*key_types) if key_types else ANY,
                union(*value_types) if value_types else ANY,
            )
        if isinstance(node, Identifier):
            return self._lookup(node.name, node.span)
        if isinstance(node, UnaryExpression):
            operand = self._infer(node.operand)
            if not is_numeric(operand):
                self._mismatch(NUMBER, operand, node.operand.span, "علامة الناقص")
            return NUMBER
        if isinstance(node, BinaryExpression):
            return self._infer_binary(node)
        if isinstance(node, CallExpression):
            return self._infer_call(node)
        if isinstance(node, IndexExpression):
            return self._infer_index(node)
        if isinstance(node, MemberExpression):
            self._infer(node.target)
            return ANY
        return ANY

    def _infer_binary(self, node: BinaryExpression) -> Type:
        left = self._infer(node.left)
        right = self._infer(node.right)
        operator = node.operator

        if operator in ("و", "أو", "==", "!=", "<", ">", "<=", ">="):
            return BOOLEAN
        if operator == "+":
            if is_numeric(left) and is_numeric(right):
                return NUMBER
            if is_textual(left) or is_textual(right):
                return TEXT
            self._mismatch(
                NUMBER if is_numeric(left) else TEXT,
                right if is_numeric(left) else left,
                node.span,
                "الجمع",
            )
            return ANY
        if operator in ("-", "*", "/", "%"):
            if is_numeric(left) and is_numeric(right):
                return NUMBER
            bad = right if is_numeric(left) else left
            self._mismatch(NUMBER, bad, node.span, f"العملية '{operator}'")
            return ANY
        return ANY

    def _callee_symbol(self, callee: Expression) -> Symbol | None:
        if isinstance(callee, Identifier):
            return self._lookup_symbol(callee.name)
        if isinstance(callee, IndexExpression) and isinstance(
            callee.target, Identifier
        ):
            exports = self._namespaces.get(callee.target.name)
            if exports is not None and isinstance(callee.index, Literal):
                key = callee.index.value
                if isinstance(key, str):
                    return exports.get(key)
        return None

    def _infer_call(self, node: CallExpression) -> Type:
        argument_types = [self._infer(argument) for argument in node.arguments]
        symbol = self._callee_symbol(node.callee)
        if symbol is not None and symbol.signature is not None:
            self._apply_signature(
                symbol.name, symbol.signature, argument_types, node.arguments, node.span
            )
            return symbol.signature.returns
        self._infer(node.callee)
        return ANY

    def _apply_signature(
        self,
        name: str,
        signature: _FunctionSignature,
        argument_types: list[Type],
        arguments: list[Expression],
        span: Span,
    ) -> None:
        if signature.parameters is None:
            return  # builtin: arity checked at runtime
        if len(arguments) != len(signature.parameters):
            self.bag.error(
                ErrorCode.ARGUMENT_COUNT,
                f"'{name}' محتاجة {len(signature.parameters)} "
                f"مدخل، بس وصلها {len(arguments)}",
                span,
                suggestion=f"نادِ '{name}' بالعدد الصحيح من القيم",
            )
            return
        for argument, actual, expected in zip(
            arguments, argument_types, signature.parameters, strict=True
        ):
            if not self._compatible(expected, actual):
                self._mismatch(expected, actual, argument.span, "مدخل الدالة")

    def _infer_index(self, node: IndexExpression) -> Type:
        namespace = self._namespace_value(node)
        if namespace is not None:
            return namespace

        target = self._infer(node.target)
        index = self._infer(node.index)

        if target.kind == "قائمة":
            if not is_numeric(index):
                self._mismatch(NUMBER, index, node.index.span, "فهرس")
            return target.arguments[0]
        if target.kind == "قاموس":
            key_type, value_type = target.arguments
            if not is_assignable(key_type, index):
                self._mismatch(key_type, index, node.index.span, "مفتاح القاموس")
            return value_type
        if target.kind == "نص":
            if not is_numeric(index):
                self._mismatch(NUMBER, index, node.index.span, "فهرس")
            return TEXT
        if target != ANY:
            self._mismatch(target, TEXT, node.target.span, "فهرسة")
        return ANY

    def _namespace_value(self, node: IndexExpression) -> Type | None:
        """Type of ``ر["اسم"]`` where ``ر`` is an imported module alias."""
        if not isinstance(node.target, Identifier):
            return None
        exports = self._namespaces.get(node.target.name)
        if exports is None:
            return None
        if isinstance(node.index, Literal) and isinstance(node.index.value, str):
            symbol = exports.get(node.index.value)
            if symbol is None:
                self.bag.error(
                    ErrorCode.UNKNOWN_IMPORTED_NAME,
                    f"الاسم '{node.index.value}' مش موجود في الوحدة "
                    f"'{node.target.name}'",
                    node.index.span,
                    suggestion="تأكد إن الاسم معرّف في الملف المستورد",
                )
                return ANY
            return symbol.type
        return ANY


def check_types(
    program: Program,
    bag: DiagnosticBag | None = None,
    *,
    strict: bool = False,
    base_dir: str | None = None,
    filename: str | None = None,
) -> DiagnosticBag:
    """Type-check ``program`` and return the bag.

    ``base_dir`` enables module-aware analysis: imports are resolved, their
    modules type-checked once, and their exported names bound with types.
    Without it the checker behaves exactly as before (single-file, gradual).
    """
    return TypeChecker(
        bag, strict=strict, base_dir=base_dir, filename=filename
    ).check(program)
