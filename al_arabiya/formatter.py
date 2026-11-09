"""A conservative, token-aware formatter.

The formatter re-lays out whitespace only: it never renames, reorders or
rewrites a token.  Every line is rebuilt from the lexer's tokens with one
canonical spacing policy (spaces around binary operators, a space after
commas and top-level colons, none around brackets, dots and dict colons),
indentation follows the block stack (``لو``/``كرر``/``دالة``/``صنف`` … open,
``خلاص`` closes, ``غير كده``/``امسك``/``أخيرا``/``حالة`` continue), and runs
of blank lines collapse to one.

Comments are not tokens — the lexer skips them — so each line's comment is
carried over verbatim from the source and re-attached two spaces after the
code.

Every result is verified before it is offered: the formatted text must lex to
exactly the same tokens (newlines, indentation and comments excluded) and
still compile cleanly.  If that check ever fails the original text is returned
unchanged, so a formatter bug can never corrupt a program.
"""

from __future__ import annotations

from dataclasses import dataclass

from al_arabiya.compiler.diagnostics.diagnostics import Diagnostic
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.compiler.lexer.lexer import Lexer
from al_arabiya.compiler.lexer.tokens import Token, TokenType

__all__ = ["FormatResult", "format_source"]

_INDENT = "    "

#: A line starting with one of these opens a new block.
_OPENERS = frozenset(
    {
        TokenType.KW_IF,
        TokenType.KW_REPEAT,
        TokenType.KW_WHILE,
        TokenType.KW_FOREACH,
        TokenType.KW_FUNC,
        TokenType.KW_CLASS,
        TokenType.KW_INTERFACE,
        TokenType.KW_TRY,
        TokenType.KW_WITH,
        TokenType.KW_MATCH,
    }
)
#: Marker for the `غير كده` branch of a `طابق`: one `خلاص` closes both.
_MATCH_ELSE = "match_else"

_NO_SPACE_BEFORE = frozenset(
    {
        TokenType.RPAREN,
        TokenType.RBRACKET,
        TokenType.RBRACE,
        TokenType.COMMA,
        TokenType.DOT,
    }
)
_NO_SPACE_AFTER = frozenset(
    {TokenType.LPAREN, TokenType.LBRACKET, TokenType.DOT}
)
#: Tokens that can end a callee/indexed value: ``ف(...)`` and ``ق[0]``.
_CALLABLE_END = frozenset(
    {
        TokenType.IDENTIFIER,
        TokenType.NUMBER,
        TokenType.STRING,
        TokenType.RPAREN,
        TokenType.RBRACKET,
    }
)
_BINARY_OPERATORS = frozenset(
    {
        TokenType.PLUS,
        TokenType.MINUS,
        TokenType.STAR,
        TokenType.SLASH,
        TokenType.PERCENT,
        TokenType.ASSIGN,
        TokenType.EQ_EQUAL,
        TokenType.NOT_EQUAL,
        TokenType.LESS,
        TokenType.GREATER,
        TokenType.LESS_EQUAL,
        TokenType.GREATER_EQUAL,
    }
)
#: After these a ``-`` is unary (``-5``), not subtraction.
_OPERAND_EXPECTED = _BINARY_OPERATORS | frozenset(
    {
        TokenType.LPAREN,
        TokenType.LBRACKET,
        TokenType.LBRACE,
        TokenType.COMMA,
        TokenType.COLON,
        TokenType.KW_RETURN,
        TokenType.KW_PRINT,
        TokenType.KW_IF,
        TokenType.KW_WHILE,
        TokenType.KW_REPEAT,
        TokenType.KW_CASE,
        TokenType.KW_YIELD,
        TokenType.KW_THROW,
        TokenType.KW_AND,
        TokenType.KW_OR,
        TokenType.KW_NOT,
        TokenType.KW_ADD,
        TokenType.KW_SUB,
        TokenType.KW_MUL,
        TokenType.KW_DIV,
        TokenType.KW_EQUAL_WORD,
        TokenType.KW_GREATER,
        TokenType.KW_LESS,
    }
)


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


def _is_unary(tokens: list[Token], index: int) -> bool:
    if tokens[index].type is not TokenType.MINUS:
        return False
    if index == 0:
        return True
    return tokens[index - 1].type in _OPERAND_EXPECTED


def _space_before(tokens: list[Token], index: int, brace_depth: int) -> bool:
    if index == 0:
        return False
    previous = tokens[index - 1]
    current = tokens[index]
    if current.type in _NO_SPACE_BEFORE:
        return False
    if previous.type in _NO_SPACE_AFTER:
        return False
    if previous.type is TokenType.LBRACE:
        return False
    if previous.type is TokenType.COMMA:
        return True
    if current.type is TokenType.COLON:
        # `خلي س : رقم` reads with spaces; `{"أ": 1}` does not.
        return brace_depth == 0
    if previous.type is TokenType.COLON:
        return True
    if previous.type is TokenType.MINUS and _is_unary(tokens, index - 1):
        return False
    if current.type in (TokenType.LPAREN, TokenType.LBRACKET):
        return previous.type not in _CALLABLE_END
    return True


