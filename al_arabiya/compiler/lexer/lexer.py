"""The AlArabiya lexer: source text → tokens.

Fully independent of the parser and the runtime: it only knows about
characters, the keyword table and the diagnostics bag it writes to.
"""

from __future__ import annotations

import unicodedata

from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag
from al_arabiya.compiler.diagnostics.errors import ErrorCode
from al_arabiya.compiler.lexer.positions import Position, Span
from al_arabiya.compiler.lexer.tokens import KEYWORDS, Token, TokenType

__all__ = ["Lexer"]

_ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_EXTENDED_ARABIC_INDIC_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_DIGIT_MAP = str.maketrans(
    _ARABIC_INDIC_DIGITS + _EXTENDED_ARABIC_INDIC_DIGITS,
    "0123456789" * 2,
)
_DECIMAL_SEPARATOR = "٫"  # ARABIC DECIMAL SEPARATOR
_THOUSANDS_SEPARATOR = "٬"  # ARABIC THOUSANDS SEPARATOR

_SIMPLE_ESCAPES: dict[str, str] = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "0": "\0",
    "\\": "\\",
    '"': '"',
    "'": "'",
}

_TWO_CHAR_OPERATORS: dict[str, TokenType] = {
    "==": TokenType.EQ_EQUAL,
    "!=": TokenType.NOT_EQUAL,
    "<=": TokenType.LESS_EQUAL,
    ">=": TokenType.GREATER_EQUAL,
}

_SINGLE_CHAR_TOKENS: dict[str, TokenType] = {
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "%": TokenType.PERCENT,
    "=": TokenType.ASSIGN,
    "<": TokenType.LESS,
    ">": TokenType.GREATER,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    "[": TokenType.LBRACKET,
    "]": TokenType.RBRACKET,
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    ",": TokenType.COMMA,
    "،": TokenType.COMMA,  # ARABIC COMMA (U+060C)
    ":": TokenType.COLON,
    ".": TokenType.DOT,
}


def _is_word_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_word_char(ch: str) -> bool:
    """Letters, digits, underscore and Arabic combining marks (tashkeel)."""
    return ch.isalpha() or ch.isdigit() or ch == "_" or unicodedata.category(ch) in (
        "Mn",
        "Mc",
        "Me",
    )


