"""An offline, file-based package manager for AlArabiya.

No network and no central registry: a *registry* is just a directory laid out
as ``<registry>/<name>/<version>/`` holding each package's ``.arb`` files (and
an optional ``حزمة.json`` for its own dependencies).  :func:`install` resolves
the dependency graph (SemVer-lite), copies each resolved package into the
project's ``حزم/`` folder and writes a lockfile.
"""

from __future__ import annotations

import json
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


def _parse_manifest_data(data: object, source: str) -> Manifest:
    if not isinstance(data, dict):
        raise PackageError(f"ملف الحزمة '{source}' لازم يكون كائن JSON")
    name = data.get(_KEY_NAME)
    if not isinstance(name, str) or not name:
        raise PackageError(f"ملف الحزمة '{source}' محتاج '{_KEY_NAME}' نصي")
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
        dependencies[dep_name] = constraint
    return Manifest(name, Version.parse(raw_version), dependencies)


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
        package_dir = self.root / name
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
        return self.root / name / str(version)

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


def install(project_dir: Path, registry: Registry) -> dict[str, Version]:
    """Resolve and vendor the project's dependencies into ``حزم/``.

    Returns the resolved name→version map and writes the lockfile.
    """
    manifest = read_manifest(project_dir / MANIFEST_NAME)
    resolved = resolve(manifest, registry)

    packages_dir = project_dir / PACKAGES_DIR
    for name, version in resolved.items():
        source = registry.path(name, version)
        if not source.is_dir():
            raise PackageError(f"الحزمة '{name}' {version} مش موجودة في السجلّ")
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
