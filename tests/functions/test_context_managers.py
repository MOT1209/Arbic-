"""Tests for context managers (``استخدم``)."""

from __future__ import annotations

import pytest

from al_arabiya.compiler.ast.nodes import WithStatement
from al_arabiya.compiler.checker import check_types
from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.runtime.interpreter.interpreter import Interpreter
from al_arabiya.vm.compiler import unsupported_reason


def parse(source: str):
    result = compile_source(source, "test.arb")
    assert result.program is not None, [(d.code, d.message) for d in result.diagnostics]
    return result.program


def parse_errors(source: str) -> list[str]:
    result = compile_source(source, "test.arb")
    return [d.code for d in result.diagnostics if d.is_error]


def run(source: str) -> str:
    program = parse(source)
    lines: list[str] = []
    Interpreter(diagnostics=DiagnosticBag(), write=lines.append).run(program)
    return "\n".join(lines)


def runtime_error(source: str) -> ArabiyaRuntimeError:
    program = parse(source)
    with pytest.raises(ArabiyaRuntimeError) as excinfo:
        Interpreter(write=lambda _text: None).run(program)
    return excinfo.value


RESOURCE = (
    "صنف مورد\n"
    "    دالة __تهيئة__ ()\n"
    "        انا.مفتوح = غلط\n"
    "    خلاص\n"
    "    دالة __دخول__ ()\n"
    "        انا.مفتوح = صح\n"
    '        اطبع "فتح"\n'
    "        رجّع انا\n"
    "    خلاص\n"
    "    دالة __خروج__ ()\n"
    "        انا.مفتوح = غلط\n"
    '        اطبع "قفل"\n'
    "    خلاص\n"
    "خلاص\n"
)


def test_parse_with_statement():
    program = parse(RESOURCE + "استخدم مورد() باسم م\n    اطبع 1\nخلاص")
    statement = program.body[1]
    assert isinstance(statement, WithStatement)
    assert statement.name == "م"
    assert len(statement.body) == 1


def test_enter_binds_its_return_value_and_exit_runs():
    source = RESOURCE + "استخدم مورد() باسم م\n    اطبع م.مفتوح\nخلاص"
    assert run(source) == "فتح\nصح\nقفل"


def test_exit_runs_when_the_body_returns():
    source = (
        RESOURCE
        + "دالة ف ()\n"
        "    استخدم مورد() باسم م\n"
        "        رجّع 5\n"
        "    خلاص\n"
        "خلاص\n"
        "اطبع ف()"
    )
    assert run(source) == "فتح\nقفل\n5"


def test_exit_runs_on_break():
    source = RESOURCE + "كرر 3 مرات\n    استخدم مورد() باسم م\n        اكسر\n    خلاص\nخلاص"
    assert run(source) == "فتح\nقفل"


def test_exit_runs_on_throw():
    source = (
        RESOURCE
        + "حاول\n"
        "    استخدم مورد() باسم م\n"
        '        ارم "خلل"\n'
        "    خلاص\n"
        "امسك خطأ\n"
        '    اطبع "تمسك"\n'
        "خلاص"
    )
    assert run(source) == "فتح\nقفل\nتمسك"


def test_exit_runs_inside_a_generator():
    source = (
        RESOURCE
        + "دالة م ()\n"
        "    استخدم مورد() باسم مورد_جاري\n"
        "        انتج 1\n"
        "        انتج 2\n"
        "    خلاص\n"
        "خلاص\n"
        "لكل س في م()\n"
        "    اطبع س\n"
        "خلاص"
    )
    assert run(source) == "فتح\n1\n2\nقفل"


def test_non_instance_is_rejected():
    error = runtime_error("استخدم 5 باسم س\n    اطبع س\nخلاص")
    assert error.diagnostic.code == ErrorCode.INVALID_CONTEXT_MANAGER


def test_missing_dunder_methods_are_rejected():
    source = (
        "صنف مورد_ناقص\n"
        "    دالة __دخول__ ()\n"
        "        رجّع 1\n"
        "    خلاص\n"
        "خلاص\n"
        "استخدم مورد_ناقص() باسم س\n"
        "    اطبع س\n"
        "خلاص"
    )
    assert runtime_error(source).diagnostic.code == ErrorCode.INVALID_CONTEXT_MANAGER


def test_dunder_arity_is_checked():
    source = (
        "صنف غريب\n"
        "    دالة __دخول__ (س)\n"
        "        رجّع س\n"
        "    خلاص\n"
        "    دالة __خروج__ ()\n"
        "        رجّع فراغ\n"
        "    خلاص\n"
        "خلاص\n"
        "استخدم غريب() باسم س\n"
        "    اطبع س\n"
        "خلاص"
    )
    assert runtime_error(source).diagnostic.code == ErrorCode.ARITY_MISMATCH


def test_with_requires_as_and_a_name():
    assert ErrorCode.EXPECTED_TOKEN in parse_errors("استخدم مورد()\n    اطبع 1\nخلاص")
    assert ErrorCode.EXPECTED_IDENTIFIER in parse_errors(
        "استخدم مورد() باسم\n    اطبع 1\nخلاص"
    )


def test_type_checker_accepts_context_managers():
    program = parse(RESOURCE + "استخدم مورد() باسم م\n    اطبع م\nخلاص")
    assert [d for d in check_types(program) if d.is_error] == []


def test_vm_falls_back_for_context_managers():
    program = parse("استخدم مورد() باسم م\n    اطبع 1\nخلاص")
    reason = unsupported_reason(program)
    assert reason is not None
    assert "استخدم" in reason
