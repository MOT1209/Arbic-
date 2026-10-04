"""The bytecode instruction set for the AlArabiya stack VM."""

from __future__ import annotations

from enum import IntEnum

__all__ = ["Op"]


class Op(IntEnum):
    """One opcode per instruction; some are followed by a single int operand."""

    CONST = 0          # operand: constant index  → push constants[idx]
    NULL = 1           # push فراغ
    TRUE = 2           # push صح
    FALSE = 3          # push غلط
    POP = 4            # discard top of stack

    DEF_GLOBAL = 5     # operand: name const idx   → globals[name] = pop()
    GET_GLOBAL = 6     # operand: name const idx   → push globals[name]
    SET_GLOBAL = 7     # operand: name const idx   → globals[name] = pop()
    GET_LOCAL = 8      # operand: slot             → push frame.slots[slot]
    SET_LOCAL = 9      # operand: slot             → frame.slots[slot] = pop()

    ADD = 10
    SUB = 11
    MUL = 12
    DIV = 13
    MOD = 14
    NEG = 15

    EQ = 16
    NEQ = 17
    LT = 18
    GT = 19
    LE = 20
    GE = 21

    PRINT = 22

    JUMP = 23          # operand: absolute target
    JUMP_IF_FALSE = 24  # operand: absolute target (pops condition)
    JUMP_IF_TRUE = 25   # operand: absolute target (pops condition)

    CALL = 26          # operand: argument count
    RETURN = 27
