"""Kernel-level sandbox guard (x86_64 Linux seccomp).

The filter is installed inside a throwaway process, so these tests observe the
real kernel decision instead of trusting the code that built the filter.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest

from al_arabiya.sandbox import SandboxLimits, run_sandboxed

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or platform.machine().lower() not in {"x86_64", "amd64"},
    reason="the OS guard is implemented for x86_64 Linux only",
)

ROOT = Path(__file__).resolve().parents[2]

PROBE = '''
import socket
import sys

from al_arabiya.sandbox.limits_linux import install_guard

if not install_guard():
    print("guard-unavailable")
    raise SystemExit(0)

results = []
try:
    socket.socket()
except PermissionError:
    results.append("net")
try:
    with open(sys.argv[1] + ".new", "w", encoding="utf-8") as handle:
        handle.write("x")
except PermissionError:
    results.append("write")
with open(sys.argv[1], encoding="utf-8") as handle:
    handle.read()
results.append("read")
print(",".join(results))
'''


def test_guard_denies_network_and_writes_but_allows_reads(tmp_path: Path) -> None:
    script = tmp_path / "probe.py"
    script.write_text(PROBE, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}

    completed = subprocess.run(
        [sys.executable, "-s", str(script), str(script)],
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "net,write,read"
    assert not (tmp_path / "probe.py.new").exists()


def test_sandboxed_run_uses_the_guard(tmp_path: Path) -> None:
    program = tmp_path / "main.arb"
    program.write_text('اطبع "من العازل"\n', encoding="utf-8")

    result = run_sandboxed(program, SandboxLimits(timeout=20))

    assert result.exit_code == 0
    assert "من العازل" in result.stdout
    assert "مش متفعّل" not in result.stderr
