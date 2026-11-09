"""Encapsulation tests: ``خاص`` privacy and ``واجهة``/``ينفذ`` contracts."""

from __future__ import annotations

import pytest

from al_arabiya.compiler.ast.nodes import ClassDeclaration, InterfaceDeclaration
from al_arabiya.compiler.checker import check_types
from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag, render_diagnostics
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.runtime.interpreter.interpreter import Interpreter
from al_arabiya.vm.compiler import unsupported_reason

ACCOUNT = """
صنف حساب
    خاص الرصيد

    دالة __تهيئة__(الرصيد)
        انا.الرصيد = الرصيد
    خلاص

    خاص دالة تحقق(المبلغ)
        رجّع المبلغ أصغر أو يساوي انا.الرصيد
    خلاص

    دالة اسحب(المبلغ)
        لو انا.تحقق(المبلغ)
            انا.الرصيد = انا.الرصيد - المبلغ
            رجّع صح
        خلاص
        رجّع غلط
    خلاص

    دالة الرصيد_الحالي()
        رجّع انا.الرصيد
    خلاص
خلاص
"""

PRINTABLE = """
واجهة قابل_للطباعة
    دالة اطبع_نفسك() : نص
    دالة ساكنة اسم_النوع() : نص
خلاص
"""

PERSON = (
    PRINTABLE
    + """
صنف شخص ينفذ قابل_للطباعة
    دالة __تهيئة__(الاسم)
        انا.الاسم = الاسم
    خلاص

    دالة اطبع_نفسك() : نص
        رجّع "أنا " + انا.الاسم
    خلاص

    دالة ساكنة اسم_النوع() : نص
        رجّع "شخص"
    خلاص
خلاص
"""
)


def compile_program(source: str):
    result = compile_source(source, "test.arb")
    assert result.program is not None, render_diagnostics(result.diagnostics, result.source)
    return result.program


def run(source: str) -> str:
    program = compile_program(source)
    lines: list[str] = []
    Interpreter(diagnostics=DiagnosticBag(), write=lines.append).run(program)
    return "\n".join(lines)


def runtime_error(source: str) -> ArabiyaRuntimeError:
    program = compile_program(source)
    with pytest.raises(ArabiyaRuntimeError) as excinfo:
        Interpreter(write=lambda _text: None).run(program)
    return excinfo.value


# ------------------------------------------------------------------- parsing


def test_private_members_and_fields_are_recorded():
    program = compile_program(ACCOUNT)
    account = program.body[0]
    assert isinstance(account, ClassDeclaration)
    assert [field.name for field in account.private_fields] == ["الرصيد"]
    assert [method.name for method in account.methods if method.is_private] == [
        "تحقق"
    ]


def test_interface_declaration_records_signatures():
    program = compile_program(PRINTABLE)
    interface = program.body[0]
    assert isinstance(interface, InterfaceDeclaration)
    assert interface.name == "قابل_للطباعة"
    assert [method.name for method in interface.methods] == [
        "اطبع_نفسك",
        "اسم_النوع",
    ]
    assert all(method.is_abstract for method in interface.methods)
    assert interface.methods[1].is_static


def test_class_header_records_implemented_interfaces():
    program = compile_program(PERSON)
    person = program.body[-1]
    assert isinstance(person, ClassDeclaration)
    assert [interface.name for interface in person.interfaces] == ["قابل_للطباعة"]


# ------------------------------------------------------------------ privacy


def test_private_members_are_usable_inside_the_class():
    source = (
        ACCOUNT
        + "\nخلي ح = حساب(100)\nاطبع ح.الرصيد_الحالي()\n"
        + "اطبع ح.اسحب(30)\nاطبع ح.الرصيد_الحالي()"
    )
    assert run(source) == "100\nصح\n70"


def test_private_field_read_from_outside_is_rejected():
    source = ACCOUNT + "\nخلي ح = حساب(100)\nاطبع ح.الرصيد"
    assert runtime_error(source).diagnostic.code == ErrorCode.PRIVATE_MEMBER_ACCESS


def test_private_field_write_from_outside_is_rejected():
    source = ACCOUNT + "\nخلي ح = حساب(100)\nح.الرصيد = 1000"
    assert runtime_error(source).diagnostic.code == ErrorCode.PRIVATE_MEMBER_ACCESS


def test_private_method_from_outside_is_rejected():
    source = ACCOUNT + "\nخلي ح = حساب(100)\nاطبع ح.تحقق(10)"
    assert runtime_error(source).diagnostic.code == ErrorCode.PRIVATE_MEMBER_ACCESS


def test_subclass_cannot_read_or_call_base_private_members():
    source = (
        ACCOUNT
        + """
صنف حساب_مميز يرث حساب
    دالة اكشف()
        رجّع انا.الرصيد
    خلاص
خلاص
حساب_مميز(10).اكشف()
"""
    )
    assert runtime_error(source).diagnostic.code == ErrorCode.PRIVATE_MEMBER_ACCESS


def test_super_cannot_call_a_private_base_method():
    source = (
        ACCOUNT
        + """
صنف حساب_مميز يرث حساب
    دالة اكشف()
        رجّع الأساس.تحقق(1)
    خلاص
خلاص
حساب_مميز(10).اكشف()
"""
    )
    assert runtime_error(source).diagnostic.code == ErrorCode.PRIVATE_MEMBER_ACCESS


def test_private_static_method_is_rejected_from_outside():
    source = """
صنف خدمة
    خاص دالة ساكنة سر()
        رجّع 42
    خلاص

    دالة ساكنة اكشف()
        رجّع خدمة.سر()
    خلاص
خلاص
اطبع خدمة.اكشف()
اطبع خدمة.سر()
"""
    assert runtime_error(source).diagnostic.code == ErrorCode.PRIVATE_MEMBER_ACCESS


