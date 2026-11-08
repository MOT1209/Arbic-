"""Bytecode containers: a :class:`Chunk` of code plus compiled functions."""

from __future__ import annotations

from dataclasses import dataclass, field

from al_arabiya.compiler.lexer.positions import Span
from al_arabiya.runtime.values import Value

__all__ = ["Cell", "Chunk", "Closure", "ImportSpec", "VMFunction"]


class Cell:
    """A boxed, shared variable slot — the storage a closure captures."""

    __slots__ = ("value",)

    def __init__(self, value: Value) -> None:
        self.value = value


@dataclass(slots=True, frozen=True)
class ImportSpec:
    """A compiled ``استورد`` request, carried in the constant pool.

    ``alias`` and ``names`` are mutually exclusive; both ``None`` means a plain
    import that merges the module's names into the current scope.
    """

    path: str
    alias: str | None = None
    names: tuple[str, ...] | None = None


@dataclass(slots=True)
class Chunk:
    """A flat instruction stream with its constant pool and per-byte spans.

    ``spans[i]`` is the source span of the instruction whose opcode is at
    ``code[i]`` (and ``None`` for operand bytes), so runtime errors can point
    back at the source.
    """

    code: list[int] = field(default_factory=list)
    constants: list[Value] = field(default_factory=list)
    spans: list[Span | None] = field(default_factory=list)


@dataclass(slots=True)
class VMFunction:
    """A compiled function prototype.

    ``upvalues`` describes how to capture each upvalue when a closure of this
    function is created: ``(is_local, index)`` — ``is_local`` captures the
    enclosing frame's local cell at ``index``, otherwise the enclosing
    closure's upvalue at ``index``.  ``captured_slots`` are the local slots
    that must be boxed in a :class:`Cell` because an inner function captures
    them.
    """

    name: str
    arity: int
    chunk: Chunk
    local_count: int
    upvalues: list[tuple[bool, int]] = field(default_factory=list)
    captured_slots: frozenset[int] = frozenset()


@dataclass(slots=True)
class Closure:
    """A runtime function value: a prototype plus its captured cells."""

    proto: VMFunction
    upvalues: list[Cell]
