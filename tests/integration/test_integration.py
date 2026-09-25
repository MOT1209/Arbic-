"""Integration tests: full programs from source to output."""

from __future__ import annotations

import pytest

from al_arabiya.compiler.diagnostics.diagnostics import render_diagnostics
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.runtime.interpreter.interpreter import Interpreter


def run_program(source: str) -> str:
    result = compile_source(source, "integration.arb")
    assert result.program is not None, render_diagnostics(
        result.diagnostics, result.source
    )
    lines: list[str] = []
    Interpreter(write=lines.append).run(result.program)
    return "\n".join(lines)


def test_spec_example():
    source = "خلي س = 10\nخلي ص = 20\n\nاطبع س + ص"
    assert run_program(source) == "30"


def test_hello_world():
    assert run_program('اطبع "أهلا بالعالم"') == "أهلا بالعالم"


def test_full_program():
    source = """\
اطبع "أهلا يا عالم"

خلي السن = 25
لو السن أكبر من 18
    اطبع "إنت راجل كبير"
غير كده
    اطبع "لسه صغير"
خلاص

كرر 3 مرات
    اطبع "بحبك يا مصر"
خلاص

خلي العداد = 1
طالما العداد أصغر أو يساوي 5
    اطبع "العدد: " + العداد
    خلي العداد = العداد + 1
خلاص
"""
    expected = "\n".join(
        [
            "أهلا يا عالم",
            "إنت راجل كبير",
            "بحبك يا مصر",
            "بحبك يا مصر",
            "بحبك يا مصر",
            "العدد: 1",
            "العدد: 2",
            "العدد: 3",
            "العدد: 4",
            "العدد: 5",
        ]
    )
    assert run_program(source) == expected


def test_fizzbuzz_style_condition_chain():
    source = """\
خلي ن = 15
لو ن % 15 يساوي 0
    اطبع "فِزباز"
غير كده لو ن % 3 يساوي 0
    اطبع "فِز"
خلاص
"""
    # `غير كده لو` is NOT supported in phase 1 — expect a diagnostics failure.
    result = compile_source(source, "integration.arb")
    assert result.has_errors


def test_counter_with_accumulator():
    source = """\
خلي المجموع = 0
خلي العداد = 1
طالما العداد أصغر أو يساوي 10
    خلي المجموع = المجموع + العداد
    خلي العداد = العداد + 1
خلاص
اطبع المجموع
"""
    assert run_program(source) == "55"


def test_arabic_numbers_program():
    source = "خلي مسافة = ١٠٠\nخلي سرعة = ٢٠\nاطبع مسافة على سرعة"
    assert run_program(source) == "5"


def test_bool_flag_pattern():
    source = """\
خلي شغال = صح
لو شغال
    اطبع "النظام شغال"
خلاص
"""
    assert run_program(source) == "النظام شغال"


def test_string_building_loop():
    source = """\
خلي النص = ""
كرر 3 مرات
    خلي النص = النص + "*"
خلاص
اطبع النص
"""
    assert run_program(source) == "***"


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("2 + 3 * 4", "14"),
        ("(2 + 3) * 4", "20"),
        ("10 / 4", "2.5"),
        ("2 * 3 + 4 * 5", "26"),
        ("100 على 10 على 2", "5"),
        ("1 - 2 - 3", "-4"),
        ("7 % 3", "1"),
        ('"أ" + 1 + 2', "أ12"),
    ],
)
def test_expression_matrix(expression, expected):
    assert run_program(f"اطبع {expression}") == expected
