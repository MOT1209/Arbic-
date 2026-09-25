"""Visitor utilities for walking the AlArabiya AST."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from al_arabiya.compiler.ast.nodes import ASTNode, iter_child_nodes

__all__ = ["ASTVisitor", "iter_walk"]


def _method_name(node: ASTNode) -> str:
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", type(node).__name__).lower()
    return f"visit_{snake}"


class ASTVisitor:
    """Dispatch visitor: ``visit_<snake_case_class_name>`` per node type.

    Subclasses override the ``visit_*`` methods they care about.  The
    interpreter is one such visitor; future backends (bytecode emitter,
    formatter, LSP indexer) will be others.
    """

    def visit(self, node: ASTNode) -> Any:
        method = getattr(self, _method_name(node), None)
        if method is None:
            raise NotImplementedError(
                f"{type(self).__name__} has no handler for {type(node).__name__}"
            )
        return method(node)

    def generic_visit(self, node: ASTNode) -> Any:
        """Fallback: visit all children (override to customise traversal)."""
        result: Any = None
        for child in iter_child_nodes(node):
            result = self.visit(child)
        return result


def iter_walk(node: ASTNode) -> Iterator[ASTNode]:
    """Yield ``node`` and all of its descendants, depth-first."""
    yield node
    for child in iter_child_nodes(node):
        yield from iter_walk(child)
