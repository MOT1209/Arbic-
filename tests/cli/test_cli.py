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
    # a رجّع that crosses a أخيرا still runs on the interpreter
    program = (
        "دالة ق ()\n"
        "    حاول\n"
        "        رجّع 1\n"
        "    أخيرا\n"
        '        اطبع "تنظيف"\n'
        "    خلاص\n"
        "خلاص\n"
        "اطبع ق()\n"
    )
    path = write_program(tmp_path, program)
    assert main(["run", "--vm", path]) == 0
    captured = capsys.readouterr()
    assert "1" in captured.out
    assert "VM" in captured.err  # a fallback note was printed


def test_run_vm_executes_closures(tmp_path, capsys):
    program = (
        "دالة عداد ()\n"
        "    خلي س = 0\n"
        "    دالة زود ()\n"
        "        س = س زائد 1\n"
        "        رجّع س\n"
        "    خلاص\n"
        "    رجّع زود\n"
        "خلاص\n"
        "خلي ز = عداد()\n"
        "اطبع ز()\n"
        "اطبع ز()\n"
    )
    path = write_program(tmp_path, program)
    assert main(["run", "--vm", path]) == 0
    captured = capsys.readouterr()
    assert captured.out.split() == ["1", "2"]
    assert "VM" not in captured.err  # ran on the VM, no fallback


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
    # a رجّع crossing a أخيرا isn't covered by the VM, so no comparison
    program = (
        "دالة ق ()\n"
        "    حاول\n"
        "        رجّع 1\n"
        "    أخيرا\n"
        '        اطبع "تنظيف"\n'
        "    خلاص\n"
        "خلاص\n"
    )
    path = write_program(tmp_path, program)
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


def test_repl_multiline_nested_blocks():
    out: list[str] = []
    code = run_repl(
        input_fn=make_input(
            ["كرر 2 مرات", "لو صح", 'اطبع "جوّه"', "خلاص", "خلاص", "خروج"]
        ),
        out=out.append,
        err=lambda _text: None,
    )
    assert code == 0
    assert [line for line in out if line == "جوّه"] == ["جوّه", "جوّه"]


def test_repl_continues_an_expression_inside_parens():
    out: list[str] = []
    code = run_repl(
        input_fn=make_input(["خلي س = (1 +", "2)", "اطبع س", "خروج"]),
        out=out.append,
        err=lambda _text: None,
    )
    assert code == 0
    assert "3" in out


def test_repl_unterminated_string_reports_and_keeps_going():
    out: list[str] = []
    err: list[str] = []
    code = run_repl(
        input_fn=make_input(['اطبع "ناقص', 'اطبع "كملنا"', "خروج"]),
        out=out.append,
        err=err.append,
    )
    assert code == 0
    assert "E1002" in "\n".join(err)
    assert "كملنا" in out


# ---------------------------------------------------------------- projects


def test_init_creates_a_runnable_project(tmp_path, capsys):
    project = tmp_path / "مشروعي"
    assert main(["init", str(project)]) == 0
    assert (project / "حزمة.json").is_file()
    assert (project / "رئيسي.arb").is_file()
    assert "اتعمل" in capsys.readouterr().out

    assert main(["run", str(project / "رئيسي.arb")]) == 0
    assert "أهلا بالعالم" in capsys.readouterr().out


def test_init_never_overwrites_existing_files(tmp_path, capsys):
    project = tmp_path / "موجود"
    project.mkdir()
    entry = project / "رئيسي.arb"
    entry.write_text('اطبع "مخصص"\n', encoding="utf-8")
    (project / "حزمة.json").write_text('{"الاسم": "قديم"}', encoding="utf-8")

    assert main(["init", str(project)]) == 0
    assert entry.read_text(encoding="utf-8") == 'اطبع "مخصص"\n'
    assert "موجود بالفعل" in capsys.readouterr().out


def test_doctor_accepts_a_fresh_project(tmp_path, capsys):
    project = tmp_path / "سليم"
    assert main(["init", str(project)]) == 0
    capsys.readouterr()

    assert main(["doctor", str(project)]) == 0
    assert "تمام" in capsys.readouterr().out


def test_doctor_reports_a_broken_manifest(tmp_path, capsys):
    project = tmp_path / "خربان"
    project.mkdir()
    (project / "حزمة.json").write_text("{", encoding="utf-8")

    assert main(["doctor", str(project)]) == 1
    assert "حزمة.json" in capsys.readouterr().err


@pytest.mark.parametrize("exit_word", ["خروج", "exit", "quit"])
def test_repl_exit_words(exit_word):
    out: list[str] = []
    code = run_repl(
        input_fn=make_input([exit_word]), out=out.append, err=lambda _text: None
    )
    assert code == 0
