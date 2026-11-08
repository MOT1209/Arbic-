"""Tests for Phase 3: lists, maps, indexing, index assignment and for-each."""

from __future__ import annotations

import pytest

from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag, render_diagnostics
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.runtime.interpreter.interpreter import Interpreter


def run(source: str) -> str:
    result = compile_source(source, "test.arb")
    assert result.program is not None, render_diagnostics(result.diagnostics, result.source)
    lines: list[str] = []
    Interpreter(diagnostics=DiagnosticBag(), write=lines.append).run(result.program)
    return "\n".join(lines)


def runtime_error(source: str) -> ArabiyaRuntimeError:
    result = compile_source(source, "test.arb")
    assert result.program is not None, render_diagnostics(result.diagnostics, result.source)
    with pytest.raises(ArabiyaRuntimeError) as excinfo:
        Interpreter(write=lambda _t: None).run(result.program)
    return excinfo.value


def parse_errors(source: str) -> list[str]:
    result = compile_source(source, "test.arb")
    return [d.code for d in result.diagnostics if d.is_error]


# -------------------------------------------------------------------- lists


def test_list_literal_and_print():
    assert run("اطبع [1، 2، 3]") == "[1، 2، 3]"


def test_empty_list():
    assert run("خلي ق = []\nاطبع طول(ق)") == "0"


def test_list_indexing():
    assert run("خلي ق = [10، 20، 30]\nاطبع ق[1]") == "20"


def test_negative_index():
    assert run("اطبع [1، 2، 3][-1]") == "3"


def test_list_index_assignment():
    assert run("خلي ق = [1، 2، 3]\nق[0] = 99\nاطبع ق") == "[99، 2، 3]"


def test_nested_lists():
    assert run("خلي ق = [[1، 2]، [3، 4]]\nاطبع ق[1][0]") == "3"


def test_multiline_list():
    assert run("خلي ق = [\n  1،\n  2،\n  3،\n]\nاطبع طول(ق)") == "3"


def test_index_out_of_range():
    assert runtime_error("اطبع [1، 2][9]").diagnostic.code == ErrorCode.INDEX_OUT_OF_RANGE


def test_non_integer_index():
    assert runtime_error('اطبع [1، 2]["ا"]').diagnostic.code == ErrorCode.INVALID_INDEX


# --------------------------------------------------------------------- maps


def test_map_literal_and_lookup():
    assert run('خلي م = {"الاسم": "أحمد"}\nاطبع م["الاسم"]') == "أحمد"


def test_map_assignment_and_new_key():
    source = 'خلي م = {"أ": 1}\nم["ب"] = 2\nاطبع م["ب"]'
    assert run(source) == "2"


def test_numeric_keys():
    assert run("خلي م = {1: \"واحد\"}\nاطبع م[1]") == "واحد"


def test_missing_key_errors():
    assert runtime_error('اطبع {"أ": 1}["ب"]').diagnostic.code == ErrorCode.KEY_NOT_FOUND


def test_unhashable_key_errors():
    assert runtime_error("اطبع {[1]: 2}").diagnostic.code == ErrorCode.UNHASHABLE_KEY


# ----------------------------------------------------------------- for-each


def test_for_each_over_list():
    assert run("لكل س في [1، 2، 3]\n    اطبع س\nخلاص") == "1\n2\n3"


def test_for_each_over_string():
    assert run('لكل ح في "اب"\n    اطبع ح\nخلاص') == "ا\nب"


def test_for_each_over_map_yields_keys():
    assert run('لكل م في {"أ": 1، "ب": 2}\n    اطبع م\nخلاص') == "أ\nب"


def test_for_each_accumulates():
    source = "خلي ك = 0\nلكل ن في [1، 2، 3، 4]\n    ك = ك زائد ن\nخلاص\nاطبع ك"
    assert run(source) == "10"


def test_for_each_with_break_and_continue():
    source = (
        "لكل ن في [1، 2، 3، 4، 5]\n"
        "    لو ن يساوي 2\n"
        "        كمل\n"
        "    خلاص\n"
        "    لو ن يساوي 4\n"
        "        اكسر\n"
        "    خلاص\n"
        "    اطبع ن\n"
        "خلاص"
    )
    assert run(source) == "1\n3"


def test_for_each_over_non_iterable_errors():
    assert runtime_error("لكل س في 5\n    اطبع س\nخلاص").diagnostic.code == ErrorCode.NOT_ITERABLE


# ------------------------------------------------------------------- parse


def test_assignment_to_non_assignable_errors():
    assert ErrorCode.INVALID_ASSIGN_TARGET in parse_errors("5 = 3")
