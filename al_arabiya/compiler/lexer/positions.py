"""Source positions and spans shared by tokens, AST nodes and diagnostics.

``line`` and ``column`` are 1-based (as humans count them), ``offset`` is a
0-based index into the source text measured in Unicode code points.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Position", "Span"]


@dataclass(frozen=True, slots=True, order=True)
class Position:
    """A single point inside a source file."""

    offset: int
    line: int
    column: int

    def __str__(self) -> str:
        return f"{self.line}:{self.column}"


@dataclass(frozen=True, slots=True)
class Span:
    """A half-open range ``[start, end)`` of source text."""

    start: Position
    end: Position

    @property
    def length(self) -> int:
        return max(0, self.end.offset - self.start.offset)

    @classmethod
    def covering(cls, first: Span, last: Span) -> Span:
        """Merge two spans into one that covers both."""
        return cls(first.start, last.end)

    def __str__(self) -> str:
        return str(self.start)
