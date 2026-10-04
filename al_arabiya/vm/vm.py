"""The AlArabiya stack virtual machine: executes compiled bytecode.

Semantics mirror the tree-walking interpreter exactly (same operators, the
same runtime error codes and spans), so the two backends are interchangeable
for the core language the compiler supports.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeGuard

from al_arabiya.compiler.diagnostics.diagnostics import Diagnostic, Severity
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.lexer.positions import Position, Span
from al_arabiya.runtime.builtins import BUILTINS
from al_arabiya.runtime.values import (
    NULL,
    BuiltinError,
    NativeFunction,
    Value,
    describe_value,
    format_value,
    is_truthy,
)
from al_arabiya.vm.chunk import VMFunction
from al_arabiya.vm.opcodes import Op

__all__ = ["VM", "run_function"]

_ZERO_SPAN = Span(Position(0, 1, 1), Position(0, 1, 1))


class _Frame:
    __slots__ = ("function", "ip", "slots")

    def __init__(self, function: VMFunction, slots: list[Value]) -> None:
        self.function = function
        self.ip = 0
        self.slots = slots


class VM:
    """Executes a compiled ``<main>`` function."""

    def __init__(self, write: Callable[[str], None] = print) -> None:
        self.write = write
        self.globals: dict[str, Value] = {builtin.name: builtin for builtin in BUILTINS}

    def run(self, main: VMFunction) -> None:
        stack: list[Value] = []
        frames: list[_Frame] = [_Frame(main, [NULL] * main.local_count)]
        frame = frames[-1]
        code = frame.function.chunk.code
        constants = frame.function.chunk.constants

        while True:
            op_index = frame.ip
            op = code[op_index]
            frame.ip += 1

            if op == Op.CONST:
                stack.append(constants[code[frame.ip]])
                frame.ip += 1
            elif op == Op.NULL:
                stack.append(NULL)
            elif op == Op.TRUE:
                stack.append(True)
            elif op == Op.FALSE:
                stack.append(False)
            elif op == Op.POP:
                stack.pop()
            elif op == Op.DEF_GLOBAL:
                self.globals[_name(constants[code[frame.ip]])] = stack.pop()
                frame.ip += 1
            elif op == Op.GET_GLOBAL:
                name = _name(constants[code[frame.ip]])
                frame.ip += 1
                if name not in self.globals:
                    raise self._error(
                        ErrorCode.UNDEFINED_VARIABLE,
                        f"المتغير '{name}' مش معرّف",
                        frame.function.chunk.spans[op_index],
                        f"اكتب 'خلي {name} = ...' الأول",
                    )
                stack.append(self.globals[name])
            elif op == Op.SET_GLOBAL:
                self.globals[_name(constants[code[frame.ip]])] = stack.pop()
                frame.ip += 1
            elif op == Op.GET_LOCAL:
                stack.append(frame.slots[code[frame.ip]])
                frame.ip += 1
            elif op == Op.SET_LOCAL:
                frame.slots[code[frame.ip]] = stack.pop()
                frame.ip += 1
            elif op == Op.ADD:
                stack.append(self._add(stack, frame.function.chunk.spans[op_index]))
            elif op in (Op.SUB, Op.MUL, Op.DIV, Op.MOD):
                stack.append(self._arith(op, stack, frame.function.chunk.spans[op_index]))
            elif op == Op.NEG:
                value = stack.pop()
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise self._error(
                        ErrorCode.TYPE_ERROR,
                        "علامة الناقص بتشتغل على الأرقام بس",
                        frame.function.chunk.spans[op_index],
                        "اكتب رقم بعد الناقص",
                    )
                stack.append(-value)
            elif op == Op.EQ:
                right = stack.pop()
                stack.append(stack.pop() == right)
            elif op == Op.NEQ:
                right = stack.pop()
                stack.append(stack.pop() != right)
            elif op in (Op.LT, Op.GT, Op.LE, Op.GE):
                stack.append(self._compare(op, stack, frame.function.chunk.spans[op_index]))
            elif op == Op.PRINT:
                self.write(format_value(stack.pop()))
            elif op == Op.JUMP:
                frame.ip = code[frame.ip]
            elif op == Op.JUMP_IF_FALSE:
                target = code[frame.ip]
                frame.ip += 1
                if not is_truthy(stack.pop()):
                    frame.ip = target
            elif op == Op.JUMP_IF_TRUE:
                target = code[frame.ip]
                frame.ip += 1
                if is_truthy(stack.pop()):
                    frame.ip = target
            elif op == Op.CALL:
                argc = code[frame.ip]
                frame.ip += 1
                new_frame = self._call(stack, argc, frame.function.chunk.spans[op_index])
                if new_frame is not None:
                    frames.append(new_frame)
                    frame = new_frame
                    code = frame.function.chunk.code
                    constants = frame.function.chunk.constants
            elif op == Op.RETURN:
                result = stack.pop()
                frames.pop()
                if not frames:
                    return
                frame = frames[-1]
                code = frame.function.chunk.code
                constants = frame.function.chunk.constants
                stack.append(result)
            else:  # pragma: no cover
                raise self._error(
                    ErrorCode.TYPE_ERROR,
                    f"تعليمة غير معروفة: {op}",
                    frame.function.chunk.spans[op_index],
                )

    # --------------------------------------------------------------- helpers

    def _call(self, stack: list[Value], argc: int, span: Span | None) -> _Frame | None:
        arguments = [stack.pop() for _ in range(argc)][::-1]
        callee = stack.pop()
        if isinstance(callee, NativeFunction):
            if callee.arity >= 0 and len(arguments) != callee.arity:
                raise self._arity_error(callee.name, callee.arity, len(arguments), span)
            try:
                stack.append(callee.fn(*arguments))
            except BuiltinError as exc:
                raise self._error(
                    ErrorCode.BUILTIN_ERROR, exc.message, span, exc.suggestion
                ) from None
            return None
        if isinstance(callee, VMFunction):
            if len(arguments) != callee.arity:
                raise self._arity_error(callee.name, callee.arity, len(arguments), span)
            slots: list[Value] = arguments + [NULL] * (callee.local_count - callee.arity)
            return _Frame(callee, slots)
        raise self._error(
            ErrorCode.NOT_CALLABLE,
            f"{describe_value(callee)} مش دالة عشان تناديها",
            span,
            "نادِ دالة معرّفة بـ 'دالة' أو دالة مدمجة زي 'طول'",
        )

    def _add(self, stack: list[Value], span: Span | None) -> Value:
        right = stack.pop()
        left = stack.pop()
        if isinstance(left, str) or isinstance(right, str):
            return format_value(left) + format_value(right)
        if _is_number(left) and _is_number(right):
            return left + right
        raise self._error(
            ErrorCode.TYPE_ERROR,
            f"مينفعش أجمع {describe_value(left)} مع {describe_value(right)}",
            span,
            "الجمع بيشتغل بين رقمين، أو مع نص للدمج",
        )

    def _arith(self, op: int, stack: list[Value], span: Span | None) -> Value:
        right = stack.pop()
        left = stack.pop()
        if _is_number(left) and _is_number(right):
            if op == Op.SUB:
                return left - right
            if op == Op.MUL:
                return left * right
            if op == Op.DIV:
                if right == 0:
                    raise self._error(
                        ErrorCode.DIVISION_BY_ZERO, "مينفعش تقسم على صفر", span,
                        "تأكد إن الطرف اليمين مش صفر",
                    )
                return left / right
            if right == 0:  # Op.MOD
                raise self._error(
                    ErrorCode.DIVISION_BY_ZERO, "مينفعش أقسم باقي على صفر", span,
                    "تأكد إن الطرف اليمين مش صفر",
                )
            return left % right
        symbol = {int(Op.SUB): "-", int(Op.MUL): "*", int(Op.DIV): "/", int(Op.MOD): "%"}[op]
        raise self._error(
            ErrorCode.TYPE_ERROR,
            f"مينفعش أعمل '{symbol}' بين {describe_value(left)} و {describe_value(right)}",
            span,
            "العمليات الحسابية محتاجة رقمين",
        )

    def _compare(self, op: int, stack: list[Value], span: Span | None) -> Value:
        right: Any = stack.pop()
        left: Any = stack.pop()
        try:
            if op == Op.LT:
                return bool(left < right)
            if op == Op.GT:
                return bool(left > right)
            if op == Op.LE:
                return bool(left <= right)
            return bool(left >= right)
        except TypeError:
            raise self._error(
                ErrorCode.TYPE_ERROR,
                f"مش هينفع أقارن {describe_value(left)} مع {describe_value(right)}",
                span,
                "قارن نفس النوع مع بعض (رقم برقم، نص بنص)",
            ) from None

    def _arity_error(
        self, name: str, expected: int, got: int, span: Span | None
    ) -> ArabiyaRuntimeError:
        return self._error(
            ErrorCode.ARITY_MISMATCH,
            f"الدالة '{name}' محتاجة {expected} مدخل، بس وصلها {got}",
            span,
            f"نادِ '{name}' بـ {expected} قيمة",
        )

    @staticmethod
    def _error(
        code: ErrorCode, message: str, span: Span | None, suggestion: str | None = None
    ) -> ArabiyaRuntimeError:
        return ArabiyaRuntimeError(
            Diagnostic(
                code=code,
                severity=Severity.ERROR,
                message=message,
                span=span if span is not None else _ZERO_SPAN,
                suggestion=suggestion,
            )
        )


def _is_number(value: Value) -> TypeGuard[int | float]:
    return isinstance(value, (int, float))


def _name(value: Value) -> str:
    assert isinstance(value, str)
    return value


def run_function(main: VMFunction, write: Callable[[str], None] = print) -> None:
    """Execute a compiled ``<main>`` function."""
    VM(write).run(main)
