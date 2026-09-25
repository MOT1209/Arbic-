"""Interpreter tests: statements, expressions, environment, runtime errors."""

from __future__ import annotations

import pytest

from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag, render_diagnostics
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.compiler.lexer.positions import Position, Span
from al_arabiya.runtime.interpreter.environment import Environment
from al_arabiya.runtime.interpreter.interpreter import Interpreter, format_value, is_truthy


def execute(source: str) -> tuple[list[str], DiagnosticBag]:
    result = compile_source(source, "test.arb")
    assert result.program is not None, render_diagnostics(result.diagnostics, result.source)
    lines: list[str] = []
    bag = DiagnosticBag()
    Interpreter(diagnostics=bag, write=lines.append).run(result.program)
    return lines, bag


def run(source: str) -> str:
    lines, _ = execute(source)
    return "\n".join(lines)


def runtime_error(source: str) -> ArabiyaRuntimeError:
    result = compile_source(source, "test.arb")
    assert result.program is not None
    interpreter = Interpreter(write=lambda _text: None)
    with pytest.raises(ArabiyaRuntimeError) as excinfo:
        interpreter.run(result.program)
    return excinfo.value


def span() -> Span:
    return Span(Position(0, 1, 1), Position(1, 1, 2))


# -------------------------------------------------------------- statements


def test_print_string():
    assert run('اطبع "مرحبا"') == "مرحبا"


def test_print_number():
    assert run("اطبع 42") == "42"


def test_print_boolean_in_arabic():
    assert run("اطبع صح") == "صح"
    assert run("اطبع غلط") == "غلط"


def test_float_whole_number_prints_without_dot():
    assert run("اطبع 3.0") == "3"
    assert run("اطبع 12.5") == "12.5"


def test_declaration_and_use():
    assert run('خلي الاسم = "أحمد"\nاطبع الاسم') == "أحمد"


def test_reassignment():
    assert run("خلي س = 1\nس = 5\nاطبع س") == "5"


def test_implicit_declaration_warns():
    lines, bag = execute("س = 7\nاطبع س")
    assert lines == ["7"]
    assert bag.warnings[0].code == ErrorCode.IMPLICIT_DECLARATION


def test_if_then():
    source = "لو 5 أكبر من 3\n    اطبع \"كبير\"\nخلاص"
    assert run(source) == "كبير"


def test_if_else_taken_branch():
    source = "لو 1 أكبر من 3\n    اطبع \"أول\"\nغير كده\n    اطبع \"تاني\"\nخلاص"
    assert run(source) == "تاني"


def test_if_without_else():
    source = "لو غلط\n    اطبع \"أول\"\nخلاص"
    assert run(source) == ""


def test_while_loop():
    source = (
        "خلي العداد = 1\n"
        "طالما العداد أصغر أو يساوي 3\n"
        "    اطبع العداد\n"
        "    خلي العداد = العداد + 1\n"
        "خلاص"
    )
    assert run(source) == "1\n2\n3"


def test_repeat_loop():
    source = "كرر 3 مرات\n    اطبع \"مرحبًا\"\nخلاص"
    assert run(source) == "مرحبًا\nمرحبًا\nمرحبًا"


def test_repeat_zero_times():
    assert run("كرر 0 مرات\n    اطبع \"أبدًا\"\nخلاص") == ""


def test_nested_control_flow():
    source = (
        "كرر 2 مرات\n"
        "    لو صح\n"
        "        اطبع \"جوا\"\n"
        "    خلاص\n"
        "خلاص"
    )
    assert run(source) == "جوا\nجوا"


# ------------------------------------------------------------- expressions


def test_arithmetic_precedence():
    assert run("اطبع 2 + 3 * 4") == "14"
    assert run("اطبع 10 - 3 - 2") == "5"
    assert run("اطبع (2 + 3) * 4") == "20"


def test_word_operators():
    assert run("اطبع 5 زائد 3") == "8"
    assert run("اطبع 9 ناقص 4") == "5"
    assert run("اطبع 7 في 6") == "42"
    assert run("اطبع 20 على 4") == "5"


def test_percent_operator():
    assert run("اطبع 7 % 3") == "1"


def test_arabic_digits_arithmetic():
    assert run("اطبع ١٠ + ٥") == "15"
    assert run("اطبع ١٢٫٥") == "12.5"


def test_division_produces_float_printed_cleanly():
    assert run("اطبع 6 / 2") == "3"
    assert run("اطبع 7 / 2") == "3.5"


