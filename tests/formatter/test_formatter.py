"""Tests for the token-aware formatter."""

from __future__ import annotations

from al_arabiya.cli.main import main
from al_arabiya.formatter import format_source


def formatted(source: str) -> str:
    result = format_source(source)
    assert result.changed, [(d.code, d.message) for d in result.diagnostics]
    return result.text


# ------------------------------------------------------------------ spacing


def test_spaces_binary_operators() -> None:
    assert formatted("خلي س=1+2*3\n") == "خلي س = 1 + 2 * 3\n"
    assert formatted("خلي ب = س>1 و س<9\n") == "خلي ب = س > 1 و س < 9\n"


def test_keeps_a_unary_minus_attached() -> None:
    assert formatted("خلي س=-5\n") == "خلي س = -5\n"
    assert formatted("كرر  -2  مرات\nخلاص\n") == "كرر -2 مرات\nخلاص\n"


def test_tightens_calls_indexing_and_members() -> None:
    source = 'اطبع ف( 1،2 )\nخلي س=ق[ 0 ]\nخلي ع=ك.اسم\n'
    expected = 'اطبع ف(1، 2)\nخلي س = ق[0]\nخلي ع = ك.اسم\n'
    assert formatted(source) == expected


def test_function_declarations_have_no_space_before_the_paren() -> None:
    source = "دالة اجمع (أ:رقم،ب:رقم):رقم\nرجّع أ+ب\nخلاص\n"
    expected = "دالة اجمع(أ : رقم، ب : رقم) : رقم\n    رجّع أ + ب\nخلاص\n"
    assert formatted(source) == expected


def test_dict_colon_is_tight_and_annotation_colon_is_spaced() -> None:
    source = 'خلي م={ "أ":1،"ب":2 }\n'
    expected = 'خلي م = {"أ": 1، "ب": 2}\n'
    assert formatted(source) == expected


def test_lambda_keeps_a_space_after_the_keyword() -> None:
    source = "خلي ف = دالة (س)\nرجّع س\nخلاص\n"
    expected = "خلي ف = دالة (س)\n    رجّع س\nخلاص\n"
    assert formatted(source) == expected


# ------------------------------------------------------------------- layout


def test_top_level_indentation_is_removed() -> None:
    assert formatted('\tاطبع "أ"\n') == 'اطبع "أ"\n'


def test_reindents_nested_blocks() -> None:
    source = "لو صح\n  خلي س = 1\n     اطبع س\nخلاص\n"
    expected = "لو صح\n    خلي س = 1\n    اطبع س\nخلاص\n"
    assert formatted(source) == expected


def test_else_and_catch_align_with_their_openers() -> None:
    source = (
        "حاول\n"
        "اطبع 1\n"
        "امسك خطأ\n"
        "اطبع 2\n"
        "أخيرا\n"
        "اطبع 3\n"
        "خلاص\n"
    )
    expected = (
        "حاول\n"
        "    اطبع 1\n"
        "امسك خطأ\n"
        "    اطبع 2\n"
        "أخيرا\n"
        "    اطبع 3\n"
        "خلاص\n"
    )
    assert formatted(source) == expected


def test_match_cases_sit_inside_the_match_block() -> None:
    source = "طابق س\nحالة 1\nاطبع 1\nحالة 2\nاطبع 2\nغير كده\nاطبع 3\nخلاص\n"
    expected = (
        "طابق س\n"
        "    حالة 1\n"
        "        اطبع 1\n"
        "    حالة 2\n"
        "        اطبع 2\n"
        "    غير كده\n"
        "        اطبع 3\n"
        "خلاص\n"
    )
    assert formatted(source) == expected


def test_private_method_opens_one_block() -> None:
    source = "صنف ص\nخاص دالة س()\nرجّع 1\nخلاص\nخلاص\n"
    expected = "صنف ص\n    خاص دالة س()\n        رجّع 1\n    خلاص\nخلاص\n"
    assert formatted(source) == expected


def test_interface_signatures_do_not_open_a_block() -> None:
    source = "واجهة مطبوع\nدالة س() : نص\nخلاص\nخلي ع = 1\n"
    expected = "واجهة مطبوع\n    دالة س() : نص\nخلاص\nخلي ع = 1\n"
    assert formatted(source) == expected


def test_continuation_lines_inside_brackets_are_indented_once() -> None:
    source = "خلي ق = [\n1،\n2،\n]\n"
    expected = "خلي ق = [\n    1،\n    2،\n]\n"
    assert formatted(source) == expected


def test_collapses_blank_lines_and_strips_trailing_spaces() -> None:
    result = format_source('خلي س = 1\n\n\n\nاطبع س   \n')
    assert result.changed
    assert result.text == "خلي س = 1\n\nاطبع س\n"


def test_normalizes_crlf_and_missing_final_newline() -> None:
    result = format_source('اطبع "أ"\r\nاطبع "ب"')
    assert result.text == 'اطبع "أ"\nاطبع "ب"\n'


# ---------------------------------------------------------------- comments


def test_preserves_and_reindents_comments() -> None:
    source = (
        "# عنوان   \n"
        "لو صح\n"
        "# جوّه\n"
        'اطبع "أ"# بعد الكود\n'
        "خلاص\n"
    )
    expected = (
        "# عنوان\n"
        "لو صح\n"
        "    # جوّه\n"
        '    اطبع "أ"  # بعد الكود\n'
        "خلاص\n"
    )
    assert formatted(source) == expected


def test_hash_inside_a_string_is_not_a_comment() -> None:
    assert formatted('اطبع "a#b"   \n') == 'اطبع "a#b"\n'


# -------------------------------------------------------- safety and repeat


def test_is_idempotent() -> None:
    source = (
        "# مثال\n"
        "صنف شخص\n"
        "دالة __تهيئة__(الاسم)\n"
        "انا.الاسم=الاسم\n"
        "خلاص\n"
        "خلاص\n"
        "خلي ع=شخص(\"أ\")\n"
    )
    once = format_source(source)
    assert once.changed
    twice = format_source(once.text)
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


# --------------------------------------------------------------------- CLI


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
