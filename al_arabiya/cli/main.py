"""The ``arabic`` command line interface.

Exit codes:
    0 — success
    1 — language error (compile or runtime)
    2 — usage / file error
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from al_arabiya import __version__
from al_arabiya.cli.repl import run_repl
from al_arabiya.compiler.checker import check_types
from al_arabiya.compiler.diagnostics.diagnostics import (
    Diagnostic,
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

_COMMANDS = frozenset(
    {
        "run",
        "check",
        "bench",
        "repl",
        "lsp",
        "packages",
        "حزمة",
        "init",
        "doctor",
        "version",
        "help",
    }
)


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass


def _emit_diagnostics(diagnostics: Iterable[Diagnostic], source: SourceFile) -> None:
    text = render_diagnostics(diagnostics, source)
    if text:
        sys.stderr.write(text + "\n")


def _read_source(path: str) -> SourceFile | None:
    """Read a program once, through the same abstraction diagnostics render from."""
    try:
        return SourceFile.from_path(path)
    except OSError:
        sys.stderr.write(f"❌ مش لاقي الملف: {path}\n")
        return None


def cmd_run(path: str, use_vm: bool = False) -> int:
    source = _read_source(path)
    if source is None:
        return 2
    result = compile_source(source.text, path)
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
    source = _read_source(path)
    if source is None:
        return 2
    result = compile_source(source.text, path)
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
    source = _read_source(path)
    if source is None:
        return 2
    result = compile_source(source.text, path)
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


def _registry_path(rest: list[str]) -> str | None:
    for index, argument in enumerate(rest):
        if argument == "--registry" and index + 1 < len(rest):
            return rest[index + 1]
        if argument.startswith("--registry="):
            return argument.split("=", 1)[1]
    return os.environ.get("ARABIC_REGISTRY")


def cmd_packages(rest: list[str]) -> int:
    from al_arabiya.packages import manager

    positional = [arg for arg in rest if not arg.startswith("--")]
    action = positional[0] if positional else "help"
    project_dir = Path(positional[1]) if len(positional) > 1 else Path.cwd()

    if action in ("install", "تثبيت"):
        registry_path = _registry_path(rest)
        if registry_path is None:
            sys.stderr.write(
                "❌ محتاج سجلّ الحزم: --registry <مسار> أو المتغيّر ARABIC_REGISTRY\n"
            )
            return 2
        try:
            resolved = manager.install(project_dir, manager.Registry(Path(registry_path)))
        except manager.PackageError as exc:
            sys.stderr.write(f"❌ {exc}\n")
            return 1
        if not resolved:
            print("مفيش اعتماديات للتثبيت.")
            return 0
        print("اتثبتت الحزم:")
        for name, version in sorted(resolved.items()):
            print(f"  {name} {version}")
        return 0

    if action in ("list", "قائمة"):
        try:
            locked = manager.read_lockfile(project_dir)
        except (OSError, ValueError) as exc:
            sys.stderr.write(f"❌ مش قادر أقرا ملف القفل: {exc}\n")
            return 1
        if not locked:
            print("مفيش حزم مثبتة (شغّل: arabic packages install).")
            return 0
        print("الحزم المثبتة:")
        for locked_name, locked_version in sorted(locked.items()):
            print(f"  {locked_name} {locked_version}")
        return 0

    sys.stderr.write(
        "استخدام: arabic packages <install|list> [مجلد] [--registry <مسار>]\n"
    )
    return 2


def cmd_init(rest: list[str]) -> int:
    from al_arabiya.packages import manager

    positional = [argument for argument in rest if not argument.startswith("-")]
    if len(positional) > 1:
        sys.stderr.write("استخدام: arabic init [مجلد]\n")
        return 2

    project = Path(positional[0]) if positional else Path.cwd()
    try:
        project.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        sys.stderr.write(f"❌ مش قادر أعمل المجلد: {exc}\n")
        return 2

    manifest = project / manager.MANIFEST_NAME
    entry = project / "رئيسي.arb"
    created: list[str] = []
    if not manifest.exists():
        payload = {
            "الاسم": project.resolve().name,
            "الإصدار": "0.1.0",
            "الاعتماديات": {},
        }
        manifest.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        created.append(manager.MANIFEST_NAME)
    if not entry.exists():
        entry.write_text('اطبع "أهلا بالعالم!"\n', encoding="utf-8")
        created.append(entry.name)

    if created:
        print("اتعمل مشروع جديد: " + "، ".join(created))
    else:
        print("المشروع موجود بالفعل — ملمستش أي ملف.")
    return 0


def cmd_doctor(rest: list[str]) -> int:
    from al_arabiya.packages import manager

    positional = [argument for argument in rest if not argument.startswith("-")]
    project = Path(positional[0]) if positional else Path.cwd()
    problems = 0

    def good(label: str) -> None:
        print(f"✓ {label}")

    def bad(label: str, detail: str) -> None:
        nonlocal problems
        problems += 1
        sys.stderr.write(f"✗ {label}: {detail}\n")

    # requires-python already pins >=3.12 at install time, so this is a report,
    # not a check.
    good(f"Python {sys.version.split()[0]}")

    encoding = (sys.stdout.encoding or "").lower()
    if not encoding or "utf" in encoding:
        good(f"ترميز المخرجات: {encoding or 'افتراضي'}")
    else:
        bad("ترميز المخرجات", f"'{encoding}' مش UTF — النص العربي ممكن يتقطع")

    manifest_path = project / manager.MANIFEST_NAME
    if manifest_path.is_file():
        try:
            parsed = manager.read_manifest(manifest_path)
        except manager.PackageError as exc:
            bad("حزمة.json", str(exc))
        else:
            good(f"حزمة.json: {parsed.name} {parsed.version}")
    else:
        good("مفيش حزمة.json (مش مطلوب للتشغيل)")

    if (project / manager.LOCKFILE_NAME).is_file():
        try:
            locked = manager.read_lockfile(project)
        except (OSError, ValueError) as exc:
            bad("ملف القفل", str(exc))
        else:
            good(f"ملف القفل: {len(locked)} حزمة")

    registry = _registry_path(rest) or os.environ.get("ARABIC_REGISTRY")
    if registry is None:
        good("مفيش سجلّ حزم مضبوط (مش مطلوب للتشغيل)")
    elif Path(registry).is_dir():
        good(f"السجلّ: {registry}")
    else:
        bad("السجلّ", f"مش لاقي المجلد: {registry}")

    if problems:
        sys.stderr.write(f"فيه {problems} مشكلة." + "\n")
        return 1
    print("كل حاجة تمام.")
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
        "  arabic packages install تثبيت الحزم من السجلّ المحلّي (في حزم/)\n"
        "  arabic init [مجلد]     يعمل حزمة.json وملف بداية\n"
        "  arabic doctor [مجلد]   يفحص البيئة والمشروع\n"
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
    if name in ("packages", "حزمة"):
        return cmd_packages(rest)
    if name == "version":
        return cmd_version()
    if name == "help":
        return cmd_help()
    if name == "init":
        return cmd_init(rest)
    if name == "doctor":
        return cmd_doctor(rest)

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
