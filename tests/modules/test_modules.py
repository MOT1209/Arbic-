"""Tests for Phase 5: modules and `استورد` (import)."""

from __future__ import annotations

from pathlib import Path

import pytest

from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag, render_diagnostics
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.runtime.interpreter.interpreter import Interpreter

MATH_MODULE = (
    "دالة جمع (أ، ب)\n"
    "    رجّع أ زائد ب\n"
    "خلاص\n"
    "دالة ضرب (أ، ب)\n"
    "    رجّع أ في ب\n"
    "خلاص\n"
    "خلي باي = 3.14\n"
)


def run_file(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    result = compile_source(source, str(path))
    assert result.program is not None, render_diagnostics(result.diagnostics, result.source)
    lines: list[str] = []
    Interpreter(
        diagnostics=DiagnosticBag(),
        write=lines.append,
        base_dir=str(path.parent),
    ).run(result.program)
    return "\n".join(lines)


def error_from_file(path: Path) -> ArabiyaRuntimeError:
    source = path.read_text(encoding="utf-8")
    result = compile_source(source, str(path))
    assert result.program is not None
    with pytest.raises(ArabiyaRuntimeError) as excinfo:
        Interpreter(write=lambda _t: None, base_dir=str(path.parent)).run(result.program)
    return excinfo.value


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_plain_import_exposes_names(tmp_path: Path):
    write(tmp_path / "رياضيات.arb", MATH_MODULE)
    main = write(tmp_path / "رئيسي.arb", 'استورد "رياضيات"\nاطبع جمع(2، 3)\nاطبع باي')
    assert run_file(main) == "5\n3.14"


def test_import_without_extension(tmp_path: Path):
    write(tmp_path / "رياضيات.arb", MATH_MODULE)
    main = write(tmp_path / "m.arb", 'استورد "رياضيات"\nاطبع ضرب(3، 4)')
    assert run_file(main) == "12"


def test_alias_import_is_a_namespace(tmp_path: Path):
    write(tmp_path / "رياضيات.arb", MATH_MODULE)
    main = write(tmp_path / "m.arb", 'استورد "رياضيات" باسم ر\nاطبع ر["جمع"](4، 5)')
    assert run_file(main) == "9"


def test_selective_import(tmp_path: Path):
    write(tmp_path / "رياضيات.arb", MATH_MODULE)
    main = write(tmp_path / "m.arb", 'من "رياضيات" استورد جمع\nاطبع جمع(1، 1)')
    assert run_file(main) == "2"


def test_selective_import_unknown_name(tmp_path: Path):
    write(tmp_path / "رياضيات.arb", MATH_MODULE)
    main = write(tmp_path / "m.arb", 'من "رياضيات" استورد مش_موجود')
    assert error_from_file(main).diagnostic.code == ErrorCode.IMPORT_ERROR


def test_missing_module(tmp_path: Path):
    main = write(tmp_path / "m.arb", 'استورد "مفقود"')
    assert error_from_file(main).diagnostic.code == ErrorCode.MODULE_NOT_FOUND


def test_import_cycle_is_detected(tmp_path: Path):
    write(tmp_path / "x.arb", 'استورد "y"')
    write(tmp_path / "y.arb", 'استورد "x"')
    assert error_from_file(tmp_path / "x.arb").diagnostic.code == ErrorCode.IMPORT_ERROR


def test_error_in_imported_file(tmp_path: Path):
    write(tmp_path / "سيء.arb", "خلي = ")
    main = write(tmp_path / "m.arb", 'استورد "سيء"')
    assert error_from_file(main).diagnostic.code == ErrorCode.IMPORT_ERROR


def test_module_is_executed_once(tmp_path: Path):
    write(tmp_path / "جانبي.arb", 'اطبع "تحميل"\nخلي ق = 1')
    main = write(
        tmp_path / "m.arb",
        'استورد "جانبي"\nاستورد "جانبي"\nاطبع ق',
    )
    # Side-effect print happens once (cached), then the value is visible.
    assert run_file(main) == "تحميل\n1"
