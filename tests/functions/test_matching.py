"""Tests for pattern matching (``طابق`` / ``حالة``)."""

from __future__ import annotations

import pytest

from al_arabiya.compiler.ast.nodes import MatchStatement
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


def test_parse_match_statement_with_guard():
    program = parse(
        "طابق 2\n"
        "    حالة 1\n"
        '        اطبع "واحد"\n'
        "    حالة 2 لو صح\n"
        '        اطبع "اتنين"\n'
        "    غير كده\n"
        '        اطبع "تاني"\n'
        "خلاص"
    )
    statement = program.body[0]
    assert isinstance(statement, MatchStatement)
    assert len(statement.cases) == 2
    assert statement.cases[1].guard is not None
    assert statement.else_body is not None


def test_literal_number_match():
    source = (
        "دالة وصّف (س)\n"
        "    طابق س\n"
        "        حالة 1\n"
        '            رجّع "واحد"\n'
        "        حالة 2\n"
        '            رجّع "اتنين"\n'
        "        غير كده\n"
        '            رجّع "تاني"\n'
        "    خلاص\n"
        "خلاص\n"
        "اطبع وصّف(1)\n"
        "اطبع وصّف(2)\n"
        "اطبع وصّف(3)"
    )
    assert run(source) == "واحد\nاتنين\nتاني"


def test_string_bool_and_null_patterns():
    source = (
        'طابق "مرحبا"\n'
        "    حالة \"تحية\"\n"
        '        اطبع "غلط"\n'
        '    حالة "مرحبا"\n'
        '        اطبع "صح"\n'
        "خلاص\n"
        "طابق صح\n"
        "    حالة غلط\n"
        '        اطبع "غلط"\n'
        "    حالة صح\n"
        '        اطبع "منطقي"\n'
        "خلاص\n"
        "طابق فراغ\n"
        "    حالة فراغ\n"
        '        اطبع "فاضي"\n'
        "خلاص"
    )
    assert run(source) == "صح\nمنطقي\nفاضي"


def test_negative_number_pattern():
    assert run("طابق -1\n    حالة -1\n        اطبع 1\nخلاص") == "1"


def test_binding_pattern_captures_the_subject():
    source = (
        "طابق 7\n"
        "    حالة قيمة\n"
        "        اطبع قيمة\n"
        "خلاص\n"
        "اطبع قيمة"
    )
    assert run(source) == "7\n7"


def test_wildcard_matches_without_binding():
    source = (
        "طابق [1، 2]\n"
        "    حالة 3\n"
        '        اطبع "غلط"\n'
        "    حالة _\n"
        '        اطبع "أي حاجة"\n'
        "خلاص"
    )
    assert run(source) == "أي حاجة"


def test_guard_can_reject_a_literal_case():
    source = (
        "خلي س = 2\n"
        "طابق 1\n"
        "    حالة 1 لو س أكبر من 5\n"
        '        اطبع "غلط"\n'
        "    غير كده\n"
        '        اطبع "بديل"\n'
        "خلاص"
    )
    assert run(source) == "بديل"


def test_first_matching_case_wins():
    source = (
        "طابق 5\n"
        "    حالة أ\n"
        '        اطبع "أول"\n'
        "    حالة ب\n"
        '        اطبع "تاني"\n'
        "خلاص"
    )
    assert run(source) == "أول"


def test_no_case_and_no_else_is_a_noop():
    assert run("طابق 9\n    حالة 1\n        اطبع 1\nخلاص") == ""


def test_match_inside_a_generator():
    source = (
        "دالة م (س)\n"
        "    طابق س\n"
        "        حالة 1\n"
        '            انتج "واحد"\n'
        "        غير كده\n"
        '            انتج "تاني"\n'
        "    خلاص\n"
        "خلاص\n"
        "لكل ن في م(1)\n"
        "    اطبع ن\n"
        "خلاص\n"
        "لكل ن في م(2)\n"
        "    اطبع ن\n"
        "خلاص"
    )
    assert run(source) == "واحد\nتاني"


def test_match_needs_at_least_one_branch():
    assert ErrorCode.UNEXPECTED_TOKEN in parse_errors("طابق 1\nخلاص")


def test_match_requires_block_end():
    assert ErrorCode.MISSING_BLOCK_END in parse_errors("طابق 1\n    حالة 1\n        اطبع 1")


def test_unmatched_subject_binding_is_not_defined():
    source = (
        "طابق 1\n"
        "    حالة 2\n"
        "        اطبع 2\n"
        "    حالة قيمة\n"
        "        اطبع قيمة\n"
        "خلاص\n"
        "اطبع قيمة"
    )
    assert run(source) == "1\n1"


def test_type_checker_accepts_matching():
    program = parse(
        "طابق 1\n"
        "    حالة قيمة لو صح\n"
        "        اطبع قيمة\n"
        "    غير كده\n"
        "        اطبع 0\n"
        "خلاص"
    )
    assert [d for d in check_types(program) if d.is_error] == []


def test_vm_falls_back_for_matching():
    reason = unsupported_reason(parse("طابق 1\n    حالة 1\n        اطبع 1\nخلاص"))
    assert reason is not None
    assert "طابق" in reason
