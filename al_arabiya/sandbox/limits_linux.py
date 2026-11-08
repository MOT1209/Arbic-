"""Kernel-level guard for the sandbox worker on x86_64 Linux.

Installs a classic-BPF seccomp filter after setting ``PR_SET_NO_NEW_PRIVS``, so
the worker cannot undo it.  Once active, these fail with ``EPERM``:

* every socket-related syscall (``socket``, ``connect``, ``bind``, ...);
* ``open``/``openat`` when the flags request write access;
* the syscalls that modify the filesystem (``unlink``, ``rename``, ``mkdir``,
  ``chmod``, ...).

Reads deliberately stay allowed: the worker still has to read the program and
its imports, the language has no I/O builtins to leak them, and stdout is
capped.  The filter is per-architecture, so :func:`install_guard` returns
``False`` on anything but x86_64 Linux; callers must report that the OS layer
is inactive rather than assume it applied.
"""

from __future__ import annotations

import ctypes
import platform
import sys

__all__ = ["install_guard"]

# Read through a plain ``str`` so mypy does not treat the comparison below as
# statically decided (it checks with the host platform, not the target's).
_PLATFORM: str = sys.platform

_PR_SET_NO_NEW_PRIVS = 38
_PR_SET_SECCOMP = 22
_SECCOMP_MODE_FILTER = 2

_AUDIT_ARCH_X86_64 = 0xC000003E

_BPF_LD_W_ABS = 0x20
_BPF_JMP_JEQ_K = 0x15
_BPF_JMP_JSET_K = 0x45
_BPF_RET_K = 0x06

_RET_ALLOW = 0x7FFF0000
_RET_EPERM = 0x00050000 | 1  # SECCOMP_RET_ERRNO | EPERM

_NR_OFFSET = 0
_ARCH_OFFSET = 4
_ARGS_OFFSET = 16
_ARG_SIZE = 8

# O_WRONLY | O_RDWR | O_CREAT | O_TRUNC | O_APPEND
_WRITE_FLAGS = 0o1 | 0o2 | 0o100 | 0o1000 | 0o2000

# Filesystem-modifying syscalls (x86_64 numbers) that are refused outright.
_DENIED_SYSCALLS = (
    41,  # socket
    42,  # connect
    43,  # accept
    44,  # sendto
    45,  # recvfrom
    46,  # sendmsg
    47,  # recvmsg
    49,  # bind
    50,  # listen
    51,  # getsockname
    52,  # getpeername
    53,  # socketpair
    54,  # setsockopt
    55,  # getsockopt
    76,  # truncate
    77,  # ftruncate
    82,  # rename
    83,  # mkdir
    84,  # rmdir
    85,  # creat
    86,  # link
    87,  # unlink
    88,  # symlink
    90,  # chmod
    91,  # fchmod
    92,  # chown
    93,  # fchown
    94,  # lchown
    132,  # utime
    133,  # mknod
    235,  # utimes
    258,  # mkdirat
    259,  # mknodat
    260,  # fchownat
    261,  # futimesat
    263,  # unlinkat
    264,  # renameat
    265,  # linkat
    266,  # symlinkat
    268,  # fchmodat
    280,  # utimensat
    288,  # accept4
    299,  # recvmmsg
    307,  # sendmmsg
    316,  # renameat2
    425,  # io_uring_setup (an I/O path that bypasses the checks above)
)


class _SockFilter(ctypes.Structure):
    """One classic-BPF instruction (``struct sock_filter``)."""

    _fields_ = [
        ("code", ctypes.c_uint16),
        ("jt", ctypes.c_uint8),
        ("jf", ctypes.c_uint8),
        ("k", ctypes.c_uint32),
    ]


class _SockFprog(ctypes.Structure):
    """A filter program (``struct sock_fprog``)."""

    _fields_ = [
        ("len", ctypes.c_uint16),
        ("filter", ctypes.POINTER(_SockFilter)),
    ]


def _arg_offset(index: int) -> int:
    return _ARGS_OFFSET + _ARG_SIZE * index


def _program() -> list[tuple[int, int, int, int]]:
    """Build the filter as ``(code, jt, jf, k)`` tuples.

    Layout: reject a foreign architecture first (clean ``EPERM``-free allow),
    then check ``open``/``openat`` flags, then the blanket syscall list.
    Jump offsets are relative instruction counts, matching ``sock_filter``.
    """
    program: list[tuple[int, int, int, int]] = [
        (_BPF_LD_W_ABS, 0, 0, _ARCH_OFFSET),
        (_BPF_JMP_JEQ_K, 1, 0, _AUDIT_ARCH_X86_64),
        (_BPF_RET_K, 0, 0, _RET_ALLOW),
        (_BPF_LD_W_ABS, 0, 0, _NR_OFFSET),
        # open(path, flags): flags are argument 1.
        (_BPF_JMP_JEQ_K, 0, 3, 2),
        (_BPF_LD_W_ABS, 0, 0, _arg_offset(1)),
        (_BPF_JMP_JSET_K, 0, 1, _WRITE_FLAGS),
        (_BPF_RET_K, 0, 0, _RET_EPERM),
        (_BPF_LD_W_ABS, 0, 0, _NR_OFFSET),
        # openat(dirfd, path, flags): flags are argument 2.
        (_BPF_JMP_JEQ_K, 0, 3, 257),
        (_BPF_LD_W_ABS, 0, 0, _arg_offset(2)),
        (_BPF_JMP_JSET_K, 0, 1, _WRITE_FLAGS),
        (_BPF_RET_K, 0, 0, _RET_EPERM),
        (_BPF_LD_W_ABS, 0, 0, _NR_OFFSET),
    ]
    for number in _DENIED_SYSCALLS:
        program.append((_BPF_JMP_JEQ_K, 0, 1, number))
        program.append((_BPF_RET_K, 0, 0, _RET_EPERM))
    program.append((_BPF_RET_K, 0, 0, _RET_ALLOW))
    return program


def install_guard() -> bool:
    """Activate the filter; ``False`` means it is not available here."""
    if _PLATFORM != "linux":
        return False
    if platform.machine().lower() not in {"x86_64", "amd64"}:
        return False

    instructions = [
        _SockFilter(code, jt, jf, k) for code, jt, jf, k in _program()
    ]
    filters = (_SockFilter * len(instructions))(*instructions)
    fprog = _SockFprog()
    fprog.len = len(instructions)
    fprog.filter = ctypes.cast(filters, ctypes.POINTER(_SockFilter))

    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.restype = ctypes.c_int
    prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    if prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        return False
    address = ctypes.addressof(fprog)
    installed: int = prctl(_PR_SET_SECCOMP, _SECCOMP_MODE_FILTER, address, 0, 0)
    return installed == 0
