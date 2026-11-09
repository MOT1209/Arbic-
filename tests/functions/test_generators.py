"""Tests for lazy generators (``انتج``)."""

from __future__ import annotations

import pytest

from al_arabiya.compiler.ast.nodes import FunctionDeclaration, YieldStatement
from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.runtime.interpreter.interpreter import Interpreter
from al_arabiya.vm.compiler import unsupported_reason


def parse(source: str):
    result = compile_source(source, "test.arb")
    assert result.program is not None, [(d.code, d.message) for d in result.diagnostics]
    return result.program


def run(source: str) -> str:
    program = parse(source)
    lines: list[str] = []
    Interpreter(diagnostics=DiagnosticBag(), write=lines.append).run(program)
    return "\n".join(lines)


def runtime_error(source: str) -> ArabiyaRuntimeError:
    program = parse(source)
    with pytest.raises(ArabiyaRuntimeError) as excinfo:
        Interpreter(write=lambda _text: None).run(program)
    return excinfo.value


def test_parse_yield_statement():
    program = parse("دالة أرقام ()\n    انتج 1\nخلاص")
    function = program.body[0]
    assert isinstance(function, FunctionDeclaration)
    assert isinstance(function.body[0], YieldStatement)


def test_generator_is_consumed_by_foreach():
    source = (
        "دالة أرقام ()\n"
        "    انتج 1\n"
        "    انتج 2\n"
        "    انتج 3\n"
        "خلاص\n"
        "لكل ن في أرقام()\n"
        "    اطبع ن\n"
        "خلاص"
    )
    assert run(source) == "1\n2\n3"


def test_generator_is_lazy_until_first_iteration():
    source = (
        "دالة ع ()\n"
        '    اطبع "بدأ"\n'
        "    انتج 1\n"
        "خلاص\n"
        "خلي م = ع()\n"
        'اطبع "قبل"\n'
        "لكل س في م\n"
        "    اطبع س\n"
        "خلاص"
    )
    assert run(source) == "قبل\nبدأ\n1"


def test_yield_inside_a_loop():
    source = (
        "دالة زوجية (ن)\n"
        "    خلي ع = 0\n"
        "    طالما ع أصغر من ن\n"
        "        انتج ع\n"
        "        ع = ع زائد 2\n"
        "    خلاص\n"
        "خلاص\n"
        "لكل س في زوجية(6)\n"
        "    اطبع س\n"
        "خلاص"
    )
    assert run(source) == "0\n2\n4"


def test_return_ends_the_generator():
    source = (
        "دالة م ()\n"
        "    انتج 1\n"
        "    رجّع\n"
        "    انتج 2\n"
        "خلاص\n"
        "لكل س في م()\n"
        "    اطبع س\n"
        "خلاص"
    )
    assert run(source) == "1"


def test_finally_runs_when_the_generator_is_exhausted():
    source = (
        "دالة م ()\n"
        "    حاول\n"
        "        انتج 1\n"
        "    أخيرا\n"
        '        اطبع "خلص"\n'
        "    خلاص\n"
        "خلاص\n"
        "لكل س في م()\n"
        "    اطبع س\n"
        "خلاص"
    )
    assert run(source) == "1\nخلص"


def test_generator_prints_as_generator():
    assert run("دالة م ()\n    انتج 1\nخلاص\nاطبع م()") == "<مولّد>"


def test_yield_outside_a_generator_is_rejected():
    assert runtime_error("انتج 1").diagnostic.code == ErrorCode.YIELD_OUTSIDE_GENERATOR


def test_generator_methods_are_not_supported():
    source = (
        "صنف ع\n"
        "    دالة قيم ()\n"
        "        انتج 1\n"
        "    خلاص\n"
        "خلاص"
    )
    error = runtime_error(source + "\nخلي ك = ع()\nلكل س في ك.قيم()\n    اطبع س\nخلاص")
    assert error.diagnostic.code == ErrorCode.YIELD_OUTSIDE_GENERATOR


def test_vm_falls_back_for_generators():
    reason = unsupported_reason(parse("دالة م ()\n    انتج 1\nخلاص"))
    assert reason is not None
    assert "انتج" in reason
