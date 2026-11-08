"""Which of a function's locals are captured by a nested function.

A captured local must be boxed in a :class:`~al_arabiya.vm.chunk.Cell` so the
inner closure and the outer function share the same mutable storage.  The
analysis is intentionally liberal: it may mark a local captured even when an
inner function only shadows the name.  Over-capturing is always correct (the
shadowing inner function resolves to its own slot and never touches the outer
cell); it only costs an extra box.
"""

from __future__ import annotations

from al_arabiya.compiler.ast.nodes import (
    Assignment,
    ASTNode,
    ForEachStatement,
    FunctionDeclaration,
    Identifier,
    IfStatement,
    MapLiteral,
    RepeatStatement,
    Statement,
    TryStatement,
    VariableDeclaration,
    WhileStatement,
    iter_child_nodes,
)

__all__ = ["captured_local_names"]


def captured_local_names(parameters: list[str], body: list[Statement]) -> set[str]:
    """Local names of a function (params + its declarations) used inside any
    nested function."""
    locals_here = set(parameters)
    _collect_scope_bindings(body, locals_here)
    used_in_nested: set[str] = set()
    _collect_used_in_nested(body, used_in_nested)
    return locals_here & used_in_nested


def _all_child_nodes(node: ASTNode) -> list[ASTNode]:
    if isinstance(node, MapLiteral):
        children: list[ASTNode] = []
        for key, value in node.entries:
            children.append(key)
            children.append(value)
        return children
    return iter_child_nodes(node)


def _collect_scope_bindings(statements: list[Statement], out: set[str]) -> None:
    """Names bound at this scope (no block scoping), not entering nested funcs."""
    for statement in statements:
        if isinstance(statement, VariableDeclaration):
            out.add(statement.name)
        elif isinstance(statement, FunctionDeclaration):
            out.add(statement.name)  # the function name binds here; skip its body
        elif isinstance(statement, ForEachStatement):
            out.add(statement.variable)
            _collect_scope_bindings(statement.body, out)
        elif isinstance(statement, IfStatement):
            _collect_scope_bindings(statement.then_body, out)
            if statement.else_body is not None:
                _collect_scope_bindings(statement.else_body, out)
        elif isinstance(statement, (WhileStatement, RepeatStatement)):
            _collect_scope_bindings(statement.body, out)
        elif isinstance(statement, TryStatement):
            if statement.catch_name is not None:
                out.add(statement.catch_name)
            _collect_scope_bindings(statement.try_body, out)
            if statement.catch_body is not None:
                _collect_scope_bindings(statement.catch_body, out)
            if statement.finally_body is not None:
                _collect_scope_bindings(statement.finally_body, out)


def _collect_used_in_nested(statements: list[Statement], out: set[str]) -> None:
    """Names used anywhere inside a nested function (at any depth)."""
    for statement in statements:
        if isinstance(statement, FunctionDeclaration):
            _collect_all_used(statement.body, out)
        elif isinstance(statement, ForEachStatement):
            _collect_used_in_nested(statement.body, out)
        elif isinstance(statement, IfStatement):
            _collect_used_in_nested(statement.then_body, out)
            if statement.else_body is not None:
                _collect_used_in_nested(statement.else_body, out)
        elif isinstance(statement, (WhileStatement, RepeatStatement)):
            _collect_used_in_nested(statement.body, out)
        elif isinstance(statement, TryStatement):
            _collect_used_in_nested(statement.try_body, out)
            if statement.catch_body is not None:
                _collect_used_in_nested(statement.catch_body, out)
            if statement.finally_body is not None:
                _collect_used_in_nested(statement.finally_body, out)


def _collect_all_used(statements: list[Statement], out: set[str]) -> None:
    for statement in statements:
        _collect_used_node(statement, out)


def _collect_used_node(node: ASTNode, out: set[str]) -> None:
    if isinstance(node, Identifier):
        out.add(node.name)
    elif isinstance(node, Assignment):
        out.add(node.target)
    for child in _all_child_nodes(node):
        _collect_used_node(child, out)
