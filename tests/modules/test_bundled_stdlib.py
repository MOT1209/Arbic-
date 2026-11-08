"""The bundled standard library: importable modules that ship with the interpreter."""

from __future__ import annotations

from pathlib import Path

from al_arabiya.cli.main import main
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.runtime.modules import stdlib_names, stdlib_path


def test_every_bundled_module_compiles() -> None:
    names = stdlib_names()
    assert {"نصوص", "قوائم", "رياضيات"} <= set(names)
    for name in names:
        path = stdlib_path(name)
        assert path is not None and Path(path).is_file()
        result = compile_source(Path(path).read_text(encoding="utf-8"), path)
        assert result.program is not None, f"module {name} does not compile"


def test_stdlib_unknown_name_is_not_a_path() -> None:
    assert stdlib_path("../../etc/passwd") is None
    assert stdlib_path("مفقود") is None


def test_text_module(tmp_path: Path, capsys) -> None:
    program = tmp_path / "م.arb"
    program.write_text(
        'استورد "نصوص"\nاطبع مكرر("ها"، 3)\nاطبع مقتبس("س")\n',
        encoding="utf-8",
    )

    assert main(["run", str(program)]) == 0
    assert capsys.readouterr().out.splitlines() == ["هاهاها", '"س"']


def test_lists_module(tmp_path: Path, capsys) -> None:
    program = tmp_path / "م.arb"
    program.write_text(
        'استورد "قوائم"\nاطبع مجموع([1، 2، 3، 4])\nاطبع الأكبر([9، 2، 7])\n',
        encoding="utf-8",
    )

    assert main(["run", str(program)]) == 0
    assert capsys.readouterr().out.splitlines() == ["10", "9"]


def test_math_module(tmp_path: Path, capsys) -> None:
    program = tmp_path / "م.arb"
    program.write_text(
        'استورد "رياضيات"\n'
        "اطبع قوة(2، 10)\n"
        'لو زوجي(4)\n    اطبع "زوجي"\nخلاص\n'
        'لو زوجي(5)\n    اطبع "غلط"\nغير كده\n    اطبع "فردي"\nخلاص\n',
        encoding="utf-8",
    )

    assert main(["run", str(program)]) == 0
    assert capsys.readouterr().out.splitlines() == ["1024", "زوجي", "فردي"]


def test_a_project_file_shadows_a_bundled_module(tmp_path: Path, capsys) -> None:
    (tmp_path / "نصوص.arb").write_text(
        'دالة رسالة ()\n    رجّع "محلي"\nخلاص\n', encoding="utf-8"
    )
    program = tmp_path / "م.arb"
    program.write_text('استورد "نصوص"\nاطبع رسالة()\n', encoding="utf-8")

    assert main(["run", str(program)]) == 0
    assert capsys.readouterr().out.strip() == "محلي"
