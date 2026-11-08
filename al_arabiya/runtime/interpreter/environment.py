"""Environment: nested scope chain for the interpreter."""

from __future__ import annotations

from al_arabiya.compiler.diagnostics.diagnostics import Diagnostic, Severity
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.lexer.positions import Span
from al_arabiya.runtime.values import Value

__all__ = ["Environment", "Value"]


class Environment:
    """A scope holding variables, optionally chained to a parent scope.

    Phase 1 uses a single global scope (matching the original Masry
    semantics), but the chain is already here so functions/modules can
    introduce nested scopes later without touching the interpreter.
    """

    def __init__(self, parent: Environment | None = None) -> None:
        self.parent = parent
        self._values: dict[str, Value] = {}

    def child(self) -> Environment:
        """Create a nested scope inside this one."""
        return Environment(parent=self)

    def define(self, name: str, value: Value) -> None:
        self._values[name] = value

    def has(self, name: str) -> bool:
        return self._resolve(name) is not None

    def local_names(self) -> list[str]:
        """Names defined directly in this scope (not parents)."""
        return list(self._values)

    def local_items(self) -> dict[str, Value]:
        """A copy of the name→value bindings defined directly in this scope."""
        return dict(self._values)

    def get(self, name: str, span: Span) -> Value:
        scope = self._resolve(name)
        if scope is None:
            raise ArabiyaRuntimeError(self._undefined(name, span))
        return scope._values[name]

    def assign(self, name: str, value: Value, span: Span) -> None:
        scope = self._resolve(name)
        if scope is None:
            raise ArabiyaRuntimeError(self._undefined(name, span))
        scope._values[name] = value

    def _resolve(self, name: str) -> Environment | None:
        scope: Environment | None = self
        while scope is not None:
            if name in scope._values:
                return scope
            scope = scope.parent
        return None

    @staticmethod
    def _undefined(name: str, span: Span) -> Diagnostic:
        return Diagnostic(
            code=ErrorCode.UNDEFINED_VARIABLE,
            severity=Severity.ERROR,
            message=f"المتغير '{name}' مش معرّف",
            span=span,
            suggestion=f"اكتب 'خلي {name} = ...' الأول",
        )
