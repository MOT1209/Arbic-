"""Module imports (استورد) running on the bytecode VM, checked against the interpreter."""

from __future__ import annotations

from pathlib import Path

import pytest

from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.runtime.interpreter.interpreter import Interpreter
from al_arabiya.vm.compiler import compile_program, unsupported_reason
from al_arabiya.vm.vm import VM

MATH_MODULE = (
    "دالة جمع (أ، ب)\n"
    "    رجّع أ زائد ب\n"
    "خلاص\n"
    "دالة ضرب (أ، ب)\n"
    "    رجّع أ في ب\n"
    "خلاص\n"
    "خلي باي = 3.14\n"
)


def _program(source: str, name: str):
    result = compile_source(source, name)
    assert result.program is not None, [(d.code, d.message) for d in result.diagnostics]
    return result.program


def run_tree(source: str, base: Path) -> str:
    out: list[str] = []
    Interpreter(write=out.append, base_dir=str(base)).run(_program(source, "main.arb"))
    return "\n".join(out)


def run_vm(source: str, base: Path) -> str:
    program = _program(source, "main.arb")
    assert unsupported_reason(program) is None, "import should be VM-supported"
    out: list[str] = []
    VM(write=out.append, base_dir=str(base)).run(compile_program(program))
    return "\n".join(out)


def write_math(tmp_path: Path) -> Path:
    (tmp_path / "رياضيات.arb").write_text(MATH_MODULE, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    "source",
    [
        'استورد "رياضيات"\nاطبع جمع(2، 3)\nاطبع باي',
        'استورد "رياضيات" باسم ر\nاطبع ر["ضرب"](4، 5)',
        'من "رياضيات" استورد جمع\nاطبع جمع(10، 20)',
        'استورد "رياضيات"\nخلي ق = [جمع(1، 1)، ضرب(2، 3)]\nاطبع ق',
        'حاول\n    استورد "مفقود"\nامسك e\n    اطبع e["الكود"]\nخلاص',
    ],
)
def test_vm_import_matches_interpreter(source: str, tmp_path: Path):
    base = write_math(tmp_path)
    assert run_vm(source, base) == run_tree(source, base)


def test_vm_imported_function_is_callable(tmp_path: Path):
    base = write_math(tmp_path)
    assert run_vm('استورد "رياضيات"\nاطبع جمع(40، 2)', base) == "42"


def test_vm_missing_module_errors(tmp_path: Path):
    program = _program('استورد "مفقود"', "main.arb")
    with pytest.raises(ArabiyaRuntimeError) as excinfo:
        VM(write=lambda _t: None, base_dir=str(tmp_path)).run(compile_program(program))
    assert excinfo.value.diagnostic.code == ErrorCode.MODULE_NOT_FOUND


def test_vm_selective_import_unknown_name(tmp_path: Path):
    base = write_math(tmp_path)
    program = _program('من "رياضيات" استورد مش_موجود', "main.arb")
    with pytest.raises(ArabiyaRuntimeError) as excinfo:
        VM(write=lambda _t: None, base_dir=str(base)).run(compile_program(program))
    assert excinfo.value.diagnostic.code == ErrorCode.IMPORT_ERROR


def test_vm_import_cycle_is_detected(tmp_path: Path):
    (tmp_path / "x.arb").write_text('استورد "y"', encoding="utf-8")
    (tmp_path / "y.arb").write_text('استورد "x"', encoding="utf-8")
    program = _program('استورد "x"', "main.arb")
    with pytest.raises(ArabiyaRuntimeError) as excinfo:
        VM(write=lambda _t: None, base_dir=str(tmp_path)).run(compile_program(program))
    assert excinfo.value.diagnostic.code == ErrorCode.IMPORT_ERROR
