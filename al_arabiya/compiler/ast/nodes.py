"""The AlArabiya AST: a typed, dataclass-based node hierarchy.

Every node carries a :class:`~al_arabiya.compiler.lexer.positions.Span` so
diagnostics, LSP features and future backends can always point back at the
source that produced them.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields

from al_arabiya.compiler.lexer.positions import Span

__all__ = [
    "Assignment",
    "ASTNode",
    "BinaryExpression",
    "BreakStatement",
    "CallExpression",
    "ContinueStatement",
    "Expression",
    "ExpressionStatement",
    "ForEachStatement",
    "FunctionDeclaration",
    "Identifier",
    "IfStatement",
    "ImportStatement",
    "IndexAssignment",
    "IndexExpression",
    "ListLiteral",
    "Literal",
    "MapLiteral",
    "NullLiteral",
    "Parameter",
    "PrintStatement",
    "Program",
    "RepeatStatement",
    "ReturnStatement",
    "Statement",
    "ThrowStatement",
    "TryStatement",
    "UnaryExpression",
    "VariableDeclaration",
    "WhileStatement",
]

#: Binary/unary operators are normalised to these canonical forms at build
#: time: Arabic word operators (`زائد`, `أكبر من`, `مش يساوي`, ...) are
#: folded into their symbol equivalents, except logical `و` / `أو`.
Operator = str


@dataclass(slots=True)
class ASTNode:
    """Base class for every AST node."""

    span: Span


# ----------------------------------------------------------------- statements


@dataclass(slots=True)
class Statement(ASTNode):
    """Base class for statements."""


@dataclass(slots=True)
class Program(ASTNode):
    """Root node: a whole compilation unit."""

    body: list[Statement] = field(default_factory=list)


@dataclass(slots=True)
class PrintStatement(Statement):
    """``اطبع <expr>``"""

    expression: Expression


@dataclass(slots=True)
class VariableDeclaration(Statement):
    """``خلي <name> = <expr>``"""

    name: str
    name_span: Span
    initializer: Expression


@dataclass(slots=True)
class Assignment(Statement):
    """``<name> = <expr>``"""

    target: str
    target_span: Span
    value: Expression


@dataclass(slots=True)
class IfStatement(Statement):
    """``لو <cond> ... غير كده ... خلاص``"""

    condition: Expression
    then_body: list[Statement]
    else_body: list[Statement] | None = None


@dataclass(slots=True)
class RepeatStatement(Statement):
    """``كرر <count> مرات ... خلاص``"""

    count: Expression
    body: list[Statement]


@dataclass(slots=True)
class WhileStatement(Statement):
    """``طالما <cond> ... خلاص``"""

    condition: Expression
    body: list[Statement]


@dataclass(slots=True)
class Parameter(ASTNode):
    """One formal parameter in a function declaration."""

    name: str


@dataclass(slots=True)
class FunctionDeclaration(Statement):
    """``دالة <name> (<params>) ... خلاص``"""

    name: str
    name_span: Span
    parameters: list[Parameter]
    body: list[Statement]

    @property
    def params(self) -> list[Parameter]:
        """Alias used by the runtime function value."""
        return self.parameters


@dataclass(slots=True)
class ReturnStatement(Statement):
    """``رجّع <expr>`` (the expression is optional)."""

    value: Expression | None = None


@dataclass(slots=True)
class ExpressionStatement(Statement):
    """An expression used as a statement (currently a function call)."""

    expression: Expression


@dataclass(slots=True)
class IndexAssignment(Statement):
    """``<collection>[<index>] = <value>``"""

    collection: Expression
    index: Expression
    value: Expression


@dataclass(slots=True)
class ForEachStatement(Statement):
    """``لكل <name> في <iterable> ... خلاص``"""

    variable: str
    variable_span: Span
    iterable: Expression
    body: list[Statement]


@dataclass(slots=True)
class ImportStatement(Statement):
    """``استورد "<path>"`` optionally ``باسم <alias>`` or ``من "<path>" استورد a، b``."""

    path: str
    path_span: Span
    alias: str | None = None
    names: tuple[str, ...] | None = None


@dataclass(slots=True)
class BreakStatement(Statement):
    """``اكسر`` — stop the innermost loop."""


@dataclass(slots=True)
class ContinueStatement(Statement):
    """``كمل`` — jump to the next iteration of the innermost loop."""


@dataclass(slots=True)
class ThrowStatement(Statement):
    """``ارم <expr>`` — raise an error value."""

    value: Expression


@dataclass(slots=True)
class TryStatement(Statement):
    """``حاول ... امسك [اسم] ... أخيرا ... خلاص`` (catch/finally each optional)."""

    try_body: list[Statement]
    catch_name: str | None = None
    catch_name_span: Span | None = None
    catch_body: list[Statement] | None = None
    finally_body: list[Statement] | None = None


# --------------------------------------------------------------- expressions


@dataclass(slots=True)
class Expression(ASTNode):
    """Base class for expressions."""


@dataclass(slots=True)
class Literal(Expression):
    """A number, string or boolean literal."""

    value: int | float | str | bool


@dataclass(slots=True)
class NullLiteral(Expression):
    """The empty value literal ``فراغ``."""


@dataclass(slots=True)
class Identifier(Expression):
    """A variable reference."""

    name: str


@dataclass(slots=True)
class CallExpression(Expression):
    """``<callee>(<args>)``"""

    callee: Expression
    arguments: list[Expression]


@dataclass(slots=True)
class IndexExpression(Expression):
    """``<target>[<index>]``"""

    target: Expression
    index: Expression


@dataclass(slots=True)
class ListLiteral(Expression):
    """``[<e>، <e>، ...]``"""

    elements: list[Expression]


@dataclass(slots=True)
class MapLiteral(Expression):
    """``{<key>: <value>، ...}``"""

    entries: list[tuple[Expression, Expression]]


@dataclass(slots=True)
class BinaryExpression(Expression):
    """``left <operator> right`` with a canonical operator string."""

    operator: Operator
    left: Expression
    right: Expression


@dataclass(slots=True)
class UnaryExpression(Expression):
    """``<operator> operand`` (currently only ``-``)."""

    operator: Operator
    operand: Expression


# ----------------------------------------------------------------- traversal


def iter_child_nodes(node: ASTNode) -> list[ASTNode]:
    """Return direct AST children of ``node`` (list fields included)."""
    children: list[ASTNode] = []
    for f in fields(node):
        value = getattr(node, f.name)
        if isinstance(value, ASTNode):
            children.append(value)
        elif isinstance(value, list):
            children.extend(item for item in value if isinstance(item, ASTNode))
    return children
