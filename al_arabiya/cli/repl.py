"""Interactive REPL for AlArabiya (العربية)."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable

from al_arabiya import __version__
from al_arabiya.compiler.diagnostics.diagnostics import (
    Diagnostic,
    DiagnosticBag,
    render_diagnostics,
)
from al_arabiya.compiler.diagnostics.errors import DiagnosticError
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.compiler.lexer.lexer import Lexer
from al_arabiya.compiler.lexer.tokens import TokenType
from al_arabiya.runtime.builtins import make_global_env
from al_arabiya.runtime.interpreter.interpreter import Interpreter

__all__ = ["run_repl"]

_EXIT_WORDS = frozenset({"خروج", "exit", "quit"})
_OPEN_BRACKETS = frozenset({"(", "[", "{"})
_CLOSE_BRACKETS = frozenset({")", "]", "}"})
#: Keywords that open a block closed by ``خلاص``.
_BLOCK_OPENERS = frozenset(
    {
        TokenType.KW_IF,
        TokenType.KW_REPEAT,
        TokenType.KW_WHILE,
        TokenType.KW_FUNC,
        TokenType.KW_FOREACH,
        TokenType.KW_TRY,
    }
)


def _pending_depth(text: str) -> tuple[int, int]:
    """Bracket depth and open-block count in ``text`` (never negative)."""
    brackets = 0
    blocks = 0
    for token in Lexer(text).tokenize():
        if token.type in (TokenType.LPAREN, TokenType.LBRACKET, TokenType.LBRACE):
            brackets += 1
        elif token.type in (TokenType.RPAREN, TokenType.RBRACKET, TokenType.RBRACE):
            brackets -= 1
        elif token.type in _BLOCK_OPENERS:
            blocks += 1
        elif token.type is TokenType.KW_END:
            blocks = max(0, blocks - 1)
    return brackets, blocks


def _is_incomplete(diagnostics: Iterable[Diagnostic], source_length: int) -> bool:
    """True when an error points at the very end of the input (keep buffering)."""
    for diagnostic in diagnostics:
        if diagnostic.is_error and diagnostic.span.start.offset >= source_length:
            return True
    return False


def run_repl(
    input_fn: Callable[[str], str] = input,
    out: Callable[[str], None] | None = None,
    err: Callable[[str], None] | None = None,
) -> int:
    write = out if out is not None else (lambda text: print(text))
    error = err if err is not None else (lambda text: print(text, file=sys.stderr))

    write("العربية REPL — AlArabiya " + __version__)
    write("اكتب أوامرك بالعربية. للخروج اكتب: خروج (exit)")
    write("")

    environment = make_global_env()
    buffer: list[str] = []
    brackets = 0
    blocks = 0

    while True:
        prompt = "... " if buffer else ">>> "
        try:
            line = input_fn(prompt)
        except (EOFError, KeyboardInterrupt):
            write("")
            write("مع السلامة 👋")
            return 0

        stripped = line.strip()
        if not buffer and stripped in _EXIT_WORDS:
            write("مع السلامة 👋")
            return 0
        if buffer and not stripped:
            continue  # inside an unfinished construct: blank lines are blank

        separator = " " if brackets > 0 else "\n"
        source = separator.join([*buffer, line]) if buffer else line
        buffer.clear()
        buffer.append(source)
        brackets, blocks = _pending_depth(source)

        if not source.strip():
            buffer.clear()
            brackets = blocks = 0
            continue

        result = compile_source(source, "<REPL>")
        if result.program is not None:
            if result.diagnostics:
                error(render_diagnostics(result.diagnostics, result.source))
            runtime_bag: DiagnosticBag = DiagnosticBag()
            interpreter = Interpreter(
                environment=environment, diagnostics=runtime_bag, write=write
            )
            try:
                interpreter.run(result.program)
            except DiagnosticError as exc:
                error(render_diagnostics([exc.diagnostic], result.source))
            if runtime_bag:
                error(render_diagnostics(runtime_bag.sorted(), result.source))
            buffer.clear()
            brackets = blocks = 0
            continue

        if brackets > 0 or blocks > 0 or _is_incomplete(result.diagnostics, len(source)):
            continue  # wait for more input

        if result.diagnostics:
            error(render_diagnostics(result.diagnostics, result.source))
        buffer.clear()
        brackets = blocks = 0
