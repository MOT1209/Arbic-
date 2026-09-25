"""AlArabiya (العربية) — a programming language with Arabic syntax.

The package is split into three layers:

- :mod:`al_arabiya.compiler` — the frontend: lexer, parser, AST, diagnostics.
- :mod:`al_arabiya.runtime`  — the backend: environment + tree-walking interpreter.
- :mod:`al_arabiya.cli`      — the ``arabic`` command line interface.
"""

__version__ = "0.1.0"
LANGUAGE_NAME = "العربية"
PROJECT_NAME = "AlArabiya"

__all__ = ["LANGUAGE_NAME", "PROJECT_NAME", "__version__"]
