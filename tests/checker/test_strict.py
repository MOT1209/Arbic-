"""Tests for the opt-in strict mode (ADR-05)."""

from __future__ import annotations

from al_arabiya.compiler.checker import check_types
from al_arabiya.compiler.diagnostics.errors import ErrorCode
from al_arabiya.compiler.frontend import compile_source


def strict_errors(source: str) -> list[str]:
    result = compile_source(source, "test.arb")
    assert result.program is not None, [
        (d.code, d.message) for d in result.diagnostics
    ]
    return [d.code for d in check_types(result.program, strict=True) if d.is_error]


def gradual_errors(source: str) -> list[str]:
    result = compile_source(source, "test.arb")
    assert result.program is not None
    return [d.code for d in check_types(result.program) if d.is_error]


def test_strict_requires_variable_annotations():
    assert ErrorCode.MISSING_ANNOTATION in strict_errors("خلي س = 5")


def test_annotated_program_is_clean_in_strict_mode():
    source = (
        "دالة اجمع (أ : رقم، ب : رقم) : رقم\n"
        "    رجّع أ زائد ب\n"
        "خلاص\n"
        "خلي س : رقم = اجمع(1، 2)\n"
        "اطبع س"
    )
    assert strict_errors(source) == []


def test_strict_requires_parameter_annotations():
    source = "دالة ا (س) : رقم\n    رجّع 1\nخلاص"
    assert ErrorCode.MISSING_ANNOTATION in strict_errors(source)


def test_strict_requires_a_return_annotation():
    source = "دالة ا (س : رقم)\n    رجّع 1\nخلاص"
    assert ErrorCode.MISSING_ANNOTATION in strict_errors(source)


def test_strict_reports_undefined_names():
    assert ErrorCode.UNDEFINED_NAME in strict_errors("خلي س : رقم = مجهول")


def test_gradual_mode_still_allows_undefined_names():
    assert gradual_errors("خلي س : رقم = مجهول") == []


def test_builtin_names_are_known_in_strict_mode():
    assert strict_errors("خلي س : رقم = طول([1])") == []


def test_lambdas_are_exempt_from_strict_annotations():
    source = "خلي ف : دالة = دالة (س)\n    رجّع س\nخلاص\nاطبع ف(1)"
    assert strict_errors(source) == []


def test_strict_keeps_ordinary_type_checks():
    assert ErrorCode.TYPE_MISMATCH in strict_errors('خلي س : رقم = "نص"')


def test_strict_reports_an_unknown_name_inside_a_function():
    source = "دالة ا (س : رقم) : رقم\n    رجّع س زائد مجهول\nخلاص"
    assert ErrorCode.UNDEFINED_NAME in strict_errors(source)
