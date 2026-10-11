"""stdlib/str.rvl on the java tier (issue #2296).

WHAT WAS WRONG. Every program that imported stdlib/str.rvl failed javac on the
java tier, whichever `str_*` function it called, because the module's `dedent`
is emitted into the same class. `dedent` accumulates into an annotated empty
list (`var lines: List[Str] = []`) and then loops over it. The emitter declared
every empty list literal as a raw `java.util.List`, so `for (ln of lines)`
bound `ln` as `Object`, and `leading_sp_tab(ln)` and `ln.slice(...)` were
rejected ("Object cannot be converted to String").

WHAT IS EMITTED NOW. An empty list literal that carries its annotation as
`"expected"` declares as that precise type (`java.util.List<String>`), the
same pin the empty-map case already reads (#274). An unannotated `var xs = []`
still declares the raw list.

The end-to-end tests need a JDK and skip without one. A skip is not a pass:
CI's `backend-java` job provisions a JDK.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "tests") not in sys.path:
    sys.path.append(str(ROOT / "tests"))

from _load_by_path import load_by_path  # noqa: E402

javac_gate = load_by_path("javac_gate", HERE / "javac_gate.py")
emit = load_by_path("revl_java_emit_2296", HERE / "emit.py").emit

from revl.compiler import compile_source  # noqa: E402
from revl.test import RUNNERS  # noqa: E402

needs_jdk = pytest.mark.skipif(javac_gate.JAVAC is None, reason=javac_gate.NO_JDK)

STR_MODULE = (ROOT / "stdlib" / "str.rvl").read_text(encoding="utf-8")

#: Several str_* functions, dedent included. The expected values are Python's
#: own (`textwrap.dedent`, `str.strip`, ...), which the py tier also returns.
STR_PROGRAM = """\
use "stdlib/str.rvl" { trim, lstrip, rstrip, contains, index_of, last_index_of,
                       ident_tokens, split_top, dedent, str_newline, str_char }

fn nl() -> Str { return str_newline() }

pub fn dedented() -> Str {
  let src = "    a".concat(nl()).concat("      b").concat(nl()).concat("   ")
    .concat(nl()).concat("    c")
  return dedent(src)
}

test "str_char" { assert str_char(65) == "A" }
test "trim" {
  assert trim("  hi  ") == "hi"
  assert lstrip("  hi ") == "hi "
  assert rstrip(" hi  ") == " hi"
}
test "search" {
  assert contains("abcabc", "ca")
  assert index_of("abcabc", "c") == 2
  assert last_index_of("abcabc", "c") == 5
}
test "tokens" {
  assert ident_tokens("a.b_1 + c").join("|") == "a|b_1|c"
  assert split_top("Map[Str, Int], Str", ",").length() == 2
}
test "dedent" {
  assert dedented() == "a".concat(nl()).concat("  b").concat(nl()).concat(nl()).concat("c")
}
"""

#: The construct itself, without the stdlib: an annotated empty list that is
#: filled and then iterated, its element passed where the element type is
#: required. One Str list and one Int list (the boxed element type).
LOOP_PROGRAM = """\
fn twice(s: Str) -> Str { return s.concat(s) }
fn inc(n: Int) -> Int { return n + 1 }

pub fn strs(text: Str) -> Str {
  var parts: List[Str] = []
  for (p of text.split(",")) { parts = parts.push(p) }
  var out: List[Str] = []
  for (p of parts) { out = out.push(twice(p)) }
  return out.join("-")
}

pub fn ints() -> Int {
  var xs: List[Int] = []
  xs = xs.push(1)
  xs = xs.push(2)
  var total = 0
  for (x of xs) { total = total + inc(x) }
  return total
}

test "str list" { assert strs("a,b") == "aa-bb" }
test "int list" { assert ints() == 5 }
"""


#: The two other places the same declaration is made. A provide-method body
#: (`_method_body_lines`, which used `var` and froze the list at
#: `List<Object>`), and element types with no generic spelling here (`Any`,
#: `Int32`), which keep the raw list rather than emit `List<Any>`/`List<int>`.
METHOD_PROGRAM = """\
fn twice(s: Str) -> Str { return s.concat(s) }

service Namer {
  fn label(text: Str) -> Str
}

component Registry provides name: Namer {
  provide name {
    fn label(text) {
      var parts: List[Str] = []
      for (p of text.split(",")) { parts = parts.push(p) }
      var out: List[Str] = []
      for (p of parts) { out = out.push(twice(p)) }
      return out.join("-")
    }
  }
}

pub fn any_and_int32() -> Int {
  var xs: List[Any] = []
  xs = xs.push(1)
  var ys: List[Int32] = []
  return xs.length() + ys.length()
}

test "raw lists" { assert any_and_int32() == 1 }
"""


def _compile(src: str) -> dict:
    return compile_source(src, "probe_2296.rvl",
                          modules={"stdlib/str.rvl": STR_MODULE})


def _java_source(src: str) -> str:
    out = emit(_compile(src))
    return out if isinstance(out, str) else "\n".join(map(str, out.values()))


def test_annotated_empty_list_declares_its_element_type():
    java = _java_source(LOOP_PROGRAM)
    assert "java.util.List<String> parts = " in java
    assert "java.util.List<String> out = " in java
    assert "java.util.List<java.lang.Long> xs = " in java


def test_method_body_and_raw_element_declarations():
    java = _java_source(METHOD_PROGRAM)
    assert "java.util.List<String> parts = " in java
    assert "java.util.List xs = " in java
    assert "java.util.List ys = " in java


def test_unannotated_empty_list_stays_raw():
    src = "pub fn f() -> Int {\n  var xs = []\n  return xs.length()\n}\n"
    assert "java.util.List xs = " in _java_source(src)


@needs_jdk
def test_annotated_list_loop_runs_on_java():
    status, message = RUNNERS["java"](_compile(LOOP_PROGRAM))
    assert status == "pass", message


@needs_jdk
def test_stdlib_str_program_runs_on_java():
    status, message = RUNNERS["java"](_compile(STR_PROGRAM))
    assert status == "pass", message


@needs_jdk
def test_method_body_and_raw_element_lists_run_on_java():
    status, message = RUNNERS["java"](_compile(METHOD_PROGRAM))
    assert status == "pass", message


#: One element type per class `_java_v3_type` has no Java spelling for: a
#: sized numeric, an undeclared generic, a function type. The precise
#: declaration is an allowlist, so each keeps the raw list and compiles.
RAW_ELEMENT_TYPES = ["Int8", "Set[Int]", "Result[Int, Str]", "(Int) -> Int"]


def _raw_element_program(elem: str) -> str:
    return (f"pub fn n() -> Int {{\n  var xs: List[{elem}] = []\n"
            "  return xs.length()\n}\n"
            'test "empty" { assert n() == 0 }\n')


@pytest.mark.parametrize("elem", RAW_ELEMENT_TYPES)
def test_undeclarable_element_type_keeps_the_raw_list(elem):
    assert "java.util.List xs = " in _java_source(_raw_element_program(elem))


@needs_jdk
@pytest.mark.parametrize("elem", RAW_ELEMENT_TYPES)
def test_undeclarable_element_type_compiles_on_java(elem):
    status, message = RUNNERS["java"](_compile(_raw_element_program(elem)))
    assert status == "pass", message
