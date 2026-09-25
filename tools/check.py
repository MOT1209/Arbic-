"""Run the full quality gate: pytest + ruff + mypy.

Usage:
    python tools/check.py
"""

from __future__ import annotations

import subprocess
import sys

CHECKS = [
    ("ruff", [sys.executable, "-m", "ruff", "check", "."]),
    ("mypy", [sys.executable, "-m", "mypy"]),
    ("pytest", [sys.executable, "-m", "pytest"]),
]


def main() -> int:
    failures: list[str] = []
    for name, command in CHECKS:
        print(f"\n=== {name} ===")
        try:
            result = subprocess.run(command, check=False)
        except OSError as exc:
            print(f"could not run {name}: {exc}")
            failures.append(name)
            continue
        if result.returncode != 0:
            failures.append(name)
    print("\n=== summary ===")
    if failures:
        print("FAILED:", ", ".join(failures))
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