def test_private_field_name_cannot_shadow_the_base():
    source = (
        ACCOUNT
        + """
صنف حساب_مميز يرث حساب
    خاص الرصيد
خلاص
"""
    )
    assert runtime_error(source).diagnostic.code == ErrorCode.PRIVATE_MEMBER_CONFLICT


def test_private_method_cannot_override_an_inherited_method():
    source = (
        ACCOUNT
        + """
صنف حساب_مميز يرث حساب
    خاص دالة اسحب(المبلغ)
        رجّع غلط
    خلاص
خلاص
"""
    )
    assert runtime_error(source).diagnostic.code == ErrorCode.PRIVATE_MEMBER_CONFLICT


def test_initializer_cannot_be_private():
    source = "صنف س\n    خاص دالة __تهيئة__()\n    خلاص\nخلاص\n"
    assert runtime_error(source).diagnostic.code == ErrorCode.PRIVATE_MEMBER_CONFLICT


# ---------------------------------------------------------------- interfaces


def test_interface_contract_is_callable_through_the_class():
    source = PERSON + '\nخلي ش = شخص("سارة")\nاطبع ش.اطبع_نفسك()\nاطبع شخص.اسم_النوع()'
    assert run(source) == "أنا سارة\nشخص"


def test_inherited_public_method_satisfies_the_interface():
    source = PRINTABLE + """
صنف شخص
    دالة اطبع_نفسك() : نص
        رجّع "شخص"
    خلاص

    دالة ساكنة اسم_النوع() : نص
        رجّع "شخص"
    خلاص
خلاص

صنف طالب يرث شخص ينفذ قابل_للطباعة
خلاص
اطبع طالب().اطبع_نفسك()
"""
    assert run(source) == "شخص"


def test_multiple_interfaces_can_be_implemented():
    source = PRINTABLE + """
واجهة مسجّل
    دالة سجّل()
خلاص

صنف خدمة ينفذ قابل_للطباعة، مسجّل
    دالة اطبع_نفسك() : نص
        رجّع "خدمة"
    خلاص

    دالة ساكنة اسم_النوع() : نص
        رجّع "خدمة"
    خلاص

    دالة سجّل()
        رجّع صح
    خلاص
خلاص
خلي خ = خدمة()
اطبع خ.اطبع_نفسك()
اطبع خ.سجّل()
"""
    assert run(source) == "خدمة\nصح"


def test_missing_interface_method_is_rejected():
    source = PRINTABLE + "\nصنف غير_مكتمل ينفذ قابل_للطباعة\nخلاص\n"
    assert runtime_error(source).diagnostic.code == ErrorCode.MISSING_INTERFACE_MEMBER


def test_wrong_interface_arity_is_rejected():
    source = PRINTABLE + """
صنف غير_مكتمل ينفذ قابل_للطباعة
    دالة اطبع_نفسك(س) : نص
        رجّع "س"
    خلاص
    دالة ساكنة اسم_النوع() : نص
        رجّع "س"
    خلاص
خلاص
"""
    assert runtime_error(source).diagnostic.code == ErrorCode.MISSING_INTERFACE_MEMBER


def test_wrong_interface_return_type_is_rejected():
    source = PRINTABLE + """
صنف غير_مكتمل ينفذ قابل_للطباعة
    دالة اطبع_نفسك() : رقم
        رجّع 1
    خلاص
    دالة ساكنة اسم_النوع() : نص
        رجّع "س"
    خلاص
خلاص
"""
    assert runtime_error(source).diagnostic.code == ErrorCode.MISSING_INTERFACE_MEMBER


def test_private_method_cannot_satisfy_an_interface():
    source = PRINTABLE + """
صنف غير_مكتمل ينفذ قابل_للطباعة
    خاص دالة اطبع_نفسك() : نص
        رجّع "س"
    خلاص
    دالة ساكنة اسم_النوع() : نص
        رجّع "س"
    خلاص
خلاص
"""
    assert runtime_error(source).diagnostic.code == ErrorCode.MISSING_INTERFACE_MEMBER


def test_undefined_interface_is_rejected():
    error = runtime_error("صنف س ينفذ مش_موجودة\nخلاص\n")
    assert error.diagnostic.code == ErrorCode.INVALID_INTERFACE


def test_a_class_cannot_be_implemented_as_an_interface():
    source = "صنف أبو\nخلاص\nصنف ابن ينفذ أبو\nخلاص\n"
    assert runtime_error(source).diagnostic.code == ErrorCode.INVALID_INTERFACE


def test_interface_is_not_instantiable():
    error = runtime_error(PRINTABLE + "\nقابل_للطباعة()")
    assert error.diagnostic.code == ErrorCode.NOT_CALLABLE


# ----------------------------------------------------------------- tooling


def test_vm_falls_back_for_interfaces():
    assert unsupported_reason(compile_program(PRINTABLE)) is not None


def test_type_checker_accepts_private_members_and_interfaces():
    source = PERSON + '\nخلي ش : صنف = شخص("سارة")\nاطبع ش.اطبع_نفسك()'
    assert check_types(compile_program(source)).errors == []


def test_type_checker_reports_a_missing_interface_method():
    source = PRINTABLE + "\nصنف غير_مكتمل ينفذ قابل_للطباعة\nخلاص\n"
    codes = {error.code for error in check_types(compile_program(source)).errors}
    assert ErrorCode.MISSING_INTERFACE_MEMBER in codes
