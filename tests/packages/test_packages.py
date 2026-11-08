"""Tests for the offline package manager and package-aware imports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from al_arabiya.compiler.frontend import compile_source
from al_arabiya.packages import manager
from al_arabiya.packages.manager import PackageError, Registry, Version
from al_arabiya.runtime.interpreter.interpreter import Interpreter
from al_arabiya.vm.compiler import compile_program
from al_arabiya.vm.vm import VM

# ------------------------------------------------------------------ helpers


def add_package(
    registry_root: Path,
    name: str,
    version: str,
    *,
    source: str = "",
    deps: dict[str, str] | None = None,
) -> None:
    pkg = registry_root / name / version
    pkg.mkdir(parents=True)
    (pkg / f"{name}.arb").write_text(source, encoding="utf-8")
    if deps is not None:
        manifest = {"الاسم": name, "الإصدار": version, "الاعتماديات": deps}
        (pkg / "حزمة.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )


def write_manifest(project: Path, deps: dict[str, str]) -> None:
    manifest = {"الاسم": "تطبيقي", "الإصدار": "1.0.0", "الاعتماديات": deps}
    (project / manager.MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )


# -------------------------------------------------------------------- semver


def test_version_parse_and_order():
    assert Version.parse("1.2.3") == Version(1, 2, 3)
    assert Version.parse("1.0.0") < Version.parse("1.0.1") < Version.parse("2.0.0")


def test_version_parse_rejects_bad():
    with pytest.raises(PackageError):
        Version.parse("1.2")


@pytest.mark.parametrize(
    "version,constraint,ok",
    [
        ("1.2.3", "1.2.3", True),
        ("1.2.3", "1.2.4", False),
        ("1.4.0", "^1.2.0", True),
        ("2.0.0", "^1.2.0", False),
        ("1.0.0", "^1.2.0", False),  # caret requires >= base
        ("9.9.9", "*", True),
        ("9.9.9", "أي", True),
    ],
)
def test_satisfies(version: str, constraint: str, ok: bool):
    assert manager.satisfies(Version.parse(version), constraint) is ok


# ------------------------------------------------------------------ resolve


def test_resolve_picks_highest_satisfying(tmp_path: Path):
    reg = tmp_path / "سجل"
    add_package(reg, "أ", "1.0.0")
    add_package(reg, "أ", "1.3.0")
    add_package(reg, "أ", "2.0.0")
    resolved = manager.resolve(
        manager.Manifest("app", Version(1, 0, 0), {"أ": "^1.0.0"}), Registry(reg)
    )
    assert resolved == {"أ": Version(1, 3, 0)}


def test_resolve_transitive(tmp_path: Path):
    reg = tmp_path / "سجل"
    add_package(reg, "أ", "1.0.0", deps={"ب": "^1.0.0"})
    add_package(reg, "ب", "1.1.0")
    resolved = manager.resolve(
        manager.Manifest("app", Version(1, 0, 0), {"أ": "^1.0.0"}), Registry(reg)
    )
    assert resolved == {"أ": Version(1, 0, 0), "ب": Version(1, 1, 0)}


def test_resolve_unsatisfiable(tmp_path: Path):
    reg = tmp_path / "سجل"
    add_package(reg, "أ", "1.0.0")
    with pytest.raises(PackageError):
        manager.resolve(
            manager.Manifest("app", Version(1, 0, 0), {"أ": "^2.0.0"}), Registry(reg)
        )


def test_resolve_conflict(tmp_path: Path):
    reg = tmp_path / "سجل"
    # root wants ب ^2, but أ needs ب ^1 → conflict
    add_package(reg, "أ", "1.0.0", deps={"ب": "^1.0.0"})
    add_package(reg, "ب", "1.0.0")
    add_package(reg, "ب", "2.0.0")
    with pytest.raises(PackageError):
        manager.resolve(
            manager.Manifest("app", Version(1, 0, 0), {"ب": "^2.0.0", "أ": "^1.0.0"}),
            Registry(reg),
        )


def test_resolve_cycle(tmp_path: Path):
    reg = tmp_path / "سجل"
    add_package(reg, "أ", "1.0.0", deps={"ب": "^1.0.0"})
    add_package(reg, "ب", "1.0.0", deps={"أ": "^1.0.0"})
    with pytest.raises(PackageError):
        manager.resolve(
            manager.Manifest("app", Version(1, 0, 0), {"أ": "^1.0.0"}), Registry(reg)
        )


# ------------------------------------------------------------------ install


def test_install_vendors_and_locks(tmp_path: Path):
    reg = tmp_path / "سجل"
    add_package(reg, "رياضيات", "1.0.0", source="خلي باي = 3\n")
    project = tmp_path / "مشروع"
    project.mkdir()
    write_manifest(project, {"رياضيات": "^1.0.0"})

    resolved = manager.install(project, Registry(reg))
    assert resolved == {"رياضيات": Version(1, 0, 0)}
    assert (project / "حزم" / "رياضيات" / "رياضيات.arb").is_file()
    assert manager.read_lockfile(project) == {"رياضيات": "1.0.0"}


# ------------------------------------------------- end-to-end import of a dep


def _run_tree(source: str, base: Path) -> str:
    out: list[str] = []
    Interpreter(write=out.append, base_dir=str(base)).run(compile_source(source, "m").program)
    return "\n".join(out)


def _run_vm(source: str, base: Path) -> str:
    out: list[str] = []
    program = compile_source(source, "m").program
    assert program is not None
    VM(write=out.append, base_dir=str(base)).run(compile_program(program))
    return "\n".join(out)


def test_installed_package_is_importable(tmp_path: Path):
    reg = tmp_path / "سجل"
    add_package(
        reg,
        "رياضيات",
        "1.0.0",
        source="دالة جمع (أ، ب)\n    رجّع أ زائد ب\nخلاص\n",
    )
    project = tmp_path / "مشروع"
    project.mkdir()
    write_manifest(project, {"رياضيات": "^1.0.0"})
    manager.install(project, Registry(reg))

    source = 'استورد "رياضيات"\nاطبع جمع(2، 3)'
    assert _run_tree(source, project) == "5"
    assert _run_vm(source, project) == "5"


def test_transitive_dependency_import(tmp_path: Path):
    reg = tmp_path / "سجل"
    add_package(
        reg,
        "رياضيات",
        "1.0.0",
        source='استورد "أدوات"\nدالة جمع (أ، ب)\n    رجّع أ زائد ب\nخلاص\n',
        deps={"أدوات": "^1.0.0"},
    )
    add_package(reg, "أدوات", "1.2.0", source="خلي اسم = \"أدوات\"\n")
    project = tmp_path / "مشروع"
    project.mkdir()
    write_manifest(project, {"رياضيات": "^1.0.0"})
    manager.install(project, Registry(reg))

    source = 'استورد "رياضيات"\nاطبع جمع(4، 5)\nاطبع اسم'
    assert _run_tree(source, project) == "9\nأدوات"
    assert _run_vm(source, project) == "9\nأدوات"


# --------------------------------------------------------------------- CLI


def test_cli_install_and_list(tmp_path: Path, capsys):
    from al_arabiya.cli.main import main

    reg = tmp_path / "سجل"
    add_package(reg, "رياضيات", "1.0.0", source="خلي باي = 3\n")
    project = tmp_path / "مشروع"
    project.mkdir()
    write_manifest(project, {"رياضيات": "^1.0.0"})

    code = main(["packages", "install", str(project), "--registry", str(reg)])
    assert code == 0
    assert "رياضيات" in capsys.readouterr().out

    code = main(["packages", "list", str(project)])
    assert code == 0
    assert "رياضيات 1.0.0" in capsys.readouterr().out


def test_cli_install_needs_registry(tmp_path: Path, capsys, monkeypatch):
    from al_arabiya.cli.main import main

    monkeypatch.delenv("ARABIC_REGISTRY", raising=False)
    project = tmp_path / "مشروع"
    project.mkdir()
    write_manifest(project, {})
    assert main(["packages", "install", str(project)]) == 2
