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
    # collections
    'خلي ق = [1، 2، 3]\nاطبع ق\nاطبع ق[0]\nق[1] = 20\nاطبع ق',
    'اطبع [1، 2][-1]',
    'خلي م = {"أ": 1، "ب": 2}\nاطبع م["أ"]\nم["ج"] = 3\nاطبع م',
    'لكل س في [10، 20، 30]\n    اطبع س\nخلاص',
    'لكل ح في "اب"\n    اطبع ح\nخلاص',
    'خلي مج = 0\nلكل ن في [1، 2، 3، 4]\n    مج = مج زائد ن\nخلاص\nاطبع مج',
    'اطبع رتب([3، 1، 2])\nاطبع مجموع([1، 2، 3])\nاطبع مدى(1، 4)',
    # repeat
    'كرر 3 مرات\n    اطبع "مرة"\nخلاص',
    'كرر 5 مرات\n    اطبع "x"\n    اكسر\nخلاص',
    # exceptions
    'حاول\n    اطبع 10 على 0\nامسك خطأ\n    اطبع خطأ["الكود"]\nخلاص',
    'حاول\n    ارم "مشكلة"\nامسك e\n    اطبع e\nخلاص',
    'حاول\n    اطبع 1\nأخيرا\n    اطبع 2\nخلاص',
    'حاول\n    ارم 1\nامسك e\n    اطبع 2\nأخيرا\n    اطبع 3\nخلاص',
    (
        "حاول\n    حاول\n        ارم 1\n    امسك\n        اطبع \"داخلي\"\n"
        "    خلاص\nامسك\n    اطبع \"خارجي\"\nخلاص"
    ),
    'دالة ض ()\n    ارم "من الدالة"\nخلاص\nحاول\n    ض()\nامسك e\n    اطبع e\nخلاص',
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


def test_index_out_of_range():
    assert vm_error("اطبع [1، 2][9]").diagnostic.code == ErrorCode.INDEX_OUT_OF_RANGE


def test_key_not_found():
    assert vm_error('اطبع {"أ": 1}["ب"]').diagnostic.code == ErrorCode.KEY_NOT_FOUND


def test_not_iterable():
    assert vm_error("لكل س في 5\n    اطبع س\nخلاص").diagnostic.code == ErrorCode.NOT_ITERABLE


def test_unhashable_key():
    assert vm_error("اطبع {[1]: 2}").diagnostic.code == ErrorCode.UNHASHABLE_KEY


def test_uncaught_throw():
    assert vm_error('ارم "خطأ"').diagnostic.code == ErrorCode.UNCAUGHT_ERROR


# ------------------------------------------------------------- supportability


@pytest.mark.parametrize(
    "source,fragment",
    [
        ("دالة ا ()\n    دالة ب ()\n        رجّع 1\n    خلاص\nخلاص", "المتداخلة"),
        # a رجّع that would jump out across a أخيرا
        (
            "دالة ق ()\n    حاول\n        رجّع 1\n    أخيرا\n        اطبع 2\n    خلاص\nخلاص",
            "أخيرا",
        ),
    ],
)
def test_unsupported_features_are_detected(source: str, fragment: str):
    reason = unsupported_reason(_program(source))
    assert reason is not None
    assert fragment in reason


@pytest.mark.parametrize(
    "source",
    [
        "دالة ا (س)\n    رجّع س زائد 1\nخلاص\nاطبع ا(2)",
        "اطبع [1، 2، 3]",
        'اطبع {"أ": 1}',
        "لكل س في [1، 2]\n    اطبع س\nخلاص",
        "كرر 3 مرات\n    اطبع 1\nخلاص",
        'حاول\n    ارم 1\nامسك e\n    اطبع e\nأخيرا\n    اطبع 2\nخلاص',
        # break inside a nested loop within a try does not escape the try
        "حاول\n    كرر 3 مرات\n        اكسر\n    خلاص\nامسك\n    اطبع 1\nخلاص",
    ],
)
def test_supported_programs_have_no_reason(source: str):
    assert unsupported_reason(_program(source)) is None


# ------------------------------------------------------------------ closures


def test_higher_order_builtin_argument_count_variadic():
    # اقرأ is variadic (arity -1); calling with zero args must not raise arity
    assert run_vm('اطبع نوع(مطلق(ناقص 3))') == run_tree('اطبع نوع(مطلق(ناقص 3))')
