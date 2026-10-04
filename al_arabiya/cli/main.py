"""The ``arabic`` command line interface.

Exit codes:
    0 — success
    1 — language error (compile or runtime)
    2 — usage / file error
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
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
from al_arabiya.vm.compiler import compile_program, unsupported_reason
from al_arabiya.vm.vm import VM

__all__ = ["main"]

_COMMANDS = frozenset({"run", "check", "bench", "repl", "lsp", "version", "help"})


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


def cmd_run(path: str, use_vm: bool = False) -> int:
    text = _read_source(path)
    if text is None:
        return 2
    result = compile_source(text, path)
    if result.diagnostics:
        _emit_diagnostics(result.diagnostics, result.source)
    if result.program is None:
        return 1

    if use_vm:
        reason = unsupported_reason(result.program)
        if reason is None:
            try:
                VM(base_dir=str(Path(path).resolve().parent)).run(
                    compile_program(result.program)
                )
            except DiagnosticError as exc:
                sys.stderr.write(render_diagnostic(exc.diagnostic, result.source) + "\n")
                return 1
            return 0
        sys.stderr.write(f"ℹ️ الـ VM لسه مبيدعمش {reason}؛ رجعت للمفسّر\n")

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


def cmd_bench(path: str, iterations: int = 3) -> int:
    text = _read_source(path)
    if text is None:
        return 2
    result = compile_source(text, path)
    if result.diagnostics:
        _emit_diagnostics(result.diagnostics, result.source)
    if result.program is None:
        return 1

    reason = unsupported_reason(result.program)
    if reason is not None:
        sys.stderr.write(f"ℹ️ الـ VM لسه مبيدعمش {reason}؛ المقارنة مش متاحة\n")
        return 2

    program = result.program
    main = compile_program(program)
    base_dir = str(Path(path).resolve().parent)

    def time_backend(run_once: Callable[[], None]) -> float:
        best = float("inf")
        for _ in range(max(1, iterations)):
            start = time.perf_counter()
            run_once()
            best = min(best, time.perf_counter() - start)
        return best

    interpreter_time = time_backend(
        lambda: Interpreter(write=lambda _text: None, base_dir=base_dir).run(program)
    )
    vm_time = time_backend(
        lambda: VM(write=lambda _text: None, base_dir=base_dir).run(main)
    )

    speedup = interpreter_time / vm_time if vm_time > 0 else float("inf")
    print(f"المفسّر (interpreter): {interpreter_time * 1000:.1f} ms")
    print(f"الآلة (bytecode VM):   {vm_time * 1000:.1f} ms")
    print(f"التسريع (speedup):     {speedup:.2f}×  (أفضل من {iterations} محاولات)")
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
        "  arabic run <ملف.arb>    تشغيل ملف (أضف --vm لآلة البايت-كود)\n"
        "  arabic check <ملف.arb>  تحليل بدون تشغيل (بيطبع كل الأخطاء)\n"
        "  arabic bench <ملف.arb>  مقارنة سرعة المفسّر بآلة البايت-كود\n"
        "  arabic repl             وضع التفاعل المباشر\n"
        "  arabic lsp              خادم المحرّر (Language Server عبر stdio)\n"
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
    if name == "lsp":
        from al_arabiya.lsp.server import main as lsp_main

        return lsp_main()
    if name == "version":
        return cmd_version()
    if name == "help":
        return cmd_help()

    use_vm = "--vm" in rest
    files = [argument for argument in rest if not argument.startswith("-")]
    if len(files) != 1:
        sys.stderr.write(f"❌ الأمر '{name}' محتاج اسم ملف واحد\n")
        return 2
    if name == "check":
        return cmd_check(files[0])
    if name == "bench":
        return cmd_bench(files[0])
    return cmd_run(files[0], use_vm=use_vm)
