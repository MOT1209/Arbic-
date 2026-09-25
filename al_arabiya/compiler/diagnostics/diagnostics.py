"""The central diagnostics system.

Every layer of the compiler reports problems by appending a
:class:`Diagnostic` to a :class:`DiagnosticBag` — never by printing or
raising bare strings.  The CLI (or an editor, or the REPL) decides how to
render them via :func:`render_diagnostic`.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum

from al_arabiya.compiler.diagnostics.source import SourceFile
from al_arabiya.compiler.lexer.positions import Span

__all__ = [
    "Diagnostic",
    "DiagnosticBag",
    "Severity",
    "render_diagnostic",
    "render_diagnostics",
]


class Severity(StrEnum):
    """Diagnostic severity; the value is the Arabic word shown to users."""

    ERROR = "خطأ"
    WARNING = "تحذير"
    INFO = "معلومة"
    HINT = "تلميح"

    @property
    def is_error(self) -> bool:
        return self is Severity.ERROR


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One problem (or note) anchored to a source span."""

    code: str
    severity: Severity
    message: str
    span: Span
    suggestion: str | None = None
    notes: tuple[str, ...] = ()

    @property
    def is_error(self) -> bool:
        return self.severity.is_error

    @property
    def location(self) -> str:
        return f"{self.span.start.line}:{self.span.start.column}"


class DiagnosticBag:
    """Accumulates diagnostics; de-duplicates and caps them."""

    def __init__(self, limit: int = 100) -> None:
        self._items: list[Diagnostic] = []
        self._seen: set[tuple[str, int, str]] = set()
        self._limit = limit
        self._truncated = False

    def add(self, diagnostic: Diagnostic) -> None:
        key = (diagnostic.code, diagnostic.span.start.offset, diagnostic.message)
        if key in self._seen:
            return
        if len(self._items) >= self._limit:
            self._truncated = True
            return
        self._seen.add(key)
        self._items.append(diagnostic)

    def error(
        self,
        code: str,
        message: str,
        span: Span,
        *,
        suggestion: str | None = None,
        notes: tuple[str, ...] = (),
    ) -> Diagnostic:
        diagnostic = Diagnostic(
            code=code,
            severity=Severity.ERROR,
            message=message,
            span=span,
            suggestion=suggestion,
            notes=notes,
        )
        self.add(diagnostic)
        return diagnostic

    def warning(
        self,
        code: str,
        message: str,
        span: Span,
        *,
        suggestion: str | None = None,
    ) -> Diagnostic:
        diagnostic = Diagnostic(
            code=code,
            severity=Severity.WARNING,
            message=message,
            span=span,
            suggestion=suggestion,
        )
        self.add(diagnostic)
        return diagnostic

    @property
    def has_errors(self) -> bool:
        return any(item.is_error for item in self._items)

    @property
    def has_warnings(self) -> bool:
        return any(item.severity is Severity.WARNING for item in self._items)

    @property
    def truncated(self) -> bool:
        return self._truncated

    @property
    def errors(self) -> list[Diagnostic]:
        return [item for item in self._items if item.is_error]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [item for item in self._items if item.severity is Severity.WARNING]

    def sorted(self) -> list[Diagnostic]:
        """Diagnostics ordered by source position."""
        return sorted(self._items, key=lambda item: (item.span.start.offset, item.code))

    def extend(self, diagnostics: Iterable[Diagnostic]) -> None:
        for diagnostic in diagnostics:
            self.add(diagnostic)

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)


def _caret_line(line_text: str, column: int, length: int) -> str:
    prefix = max(0, column - 1)
    visible = max(0, len(line_text) - prefix)
    carets = max(1, min(length, visible)) if visible else max(1, length)
    return " " * prefix + "^" * carets


def render_diagnostic(diagnostic: Diagnostic, source: SourceFile) -> str:
    """Render a diagnostic in the canonical Arabic RTL layout.

    .. code-block:: text

        خطأ E1001

        main.arb:4:12

        خلي العمر = "أحمد"
                   ^^^^^^^

        القيمة النصية لا تتوافق مع النوع المتوقع.

        اقتراح: استخدم رقمًا بدل النص
    """
    start = diagnostic.span.start
    line_text = source.line_text(start.line).replace("\t", " ")
    length = min(
        diagnostic.span.length,
        max(1, len(line_text) - max(0, start.column - 1)) or 1,
    )
    parts = [
        f"{diagnostic.severity} {diagnostic.code}",
        "",
        f"{source.name}:{start.line}:{start.column}",
        "",
        line_text,
        _caret_line(line_text, start.column, length),
        "",
        diagnostic.message,
    ]
    if diagnostic.suggestion:
        parts.extend(["", f"اقتراح: {diagnostic.suggestion}"])
    for note in diagnostic.notes:
        parts.extend(["", f"ملاحظة: {note}"])
    return "\n".join(parts)


def render_diagnostics(
    diagnostics: Iterable[Diagnostic], source: SourceFile, *, limit: int | None = None
) -> str:
    """Render every diagnostic, optionally capped at ``limit`` entries."""
    rendered: list[str] = []
    for index, diagnostic in enumerate(diagnostics):
        if limit is not None and index >= limit:
            rendered.append(f"... وأخطاء أخرى ({index}+).")
            break
        rendered.append(render_diagnostic(diagnostic, source))
    return "\n\n".join(rendered)
