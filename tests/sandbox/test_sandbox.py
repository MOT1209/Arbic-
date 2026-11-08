"""Tests for the isolated worker (real subprocesses, no mocks)."""

from __future__ import annotations

import sys

import pytest

from al_arabiya.cli.main import main
from al_arabiya.sandbox import SandboxLimits, run_sandboxed


def write(tmp_path, text: str):
    path = tmp_path / "main.arb"
    path.write_text(text, encoding="utf-8")
    return path


def test_matches_a_local_run(tmp_path) -> None:
    path = write(
        tmp_path,
        "خلي س = 0\nكرر 10 مرات\n    س = س زائد 1\nخلاص\nاطبع س\n",
    )
    result = run_sandboxed(path, SandboxLimits(timeout=10.0))
    assert result.exit_code == 0
    assert result.stdout.strip() == "10"
    assert not result.timed_out


def test_wall_clock_timeout_kills_a_runaway_program(tmp_path) -> None:
    path = write(
        tmp_path,
        "خلي س = 0\n"
        "كرر 2000 مرات\n"
        "    كرر 2000 مرات\n"
        "        س = س زائد 1\n"
        "    خلاص\n"
        "خلاص\n"
        "اطبع س\n",
    )
    result = run_sandboxed(path, SandboxLimits(timeout=0.5))
    assert result.timed_out
    assert result.exit_code == 1
    assert "الوقت" in result.stderr


def test_output_is_capped(tmp_path) -> None:
    path = write(
        tmp_path,
        'كرر 20000 مرات\n    اطبع "abcdefghijklmnopqrst"\nخلاص\n',
    )
    result = run_sandboxed(path, SandboxLimits(timeout=20.0, output_bytes=4096))
    assert result.limit == "output"
    assert len(result.stdout) <= 4096 + 200
    assert "المخرجات" in result.stderr


def test_stdin_is_closed(tmp_path) -> None:
    path = write(tmp_path, "اقرأ()\n")
    result = run_sandboxed(path, SandboxLimits(timeout=10.0))
    assert result.exit_code == 1
    assert "إدخال" in result.stderr


def test_missing_program_exits_two(tmp_path) -> None:
    result = run_sandboxed(tmp_path / "لا_يوجد.arb")
    assert result.exit_code == 2
    assert "مش لاقي" in result.stderr


def test_cli_run_uses_the_sandbox(tmp_path, capsys) -> None:
    path = write(tmp_path, 'اطبع "من العازل"\n')
    assert main(["run", "--sandbox", str(path)]) == 0
    assert "من العازل" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        ["run", "--timeout", "abc", "main.arb"],
        ["run", "--timeout", "0", "main.arb"],
        ["run", "--memory", "1", "main.arb"],
        ["run", "--nope", "main.arb"],
    ],
)
def test_bad_run_options_exit_two(argv: list[str], capsys) -> None:
    assert main(argv) == 2
    assert "❌" in capsys.readouterr().err


@pytest.mark.skipif(sys.platform == "win32", reason="RLIMIT_AS is POSIX-only")
def test_memory_limit_stops_runaway_allocation(tmp_path) -> None:
    path = write(
        tmp_path,
        'خلي ق = []\nطالما صح\n    اضف(ق، "متسلسلة طويلة بلا داعي")\nخلاص\n',
    )
    result = run_sandboxed(
        path, SandboxLimits(timeout=30.0, memory_bytes=128 * 1024 * 1024)
    )
    assert result.exit_code != 0
    assert result.stdout == ""
