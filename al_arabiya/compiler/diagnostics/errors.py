"""Error codes and exception types shared by every compiler layer.

Code ranges:

======== ==========================================================
E1xxx    lexical errors
E2xxx    syntax errors
W3xxx    warnings (semantic / usage)
E4xxx    runtime errors
======== ==========================================================
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from al_arabiya.compiler.diagnostics.diagnostics import Diagnostic

__all__ = [
    "AlArabiyaError",
    "ArabiyaRuntimeError",
    "DiagnosticError",
    "ErrorCode",
    "LexError",
    "ParseError",
]


class ErrorCode(StrEnum):
    """Stable, documented error codes shown in every diagnostic."""

    # --- lexical (E1xxx) ---
    UNEXPECTED_CHARACTER = "E1001"
    UNTERMINATED_STRING = "E1002"
    INVALID_ESCAPE = "E1003"
    INVALID_NUMBER = "E1004"
    UNEXPECTED_OPERATOR = "E1005"

    # --- syntax (E2xxx) ---
    EXPECTED_TOKEN = "E2001"
    UNEXPECTED_TOKEN = "E2002"
    UNEXPECTED_EOF = "E2003"
    MISSING_BLOCK_END = "E2004"
    EXPECTED_IDENTIFIER = "E2005"
    EXPECTED_NEWLINE = "E2006"

    # --- warnings (W3xxx) ---
    IMPLICIT_DECLARATION = "W3001"

    # --- runtime (E4xxx) ---
    UNDEFINED_VARIABLE = "E4001"
    DIVISION_BY_ZERO = "E4002"
    TYPE_ERROR = "E4003"
    INVALID_REPEAT_COUNT = "E4004"
    LOOP_LIMIT_EXCEEDED = "E4005"


class AlArabiyaError(Exception):
    """Base class for every error raised by AlArabiya itself."""


class DiagnosticError(AlArabiyaError):
    """An exception carrying a single ready-to-render diagnostic."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class LexError(DiagnosticError):
    """Raised internally by the lexer (rarely — it mostly collects)."""


class ParseError(DiagnosticError):
    """Internal control-flow signal: abort the current statement."""


class ArabiyaRuntimeError(DiagnosticError):
    """A runtime failure with a source location."""
