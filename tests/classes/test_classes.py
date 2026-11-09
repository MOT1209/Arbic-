"""Class tests: ``صنف``, ``__تهيئة__``, fields, methods and static methods."""

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
    دالة __تهيئة__(الاسم، السن)
        انا.الاسم = الاسم
        انا.السن = السن
    خلاص

    دالة عرّف_نفسك()
        رجّع "أنا " + انا.الاسم
    خلاص

    دالة ساكنة نوع_الكائن()
        رجّع "إنسان"
    خلاص
خلاص
"""


def compile_program(source: str):
    result = compile_source(source, "test.arb")
    assert result.program is not None, render_diagnostics(result.diagnostics, result.source)
    return result.program


def execute(source: str) -> tuple[list[str], DiagnosticBag]:
    program = compile_program(source)
    lines: list[str] = []
    bag = DiagnosticBag()
    Interpreter(diagnostics=bag, write=lines.append).run(program)
    return lines, bag


def run(source: str) -> str:
    lines, _ = execute(source)
    return "\n".join(lines)


def runtime_error(source: str) -> ArabiyaRuntimeError:
    program = compile_program(source)
    interpreter = Interpreter(write=lambda _text: None)
    with pytest.raises(ArabiyaRuntimeError) as excinfo:
        interpreter.run(program)
    return excinfo.value


# ------------------------------------------------------------------- parsing


def test_class_declaration_parses_methods_and_static_flag():
    program = compile_program(PERSON)
    class_node = program.body[0]
    assert isinstance(class_node, ClassDeclaration)
    assert class_node.name == "شخص"
    assert [method.name for method in class_node.methods] == [
        "__تهيئة__",
        "عرّف_نفسك",
        "نوع_الكائن",
    ]
    assert [method.is_static for method in class_node.methods] == [False, False, True]


# --------------------------------------------------------------- execution


def test_initializer_sets_fields():
    source = PERSON + '\nخلي س = شخص("سارة"، 25)\nاطبع س.الاسم\nاطبع س.السن'
    assert run(source) == "سارة\n25"


def test_instance_method_reads_self():
    source = PERSON + '\nخلي س = شخص("سارة"، 25)\nاطبع س.عرّف_نفسك()'
    assert run(source) == "أنا سارة"


def test_static_method_is_called_on_the_class():
    assert run(PERSON + "\nاطبع شخص.نوع_الكائن()") == "إنسان"


def test_field_assignment_updates_the_instance():
    source = PERSON + '\nخلي س = شخص("سارة"، 25)\nس.الاسم = "نور"\nاطبع س.الاسم'
    assert run(source) == "نور"


def test_class_without_initializer_takes_no_arguments():
    source = "صنف فارغ\n    دالة قيمة()\n        رجّع 1\n    خلاص\nخلاص\nاطبع فارغ().قيمة()"
    assert run(source) == "1"


def test_instance_formats_with_its_class_name():
    assert run(PERSON + "\nاطبع شخص(\"سارة\"، 25)") == "<كائن شخص>"


# -------------------------------------------------------------------- errors


def test_missing_member_reports_member_not_found():
    source = PERSON + '\nخلي س = شخص("سارة"، 25)\nاطبع س.مش_موجود'
    error = runtime_error(source)
    assert error.diagnostic.code == ErrorCode.MEMBER_NOT_FOUND


def test_member_access_on_a_number_is_rejected():
    error = runtime_error("خلي س = 5\nاطبع س.اسم")
    assert error.diagnostic.code == ErrorCode.INVALID_MEMBER_ACCESS


def test_field_assignment_on_a_number_is_rejected():
    error = runtime_error("خلي س = 5\nس.اسم = 3")
    assert error.diagnostic.code == ErrorCode.INVALID_MEMBER_ACCESS


def test_constructor_arity_mismatch():
    source = PERSON + '\nشخص("سارة")'
    error = runtime_error(source)
    assert error.diagnostic.code == ErrorCode.ARITY_MISMATCH


def test_constructor_with_arguments_and_no_initializer_is_an_arity_error():
    error = runtime_error("صنف فارغ\nخلاص\nفارغ(1)")
    assert error.diagnostic.code == ErrorCode.ARITY_MISMATCH


def test_instance_method_cannot_be_read_from_the_class():
    error = runtime_error(PERSON + "\nاطبع شخص.عرّف_نفسك")
    assert error.diagnostic.code == ErrorCode.INVALID_MEMBER_ACCESS


# ----------------------------------------------------------------- tooling


def test_vm_reports_classes_as_unsupported_so_it_can_fall_back():
    assert unsupported_reason(compile_program(PERSON)) is not None


def test_type_checker_accepts_class_code_and_the_class_type():
    source = PERSON + '\nخلي س : صنف = شخص("سارة"، 25)\nاطبع س'
    assert check_types(compile_program(source)).errors == []
