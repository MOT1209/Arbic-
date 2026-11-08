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
    EXPECTED_PARAMETER = "E2007"
    INVALID_ASSIGN_TARGET = "E2008"
    TRY_WITHOUT_HANDLER = "E2009"

    # --- warnings (W3xxx) ---
    IMPLICIT_DECLARATION = "W3001"

    # --- static type checking (E5xxx) ---
    TYPE_MISMATCH = "E5001"
    UNKNOWN_TYPE_NAME = "E5002"
    ARGUMENT_COUNT = "E5003"

    # --- runtime (E4xxx) ---
    UNDEFINED_VARIABLE = "E4001"
    DIVISION_BY_ZERO = "E4002"
    TYPE_ERROR = "E4003"
    INVALID_REPEAT_COUNT = "E4004"
    LOOP_LIMIT_EXCEEDED = "E4005"
    ARITY_MISMATCH = "E4006"
    NOT_CALLABLE = "E4007"
    RETURN_OUTSIDE_FUNCTION = "E4008"
    LOOP_CONTROL_OUTSIDE_LOOP = "E4009"
    BUILTIN_ERROR = "E4010"
    INDEX_OUT_OF_RANGE = "E4011"
    KEY_NOT_FOUND = "E4012"
    INVALID_INDEX = "E4013"
    NOT_ITERABLE = "E4014"
    MODULE_NOT_FOUND = "E4015"
    IMPORT_ERROR = "E4016"
    UNHASHABLE_KEY = "E4017"
    UNCAUGHT_ERROR = "E4018"


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
