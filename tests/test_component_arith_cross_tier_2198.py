"""Component-method arithmetic executes the same on py, go, rust and java.

Issue #2198 (quality audit QUAL-01). The component lowering had dropped the
`operands` annotation the fn lowering records, so a `/`, `%`, `+`, `-` or `*`
written in a provide method, or in an activation `effect` argument, reached
each backend unannotated and fell back to the host operator: `-7 % 2` was `1`
on py and `-1` on java, `-7 / 2` was `-3.0` on java, and go and rust did not
build. #2258 put the annotation back through one helper shared by both strata
(`_operand_annotation` in `src/revl/lower.py`), and #2261/#2312 taught the go
component renderer to read it.

What no test did until now is EXECUTE the component forms on rust and java.
`tests/test_component_operands_2198.py` checks the IR and runs py;
`tests/test_go_component_checked_arith_2259.py` and
`tests/test_go_component_int32_trap_2262.py` run go against py and ts. This
file runs one matrix on all four tiers the issue names, so a tier that stops
reading `operands` in a component body, or a lowering that stops writing it,
goes red here:

  * values: truncated `%` (including `Int.MIN % -1 == 0`), true `/` (IEEE at a
    zero divisor, Int32 operands widening), Float `%` (NaN at a zero divisor),
    config-field operands (the issue's repro) and `+` in range, in a provide
    method and in activation `effect` arguments;
  * faults: Int and Int32 `+ - *` and unary `-` one past the edge, and Int `%`
    by a zero divisor, must FAIL on every tier rather than answer a value;
  * the same with a module `fn` beside the component, which puts the
    document on each tier's combined emit path.

The fault text is revl's own on every tier here (`revl: Int overflow`, and
`revl: Int32 overflow` for Int32; java re-raises `Math.*Exact` in those words
since #2381, as docs/arithmetic.md states), so the assertion is the fault
itself plus the text that names it.
"""

import pytest

from revl import compile_source
from revl.test import RUNNERS

TIERS = ("go", "java", "py", "rust")

INT_MAX = "9223372036854775807"
INT_MIN = "(0 - 9223372036854775807 - 1)"
I32_MAX = "2147483647.to_int32()"
I32_MIN = "(0 - 2147483647 - 1).to_int32()"

_SERVICES = """
service Arith {
  fn add(x: Int) -> Int
  fn sub(x: Int) -> Int
  fn mul(x: Int) -> Int
  fn neg(x: Int) -> Int
  fn add32(x: Int32) -> Int32
  fn sub32(x: Int32) -> Int32
  fn mul32(x: Int32) -> Int32
  fn neg32(x: Int32) -> Int32
  fn rem(a: Int, b: Int) -> Int
  fn quo(a: Int, b: Int) -> Float
  fn quo32(a: Int32, b: Int32) -> Float
  fn frem(a: Float, b: Float) -> Float
  fn crem() -> Int
  fn cquo() -> Float
}
service Store {
  fn open(v: Int) -> Int
  fn close(t: Int)
}
service Probe {
  fn ok() -> Int
}
"""

_COMPONENTS = """
component S provides store: Store {
  provide store {
    fn open(v) = v
    fn close(t) { }
  }
}
component A provides arith: Arith {
  config { a: Int = -7, b: Int = 2 }
  provide arith {
    fn add(x) = ADD_LHS + 1
    fn sub(x) = x - 1
    fn mul(x) = x * 2
    fn neg(x) = -x
    fn add32(x) = x + 1.to_int32()
    fn sub32(x) = x - 1.to_int32()
    fn mul32(x) = x * 2.to_int32()
    fn neg32(x) = -x
    fn rem(a, b) { return a % b }
    fn quo(a, b) { return a / b }
    fn quo32(a, b) = a / b
    fn frem(a, b) = a % b
    fn crem() = config.a % config.b
    fn cquo() = config.a / config.b
  }
}
component E requires store: Store provides probe: Probe {
  config { a: Int = -7, b: Int = 2 }
  let r = effect store.open(config.a % config.b) undo store.close(r)
  let s = effect store.open(config.a + config.b) undo store.close(s)
  if (r != 0 - 1) {
    fail "an effect argument remainder is not truncated"
  }
  if (s != 0 - 5) {
    fail "an effect argument sum is not Int addition"
  }
  provide probe {
    fn ok() = 1
  }
}
"""

#: `E` provides `probe` and the test calls it: py records a failed activation
#: on the component's fiber and raises it only when a provided key is called,
#: so a bare `load E` would not surface an activation `fail` there. The fail
#: messages carry no `%`, because go renders a `fail` message as a format
#: string.

#: A module `fn` beside the components puts the document on each tier's
#: combined emitter (typed core plus live components).
_BESIDE = "fn pick(x: Int) -> Int { return x }\n"


def _source(beside: bool) -> str:
    lhs = "pick(x)" if beside else "x"
    return ((_BESIDE if beside else "") + _SERVICES
            + _COMPONENTS.replace("ADD_LHS", lhs))


