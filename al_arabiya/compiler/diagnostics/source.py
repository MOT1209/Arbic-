"""Source file abstraction used by the diagnostics renderer."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["SourceFile"]


@dataclass(slots=True)
class SourceFile:
    """An in-memory source file with lazy line indexing."""

    name: str
    text: str
    _lines: list[str] = field(init=False, repr=False, default_factory=list)

    def __post_init__(self) -> None:
        self._lines = [line.rstrip("\r") for line in self.text.split("\n")]

    @classmethod
    def from_path(cls, path: str) -> SourceFile:
        """Read a UTF-8 source file (BOM tolerant)."""
        with open(path, encoding="utf-8-sig") as handle:
            return cls(name=path, text=handle.read())

    @property
    def line_count(self) -> int:
        return len(self._lines)

    def line_text(self, line: int) -> str:
        """Return the text of a 1-based line; empty string when out of range."""
        if 1 <= line <= len(self._lines):
            return self._lines[line - 1]
        return ""
