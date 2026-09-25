"""Diagnostics tests: bag behaviour and the Arabic renderer."""

from __future__ import annotations

import pytest

from al_arabiya.compiler.diagnostics.diagnostics import (
    Diagnostic,
    DiagnosticBag,
    Severity,
    render_diagnostic,
    render_diagnostics,
)
from al_arabiya.compiler.diagnostics.source import SourceFile
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.compiler.lexer.positions import Position, Span


def span_at(line: int = 1, column: int = 1, offset: int = 0, length: int = 1) -> Span:
    start = Position(offset, line, column)
    end = Position(offset + length, line, column + length)
    return Span(start, end)


# --------------------------------------------------------------------- bag


def test_bag_starts_empty():
    bag = DiagnosticBag()
    assert len(bag) == 0
    assert not bag.has_errors
    assert not bag


def test_bag_collects_error():
    bag = DiagnosticBag()
    bag.error("E9999", "مشكلة", span_at())
    assert bag.has_errors
    assert len(bag.errors) == 1


def test_bag_warning_is_not_error():
    bag = DiagnosticBag()
    bag.warning("W9999", "تحذير", span_at())
    assert not bag.has_errors
    assert bag.has_warnings
    assert len(bag.warnings) == 1


def test_bag_deduplicates():
    bag = DiagnosticBag()
    bag.error("E9999", "مشكلة", span_at())
    bag.error("E9999", "مشكلة", span_at())
    assert len(bag) == 1


def test_bag_limit():
    bag = DiagnosticBag(limit=3)
    for index in range(10):
        bag.error("E9999", f"خطأ {index}", span_at(offset=index))
    assert len(bag) == 3
    assert bag.truncated


def test_bag_sorted_by_position():
    bag = DiagnosticBag()
    bag.error("E2", "ثاني", span_at(line=2, offset=10))
    bag.error("E1", "أول", span_at(line=1, offset=0))
    assert [d.span.start.line for d in bag.sorted()] == [1, 2]


def test_diagnostic_location_property():
    diagnostic = Diagnostic("E1001", Severity.ERROR, "رسالة", span_at(4, 12, 40))
    assert diagnostic.location == "4:12"
    assert diagnostic.is_error


# ----------------------------------------------------------------- render


def test_render_contains_all_required_parts():
    source = SourceFile("main.arb", 'خلي العمر = "أحمد"')
    diagnostic = Diagnostic(
        code="E1001",
        severity=Severity.ERROR,
        message="القيمة النصية لا تتوافق مع النوع المتوقع.",
        span=span_at(line=1, column=12, offset=11, length=7),
        suggestion="استخدم رقمًا",
    )
    rendered = render_diagnostic(diagnostic, source)
    assert "خطأ E1001" in rendered
    assert "main.arb:1:12" in rendered
    assert 'خلي العمر = "أحمد"' in rendered
    caret_line = rendered.splitlines()[5]
    assert set(caret_line.strip()) == {"^"}
    assert caret_line.index("^") == 11  # aligned under column 12
    assert "القيمة النصية لا تتوافق" in rendered
    assert "اقتراح: استخدم رقمًا" in rendered


def test_render_warning_uses_arabic_severity():
    source = SourceFile("main.arb", "س = 5")
    diagnostic = Diagnostic(
        code="W3001",
        severity=Severity.WARNING,
        message="تحذير بسيط",
        span=span_at(),
    )
    assert render_diagnostic(diagnostic, source).startswith("تحذير W3001")


def test_render_multiple_diagnostics():
    source = SourceFile("main.arb", "x")
    bag = DiagnosticBag()
    bag.error("E1001", "أول", span_at())
    bag.error("E1002", "تاني", span_at(offset=2))
    rendered = render_diagnostics(bag.sorted(), source)
    assert "أول" in rendered
    assert "تاني" in rendered


def test_render_missing_line_is_empty():
    source = SourceFile("main.arb", "سطر واحد")
    diagnostic = Diagnostic("E1001", Severity.ERROR, "رسالة", span_at(line=99))
    assert render_diagnostic(diagnostic, source)  # no crash


def test_render_tabs_are_flattened():
    source = SourceFile("main.arb", "\tخلي س = 1")
    diagnostic = Diagnostic("E1001", Severity.ERROR, "رسالة", span_at(column=5, offset=4))
    rendered = render_diagnostic(diagnostic, source)
    assert "\t" not in rendered.splitlines()[4]


# ----------------------------------------------------------------- source


def test_source_line_text():
    source = SourceFile("a.arb", "أول\nتاني\nتالت")
    assert source.line_count == 3
    assert source.line_text(2) == "تاني"
    assert source.line_text(0) == ""
    assert source.line_text(99) == ""


def test_source_handles_crlf():
    source = SourceFile("a.arb", "أول\r\nتاني")
    assert source.line_text(1) == "أول"
    assert source.line_text(2) == "تاني"


def test_source_from_missing_path():
    with pytest.raises(OSError):
        SourceFile.from_path("لا_يوجد_ملف.arb")


def test_compile_produces_diagnostic_with_code_and_position():
    result = compile_source("خلي = 5", "main.arb")
    error = next(d for d in result.diagnostics if d.is_error)
    assert error.code.startswith("E")
    assert error.span.start.line == 1
    assert error.span.start.column == 5
    assert render_diagnostic(error, result.source)
