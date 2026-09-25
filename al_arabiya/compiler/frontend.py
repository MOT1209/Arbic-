"""The compiler frontend facade: source text → tokens → AST.

Nothing in this module executes anything; it only reports diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass

from al_arabiya.compiler.ast.nodes import Program
from al_arabiya.compiler.diagnostics.diagnostics import Diagnostic, DiagnosticBag
from al_arabiya.compiler.diagnostics.errors import DiagnosticError
from al_arabiya.compiler.diagnostics.source import SourceFile
from al_arabiya.compiler.lexer.lexer import Lexer
from al_arabiya.compiler.parser.parser import Parser

__all__ = ["FrontendResult", "compile_source", "compile_text"]


@dataclass(frozen=True, slots=True)
class FrontendResult:
    """Outcome of a compilation: the AST (if clean) plus all diagnostics."""

    program: Program | None
    diagnostics: tuple[Diagnostic, ...]
    source: SourceFile

    @property
    def ok(self) -> bool:
        return self.program is not None and not any(d.is_error for d in self.diagnostics)

    @property
    def has_errors(self) -> bool:
        return any(d.is_error for d in self.diagnostics)

    @property
    def has_warnings(self) -> bool:
        return any(not d.is_error for d in self.diagnostics)


def compile_source(text: str, filename: str = "<input>") -> FrontendResult:
    """Run the full frontend over ``text``."""
    source = SourceFile(filename, text)
    bag = DiagnosticBag()
    program: Program | None = None
    try:
        tokens = Lexer(text, bag).tokenize()
        # parse even when the lexer recovered from errors: users get every
        # problem in one pass instead of one layer at a time
        program = Parser(tokens, bag).parse_program()
    except DiagnosticError as exc:  # defensive: collect, never crash
        bag.add(exc.diagnostic)
        program = None
    if bag.has_errors:
        program = None
    return FrontendResult(program, tuple(bag.sorted()), source)


def compile_text(text: str) -> Program:
    """Compile ``text`` and raise the first error (handy in tests/tools)."""
    result = compile_source(text)
    if not result.ok or result.program is None:
        first = next((d for d in result.diagnostics if d.is_error), None)
        if first is not None:
            from al_arabiya.compiler.diagnostics.errors import DiagnosticError as _DE

            raise _DE(first)
        raise ValueError("compilation failed without diagnostics")
    return result.program
