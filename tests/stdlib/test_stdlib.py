"""Tests for Phase 4: the standard builtin library."""

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


def test_append_and_remove():
    assert run("خلي ق = []\nاضف(ق، 1)\nاضف(ق، 2)\nاطبع ق") == "[1، 2]"
    assert run("خلي ق = [1، 2، 3]\nاحذف(ق، 1)\nاطبع ق") == "[1، 3]"


def test_range():
    assert run("اطبع مدى(4)") == "[0، 1، 2، 3]"
    assert run("اطبع مدى(2، 5)") == "[2، 3، 4]"


def test_sum_max_min():
    assert run("اطبع مجموع([1، 2، 3، 4])") == "10"
    assert run("اطبع اكبر([3، 9، 2])") == "9"
    assert run("اطبع اصغر([3، 9، 2])") == "2"


def test_sort_numbers_and_strings():
    assert run("اطبع رتب([3، 1، 2])") == "[1، 2، 3]"
    assert run('اطبع رتب(["ج"، "ا"، "ب"])') == "[ا، ب، ج]"


def test_reverse():
    assert run("اطبع اعكس([1، 2، 3])") == "[3، 2، 1]"
    assert run('اطبع اعكس("ابج")') == "جبا"


def test_contains():
    assert run("اطبع يحتوي([1، 2]، 2)") == "صح"
    assert run('اطبع يحتوي("أهلا"، "ه")') == "صح"
    assert run('اطبع يحتوي({"أ": 1}، "أ")') == "صح"


def test_keys_and_values():
    assert run('اطبع مفاتيح({"أ": 1، "ب": 2})') == "[أ، ب]"
    assert run('اطبع قيم({"أ": 1، "ب": 2})') == "[1، 2]"


def test_string_ops():
    assert run('اطبع قسّم("a,b,c"، ",")') == "[a، b، c]"
    assert run('اطبع ادمج(["x"، "y"، "z"]، "-")') == "x-y-z"
    assert run('اطبع استبدل("ممم"، "م"، "ن")') == "ننن"


def test_math_ops():
    assert run("اطبع جذر(81)") == "9"
    assert run("اطبع اس(2، 8)") == "256"
    assert run("اطبع مطلق(-4)") == "4"
    assert run("اطبع قرّب(2.4)") == "2"


def test_type_errors_are_located():
    assert runtime_error("اطبع مجموع([1، \"x\"])").diagnostic.code == ErrorCode.BUILTIN_ERROR
    assert runtime_error("اطبع جذر(-1)").diagnostic.code == ErrorCode.BUILTIN_ERROR
    assert runtime_error('اطبع مفاتيح([1])').diagnostic.code == ErrorCode.BUILTIN_ERROR
