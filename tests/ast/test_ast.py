"""AST tests: node hierarchy, structure and source locations."""

from __future__ import annotations

from al_arabiya.compiler.ast.nodes import (
    BinaryExpression,
    Identifier,
    Literal,
    PrintStatement,
    Program,
    iter_child_nodes,
)
from al_arabiya.compiler.ast.visitor import iter_walk
from al_arabiya.compiler.frontend import compile_source


def parse_ok(source: str) -> Program:
    result = compile_source(source, "test.arb")
    assert result.program is not None, [(d.code, d.message) for d in result.diagnostics]
    return result.program


def test_program_is_root_node():
    program = parse_ok('اطبع "مرحبا"')
    assert isinstance(program, Program)
    assert isinstance(program.body[0], PrintStatement)


def test_statement_hierarchy():
    program = parse_ok('خلي س = 1\nاطبع س')
    from al_arabiya.compiler.ast.nodes import Statement

    for statement in program.body:
        assert isinstance(statement, Statement)


def test_expression_hierarchy():
    program = parse_ok("اطبع 1 + اسم")
    expression = program.body[0].expression
    assert isinstance(expression, BinaryExpression)
    assert isinstance(expression.left, Literal)
    assert isinstance(expression.right, Identifier)


def test_every_node_has_span():
    program = parse_ok("خلي س = 1\nاطبع س + 2")
    for node in iter_walk(program):
        assert node.span is not None
        assert node.span.end.offset >= node.span.start.offset


def test_literal_span_covers_source_text():
    source = 'اطبع "مرحبا"'
    program = parse_ok(source)
    literal = program.body[0].expression
    covered = source[literal.span.start.offset : literal.span.end.offset]
    assert covered == '"مرحبا"'


def test_binary_span_covers_whole_expression():
    source = "اطبع 2 + 3"
    program = parse_ok(source)
    binary = program.body[0].expression
    covered = source[binary.span.start.offset : binary.span.end.offset]
    assert covered == "2 + 3"


def test_declaration_name_span_points_at_name():
    source = "خلي الاسم = 1"
    program = parse_ok(source)
    declaration = program.body[0]
    name_text = source[declaration.name_span.start.offset : declaration.name_span.end.offset]
    assert name_text == "الاسم"


def test_program_span_covers_input():
    source = "اطبع 1\nاطبع 2"
    program = parse_ok(source)
    covered = source[program.span.start.offset : program.span.end.offset]
    assert covered.strip() == source


def test_iter_child_nodes():
    program = parse_ok("اطبع 1 + 2")
    children = iter_child_nodes(program)
    assert len(children) == 1  # the PrintStatement
    binary = children[0].expression
    binary_children = iter_child_nodes(binary)
    assert len(binary_children) == 2  # left and right (operator is a str)


def test_iter_walk_reaches_every_node():
    program = parse_ok("خلي س = 1 + 2")
    kinds = [type(node).__name__ for node in iter_walk(program)]
    assert kinds == ["Program", "VariableDeclaration", "BinaryExpression", "Literal", "Literal"]
