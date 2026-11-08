"""An offline, file-based package manager for AlArabiya.

No network and no central registry: a *registry* is just a directory laid out
as ``<registry>/<name>/<version>/`` holding each package's ``.arb`` files (and
an optional ``حزمة.json`` for its own dependencies).  :func:`install` resolves
the dependency graph (SemVer-lite), copies each resolved package into the
project's ``حزم/`` folder and writes a lockfile.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "MANIFEST_NAME",
    "LOCKFILE_NAME",
    "PACKAGES_DIR",
    "Manifest",
    "PackageError",
    "Registry",
    "Version",
    "install",
    "read_manifest",
    "resolve",
    "satisfies",
]

MANIFEST_NAME = "حزمة.json"
LOCKFILE_NAME = "حزمة-قفل.json"
PACKAGES_DIR = "حزم"

# manifest keys (Arabic)
_KEY_NAME = "الاسم"
_KEY_VERSION = "الإصدار"
_KEY_DEPS = "الاعتماديات"
_KEY_HASHES = "البصمات"
_HASH_LENGTH = 64


class PackageError(Exception):
    """A package resolution or installation problem (reported by the CLI)."""


@dataclass(frozen=True, order=True)
class Version:
    """A small SemVer triple (major.minor.patch)."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> Version:
        parts = text.strip().split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise PackageError(f"إصدار غير صالح: '{text}' (المتوقع x.y.z)")
        major, minor, patch = (int(part) for part in parts)
        return cls(major, minor, patch)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def satisfies(version: Version, constraint: str) -> bool:
    """Does ``version`` satisfy ``constraint``?

    Supported: ``*`` / ``أي`` (any), ``^x.y.z`` (same major, >= the version),
    and an exact ``x.y.z``.
    """
    constraint = constraint.strip()
    if constraint in ("*", "أي"):
        return True
    if constraint.startswith("^"):
        base = Version.parse(constraint[1:])
        return version.major == base.major and version >= base
    return version == Version.parse(constraint)


@dataclass
class Manifest:
    """A parsed ``حزمة.json``."""

    name: str
    version: Version
    dependencies: dict[str, str] = field(default_factory=dict)
    #: optional ``file -> sha256`` map, checked before anything is installed
    hashes: dict[str, str] = field(default_factory=dict)


def _validate_name(name: str, source: str) -> str:
    """Reject names that could point outside a package directory."""
    if (
        not name
        or name in (".", "..")
        or name[0] in "/\\"
        or any(ch in name for ch in "/\\:")
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)
    ):
        raise PackageError(f"اسم حزمة غير صالح في '{source}': '{name}'")
    return name


def _validate_relative_path(relative: str, source: str) -> str:
    """A checksum key must be a plain path inside the package directory."""
    pure = Path(relative)
    if (
        not relative
        or pure.is_absolute()
        or any(part in ("..",) for part in pure.parts)
        or relative.startswith(("/", "\\"))
    ):
        raise PackageError(f"مسار غير صالح في '{_KEY_HASHES}' بـ '{source}': '{relative}'")
    return relative


def _parse_manifest_data(data: object, source: str) -> Manifest:
    if not isinstance(data, dict):
        raise PackageError(f"ملف الحزمة '{source}' لازم يكون كائن JSON")
    name = data.get(_KEY_NAME)
    if not isinstance(name, str) or not name:
        raise PackageError(f"ملف الحزمة '{source}' محتاج '{_KEY_NAME}' نصي")
    _validate_name(name, source)
    raw_version = data.get(_KEY_VERSION, "0.0.0")
    if not isinstance(raw_version, str):
        raise PackageError(f"'{_KEY_VERSION}' في '{source}' لازم يكون نص")
    raw_deps = data.get(_KEY_DEPS, {})
    if not isinstance(raw_deps, dict):
        raise PackageError(f"'{_KEY_DEPS}' في '{source}' لازم يكون كائن")
    dependencies: dict[str, str] = {}
    for dep_name, constraint in raw_deps.items():
        if not isinstance(dep_name, str) or not isinstance(constraint, str):
            raise PackageError(f"اعتماد غير صالح في '{source}'")
        dependencies[_validate_name(dep_name, source)] = constraint

    raw_hashes = data.get(_KEY_HASHES, {})
    if not isinstance(raw_hashes, dict):
        raise PackageError(f"'{_KEY_HASHES}' في '{source}' لازم يكون كائن")
    hashes: dict[str, str] = {}
    for relative, digest in raw_hashes.items():
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise PackageError(f"بصمة غير صالحة في '{source}'")
        if len(digest) != _HASH_LENGTH:
            raise PackageError(
                f"بصمة '{relative}' في '{source}' لازم تكون sha256 (64 حرفًا hex)"
            )
        hashes[_validate_relative_path(relative, source)] = digest.lower()
    return Manifest(name, Version.parse(raw_version), dependencies, hashes)


