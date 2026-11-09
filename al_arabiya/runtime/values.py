"""Runtime value model shared by the interpreter and the builtin library.

Kept deliberately free of imports from the interpreter or the builtins so it
can be the common leaf both of them depend on (no import cycles).  It owns the
``Value`` union, the callable value types, the ``NULL`` singleton and the
small set of value helpers (:func:`format_value`, :func:`is_truthy`,
:func:`describe_value`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from al_arabiya.compiler.ast.nodes import (
        ClassDeclaration,
        FunctionDeclaration,
        InterfaceDeclaration,
        LambdaExpression,
        MethodDeclaration,
    )
    from al_arabiya.runtime.interpreter.environment import Environment

__all__ = [
    "NULL",
    "ArabiyaFunction",
    "BoundMethod",
    "BuiltinError",
    "ClassValue",
    "InstanceValue",
    "InterfaceValue",
    "LambdaFunction",
    "NativeFunction",
    "Null",
    "SuperValue",
    "Value",
    "describe_value",
    "format_value",
    "is_truthy",
]


@dataclass(frozen=True, slots=True)
class Null:
    """The single empty value (``فراغ``)."""

    def __str__(self) -> str:
        return "فراغ"


#: The one and only null value.
NULL: Final[Null] = Null()


@dataclass(slots=True)
class ArabiyaFunction:
    """A user-defined function with the scope it was declared in (closure)."""

    declaration: FunctionDeclaration
    closure: Environment

    @property
    def name(self) -> str:
        return self.declaration.name

    @property
    def arity(self) -> int:
        return len(self.declaration.params)


@dataclass(slots=True)
class LambdaFunction:
    """An anonymous function with the scope it was created in (closure)."""

    declaration: LambdaExpression
    closure: Environment

    @property
    def name(self) -> str:
        return "مجهولة"

    @property
    def arity(self) -> int:
        return len(self.declaration.params)


@dataclass(slots=True)
class NativeFunction:
    """A builtin implemented in Python.

    ``arity`` is the exact argument count, or ``-1`` for a variadic builtin
    that validates its own arguments.
    """

    name: str
    arity: int
    fn: Callable[..., Value]


@dataclass(slots=True, eq=False)
class ClassValue:
    """A class declared with ``صنف``, its scope and its single base class."""

    declaration: ClassDeclaration
    closure: Environment
    base: ClassValue | None = None
    interfaces: tuple[InterfaceValue, ...] = ()

    @property
    def name(self) -> str:
        return self.declaration.name

    def is_same_or_descendant_of(self, other: ClassValue) -> bool:
        klass: ClassValue | None = self
        while klass is not None:
            if klass is other:
                return True
            klass = klass.base
        return False

    def private_field_owner(self, name: str) -> ClassValue | None:
        klass: ClassValue | None = self
        while klass is not None:
            if any(field.name == name for field in klass.declaration.private_fields):
                return klass
            klass = klass.base
        return None

    def private_method_owner(
        self, name: str, *, is_static: bool
    ) -> ClassValue | None:
        klass: ClassValue | None = self
        while klass is not None:
            for method in klass.declaration.methods:
                if (
                    method.name == name
                    and method.is_static == is_static
                    and method.is_private
                ):
                    return klass
            klass = klass.base
        return None

    def resolve_instance_method(
        self, name: str
    ) -> tuple[ClassValue, MethodDeclaration] | None:
        """Find an instance method up the inheritance chain."""
        klass: ClassValue | None = self
        while klass is not None:
            for method in klass.declaration.methods:
                if method.name == name and not method.is_static:
                    return klass, method
            klass = klass.base
        return None

    def resolve_instance_method_for(
        self, name: str, current: ClassValue | None
    ) -> tuple[ClassValue, MethodDeclaration] | None:
        """Resolve an instance method, honouring ``خاص`` for the caller."""
        if current is not None and self.is_same_or_descendant_of(current):
            for method in current.declaration.methods:
                if method.name == name and not method.is_static and method.is_private:
                    return current, method
        klass: ClassValue | None = self
        while klass is not None:
            for method in klass.declaration.methods:
                if method.name == name and not method.is_static:
                    if method.is_private and current is not klass:
                        continue
                    return klass, method
            klass = klass.base
        return None

    def resolve_static_method(
        self, name: str
    ) -> tuple[ClassValue, MethodDeclaration] | None:
        """Find a static method up the inheritance chain."""
        klass: ClassValue | None = self
        while klass is not None:
            for method in klass.declaration.methods:
                if method.name == name and method.is_static:
                    return klass, method
            klass = klass.base
        return None

    def resolve_static_method_for(
        self, name: str, current: ClassValue | None
    ) -> tuple[ClassValue, MethodDeclaration] | None:
        """Resolve a static method, honouring ``خاص`` for the caller."""
        if current is not None and self.is_same_or_descendant_of(current):
            for method in current.declaration.methods:
                if method.name == name and method.is_static and method.is_private:
                    return current, method
        klass: ClassValue | None = self
        while klass is not None:
            for method in klass.declaration.methods:
                if method.name == name and method.is_static:
                    if method.is_private and current is not klass:
                        continue
                    return klass, method
            klass = klass.base
        return None


@dataclass(slots=True, eq=False)
class InstanceValue:
    """An object created by calling a :class:`ClassValue`."""

    klass: ClassValue
    fields: dict[str, Value]

    @property
    def class_name(self) -> str:
        return self.klass.name


@dataclass(slots=True, eq=False)
class SuperValue:
    """``الأساس`` inside a method: resolved against the declaring class's base."""

    instance: InstanceValue
    start: ClassValue


