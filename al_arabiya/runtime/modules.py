"""Module loading for ``استورد`` (import).

A module is just another ``.arb`` file.  It is compiled and executed once in
its own global scope; the names it defines at the top level become its exports.
Results are cached by absolute path and in-progress loads are tracked so import
cycles fail with a clear diagnostic instead of recursing forever.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from al_arabiya.compiler.diagnostics.diagnostics import Diagnostic, Severity
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.compiler.lexer.positions import Span
from al_arabiya.runtime.builtins import BUILTINS, make_global_env
from al_arabiya.runtime.interpreter.environment import Environment
from al_arabiya.runtime.values import Value

__all__ = ["ModuleLoader", "module_exports"]

_BUILTIN_NAMES = frozenset(builtin.name for builtin in BUILTINS)


def module_exports(module_env: Environment) -> dict[str, Value]:
    """The names a module makes available (its top-level defs, minus builtins)."""
    return {
        name: value
        for name, value in module_env.local_items().items()
        if name not in _BUILTIN_NAMES
    }


class ModuleLoader:
    """Loads, runs and caches imported modules."""

    def __init__(self, write: Callable[[str], None]) -> None:
        self._write = write
        self._cache: dict[str, Environment] = {}
        self._loading: set[str] = set()

    def locate(self, name: str, base_dir: str) -> str:
        """Resolve an import name to an absolute path.

        A sibling ``.arb`` file wins; otherwise an installed package in the
        nearest ``حزم/`` folder found by walking up from ``base_dir`` (so a
        vendored package can import its own dependencies from the project's
        ``حزم/``).  Returns the sibling candidate when nothing exists, so
        :meth:`load` reports the usual MODULE_NOT_FOUND.
        """
        raw = name if name.endswith(".arb") else name + ".arb"
        direct = os.path.normpath(os.path.join(base_dir, raw))
        if os.path.isfile(direct):
            return direct
        bare = name[:-4] if name.endswith(".arb") else name
        for ancestor in self._ancestors(base_dir):
            packages = os.path.join(ancestor, "حزم")
            for candidate in (
                os.path.join(packages, raw),
                os.path.join(packages, bare, "رئيسي.arb"),
                os.path.join(packages, bare, raw),
            ):
                normalized = os.path.normpath(candidate)
                if os.path.isfile(normalized):
                    return normalized
        return direct

    @staticmethod
    def _ancestors(start: str) -> list[str]:
        current = os.path.abspath(start)
        chain = [current]
        while True:
            parent = os.path.dirname(current)
            if parent == current:
                break
            chain.append(parent)
            current = parent
        return chain

    def load(self, abs_path: str, span: Span) -> Environment:
        if abs_path in self._cache:
            return self._cache[abs_path]
        if abs_path in self._loading:
            raise self._error(
                ErrorCode.IMPORT_ERROR,
                f"استيراد دائري: الملف '{os.path.basename(abs_path)}' بيستورد نفسه",
                span,
                "شيل الاستيراد الدائري بين الملفات",
            )
        try:
            with open(abs_path, encoding="utf-8-sig") as handle:
                text = handle.read()
        except OSError:
            raise self._error(
                ErrorCode.MODULE_NOT_FOUND,
                f"مش لاقي الملف: {abs_path}",
                span,
                "تأكد إن اسم الملف ومكانه صح",
            ) from None

        result = compile_source(text, abs_path)
        if result.program is None:
            first = next((d for d in result.diagnostics if d.is_error), None)
            detail = first.message if first is not None else "خطأ في الترجمة"
            raise self._error(
                ErrorCode.IMPORT_ERROR,
                f"فيه خطأ في الملف المستورد '{os.path.basename(abs_path)}': {detail}",
                span,
                "صلّح أخطاء الملف المستورد الأول",
            )

        # Imported lazily to avoid an import cycle (interpreter imports this module).
        from al_arabiya.runtime.interpreter.interpreter import Interpreter

        module_env = make_global_env()
        self._loading.add(abs_path)
        try:
            interpreter = Interpreter(
                environment=module_env,
                write=self._write,
                base_dir=os.path.dirname(abs_path),
                loader=self,
            )
            interpreter.run(result.program)
        finally:
            self._loading.discard(abs_path)

        self._cache[abs_path] = module_env
        return module_env

    @staticmethod
    def _error(
        code: ErrorCode, message: str, span: Span, suggestion: str
    ) -> ArabiyaRuntimeError:
        return ArabiyaRuntimeError(
            Diagnostic(
                code=code,
                severity=Severity.ERROR,
                message=message,
                span=span,
                suggestion=suggestion,
            )
        )
