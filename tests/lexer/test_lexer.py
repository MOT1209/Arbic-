"""Lexer tests: identifiers, numbers, strings, operators, positions, errors."""

from __future__ import annotations

from al_arabiya.compiler.diagnostics.errors import ErrorCode
from al_arabiya.compiler.lexer.tokens import KEYWORDS, TokenType

# ------------------------------------------------------------- identifiers


def test_arabic_identifier(lex):
    tokens = lex("العمر")
    assert tokens[0].type is TokenType.IDENTIFIER
    assert tokens[0].value == "العمر"


def test_english_identifier(lex):
    tokens = lex("result_count")
    assert tokens[0].type is TokenType.IDENTIFIER
    assert tokens[0].value == "result_count"


def test_mixed_identifiers(lex):
    tokens = lex("اسم_1 name2")
    assert [t.type for t in tokens[:2]] == [TokenType.IDENTIFIER, TokenType.IDENTIFIER]
    assert [t.value for t in tokens[:2]] == ["اسم_1", "name2"]


def test_keyword_like_word_is_identifier(lex):
    tokens = lex("أكبرمن")
    assert tokens[0].type is TokenType.IDENTIFIER


# ----------------------------------------------------------------- keywords


def test_every_keyword_maps_to_its_token_type(lex):
    for word, token_type in KEYWORDS.items():
        tokens = lex(word)
        assert tokens[0].type is token_type, word
        assert tokens[0].value == word


def test_keyword_set_covers_language(lex):
    for word in ("اطبع", "خلي", "لو", "غير كده", "خلاص", "كرر", "مرات", "طالما"):
        first = lex(word)[0]
        assert first.type.name.startswith("KW_")


# ------------------------------------------------------------------ numbers


def test_english_integer(lex):
    assert lex("123")[0].value == 123
    assert isinstance(lex("123")[0].value, int)


def test_arabic_indic_integer(lex):
    assert lex("١٢٣")[0].value == 123


def test_extended_arabic_indic_integer(lex):
    assert lex("۱۲۳")[0].value == 123


def test_english_float(lex):
    assert lex("12.5")[0].value == 12.5


def test_arabic_decimal_separator(lex):
    assert lex("١٢٫٥")[0].value == 12.5


def test_number_raw_preserved(lex):
    token = lex("٤٢")[0]
    assert token.value == 42
    assert token.raw == "٤٢"


def test_invalid_number_reports_error(lex):
    from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag
    from al_arabiya.compiler.lexer.lexer import Lexer

    bag = DiagnosticBag()
    tokens = Lexer("1..2", bag).tokenize()
    assert bag.has_errors
    assert bag.errors[0].code == ErrorCode.INVALID_NUMBER
    assert tokens[0].type is TokenType.NUMBER


# ----------------------------------------------------------------- strings


def test_simple_string(lex):
    token = lex('"مرحبا"')[0]
    assert token.type is TokenType.STRING
    assert token.value == "مرحبا"


def test_string_with_operators_inside(lex):
    assert lex('"1 + 2 = 3"')[0].value == "1 + 2 = 3"


def test_string_escape_sequences(lex):
    assert lex(r'"أ\nب\tج"')[0].value == "أ\nب\tج"


def test_string_escape_quote_and_backslash(lex):
    assert lex(r'"قُل \"أهلا\" \\ "')[0].value == 'قُل "أهلا" \\ '


def test_string_unicode_escape(lex):
    assert lex(r'"\u{0627}\u{0644}"')[0].value == "ال"


def test_unterminated_string_reports_error(lex):
    from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag
    from al_arabiya.compiler.lexer.lexer import Lexer

    bag = DiagnosticBag()
    Lexer('"نص مقفول', bag).tokenize()
    assert bag.errors[0].code == ErrorCode.UNTERMINATED_STRING


def test_unknown_escape_reports_error(lex):
    from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag
    from al_arabiya.compiler.lexer.lexer import Lexer

    bag = DiagnosticBag()
    tokens = Lexer(r'"a\qb"', bag).tokenize()
    assert any(d.code == ErrorCode.INVALID_ESCAPE for d in bag.errors)
    assert tokens[0].value == "aqb"  # recovery keeps the character


# -------------------------------------------------- operators & delimiters


def test_two_character_operators(lex):
    for text in ("==", "!=", "<=", ">="):
        assert lex(text)[0].type in (
            TokenType.EQ_EQUAL,
            TokenType.NOT_EQUAL,
            TokenType.LESS_EQUAL,
            TokenType.GREATER_EQUAL,
        )


def test_single_character_operators(lex):
    expected = {
        "+": TokenType.PLUS,
        "-": TokenType.MINUS,
        "*": TokenType.STAR,
        "/": TokenType.SLASH,
        "%": TokenType.PERCENT,
        "=": TokenType.ASSIGN,
        "<": TokenType.LESS,
        ">": TokenType.GREATER,
    }
    for text, token_type in expected.items():
        assert lex(text)[0].type is token_type


