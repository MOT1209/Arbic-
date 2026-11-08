"""Tests for Phase 2: functions, return, calls, builtins and loop control."""

from __future__ import annotations

import pytest

from al_arabiya.compiler.ast.nodes import (
    CallExpression,
    ExpressionStatement,
    FunctionDeclaration,
    ReturnStatement,
)
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
    interpreter = Interpreter(write=lambda _text: None)
    with pytest.raises(ArabiyaRuntimeError) as excinfo:
        interpreter.run(result.program)
    return excinfo.value


# ------------------------------------------------------------------ parsing


def test_parse_function_declaration():
    program = parse("دالة اجمع (أ، ب)\n    رجّع أ زائد ب\nخلاص")
    declaration = program.body[0]
    assert isinstance(declaration, FunctionDeclaration)
    assert declaration.name == "اجمع"
    assert [p.name for p in declaration.parameters] == ["أ", "ب"]
    assert isinstance(declaration.body[0], ReturnStatement)


def test_parse_call_statement():
    program = parse("دالة ا ()\n    رجّع 1\nخلاص\nا()")
    statement = program.body[1]
    assert isinstance(statement, ExpressionStatement)
    assert isinstance(statement.expression, CallExpression)


def test_ascii_and_arabic_comma_both_separate_arguments():
    assert run("دالة ج (أ، ب)\n    رجّع أ زائد ب\nخلاص\nاطبع ج(1، 2)") == "3"
    assert run("دالة ج (أ,ب)\n    رجّع أ زائد ب\nخلاص\nاطبع ج(1,2)") == "3"


def test_bare_expression_still_errors():
    assert ErrorCode.UNEXPECTED_TOKEN in parse_errors("1 زائد 2")


# --------------------------------------------------------------- evaluation


def test_call_returns_value():
    assert run("دالة اجمع (أ، ب)\n    رجّع أ زائد ب\nخلاص\nاطبع اجمع(2، 3)") == "5"


def test_recursion():
    source = (
        "دالة مضروب (ن)\n"
        "    لو ن أصغر أو يساوي 1\n"
        "        رجّع 1\n"
        "    خلاص\n"
        "    رجّع ن في مضروب(ن ناقص 1)\n"
        "خلاص\n"
        "اطبع مضروب(5)"
    )
    assert run(source) == "120"


def test_closure_captures_scope():
    source = (
        "دالة عداد ()\n"
        "    خلي س = 0\n"
        "    دالة زود ()\n"
        "        س = س زائد 1\n"
        "        رجّع س\n"
        "    خلاص\n"
        "    رجّع زود\n"
        "خلاص\n"
        "خلي ز = عداد()\n"
        "اطبع ز()\n"
        "اطبع ز()"
    )
    assert run(source) == "1\n2"


def test_function_without_return_yields_null():
    assert run("دالة لاشيء ()\n    خلي س = 1\nخلاص\nاطبع لاشيء()") == "فراغ"


def test_parameters_are_scoped_to_the_call():
    source = "دالة ض (س)\n    رجّع س\nخلاص\nخلي س = 10\nاطبع ض(3)\nاطبع س"
    assert run(source) == "3\n10"


# ----------------------------------------------------------- loop control


def test_break_stops_loop():
    assert run("كرر 5 مرات\n    اطبع 1\n    اكسر\nخلاص") == "1"


def test_continue_skips_rest_of_iteration():
    source = (
        "خلي ع = 0\n"
        "طالما ع أصغر من 5\n"
        "    ع = ع زائد 1\n"
        "    لو ع يساوي 3\n"
        "        كمل\n"
        "    خلاص\n"
        "    اطبع ع\n"
        "خلاص"
    )
    assert run(source) == "1\n2\n4\n5"


# ------------------------------------------------------------------ null


def test_null_literal_is_falsy():
    assert run("لو فراغ\n    اطبع 1\nغير كده\n    اطبع 2\nخلاص") == "2"


# ---------------------------------------------------------------- errors


def test_arity_mismatch():
    error = runtime_error("دالة ا (أ، ب)\n    رجّع أ\nخلاص\nاطبع ا(1)")
    assert error.diagnostic.code == ErrorCode.ARITY_MISMATCH


def test_calling_non_function():
    error = runtime_error("خلي س = 5\nاطبع س(1)")
    assert error.diagnostic.code == ErrorCode.NOT_CALLABLE


def test_return_outside_function():
    error = runtime_error("رجّع 5")
    assert error.diagnostic.code == ErrorCode.RETURN_OUTSIDE_FUNCTION


def test_break_outside_loop():
    error = runtime_error("اكسر")
    assert error.diagnostic.code == ErrorCode.LOOP_CONTROL_OUTSIDE_LOOP


def test_break_cannot_escape_function_into_outer_loop():
    source = "دالة خطر ()\n    اكسر\nخلاص\nكرر 3 مرات\n    خطر()\nخلاص"
    error = runtime_error(source)
    assert error.diagnostic.code == ErrorCode.LOOP_CONTROL_OUTSIDE_LOOP


# --------------------------------------------------------------- builtins


def test_len_builtin():
    assert run('اطبع طول("مرحبا")') == "5"


def test_type_builtin():
    assert run("اطبع نوع(5)") == "رقم"
    assert run('اطبع نوع("نص")') == "نص"
    assert run("اطبع نوع(صح)") == "منطقي (صح/غلط)"


def test_number_and_text_casts():
    assert run('اطبع رقم("42") زائد 8') == "50"
    assert run("اطبع نص(10) زائد \"!\"") == "10!"


def test_abs_and_round_builtins():
    assert run("اطبع مطلق(-7)") == "7"
    assert run("اطبع قرّب(3.7)") == "4"


def test_builtin_type_error_is_located():
    error = runtime_error("اطبع طول(5)")
    assert error.diagnostic.code == ErrorCode.BUILTIN_ERROR


def test_builtin_arity_is_checked():
    error = runtime_error("اطبع طول()")
    assert error.diagnostic.code == ErrorCode.ARITY_MISMATCH
