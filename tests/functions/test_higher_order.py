"""Tests for higher-order functions (functions as values)."""

from __future__ import annotations

from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.runtime.interpreter.interpreter import Interpreter


def run(source: str) -> str:
    result = compile_source(source, "test.arb")
    assert result.program is not None, [(d.code, d.message) for d in result.diagnostics]
    lines: list[str] = []
    Interpreter(diagnostics=DiagnosticBag(), write=lines.append).run(result.program)
    return "\n".join(lines)


def test_function_can_be_passed_as_an_argument():
    source = (
        "دالة ضعف (س)\n"
        "    رجّع س في 2\n"
        "خلاص\n"
        "دالة طبّق (د، س)\n"
        "    رجّع د(س)\n"
        "خلاص\n"
        "اطبع طبّق(ضعف، 4)"
    )
    assert run(source) == "8"


def test_function_can_return_a_function():
    source = (
        "دالة جامع (ن)\n"
        "    دالة أضف (س)\n"
        "        رجّع س زائد ن\n"
        "    خلاص\n"
        "    رجّع أضف\n"
        "خلاص\n"
        "خلي أضف_عشرة = جامع(10)\n"
        "اطبع أضف_عشرة(5)"
    )
    assert run(source) == "15"


def test_lambdas_can_be_composed():
    source = (
        "خلي ضعف = دالة (س)\n"
        "    رجّع س في 2\n"
        "خلاص\n"
        "خلي زائد_واحد = دالة (س)\n"
        "    رجّع س زائد 1\n"
        "خلاص\n"
        "خلي تركيب = دالة (أ، ب)\n"
        "    رجّع دالة (س)\n"
        "        رجّع ب(أ(س))\n"
        "    خلاص\n"
        "خلاص\n"
        "اطبع تركيب(ضعف، زائد_واحد)(5)"
    )
    assert run(source) == "11"


def test_functions_inside_collections():
    source = (
        "دالة ضعف (س)\n"
        "    رجّع س في 2\n"
        "خلاص\n"
        "خلي دوال = [ضعف، دالة (س)\n"
        "    رجّع س زائد 1\n"
        "خلاص]\n"
        "اطبع دوال[0](3)\n"
        "اطبع دوال[1](3)"
    )
    assert run(source) == "6\n4"