def test_delimiters(lex):
    expected = {
        "(": TokenType.LPAREN,
        ")": TokenType.RPAREN,
        "[": TokenType.LBRACKET,
        "]": TokenType.RBRACKET,
        "{": TokenType.LBRACE,
        "}": TokenType.RBRACE,
        ",": TokenType.COMMA,
        ":": TokenType.COLON,
        ".": TokenType.DOT,
    }
    for text, token_type in expected.items():
        assert lex(text)[0].type is token_type


def test_operator_sequence(lex):
    tokens = lex("س + 1 == 2 != 3 >= 4 <= 5 > 6 < 7")
    types = [t.type for t in tokens if t.type not in (TokenType.NEWLINE,)]
    assert types == [
        TokenType.IDENTIFIER,
        TokenType.PLUS,
        TokenType.NUMBER,
        TokenType.EQ_EQUAL,
        TokenType.NUMBER,
        TokenType.NOT_EQUAL,
        TokenType.NUMBER,
        TokenType.GREATER_EQUAL,
        TokenType.NUMBER,
        TokenType.LESS_EQUAL,
        TokenType.NUMBER,
        TokenType.GREATER,
        TokenType.NUMBER,
        TokenType.LESS,
        TokenType.NUMBER,
        TokenType.EOF,
    ]


# ---------------------------------------------------------------- positions


def test_positions_on_arabic_source(lex):
    tokens = lex("خلي س = 10\nاطبع س")
    by_type = [(t.type, t.line, t.column) for t in tokens]
    assert by_type == [
        (TokenType.KW_LET, 1, 1),
        (TokenType.IDENTIFIER, 1, 5),
        (TokenType.ASSIGN, 1, 7),
        (TokenType.NUMBER, 1, 9),
        (TokenType.NEWLINE, 1, 11),
        (TokenType.KW_PRINT, 2, 1),
        (TokenType.IDENTIFIER, 2, 6),
        (TokenType.EOF, 2, 7),
    ]


def test_position_offset_and_length(lex):
    token = lex("العمر")[0]
    assert token.span.start.offset == 0
    assert token.span.start.line == 1
    assert token.span.start.column == 1
    assert token.length == 5  # code points, Arabic counted correctly


def test_second_line_offsets(lex):
    source = "1\n22\n333"
    tokens = lex(source)
    numbers = [t for t in tokens if t.type is TokenType.NUMBER]
    assert [(t.line, t.column, t.span.start.offset) for t in numbers] == [
        (1, 1, 0),
        (2, 1, 2),
        (3, 1, 5),
    ]


# ------------------------------------------------- comments & whitespace


def test_line_comment_skipped(lex):
    tokens = lex("# ده تعليق\nخلي")
    assert tokens[0].type is TokenType.NEWLINE
    assert tokens[1].type is TokenType.KW_LET


def test_comment_to_end_of_line(lex):
    tokens = lex('اطبع 1 # وده تعليق')
    assert [t.type for t in tokens] == [
        TokenType.KW_PRINT,
        TokenType.NUMBER,
        TokenType.EOF,
    ]


def test_whitespace_and_tabs_ignored(lex):
    assert len([t for t in lex("\t  خلي \t س ") if t.type != TokenType.EOF]) == 2


def test_newlines_preserved(lex):
    tokens = lex("\n\n\n")
    assert [t.type for t in tokens] == [
        TokenType.NEWLINE,
        TokenType.NEWLINE,
        TokenType.NEWLINE,
        TokenType.EOF,
    ]


def test_empty_source_gives_eof_only(lex):
    assert [t.type for t in lex("")] == [TokenType.EOF]


# ------------------------------------------------------------------ errors


def test_invalid_character_reports_e1001(lex):
    from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag
    from al_arabiya.compiler.lexer.lexer import Lexer

    bag = DiagnosticBag()
    Lexer("خلي س = @", bag).tokenize()
    diagnostic = bag.errors[0]
    assert diagnostic.code == ErrorCode.UNEXPECTED_CHARACTER
    assert diagnostic.span.start.line == 1
    assert diagnostic.span.start.column == 9


def test_lone_bang_reports_e1005(lex):
    from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag
    from al_arabiya.compiler.lexer.lexer import Lexer

    bag = DiagnosticBag()
    Lexer("س !", bag).tokenize()
    assert bag.errors[0].code == ErrorCode.UNEXPECTED_OPERATOR


def test_error_at_correct_line(lex):
    from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag
    from al_arabiya.compiler.lexer.lexer import Lexer

    bag = DiagnosticBag()
    Lexer("اطبع 1\nخلي س = @", bag).tokenize()
    assert bag.errors[0].span.start.line == 2


def test_eof_token_always_last(lex):
    tokens = lex("خلي س = 1")
    assert tokens[-1].type is TokenType.EOF
    assert tokens[-1].value is None
