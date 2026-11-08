"""A conservative, whitespace-only formatter.

The formatter deliberately does **not** re-layout code: AlArabiya's lexer
ignores indentation, so only whitespace that cannot appear inside a token is
touched — line endings, leading tabs, trailing spaces, blank-line runs and the
final newline.  Nothing inside a string can be reached that way, because the
lexer never lets a string span a line (an unterminated string is ``E1002``).

Every result is verified before it is offered: the formatted text must lex to
exactly the same tokens (newlines excluded) and still compile cleanly.  If that
check ever fails the original text is returned unchanged, so a formatter bug can
never corrupt a program.
"""

from __future__ import annotations

from dataclasses import dataclass

from al_arabiya.compiler.diagnostics.diagnostics import Diagnostic
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.compiler.lexer.lexer import Lexer
from al_arabiya.compiler.lexer.tokens import TokenType

__all__ = ["FormatResult", "format_source"]

_INDENT = "    "


@dataclass(frozen=True, slots=True)
class FormatResult:
    """The formatted text plus whether anything changed.

    ``diagnostics`` is non-empty only when the input does not compile; such a
    file is never rewritten.
    """

    text: str
    changed: bool
    diagnostics: tuple[Diagnostic, ...] = ()


def _signature(text: str) -> list[tuple[TokenType, object]]:
    """Every token except NEWLINE/EOF, so blank-line policy is not observed."""
    tokens = Lexer(text).tokenize()
    return [
        (token.type, token.value)
        for token in tokens
        if token.type not in (TokenType.NEWLINE, TokenType.EOF)
    ]


def _rewrite(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for raw in normalized.split("\n"):
        stripped = raw.lstrip(" \t")
        leading = raw[: len(raw) - len(stripped)].replace("\t", _INDENT)
        lines.append(leading + stripped.rstrip(" \t"))

    collapsed: list[str] = []
    for line in lines:
        if line == "" and collapsed and collapsed[-1] == "":
            continue
        collapsed.append(line)
    while collapsed and collapsed[-1] == "":
        collapsed.pop()
    return "\n".join(collapsed) + "\n"


def format_source(text: str) -> FormatResult:
    """Format ``text``; return it untouched if it does not compile."""
    result = compile_source(text)
    if result.program is None or result.has_errors:
        return FormatResult(text, False, result.diagnostics)

    formatted = _rewrite(text)
    if formatted == text:
        return FormatResult(text, False)

    try:
        signature = _signature(formatted)
        still_clean = compile_source(formatted).program is not None
    except Exception:  # noqa: BLE001 - never hand back unverified text
        return FormatResult(text, False)
    if not still_clean or signature != _signature(text):
        return FormatResult(text, False)
    return FormatResult(formatted, True)
