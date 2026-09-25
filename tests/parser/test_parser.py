"""Parser tests: statements, expressions, precedence and syntax errors."""

from __future__ import annotations

from al_arabiya.compiler.ast.nodes import (
    BinaryExpression,
    Identifier,
    IfStatement,
    Literal,
    PrintStatement,
    RepeatStatement,
    UnaryExpression,
    VariableDeclaration,
    WhileStatement,
)
from al_arabiya.compiler.diagnostics.errors import ErrorCode
from al_arabiya.compiler.frontend import compile_source


def parse(source: str):
    result = compile_source(source, "test.arb")
    assert result.program is not None, [
        (d.code, d.message) for d in result.diagnostics
    ]
    return result.program


def parse_errors(source: str) -> list[str]:
    result = compile_source(source, "test.arb")
    return [d.code for d in result.diagnostics if d.is_error]


# ------------------------------------------------------------- statements


def test_print_statement():
    program = parse('اطبع "أهلا"')
    statement = program.body[0]
    assert isinstance(statement, PrintStatement)
    assert isinstance(statement.expression, Literal)
    assert statement.expression.value == "أهلا"


def test_variable_declaration():
    program = parse('خلي الاسم = "أحمد"')
    statement = program.body[0]
    assert isinstance(statement, VariableDeclaration)
    assert statement.name == "الاسم"
    assert isinstance(statement.initializer, Literal)


def test_declaration_of_number():
    statement = parse("خلي العمر = 25").body[0]
    assert isinstance(statement, VariableDeclaration)
    assert statement.initializer.value == 25


def test_reassignment():
    program = parse("س = 5")
    from al_arabiya.compiler.ast.nodes import Assignment

    statement = program.body[0]
    assert isinstance(statement, Assignment)
    assert statement.target == "س"
    assert statement.value.value == 5


def test_if_statement():
    program = parse("لو صح\n    اطبع 1\nخلاص")
    statement = program.body[0]
    assert isinstance(statement, IfStatement)
    assert len(statement.then_body) == 1
    assert statement.else_body is None


def test_if_else_statement():
    program = parse("لو صح\n    اطبع 1\nغير كده\n    اطبع 2\nخلاص")
    statement = program.body[0]
    assert isinstance(statement, IfStatement)
    assert statement.else_body is not None
    assert len(statement.else_body) == 1


def test_repeat_statement():
    program = parse("كرر 3 مرات\n    اطبع 1\nخلاص")
    statement = program.body[0]
    assert isinstance(statement, RepeatStatement)
    assert statement.count.value == 3


def test_repeat_with_once():
    program = parse("كرر 1 مرة\n    اطبع 1\nخلاص")
    assert isinstance(program.body[0], RepeatStatement)


def test_while_statement():
    program = parse("طالما صح\n    اطبع 1\n    خلي ك = 1\nخلاص")
    statement = program.body[0]
    assert isinstance(statement, WhileStatement)
    assert len(statement.body) == 2


def test_nested_blocks():
    program = parse(
        "لو صح\n    كرر 2 مرات\n        اطبع 1\n    خلاص\nخلاص"
    )
    outer = program.body[0]
    assert isinstance(outer, IfStatement)
    assert isinstance(outer.then_body[0], RepeatStatement)


def test_multiple_statements():
    program = parse('اطبع 1\nخلي س = 2\nس = 3')
    assert len(program.body) == 3


# ------------------------------------------------------------- expressions


def test_multiplication_binds_tighter():
    expression = parse("اطبع 2 + 3 * 4").body[0].expression
    assert isinstance(expression, BinaryExpression)
    assert expression.operator == "+"
    assert isinstance(expression.right, BinaryExpression)
    assert expression.right.operator == "*"


def test_left_associative_subtraction():
    expression = parse("اطبع 10 - 3 - 2").body[0].expression
    assert isinstance(expression, BinaryExpression)
    assert expression.operator == "-"
    assert isinstance(expression.left, BinaryExpression)


def test_parentheses_override_precedence():
    expression = parse("اطبع (2 + 3) * 4").body[0].expression
    assert expression.operator == "*"
    assert isinstance(expression.left, BinaryExpression)
    assert expression.left.operator == "+"


def test_word_operators():
    expression = parse("اطبع 5 زائد 3 ناقص 2").body[0].expression
    assert expression.operator == "-"
    assert expression.left.operator == "+"


def test_arabic_multiplication_words():
    expression = parse("اطبع 7 في 6 على 2").body[0].expression
    assert expression.operator == "/"
    assert expression.left.operator == "*"


