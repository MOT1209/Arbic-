"""Adversarial input tests for the lexer, parser, and diagnostic renderer.

Hypothesis is deliberately not a dependency: these tests use a seeded,
corpus-based generator, so a failing case can always be replayed from the
printed seed and source. They assert *robustness*, not accepted syntax —
any input may produce diagnostics, but it must never crash the front end or
emit a span outside the source.
"""

from __future__ import annotations

import random

import pytest

from al_arabiya.compiler.diagnostics.diagnostics import render_diagnostics
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.compiler.lexer.lexer import Lexer

# Fragments chosen to hit every layer: keywords, operators, literals,
# brackets, Arabic identifiers, and characters that are legal only in some
# contexts. Order matters only in that random.shuffle mixes them freely.
CORPUS: tuple[str, ...] = (
    "خلي",
    "اطبع",
    "لو",
    "غير كده",
    "خلاص",
    "كرر",
    "مرات",
    "مرة",
    "طالما",
    "دالة",
    "رجّع",
    "لكل",
    "في",
    "استورد",
    "باسم",
    "من",
    "حاول",
    "امسك",
    "أخيرا",
    "ارم",
    "اكسر",
    "كمل",
    "صح",
    "غلط",
    "فراغ",
    "و",
    "أو",
    "مش",
    "يساوي",
    "أكبر",
    "أصغر",
    "زائد",
    "ناقص",
    "على",
    "س",
    "ص",
    "اسم_طويل",
    "٠",
    "١٢٣",
    "٣٫١٤",
    "1",
    "2.5",
    '"نص"',
    '"غير مغلق',
    "\\n",
    "\\u{zz}",
    "[",
    "]",
    "{",
    "}",
    "(",
    ")",
    ",",
    "،",
    ":",
    "=",
    "+",
    "-",
    "*",
    "/",
    "%",
    "==",
    "!=",
    "<",
    ">",
    "<=",
    ">=",
    ".",
    "# تعليق",
    "\n",
    "\n",
    "\n",
    "\t",
    " ",
    "\u200f",
    "\u064e",
)

SEEDS = range(30)


def _source(seed: int) -> str:
    rng = random.Random(seed)
    length = rng.randint(0, 60)
    return " ".join(rng.choice(CORPUS) for _ in range(length))


def _check_robust(source: str, label: str) -> None:
    tokens = Lexer(source).tokenize()
    assert isinstance(tokens, list), label

    result = compile_source(source, "fuzz.arb")

    for diagnostic in result.diagnostics:
        assert 0 <= diagnostic.span.start.offset <= len(source), (label, diagnostic.code)
        assert diagnostic.span.length >= 0, (label, diagnostic.code)

    # Rendering is part of the contract: a malformed span must not raise here.
    rendered = render_diagnostics(result.diagnostics, result.source)
    assert isinstance(rendered, str), label


@pytest.mark.parametrize("seed", SEEDS)
def test_random_token_soup_is_handled(seed: int) -> None:
    _check_robust(_source(seed), f"seed={seed}")


MALFORMED: tuple[str, ...] = (
    "",
    "   ",
    "\n\n\n",
    "كرر",
    "كرر 3",
    "كرر 3 مرات",
    "دالة",
    "دالة ا (",
    "استورد",
    "من",
    'من "وحدة"',
    "لو\nخلاص",
    "لو 1 أكبر من\nخلاص",
    "حاول\nخلاص",
    'اطبع "غير مغلق',
    "اطبع 1 +\n2",
    "اطبع [1، 2",
    'اطبع {"أ"}',
    "اطبع 1.2.3",
    "اطبع \\u{zz}",
    "اطبع ((((((((((((1))))))))))))",
    "خلي = 5",
    "= 5",
    "اطبع س.",
    "# تعليق بس",
)


@pytest.mark.parametrize("source", MALFORMED)
def test_malformed_programs_never_crash(source: str) -> None:
    _check_robust(source, repr(source))


@pytest.mark.parametrize("seed", SEEDS)
def test_repeated_compilation_is_stable(seed: int) -> None:
    """The same input must produce the same diagnostics twice."""
    source = _source(seed)
    first = compile_source(source, "fuzz.arb")
    second = compile_source(source, "fuzz.arb")
    assert [(d.code, d.span.start.offset) for d in first.diagnostics] == [
        (d.code, d.span.start.offset) for d in second.diagnostics
    ]
