"""The sandbox worker process.

Started by :func:`al_arabiya.sandbox.run_sandboxed` with explicit limits on the
command line, then it applies them to itself before running anything:

* POSIX — ``RLIMIT_AS`` (address space), ``RLIMIT_CPU``, ``RLIMIT_FSIZE``
  (no files may be written) and ``RLIMIT_NOFILE``.
* Windows — a Job Object carrying a process-memory ceiling and a single-process
  limit.  If the job cannot be created, the worker refuses to run: a limit that
  silently did not apply is worse than no sandbox at all.

stdout/stderr are wrapped in capped writers so a program that prints forever
cannot exhaust the parent's memory.  Exceeding a cap exits with code 3, which
the parent reports as the output limit.
"""

from __future__ import annotations

import argparse
import ctypes
import importlib
import sys
from typing import Any, cast

_OUTPUT_LIMIT_EXIT = 3


class _OutputLimit(Exception):
    """Raised when a capped stream would be written past its limit."""


class _CappedWriter:
    """A text stream that stops accepting writes after ``limit`` bytes."""

    def __init__(self, stream: object, limit: int) -> None:
        self._stream = stream
        self._limit = limit
        self._used = 0

    def write(self, text: str) -> int:
        if self._used >= self._limit:
            raise _OutputLimit
        encoded = text.encode("utf-8", errors="replace")
        room = self._limit - self._used
        if len(encoded) > room:
            text = encoded[:room].decode("utf-8", errors="ignore")
            encoded = text.encode("utf-8", errors="replace")
            self._used = self._limit
            cast(Any, self._stream).write(text)
            raise _OutputLimit
        self._used += len(encoded)
        cast(Any, self._stream).write(text)
        return len(text)

    def flush(self) -> None:
        cast(Any, self._stream).flush()

    def isatty(self) -> bool:
        return False

    def __getattr__(self, name: str) -> object:
        return getattr(self._stream, name)


def _apply_posix_limits(memory_bytes: int, timeout: float) -> None:
    resource = cast(Any, importlib.import_module("resource"))
    # CPU time is only a backstop: the parent enforces the wall-clock timeout,
    # and a lower CPU limit would kill the worker first and hide that fact.
    seconds = max(2, int(timeout) + 5)
    wanted = {
        "RLIMIT_AS": memory_bytes,
        "RLIMIT_CPU": seconds,
        "RLIMIT_FSIZE": 0,
        "RLIMIT_NOFILE": 32,
    }
    for name, value in wanted.items():
        limit = getattr(resource, name, None)
        if limit is None:
            continue
        try:
            soft, hard = resource.getrlimit(limit)
            cap = value if hard == resource.RLIM_INFINITY else min(value, hard)
            resource.setrlimit(limit, (cap, cap))
        except (ValueError, OSError):
            continue


_JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
_JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def _structure(name: str, fields: list[tuple[str, object]]) -> type[ctypes.Structure]:
    """ctypes requires ``_fields_`` in the class body; declare it dynamically."""
    return cast(
        "type[ctypes.Structure]",
        type(name, (ctypes.Structure,), {"_fields_": fields}),
    )


_BasicLimitInformation = _structure(
    "_BasicLimitInformation",
    [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_void_p),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ],
)

_IoCounters = _structure(
    "_IoCounters",
    [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ],
)

_ExtendedLimitInformation = _structure(
    "_ExtendedLimitInformation",
    [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ],
)


def _apply_windows_limits(memory_bytes: int) -> bool:
    """Assign this process to a Job Object with a memory ceiling."""
    # WinDLL only exists in the Windows typeshed; looked up so Linux type
    # checking stays valid.  Handles are 64-bit pointers, so every restype has
    # to be declared — ctypes truncates to c_int otherwise (ERROR_INVALID_HANDLE).
    kernel32 = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)  # noqa: B009
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.SetInformationJobObject.restype = ctypes.c_int
    kernel32.SetInformationJobObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    kernel32.AssignProcessToJobObject.restype = ctypes.c_int
    kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return False
    info = _ExtendedLimitInformation()
    basic = cast(Any, info).BasicLimitInformation
    basic.LimitFlags = (
        _JOB_OBJECT_LIMIT_PROCESS_MEMORY
        | _JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        | _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    )
    basic.ActiveProcessLimit = 1
    cast(Any, info).ProcessMemoryLimit = memory_bytes
    if not kernel32.SetInformationJobObject(
        ctypes.c_void_p(job),
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        kernel32.CloseHandle(ctypes.c_void_p(job))
        return False
    if not kernel32.AssignProcessToJobObject(
        ctypes.c_void_p(job), kernel32.GetCurrentProcess()
    ):
        kernel32.CloseHandle(ctypes.c_void_p(job))
        return False
    # The handle intentionally stays open: closing it would kill this process
    # (KILL_ON_JOB_CLOSE) before the program has run.
    return True


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--memory", type=int, required=True)
    parser.add_argument("--output", type=int, required=True)
    parser.add_argument("program")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    options = _parse(sys.argv[1:] if argv is None else argv)

    real_stdout, real_stderr = sys.stdout, sys.stderr
    sys.stdout = cast(Any, _CappedWriter(real_stdout, options.output))
    sys.stderr = cast(Any, _CappedWriter(real_stderr, options.output))

    if sys.platform == "win32":
        if not _apply_windows_limits(options.memory):
            real_stderr.write("❌ مش قادر أفعّل حدود العازل على Windows\n")
            return 2
    else:
        _apply_posix_limits(options.memory, options.timeout)

    from al_arabiya.cli.main import main as cli_main

    try:
        code = cli_main(["run", options.program])
    except _OutputLimit:
        code = _OUTPUT_LIMIT_EXIT
    except BaseException as exc:  # noqa: BLE001 - never leak a traceback to users
        try:
            real_stderr.write(f"❌ العامل وقف: {type(exc).__name__}\n")
        except (OSError, ValueError):
            pass
        return 1

    if code == _OUTPUT_LIMIT_EXIT:
        real_stderr.write("⛔ المخرجات عدّت الحد المسموح — التنفيذ اتوقف\n")
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
