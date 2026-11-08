"""Tests for the whitespace-only formatter."""

from __future__ import annotations

from al_arabiya.cli.main import main
from al_arabiya.formatter import format_source


def test_collapses_blank_lines_and_strips_trailing_spaces() -> None:
    result = format_source('خلي س = 1\n\n\n\nاطبع س   \n')
    assert result.changed
    assert result.text == "خلي س = 1\n\nاطبع س\n"


def test_expands_leading_tabs() -> None:
    result = format_source('\tاطبع "أ"\n')
    assert result.text == '    اطبع "أ"\n'


def test_normalizes_crlf_and_missing_final_newline() -> None:
    result = format_source('اطبع "أ"\r\nاطبع "ب"')
    assert result.text == 'اطبع "أ"\nاطبع "ب"\n'


def test_is_idempotent() -> None:
    once = format_source('\tاطبع "أ"   \n\n\n')
    twice = format_source(once.text)
    assert once.changed
    assert not twice.changed
    assert twice.text == once.text


def test_never_touches_string_contents() -> None:
    text = 'اطبع "مسافتين  جوه النص، وعلامة تبويب\\t"   \n'
    result = format_source(text)
    assert result.changed
    assert '"مسافتين  جوه النص، وعلامة تبويب\\t"' in result.text
    assert result.text.count("  ") == 1  # the two spaces inside the literal only


def test_broken_source_is_returned_untouched() -> None:
    text = "لو صح\n"
    result = format_source(text)
    assert not result.changed
    assert result.text == text
    assert result.diagnostics


def test_cli_format_check_does_not_write(tmp_path, capsys) -> None:
    path = tmp_path / "main.arb"
    path.write_text("خلي س = 1\n\n\nاطبع س\n", encoding="utf-8")

    assert main(["format", "--check", str(path)]) == 1
    assert "محتاج تنسيق" in capsys.readouterr().out
    assert path.read_text(encoding="utf-8") == "خلي س = 1\n\n\nاطبع س\n"

    assert main(["format", str(path)]) == 0
    assert path.read_text(encoding="utf-8") == "خلي س = 1\n\nاطبع س\n"
    capsys.readouterr()
    assert main(["format", "--check", str(path)]) == 0


def test_cli_format_directory_skips_vendored_packages(tmp_path, capsys) -> None:
    (tmp_path / "حزم" / "مكتبة").mkdir(parents=True)
    vendored = tmp_path / "حزم" / "مكتبة" / "رئيسي.arb"
    vendored.write_text("خلي س = 1\n\n\n\n", encoding="utf-8")
    loose = tmp_path / "رئيسي.arb"
    loose.write_text("خلي س = 1\n\n\n\n", encoding="utf-8")

    assert main(["format", str(tmp_path)]) == 0
    assert "1 ملف" in capsys.readouterr().out
    assert vendored.read_text(encoding="utf-8") == "خلي س = 1\n\n\n\n"
    assert loose.read_text(encoding="utf-8") == "خلي س = 1\n"


def test_cli_format_refuses_broken_files(tmp_path, capsys) -> None:
    path = tmp_path / "main.arb"
    path.write_text("لو صح\n", encoding="utf-8")
    assert main(["format", str(path)]) == 1
    assert "E2004" in capsys.readouterr().err
    assert path.read_text(encoding="utf-8") == "لو صح\n"


def test_cli_format_missing_path(tmp_path, capsys) -> None:
    assert main(["format", str(tmp_path / "لا_يوجد")]) == 2