class Lexer:
    """Scans UTF-8 source text into a list of :class:`Token` objects."""

    def __init__(self, source: str, bag: DiagnosticBag | None = None) -> None:
        self._source = source
        self._bag = bag if bag is not None else DiagnosticBag()
        self._pos = 0
        self._line = 1
        self._column = 1
        self._tokens: list[Token] = []

    @property
    def bag(self) -> DiagnosticBag:
        return self._bag

    def tokenize(self) -> list[Token]:
        """Tokenize the whole source; always ends with an ``EOF`` token."""
        self._tokens = []
        while not self._at_end():
            self._scan_token()
        end = self._here()
        self._tokens.append(Token(TokenType.EOF, None, Span(end, end), ""))
        return self._tokens

    # ------------------------------------------------------------------ utils

    def _at_end(self) -> bool:
        return self._pos >= len(self._source)

    def _peek(self, ahead: int = 0) -> str | None:
        index = self._pos + ahead
        if 0 <= index < len(self._source):
            return self._source[index]
        return None

    def _here(self) -> Position:
        return Position(self._pos, self._line, self._column)

    def _advance(self) -> str:
        ch = self._source[self._pos]
        self._pos += 1
        if ch == "\n":
            self._line += 1
            self._column = 1
        else:
            self._column += 1
        return ch

    def _emit(
        self,
        token_type: TokenType,
        value: str | int | float | None,
        start: Position,
        raw: str,
    ) -> None:
        self._tokens.append(
            Token(token_type, value, Span(start, self._here()), raw)
        )

    def _is_digit(self, ch: str) -> bool:
        return (
            ch in "0123456789"
            or ch in _ARABIC_INDIC_DIGITS
            or ch in _EXTENDED_ARABIC_INDIC_DIGITS
        )

    # ----------------------------------------------------------------- scan

    def _scan_token(self) -> None:
        ch = self._peek()
        assert ch is not None

        if ch == "\n":
            start = self._here()
            self._advance()
            self._emit(TokenType.NEWLINE, "\n", start, "\n")
            return
        if ch in " \t\r":
            self._advance()
            return
        if ch == "#":
            while not self._at_end() and self._peek() != "\n":
                self._advance()
            return
        if ch == '"':
            self._scan_string()
            return
        if self._is_digit(ch):
            self._scan_number()
            return
        if _is_word_start(ch):
            self._scan_word()
            return
        self._scan_symbol()

    def _scan_string(self) -> None:
        start = self._here()
        self._advance()  # opening quote
        parts: list[str] = []
        terminated = False
        while not self._at_end():
            ch = self._peek()
            assert ch is not None
            if ch == '"':
                self._advance()
                terminated = True
                break
            if ch == "\n":
                break
            if ch == "\\":
                parts.append(self._scan_escape())
                continue
            parts.append(self._advance())

        raw = self._source[start.offset : self._pos]
        if not terminated:
            self._bag.error(
                ErrorCode.UNTERMINATED_STRING,
                "النص مقفلش بعلامة تنصيص \"",
                Span(start, self._here()),
                suggestion="اقفل النص بعلامة \" تانية قبل نهاية السطر",
            )
        self._emit(TokenType.STRING, "".join(parts), start, raw)

    def _scan_escape(self) -> str:
        backslash = self._here()
        self._advance()  # backslash
        if self._at_end():
            self._bag.error(
                ErrorCode.INVALID_ESCAPE,
                "character escape ناقص بعد علامة \\",
                Span(backslash, self._here()),
                suggestion="اكتب \\n أو \\\\ أو \" أو استخدم \\u{...}",
            )
            return ""
        ch = self._peek()
        assert ch is not None
        if ch in _SIMPLE_ESCAPES:
            self._advance()
            return _SIMPLE_ESCAPES[ch]
        if ch == "u":
            return self._scan_unicode_escape(backslash)
        self._advance()
        self._bag.error(
            ErrorCode.INVALID_ESCAPE,
            f"escape sequence مش معروف: \\{ch}",
            Span(backslash, self._here()),
            suggestion="الـ escapes المتاحة: \\n \\t \\r \\0 \\\\ \\\" \\' \\u{XXXX}",
        )
        return ch

    def _scan_unicode_escape(self, start: Position) -> str:
        self._advance()  # 'u'
        if self._peek() != "{":
            self._bag.error(
                ErrorCode.INVALID_ESCAPE,
                "الـ \\u لازم تيجي بين قوسين: \\u{XXXX}",
                Span(start, self._here()),
                suggestion="مثال: \\u{0627}",
            )
            return ""
        self._advance()  # '{'
        digits = ""
        while not self._at_end() and self._peek() not in (None, "}"):
            digits += self._advance()
        if self._peek() != "}":
            self._bag.error(
                ErrorCode.INVALID_ESCAPE,
                "قوس الـ unicode escape مش متقفل",
                Span(start, self._here()),
                suggestion="مثال: \\u{0627}",
            )
            return ""
        self._advance()  # '}'
        if not digits or len(digits) > 6 or not all(c in "0123456789abcdefABCDEF" for c in digits):
            self._bag.error(
                ErrorCode.INVALID_ESCAPE,
                f"كود unicode غير صالح: {digits!r}",
                Span(start, self._here()),
                suggestion="استخدم 1 إلى 6 hex digits مثل \\u{0627}",
            )
            return ""
        return chr(int(digits, 16))

    def _scan_number(self) -> None:
        start = self._here()
        start_offset = self._pos
        while not self._at_end():
            ch = self._peek()
            assert ch is not None
            if self._is_digit(ch) or ch in (".", _DECIMAL_SEPARATOR, _THOUSANDS_SEPARATOR):
                self._advance()
            else:
                break
        raw = self._source[start_offset : self._pos]
        normalized = raw.translate(_DIGIT_MAP)
        normalized = normalized.replace(_DECIMAL_SEPARATOR, ".").replace(
            _THOUSANDS_SEPARATOR, ""
        )

        value: int | float
        if normalized.count(".") > 1:
            self._bag.error(
                ErrorCode.INVALID_NUMBER,
                f"رقم غير صالح: '{raw}'",
                Span(start, self._here()),
                suggestion="استخدم فاصلة عشرية واحدة بس (1.5 أو ١٫٥)",
            )
            head, *rest = normalized.split(".")
            normalized = ".".join([head, rest[0]]) if rest else head
            value = float(normalized) if "." in normalized else int(normalized or "0")
        elif "." in normalized:
            try:
                value = float(normalized)
            except ValueError:
                self._bag.error(
                    ErrorCode.INVALID_NUMBER,
                    f"رقم غير صالح: '{raw}'",
                    Span(start, self._here()),
                    suggestion="اكتب الرقم بشكل زي 12 أو 12.5 أو ١٢٫٥",
                )
                value = 0
        else:
            value = int(normalized or "0")
        self._emit(TokenType.NUMBER, value, start, raw)

    def _scan_word(self) -> None:
        start = self._here()
        start_offset = self._pos
        while not self._at_end():
            ch = self._peek()
            assert ch is not None
            if _is_word_char(ch):
                self._advance()
            else:
                break
        raw = self._source[start_offset : self._pos]
        keyword = KEYWORDS.get(raw)
        if keyword is not None:
            self._emit(keyword, raw, start, raw)
        else:
            self._emit(TokenType.IDENTIFIER, raw, start, raw)

    def _scan_symbol(self) -> None:
        start = self._here()
        ch = self._peek()
        assert ch is not None
        two = self._source[self._pos : self._pos + 2]
        token_type = _TWO_CHAR_OPERATORS.get(two)
        if token_type is not None:
            self._advance()
            self._advance()
            self._emit(token_type, two, start, two)
            return
        token_type = _SINGLE_CHAR_TOKENS.get(ch)
        if token_type is not None:
            self._advance()
            self._emit(token_type, ch, start, ch)
            return
        if ch == "!":
            self._advance()
            self._bag.error(
                ErrorCode.UNEXPECTED_OPERATOR,
                "علامة '!' لوحدها مش مفهومة",
                Span(start, self._here()),
                suggestion="اكتب '!=' لو عايز 'مش يساوي'",
            )
            return
        self._advance()
        self._bag.error(
            ErrorCode.UNEXPECTED_CHARACTER,
            f"حرف غير متوقع: '{ch}'",
            Span(start, self._here()),
            suggestion='امسح الحرف أو حطّه جوه تعليق (يبدأ بـ "#")',
        )