def test_arabic_comparison_words():
    expression = parse("اطبع س أكبر من 5").body[0].expression
    assert expression.operator == ">"


def test_arabic_greater_or_equal():
    expression = parse("اطبع س أكبر أو يساوي 5").body[0].expression
    assert expression.operator == ">="


def test_arabic_less_or_equal():
    expression = parse("اطبع س أصغر أو يساوي 5").body[0].expression
    assert expression.operator == "<="


def test_arabic_not_equal():
    expression = parse("اطبع س مش يساوي 5").body[0].expression
    assert expression.operator == "!="


def test_arabic_equal_word():
    expression = parse("اطبع س يساوي 5").body[0].expression
    assert expression.operator == "=="


def test_symbolic_comparisons():
    for symbol in (">", "<", ">=", "<=", "==", "!="):
        expression = parse(f"اطبع 1 {symbol} 2").body[0].expression
        assert expression.operator == symbol


def test_logical_and_binds_tighter_than_or():
    expression = parse("اطبع صح أو غلط و غلط").body[0].expression
    assert expression.operator == "أو"
    assert isinstance(expression.right, BinaryExpression)
    assert expression.right.operator == "و"


def test_unary_minus():
    expression = parse("اطبع -5 + 3").body[0].expression
    assert expression.operator == "+"
    assert isinstance(expression.left, UnaryExpression)
    assert expression.left.operand.value == 5


def test_unary_word_minus():
    expression = parse("اطبع ناقص 5").body[0].expression
    assert isinstance(expression, UnaryExpression)


def test_boolean_literals():
    program = parse("خلي شغال = صح\nخلي تاني = غلط")
    assert program.body[0].initializer.value is True
    assert program.body[1].initializer.value is False


def test_identifier_expression():
    expression = parse("اطبع الاسم").body[0].expression
    assert isinstance(expression, Identifier)
    assert expression.name == "الاسم"


def test_percent_operator():
    expression = parse("اطبع 7 % 3").body[0].expression
    assert expression.operator == "%"


def test_deeply_nested_expression():
    expression = parse("اطبع (1 + 2) * (3 - 1) / 2").body[0].expression
    assert expression.operator == "/"
    assert expression.left.operator == "*"


# ------------------------------------------------------------ syntax errors


def test_missing_block_end():
    codes = parse_errors("لو صح\n    اطبع 1")
    assert ErrorCode.MISSING_BLOCK_END in codes


def test_missing_equals_in_declaration():
    codes = parse_errors("خلي س 5")
    assert ErrorCode.EXPECTED_TOKEN in codes


def test_missing_identifier_after_let():
    codes = parse_errors("خلي = 5")
    assert ErrorCode.EXPECTED_IDENTIFIER in codes


def test_unknown_statement():
    codes = parse_errors("}" )
    assert ErrorCode.UNEXPECTED_TOKEN in codes


def test_missing_newline_between_statements():
    codes = parse_errors("اطبع 1 اطبع 2")
    assert ErrorCode.EXPECTED_NEWLINE in codes


def test_greater_without_from():
    codes = parse_errors("اطبع س أكبر 5")
    assert ErrorCode.EXPECTED_TOKEN in codes


def test_not_without_equal():
    codes = parse_errors("اطبع س مش 5")
    assert ErrorCode.EXPECTED_TOKEN in codes


def test_repeat_without_times_word():
    codes = parse_errors("كرر 3\n    اطبع 1\nخلاص")
    assert ErrorCode.EXPECTED_TOKEN in codes


def test_else_without_that():
    codes = parse_errors("لو صح\n    اطبع 1\nغير\n    اطبع 2\nخلاص")
    assert ErrorCode.EXPECTED_TOKEN in codes


def test_bare_expression_is_not_a_statement():
    codes = parse_errors("1 + 2")
    assert ErrorCode.UNEXPECTED_TOKEN in codes


def test_incomplete_expression_reports_eof():
    codes = parse_errors("اطبع")
    assert ErrorCode.UNEXPECTED_EOF in codes


def test_multiple_errors_are_collected():
    result = compile_source("}\nخلي س 5\n@")
    codes = [d.code for d in result.diagnostics if d.is_error]
    assert len(codes) >= 3


def test_error_carries_position():
    result = compile_source("اطبع 1\nخلي = 5")
    error = next(d for d in result.diagnostics if d.is_error)
    assert error.span.start.line == 2
    assert error.span.start.column == 5
