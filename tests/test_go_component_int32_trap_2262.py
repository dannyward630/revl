"""Int32 arithmetic in a component method body traps on go, as in a `fn`.

Issue #2262. The go component emitter's typed arithmetic arm
(`backends/go/emit.py`, `_comp_typed_arith`) sent an Int `+ - *` through the
checked `revlAdd`/`revlSub`/`revlMul` helpers (issue #2259) but matched only
`operands == "Int"`. An `Int32` node fell through to the bare Go operator on
`int32`, which wraps silently, so `Int32.MAX + 1` answered `Int32.MIN`.
docs/arithmetic.md says Int32 overflow traps with `revl: Int32 overflow`, and
py and ts do trap. Unary `-` on Int32 had the same gap.

The arm now renders `revlAddI32`/`revlSubI32`/`revlMulI32`, the helpers the
top-level fn renderer (`_go_v3_expr`) uses, and unary `-` as
`revlSubI32(0, x)`.

Every probe runs the same document on go, py and ts. py and ts are the
reference; go must agree with them.
"""

import pytest

from revl import compile_source
from revl.test import RUNNERS

TIERS = ("go", "py", "ts")

I32_MAX = "2147483647.to_int32()"
I32_MIN = "(0 - 2147483647 - 1).to_int32()"

_COMPONENT = """
service Narrow {
  fn add(x: Int32) -> Int32
  fn sub(x: Int32) -> Int32
  fn mul(x: Int32) -> Int32
  fn neg(x: Int32) -> Int32
}
component N provides narrow: Narrow {
  provide narrow {
    fn add(x) = x + 1.to_int32()
    fn sub(x) = x - 1.to_int32()
    fn mul(x) = x * 2.to_int32()
    fn neg(x) = -x
  }
}
"""

#: method -> the argument that pushes it one past the Int32 range.
OVERFLOWS = {
    "add": I32_MAX,
    "sub": I32_MIN,
    "mul": I32_MAX,
    "neg": I32_MIN,
}

#: The non-vacuity control: in range, the checked helpers answer the value,
#: right up to each edge.
_IN_RANGE_TEST = _COMPONENT + """
lifecycle test "in range" {
  load N
  let a = call narrow.add(5.to_int32())
  assert a.to_int() == 6
  let s = call narrow.sub(5.to_int32())
  assert s.to_int() == 4
  let m = call narrow.mul(21.to_int32())
  assert m.to_int() == 42
  let n = call narrow.neg(7.to_int32())
  assert n.to_int() == 0 - 7
  let top = call narrow.add(2147483646.to_int32())
  assert top.to_int() == 2147483647
  let bottom = call narrow.sub((0 - 2147483647).to_int32())
  assert bottom.to_int() == 0 - 2147483647 - 1
  unload N
}
"""


def _run(tier: str, source: str):
    status, message = RUNNERS[tier](compile_source(source, "comp_int32_2262.rvl"))
    if status == "skip":
        pytest.skip(f"{tier}: {message}")
    return status, message


def _overflow_doc(method: str, arg: str) -> str:
    return _COMPONENT + f"""
lifecycle test "one past the Int32 edge" {{
  load N
  let r = call narrow.{method}({arg})
  assert r == r
  unload N
}}
"""


@pytest.mark.parametrize("method", sorted(OVERFLOWS))
@pytest.mark.parametrize("tier", TIERS)
def test_component_int32_overflow_traps(tier, method, capsys):
    status, message = _run(tier, _overflow_doc(method, OVERFLOWS[method]))
    output = capsys.readouterr().out
    assert status == "fail", (
        f"{tier}: `{method}` one past the Int32 range answered a value "
        f"({status}: {message}); the result wrapped instead of trapping")
    assert "revl: Int32 overflow" in output, (
        f"{tier}: `{method}` failed, but not with the Int32 overflow trap:\n"
        f"{output[-2000:]}")


@pytest.mark.parametrize("tier", TIERS)
def test_component_int32_arithmetic_in_range(tier):
    status, message = _run(tier, _IN_RANGE_TEST)
    assert status == "pass", f"{tier}: {message}"


#: A module `fn` beside the component puts a lifecycle document on the
#: combined emitter (typed core plus live components), whose prelude writes the
#: I32 helpers off its own flag. The trap must hold there too.
_BESIDE_A_FN = """
fn pick(x: Int32) -> Int32 { return x }
""" + _COMPONENT.replace("fn add(x) = x + 1.to_int32()",
                         "fn add(x) = pick(x) + 1.to_int32()")


@pytest.mark.parametrize("tier", TIERS)
def test_component_int32_overflow_traps_beside_a_fn(tier, capsys):
    source = _BESIDE_A_FN + """
lifecycle test "one past the Int32 edge, combined" {
  load N
  let r = call narrow.add(2147483647.to_int32())
  assert r == r
  unload N
}
"""
    status, message = _run(tier, source)
    output = capsys.readouterr().out
    assert status == "fail", f"{tier}: answered a value ({status}: {message})"
    assert "revl: Int32 overflow" in output, output[-2000:]