def _render_tokens(tokens: list[Token]) -> str:
    """Rebuild one line of code with canonical spacing."""
    parts: list[str] = []
    brace_depth = 0
    for index, token in enumerate(tokens):
        if _space_before(tokens, index, brace_depth):
            parts.append(" ")
        parts.append(token.raw)
        if token.type is TokenType.LBRACE:
            brace_depth += 1
        elif token.type is TokenType.RBRACE:
            brace_depth = max(0, brace_depth - 1)
    return "".join(parts)


def _comment_start(line: str, tokens: list[Token]) -> int:
    """Index of the ``#`` that starts this line's comment, or ``-1``.

    Searching starts after the last token, so a ``#`` inside a string literal
    can never be mistaken for a comment.
    """
    start = 0
    if tokens:
        last = tokens[-1]
        start = last.column - 1 + len(last.raw)
    return line.find("#", start)


def _group_tokens(source: str) -> dict[int, list[Token]]:
    grouped: dict[int, list[Token]] = {}
    for token in Lexer(source).tokenize():
        if token.type in (TokenType.NEWLINE, TokenType.EOF):
            continue
        grouped.setdefault(token.line, []).append(token)
    return grouped


def _rewrite(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    grouped = _group_tokens(normalized)
    lines = normalized.split("\n")

    stack: list[TokenType | str] = []
    bracket_depth = 0
    output: list[str] = []

    for number, raw in enumerate(lines, start=1):
        tokens = grouped.get(number, [])
        first = tokens[0].type if tokens else None
        at_block_level = bracket_depth == 0
        continues_match = False

        if at_block_level and tokens:
            if first is TokenType.KW_END:
                if stack and stack[-1] in (TokenType.KW_CASE, _MATCH_ELSE):
                    stack.pop()
                    # `طابق` and its last branch share one `خلاص`.
                    if _top_is_match(stack):
                        stack.pop()
                elif stack:
                    stack.pop()
            elif first is TokenType.KW_CASE:
                if stack and stack[-1] is TokenType.KW_CASE:
                    stack.pop()
            elif first is TokenType.KW_ELSE:
                if stack and stack[-1] is TokenType.KW_CASE:
                    stack.pop()
                    continues_match = True
                elif stack and stack[-1] is TokenType.KW_IF:
                    stack.pop()
            elif first in (TokenType.KW_CATCH, TokenType.KW_FINALLY):
                if stack and stack[-1] in (TokenType.KW_TRY, TokenType.KW_CATCH):
                    stack.pop()

        level = len(stack)
        if bracket_depth > 0:
            level = len(stack) + bracket_depth
            if first in (TokenType.RPAREN, TokenType.RBRACKET, TokenType.RBRACE):
                level -= 1

        comment_at = _comment_start(raw, tokens)
        comment = raw[comment_at:].rstrip(" \t") if comment_at >= 0 else ""
        code = _render_tokens(tokens)
        if code and comment:
            body = f"{code}  {comment}"
        else:
            body = code or comment
        output.append(_INDENT * level + body if body else "")

        for token in tokens:
            if token.type in (
                TokenType.LPAREN,
                TokenType.LBRACKET,
                TokenType.LBRACE,
            ):
                bracket_depth += 1
            elif token.type in (
                TokenType.RPAREN,
                TokenType.RBRACKET,
                TokenType.RBRACE,
            ):
                bracket_depth = max(0, bracket_depth - 1)

        if at_block_level and tokens:
            if first is TokenType.KW_CASE:
                stack.append(TokenType.KW_CASE)
            elif first is TokenType.KW_ELSE:
                stack.append(_MATCH_ELSE if continues_match else TokenType.KW_ELSE)
            elif first in (TokenType.KW_CATCH, TokenType.KW_FINALLY):
                stack.append(first)
            else:
                method = first is TokenType.KW_FUNC or (
                    first is TokenType.KW_PRIVATE
                    and len(tokens) > 1
                    and tokens[1].type is TokenType.KW_FUNC
                )
                if first in _OPENERS:
                    if not _is_interface_signature(first, stack):
                        stack.append(first)
                elif method:
                    stack.append(TokenType.KW_FUNC)
                # A lambda opens a block mid-statement: `خلي ف = دالة (س)`.
                lambdas = sum(
                    1 for token in tokens if token.type is TokenType.KW_FUNC
                )
                for _ in range(lambdas - (1 if method else 0)):
                    stack.append(TokenType.KW_FUNC)

    collapsed: list[str] = []
    for line in output:
        if line == "" and collapsed and collapsed[-1] == "":
            continue
        collapsed.append(line)
    while collapsed and collapsed[0] == "":
        collapsed.pop(0)
    while collapsed and collapsed[-1] == "":
        collapsed.pop()
    return "\n".join(collapsed) + "\n"


def _top_is_match(stack: list[TokenType | str]) -> bool:
    return bool(stack) and stack[-1] is TokenType.KW_MATCH


def _is_interface_signature(
    first: TokenType | None, stack: list[TokenType | str]
) -> bool:
    """``دالة`` inside a ``واجهة`` is a bare signature, not a block opener."""
    return (
        first is TokenType.KW_FUNC
        and bool(stack)
        and stack[-1] is TokenType.KW_INTERFACE
    )


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
