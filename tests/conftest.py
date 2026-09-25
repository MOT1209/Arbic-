"""Shared fixtures for the AlArabiya test suite."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag, render_diagnostics
from al_arabiya.compiler.frontend import FrontendResult, compile_source
from al_arabiya.compiler.lexer.lexer import Lexer
from al_arabiya.compiler.lexer.tokens import Token
from al_arabiya.runtime.interpreter.interpreter import Interpreter


def render_failure(result: FrontendResult) -> str:
    return render_diagnostics(result.diagnostics, result.source)


@pytest.fixture
def lex() -> Callable[[str], list[Token]]:
    def _lex(source: str) -> list[Token]:
        return Lexer(source).tokenize()

    return _lex


@pytest.fixture
def compile_ok() -> Callable[..., object]:
    def _compile(source: str, filename: str = "test.arb") -> FrontendResult:
        result = compile_source(source, filename)
        assert result.program is not None, render_failure(result)
        return result

    return _compile


@pytest.fixture
def run() -> Callable[[str], str]:
    def _run(source: str) -> str:
        result = compile_source(source, "test.arb")
        assert result.program is not None, render_failure(result)
        lines: list[str] = []
        bag = DiagnosticBag()
        Interpreter(diagnostics=bag, write=lines.append).run(result.program)
        return "\n".join(lines)

    return _run
