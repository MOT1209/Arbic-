"""The AlArabiya standard builtins.

Each builtin is a :class:`NativeFunction` registered into a fresh global
:class:`Environment` by :func:`make_global_env`.  Builtins report problems by
raising :class:`BuiltinError`; the interpreter attaches the call-site location
and turns it into a normal diagnostic.
"""

from __future__ import annotations

from al_arabiya.runtime.interpreter.environment import Environment
from al_arabiya.runtime.values import (
    BuiltinError,
    NativeFunction,
    Value,
    describe_value,
    format_value,
    is_truthy,
)

__all__ = ["BUILTINS", "make_global_env"]


def _b_len(value: Value) -> Value:
    if isinstance(value, (str, list, dict)):
        return len(value)
    raise BuiltinError(
        f"'طول' بيشتغل على النص والقوائم والقواميس، مش على {describe_value(value)}",
        'جرّب: طول("أهلا") أو طول([1، 2، 3])',
    )


def _b_type(value: Value) -> Value:
    return describe_value(value)


def _b_number(value: Value) -> Value:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError:
            try:
                return float(text)
            except ValueError:
                raise BuiltinError(
                    f"مينفعش أحوّل '{value}' لرقم",
                    'لازم يكون النص رقم زي "12" أو "3.5"',
                ) from None
    raise BuiltinError(
        f"مينفعش أحوّل {describe_value(value)} لرقم",
        "حوّل النصوص والأرقام والقيم المنطقية بس",
    )


def _b_text(value: Value) -> Value:
    return format_value(value)


def _b_bool(value: Value) -> Value:
    return is_truthy(value)


def _b_input(*args: Value) -> Value:
    if len(args) > 1:
        raise BuiltinError(
            "'اقرأ' بتاخد رسالة واحدة على الأكثر",
            'جرّب: اقرأ("اكتب اسمك: ")',
        )
    prompt = format_value(args[0]) if args else ""
    try:
        return input(prompt)
    except EOFError:
        raise BuiltinError("مفيش إدخال متاح", "شغّل البرنامج في وضع تفاعلي") from None


def _b_abs(value: Value) -> Value:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BuiltinError(
            f"'مطلق' بيشتغل على الأرقام بس، مش على {describe_value(value)}",
            "جرّب: مطلق(-5)",
        )
    return abs(value)


def _b_round(value: Value) -> Value:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BuiltinError(
            f"'قرّب' بيشتغل على الأرقام بس، مش على {describe_value(value)}",
            "جرّب: قرّب(3.7)",
        )
    return round(value)


#: The full builtin table (name → native function).
BUILTINS: tuple[NativeFunction, ...] = (
    NativeFunction("طول", 1, _b_len),
    NativeFunction("نوع", 1, _b_type),
    NativeFunction("رقم", 1, _b_number),
    NativeFunction("نص", 1, _b_text),
    NativeFunction("منطقي", 1, _b_bool),
    NativeFunction("اقرأ", -1, _b_input),
    NativeFunction("مطلق", 1, _b_abs),
    NativeFunction("قرّب", 1, _b_round),
)


def make_global_env() -> Environment:
    """Build a fresh global scope pre-populated with every builtin."""
    env = Environment()
    for builtin in BUILTINS:
        env.define(builtin.name, builtin)
    return env
