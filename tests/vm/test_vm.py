"""Tests for the bytecode compiler + stack VM, incl. parity with the interpreter."""

from __future__ import annotations

import pytest

from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.runtime.interpreter.interpreter import Interpreter
from al_arabiya.vm.compiler import compile_program, unsupported_reason
from al_arabiya.vm.vm import VM


def _program(source: str):
    result = compile_source(source, "test.arb")
    assert result.program is not None, [(d.code, d.message) for d in result.diagnostics]
    return result.program


def run_tree(source: str) -> str:
    out: list[str] = []
    Interpreter(write=out.append).run(_program(source))
    return "\n".join(out)


def run_vm(source: str) -> str:
    out: list[str] = []
    VM(write=out.append).run(compile_program(_program(source)))
    return "\n".join(out)


def vm_error(source: str) -> ArabiyaRuntimeError:
    with pytest.raises(ArabiyaRuntimeError) as excinfo:
        VM(write=lambda _t: None).run(compile_program(_program(source)))
    return excinfo.value


PARITY_PROGRAMS = [
    'اطبع 1 زائد 2 في 3',
    'اطبع (1 زائد 2) في 3',
    'اطبع 10 على 4',
    'اطبع 17 % 5',
    'اطبع ناقص 7',
    'خلي س = 5\nس = س زائد 1\nاطبع س',
    'اطبع "أ" زائد "ب" زائد 3',
    'اطبع 3 أكبر من 2\nاطبع 2 أكبر أو يساوي 5\nاطبع 2 يساوي 2\nاطبع 2 مش يساوي 3',
    'اطبع صح و غلط\nاطبع صح أو غلط\nاطبع غلط أو صح',
    'لو 3 أكبر من 2\n    اطبع "أ"\nغير كده\n    اطبع "ب"\nخلاص',
    'خلي ع = 0\nطالما ع أصغر من 4\n    اطبع ع\n    ع = ع زائد 1\nخلاص',
    'خلي ع = 0\nطالما صح\n    ع = ع زائد 1\n    لو ع يساوي 3\n        اكسر\n    خلاص\nخلاص\nاطبع ع',
    (
        "خلي ع = 0\nخلي مج = 0\nطالما ع أصغر من 5\n    ع = ع زائد 1\n"
        "    لو ع يساوي 3\n        كمل\n    خلاص\n    مج = مج زائد ع\nخلاص\nاطبع مج"
    ),
    'دالة مربع (س)\n    رجّع س في س\nخلاص\nاطبع مربع(7)',
    (
        "دالة مضروب (ن)\n    لو ن أصغر أو يساوي 1\n        رجّع 1\n    خلاص\n"
        "    رجّع ن في مضروب(ن ناقص 1)\nخلاص\nاطبع مضروب(6)"
    ),
    'دالة لاشيء ()\n    خلي س = 1\nخلاص\nاطبع لاشيء()',
    'اطبع طول("مرحبا")\nاطبع مطلق(ناقص 9)',
    'اطبع فراغ',
]


@pytest.mark.parametrize("source", PARITY_PROGRAMS, ids=range(len(PARITY_PROGRAMS)))
def test_vm_matches_interpreter(source: str):
    assert run_vm(source) == run_tree(source)


# -------------------------------------------------------------- error parity


def test_division_by_zero():
    assert vm_error("اطبع 1 على 0").diagnostic.code == ErrorCode.DIVISION_BY_ZERO


def test_undefined_variable():
    assert vm_error("اطبع مجهول").diagnostic.code == ErrorCode.UNDEFINED_VARIABLE


def test_type_error_in_arithmetic():
    assert vm_error('اطبع "x" ناقص 1').diagnostic.code == ErrorCode.TYPE_ERROR


def test_arity_mismatch():
    source = "دالة ا (أ، ب)\n    رجّع أ\nخلاص\nاطبع ا(1)"
    assert vm_error(source).diagnostic.code == ErrorCode.ARITY_MISMATCH


def test_not_callable():
    assert vm_error("خلي س = 5\nاطبع س(1)").diagnostic.code == ErrorCode.NOT_CALLABLE


def test_builtin_error():
    assert vm_error("اطبع طول(5)").diagnostic.code == ErrorCode.BUILTIN_ERROR


# ------------------------------------------------------------- supportability


@pytest.mark.parametrize(
    "source,fragment",
    [
        ("اطبع [1، 2]", "القوائم"),
        ("اطبع {\"أ\": 1}", "القواميس"),
        ("كرر 3 مرات\n    اطبع 1\nخلاص", "كرر"),
        ("لكل س في [1]\n    اطبع س\nخلاص", "لكل"),
        ("حاول\n    اطبع 1\nأخيرا\n    اطبع 2\nخلاص", "حاول"),
        ('ارم "x"', "ارم"),
        ('استورد "m"', "استورد"),
        ("دالة ا ()\n    دالة ب ()\n        رجّع 1\n    خلاص\nخلاص", "المتداخلة"),
    ],
)
def test_unsupported_features_are_detected(source: str, fragment: str):
    reason = unsupported_reason(_program(source))
    assert reason is not None
    assert fragment in reason


def test_supported_program_has_no_reason():
    source = "دالة ا (س)\n    رجّع س زائد 1\nخلاص\nاطبع ا(2)"
    assert unsupported_reason(_program(source)) is None


# ------------------------------------------------------------------ closures


def test_higher_order_builtin_argument_count_variadic():
    # اقرأ is variadic (arity -1); calling with zero args must not raise arity
    assert run_vm('اطبع نوع(مطلق(ناقص 3))') == run_tree('اطبع نوع(مطلق(ناقص 3))')
