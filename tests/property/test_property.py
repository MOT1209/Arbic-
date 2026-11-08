"""Deterministic property-style tests.

Hypothesis is deliberately not a dependency, so the generator is seeded: a
failure message always carries the seed and the input, which makes the case
reproducible without shrinking.
"""

from __future__ import annotations

import random

import pytest

from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.compiler.lexer.lexer import Lexer
from al_arabiya.compiler.lexer.tokens import TokenType
from al_arabiya.runtime.interpreter.interpreter import Interpreter

SEEDS = range(12)

_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_SAFE_CHARS = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي 0123456789.,،؛:-_+=!?()"

#: character -> its source-level escape
_ESCAPES = {
    "\n": "\\n",
    "\t": "\\t",
    "\r": "\\r",
    "\\": "\\\\",
    '"': '\\"',
    "'": "\\'",
}


def _single_number(text: str):
    tokens = [token for token in Lexer(text).tokenize() if token.type is TokenType.NUMBER]
    assert len(tokens) == 1, (text, [token.type for token in tokens])
    return tokens[0]


def _single_string(literal: str):
    tokens = [token for token in Lexer(literal).tokenize() if token.type is TokenType.STRING]
    assert len(tokens) == 1, literal
    return tokens[0]


def _arabic_digits(text: str) -> str:
    return text.translate(str.maketrans("0123456789", _ARABIC_DIGITS))


@pytest.mark.parametrize("seed", SEEDS)
def test_integer_literals_round_trip_in_both_digit_sets(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(20):
        value = rng.randrange(0, 10**9)
        literal = str(value)
        for text in (literal, _arabic_digits(literal)):
            assert _single_number(text).value == value, (seed, text)


@pytest.mark.parametrize("seed", SEEDS)
def test_decimal_literals_round_trip(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(20):
        whole = rng.randrange(0, 10**6)
        fraction = rng.randrange(0, 10**6)
        text = f"{whole}.{fraction:06d}"
        token = _single_number(text)
        assert isinstance(token.value, float)
        assert token.value == pytest.approx(float(text)), (seed, text)


@pytest.mark.parametrize("seed", SEEDS)
def test_string_literals_round_trip(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(15):
        text = "".join(rng.choice(_SAFE_CHARS) for _ in range(rng.randrange(0, 30)))
        assert _single_string(f'"{text}"').value == text, (seed, text)


def test_escape_sequences_round_trip() -> None:
    rng = random.Random(2024)
    alphabet = list(_ESCAPES) + list("abcابت")
    for _ in range(60):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 12)))
        literal = "".join(_ESCAPES.get(char, char) for char in text)
        assert _single_string(f'"{literal}"').value == text, text


def test_repeat_count_matches_the_number_of_iterations() -> None:
    for count in range(0, 40):
        result = compile_source(f'كرر {count} مرات\nاطبع "س"\nخلاص\n', "<property>")
        assert result.program is not None, count
        lines: list[str] = []
        Interpreter(diagnostics=DiagnosticBag(), write=lines.append).run(result.program)
        assert len(lines) == count, count