def read_manifest(path: Path) -> Manifest:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PackageError(f"مش لاقي ملف الحزمة: {path}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PackageError(f"ملف الحزمة '{path}' فيه JSON غير صالح: {exc}") from exc
    return _parse_manifest_data(data, str(path))


class Registry:
    """A directory of packages: ``<root>/<name>/<version>/``."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def available_versions(self, name: str) -> list[Version]:
        package_dir = self.root / _validate_name(name, str(self.root))
        if not package_dir.is_dir():
            return []
        versions: list[Version] = []
        for child in package_dir.iterdir():
            if child.is_dir():
                try:
                    versions.append(Version.parse(child.name))
                except PackageError:
                    continue
        return sorted(versions)

    def path(self, name: str, version: Version) -> Path:
        return self.root / _validate_name(name, str(self.root)) / str(version)

    def manifest(self, name: str, version: Version) -> Manifest | None:
        manifest_path = self.path(name, version) / MANIFEST_NAME
        if manifest_path.is_file():
            return read_manifest(manifest_path)
        return None


def resolve(manifest: Manifest, registry: Registry) -> dict[str, Version]:
    """Resolve the full dependency set to concrete versions.

    Highest-satisfying version wins.  Raises :class:`PackageError` on an
    unsatisfiable constraint, a version conflict, or a dependency cycle.
    """
    resolved: dict[str, Version] = {}

    def visit(dependencies: dict[str, str], chain: tuple[str, ...]) -> None:
        for name, constraint in dependencies.items():
            candidates = [
                version
                for version in registry.available_versions(name)
                if satisfies(version, constraint)
            ]
            if not candidates:
                raise PackageError(
                    f"مفيش إصدار من الحزمة '{name}' يطابق '{constraint}'"
                )
            chosen = max(candidates)
            if name in chain:
                cycle = " → ".join([*chain, name])
                raise PackageError(f"اعتماد دائري بين الحزم: {cycle}")
            if name in resolved:
                if not satisfies(resolved[name], constraint):
                    raise PackageError(
                        f"تعارض في إصدارات '{name}': "
                        f"{resolved[name]} لا يطابق '{constraint}'"
                    )
                continue
            resolved[name] = chosen
            sub = registry.manifest(name, chosen)
            if sub is not None:
                visit(sub.dependencies, (*chain, name))

    visit(manifest.dependencies, ())
    return resolved


def _reject_symlinks(source: Path, name: str) -> None:
    """Refuse a package tree that contains symlinks.

    ``copytree`` would otherwise copy the link target's content (or, with
    ``symlinks=True``, plant a link that escapes ``حزم/`` when read later), so a
    registry entry cannot vouch for paths outside itself.
    """
    if source.is_symlink():
        raise PackageError(f"الحزمة '{name}' نفسها symlink — مرفوضة")
    for root, directories, files in os.walk(source, followlinks=False):
        for entry in (*directories, *files):
            candidate = os.path.join(root, entry)
            if os.path.islink(candidate):
                relative = os.path.relpath(candidate, source)
                raise PackageError(f"الحزمة '{name}' فيها symlink: '{relative}'")


def _verify_hashes(source: Path, manifest: Manifest | None, name: str) -> None:
    """Check the optional ``البصمات`` map before anything is written."""
    if manifest is None or not manifest.hashes:
        return
    for relative, expected in manifest.hashes.items():
        target = source / relative
        if not target.is_file():
            raise PackageError(
                f"ملف البصمة '{relative}' مش موجود في الحزمة '{name}'"
            )
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            raise PackageError(
                f"بصمة '{relative}' في الحزمة '{name}' مش مطابقة "
                "(الملف اتغيّر بعد النشر)"
            )


def install(project_dir: Path, registry: Registry) -> dict[str, Version]:
    """Resolve and vendor the project's dependencies into ``حزم/``.

    Every source package is inspected (symlinks, hashes) *before* the first
    ``حزم/<name>`` folder is removed, so a broken registry entry cannot destroy
    an existing installation.  Returns the resolved name→version map and writes
    the lockfile.
    """
    manifest = read_manifest(project_dir / MANIFEST_NAME)
    resolved = resolve(manifest, registry)

    plan: list[tuple[str, Path]] = []
    for name, version in resolved.items():
        source = registry.path(name, version)
        if not source.is_dir():
            raise PackageError(f"الحزمة '{name}' {version} مش موجودة في السجلّ")
        _reject_symlinks(source, name)
        _verify_hashes(source, registry.manifest(name, version), name)
        plan.append((name, source))

    packages_dir = project_dir / PACKAGES_DIR
    for name, source in plan:
        destination = packages_dir / name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)

    _write_lockfile(project_dir, resolved)
    return resolved


def _write_lockfile(project_dir: Path, resolved: dict[str, Version]) -> None:
    payload = {_KEY_DEPS: {name: str(version) for name, version in resolved.items()}}
    (project_dir / LOCKFILE_NAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def read_lockfile(project_dir: Path) -> dict[str, str]:
    lock_path = project_dir / LOCKFILE_NAME
    if not lock_path.is_file():
        return {}
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    deps = data.get(_KEY_DEPS, {}) if isinstance(data, dict) else {}
    return {k: v for k, v in deps.items() if isinstance(k, str) and isinstance(v, str)}
