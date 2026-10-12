"""Issue #2284: a block whose body holds only a comment emits `pass` on py.

The checker accepts a branch, loop or body that holds only a comment, and the
ts tier runs it (`if (x) { }` is legal JavaScript). The python emitter wrote the
block header with nothing under it, so the module failed at `exec` with an
IndentationError pointing into generated code. Every block the emitter renders
from author steps now closes through `_Lines.close_block`, which adds `pass`
when the body holds no statement.

The sources below are shared with the self-host oracle
(tests/test_selfhost_emit_py.py imports `FN_CASES` and `COMPONENT_CASES`), which
holds selfhost/emit_py.rvl to the same bytes.

`FN_CASES` are fn-grammar forms: each source carries its own `test` blocks and
runs without cordis. `COMPONENT_CASES` are component-grammar forms: each carries
a `lifecycle test`, which needs cordis-py to run. Not listed, because the
checker rejects them before any emitter sees them: a component `if` guard
("guard cannot be empty") and a match arm (an arm is an expression, never a
block).

Five cases emitted invalid Python before the fix: fn-if-then, fn-if-both-arms,
fn-nested-if-in-loop, effect-setup-if and extern-py-body. The others were
already guarded by ad-hoc checks, now folded into the one helper; they stay to
hold every block form to it.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "backends" / "python"))

from _backend_import import backend_emitter  # noqa: E402
from revl import compile_source  # noqa: E402

emit = backend_emitter("python")

FN_CASES = {
    "fn-if-then": """
pub fn pick(n: Int) -> Int {
  if (n > 0) {
    // nothing to do here on purpose
  }
  return n
}
test "pick" { assert pick(3) == 3 }
""",
    "fn-if-else": """
pub fn clamp(n: Int) -> Int {
  var m = n
  if (n < 0) {
    m = 0
  } else {
    // a non-negative input is kept
  }
  return m
}
test "clamp" {
  assert clamp(-2) == 0
  assert clamp(5) == 5
}
""",
    "fn-if-both-arms": """
pub fn same(n: Int) -> Int {
  if (n > 0) {
    // positive
  } else {
    // not positive
  }
  return n
}
test "same" { assert same(2) == 2 }
""",
    "fn-while": """
pub fn idle(n: Int) -> Int {
  while (n < 0) {
    // never entered
  }
  return n
}
test "idle" { assert idle(1) == 1 }
""",
    "fn-for": """
pub fn walk(xs: List[Int]) -> Int {
  for (x of xs) {
    // walk without work
  }
  return xs.length
}
test "walk" { assert walk([1, 2]) == 2 }
""",
    "fn-nested-if-in-loop": """
pub fn count(xs: List[Int]) -> Int {
  var n = 0
  for (x of xs) {
    if (x > 1) {
      // large items are skipped
    }
    n += 1
  }
  return n
}
test "count" { assert count([1, 2, 3]) == 3 }
""",
    "fn-body": """
pub fn nothing(n: Int) {
  // nothing to do
}
pub fn one() -> Int { return 1 }
test "one" { assert one() == 1 }
""",
    "test-body": """
pub fn one() -> Int { return 1 }
test "a test that only explains" {
  // nothing to check here yet
}
test "one" { assert one() == 1 }
""",
}

_SERVICE = """
service Count {
  fn bump(n: Int) -> Int
  fn idle(n: Int)
}
"""

_LIFECYCLE = """
lifecycle test "counter" {
  load Counter
  let r = call c.bump(4)
  assert r == 4
}
"""


def _component(body: str, bump: str = "return n", idle: str = "") -> str:
    return (_SERVICE
            + "component Counter provides c: Count {\n"
            + body
            + "  provide c {\n"
            + "    fn bump(n) {\n      " + bump + "\n    }\n"
            + "    fn idle(n) {\n      " + (idle or "return") + "\n    }\n"
            + "  }\n}\n"
            + _LIFECYCLE)


COMPONENT_CASES = {
    "effect-setup-if": _component("""  let scratch = effect {
    if (1 > 2) {
      // no setup is needed here
    }
    Map.new()
  } undo scratch.drop()
"""),
    "method-if-then": _component("", bump="""var m = n
      if (n > 10) {
        // a large input passes through
      }
      return m"""),
    "method-else": _component("", bump="""var m = n
      if (n < 0) {
        m = 0
      } else {
        // a non-negative input is kept
      }
      return m"""),
    "method-while": _component("", bump="""while (n < 0) {
        // never entered
      }
      return n"""),
    "method-for": _component("", bump="""for (x of [1, 2]) {
        // walk without work
      }
      return n"""),
    "method-body": _component("", idle="// nothing to do"),
    "extern-py-body": """
extern pure fn host_noop() = @ts { } = @py {
  # nothing to do on this host
}
""" + _component(""),
    "lifecycle-body": _component("") + """
lifecycle test "a lifecycle test that only explains" {
  // nothing to drive here yet
}
""",
}

needs_cordis = pytest.mark.skipif(
    importlib.util.find_spec("cordis") is None,
    reason="a lifecycle test drives a live cordis-py runtime")


def _emitted(source: str, name: str) -> str:
    return emit.emit(compile_source(source, f"{name}.rvl"))


@pytest.mark.parametrize("name", sorted(FN_CASES))
def test_comment_only_fn_block_runs_on_py(name):
    """The emitted module compiles, and every `test` block in it passes."""
    namespace: dict = {}
    exec(compile(_emitted(FN_CASES[name], name), f"{name}.py", "exec"), namespace)
    tests = namespace["REVL_TESTS"]
    assert tests, name
    for _, run in tests:
        run()


@pytest.mark.parametrize("name", sorted(COMPONENT_CASES))
def test_comment_only_component_block_compiles_on_py(name):
    """The emitted module is valid Python. Running it needs cordis (below)."""
    compile(_emitted(COMPONENT_CASES[name], name), f"{name}.py", "exec")


@needs_cordis
@pytest.mark.parametrize("name", sorted(COMPONENT_CASES))
def test_comment_only_component_block_runs_on_py(name):
    from revl import test as revl_test

    status, summary = revl_test.run_py(
        compile_source(COMPONENT_CASES[name], f"{name}.rvl"))
    assert status == "pass", (status, summary)


def test_a_comment_only_branch_emits_pass_under_its_header():
    """The issue's reproducer, pinned at the line: `pass` sits under the `if`."""
    lines = _emitted(FN_CASES["fn-if-then"], "pick").splitlines()
    head = lines.index("    if (n > 0):")
    assert lines[head + 1] == "        pass"


def test_a_comment_only_extern_body_keeps_its_comment_and_gains_pass():
    lines = _emitted(COMPONENT_CASES["extern-py-body"], "extern").splitlines()
    head = lines.index("def host_noop():")
    assert lines[head + 1:head + 3] == ["    # nothing to do on this host", "    pass"]


def test_a_block_with_a_statement_gains_no_pass():
    """`pass` is only for an empty body: a non-empty one is byte-identical."""
    source = "pub fn f(n: Int) -> Int {\n  if (n > 0) { return 1 }\n  return n\n}\n"
    lines = _emitted(source, "nonempty").splitlines()
    head = lines.index("    if (n > 0):")
    assert lines[head + 1:head + 3] == ["        return 1", "    return n"]
