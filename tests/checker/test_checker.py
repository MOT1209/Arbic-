"""Tests for the optional, gradual static type checker."""

from __future__ import annotations

from al_arabiya.compiler.checker import check_types
from al_arabiya.compiler.diagnostics.errors import ErrorCode
from al_arabiya.compiler.frontend import compile_source


def type_errors(source: str) -> list[str]:
    result = compile_source(source, "test.arb")
    assert result.program is not None, [(d.code, d.message) for d in result.diagnostics]
    bag = check_types(result.program)
    return [d.code for d in bag if d.is_error]


def is_clean(source: str) -> bool:
    return type_errors(source) == []


# --------------------------------------------------- gradual / non-breaking


def test_unannotated_program_is_clean():
    assert is_clean('خلي س = 5\nاطبع س + 1\nخلي ن = "نص"\nاطبع ن')


def test_annotation_matching_value_is_clean():
    assert is_clean("خلي س : رقم = 5")
    assert is_clean('خلي ن : نص = "أهلا"')
    assert is_clean("خلي ب : منطقي = صح")
    assert is_clean("خلي ق : قائمة = [1، 2]")


def test_any_is_compatible_both_ways():
    # unknown function result is `أي`, usable where a number is expected
    assert is_clean("خلي س : رقم = مجهول()\nاطبع س + 1")


# ------------------------------------------------------------- mismatches


def test_declaration_type_mismatch():
    assert ErrorCode.TYPE_MISMATCH in type_errors('خلي س : رقم = "نص"')


def test_unknown_type_name():
    assert ErrorCode.UNKNOWN_TYPE_NAME in type_errors("خلي س : لون = 5")


def test_arithmetic_on_non_numbers():
    assert ErrorCode.TYPE_MISMATCH in type_errors('خلي ن : نص = "x"\nاطبع ن ناقص 1')


def test_string_concat_is_allowed():
    assert is_clean('خلي ن : نص = "x"\nاطبع ن زائد 1')


def test_assignment_type_mismatch():
    assert ErrorCode.TYPE_MISMATCH in type_errors('خلي س : رقم = 1\nس = "نص"')


# -------------------------------------------------------------- functions


def test_typed_function_is_clean():
    source = "دالة اجمع (أ : رقم، ب : رقم) : رقم\n    رجّع أ زائد ب\nخلاص\nاطبع اجمع(2، 3)"
    assert is_clean(source)


def test_return_type_mismatch():
    source = 'دالة ا (أ : رقم) : رقم\n    رجّع "نص"\nخلاص'
    assert ErrorCode.TYPE_MISMATCH in type_errors(source)


def test_argument_type_mismatch():
    source = 'دالة ض (أ : رقم) : رقم\n    رجّع أ\nخلاص\nاطبع ض("نص")'
    assert ErrorCode.TYPE_MISMATCH in type_errors(source)


def test_argument_count_mismatch():
    source = "دالة ض (أ : رقم) : رقم\n    رجّع أ\nخلاص\nاطبع ض(1، 2)"
    assert ErrorCode.ARGUMENT_COUNT in type_errors(source)


def test_call_return_type_flows_into_annotation():
    source = (
        "دالة اسم () : نص\n"
        '    رجّع "أحمد"\n'
        "خلاص\n"
        "خلي س : رقم = اسم()"  # نص assigned to رقم
    )
    assert ErrorCode.TYPE_MISMATCH in type_errors(source)


def test_unannotated_params_are_any():
    # no annotations => gradual => no errors even if misused numerically
    source = "دالة ا (أ)\n    رجّع أ زائد 1\nخلاص\nاطبع ا(\"نص\")"
    assert is_clean(source)


def test_repeat_count_must_be_number():
    assert ErrorCode.TYPE_MISMATCH in type_errors('خلي ن : نص = "x"\nكرر ن مرات\n    اطبع 1\nخلاص')
