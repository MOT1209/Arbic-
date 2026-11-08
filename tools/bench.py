"""Best-of-N timings for the interpreter and the bytecode VM.

Usage:
    python -m tools.bench [--iterations N] [program ...]

With no arguments it measures a few reference programs. The harness only
records measurements — it makes no claim that one backend is faster for a
given program, and it never runs as part of the CI gate.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from pathlib import Path

from al_arabiya.compiler.diagnostics.errors import DiagnosticError
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.runtime.interpreter.interpreter import Interpreter
from al_arabiya.vm.compiler import compile_program, unsupported_reason
from al_arabiya.vm.vm import VM

DEFAULT_PROGRAMS = (
    "examples/loops.arb",
    "examples/functions.arb",
    "examples/collections.arb",
)


def best_of(run_once: Callable[[], None], iterations: int) -> float:
    best = float("inf")
    for _ in range(max(1, iterations)):
        start = time.perf_counter()
        run_once()
        best = min(best, time.perf_counter() - start)
    return best


def measure(path: Path, iterations: int) -> int:
    text = path.read_text(encoding="utf-8-sig")
    started = time.perf_counter()
    result = compile_source(text, str(path))
    compile_seconds = time.perf_counter() - started

    if result.program is None:
        print(f"{path}: compilation failed ({len(result.diagnostics)} diagnostics)")
        return 1

    program = result.program
    base_dir = str(path.resolve().parent)
    print(f"{path}")
    print(f"  compile      {compile_seconds * 1000:8.2f} ms")

    def run_interpreter() -> None:
        Interpreter(write=lambda _text: None, base_dir=base_dir).run(program)

    try:
        interpreter_seconds = best_of(run_interpreter, iterations)
    except DiagnosticError as exc:
        print(f"  interpreter  failed: {exc.diagnostic.code}")
        return 1
    print(f"  interpreter  {interpreter_seconds * 1000:8.2f} ms")

    reason = unsupported_reason(program)
    if reason is not None:
        print(f"  vm           skipped ({reason})")
        return 0

    vm_program = compile_program(program)

    def run_vm() -> None:
        VM(write=lambda _text: None, base_dir=base_dir).run(vm_program)

    try:
        vm_seconds = best_of(run_vm, iterations)
    except DiagnosticError as exc:
        print(f"  vm           failed: {exc.diagnostic.code}")
        return 1
    print(f"  vm           {vm_seconds * 1000:8.2f} ms")
    if vm_seconds > 0:
        print(f"  ratio        {interpreter_seconds / vm_seconds:8.2f}x")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Time interpreter vs bytecode VM.")
    parser.add_argument("programs", nargs="*", default=list(DEFAULT_PROGRAMS))
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args(argv)

    failures = 0
    for name in args.programs:
        path = Path(name)
        if not path.is_file():
            print(f"{path}: file not found")
            failures += 1
            continue
        failures += measure(path, args.iterations)
        print()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
