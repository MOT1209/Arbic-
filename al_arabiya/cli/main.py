"""The ``arabic`` command line interface.

Exit codes:
    0 — success
    1 — language error (compile or runtime)
    2 — usage / file error
"""

from __future__ import annotations

import sys
from pathlib import Path

from al_arabiya import __version__
from al_arabiya.cli.repl import run_repl
from al_arabiya.compiler.checker import check_types
from al_arabiya.compiler.diagnostics.diagnostics import (
    DiagnosticBag,
    render_diagnostic,
    render_diagnostics,
)
from al_arabiya.compiler.diagnostics.errors import DiagnosticError
from al_arabiya.compiler.diagnostics.source import SourceFile
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.runtime.interpreter.interpreter import Interpreter

__all__ = ["main"]

_COMMANDS = frozenset({"run", "check", "repl", "version", "help"})


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            pass


def _emit_diagnostics(diagnostics: object, source: SourceFile) -> None:
    text = render_diagnostics(diagnostics, source)  # type: ignore[arg-type]
    if text:
        sys.stderr.write(text + "\n")


def _read_source(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8-sig") as handle:
            return handle.read()
    except OSError:
        sys.stderr.write(f"❌ مش لاقي الملف: {path}\n")
        return None


def cmd_run(path: str) -> int:
    text = _read_source(path)
    if text is None:
        return 2
    result = compile_source(text, path)
    if result.diagnostics:
        _emit_diagnostics(result.diagnostics, result.source)
    if result.program is None:
        return 1

    runtime_bag: DiagnosticBag = DiagnosticBag()
    interpreter = Interpreter(
        diagnostics=runtime_bag,
        base_dir=str(Path(path).resolve().parent),
    )
    try:
        interpreter.run(result.program)
    except DiagnosticError as exc:
        sys.stderr.write(render_diagnostic(exc.diagnostic, result.source) + "\n")
        return 1
    if runtime_bag:
        _emit_diagnostics(runtime_bag.sorted(), result.source)
    return 0


def cmd_check(path: str) -> int:
    text = _read_source(path)
    if text is None:
        return 2
    result = compile_source(text, path)
    if result.diagnostics:
        _emit_diagnostics(result.diagnostics, result.source)
    if result.has_errors:
        sys.stderr.write("❌ فيه أخطاء في الكود\n")
        return 1

    # Static (gradual) type checking runs only once the syntax is clean.
    if result.program is not None:
        type_bag = check_types(result.program)
        if type_bag:
            _emit_diagnostics(type_bag.sorted(), result.source)
        if type_bag.has_errors:
            sys.stderr.write("❌ فيه أخطاء في الأنواع\n")
            return 1

    sys.stderr.write("✓ الكود سليم\n")
    return 0


def cmd_version() -> int:
    print(f"arabic {__version__} — AlArabiya / العربية")
    return 0


def cmd_help() -> int:
    print(
        "العربية (AlArabiya) — أمر التشغيل\n"
        "\n"
        "الاستخدام:\n"
        "  arabic run <ملف.arb>    تشغيل ملف\n"
        "  arabic check <ملف.arb>  تحليل بدون تشغيل (بيطبع كل الأخطاء)\n"
        "  arabic repl             وضع التفاعل المباشر\n"
        "  arabic version          إصدار اللغة\n"
        "  arabic help             هذه المساعدة\n"
        "\n"
        "أكواد الخروج:\n"
        "  0  نجاح\n"
        "  1  خطأ لغوي (ترجمة أو تشغيل)\n"
        "  2  خطأ استخدام / الملف مش موجود"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        return run_repl()
    command = args[0]
    if command in ("-h", "--help"):
        return cmd_help()
    if command not in _COMMANDS:
        if command.endswith(".arb") or Path(command).exists():
            args = ["run", *args]
        else:
            sys.stderr.write(f"❌ أمر مش معروف: {command}\n")
            return 2

    name, rest = args[0], args[1:]
    if name == "repl":
        return run_repl()
    if name == "version":
        return cmd_version()
    if name == "help":
        return cmd_help()
    if len(rest) != 1:
        sys.stderr.write(f"❌ الأمر '{name}' محتاج اسم ملف واحد\n")
        return 2
    if name == "check":
        return cmd_check(rest[0])
    return cmd_run(rest[0])