@dataclass(slots=True, eq=False)
class InterfaceValue:
    """A ``واجهة`` declaration: signatures only, never instantiated."""

    declaration: InterfaceDeclaration
    closure: Environment

    @property
    def name(self) -> str:
        return self.declaration.name


@dataclass(slots=True, eq=False)
class BoundMethod:
    """A method together with the instance it was read from (``None`` if static)."""

    instance: InstanceValue | None
    method: MethodDeclaration
    declaring: ClassValue

    @property
    def name(self) -> str:
        return self.method.name

    @property
    def arity(self) -> int:
        return len(self.method.params)


class BuiltinError(Exception):
    """Raised by a builtin to signal a runtime problem.

    The interpreter catches it at the call site and turns it into a located
    :class:`~al_arabiya.compiler.diagnostics.diagnostics.Diagnostic`, so
    builtins never need to know about spans.
    """

    def __init__(self, message: str, suggestion: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion


#: Every value the language can hold at runtime (recursive: lists/maps nest).
Value = (
    int
    | float
    | str
    | bool
    | Null
    | ArabiyaFunction
    | LambdaFunction
    | NativeFunction
    | ClassValue
    | InstanceValue
    | BoundMethod
    | SuperValue
    | InterfaceValue
    | list["Value"]
    | dict["Value", "Value"]
)


def format_value(value: Value) -> str:
    """Render a runtime value the way AlArabiya prints it."""
    if isinstance(value, bool):
        return "صح" if value else "غلط"
    if isinstance(value, Null):
        return "فراغ"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, ClassValue):
        return f"<صنف {value.name}>"
    if isinstance(value, InstanceValue):
        return f"<كائن {value.class_name}>"
    if isinstance(value, BoundMethod):
        return f"<دالة {value.name}>"
    if isinstance(value, SuperValue):
        return f"<الأساس {value.start.name}>"
    if isinstance(value, InterfaceValue):
        return f"<واجهة {value.name}>"
    if isinstance(value, (ArabiyaFunction, LambdaFunction, NativeFunction)):
        return f"<دالة {value.name}>"
    if isinstance(value, list):
        return "[" + "، ".join(format_value(item) for item in value) + "]"
    if isinstance(value, dict):
        inner = "، ".join(
            f"{format_value(key)}: {format_value(val)}" for key, val in value.items()
        )
        return "{" + inner + "}"
    return str(value)


def is_truthy(value: Value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, Null):
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(
        value, (ArabiyaFunction, LambdaFunction, NativeFunction, BoundMethod)
    ):
        return True
    if isinstance(value, (ClassValue, InstanceValue, SuperValue, InterfaceValue)):
        return True
    return len(value) > 0


def describe_value(value: Value) -> str:
    if isinstance(value, bool):
        return "منطقي (صح/غلط)"
    if isinstance(value, Null):
        return "فراغ"
    if isinstance(value, (int, float)):
        return "رقم"
    if isinstance(
        value, (ArabiyaFunction, LambdaFunction, NativeFunction, BoundMethod)
    ):
        return "دالة"
    if isinstance(value, InstanceValue):
        return "كائن"
    if isinstance(value, ClassValue):
        return "صنف"
    if isinstance(value, SuperValue):
        return "أساس"
    if isinstance(value, InterfaceValue):
        return "واجهة"
    if isinstance(value, list):
        return "قائمة"
    if isinstance(value, dict):
        return "قاموس"
    return "نص"
