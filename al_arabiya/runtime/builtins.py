"""The AlArabiya standard builtins.

Each builtin is a :class:`NativeFunction` registered into a fresh global
:class:`Environment` by :func:`make_global_env`.  Builtins report problems by
raising :class:`BuiltinError`; the interpreter attaches the call-site location
and turns it into a normal diagnostic.
"""

from __future__ import annotations

import math

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


def _as_int(value: Value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BuiltinError(
            f"'{name}' محتاجة رقم صحيح، مش {describe_value(value)}",
            "استخدم رقم صحيح زي 3",
        )
    return value


def _as_list(value: Value, name: str) -> list[Value]:
    if not isinstance(value, list):
        raise BuiltinError(
            f"'{name}' بتشتغل على القوائم بس، مش على {describe_value(value)}",
            "مرّر قائمة زي [1، 2، 3]",
        )
    return value


def _as_str(value: Value, name: str) -> str:
    if not isinstance(value, str):
        raise BuiltinError(
            f"'{name}' بتشتغل على النصوص بس، مش على {describe_value(value)}",
            'مرّر نص زي "أهلا"',
        )
    return value


def _numbers(items: list[Value], name: str) -> list[float]:
    out: list[float] = []
    for item in items:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise BuiltinError(
                f"'{name}' محتاجة قائمة أرقام، لكن فيها {describe_value(item)}",
                "تأكد إن كل عناصر القائمة أرقام",
            )
        out.append(item)
    return out


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


# ---------------------------------------------------------------- lists


def _b_append(collection: Value, item: Value) -> Value:
    items = _as_list(collection, "اضف")
    items.append(item)
    return items


def _b_remove_at(collection: Value, index: Value) -> Value:
    items = _as_list(collection, "احذف")
    position = _as_int(index, "احذف")
    actual = position + len(items) if position < 0 else position
    if actual < 0 or actual >= len(items):
        raise BuiltinError(
            f"الفهرس {position} بره حدود القائمة (الطول {len(items)})",
            "استخدم فهرس صحيح جوّه حدود القائمة",
        )
    return items.pop(actual)


def _b_range(*args: Value) -> Value:
    if len(args) == 1:
        start, stop = 0, _as_int(args[0], "مدى")
    elif len(args) == 2:
        start, stop = _as_int(args[0], "مدى"), _as_int(args[1], "مدى")
    else:
        raise BuiltinError(
            "'مدى' بتاخد رقم واحد أو رقمين",
            "مثال: مدى(5) أو مدى(2، 6)",
        )
    return list(range(start, stop))


def _b_sum(collection: Value) -> Value:
    numbers = _numbers(_as_list(collection, "مجموع"), "مجموع")
    total: float = 0
    for number in numbers:
        total += number
    return total


def _b_max(collection: Value) -> Value:
    numbers = _numbers(_as_list(collection, "اكبر"), "اكبر")
    if not numbers:
        raise BuiltinError("'اكبر' محتاجة قائمة فيها عنصر على الأقل")
    return max(numbers)


def _b_min(collection: Value) -> Value:
    numbers = _numbers(_as_list(collection, "اصغر"), "اصغر")
    if not numbers:
        raise BuiltinError("'اصغر' محتاجة قائمة فيها عنصر على الأقل")
    return min(numbers)


def _b_sort(collection: Value) -> Value:
    items = _as_list(collection, "رتب")
    out: list[Value] = []
    if all(isinstance(x, str) for x in items):
        out.extend(sorted(items, key=lambda x: str(x)))
    else:
        out.extend(sorted(_numbers(items, "رتب")))
    return out


def _b_reverse(collection: Value) -> Value:
    if isinstance(collection, str):
        return collection[::-1]
    items = _as_list(collection, "اعكس")
    return list(reversed(items))


def _b_contains(container: Value, item: Value) -> Value:
    if isinstance(container, str):
        return _as_str(item, "يحتوي") in container
    if isinstance(container, list):
        return item in container
    if isinstance(container, dict):
        return item in container
    raise BuiltinError(
        f"'يحتوي' بتشتغل على النص والقائمة والقاموس، مش على {describe_value(container)}",
    )


def _b_keys(mapping: Value) -> Value:
    if not isinstance(mapping, dict):
        raise BuiltinError(
            f"'مفاتيح' بتشتغل على القواميس بس، مش على {describe_value(mapping)}",
        )
    return list(mapping.keys())


def _b_values(mapping: Value) -> Value:
    if not isinstance(mapping, dict):
        raise BuiltinError(
            f"'قيم' بتشتغل على القواميس بس، مش على {describe_value(mapping)}",
        )
    return list(mapping.values())


# ---------------------------------------------------------------- strings


def _b_split(text: Value, separator: Value) -> Value:
    source = _as_str(text, "قسّم")
    sep = _as_str(separator, "قسّم")
    if sep == "":
        raise BuiltinError("الفاصل في 'قسّم' مينفعش يكون فاضي")
    return list(source.split(sep))


def _b_join(parts: Value, separator: Value) -> Value:
    items = _as_list(parts, "ادمج")
    sep = _as_str(separator, "ادمج")
    return sep.join(format_value(item) for item in items)


def _b_replace(text: Value, old: Value, new: Value) -> Value:
    return _as_str(text, "استبدل").replace(_as_str(old, "استبدل"), _as_str(new, "استبدل"))


# ---------------------------------------------------------------- math


def _b_sqrt(value: Value) -> Value:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BuiltinError(f"'جذر' بتشتغل على الأرقام بس، مش على {describe_value(value)}")
    if value < 0:
        raise BuiltinError("مينفعش آخد جذر رقم سالب", "استخدم رقم موجب أو صفر")
    return math.sqrt(value)


def _b_power(base: Value, exponent: Value) -> Value:
    if isinstance(base, bool) or not isinstance(base, (int, float)):
        raise BuiltinError(f"'اس' محتاجة أرقام، مش {describe_value(base)}")
    if isinstance(exponent, bool) or not isinstance(exponent, (int, float)):
        raise BuiltinError(f"'اس' محتاجة أرقام، مش {describe_value(exponent)}")
    return base**exponent


#: The full builtin table (name → native function).
BUILTINS: tuple[NativeFunction, ...] = (
    # core
    NativeFunction("طول", 1, _b_len),
    NativeFunction("نوع", 1, _b_type),
    NativeFunction("رقم", 1, _b_number),
    NativeFunction("نص", 1, _b_text),
    NativeFunction("منطقي", 1, _b_bool),
    NativeFunction("اقرأ", -1, _b_input),
    # math
    NativeFunction("مطلق", 1, _b_abs),
    NativeFunction("قرّب", 1, _b_round),
    NativeFunction("جذر", 1, _b_sqrt),
    NativeFunction("اس", 2, _b_power),
    # lists
    NativeFunction("اضف", 2, _b_append),
    NativeFunction("احذف", 2, _b_remove_at),
    NativeFunction("مدى", -1, _b_range),
    NativeFunction("مجموع", 1, _b_sum),
    NativeFunction("اكبر", 1, _b_max),
    NativeFunction("اصغر", 1, _b_min),
    NativeFunction("رتب", 1, _b_sort),
    NativeFunction("اعكس", 1, _b_reverse),
    NativeFunction("يحتوي", 2, _b_contains),
    NativeFunction("مفاتيح", 1, _b_keys),
    NativeFunction("قيم", 1, _b_values),
    # strings
    NativeFunction("قسّم", 2, _b_split),
    NativeFunction("ادمج", 2, _b_join),
    NativeFunction("استبدل", 3, _b_replace),
)


def make_global_env() -> Environment:
    """Build a fresh global scope pre-populated with every builtin."""
    env = Environment()
    for builtin in BUILTINS:
        env.define(builtin.name, builtin)
    return env
