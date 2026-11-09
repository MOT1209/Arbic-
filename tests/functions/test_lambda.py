"""Tests for anonymous functions (lambda expressions)."""

from __future__ import annotations

import pytest

from al_arabiya.compiler.ast.nodes import (
    LambdaExpression,
    ReturnStatement,
    VariableDeclaration,
)
from al_arabiya.compiler.checker import check_types
from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag
from al_arabiya.compiler.diagnostics.errors import ArabiyaRuntimeError, ErrorCode
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.runtime.interpreter.interpreter import Interpreter
from al_arabiya.vm.compiler import unsupported_reason


def parse(source: str):
    result = compile_source(source, "test.arb")
    assert result.program is not None, [(d.code, d.message) for d in result.diagnostics]
    return result.program


def parse_errors(source: str) -> list[str]:
    result = compile_source(source, "test.arb")
    return [d.code for d in result.diagnostics if d.is_error]


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


# ------------------------------------------------------------------ parsing


def test_parse_lambda_as_expression():
    program = parse("خلي مربع = دالة (س)\n    رجّع س في س\nخلاص")
    declaration = program.body[0]
    assert isinstance(declaration, VariableDeclaration)
    assert isinstance(declaration.initializer, LambdaExpression)
    assert [p.name for p in declaration.initializer.parameters] == ["س"]
    assert isinstance(declaration.initializer.body[0], ReturnStatement)


def test_lambda_body_must_start_on_a_new_line():
    assert ErrorCode.EXPECTED_NEWLINE in parse_errors(
        "خلي ف = دالة (س) رجّع س\nخلاص"
    )


# --------------------------------------------------------------- evaluation


def test_lambda_runs_and_closes_over_scope():
    source = (
        "دالة عداد ()\n"
        "    خلي ن = 0\n"
        "    رجّع دالة ()\n"
        "        ن = ن زائد 1\n"
        "        رجّع ن\n"
        "    خلاص\n"
        "خلاص\n"
        "خلي ع = عداد()\n"
        "اطبع ع()\n"
        "اطبع ع()"
    )
    assert run(source) == "1\n2"


def test_lambda_is_a_first_class_value():
    source = (
        "دالة طبّق (عملية، قيمة)\n"
        "    رجّع عملية(قيمة)\n"
        "خلاص\n"
        "خلي ضعف = دالة (س)\n"
        "    رجّع س في 2\n"
        "خلاص\n"
        "اطبع طبّق(ضعف، 21)"
    )
    assert run(source) == "42"


def test_lambda_with_annotations():
    source = (
        "خلي زائد_واحد = دالة (س : رقم) : رقم\n"
        "    رجّع س زائد 1\n"
        "خلاص\n"
        "اطبع زائد_واحد(41)"
    )
    assert run(source) == "42"


def test_lambda_prints_as_anonymous_function():
    assert run("اطبع دالة ()\n    رجّع 1\nخلاص") == "<دالة مجهولة>"


def test_lambda_arity_mismatch():
    error = runtime_error("خلي ف = دالة (أ، ب)\n    رجّع أ\nخلاص\nاطبع ف(1)")
    assert error.diagnostic.code == ErrorCode.ARITY_MISMATCH


# --------------------------------------------------------------- type check


def test_type_checker_checks_the_lambda_body():
    program = parse("خلي ف = دالة (س : رقم) : نص\n    رجّع س\nخلاص")
    codes = [d.code for d in check_types(program) if d.is_error]
    assert ErrorCode.TYPE_MISMATCH in codes


def test_type_checker_accepts_a_well_typed_lambda():
    program = parse("خلي ف = دالة (س : رقم) : رقم\n    رجّع س زائد 1\nخلاص")
    assert [d for d in check_types(program) if d.is_error] == []


# ---------------------------------------------------------------------- vm


def test_vm_falls_back_for_lambdas():
    reason = unsupported_reason(parse("خلي ف = دالة ()\n    رجّع 1\nخلاص"))
    assert reason is not None
    assert "دالة مجهولة" in reason
