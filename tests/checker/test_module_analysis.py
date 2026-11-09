"""Tests for module-aware static analysis (imports resolved and type-checked)."""

from __future__ import annotations

from pathlib import Path

from al_arabiya.compiler.checker import check_types
from al_arabiya.compiler.diagnostics.errors import ErrorCode
from al_arabiya.compiler.frontend import compile_source

MODULE = (
    "دالة ضعف (س : رقم) : رقم\n"
    "    رجّع س في 2\n"
    "خلاص\n"
    'خلي ثابت : نص = "وحدة"\n'
)


def write_module(directory: Path, name: str, source: str) -> Path:
    path = directory / f"{name}.arb"
    path.write_text(source, encoding="utf-8")
    return path


def check_file(path: Path) -> list[str]:
    result = compile_source(path.read_text(encoding="utf-8"), str(path))
    assert result.program is not None, [
        (d.code, d.message) for d in result.diagnostics
    ]
    bag = check_types(
        result.program, base_dir=str(path.parent), filename=str(path)
    )
    return [d.code for d in bag if d.is_error]


def test_imported_function_parameter_types_are_checked(tmp_path: Path):
    write_module(tmp_path, "رياضيات", MODULE)
    main = write_module(
        tmp_path, "رئيسي", 'من "رياضيات" استورد ضعف\nاطبع ضعف("نص")'
    )
    assert ErrorCode.TYPE_MISMATCH in check_file(main)


def test_imported_function_arity_is_checked(tmp_path: Path):
    write_module(tmp_path, "رياضيات", MODULE)
    main = write_module(
        tmp_path, "رئيسي", 'من "رياضيات" استورد ضعف\nاطبع ضعف(1، 2)'
    )
    assert ErrorCode.ARGUMENT_COUNT in check_file(main)


def test_import_all_binds_exported_return_types(tmp_path: Path):
    write_module(tmp_path, "رياضيات", MODULE)
    main = write_module(tmp_path, "رئيسي", 'استورد "رياضيات"\nخلي س : نص = ضعف(2)')
    assert ErrorCode.TYPE_MISMATCH in check_file(main)


def test_imported_constant_keeps_its_type(tmp_path: Path):
    write_module(tmp_path, "رياضيات", MODULE)
    main = write_module(
        tmp_path, "رئيسي", 'من "رياضيات" استورد ثابت\nخلي س : رقم = ثابت'
    )
    assert ErrorCode.TYPE_MISMATCH in check_file(main)


def test_alias_namespace_calls_are_typed(tmp_path: Path):
    write_module(tmp_path, "رياضيات", MODULE)
    main = write_module(
        tmp_path,
        "رئيسي",
        'استورد "رياضيات" باسم ر\nخلي س : نص = ر["ضعف"](2)',
    )
    assert ErrorCode.TYPE_MISMATCH in check_file(main)


def test_unknown_name_through_a_namespace_is_reported(tmp_path: Path):
    write_module(tmp_path, "رياضيات", MODULE)
    main = write_module(
        tmp_path, "رئيسي", 'استورد "رياضيات" باسم ر\nاطبع ر["مش_موجود"]'
    )
    assert ErrorCode.UNKNOWN_IMPORTED_NAME in check_file(main)


def test_unknown_name_in_from_import_is_reported(tmp_path: Path):
    write_module(tmp_path, "رياضيات", MODULE)
    main = write_module(
        tmp_path, "رئيسي", 'من "رياضيات" استورد مش_موجود'
    )
    assert ErrorCode.UNKNOWN_IMPORTED_NAME in check_file(main)


def test_missing_module_is_reported(tmp_path: Path):
    main = write_module(tmp_path, "رئيسي", 'استورد "مش_موجود"')
    assert ErrorCode.MODULE_UNRESOLVED in check_file(main)


def test_module_with_syntax_errors_is_reported(tmp_path: Path):
    write_module(tmp_path, "مكسور", "خلي\n")
    main = write_module(tmp_path, "رئيسي", 'استورد "مكسور"')
    assert ErrorCode.MODULE_UNRESOLVED in check_file(main)


def test_module_with_type_errors_is_reported(tmp_path: Path):
    write_module(tmp_path, "غلط", 'خلي س : رقم = "نص"\n')
    main = write_module(tmp_path, "رئيسي", 'استورد "غلط"')
    assert ErrorCode.MODULE_UNRESOLVED in check_file(main)


def test_circular_imports_are_reported(tmp_path: Path):
    write_module(tmp_path, "أ", 'استورد "ب"\nاطبع 1')
    write_module(tmp_path, "ب", 'استورد "أ"\nاطبع 2')
    assert ErrorCode.MODULE_UNRESOLVED in check_file(tmp_path / "أ.arb")


def test_import_path_traversal_is_refused(tmp_path: Path):
    main = write_module(tmp_path, "رئيسي", 'استورد "../بره"')
    assert ErrorCode.IMPORT_ERROR in check_file(main)


def test_without_a_base_dir_imports_stay_dynamic():
    result = compile_source('استورد "مش_موجود"\nاطبع ضعف(1)', "test.arb")
    assert result.program is not None
    assert [d for d in check_types(result.program) if d.is_error] == []
