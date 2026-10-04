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

    # --- collections ---
    BUILD_LIST = 28    # operand: element count   → push list of the top n values
    BUILD_MAP = 29     # operand: entry count     → push dict from the top 2n values
    INDEX_GET = 30     # pop index, target        → push target[index]
    INDEX_SET = 31     # pop value, index, target → target[index] = value

    # --- for-each (iterates list/str/map-keys; state lives on the stack) ---
    FOR_PREP = 32      # pop iterable → push (items, 0)
    FOR_NEXT = 33      # operand: exit target; else push next item (to be stored)
    FOR_POP = 34       # drop (items, index) — used by break

    # --- repeat (كرر) ---
    REP_PREP = 35      # pop count → push remaining
    REP_NEXT = 36      # operand: exit target; else decrement remaining
    REP_POP = 37       # drop remaining — used by break

    # --- exceptions ---
    SETUP_EXCEPT = 38  # operand: catch target
    SETUP_FINALLY = 39  # operand: finally target
    POP_BLOCK = 40     # pop the top exception block
    THROW = 41         # pop value → raise it
    PUSH_FINALLY_OK = 42  # push the "normal completion" marker before a finally
    END_FINALLY = 43   # pop marker; re-raise if it carries an exception
