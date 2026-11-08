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
    from al_arabiya.compiler.ast.nodes import FunctionDeclaration
    from al_arabiya.runtime.interpreter.environment import Environment

__all__ = [
    "NULL",
    "ArabiyaFunction",
    "BuiltinError",
    "NativeFunction",
    "Null",
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
class NativeFunction:
    """A builtin implemented in Python.

    ``arity`` is the exact argument count, or ``-1`` for a variadic builtin
    that validates its own arguments.
    """

    name: str
    arity: int
    fn: Callable[..., Value]


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
    | NativeFunction
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
    if isinstance(value, (ArabiyaFunction, NativeFunction)):
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
    if isinstance(value, (ArabiyaFunction, NativeFunction)):
        return True
    return len(value) > 0


def describe_value(value: Value) -> str:
    if isinstance(value, bool):
        return "منطقي (صح/غلط)"
    if isinstance(value, Null):
        return "فراغ"
    if isinstance(value, (int, float)):
        return "رقم"
    if isinstance(value, (ArabiyaFunction, NativeFunction)):
        return "دالة"
    if isinstance(value, list):
        return "قائمة"
    if isinstance(value, dict):
        return "قاموس"
    return "نص"
