"""Emission extern callables must not escape as first-class values (#2842)."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl.compiler import compile_source  # noqa: E402
from revl.errors import RevlError  # noqa: E402


_HOST = "extern emission fn send(x: Str) -> Int = @py { return 1 }\n"
_SERVICE = "service Ops { emission fn invoke() -> Int }\n"

_CASES = [
    (
        "bound-local",
        'let f = send\nreturn f("x")',
        "",
        "send",
    ),
    (
        "function-typed-argument",
        'return apply(send, "x")',
        "fn apply(f: (Str) -> Int, x: Str) -> Int { return f(x) }\n",
        "send",
    ),
    (
        "helper-returns-callable",
        'let f = get_send()\nlet first = f("one")\nreturn f("two")',
        "fn get_send() -> (Str) -> Int { return send }\n",
        "send",
    ),
    (
        "helper-reaching-emission-used-as-value",
        'let f = bill\nreturn f("x")',
        "fn bill(x: Str) -> Int { return send(x) }\n",
        "bill",
    ),
    (
        "arrow-captures-callable",
        'let get_send = () => send\nlet f = get_send()\nreturn f("x")',
        "",
        "send",
    ),
]


def _program(body: str, functions: str = "") -> str:
    return (
        _HOST
        + functions
        + _SERVICE
        + "component C provides ops: Ops {\n"
        + "  provide ops {\n"
        + "    fn invoke() {\n"
        + f"      {body}\n"
        + "    }\n"
        + "  }\n"
        + "}\n"
    )


@pytest.mark.parametrize(
    ("_name", "body", "functions", "callable_name"),
    _CASES,
    ids=[case[0] for case in _CASES],
)
def test_emission_reaching_callables_are_refused_by_name(
    _name, body, functions, callable_name
):
    with pytest.raises(RevlError) as caught:
        compile_source(_program(body, functions), "emission-values-2842.rvl")

    assert caught.value.code == "G4"
    assert caught.value.message == (
        f"call to emission `{callable_name}` must be marked `emit` (G4)"
    )


def test_emit_marked_emission_still_uses_the_python_recording_seam():
    source = _program('return emit send("x")')
    ir = compile_source(source, "emission-values-2842-control.rvl")
    spec = importlib.util.spec_from_file_location(
        "pyemit_emission_values_2842", ROOT / "backends/python/emit.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert "_revl_extern_emit(_revl_ctx, 'send', send," in module.emit(ir)


def test_non_emission_extern_values_remain_usable():
    source = (
        "extern pure fn format_name(x: Str) -> Str = @py { return x }\n"
        + _SERVICE
        + "component C provides ops: Ops {\n"
        + "  provide ops {\n"
        + '    fn invoke() { let f = format_name return f("x") }\n'
        + "  }\n"
        + "}\n"
    )

    compile_source(source, "emission-values-2842-pure-control.rvl")


def test_scoped_callable_shadowing_an_emission_name_is_not_misclassified():
    source = (
        _HOST
        + "service Ops { emission fn invoke(send: (Str) -> Int) -> Int }\n"
        + "component C provides ops: Ops {\n"
        + "  provide ops { fn invoke(send) { let alias = send return 1 } }\n"
        + "}\n"
    )

    compile_source(source, "emission-values-2842-shadow-control.rvl")
