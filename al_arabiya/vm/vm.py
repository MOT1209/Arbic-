"""The AlArabiya stack virtual machine: executes compiled bytecode.

Semantics mirror the tree-walking interpreter exactly (same operators,
collections, exceptions and runtime error codes/spans), so the two backends
are interchangeable for the language the compiler supports.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeGuard, cast

from al_arabiya.compiler.diagnostics.diagnostics import Diagnostic, Severity
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.lexer.positions import Position, Span
from al_arabiya.runtime.builtins import BUILTINS
from al_arabiya.runtime.values import (
    NULL,
    ArabiyaFunction,
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

# Exception-block kinds stored on a frame.
_EXCEPT = 0
_FINALLY = 1


class _VMRaise(Exception):
    """A value thrown by ``ارم`` inside the VM (catchable by ``حاول``)."""

    def __init__(self, value: Value, span: Span | None) -> None:
        super().__init__()
        self.value = value
        self.span = span


class _ExcMarker:
    """Transient stack marker telling ``END_FINALLY`` to re-raise ``exc``."""

    __slots__ = ("exc",)

    def __init__(self, exc: ArabiyaRuntimeError | _VMRaise) -> None:
        self.exc = exc


_FINALLY_OK = object()  # transient marker: a finally reached by normal flow


class _Frame:
    __slots__ = ("function", "ip", "slots", "blocks")

    def __init__(self, function: VMFunction, slots: list[Any]) -> None:
        self.function = function
        self.ip = 0
        self.slots = slots
        self.blocks: list[tuple[int, int, int]] = []  # (kind, handler_ip, stack_len)


class VM:
    """Executes a compiled ``<main>`` function."""

    def __init__(self, write: Callable[[str], None] = print) -> None:
        self.write = write
        self.globals: dict[str, Value] = {builtin.name: builtin for builtin in BUILTINS}

    def run(self, main: VMFunction) -> None:
        stack: list[Any] = []
        frames: list[_Frame] = [_Frame(main, [NULL] * main.local_count)]
        while True:
            try:
                self._execute(frames, stack)
                return
            except (ArabiyaRuntimeError, _VMRaise) as exc:
                if not self._unwind(exc, frames, stack):
                    raise self._finalize(exc) from None
                # handled: fall through to re-enter _execute at the handler

    # ---------------------------------------------------------- dispatch loop

    def _execute(self, frames: list[_Frame], stack: list[Any]) -> None:
        frame = frames[-1]
        code = frame.function.chunk.code
        constants = frame.function.chunk.constants
        spans = frame.function.chunk.spans

        while True:
            ip = frame.ip
            op = code[ip]
            frame.ip = ip + 1

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
                        spans[ip],
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
                stack.append(self._add(stack, spans[ip]))
            elif op in (Op.SUB, Op.MUL, Op.DIV, Op.MOD):
                stack.append(self._arith(op, stack, spans[ip]))
            elif op == Op.NEG:
                value = stack.pop()
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise self._error(
                        ErrorCode.TYPE_ERROR,
                        "علامة الناقص بتشتغل على الأرقام بس",
                        spans[ip],
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
                stack.append(self._compare(op, stack, spans[ip]))
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
            elif op == Op.BUILD_LIST:
                count = code[frame.ip]
                frame.ip += 1
                items = stack[len(stack) - count :]
                del stack[len(stack) - count :]
                stack.append(items)
            elif op == Op.BUILD_MAP:
                count = code[frame.ip]
                frame.ip += 1
                stack.append(self._build_map(stack, count, spans[ip]))
            elif op == Op.INDEX_GET:
                stack.append(self._index_get(stack, spans[ip]))
            elif op == Op.INDEX_SET:
                self._index_set(stack, spans[ip])
            elif op == Op.FOR_PREP:
                stack.append(self._iterate(stack.pop(), spans[ip]))
                stack.append(0)
            elif op == Op.FOR_NEXT:
                target = code[frame.ip]
                frame.ip += 1
                index = stack[-1]
                items = stack[-2]
                if index >= len(items):
                    stack.pop()
                    stack.pop()
                    frame.ip = target
                else:
                    stack[-1] = index + 1
                    stack.append(items[index])
            elif op == Op.FOR_POP:
                stack.pop()
                stack.pop()
            elif op == Op.REP_PREP:
                stack.append(self._repeat_count(stack.pop(), spans[ip]))
            elif op == Op.REP_NEXT:
                target = code[frame.ip]
                frame.ip += 1
                remaining = stack[-1]
                if remaining <= 0:
                    stack.pop()
                    frame.ip = target
                else:
                    stack[-1] = remaining - 1
            elif op == Op.REP_POP:
                stack.pop()
            elif op == Op.SETUP_EXCEPT:
                frame.blocks.append((_EXCEPT, code[frame.ip], len(stack)))
                frame.ip += 1
            elif op == Op.SETUP_FINALLY:
                frame.blocks.append((_FINALLY, code[frame.ip], len(stack)))
                frame.ip += 1
            elif op == Op.POP_BLOCK:
                frame.blocks.pop()
            elif op == Op.PUSH_FINALLY_OK:
                stack.append(_FINALLY_OK)
            elif op == Op.END_FINALLY:
                marker = stack.pop()
                if isinstance(marker, _ExcMarker):
                    raise marker.exc
            elif op == Op.THROW:
                raise _VMRaise(stack.pop(), spans[ip])
            elif op == Op.CALL:
                argc = code[frame.ip]
                frame.ip += 1
                new_frame = self._call(stack, argc, spans[ip])
                if new_frame is not None:
                    frames.append(new_frame)
                    frame = new_frame
                    code = frame.function.chunk.code
                    constants = frame.function.chunk.constants
                    spans = frame.function.chunk.spans
            elif op == Op.RETURN:
                result = stack.pop()
                frames.pop()
                if not frames:
                    return
                frame = frames[-1]
                code = frame.function.chunk.code
                constants = frame.function.chunk.constants
                spans = frame.function.chunk.spans
                stack.append(result)
            else:  # pragma: no cover
                raise self._error(
                    ErrorCode.TYPE_ERROR, f"تعليمة غير معروفة: {op}", spans[ip]
                )

    # --------------------------------------------------------- exceptions

    def _unwind(
        self, exc: ArabiyaRuntimeError | _VMRaise, frames: list[_Frame], stack: list[Any]
    ) -> bool:
        while frames:
            frame = frames[-1]
            while frame.blocks:
                kind, handler_ip, stack_len = frame.blocks.pop()
                del stack[stack_len:]
                if kind == _EXCEPT:
                    stack.append(self._error_value(exc))
                else:  # _FINALLY
                    stack.append(_ExcMarker(exc))
                frame.ip = handler_ip
                return True
            frames.pop()
        return False

    @staticmethod
    def _error_value(exc: ArabiyaRuntimeError | _VMRaise) -> Value:
        if isinstance(exc, _VMRaise):
            return exc.value
        diagnostic = exc.diagnostic
        error_map: dict[Value, Value] = {
            "الرسالة": diagnostic.message,
            "الكود": str(diagnostic.code),
        }
        if diagnostic.suggestion is not None:
            error_map["اقتراح"] = diagnostic.suggestion
        return error_map

    def _finalize(self, exc: ArabiyaRuntimeError | _VMRaise) -> ArabiyaRuntimeError:
        if isinstance(exc, _VMRaise):
            return self._error(
                ErrorCode.UNCAUGHT_ERROR,
                f"خطأ مرمي مش متمسك: {format_value(exc.value)}",
                exc.span,
                "لفّ الكود بـ 'حاول ... امسك ... خلاص' عشان تمسك الخطأ",
            )
        return exc

    # --------------------------------------------------------------- calls

    def _call(self, stack: list[Any], argc: int, span: Span | None) -> _Frame | None:
        arguments = stack[len(stack) - argc :]
        del stack[len(stack) - argc :]
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
            slots: list[Any] = arguments + [NULL] * (callee.local_count - callee.arity)
            return _Frame(callee, slots)
        raise self._error(
            ErrorCode.NOT_CALLABLE,
            f"{describe_value(callee)} مش دالة عشان تناديها",
            span,
            "نادِ دالة معرّفة بـ 'دالة' أو دالة مدمجة زي 'طول'",
        )

    # --------------------------------------------------------- collections

    def _build_map(self, stack: list[Any], count: int, span: Span | None) -> Value:
        pairs: list[tuple[Any, Any]] = []
        for _ in range(count):
            value = stack.pop()
            key = stack.pop()
            pairs.append((key, value))
        result: dict[Value, Value] = {}
        for key, value in reversed(pairs):
            result[self._hashable_key(key, span)] = value
        return result

    def _index_get(self, stack: list[Any], span: Span | None) -> Value:
        index = stack.pop()
        target = stack.pop()
        if isinstance(target, (list, str)):
            return cast(Value, target[self._list_index(target, index, span)])
        if isinstance(target, dict):
            key = self._hashable_key(index, span)
            if key not in target:
                raise self._error(
                    ErrorCode.KEY_NOT_FOUND,
                    f"المفتاح {format_value(key)} مش موجود في القاموس",
                    span,
                    "تأكد إن المفتاح موجود، أو ضيفه الأول",
                )
            return cast(Value, target[key])
        raise self._error(
            ErrorCode.INVALID_INDEX,
            f"مينفعش أفهرس {describe_value(target)}",
            span,
            "الفهرسة بتشتغل مع القوائم والنصوص والقواميس",
        )

    def _index_set(self, stack: list[Any], span: Span | None) -> None:
        value = stack.pop()
        index = stack.pop()
        target = stack.pop()
        if isinstance(target, list):
            target[self._list_index(target, index, span)] = value
            return
        if isinstance(target, dict):
            target[self._hashable_key(index, span)] = value
            return
        raise self._error(
            ErrorCode.INVALID_INDEX,
            f"مينفعش أحط قيمة جوّه {describe_value(target)}",
            span,
            "الفهرسة بالكتابة بتشتغل مع القوائم والقواميس بس",
        )

    def _list_index(self, sequence: Any, index: Any, span: Span | None) -> int:
        if isinstance(index, bool) or not isinstance(index, int):
            raise self._error(
                ErrorCode.INVALID_INDEX,
                f"الفهرس لازم يكون رقم صحيح، مش {describe_value(index)}",
                span,
                "مثال: ق[0]",
            )
        length = len(sequence)
        position = index + length if index < 0 else index
        if position < 0 or position >= length:
            raise self._error(
                ErrorCode.INDEX_OUT_OF_RANGE,
                f"الفهرس {index} بره حدود العنصر (الطول {length})",
                span,
                "استخدم فهرس بين 0 و (الطول ناقص 1)",
            )
        return position

    def _hashable_key(self, key: Any, span: Span | None) -> Value:
        if isinstance(key, (list, dict, ArabiyaFunction, NativeFunction, VMFunction)):
            label = "دالة" if isinstance(key, VMFunction) else describe_value(key)
            raise self._error(
                ErrorCode.UNHASHABLE_KEY,
                f"مينفعش أستخدم {label} كمفتاح",
                span,
                "المفاتيح لازم تكون نص أو رقم أو منطقي",
            )
        return cast(Value, key)

    def _iterate(self, value: Any, span: Span | None) -> list[Any]:
        if isinstance(value, list):
            return list(value)
        if isinstance(value, str):
            return list(value)
        if isinstance(value, dict):
            return list(value.keys())
        raise self._error(
            ErrorCode.NOT_ITERABLE,
            f"مينفعش أدور على {describe_value(value)} بـ 'لكل'",
            span,
            "استخدم 'لكل' مع قائمة أو نص أو قاموس",
        )

    def _repeat_count(self, count: Any, span: Span | None) -> int:
        if isinstance(count, bool) or not isinstance(count, (int, float)):
            raise self._error(
                ErrorCode.INVALID_REPEAT_COUNT,
                "عدد التكرار لازم يكون رقم",
                span,
                "مثال: كرر 3 مرات",
            )
        return int(count)

    # --------------------------------------------------------------- arithmetic

    def _add(self, stack: list[Any], span: Span | None) -> Value:
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

    def _arith(self, op: int, stack: list[Any], span: Span | None) -> Value:
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

    def _compare(self, op: int, stack: list[Any], span: Span | None) -> Value:
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

    # --------------------------------------------------------------- errors

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


def _is_number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, (int, float))


def _name(value: Any) -> str:
    assert isinstance(value, str)
    return value


def run_function(main: VMFunction, write: Callable[[str], None] = print) -> None:
    """Execute a compiled ``<main>`` function."""
    VM(write).run(main)
