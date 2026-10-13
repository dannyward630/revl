"""Issue #2311: a call through a function-typed parameter took the signature of
a same-named top-level fn from another file of the composition.

The lowering read the program-wide signature table for every `name(...)` call,
without asking whether `name` is a local binding. A private `fn step` in
another file then decided the arity and the parameter types of `step(x)` inside
`fn apply(x: Int, step: (Int) -> Int)`, where `step` is the parameter:

  * more parameters than the call gives: the default-argument fill found no
    default and the compile stopped with `unexpected expression in fn body` at
    line 1 of the caller's file;
  * the same number of parameters: the compile succeeded, but the argument was
    annotated with the other fn's parameter type, so a `Float` there emitted
    `step(float(x))`.

The checker already resolved `step` to the parameter. Lowering now types a
call to a local binding from that binding's own declared function type.

Each composition is measured by RUNNING the emitted program's `test` block on
the py and ts tiers, so a fix that only silences the compile error, or only
changes the emitted text, does not pass.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from revl import compile_files  # noqa: E402
from revl.errors import RevlError  # noqa: E402
from revl.test import RUNNERS  # noqa: E402

# The caller's file. `inc` is passed as the `step` argument; the rendered
# result tells an Int answer ("4") from a Float one ("4.0") on every tier.
_CALLER = '''fn apply(x: Int, step: (Int) -> Int) -> Int {
  return step(x)
}

fn inc(n: Int) -> Int {
  return n + 1
}

test "a call through a fn-typed parameter uses the parameter's type" {
  assert `${apply(3, inc)}` == "4"
}
'''

# Mode 1: a same-named private fn with MORE parameters than the call gives.
_WIDER = '''fn step(a: Int, b: Int, c: Int) -> Int {
  return a + b + c
}
'''

# Mode 2: a same-named private fn with the same arity and a Float parameter.
_FLOAT = '''fn step(a: Float) -> Float {
  return a
}
'''

# The parameter's OWN type is still honoured: an Int argument to a
# `(Float) -> Float` parameter widens, exactly as it does for a top-level fn.
# Without the mark the ts tier passed the Int through as a BigInt, so `same`
# returned `3n` and compared unequal to `3.0`.
_LOCAL_FLOAT = '''fn apply(x: Int, f: (Float) -> Float) -> Float {
  return f(x)
}

fn same(v: Float) -> Float {
  return v
}

test "a fn-typed parameter widens by its own declared type" {
  assert apply(3, same) == 3.0
}
'''

_MODES = {"more_params": _WIDER, "same_arity_float": _FLOAT}


def _compose(tmp_path, *sources):
    paths = []
    for i, source in enumerate(sources):
        path = tmp_path / f"f{i}.rvl"
        path.write_text(source)
        paths.append(str(path))
    return compile_files(paths)


def _apply_call(ir):
    """The lowered `return step(x)` statement of `apply`."""
    apply = next(f for f in ir["functions"] if f["name"] == "apply")
    return apply["body"][-1]["expr"]


@pytest.mark.parametrize("mode", sorted(_MODES))
def test_call_takes_the_parameter_type_not_the_other_file(tmp_path, mode):
    ir = _compose(tmp_path, _CALLER, _MODES[mode])
    call = _apply_call(ir)
    assert call["kind"] == "call"
    assert call["callee"] == {"kind": "var", "name": "step"}
    assert len(call["args"]) == 1
    assert "widen" not in call["args"][0]


def test_local_fn_type_still_marks_its_own_widening(tmp_path):
    ir = _compose(tmp_path, _LOCAL_FLOAT)
    call = _apply_call(ir)
    assert call["args"][0].get("widen") == "Float"


def test_missing_argument_without_default_names_the_callee_and_line():
    # Defensive path: if a call ever reaches lowering short of a parameter
    # that has no default, the error names the callee at the call's line,
    # never `line 1`. The checker refuses such a call, so the signature table
    # is handed to the lowering directly.
    from revl.lower import FNS_KEY, _lower_pure_expr
    from revl.parser import ExprCall, ExprLit, ExprVar

    types = {FNS_KEY: {"g": {"params": ["Int", "Int"], "defaults": [None, None]}}}
    call = ExprCall(ExprVar("g", 7), [ExprLit(1, 7)], 7)
    with pytest.raises(RevlError) as caught:
        _lower_pure_expr(call, {}, {"g"}, {}, "caller.rvl", {}, types)
    error = caught.value
    assert error.line == 7
    assert "`g`" in str(error)
    assert "parameter 2 has no default" in str(error)


@pytest.mark.parametrize("tier", ["py", "ts"])
@pytest.mark.parametrize("mode", sorted(_MODES))
def test_composition_runs(tmp_path, tier, mode):
    status, message = RUNNERS[tier](_compose(tmp_path, _CALLER, _MODES[mode]))
    if status == "skip":
        pytest.skip(f"{tier}: {message}")
    assert status == "pass", f"{tier} failed: {message}"


# ts only: the py tier compares an Int equal to a Float, so it passed before
# the mark as well and would prove nothing here.
@pytest.mark.parametrize("tier", ["ts"])
def test_local_fn_type_widening_runs(tmp_path, tier):
    status, message = RUNNERS[tier](_compose(tmp_path, _LOCAL_FLOAT))
    if status == "skip":
        pytest.skip(f"{tier}: {message}")
    assert status == "pass", f"{tier} failed: {message}"


def test_compile_error_is_not_line_one(tmp_path):
    # The mode-1 composition used to raise `f0.rvl:1: unexpected expression in
    # fn body`. It now compiles; keep the old failure from coming back as any
    # RevlError at all.
    try:
        _compose(tmp_path, _CALLER, _WIDER)
    except RevlError as error:  # pragma: no cover - the regression itself
        pytest.fail(f"composition refused: {error}")
