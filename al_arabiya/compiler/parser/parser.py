"""The AlArabiya parser: tokens → AST.

Statements are parsed by recursive descent; expressions use precedence
climbing (a Pratt-style loop) so that new operator families (calls,
indexing, member access, ...) can be added as single parselets later on.
The parser never executes anything and never raises bare strings — every
problem becomes a :class:`Diagnostic` in the bag.
"""

from __future__ import annotations

from al_arabiya.compiler.ast.nodes import (
    Assignment,
    BinaryExpression,
    BreakStatement,
    CallExpression,
    ContinueStatement,
    Expression,
    ExpressionStatement,
    ForEachStatement,
    FunctionDeclaration,
    Identifier,
    IfStatement,
    ImportStatement,
    IndexAssignment,
    IndexExpression,
    ListLiteral,
    Literal,
    MapLiteral,
    NullLiteral,
    Parameter,
    PrintStatement,
    Program,
    RepeatStatement,
    ReturnStatement,
    Statement,
    ThrowStatement,
    TryStatement,
    UnaryExpression,
    VariableDeclaration,
    WhileStatement,
)
from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag
from al_arabiya.compiler.diagnostics.errors import ErrorCode, ParseError
from al_arabiya.compiler.lexer.positions import Position, Span
from al_arabiya.compiler.lexer.tokens import Token, TokenType
from al_arabiya.compiler.parser.precedence import Precedence

__all__ = ["Parser"]

_INFIX_PRECEDENCE: dict[TokenType, Precedence] = {
    TokenType.KW_OR: Precedence.LOGICAL_OR,
    TokenType.KW_AND: Precedence.LOGICAL_AND,
    TokenType.KW_GREATER: Precedence.COMPARISON,
    TokenType.KW_LESS: Precedence.COMPARISON,
    TokenType.KW_NOT: Precedence.COMPARISON,
    TokenType.KW_EQUAL_WORD: Precedence.COMPARISON,
    TokenType.EQ_EQUAL: Precedence.COMPARISON,
    TokenType.NOT_EQUAL: Precedence.COMPARISON,
    TokenType.LESS: Precedence.COMPARISON,
    TokenType.GREATER: Precedence.COMPARISON,
    TokenType.LESS_EQUAL: Precedence.COMPARISON,
    TokenType.GREATER_EQUAL: Precedence.COMPARISON,
    TokenType.PLUS: Precedence.ADDITIVE,
    TokenType.KW_ADD: Precedence.ADDITIVE,
    TokenType.MINUS: Precedence.ADDITIVE,
    TokenType.KW_SUB: Precedence.ADDITIVE,
    TokenType.STAR: Precedence.MULTIPLICATIVE,
    TokenType.KW_MUL: Precedence.MULTIPLICATIVE,
    TokenType.SLASH: Precedence.MULTIPLICATIVE,
    TokenType.KW_DIV: Precedence.MULTIPLICATIVE,
    TokenType.PERCENT: Precedence.MULTIPLICATIVE,
}

_SIMPLE_INFIX: dict[TokenType, tuple[str, int]] = {
    TokenType.KW_OR: ("أو", 1),
    TokenType.KW_AND: ("و", 1),
    TokenType.EQ_EQUAL: ("==", 1),
    TokenType.NOT_EQUAL: ("!=", 1),
    TokenType.LESS: ("<", 1),
    TokenType.GREATER: (">", 1),
    TokenType.LESS_EQUAL: ("<=", 1),
    TokenType.GREATER_EQUAL: (">=", 1),
    TokenType.PLUS: ("+", 1),
    TokenType.KW_ADD: ("+", 1),
    TokenType.MINUS: ("-", 1),
    TokenType.KW_SUB: ("-", 1),
    TokenType.STAR: ("*", 1),
    TokenType.KW_MUL: ("*", 1),
    TokenType.SLASH: ("/", 1),
    TokenType.KW_DIV: ("/", 1),
    TokenType.PERCENT: ("%", 1),
    TokenType.KW_EQUAL_WORD: ("==", 1),
}


