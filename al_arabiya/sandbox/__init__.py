"""Run an AlArabiya program in an isolated worker process.

The worker is a separate ``python`` process with:

* a wall-clock timeout enforced from here (the worker is killed, not waited on);
* a hard memory ceiling — ``RLIMIT_AS`` on POSIX, a Job Object on Windows;
* closed stdin, so ``اقرأ`` cannot block on a service's terminal;
* capped stdout/stderr, so a program cannot exhaust our memory by printing;
* the program's folder as the working directory, exactly like a local run.

What this does *not* do yet: block filesystem or network access at the OS
level.  Today the language has no file/network builtins at all, so a program
cannot reach either; the moment interop or I/O lands, the seccomp/AppContainer
layer described in ``docs/architecture/sandbox-design.md`` becomes mandatory
before that feature ships.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = ["SandboxLimits", "SandboxResult", "worker_command", "run_sandboxed"]

_MARKER = "⛔"


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    """Hard limits for one run."""

    timeout: float = 5.0
    memory_bytes: int = 256 * 1024 * 1024
    output_bytes: int = 64 * 1024


@dataclass(frozen=True, slots=True)
class SandboxResult:
    """What the worker produced, with the reason it stopped if it was killed."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    limit: str | None = None  # "time" | "output" | "memory" | None


def worker_command(path: Path, limits: SandboxLimits) -> list[str]:
    """The argv used to start the worker (kept separate so tests can inspect it)."""
    return [
        sys.executable,
        "-s",
        "-m",
        "al_arabiya.sandbox.worker",
        "--timeout",
        f"{limits.timeout}",
        "--memory",
        f"{limits.memory_bytes}",
        "--output",
        f"{limits.output_bytes}",
        str(path),
    ]


def _decode(raw: bytes, limit: int) -> str:
    text = raw.decode("utf-8", errors="replace")
    if len(text) > limit:
        return text[:limit] + f"\n{_MARKER} المخرجات اتقصّت عند الحد\n"
    return text


def _worker_env() -> dict[str, str]:
    """A minimal environment: no registry, tokens or user config leak in."""
    package_root = str(Path(__file__).resolve().parents[2])
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": package_root,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


def run_sandboxed(
    path: Path,
    limits: SandboxLimits | None = None,
    base_dir: Path | None = None,
) -> SandboxResult:
    """Run ``path`` inside the worker and return its captured result."""
    limits = limits or SandboxLimits()
    path = path.resolve()
    cwd = (base_dir or path.parent).resolve()
    try:
        process = subprocess.Popen(
            worker_command(path, limits),
            cwd=str(cwd),
            env=_worker_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        return SandboxResult(2, "", f"❌ مش قادر أبدأ العامل: {exc}\n", limit="start")

    timed_out = False
    try:
        stdout_raw, stderr_raw = process.communicate(timeout=limits.timeout + 2.0)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout_raw, stderr_raw = process.communicate()

    # leave a little room for the truncation marker itself
    room = max(1024, limits.output_bytes)
    stdout = _decode(stdout_raw, room)
    stderr = _decode(stderr_raw, room)

    if timed_out:
        stderr += f"{_MARKER} الوقت خلص ({limits.timeout:g} ثانية) — العملية اتقفلت\n"
        return SandboxResult(1, stdout, stderr, timed_out=True, limit="time")

    limit: str | None = None
    if process.returncode == 3:
        limit = "output"
    elif process.returncode != 0 and not stderr.strip():
        limit = "memory"
    return SandboxResult(
        process.returncode if process.returncode >= 0 else 1,
        stdout,
        stderr,
        limit=limit,
    )
