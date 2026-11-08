"""Check that relative links in the project's Markdown files resolve.

No third-party dependency: the docs are local, so a link only has to point at a
file that exists.  External links, anchors and mailto links are skipped (the CI
sandbox has no network, and anchors are validated by the docs build we do not
have yet).

Usage::

    python -m tools.check_links

Exits ``1`` when a target is missing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
_TARGETS = ("README.md", "CONTRIBUTING.md", "SECURITY.md")
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_FENCE = re.compile(r"^\s*(```|~~~)")


def _markdown_files() -> list[Path]:
    files = [ROOT / name for name in _TARGETS if (ROOT / name).is_file()]
    files.extend(sorted((ROOT / "docs").rglob("*.md")))
    return files


def _links(text: str) -> list[str]:
    """Link targets outside fenced code blocks."""
    found: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        found.extend(_LINK.findall(line))
    return found


def broken_links(root: Path = ROOT) -> list[tuple[Path, str]]:
    broken: list[tuple[Path, str]] = []
    for path in _markdown_files():
        for target in _links(path.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative = unquote(target.split("#", 1)[0])
            if not relative:
                continue
            if not (path.parent / relative).exists():
                broken.append((path, target))
    return broken


def _use_utf8_output() -> None:
    """GitHub's Windows runners default to cp1252, which cannot encode Arabic."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def main() -> int:
    _use_utf8_output()
    broken = broken_links()
    if not broken:
        print("كل الروابط النسبية سليمة.")
        return 0
    for path, target in broken:
        print(f"❌ {path.relative_to(ROOT)} → {target}")
    print(f"{len(broken)} رابط مكسور.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
