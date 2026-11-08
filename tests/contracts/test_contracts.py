"""Phase 1 contracts: error codes and CLI exit codes must not drift.

Two user-facing promises are pinned here:

* every ``ErrorCode`` member appears in the reference table of
  ``docs/language/syntax.md`` and every documented code still exists — so a
  new code cannot ship undocumented, and the docs cannot invent a code;
* the ``arabic`` command exits with ``0`` on success, ``1`` on a language
  error and ``2`` on a usage/file error, exactly as the README and
  ``arabic help`` state.

The reference table is the only place codes are listed for users, so it has
to grow with the enum: E1 lexical, E2 syntax, W3 warnings, E4 runtime, E5
static type checking.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from al_arabiya.cli.main import main
from al_arabiya.compiler.diagnostics.errors import ErrorCode

ROOT = Path(__file__).resolve().parents[2]
SYNTAX_DOC = ROOT / "docs" / "language" / "syntax.md"
SOURCE_DIR = ROOT / "al_arabiya"

_DOCUMENTED_CODE = re.compile(r"^\|\s*`([EW]\d{4})`\s*\|", re.MULTILINE)
_CODE_SHAPE = re.compile(r"[EW]\d{4}")


def documented_codes() -> set[str]:
    return set(_DOCUMENTED_CODE.findall(SYNTAX_DOC.read_text(encoding="utf-8")))


# ------------------------------------------------------------- error codes


def test_documented_codes_match_the_enum() -> None:
    assert documented_codes() == {code.value for code in ErrorCode}


def test_error_codes_are_unique() -> None:
    values = [code.value for code in ErrorCode]
    assert len(values) == len(set(values))


def test_error_codes_keep_their_layer_ranges() -> None:
    for code in ErrorCode:
        assert _CODE_SHAPE.fullmatch(code.value), code
        if code.value.startswith("E"):
            assert code.value[1] in "1245", f"{code.name} is outside E1/E2/E4/E5"
        else:
            assert code.value[1] == "3", f"{code.name} is outside W3"


def test_every_code_is_used_by_the_implementation() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in SOURCE_DIR.rglob("*.py")
        if path.name != "errors.py"
    )
    unused = [
        member.name
        for member in ErrorCode
        if f"ErrorCode.{member.name}" not in sources
    ]
    assert unused == [], f"declared but never raised: {unused}"


# --------------------------------------------------------------- CLI codes


def _program(tmp_path: Path, text: str) -> str:
    path = tmp_path / "main.arb"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_success_exits_zero(tmp_path: Path) -> None:
    assert main(["run", _program(tmp_path, 'اطبع "أهلا"\n')]) == 0


def test_compile_error_exits_one(tmp_path: Path) -> None:
    assert main(["run", _program(tmp_path, "لو صح\n    اطبع 1\n")]) == 1


def test_runtime_error_exits_one(tmp_path: Path) -> None:
    assert main(["run", _program(tmp_path, "اطبع 1 / 0\n")]) == 1


def test_missing_file_exits_two(tmp_path: Path) -> None:
    assert main(["run", str(tmp_path / "لا_يوجد.arb")]) == 2


@pytest.mark.parametrize("argv", [["foo"], ["run"]])
def test_usage_errors_exit_two(argv: list[str]) -> None:
    assert main(argv) == 2


def test_help_documents_exactly_the_supported_exit_codes(capsys) -> None:
    assert main(["help"]) == 0
    out = capsys.readouterr().out
    documented = out.split("أكواد الخروج:")[1]
    for code in ("0", "1", "2"):
        assert code in documented
    assert "3" not in documented
