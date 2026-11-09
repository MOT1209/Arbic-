"""Tests for full static types: generics, optionals, unions and inference."""

from __future__ import annotations

from al_arabiya.compiler.checker import check_types
from al_arabiya.compiler.diagnostics.errors import ErrorCode
from al_arabiya.compiler.frontend import compile_source


def diagnostics(source: str):
    result = compile_source(source, "test.arb")
    assert result.program is not None, [
        (d.code, d.message) for d in result.diagnostics
    ]
    return [d for d in check_types(result.program) if d.is_error]


def type_errors(source: str) -> list[str]:
    return [d.code for d in diagnostics(source)]


def is_clean(source: str) -> bool:
    return type_errors(source) == []


# ------------------------------------------------------------------ generics


def test_list_element_type_is_checked():
    assert is_clean("خلي ق : قائمة[رقم] = [1، 2، 3]")
    assert ErrorCode.TYPE_MISMATCH in type_errors('خلي ق : قائمة[رقم] = [1، "نص"]')


def test_nested_generic_is_clean():
    assert is_clean("خلي ق : قائمة[قائمة[رقم]] = [[1]، [2]]")


def test_map_key_and_value_are_checked():
    assert is_clean('خلي م : قاموس[نص، رقم] = {"أ": 1}')
    assert ErrorCode.TYPE_MISMATCH in type_errors('خلي م : قاموس[نص، رقم] = {1: 2}')
    assert ErrorCode.TYPE_MISMATCH in type_errors(
        'خلي م : قاموس[نص، رقم] = {"أ": "نص"}'
    )


def test_indexing_a_list_returns_the_element_type():
    source = "خلي ق : قائمة[رقم] = [1]\nخلي س : نص = ق[0]"
    assert ErrorCode.TYPE_MISMATCH in type_errors(source)


def test_indexing_a_map_checks_the_key_and_returns_the_value():
    base = 'خلي م : قاموس[نص، رقم] = {"أ": 1}\n'
    assert is_clean(base + "خلي س : رقم = م[\"أ\"]")
    assert ErrorCode.TYPE_MISMATCH in type_errors(base + "خلي س : نص = م[\"أ\"]")
    assert ErrorCode.TYPE_MISMATCH in type_errors(base + "خلي س : رقم = م[1]")


def test_for_each_binds_the_element_type():
    source = (
        'خلي ق : قائمة[نص] = ["أ"]\n'
        "لكل ع في ق\n"
        "    خلي س : رقم = ع\n"
        "خلاص"
    )
    assert ErrorCode.TYPE_MISMATCH in type_errors(source)


def test_inferred_literals_are_not_any():
    source = 'خلي ق = [1، "نص"]\nخلي س : قائمة[نص] = ق'
    assert ErrorCode.TYPE_MISMATCH in type_errors(source)


def test_function_parameter_uses_the_generic_type():
    source = (
        "دالة ا (ق : قائمة[رقم]) : رقم\n"
        "    رجّع 1\n"
        "خلاص\n"
        'اطبع ا(["نص"])'
    )
    assert ErrorCode.TYPE_MISMATCH in type_errors(source)


# --------------------------------------------------------- optional / union


def test_optional_accepts_the_value_and_null():
    assert is_clean("خلي س : اختياري[نص] = فراغ")
    assert is_clean('خلي س : اختياري[نص] = "أهلا"')


def test_optional_rejects_another_type():
    assert ErrorCode.TYPE_MISMATCH in type_errors("خلي س : اختياري[نص] = 5")


def test_optional_is_rendered_as_sugar_in_messages():
    messages = [d.message for d in diagnostics("خلي س : اختياري[نص] = 5")]
    assert any("اختياري[نص]" in message for message in messages)


def test_union_accepts_each_member():
    assert is_clean("خلي س : رقم أو نص = 5")
    assert is_clean('خلي س : رقم أو نص = "خمسة"')


def test_union_rejects_a_non_member():
    assert ErrorCode.TYPE_MISMATCH in type_errors("خلي س : رقم أو نص = صح")


def test_union_inside_a_generic():
    assert is_clean("خلي ق : قائمة[رقم أو نص] = [1، \"نص\"]")


# ------------------------------------------------------------ type arguments


def test_optional_without_argument_is_rejected():
    assert ErrorCode.INVALID_TYPE_ARGUMENT in type_errors("خلي س : اختياري = 1")


def test_wrong_generic_arity_is_rejected():
    assert ErrorCode.INVALID_TYPE_ARGUMENT in type_errors(
        "خلي س : قائمة[رقم، نص] = [1]"
    )
    assert ErrorCode.INVALID_TYPE_ARGUMENT in type_errors("خلي س : قاموس[نص] = {}")


def test_arguments_on_a_simple_type_are_rejected():
    assert ErrorCode.INVALID_TYPE_ARGUMENT in type_errors("خلي س : رقم[نص] = 1")


def test_unknown_type_inside_a_generic_is_reported():
    assert ErrorCode.UNKNOWN_TYPE_NAME in type_errors("خلي س : قائمة[لون] = []")


def test_bare_container_types_stay_gradual():
    assert is_clean("خلي س : قائمة = [1، \"نص\"]")
    assert is_clean('خلي م : قاموس = {"أ": 1}')
