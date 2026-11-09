"""The static type model used by the gradual checker.

A type is an immutable value so signatures and symbol tables can share it and
compare it with ``==``.  Surface names are Arabic, exactly as users write them
in annotations:

``رقم`` · ``نص`` · ``منطقي`` · ``فراغ`` · ``قائمة[T]`` · ``قاموس[K, V]`` ·
``اختياري[T]`` · ``أو`` unions · ``دالة`` · ``صنف`` · ``أي``

``أي`` (any) is the gradual escape hatch: it is compatible with every type in
both directions, so un-annotated code is never rejected.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ANY",
    "BOOLEAN",
    "CLASS",
    "FUNCTION",
    "NULL",
    "NUMBER",
    "TEXT",
    "Type",
    "is_assignable",
    "is_numeric",
    "is_textual",
    "join",
    "list_of",
    "map_of",
    "optional",
    "render",
    "union",
]

KIND_NUMBER = "رقم"
KIND_TEXT = "نص"
KIND_BOOL = "منطقي"
KIND_NULL = "فراغ"
KIND_LIST = "قائمة"
KIND_MAP = "قاموس"
KIND_FUNCTION = "دالة"
KIND_CLASS = "صنف"
KIND_ANY = "أي"
KIND_UNION = "أو"

#: Names a user may write in ``: <type>`` before adding generic arguments.
SIMPLE_TYPE_NAMES = frozenset(
    {
        KIND_NUMBER,
        KIND_TEXT,
        KIND_BOOL,
        KIND_NULL,
        KIND_FUNCTION,
        KIND_CLASS,
        KIND_ANY,
    }
)


@dataclass(frozen=True, slots=True)
class Type:
    """One static type.

    ``arguments`` holds generic arguments (one element for ``قائمة``, two for
    ``قاموس``), and ``members`` is only used by unions.  Keeping both fields
    on one frozen dataclass makes equality, hashing and caching trivial.
    """

    kind: str
    arguments: tuple[Type, ...] = ()
    members: tuple[Type, ...] = ()

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return render(self)


NUMBER = Type(KIND_NUMBER)
TEXT = Type(KIND_TEXT)
BOOLEAN = Type(KIND_BOOL)
NULL = Type(KIND_NULL)
FUNCTION = Type(KIND_FUNCTION)
CLASS = Type(KIND_CLASS)
ANY = Type(KIND_ANY)


def list_of(item: Type = ANY) -> Type:
    """``قائمة[item]``; a bare ``قائمة`` is ``قائمة[أي]``."""
    return Type(KIND_LIST, (item,))


def map_of(key: Type = ANY, value: Type = ANY) -> Type:
    """``قاموس[key، value]``; a bare ``قاموس`` maps any key to any value."""
    return Type(KIND_MAP, (key, value))


def union(*types: Type) -> Type:
    """Build a normalised union: flattened, de-duplicated, garbage-collected.

    ``أي`` absorbs the whole union (it is compatible with everything), and a
    single remaining member collapses back to that member.
    """
    flat: list[Type] = []
    for item in types:
        candidates = item.members if item.kind == KIND_UNION else (item,)
        for candidate in candidates:
            if candidate == ANY:
                return ANY
            if candidate not in flat:
                flat.append(candidate)
    if not flat:
        return NULL
    if len(flat) == 1:
        return flat[0]
    return Type(KIND_UNION, members=tuple(flat))


def optional(inner: Type) -> Type:
    """``اختياري[inner]`` — ``inner`` or ``فراغ``."""
    return union(inner, NULL)


def _is_optional(t: Type) -> bool:
    return t.kind == KIND_UNION and len(t.members) == 2 and NULL in t.members


def render(t: Type) -> str:
    """Render a type the way the user would write it (used in diagnostics)."""
    if t.kind == KIND_LIST:
        return f"قائمة[{render(t.arguments[0])}]"
    if t.kind == KIND_MAP:
        return f"قاموس[{render(t.arguments[0])}، {render(t.arguments[1])}]"
    if t.kind == KIND_UNION:
        if _is_optional(t):
            inner = next(member for member in t.members if member != NULL)
            return f"اختياري[{render(inner)}]"
        return " أو ".join(render(member) for member in t.members)
    return t.kind


def is_numeric(t: Type) -> bool:
    """Is every value of ``t`` a number (``أي`` counts: it may be one)?"""
    if t.kind == KIND_UNION:
        return all(is_numeric(member) for member in t.members)
    return t.kind in (KIND_NUMBER, KIND_ANY)


def is_textual(t: Type) -> bool:
    """Is every value of ``t`` text (``أي`` counts: it may be one)?"""
    if t.kind == KIND_UNION:
        return all(is_textual(member) for member in t.members)
    return t.kind in (KIND_TEXT, KIND_ANY)


def _invariant_list(expected: Type, actual: Type) -> bool:
    """Lists are mutable, so their element types must match both ways."""
    expected_item = expected.arguments[0]
    actual_item = actual.arguments[0]
    return is_assignable(expected_item, actual_item) and is_assignable(
        actual_item, expected_item
    )


def _invariant_map(expected: Type, actual: Type) -> bool:
    expected_key, expected_value = expected.arguments
    actual_key, actual_value = actual.arguments
    keys = is_assignable(expected_key, actual_key) and is_assignable(
        actual_key, expected_key
    )
    values = is_assignable(expected_value, actual_value) and is_assignable(
        actual_value, expected_value
    )
    return keys and values


def is_assignable(expected: Type, actual: Type) -> bool:
    """Gradual assignability: can a value of ``actual`` flow into ``expected``?"""
    if expected == ANY or actual == ANY:
        return True
    if expected == actual:
        return True
    if expected.kind == KIND_UNION:
        return any(is_assignable(member, actual) for member in expected.members)
    if actual.kind == KIND_UNION:
        return all(is_assignable(expected, member) for member in actual.members)
    if expected.kind == KIND_LIST and actual.kind == KIND_LIST:
        return _invariant_list(expected, actual)
    if expected.kind == KIND_MAP and actual.kind == KIND_MAP:
        return _invariant_map(expected, actual)
    return False


def join(left: Type, right: Type) -> Type:
    """The type of a value that could be either side (list/map inference)."""
    if left == right:
        return left
    if is_assignable(left, right):
        return left
    if is_assignable(right, left):
        return right
    return union(left, right)