#: docs/arithmetic.md: `%` truncates toward zero and `Int.MIN % -1` is 0; `/`
#: is IEEE true division, so a zero divisor is a value (+inf, NaN), not a
#: fault; a Float `%` is `fmod`, NaN at a zero divisor.
_VALUES = """
lifecycle test "component arithmetic values" {
  load A
  let r = call arith.rem(0 - 7, 2)
  assert r == 0 - 1
  let m = call arith.rem(0 - 9223372036854775807 - 1, 0 - 1)
  assert m == 0
  let q = call arith.quo(0 - 7, 2)
  assert q == 0.0 - 3.5
  let inf = call arith.quo(1, 0)
  assert inf > 1000000000000.0
  let nan = call arith.quo(0, 0)
  assert nan != nan
  let q32 = call arith.quo32((0 - 7).to_int32(), 2.to_int32())
  assert q32 == 0.0 - 3.5
  let f = call arith.frem(0.0 - 5.5, 2.0)
  assert f == 0.0 - 1.5
  let fz = call arith.frem(1.0, 0.0)
  assert fz != fz
  let c = call arith.crem()
  assert c == 0 - 1
  let d = call arith.cquo()
  assert d == 0.0 - 3.5
  let a = call arith.add(41)
  assert a == 42
  let top = call arith.sub(0 - 9223372036854775807)
  assert top == 0 - 9223372036854775807 - 1
  let a32 = call arith.add32(2147483646.to_int32())
  assert a32.to_int() == 2147483647
  let n32 = call arith.neg32(7.to_int32())
  assert n32.to_int() == 0 - 7
  unload A
}

lifecycle test "effect argument arithmetic values" {
  load S
  load E
  let ok = call probe.ok()
  assert ok == 1
  unload E
  unload S
}
"""

#: method -> (argument, the word the fault names). Each one is one past the
#: edge, or a zero divisor, and must fault on every tier.
FAULTS = {
    "add": (INT_MAX, "revl: int overflow"),
    "sub": (INT_MIN, "revl: int overflow"),
    "mul": (INT_MAX, "revl: int overflow"),
    "neg": (INT_MIN, "revl: int overflow"),
    "add32": (I32_MAX, "revl: int32 overflow"),
    "sub32": (I32_MIN, "revl: int32 overflow"),
    "mul32": (I32_MAX, "revl: int32 overflow"),
    "neg32": (I32_MIN, "revl: int32 overflow"),
    "rem": ("7, 0", "zero"),
}


def _run(tier: str, source: str, capsys):
    status, message = RUNNERS[tier](
        compile_source(source, "comp_arith_cross_tier_2198.rvl"))
    if status == "skip":
        pytest.skip(f"{tier}: {message}")
    return status, f"{message}\n{capsys.readouterr().out}"


#: Text a toolchain prints when the document did not build. A build log quotes
#: emitted source, which can hold "revl: Int overflow", so a fault case must
#: also show the program built and then faulted.
_BUILD_FAILED = ("error[e", "javac failed", "[build failed]")


def _assert_faulted(tier: str, method: str, arg: str, word: str,
                    status: str, output: str) -> None:
    lowered = output.lower()
    assert status == "fail", (
        f"{tier}: `{method}({arg})` answered a value instead of faulting:\n"
        f"{output[-3000:]}")
    assert not any(marker in lowered for marker in _BUILD_FAILED), (
        f"{tier}: `{method}({arg})` did not build:\n{output[-3000:]}")
    assert word in lowered, (
        f"{tier}: `{method}({arg})` failed, but not with a {word} fault:\n"
        f"{output[-3000:]}")


def _fault_doc(method: str, arg: str, beside: bool) -> str:
    return _source(beside) + f"""
lifecycle test "one past the edge" {{
  load A
  let r = call arith.{method}({arg})
  assert r == r
  unload A
}}
"""


@pytest.mark.parametrize("beside", [False, True], ids=["components", "beside_a_fn"])
@pytest.mark.parametrize("tier", TIERS)
def test_component_arithmetic_values_agree(tier, beside, capsys):
    status, output = _run(tier, _source(beside) + _VALUES, capsys)
    assert status == "pass", f"{tier}: {output[-3000:]}"


@pytest.mark.parametrize("method", sorted(FAULTS))
@pytest.mark.parametrize("tier", TIERS)
def test_component_arithmetic_faults(tier, method, capsys):
    arg, word = FAULTS[method]
    status, output = _run(tier, _fault_doc(method, arg, False), capsys)
    _assert_faulted(tier, method, arg, word, status, output)


@pytest.mark.parametrize("method", ["add", "rem"])
@pytest.mark.parametrize("tier", TIERS)
def test_component_arithmetic_faults_beside_a_fn(tier, method, capsys):
    arg, word = FAULTS[method]
    status, output = _run(tier, _fault_doc(method, arg, True), capsys)
    _assert_faulted(tier, method, arg, word, status, output)
