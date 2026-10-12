"""Primitive and `Any` type arguments in v3 signatures on the java tier (#2303).

WHAT WAS WRONG. `_java_v3_type` spelled a type argument by boxing only `long`,
`double` and `boolean`, so `List[Int32]` was `java.util.List<int>`, which is
not Java. `Any` has no `TYPE_MAP` entry, so it fell through to a bare
identifier and `List[Any]` named a class `Any` that does not exist. A generic
record (`type Bx[T] = { v: T }`) was worse: the class was declared without its
type parameter (`public final T v;` with no `T` in scope) and every use applied
`Object` to it (`Bx<Object>` on a class that takes no parameters).

WHAT IS EMITTED NOW. `Int32` boxes to `java.lang.Integer`, `Any` is `Object`,
and a generic record is `Bx<T>` with each use applying its arguments boxed
(`Bx<java.lang.Long>`).

The run tests exercise signatures with empty and `Any` lists only: the checker
accepts no Int32 literal, so no non-empty `List[Int32]` is built here.

The compile and run tests need a JDK and skip without one. A skip is not a
pass: CI's `backend-java` job provisions a JDK.
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
emit = load_by_path("revl_java_emit_2303", HERE / "emit.py").emit

from revl.compiler import compile_source  # noqa: E402
from revl.test import RUNNERS  # noqa: E402

needs_jdk = pytest.mark.skipif(javac_gate.JAVAC is None, reason=javac_gate.NO_JDK)

#: One signature per element class: a sized int, `Any`, a map value, an
#: option, and the nesting of each inside the other.
SCALAR_PROGRAM = """\
pub fn ints(xs: List[Int32]) -> List[Int32] { return xs }
pub fn anys(xs: List[Any]) -> List[Any] { return xs.push(1) }
pub fn table(d: Map[Str, Int32]) -> Map[Str, Int32] { return d }
pub fn maybe(x: Opt[Int32]) -> Opt[Int32] { return x }
pub fn rows(xs: List[List[Int32]]) -> List[List[Int32]] { return xs }
pub fn mixed(d: Map[Str, List[Any]]) -> Map[Str, List[Any]] { return d }

pub fn count() -> Int {
  return ints([]).length() + anys([]).length() + rows([]).length()
}
test "count" { assert count() == 1 }
"""

#: A generic record as a list element, a map value, a parameter and a return,
#: with a primitive, a string and a second type parameter as the argument.
RECORD_PROGRAM = """\
type Bx[T] = { v: T }
type Pair[A, B] = { first: A, second: B }

pub fn mk(n: Int) -> Bx[Int] { return { v: n } }
pub fn get(b: Bx[Int]) -> Int { return b.v }
pub fn boxes(bs: List[Bx[Int]]) -> List[Bx[Int]] { return bs.push(mk(2)) }
pub fn by_name(m: Map[Str, Bx[Str]]) -> Map[Str, Bx[Str]] { return m }
pub fn wide(bs: List[Bx[Int32]]) -> List[Bx[Int32]] { return bs }
pub fn pair(p: Pair[Str, Int]) -> Int { return p.second }

pub fn total() -> Int {
  var sum = 0
  for (b of boxes([mk(1)])) { sum = sum + get(b) }
  return sum
}
test "get" { assert get(mk(3)) == 3 }
test "total" { assert total() == 3 }
test "pair" { assert pair({ first: "a", second: 4 }) == 4 }
"""


def _compile(src: str) -> dict:
    return compile_source(src, "probe_2303.rvl")


def _java_source(src: str) -> str:
    out = emit(_compile(src))
    return out if isinstance(out, str) else "\n".join(map(str, out.values()))


def test_int32_type_argument_is_boxed():
    java = _java_source(SCALAR_PROGRAM)
    assert "java.util.List<java.lang.Integer> ints(" in java
    assert "java.util.Map<String, java.lang.Integer> table(" in java
    assert "java.util.Optional<java.lang.Integer> maybe(" in java
    assert "java.util.List<java.util.List<java.lang.Integer>> rows(" in java
    assert "<int>" not in java and "<int," not in java


def test_any_type_argument_is_object():
    java = _java_source(SCALAR_PROGRAM)
    assert "java.util.List<Object> anys(java.util.List<Object> xs)" in java
    assert "java.util.Map<String, java.util.List<Object>> mixed(" in java
    assert "<Any>" not in java


def test_generic_record_declares_and_applies_its_parameters():
    java = _java_source(RECORD_PROGRAM)
    assert "public static final class Bx<T> {" in java
    assert "public static final class Pair<A, B> {" in java
    assert "java.util.List<Bx<java.lang.Long>> boxes(" in java
    assert "java.util.Map<String, Bx<String>> by_name(" in java
    assert "java.util.List<Bx<java.lang.Integer>> wide(" in java
    assert "Pair<String, java.lang.Long> p" in java
    assert "Bx<Object>" not in java


def test_plain_record_is_not_parameterised():
    java = _java_source("type P = { n: Int }\npub fn f(p: P) -> Int { return p.n }\n")
    assert "public static final class P {" in java


@needs_jdk
def test_scalar_type_arguments_compile_on_java():
    javac_gate.compile_check(_java_source(SCALAR_PROGRAM), "scalar type arguments")


@needs_jdk
def test_generic_record_signatures_compile_on_java():
    javac_gate.compile_check(_java_source(RECORD_PROGRAM), "generic records")


@needs_jdk
def test_scalar_type_arguments_run_on_java():
    status, message = RUNNERS["java"](_compile(SCALAR_PROGRAM))
    assert status == "pass", message


@needs_jdk
def test_generic_record_signatures_run_on_java():
    status, message = RUNNERS["java"](_compile(RECORD_PROGRAM))
    assert status == "pass", message
