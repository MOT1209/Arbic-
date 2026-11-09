"""Tests for function decorators (``مزخرف``)."""

from __future__ import annotations

import pytest

from al_arabiya.compiler.ast.nodes import FunctionDeclaration
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


WRAPPER = (
    "دالة سجل (دالة_أصلية)\n"
    "    دالة ملفوفة (س)\n"
    '        اطبع "قبل"\n'
    "        خلي ناتج = دالة_أصلية(س)\n"
    '        اطبع "بعد"\n'
    "        رجّع ناتج\n"
    "    خلاص\n"
    "    رجّع ملفوفة\n"
    "خلاص\n"
)


# ------------------------------------------------------------------ parsing


def test_parse_decorator_attaches_to_the_function():
    program = parse("دالة هوية (د)\n    رجّع د\nخلاص\nمزخرف هوية\nدالة ف ()\n    رجّع 1\nخلاص")
    function = program.body[1]
    assert isinstance(function, FunctionDeclaration)
    assert function.name == "ف"
    assert len(function.decorators) == 1


def test_decorator_must_be_followed_by_a_function():
    assert ErrorCode.UNEXPECTED_TOKEN in parse_errors("مزخرف هوية\nخلي س = 1")


# --------------------------------------------------------------- evaluation


def test_decorator_wraps_the_function():
    source = WRAPPER + "مزخرف سجل\nدالة ضعف (س)\n    رجّع س في 2\nخلاص\nاطبع ضعف(5)"
    assert run(source) == "قبل\nبعد\n10"


def test_decorators_apply_closest_first():
    source = (
        "دالة أول (د)\n"
        '    اطبع "أول"\n'
        "    رجّع د\n"
        "خلاص\n"
        "دالة تاني (د)\n"
        '    اطبع "تاني"\n'
        "    رجّع د\n"
        "خلاص\n"
        "مزخرف أول\n"
        "مزخرف تاني\n"
        "دالة ف ()\n"
        "    رجّع 1\n"
        "خلاص"
    )
    assert run(source) == "تاني\nأول"


def test_decorator_factory_receives_its_arguments():
    source = (
        "دالة مضاعف (ن)\n"
        "    دالة لافّ (دالة_أصلية)\n"
        "        دالة ملفوفة (س)\n"
        "            رجّع دالة_أصلية(س) في ن\n"
        "        خلاص\n"
        "        رجّع ملفوفة\n"
        "    خلاص\n"
        "    رجّع لافّ\n"
        "خلاص\n"
        "مزخرف مضاعف(3)\n"
        "دالة هوية (س)\n"
        "    رجّع س\n"
        "خلاص\n"
        "اطبع هوية(4)"
    )
    assert run(source) == "12"


def test_decorator_can_replace_the_function_with_a_lambda():
    source = (
        "دالة ثابت (د)\n"
        "    رجّع دالة ()\n"
        "        رجّع 7\n"
        "    خلاص\n"
        "خلاص\n"
        "مزخرف ثابت\n"
        "دالة ف ()\n"
        "    رجّع 1\n"
        "خلاص\n"
        "اطبع ف()"
    )
    assert run(source) == "7"


def test_decorator_arity_is_checked():
    source = (
        "دالة سيء (أ، ب)\n"
        "    رجّع أ\n"
        "خلاص\n"
        "مزخرف سيء\n"
        "دالة ف ()\n"
        "    رجّع 1\n"
        "خلاص"
    )
    assert runtime_error(source).diagnostic.code == ErrorCode.ARITY_MISMATCH


def test_decorator_must_be_callable():
    source = "خلي س = 5\nمزخرف س\nدالة ف ()\n    رجّع 1\nخلاص"
    assert runtime_error(source).diagnostic.code == ErrorCode.NOT_CALLABLE


# --------------------------------------------------------------- type check


def test_type_checker_rejects_a_non_callable_decorator():
    program = parse("خلي س : رقم = 5\nمزخرف س\nدالة ف ()\n    رجّع 1\nخلاص")
    codes = [d.code for d in check_types(program) if d.is_error]
    assert ErrorCode.TYPE_MISMATCH in codes


def test_type_checker_accepts_a_typed_decorator():
    source = (
        "دالة هوية (د : دالة) : دالة\n"
        "    رجّع د\n"
        "خلاص\n"
        "مزخرف هوية\n"
        "دالة ف () : رقم\n"
        "    رجّع 1\n"
        "خلاص"
    )
    program = parse(source)
    assert [d for d in check_types(program) if d.is_error] == []


# ---------------------------------------------------------------------- vm


def test_vm_falls_back_for_decorators():
    program = parse("دالة هوية (د)\n    رجّع د\nخلاص\nمزخرف هوية\nدالة ف ()\n    رجّع 1\nخلاص")
    reason = unsupported_reason(program)
    assert reason is not None
    assert "مزخرف" in reason
