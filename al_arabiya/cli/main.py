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
        "debug",
        "repl",
        "lsp",
        "packages",
        "حزمة",
        "init",
        "doctor",
        "build",
        "test",
        "format",
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


def cmd_run(
    path: str,
    use_vm: bool = False,
    *,
    sandbox: bool = False,
    timeout: float = 5.0,
    memory_mb: int = 256,
) -> int:
    if sandbox:
        from al_arabiya.sandbox import SandboxLimits, run_sandboxed

        program = Path(path)
        if not program.is_file():
            sys.stderr.write(f"❌ مش لاقي الملف: {path}\n")
            return 2
        sandbox_result = run_sandboxed(
            program,
            SandboxLimits(timeout=timeout, memory_bytes=memory_mb * 1024 * 1024),
            base_dir=program.resolve().parent,
        )
        sys.stdout.write(sandbox_result.stdout)
        sys.stderr.write(sandbox_result.stderr)
        if sandbox_result.limit == "output":
            sys.stderr.write("⛔ البرنامج طبع فوق الحد المسموح\n")
        elif sandbox_result.limit == "memory":
            sys.stderr.write("⛔ العامل اتقفل (تعدّى حد الذاكرة أو واجه عطلًا)\n")
        elif sandbox_result.limit == "signal":
            sys.stderr.write("⛔ العامل اتقفل بإشارة من نظام التشغيل (تعدّى حدًّا)\n")
        if sandbox_result.timed_out:
            return 1
        return sandbox_result.exit_code if sandbox_result.exit_code in (0, 1, 2) else 1

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


class _UsageError(Exception):
    """A bad command line (reported with exit code 2)."""


def _bounded(value: str, option: str, low: float, high: float, *, integer: bool) -> float:
    try:
        number = int(value) if integer else float(value)
    except ValueError:
        raise _UsageError(f"{option} محتاج رقم، مش '{value}'") from None
    if not low <= number <= high:
        raise _UsageError(f"{option} لازم يكون بين {low:g} و{high:g}")
    return number


def _parse_run_args(rest: list[str]) -> tuple[bool, bool, float, int, list[str]]:
    use_vm = False
    sandbox = False
    timeout = 5.0
    memory = 256
    files: list[str] = []
    index = 0
    while index < len(rest):
        argument = rest[index]
        if argument == "--vm":
            use_vm = True
        elif argument == "--sandbox":
            sandbox = True
        elif argument in ("--timeout", "--memory"):
            if index + 1 >= len(rest):
                raise _UsageError(f"{argument} محتاج قيمة")
            value = rest[index + 1]
            index += 1
            if argument == "--timeout":
                timeout = _bounded(value, argument, 0.1, 3600, integer=False)
            else:
                memory = int(_bounded(value, argument, 16, 4096, integer=True))
        elif argument.startswith(("--timeout=", "--memory=")):
            option, _, value = argument.partition("=")
            if option == "--timeout":
                timeout = _bounded(value, option, 0.1, 3600, integer=False)
            else:
                memory = int(_bounded(value, option, 16, 4096, integer=True))
        elif argument.startswith("-"):
            raise _UsageError(f"خيار مش معروف: {argument}")
        else:
            files.append(argument)
        index += 1
    return use_vm, sandbox, timeout, memory, files


def _project_files(root: Path) -> list[Path]:
    """Every ``.arb`` file in a project, minus the vendored ``حزم/`` folder."""
    packages = root / "حزم"
    return [path for path in sorted(root.rglob("*.arb")) if packages not in path.parents]


def cmd_build(rest: list[str]) -> int:
    positional = [argument for argument in rest if not argument.startswith("-")]
    if len(positional) > 1:
        sys.stderr.write("استخدام: arabic build [مجلد]\n")
        return 2
    root = Path(positional[0]) if positional else Path.cwd()
    if not root.is_dir():
        sys.stderr.write(f"❌ مش لاقي المجلد: {root}\n")
        return 2
    programs = _project_files(root)
    if not programs:
        sys.stderr.write("❌ مفيش ملفات .arb في المشروع\n")
        return 2

    failed = 0
    for program in programs:
        try:
            source = SourceFile.from_path(str(program))
        except OSError:
            sys.stderr.write(f"❌ مش قادر أقرا: {program}\n")
            failed += 1
            continue
        result = compile_source(source.text, str(program))
        if result.diagnostics:
            _emit_diagnostics(result.diagnostics, result.source)
        if result.program is None or result.has_errors:
            failed += 1
            continue
        type_bag = check_types(result.program)
        if type_bag:
            _emit_diagnostics(type_bag.sorted(), result.source)
        if type_bag.has_errors:
            failed += 1

    if failed:
        sys.stderr.write(f"❌ فشل بناء {failed} من {len(programs)} ملف\n")
        return 1
    print(f"✓ اتبنى المشروع: {len(programs)} ملف")
    return 0


