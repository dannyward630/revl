"""Issue #2297: on ts, a block match arm that captures a record emitted an
unclosed parameter type.

A block match arm is lifted into a helper fn (`match_arm_N`) whose parameters
are the bindings it reads. A binding whose value is a record literal with no
declared type carries the checker's structural spelling, `{name: Str, rows:
List[Str]}`, and the ts type renderer had no case for it. It took the generic
`Head[Args]` path, cut the type at its first `[`, and wrote
`{name: Str, rows: List<unknown>`: no closing brace, revl type names, and the
next parameters swallowed into it. vitest refused the file with a parse error.
A record nested in a list (`List[List[{w: Int}]]`) was refused outright, as an
invalid type name.

The fix gives `_ts_v3_type` a structural-record case, so every signature
(lifted arm params and return, arrow params, typed `var` locals) renders
`{ name: string; rows: string[] }`. `_split_v3_types` now nests on braces, and
a union element of a list is parenthesised (`(bigint | undefined)[]`).

revl has no tuple type (docs/function-types.md), so the multi-part capture
variant here is a list of records plus a list of lists of records.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from revl import compile_source  # noqa: E402
from revl.test import RUNNERS  # noqa: E402


def _reference():
    spec = importlib.util.spec_from_file_location(
        "tsemit_2297", ROOT / "backends" / "typescript" / "emit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The issue's reproducer: a captured record and a record return type.
ISSUE = '''pub type S = { name: Str, rows: List[Str] }
fn pick(r: Result[List[S], Str], name: Str) -> S {
  let missing = { name: "", rows: ["missing"] }
  return match r {
    Ok(xs) => {
      var found = missing
      for (x of xs) { if (x.name == name) { found = x } }
      found
    },
    Err(e) => { name: e, rows: [] },
  }
}
test "block arm" {
  assert pick(Ok([{ name: "a", rows: [] }]), "a").name == "a"
  assert pick(Ok([{ name: "a", rows: [] }]), "b").rows[0] == "missing"
  assert pick(Err("e"), "a").name == "e"
}
'''

# Several captures at once, records inside generics: a list of records and a
# list of lists of records.
GENERIC = '''fn tally(r: Result[Int, Str], k: Str) -> Int {
  let pairs = [{ k: "a", v: 1 }, { k: "b", v: 2 }]
  let grid = [[{ w: 10 }], [{ w: 20 }, { w: 30 }]]
  return match r {
    Ok(v) => {
      var total = v
      for (p of pairs) { if (p.k == k) { total = total + p.v } }
      for (row of grid) { total = total + row.length() }
      total
    },
    Err(e) => 0,
  }
}
test "generic capture" {
  assert tally(Ok(1), "b") == 6
  assert tally(Err("e"), "b") == 0
}
'''

# A record whose field is itself a record.
NESTED = '''pub type Out = { a: Int, tags: List[Str], n: Int }
fn outer(r: Result[Int, Str]) -> Out {
  let base = { inner: { a: 1, tags: ["x"] }, n: 2 }
  return match r {
    Ok(v) => {
      var cur = base
      if (v > 0) { cur = { inner: { a: v, tags: ["y", "z"] }, n: v } }
      { a: cur.inner.a, tags: cur.inner.tags, n: cur.n }
    },
    Err(e) => { a: 0, tags: [], n: 0 },
  }
}
test "nested record" {
  assert outer(Ok(5)).a == 5
  assert outer(Ok(5)).tags.length() == 2
  assert outer(Ok(0)).tags[0] == "x"
  assert outer(Err("e")).n == 0
}
'''

PROGRAMS = {"issue": ISSUE, "generic": GENERIC, "nested": NESTED}

SIGNATURES = {
    "issue": "export function match_arm_0(missing: { name: string; rows: string[] }, "
             "name: string, xs: S[]): { name: string; rows: string[] } {",
    "generic": "export function match_arm_0(grid: { w: bigint }[][], k: string, "
               "pairs: { k: string; v: bigint }[], v: bigint): bigint {",
    "nested": "export function match_arm_0(base: { inner: { a: bigint; tags: string[] }; "
              "n: bigint }, v: bigint): { a: bigint; n: bigint; tags: string[] } {",
}


@pytest.mark.parametrize("case", sorted(PROGRAMS))
def test_lifted_arm_signature_closes(case):
    ir = compile_source(PROGRAMS[case], f"arm_{case}.rvl")
    src = _reference().emit(ir)
    assert SIGNATURES[case] in src.splitlines()


@pytest.mark.parametrize(("surface", "rendered"), [
    ("{}", "{}"),
    ("{a: Int, b: Str}", "{ a: bigint; b: string }"),
    ("{a: {b: Int, c: List[Str]}, d: Bool}",
     "{ a: { b: bigint; c: string[] }; d: boolean }"),
    ("{function: Int}", '{ "function": bigint }'),
    ("Map[Str, {x: Int, y: Int}]", "Map<string, { x: bigint; y: bigint }>"),
    ("Opt[{a: Int}]", "{ a: bigint } | undefined"),
    ("({a: Int}) -> {b: Str}", "((a0: { a: bigint }) => { b: string })"),
    ("({a: Int, b: Str}) -> Int", "((a0: { a: bigint; b: string }) => bigint)"),
    ("List[Opt[Int]]", "(bigint | undefined)[]"),
    ("List[Result[Int, Str]]",
     '({ kind: "Ok"; value: bigint } | { kind: "Err"; value: string })[]'),
    ("List[{a: Opt[Int]}]", "{ a: bigint | undefined }[]"),
    ("List[(Int) -> Opt[Str]]", "((a0: bigint) => string | undefined)[]"),
    ("List[Map[Str, Opt[Int]]]", "Map<string, bigint | undefined>[]"),
])
def test_ts_type_renders_structural_and_generic_types(surface, rendered):
    assert _reference()._ts_v3_type(surface) == rendered


@pytest.mark.parametrize("tier", ["py", "ts"])
@pytest.mark.parametrize("case", sorted(PROGRAMS))
def test_block_arm_record_capture_executes(tier, case):
    status, message = RUNNERS[tier](compile_source(PROGRAMS[case], f"arm_{case}.rvl"))
    if status == "skip":
        pytest.skip(f"{tier}: {message}")
    assert status == "pass", f"{tier} failed: {message}"