def test_comparisons():
    assert run("اطبع 5 أكبر من 3") == "صح"
    assert run("اطبع 5 أصغر أو يساوي 5") == "صح"
    assert run("اطبع 5 مش يساوي 6") == "صح"
    assert run("اطبع 5 يساوي 5") == "صح"


def test_logic_operators():
    assert run("اطبع صح و غلط") == "غلط"
    assert run("اطبع صح أو غلط") == "صح"
    assert run("اطبع غلط أو غلط") == "غلط"


def test_logic_short_circuits():
    # legacy Masry behaviour: right side is never evaluated when left is false
    lines, bag = execute("اطبع غلط و غيرمعرّف")
    assert lines == ["غلط"]
    assert not bag.has_errors


def test_string_concatenation():
    assert run('اطبع "العمر: " + 25') == "العمر: 25"
    assert run('خلي ن = "أحمد"\nاطبع "أهلاً " + ن') == "أهلاً أحمد"


def test_negative_numbers():
    assert run("اطبع -5") == "-5"
    assert run("اطبع 3 - 10") == "-7"


def test_string_comparison():
    assert run('اطبع "أحمد" يساوي "أحمد"') == "صح"


# -------------------------------------------------------------- environment


def test_environment_define_and_get():
    env = Environment()
    env.define("س", 5)
    assert env.get("س", span()) == 5


def test_environment_missing_raises_with_code():
    env = Environment()
    with pytest.raises(ArabiyaRuntimeError) as excinfo:
        env.get("س", span())
    assert excinfo.value.diagnostic.code == ErrorCode.UNDEFINED_VARIABLE
    assert "خلي" in (excinfo.value.diagnostic.suggestion or "")


def test_environment_parent_chain_lookup():
    parent = Environment()
    parent.define("عام", 1)
    child = parent.child()
    assert child.get("عام", span()) == 1


def test_environment_child_shadowing():
    parent = Environment()
    parent.define("س", 1)
    child = parent.child()
    child.define("س", 2)
    assert child.get("س", span()) == 2
    assert parent.get("س", span()) == 1


def test_environment_assign_walks_up_to_definition():
    parent = Environment()
    parent.define("س", 1)
    child = parent.child()
    child.assign("س", 9, span())
    assert parent.get("س", span()) == 9


def test_environment_assign_missing_raises():
    env = Environment()
    with pytest.raises(ArabiyaRuntimeError):
        env.assign("س", 1, span())


# ------------------------------------------------------------ runtime errors


def test_undefined_variable_error():
    error = runtime_error("اطبع س")
    assert error.diagnostic.code == ErrorCode.UNDEFINED_VARIABLE
    assert error.diagnostic.span.start.line == 1


def test_division_by_zero_error():
    error = runtime_error("اطبع 5 / 0")
    assert error.diagnostic.code == ErrorCode.DIVISION_BY_ZERO
    assert "صفر" in error.diagnostic.message


def test_modulo_by_zero_error():
    error = runtime_error("اطبع 5 % 0")
    assert error.diagnostic.code == ErrorCode.DIVISION_BY_ZERO


def test_unary_type_error():
    error = runtime_error('اطبع ناقص "أحمد"')
    assert error.diagnostic.code == ErrorCode.TYPE_ERROR


def test_arithmetic_type_error():
    error = runtime_error('اطبع "أحمد" - 1')
    assert error.diagnostic.code == ErrorCode.TYPE_ERROR


def test_comparison_type_error():
    error = runtime_error('اطبع 5 أكبر من "أحمد"')
    assert error.diagnostic.code == ErrorCode.TYPE_ERROR


def test_repeat_count_must_be_number():
    error = runtime_error('كرر "خمسة" مرات\n    اطبع 1\nخلاص')
    assert error.diagnostic.code == ErrorCode.INVALID_REPEAT_COUNT


def test_loop_guard(monkeypatch):
    import al_arabiya.runtime.interpreter.interpreter as interpreter_module

    monkeypatch.setattr(interpreter_module, "_MAX_LOOP_ITERATIONS", 10)
    error = runtime_error("طالما صح\n    خلي س = 1\nخلاص")
    assert error.diagnostic.code == ErrorCode.LOOP_LIMIT_EXCEEDED


# ------------------------------------------------------------------ helpers


def test_format_value():
    assert format_value(True) == "صح"
    assert format_value(False) == "غلط"
    assert format_value(3.0) == "3"
    assert format_value(3.5) == "3.5"
    assert format_value("نص") == "نص"
    assert format_value(10) == "10"


def test_is_truthy():
    assert is_truthy(1)
    assert not is_truthy(0)
    assert is_truthy("نص")
    assert not is_truthy("")
    assert is_truthy(True)
