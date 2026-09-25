"""Token model: types, keyword table and the :class:`Token` dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from al_arabiya.compiler.lexer.positions import Span

__all__ = ["KEYWORDS", "Token", "TokenType"]


class TokenType(Enum):
    """Every lexical unit the language understands.

    Keyword members carry their Arabic word as the value, which makes the
    parser's matching explicit and type-safe.  Adding a keyword is a
    one-line change here plus one row in the keyword table of the lexer.
    """

    # --- structure ---
    EOF = "EOF"
    NEWLINE = "NEWLINE"

    # --- literals ---
    IDENTIFIER = "IDENTIFIER"
    NUMBER = "NUMBER"
    STRING = "STRING"

    # --- keywords (single words; multi-word operators are joined by the parser) ---
    KW_PRINT = "اطبع"
    KW_LET = "خلي"
    KW_IF = "لو"
    KW_ELSE = "غير"
    KW_THAT = "كده"
    KW_END = "خلاص"
    KW_REPEAT = "كرر"
    KW_TIMES = "مرات"
    KW_ONCE = "مرة"
    KW_WHILE = "طالما"
    KW_TRUE = "صح"
    KW_FALSE = "غلط"
    KW_GREATER = "أكبر"
    KW_LESS = "أصغر"
    KW_FROM = "من"
    KW_EQUAL_WORD = "يساوي"
    KW_NOT = "مش"
    KW_AND = "و"
    KW_OR = "أو"
    KW_ADD = "زائد"
    KW_SUB = "ناقص"
    KW_MUL = "في"
    KW_DIV = "على"

    # --- operators ---
    PLUS = "+"
    MINUS = "-"
    STAR = "*"
    SLASH = "/"
    PERCENT = "%"
    ASSIGN = "="
    EQ_EQUAL = "=="
    NOT_EQUAL = "!="
    LESS = "<"
    GREATER = ">"
    LESS_EQUAL = "<="
    GREATER_EQUAL = ">="

    # --- delimiters ---
    LPAREN = "("
    RPAREN = ")"
    LBRACKET = "["
    RBRACKET = "]"
    LBRACE = "{"
    RBRACE = "}"
    COMMA = ","
    COLON = ":"
    DOT = "."


#: Arabic word → token type (built once from the ``KW_`` members above).
KEYWORDS: dict[str, TokenType] = {
    member.value: member for member in TokenType if member.name.startswith("KW_")
}


@dataclass(frozen=True, slots=True)
class Token:
    """One lexical unit with its exact source location."""

    type: TokenType
    value: str | int | float | None
    span: Span
    raw: str

    @property
    def line(self) -> int:
        return self.span.start.line

    @property
    def column(self) -> int:
        return self.span.start.column

    @property
    def length(self) -> int:
        return self.span.length

    def describe(self) -> str:
        """Human-readable (Arabic) description used in error messages."""
        if self.type is TokenType.EOF:
            return "نهاية الملف"
        if self.type is TokenType.NEWLINE:
            return "نهاية السطر"
        if self.raw:
            return f"'{self.raw}'"
        return f"'{self.type.value}'"
