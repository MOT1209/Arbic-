"""Operator precedence table for the precedence-climbing expression parser.

Precedence grows towards the caller: a larger number binds tighter.
All binary operators are left-associative in AlArabiya.
"""

from __future__ import annotations

from enum import IntEnum

__all__ = ["Precedence"]


class Precedence(IntEnum):
    """Binding powers used by :meth:`Parser.parse_expression`."""

    LOWEST = 0
    LOGICAL_OR = 1       # أو
    LOGICAL_AND = 2      # و
    COMPARISON = 3       # أكبر من، يساوي، !=، ...
    ADDITIVE = 4         # + - زائد ناقص
    MULTIPLICATIVE = 5   # * / % في على
    UNARY = 6            # - ناقص (prefix)
