"""Inheritance tests: single base, overrides, ``الأساس`` and initialization."""

from __future__ import annotations

import pytest

from al_arabiya.compiler.ast.nodes import ClassDeclaration
from al_arabiya.compiler.checker import check_types
from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag, render_diagnostics
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.runtime.interpreter.interpreter import Interpreter
from al_arabiya.vm.compiler import unsupported_reason

PERSON = """
صنف شخص
    دالة __تهيئة__(الاسم)
        انا.الاسم = الاسم
    خلاص

    دالة عرّف()
        رجّع "أنا " + انا.الاسم
    خلاص

    دالة ساكنة نوع()
        رجّع "إنسان"
    خلاص
خلاص
"""

STUDENT = (
    PERSON
    + """
صنف طالب يرث شخص
    دالة __تهيئة__(الاسم، الصف)
        الأساس.__تهيئة__(الاسم)
        انا.الصف = الصف
    خلاص

    دالة عرّف()
        رجّع الأساس.عرّف() + " في " + انا.الصف
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


def test_class_header_records_the_base_name():
    program = compile_program(STUDENT)
    student = program.body[-1]
    assert isinstance(student, ClassDeclaration)
    assert student.name == "طالب"
    assert student.base_name == "شخص"


# --------------------------------------------------------------- execution


def test_subclass_inherits_methods_and_static_methods():
    source = (
        PERSON
        + "\nصنف طالب يرث شخص\nخلاص\nخلي ط = طالب(\"سارة\")\n"
        + "اطبع ط.عرّف()\nاطبع طالب.نوع()"
    )
    assert run(source) == "أنا سارة\nإنسان"


def test_subclass_without_initializer_uses_the_base_initializer():
    source = (
        PERSON
        + "\nصنف طالب يرث شخص\nخلاص\n"
        + 'خلي ط = طالب("سارة")\nاطبع ط.الاسم'
    )
    assert run(source) == "سارة"


def test_override_replaces_the_base_method():
    source = (
        PERSON
        + """
صنف طالب يرث شخص
    دالة عرّف()
        رجّع "طالب"
    خلاص
خلاص
خلي ط = طالب("سارة")
اطبع ط.عرّف()
"""
    )
    assert run(source) == "طالب"


def test_super_calls_the_base_method_on_the_same_instance():
    source = STUDENT + '\nخلي ط = طالب("سارة"، "الثاني")\nاطبع ط.عرّف()'
    assert run(source) == "أنا سارة في الثاني"


def test_super_initializer_chains_base_fields():
    source = STUDENT + '\nخلي ط = طالب("سارة"، "الثاني")\nاطبع ط.الاسم\nاطبع ط.الصف'
    assert run(source) == "سارة\nالثاني"


def test_subclass_initializer_does_not_call_the_base_automatically():
    source = (
        PERSON
        + """
صنف طالب يرث شخص
    دالة __تهيئة__(الصف)
        انا.الصف = الصف
    خلاص
خلاص
خلي ط = طالب("الثاني")
"""
    )
    assert runtime_error(source + "\nاطبع ط.الاسم").diagnostic.code == (
        ErrorCode.MEMBER_NOT_FOUND
    )


def test_super_without_a_base_is_undefined():
    source = (
        "صنف وحيد\n"
        "    دالة اطبع_الأساس()\n"
        "        اطبع الأساس\n"
        "    خلاص\n"
        "خلاص\n"
        "وحيد().اطبع_الأساس()"
    )
    assert runtime_error(source).diagnostic.code == ErrorCode.UNDEFINED_VARIABLE


# -------------------------------------------------------------------- errors


def test_base_must_be_defined_before_the_subclass():
    error = runtime_error("صنف طالب يرث شخص\nخلاص")
    assert error.diagnostic.code == ErrorCode.INVALID_BASE_CLASS


def test_base_must_be_a_class():
    error = runtime_error("خلي س = 5\nصنف طالب يرث س\nخلاص")
    assert error.diagnostic.code == ErrorCode.INVALID_BASE_CLASS


def test_super_cannot_assign_fields():
    source = (
        PERSON
        + """
صنف طالب يرث شخص
    دالة غيّر()
        الأساس.الاسم = "آخر"
    خلاص
خلاص
طالب("سارة").غيّر()
"""
    )
    assert runtime_error(source).diagnostic.code == ErrorCode.INVALID_MEMBER_ACCESS


def test_super_missing_method_reports_member_not_found():
    source = (
        PERSON
        + """
صنف طالب يرث شخص
    دالة نادي()
        رجّع الأساس.مش_موجود()
    خلاص
خلاص
طالب("سارة").نادي()
"""
    )
    assert runtime_error(source).diagnostic.code == ErrorCode.MEMBER_NOT_FOUND


# ----------------------------------------------------------------- tooling


def test_vm_falls_back_for_inheritance():
    assert unsupported_reason(compile_program(STUDENT)) is not None


def test_type_checker_accepts_super_and_inheritance():
    source = STUDENT + '\nخلي ط : صنف = طالب("سارة"، "الثاني")\nاطبع ط.عرّف()'
    assert check_types(compile_program(source)).errors == []
