"""Tests for exception handling: حاول / امسك / أخيرا / ارم."""

from __future__ import annotations

import pytest

from al_arabiya.compiler.ast.nodes import ThrowStatement, TryStatement
from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag, render_diagnostics
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.runtime.interpreter.interpreter import Interpreter


def parse(source: str):
    result = compile_source(source, "test.arb")
    assert result.program is not None, [(d.code, d.message) for d in result.diagnostics]
    return result.program


def parse_errors(source: str) -> list[str]:
    result = compile_source(source, "test.arb")
    return [d.code for d in result.diagnostics if d.is_error]


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


# ------------------------------------------------------------------ parsing


def test_parse_try_catch_finally():
    program = parse(
        "حاول\n    اطبع 1\nامسك خطأ\n    اطبع 2\nأخيرا\n    اطبع 3\nخلاص"
    )
    node = program.body[0]
    assert isinstance(node, TryStatement)
    assert node.catch_name == "خطأ"
    assert node.catch_body is not None
    assert node.finally_body is not None


def test_parse_throw():
    program = parse('ارم "خطأ"')
    assert isinstance(program.body[0], ThrowStatement)


def test_try_without_handler_errors():
    codes = parse_errors("حاول\n    اطبع 1\nخلاص")
    assert ErrorCode.TRY_WITHOUT_HANDLER in codes


# --------------------------------------------------------------- behaviour


def test_catch_runtime_error_exposes_message_and_code():
    source = (
        "حاول\n"
        "    اطبع 10 على 0\n"
        "امسك خطأ\n"
        '    اطبع خطأ["الكود"]\n'
        "خلاص"
    )
    assert run(source) == "E4002"


def test_throw_and_catch_a_value():
    source = 'حاول\n    ارم "مشكلة"\nامسك e\n    اطبع e\nخلاص'
    assert run(source) == "مشكلة"


def test_throw_a_map_value():
    source = (
        'حاول\n'
        '    ارم {"نوع": "تنبيه"}\n'
        'امسك e\n'
        '    اطبع e["نوع"]\n'
        'خلاص'
    )
    assert run(source) == "تنبيه"


def test_finally_runs_on_success():
    assert run("حاول\n    اطبع 1\nأخيرا\n    اطبع 2\nخلاص") == "1\n2"


def test_finally_runs_on_error():
    source = "حاول\n    ارم 1\nامسك e\n    اطبع 2\nأخيرا\n    اطبع 3\nخلاص"
    assert run(source) == "2\n3"


def test_catch_without_variable():
    assert run('حاول\n    ارم 1\nامسك\n    اطبع "ماشي"\nخلاص') == "ماشي"


def test_uncaught_throw_is_runtime_error():
    assert runtime_error('ارم "خطأ"').diagnostic.code == ErrorCode.UNCAUGHT_ERROR


def test_finally_runs_even_without_catch_then_reraises():
    source = "حاول\n    ارم 1\nأخيرا\n    اطبع 99\nخلاص"
    error = runtime_error(source)
    assert error.diagnostic.code == ErrorCode.UNCAUGHT_ERROR


def test_nested_try_inner_catches():
    source = (
        "حاول\n"
        "    حاول\n"
        "        ارم 1\n"
        "    امسك\n"
        '        اطبع "داخلي"\n'
        "    خلاص\n"
        "امسك\n"
        '    اطبع "خارجي"\n'
        "خلاص"
    )
    assert run(source) == "داخلي"


def test_finally_runs_when_breaking_out_of_loop():
    source = (
        "كرر 3 مرات\n"
        "    حاول\n"
        "        اكسر\n"
        "    أخيرا\n"
        '        اطبع "تنظيف"\n'
        "    خلاص\n"
        "خلاص\n"
        'اطبع "بعد الحلقة"'
    )
    assert run(source) == "تنظيف\nبعد الحلقة"


def test_return_in_try_runs_finally():
    source = (
        "دالة ق ()\n"
        "    حاول\n"
        "        رجّع 1\n"
        "    أخيرا\n"
        '        اطبع "تنظيف"\n'
        "    خلاص\n"
        "خلاص\n"
        "اطبع ق()"
    )
    assert run(source) == "تنظيف\n1"


def test_error_thrown_in_function_is_caught_by_caller():
    source = (
        "دالة خطر ()\n"
        "    ارم \"من الدالة\"\n"
        "خلاص\n"
        "حاول\n"
        "    خطر()\n"
        "امسك e\n"
        "    اطبع e\n"
        "خلاص"
    )
    assert run(source) == "من الدالة"