class Parser:
    """Turns a token stream into a :class:`Program` AST."""

    def __init__(self, tokens: list[Token], bag: DiagnosticBag | None = None) -> None:
        if not tokens:
            raise ValueError("Parser needs at least an EOF token")
        self._tokens = tokens
        self._bag = bag if bag is not None else DiagnosticBag()
        self._index = 0
        self._prev = tokens[0]

    @property
    def bag(self) -> DiagnosticBag:
        return self._bag

    # ---------------------------------------------------------------- helpers

    def _peek(self, ahead: int = 0) -> Token:
        index = min(self._index + ahead, len(self._tokens) - 1)
        return self._tokens[index]

    def _at_eof(self) -> bool:
        return self._peek().type is TokenType.EOF

    def _advance(self) -> Token:
        token = self._tokens[self._index]
        if self._index < len(self._tokens) - 1:
            self._index += 1
        self._prev = token
        return token

    def _check(self, token_type: TokenType) -> bool:
        return self._peek().type is token_type

    def _match(self, token_type: TokenType) -> bool:
        if self._check(token_type):
            self._advance()
            return True
        return False

    def _skip_newlines(self) -> None:
        while self._check(TokenType.NEWLINE):
            self._advance()

    def _make_error(
        self,
        token: Token,
        code: ErrorCode,
        message: str,
        suggestion: str | None = None,
    ) -> ParseError:
        diagnostic = self._bag.error(code, message, token.span, suggestion=suggestion)
        return ParseError(diagnostic)

    def _expect(
        self,
        token_type: TokenType,
        code: ErrorCode,
        message: str,
        suggestion: str | None = None,
    ) -> Token:
        if self._check(token_type):
            return self._advance()
        raise self._make_error(self._peek(), code, message, suggestion)

    def _end_statement(self) -> None:
        """Every statement must be followed by a newline (or the file end)."""
        if self._at_eof():
            return
        if self._check(TokenType.NEWLINE):
            self._advance()
            self._skip_newlines()
            return
        raise self._make_error(
            self._peek(),
            ErrorCode.EXPECTED_NEWLINE,
            "محتاج تبدأ أمر جديد في سطر لوحده",
            suggestion="اقفل الأمر الحالي وابدأ اللي بعده في سطر جديد",
        )

    def _synchronize(self) -> None:
        """Panic-mode recovery: skip to the next statement boundary."""
        while not self._at_eof() and not self._check(TokenType.NEWLINE):
            self._advance()
        if self._check(TokenType.NEWLINE):
            self._advance()
        self._skip_newlines()

    # --------------------------------------------------------------- program

    def parse_program(self) -> Program:
        self._skip_newlines()
        start: Position = self._peek().span.start
        body: list[Statement] = []
        while not self._at_eof():
            before = self._index
            try:
                statement = self._parse_statement()
            except ParseError:
                self._synchronize()
            else:
                if statement is not None:
                    body.append(statement)
            if self._index == before:
                self._advance()
            self._skip_newlines()
        return Program(Span(start, self._peek().span.end), body)

    def parse_expression(
        self, min_bp: Precedence = Precedence.LOWEST
    ) -> Expression:
        """Precedence-climbing entry point."""
        left = self._parse_prefix()
        while True:
            affix = self._peek_infix(min_bp)
            if affix is None:
                break
            operator, precedence, count = affix
            for _ in range(count):
                self._advance()
            right = self.parse_expression(Precedence(int(precedence) + 1))
            left = BinaryExpression(Span(left.span.start, right.span.end), operator, left, right)
        return left

    def _peek_infix(
        self, min_bp: Precedence
    ) -> tuple[str, Precedence, int] | None:
        token = self._peek()
        precedence = _INFIX_PRECEDENCE.get(token.type)
        if precedence is None or precedence < min_bp:
            return None

        if token.type is TokenType.KW_GREATER:
            nxt = self._peek(1)
            if nxt.type is TokenType.KW_FROM:
                return ">", precedence, 2
            if nxt.type is TokenType.KW_OR and self._peek(2).type is TokenType.KW_EQUAL_WORD:
                return ">=", precedence, 3
            raise self._make_error(
                token,
                ErrorCode.EXPECTED_TOKEN,
                "بعد 'أكبر' لازم تيجي 'من' (أو 'أكبر أو يساوي')",
                suggestion="اكتب: س أكبر من 5  أو  س أكبر أو يساوي 5",
            )
        if token.type is TokenType.KW_LESS:
            nxt = self._peek(1)
            if nxt.type is TokenType.KW_FROM:
                return "<", precedence, 2
            if nxt.type is TokenType.KW_OR and self._peek(2).type is TokenType.KW_EQUAL_WORD:
                return "<=", precedence, 3
            raise self._make_error(
                token,
                ErrorCode.EXPECTED_TOKEN,
                "بعد 'أصغر' لازم تيجي 'من' (أو 'أصغر أو يساوي')",
                suggestion="اكتب: س أصغر من 5  أو  س أصغر أو يساوي 5",
            )
        if token.type is TokenType.KW_NOT:
            if self._peek(1).type is TokenType.KW_EQUAL_WORD:
                return "!=", precedence, 2
            raise self._make_error(
                token,
                ErrorCode.EXPECTED_TOKEN,
                "بعد 'مش' لازم تيجي 'يساوي'",
                suggestion="اكتب: س مش يساوي 5",
            )

        operator, count = _SIMPLE_INFIX[token.type]
        return operator, precedence, count

    def _parse_prefix(self) -> Expression:
        expr = self._parse_atom()
        while True:
            if self._check(TokenType.LPAREN):
                expr = self._finish_call(expr)
            elif self._check(TokenType.LBRACKET):
                expr = self._finish_index(expr)
            else:
                break
        return expr

    def _finish_index(self, target: Expression) -> Expression:
        self._advance()  # consume '['
        index = self.parse_expression()
        bracket = self._expect(
            TokenType.RBRACKET,
            ErrorCode.EXPECTED_TOKEN,
            "قوس الفهرسة '[' مش متقفل",
            suggestion="اقفل القوس بـ ']'",
        )
        return IndexExpression(Span(target.span.start, bracket.span.end), target, index)

    def _finish_call(self, callee: Expression) -> Expression:
        self._advance()  # consume '('
        self._skip_newlines()
        arguments: list[Expression] = []
        if not self._check(TokenType.RPAREN):
            arguments.append(self.parse_expression())
            self._skip_newlines()
            while self._match(TokenType.COMMA):
                self._skip_newlines()
                arguments.append(self.parse_expression())
                self._skip_newlines()
        rparen = self._expect(
            TokenType.RPAREN,
            ErrorCode.EXPECTED_TOKEN,
            "قوس الاستدعاء '(' مش متقفل",
            suggestion="اقفل القوس بـ ')'",
        )
        return CallExpression(
            Span(callee.span.start, rparen.span.end), callee, arguments
        )

    def _parse_list_literal(self, bracket: Token) -> Expression:
        self._skip_newlines()
        elements: list[Expression] = []
        if not self._check(TokenType.RBRACKET):
            elements.append(self.parse_expression())
            self._skip_newlines()
            while self._match(TokenType.COMMA):
                self._skip_newlines()
                if self._check(TokenType.RBRACKET):  # trailing comma
                    break
                elements.append(self.parse_expression())
                self._skip_newlines()
        end = self._expect(
            TokenType.RBRACKET,
            ErrorCode.EXPECTED_TOKEN,
            "قوس القائمة '[' مش متقفل",
            suggestion="اقفل القائمة بـ ']'",
        )
        return ListLiteral(Span(bracket.span.start, end.span.end), elements)

    def _parse_map_literal(self, brace: Token) -> Expression:
        self._skip_newlines()
        entries: list[tuple[Expression, Expression]] = []
        if not self._check(TokenType.RBRACE):
            entries.append(self._parse_map_entry())
            self._skip_newlines()
            while self._match(TokenType.COMMA):
                self._skip_newlines()
                if self._check(TokenType.RBRACE):  # trailing comma
                    break
                entries.append(self._parse_map_entry())
                self._skip_newlines()
        end = self._expect(
            TokenType.RBRACE,
            ErrorCode.EXPECTED_TOKEN,
            "قوس القاموس '{' مش متقفل",
            suggestion="اقفل القاموس بـ '}'",
        )
        return MapLiteral(Span(brace.span.start, end.span.end), entries)

    def _parse_map_entry(self) -> tuple[Expression, Expression]:
        key = self.parse_expression()
        self._expect(
            TokenType.COLON,
            ErrorCode.EXPECTED_TOKEN,
            "محتاج ':' بين المفتاح والقيمة",
            suggestion='مثال: {"الاسم": "أحمد"}',
        )
        value = self.parse_expression()
        return key, value

    def _parse_atom(self) -> Expression:
        token = self._advance()
        token_type = token.type

        if token_type is TokenType.NUMBER:
            assert isinstance(token.value, (int, float))
            return Literal(token.span, token.value)
        if token_type is TokenType.STRING:
            assert isinstance(token.value, str)
            return Literal(token.span, token.value)
        if token_type is TokenType.KW_TRUE:
            return Literal(token.span, True)
        if token_type is TokenType.KW_FALSE:
            return Literal(token.span, False)
        if token_type is TokenType.KW_NULL:
            return NullLiteral(token.span)
        if token_type is TokenType.LBRACKET:
            return self._parse_list_literal(token)
        if token_type is TokenType.LBRACE:
            return self._parse_map_literal(token)
        if token_type is TokenType.IDENTIFIER:
            assert isinstance(token.value, str)
            return Identifier(token.span, token.value)
        if token_type is TokenType.LPAREN:
            inner = self.parse_expression()
            self._expect(
                TokenType.RPAREN,
                ErrorCode.EXPECTED_TOKEN,
                "قوس '(' مش متقفل",
                suggestion="اقفل القوس بـ ')'",
            )
            return inner
        if token_type in (TokenType.MINUS, TokenType.KW_SUB):
            operand = self.parse_expression(Precedence.UNARY)
            return UnaryExpression(Span(token.span.start, operand.span.end), "-", operand)
        if token_type is TokenType.EOF:
            raise self._make_error(
                token,
                ErrorCode.UNEXPECTED_EOF,
                "الكود خلص قبل ما التعبير يكمل",
            )
        if token_type is TokenType.NEWLINE:
            raise self._make_error(
                token,
                ErrorCode.UNEXPECTED_TOKEN,
                "محتاج تعبير هنا بس لقيت نهاية السطر",
            )
        raise self._make_error(
            token,
            ErrorCode.UNEXPECTED_TOKEN,
            f"مش فاهم {token.describe()} هنا",
            suggestion="ابدأ التعبير برقم أو نص أو اسم متغير أو قوس '('",
        )

    # ------------------------------------------------------------- statements

    def _parse_statement(self) -> Statement | None:
        token = self._peek()
        token_type = token.type
        if token_type is TokenType.NEWLINE:
            self._advance()
            return None
        if token_type is TokenType.KW_PRINT:
            return self._parse_print()
        if token_type is TokenType.KW_LET:
            return self._parse_declaration()
        if token_type is TokenType.KW_IF:
            return self._parse_if()
        if token_type is TokenType.KW_REPEAT:
            return self._parse_repeat()
        if token_type is TokenType.KW_WHILE:
            return self._parse_while()
        if token_type is TokenType.KW_FUNC:
            return self._parse_function()
        if token_type is TokenType.KW_RETURN:
            return self._parse_return()
        if token_type is TokenType.KW_BREAK:
            return self._parse_break()
        if token_type is TokenType.KW_CONTINUE:
            return self._parse_continue()
        if token_type is TokenType.KW_FOREACH:
            return self._parse_for_each()
        if token_type is TokenType.KW_IMPORT:
            return self._parse_import()
        if token_type is TokenType.KW_FROM:
            return self._parse_from_import()
        if token_type is TokenType.KW_TRY:
            return self._parse_try()
        if token_type is TokenType.KW_THROW:
            return self._parse_throw()
        if token_type is TokenType.IDENTIFIER and self._peek(1).type is TokenType.ASSIGN:
            return self._parse_assignment()
        return self._parse_expression_statement(token)

    def _parse_expression_statement(self, first: Token) -> Statement:
        """A call statement, an index assignment, or (otherwise) an error."""
        expression = self.parse_expression()
        if self._check(TokenType.ASSIGN):
            return self._finish_index_assignment(expression, first)
        if not isinstance(expression, CallExpression):
            raise self._make_error(
                first,
                ErrorCode.UNEXPECTED_TOKEN,
                f"مش عارف أعمل إيه بـ {first.describe()}",
                suggestion="الأوامر: اطبع، خلي، لو، كرر، طالما، دالة — أو نادِ دالة",
            )
        end = self._prev.span.end
        self._end_statement()
        return ExpressionStatement(Span(expression.span.start, end), expression)

    def _finish_index_assignment(self, target: Expression, first: Token) -> Statement:
        if not isinstance(target, IndexExpression):
            raise self._make_error(
                first,
                ErrorCode.INVALID_ASSIGN_TARGET,
                "مينفعش تدّي قيمة للحاجة دي",
                suggestion="غيّر متغيّر (س = ...) أو عنصر في قائمة/قاموس (ق[0] = ...)",
            )
        self._advance()  # consume '='
        value = self.parse_expression()
        end = self._prev.span.end
        self._end_statement()
        return IndexAssignment(
            Span(target.span.start, end), target.target, target.index, value
        )

    def _parse_for_each(self) -> ForEachStatement:
        keyword = self._advance()
        name_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.EXPECTED_IDENTIFIER,
            "بعد 'لكل' لازم يجي اسم المتغير",
            suggestion="مثال: لكل عنصر في القائمة",
        )
        self._expect(
            TokenType.KW_MUL,  # the word "في" doubles as the "in" of a for-each
            ErrorCode.EXPECTED_TOKEN,
            "محتاج 'في' بعد اسم المتغير",
            suggestion="مثال: لكل عنصر في القائمة",
        )
        iterable = self.parse_expression()
        self._end_statement()
        body = self._parse_block({TokenType.KW_END})
        self._expect_block_end("'لكل' لازم تتقفل بكلمة 'خلاص'")
        end = self._prev.span.end
        self._end_statement()
        assert isinstance(name_token.value, str)
        return ForEachStatement(
            Span(keyword.span.start, end), name_token.value, name_token.span, iterable, body
        )

    def _parse_import(self) -> ImportStatement:
        keyword = self._advance()
        path_token = self._expect_string_path()
        alias: str | None = None
        if self._match(TokenType.KW_AS):
            alias_token = self._expect(
                TokenType.IDENTIFIER,
                ErrorCode.EXPECTED_IDENTIFIER,
                "بعد 'باسم' لازم يجي اسم",
                suggestion='مثال: استورد "رياضيات" باسم ر',
            )
            assert isinstance(alias_token.value, str)
            alias = alias_token.value
        end = self._prev.span.end
        self._end_statement()
        assert isinstance(path_token.value, str)
        return ImportStatement(
            Span(keyword.span.start, end), path_token.value, path_token.span, alias=alias
        )

    def _parse_from_import(self) -> ImportStatement:
        keyword = self._advance()
        path_token = self._expect_string_path()
        self._expect(
            TokenType.KW_IMPORT,
            ErrorCode.EXPECTED_TOKEN,
            "بعد اسم الملف لازم تكتب 'استورد'",
            suggestion='مثال: من "رياضيات" استورد جمع، طرح',
        )
        names: list[str] = []
        first = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.EXPECTED_IDENTIFIER,
            "محتاج اسم على الأقل بعد 'استورد'",
            suggestion='مثال: من "رياضيات" استورد جمع',
        )
        assert isinstance(first.value, str)
        names.append(first.value)
        while self._match(TokenType.COMMA):
            name_token = self._expect(
                TokenType.IDENTIFIER,
                ErrorCode.EXPECTED_IDENTIFIER,
                "محتاج اسم بعد الفاصلة",
            )
            assert isinstance(name_token.value, str)
            names.append(name_token.value)
        end = self._prev.span.end
        self._end_statement()
        assert isinstance(path_token.value, str)
        return ImportStatement(
            Span(keyword.span.start, end),
            path_token.value,
            path_token.span,
            names=tuple(names),
        )

    def _expect_string_path(self) -> Token:
        return self._expect(
            TokenType.STRING,
            ErrorCode.EXPECTED_TOKEN,
            "اسم الملف لازم يكون نص بين علامتي تنصيص",
            suggestion='مثال: استورد "رياضيات"',
        )

    def _parse_print(self) -> PrintStatement:
        keyword = self._advance()
        expression = self.parse_expression()
        end = self._prev.span.end
        self._end_statement()
        return PrintStatement(Span(keyword.span.start, end), expression)

    def _parse_declaration(self) -> VariableDeclaration:
        keyword = self._advance()
        name_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.EXPECTED_IDENTIFIER,
            "بعد 'خلي' لازم يجي اسم المتغير",
            suggestion="مثال: خلي الاسم = \"أحمد\"",
        )
        self._expect(
            TokenType.ASSIGN,
            ErrorCode.EXPECTED_TOKEN,
            "محتاج علامة '=' بعد اسم المتغير",
            suggestion="مثال: خلي العمر = 25",
        )
        initializer = self.parse_expression()
        end = self._prev.span.end
        self._end_statement()
        assert isinstance(name_token.value, str)
        return VariableDeclaration(
            Span(keyword.span.start, end),
            name_token.value,
            name_token.span,
            initializer,
        )

    def _parse_assignment(self) -> Assignment:
        name_token = self._advance()
        assert isinstance(name_token.value, str)
        name = name_token.value
        self._expect(
            TokenType.ASSIGN,
            ErrorCode.EXPECTED_TOKEN,
            f"'{name}' لازم يتبعه '=' لو عايز تغيّر قيمته",
            suggestion=f"اكتب: {name} = القيمة الجديدة",
        )
        value = self.parse_expression()
        end = self._prev.span.end
        self._end_statement()
        return Assignment(Span(name_token.span.start, end), name, name_token.span, value)

    def _parse_block(self, terminators: set[TokenType]) -> list[Statement]:
        self._skip_newlines()
        body: list[Statement] = []
        while not self._at_eof() and self._peek().type not in terminators:
            before = self._index
            try:
                statement = self._parse_statement()
            except ParseError:
                self._synchronize()
            else:
                if statement is not None:
                    body.append(statement)
            if self._index == before:
                self._advance()
            self._skip_newlines()
        return body

    def _expect_block_end(self, message: str) -> Token:
        if self._check(TokenType.KW_END):
            return self._advance()
        raise self._make_error(
            self._peek(),
            ErrorCode.MISSING_BLOCK_END,
            message,
            suggestion="اقفل الكتلة بكلمة 'خلاص'",
        )

    def _parse_if(self) -> IfStatement:
        keyword = self._advance()
        condition = self.parse_expression()
        self._end_statement()
        then_body = self._parse_block({TokenType.KW_ELSE, TokenType.KW_END})
        else_body: list[Statement] | None = None
        if self._check(TokenType.KW_ELSE):
            self._advance()
            self._expect(
                TokenType.KW_THAT,
                ErrorCode.EXPECTED_TOKEN,
                "بعد 'غير' لازم تكتب 'كده'",
                suggestion="اكتب: غير كده",
            )
            self._end_statement()
            else_body = self._parse_block({TokenType.KW_END})
        self._expect_block_end("الشرط لازم يتقفل بكلمة 'خلاص'")
        end = self._prev.span.end
        self._end_statement()
        return IfStatement(Span(keyword.span.start, end), condition, then_body, else_body)

    def _parse_repeat(self) -> RepeatStatement:
        keyword = self._advance()
        count = self.parse_expression()
        if self._peek().type in (TokenType.KW_TIMES, TokenType.KW_ONCE):
            self._advance()
        else:
            raise self._make_error(
                self._peek(),
                ErrorCode.EXPECTED_TOKEN,
                "بعد عدد التكرار لازم تكتب 'مرات'",
                suggestion="مثال: كرر 3 مرات",
            )
        self._end_statement()
        body = self._parse_block({TokenType.KW_END})
        self._expect_block_end("التكرار لازم يتقفل بكلمة 'خلاص'")
        end = self._prev.span.end
        self._end_statement()
        return RepeatStatement(Span(keyword.span.start, end), count, body)

    def _parse_while(self) -> WhileStatement:
        keyword = self._advance()
        condition = self.parse_expression()
        self._end_statement()
        body = self._parse_block({TokenType.KW_END})
        self._expect_block_end("'طالما' لازم تتقفل بكلمة 'خلاص'")
        end = self._prev.span.end
        self._end_statement()
        return WhileStatement(Span(keyword.span.start, end), condition, body)

    def _parse_function(self) -> FunctionDeclaration:
        keyword = self._advance()
        name_token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.EXPECTED_IDENTIFIER,
            "بعد 'دالة' لازم يجي اسم الدالة",
            suggestion="مثال: دالة اجمع (أ، ب)",
        )
        self._expect(
            TokenType.LPAREN,
            ErrorCode.EXPECTED_TOKEN,
            "محتاج '(' بعد اسم الدالة",
            suggestion="مثال: دالة اجمع (أ، ب)",
        )
        parameters: list[Parameter] = []
        if not self._check(TokenType.RPAREN):
            parameters.append(self._parse_parameter())
            while self._match(TokenType.COMMA):
                parameters.append(self._parse_parameter())
        self._expect(
            TokenType.RPAREN,
            ErrorCode.EXPECTED_TOKEN,
            "قوس المعاملات مش متقفل",
            suggestion="اقفل القوس بـ ')'",
        )
        self._end_statement()
        body = self._parse_block({TokenType.KW_END})
        self._expect_block_end("الدالة لازم تتقفل بكلمة 'خلاص'")
        end = self._prev.span.end
        self._end_statement()
        assert isinstance(name_token.value, str)
        return FunctionDeclaration(
            Span(keyword.span.start, end),
            name_token.value,
            name_token.span,
            parameters,
            body,
        )

    def _parse_parameter(self) -> Parameter:
        token = self._expect(
            TokenType.IDENTIFIER,
            ErrorCode.EXPECTED_PARAMETER,
            "اسم المعامل لازم يكون كلمة",
            suggestion="مثال: دالة اجمع (أ، ب)",
        )
        assert isinstance(token.value, str)
        return Parameter(token.span, token.value)

    def _parse_return(self) -> ReturnStatement:
        keyword = self._advance()
        value: Expression | None = None
        if not self._check(TokenType.NEWLINE) and not self._at_eof():
            value = self.parse_expression()
        end = value.span.end if value is not None else keyword.span.end
        self._end_statement()
        return ReturnStatement(Span(keyword.span.start, end), value)

    def _parse_break(self) -> BreakStatement:
        keyword = self._advance()
        self._end_statement()
        return BreakStatement(keyword.span)

    def _parse_continue(self) -> ContinueStatement:
        keyword = self._advance()
        self._end_statement()
        return ContinueStatement(keyword.span)

    def _parse_throw(self) -> ThrowStatement:
        keyword = self._advance()
        value = self.parse_expression()
        end = self._prev.span.end
        self._end_statement()
        return ThrowStatement(Span(keyword.span.start, end), value)

    def _parse_try(self) -> TryStatement:
        keyword = self._advance()
        self._end_statement()
        try_body = self._parse_block(
            {TokenType.KW_CATCH, TokenType.KW_FINALLY, TokenType.KW_END}
        )

        catch_name: str | None = None
        catch_name_span: Span | None = None
        catch_body: list[Statement] | None = None
        if self._check(TokenType.KW_CATCH):
            self._advance()
            if self._check(TokenType.IDENTIFIER):
                name_token = self._advance()
                assert isinstance(name_token.value, str)
                catch_name = name_token.value
                catch_name_span = name_token.span
            self._end_statement()
            catch_body = self._parse_block({TokenType.KW_FINALLY, TokenType.KW_END})

        finally_body: list[Statement] | None = None
        if self._check(TokenType.KW_FINALLY):
            self._advance()
            self._end_statement()
            finally_body = self._parse_block({TokenType.KW_END})

        if catch_body is None and finally_body is None:
            raise self._make_error(
                self._peek(),
                ErrorCode.TRY_WITHOUT_HANDLER,
                "'حاول' لازم يتبعها 'امسك' أو 'أخيرا'",
                suggestion="ضيف 'امسك' لمعالجة الخطأ أو 'أخيرا' للتنظيف",
            )

        self._expect_block_end("'حاول' لازم تتقفل بكلمة 'خلاص'")
        end = self._prev.span.end
        self._end_statement()
        return TryStatement(
            Span(keyword.span.start, end),
            try_body,
            catch_name=catch_name,
            catch_name_span=catch_name_span,
            catch_body=catch_body,
            finally_body=finally_body,
        )