def cmd_test(rest: list[str]) -> int:
    positional = [argument for argument in rest if not argument.startswith("-")]
    if len(positional) > 1:
        sys.stderr.write("استخدام: arabic test [مجلد]\n")
        return 2
    root = Path(positional[0]) if positional else Path.cwd()
    tests_dir = root / "اختبارات"
    if not tests_dir.is_dir():
        sys.stderr.write(f"❌ مفيش مجلد اختبارات في: {root}\n")
        return 2
    programs = sorted(tests_dir.rglob("*.arb"))
    if not programs:
        sys.stderr.write("❌ مجلد اختبارات مفيهوش ملفات .arb\n")
        return 2

    failed: list[str] = []
    for program in programs:
        name = program.relative_to(root).as_posix()
        print(f"• {name}")
        if cmd_run(str(program)) != 0:
            failed.append(name)
    if failed:
        sys.stderr.write(f"❌ فشل {len(failed)} من {len(programs)} اختبار\n")
        for name in failed:
            sys.stderr.write(f"  - {name}\n")
        return 1
    print(f"✓ نجح {len(programs)} اختبار")
    return 0


def cmd_format(rest: list[str]) -> int:
    from al_arabiya.formatter import format_source

    unknown = [
        argument
        for argument in rest
        if argument.startswith("-") and argument != "--check"
    ]
    if unknown:
        sys.stderr.write(f"❌ خيار مش معروف: {unknown[0]}\n")
        return 2
    check_only = "--check" in rest
    positional = [argument for argument in rest if not argument.startswith("-")]
    if len(positional) > 1:
        sys.stderr.write("استخدام: arabic format [مسار] [--check]\n")
        return 2
    target = Path(positional[0]) if positional else Path.cwd()
    files: list[Path]
    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = _project_files(target)
    else:
        sys.stderr.write(f"❌ مش لاقي المسار: {target}\n")
        return 2

    changed: list[Path] = []
    broken = 0
    for program in files:
        try:
            text = program.read_text(encoding="utf-8-sig")
            source = SourceFile.from_path(str(program))
        except OSError:
            sys.stderr.write(f"❌ مش قادر أقرا: {program}\n")
            broken += 1
            continue
        result = format_source(text)
        if result.diagnostics:
            _emit_diagnostics(result.diagnostics, source)
            sys.stderr.write(f"⚠️ اتخطّى (فيه أخطاء): {program}\n")
            broken += 1
            continue
        if result.changed:
            changed.append(program)
            if not check_only:
                with open(program, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(result.text)

    if check_only and changed:
        for program in changed:
            print(f"محتاج تنسيق: {program}")
        sys.stderr.write(f"❌ {len(changed)} ملف محتاج تنسيق\n")
        return 1
    if broken:
        return 1
    if not changed:
        print("كل الملفات منسّقة بالفعل.")
        return 0
    print(f"اتنسّق {len(changed)} ملف.")
    return 0


def cmd_debug(rest: list[str]) -> int:
    """Run the DAP debug adapter on stdio (VS Code and other DAP clients)."""
    program: str | None = None
    for argument in rest:
        if argument == "--stdio":
            continue
        if argument.startswith("-"):
            sys.stderr.write(f"❌ خيار غير معروف: {argument}\n")
            return 2
        if program is not None:
            sys.stderr.write("❌ الأمر 'debug' بياخد ملف واحد بس\n")
            return 2
        program = argument
    from al_arabiya.debugger.session import main as debug_main

    return debug_main(program)


def cmd_version() -> int:
    print(f"arabic {__version__} — AlArabiya / العربية")
    return 0


def cmd_help() -> int:
    print(
        "العربية (AlArabiya) — أمر التشغيل\n"
        "\n"
        "الاستخدام:\n"
        "  arabic run <ملف.arb>    تشغيل ملف (--vm لآلة البايت-كود، --sandbox لعزل التنفيذ)\n"
        "  arabic check <ملف.arb>  تحليل بدون تشغيل (بيطبع كل الأخطاء)\n"
        "  arabic build [مجلد]    تحقق شامل من كل ملفات المشروع\n"
        "  arabic test [مجلد]     يشغّل ملفات اختبارات/*.arb\n"
        "  arabic format [مسار]   ينسّق المسافات (--check يعرض من غير ما يكتب)\n"
        "  arabic bench <ملف.arb>  مقارنة سرعة المفسّر بآلة البايت-كود\n"
        "  arabic debug <ملف.arb>  خادم تصحيح (DAP) على stdio\n"
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
    if name == "debug":
        return cmd_debug(rest)
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
    if name == "build":
        return cmd_build(rest)
    if name == "test":
        return cmd_test(rest)
    if name == "format":
        return cmd_format(rest)

    try:
        use_vm, sandbox, timeout, memory, files = _parse_run_args(rest)
    except _UsageError as exc:
        sys.stderr.write(f"❌ {exc}\n")
        return 2
    if len(files) != 1:
        sys.stderr.write(f"❌ الأمر '{name}' محتاج اسم ملف واحد\n")
        return 2
    if name == "check":
        return cmd_check(files[0])
    if name == "bench":
        return cmd_bench(files[0])
    return cmd_run(
        files[0],
        use_vm=use_vm,
        sandbox=sandbox,
        timeout=timeout,
        memory_mb=memory,
    )
