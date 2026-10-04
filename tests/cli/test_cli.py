"""CLI and REPL tests (via main() with injected argv)."""

from __future__ import annotations

import pytest

from al_arabiya.cli.main import main
from al_arabiya.cli.repl import run_repl

GOOD_PROGRAM = 'اطبع "أهلا بالعالم"\n'


def write_program(tmp_path, text: str, name: str = "main.arb"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_version(capsys):
    assert main(["version"]) == 0
    assert "0.1.0" in capsys.readouterr().out


def test_help(capsys):
    assert main(["help"]) == 0
    assert "arabic run" in capsys.readouterr().out


def test_help_flag(capsys):
    assert main(["--help"]) == 0


def test_unknown_command_returns_2(capsys):
    assert main(["foo"]) == 2
    assert "أمر مش معروف" in capsys.readouterr().err


def test_missing_file_returns_2(tmp_path, capsys):
    assert main(["run", str(tmp_path / "لايوجد.arb")]) == 2
    assert "مش لاقي الملف" in capsys.readouterr().err


def test_run_ok(tmp_path, capsys):
    path = write_program(tmp_path, GOOD_PROGRAM)
    assert main(["run", path]) == 0
    assert "أهلا بالعالم" in capsys.readouterr().out


def test_run_without_subcommand(tmp_path, capsys):
    path = write_program(tmp_path, GOOD_PROGRAM)
    assert main([path]) == 0
    assert "أهلا بالعالم" in capsys.readouterr().out


def test_run_compile_error(tmp_path, capsys):
    path = write_program(tmp_path, "لو صح\n    اطبع 1\n")
    assert main(["run", path]) == 1
    captured = capsys.readouterr()
    assert "E2004" in captured.err


def test_run_runtime_error(tmp_path, capsys):
    path = write_program(tmp_path, "اطبع 1 / 0\n")
    assert main(["run", path]) == 1
    assert "E4002" in capsys.readouterr().err


def test_check_ok(tmp_path, capsys):
    path = write_program(tmp_path, GOOD_PROGRAM)
    assert main(["check", path]) == 0
    assert "سليم" in capsys.readouterr().err


def test_check_error(tmp_path, capsys):
    path = write_program(tmp_path, "خلي = 5\n")
    assert main(["check", path]) == 1
    assert "E2005" in capsys.readouterr().err


def test_check_passes_well_typed_program(tmp_path, capsys):
    path = write_program(tmp_path, "خلي س : رقم = 5\nاطبع س\n")
    assert main(["check", path]) == 0
    assert "سليم" in capsys.readouterr().err


def test_check_reports_type_error(tmp_path, capsys):
    path = write_program(tmp_path, 'خلي س : رقم = "نص"\n')
    assert main(["check", path]) == 1
    assert "E5001" in capsys.readouterr().err


def test_run_ignores_type_annotations(tmp_path, capsys):
    path = write_program(tmp_path, "خلي س : رقم = 5\nاطبع س\n")
    assert main(["run", path]) == 0
    assert "5" in capsys.readouterr().out


def test_check_does_not_execute(tmp_path, capsys):
    path = write_program(tmp_path, GOOD_PROGRAM)
    main(["check", path])
    assert "أهلا بالعالم" not in capsys.readouterr().out


def test_run_without_file_argument(tmp_path, capsys):
    assert main(["run"]) == 2
    assert "محتاج اسم ملف" in capsys.readouterr().err


def test_run_with_vm_backend(tmp_path, capsys):
    path = write_program(tmp_path, "دالة م (س)\n    رجّع س في س\nخلاص\nاطبع م(8)\n")
    assert main(["run", "--vm", path]) == 0
    assert "64" in capsys.readouterr().out


def test_run_vm_falls_back_on_unsupported(tmp_path, capsys):
    # nested functions (closures over locals) still run on the interpreter
    program = (
        "دالة خارجي ()\n"
        "    دالة داخلي ()\n"
        "        رجّع 1\n"
        "    خلاص\n"
        "    رجّع داخلي()\n"
        "خلاص\n"
        'اطبع خارجي()\n'
    )
    path = write_program(tmp_path, program)
    assert main(["run", "--vm", path]) == 0
    captured = capsys.readouterr()
    assert "1" in captured.out
    assert "VM" in captured.err  # a fallback note was printed


def test_run_vm_executes_lists_and_exceptions(tmp_path, capsys):
    program = (
        "خلي ق = [1، 2، 3]\n"
        "حاول\n"
        "    اطبع ق[1]\n"
        "    ارم \"توقف\"\n"
        "امسك e\n"
        "    اطبع e\n"
        "خلاص\n"
    )
    path = write_program(tmp_path, program)
    assert main(["run", "--vm", path]) == 0
    captured = capsys.readouterr()
    assert "2" in captured.out
    assert "توقف" in captured.out
    assert "VM" not in captured.err  # ran on the VM, no fallback


def test_run_vm_runtime_error(tmp_path, capsys):
    path = write_program(tmp_path, "اطبع 1 على 0\n")
    assert main(["run", "--vm", path]) == 1
    assert "E4002" in capsys.readouterr().err


def test_bench_reports_speedup(tmp_path, capsys):
    path = write_program(tmp_path, "خلي ع = 0\nطالما ع أصغر من 100\n    ع = ع زائد 1\nخلاص\n")
    assert main(["bench", path]) == 0
    out = capsys.readouterr().out
    assert "speedup" in out or "التسريع" in out


def test_bench_unsupported_returns_2(tmp_path, capsys):
    # import isn't covered by the VM, so the comparison isn't available
    path = write_program(tmp_path, 'استورد "لا_يوجد"\n')
    assert main(["bench", path]) == 2


# ---------------------------------------------------------------------- REPL


def make_input(lines: list[str]):
    state = {"index": 0}

    def _input(prompt: str) -> str:
        if state["index"] >= len(lines):
            raise EOFError
        line = lines[state["index"]]
        state["index"] += 1
        return line

    return _input


def test_repl_basic_session():
    out: list[str] = []
    err: list[str] = []
    code = run_repl(
        input_fn=make_input(['اطبع "مرحبا"', "خلي س = 10", "اطبع س", "خروج"]),
        out=out.append,
        err=err.append,
    )
    assert code == 0
    text = "\n".join(out)
    assert "العربية REPL" in text
    assert "مرحبا" in text
    assert "10" in text
    assert err == []


def test_repl_state_persists_between_lines():
    out: list[str] = []
    run_repl(
        input_fn=make_input(["خلي س = 5", "س = 7", "اطبع س", "exit"]),
        out=out.append,
        err=lambda _text: None,
    )
    assert "7" in "\n".join(out)


def test_repl_multiline_block():
    out: list[str] = []
    code = run_repl(
        input_fn=make_input(["لو صح", 'اطبع "داخل"', "خلاص", "خروج"]),
        out=out.append,
        err=lambda _text: None,
    )
    assert code == 0
    assert "داخل" in "\n".join(out)


def test_repl_reports_errors_and_continues():
    out: list[str] = []
    err: list[str] = []
    code = run_repl(
        input_fn=make_input(["خلي = 5", 'اطبع "كمان"', "خروج"]),
        out=out.append,
        err=err.append,
    )
    assert code == 0
    assert "E2005" in "\n".join(err)
    assert "كمان" in "\n".join(out)


def test_repl_eof_exits():
    out: list[str] = []
    code = run_repl(
        input_fn=make_input([]), out=out.append, err=lambda _text: None
    )
    assert code == 0
    assert "مع السلامة" in "\n".join(out)


def test_repl_runtime_error_does_not_crash():
    out: list[str] = []
    err: list[str] = []
    code = run_repl(
        input_fn=make_input(["اطبع 1 / 0", 'اطبع "عايش"', "خروج"]),
        out=out.append,
        err=err.append,
    )
    assert code == 0
    assert "E4002" in "\n".join(err)
    assert "عايش" in "\n".join(out)


def test_main_without_args_starts_repl(monkeypatch):
    called = []
    monkeypatch.setattr("al_arabiya.cli.main.run_repl", lambda: called.append(1) or 0)
    assert main([]) == 0
    assert called == [1]


@pytest.mark.parametrize("exit_word", ["خروج", "exit", "quit"])
def test_repl_exit_words(exit_word):
    out: list[str] = []
    code = run_repl(
        input_fn=make_input([exit_word]), out=out.append, err=lambda _text: None
    )
    assert code == 0
