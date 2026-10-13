"""Arithmetic in a component method body means what it means in a `fn`, on go.

Issue #2259, and the go half of issue #2198. The go component emitter's `bin`
arm (`backends/go/emit.py`, `_expr`) wrote every arithmetic operator as the
bare Go one and never read the `operands` annotation the lowering records
(the #2198 lowering fix put it back on component nodes). So in a provide
method:

  * Int `+ - *` wrapped silently at the int64 edge, where docs/arithmetic.md
    says Int overflow traps, and py and ts do trap ("revl: Int overflow");
  * `Int / Int` was Go integer division inside a `float64` method, which does
    not build ("cannot use ... (value of type int64) as float64 value");
  * Float `/` and `%` had the same gap (`%` is not defined on float64 in Go).

The arm now keys on `operands` the way the top-level fn renderer
(`_go_v3_expr`) does: the checked `revlAdd`/`revlSub`/`revlMul` helpers for
Int `+ - *`, `revlDiv` for true division, `math.Mod` for a Float `%`.

Every probe runs the same document on go, py and ts. py and ts are the
reference; go must agree with them.
"""

import pytest

from revl import compile_source
from revl.test import RUNNERS

TIERS = ("go", "py", "ts")

INT_MAX = "9223372036854775807"
INT_MIN = "(0 - 9223372036854775807 - 1)"

_INT_COMPONENT = """
service Bump {
  fn add(x: Int) -> Int
  fn sub(x: Int) -> Int
  fn mul(x: Int) -> Int
}
component B provides bump: Bump {
  provide bump {
    fn add(x) = x + 1
    fn sub(x) = x - 1
    fn mul(x) = x * 2
  }
}
"""

#: method -> the argument that pushes it one past the Int range.
OVERFLOWS = {
    "add": INT_MAX,
    "sub": INT_MIN,
    "mul": INT_MAX,
}

_FLOAT_COMPONENT = """
service Arith {
  fn rem(a: Int, b: Int) -> Int
  fn quo(a: Int, b: Int) -> Float
  fn half(x: Float) -> Float
  fn frem(x: Float) -> Float
}
component A provides arith: Arith {
  provide arith {
    fn rem(a, b) { return a % b }
    fn quo(a, b) { return a / b }
    fn half(x) = x / 2.0
    fn frem(x) = x % 2.0
  }
}
"""

#: The #2198 repro's answers (docs/arithmetic.md): `%` truncates toward zero
#: and `/` is true division, so -7 % 2 is -1 and -7 / 2 is -3.5. A Float `%`
#: is IEEE `fmod`, which takes the dividend's sign: -5.5 % 2.0 is -1.5.
_FLOAT_TEST = _FLOAT_COMPONENT + """
lifecycle test "operands decide the arithmetic" {
  load A
  let r = call arith.rem(0 - 7, 2)
  assert r == 0 - 1
  let q = call arith.quo(0 - 7, 2)
  assert q == 0.0 - 3.5
  let h = call arith.half(5.0)
  assert h == 2.5
  let f = call arith.frem(5.5)
  assert f == 1.5
  let g = call arith.frem(0.0 - 5.5)
  assert g == 0.0 - 1.5
  unload A
}
"""

#: The non-vacuity control: in range, the checked helpers answer the value.
_IN_RANGE_TEST = _INT_COMPONENT + """
lifecycle test "in range" {
  load B
  let a = call bump.add(5)
  assert a == 6
  let s = call bump.sub(5)
  assert s == 4
  let m = call bump.mul(21)
  assert m == 42
  let n = call bump.sub(0 - 9223372036854775807)
  assert n == 0 - 9223372036854775807 - 1
  unload B
}
"""


def _run(tier: str, source: str):
    status, message = RUNNERS[tier](compile_source(source, "comp_arith_2259.rvl"))
    if status == "skip":
        pytest.skip(f"{tier}: {message}")
    return status, message


def _overflow_doc(method: str, arg: str) -> str:
    return _INT_COMPONENT + f"""
lifecycle test "one past the edge" {{
  load B
  let r = call bump.{method}({arg})
  assert r == r
  unload B
}}
"""


@pytest.mark.parametrize("method", sorted(OVERFLOWS))
@pytest.mark.parametrize("tier", TIERS)
def test_component_int_overflow_traps(tier, method, capsys):
    status, message = _run(tier, _overflow_doc(method, OVERFLOWS[method]))
    output = capsys.readouterr().out
    assert status == "fail", (
        f"{tier}: `{method}` one past the Int range answered a value "
        f"({status}: {message}); the result wrapped instead of trapping")
    assert "revl: Int overflow" in output, (
        f"{tier}: `{method}` failed, but not with the Int overflow trap:\n"
        f"{output[-2000:]}")


@pytest.mark.parametrize("tier", TIERS)
def test_component_int_arithmetic_in_range(tier):
    status, message = _run(tier, _IN_RANGE_TEST)
    assert status == "pass", f"{tier}: {message}"


@pytest.mark.parametrize("tier", TIERS)
def test_component_division_and_float_operands(tier):
    status, message = _run(tier, _FLOAT_TEST)
    assert status == "pass", f"{tier}: {message}"
