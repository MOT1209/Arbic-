"""Bytecode containers: a :class:`Chunk` of code plus compiled functions."""

from __future__ import annotations

from dataclasses import dataclass, field

from al_arabiya.compiler.lexer.positions import Span
from al_arabiya.runtime.values import Value

__all__ = ["Chunk", "ImportSpec", "VMFunction"]


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
    """A compiled function: its name, arity, chunk and local-slot count."""

    name: str
    arity: int
    chunk: Chunk
    local_count: int
