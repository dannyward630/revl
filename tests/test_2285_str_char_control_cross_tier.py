"""`str_char` and `Int.to_char` across every tier (issue #2285).

Pure revl had no way to spell a carriage return. `"..."` strings carry no
escapes, a backtick template holds a literal byte but the source reader folds a
CR byte to LF before the lexer runs, and `stdlib/str.rvl`'s `str_char(13)`
returned `""`. Mail protocols need CRLF, so revl-sp had to decode a JSON escape
to get one.

The fix is a blessed per-tier primitive, `Int.to_char()`: the one-code-point
string for a Unicode scalar value, `""` for anything else (negative, a
surrogate, above U+10FFFF). `str_char` routes every code point the pure table
does not cover through it, so CR, NUL and the other control characters now
round-trip through `charCodeAt` on every tier.

Each tier builds AND runs the same program and asserts the same values; a tier
that disagrees fails its own run. cargo and javac are slow, so those two run
only with REVL_CROSS_TIER_SLOW=1, the same split tests/test_1850_show_cross_tier.py
uses.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl import compile_files, compile_source  # noqa: E402
from revl.lower import _BUILTIN_METHODS  # noqa: E402
from revl.test import RUNNERS  # noqa: E402
from revl.typecheck import _BUILTIN_SIG  # noqa: E402

STDLIB = ROOT / "stdlib" / "str.rvl"

PROGRAM = """\
use "stdlib/str.rvl" { str_char, str_crlf, str_newline, str_tab }

fn one(code: Int) -> Bool {
  let s = str_char(code)
  return s.length() == 1 && s.charCodeAt(0) == code
}

fn crlf() -> Str { return str_char(13).concat(str_newline()) }

test "the control characters are one code point each" {
  assert one(13)
  assert one(9)
  assert one(0)
  assert one(1)
  assert one(27)
  assert one(31)
  assert one(127)
}

test "CRLF is two code points, CR then LF" {
  assert crlf().length() == 2
  assert crlf().charCodeAt(0) == 13
  assert crlf().charCodeAt(1) == 10
  assert str_crlf() == crlf()
  assert str_crlf().length() == 2
}

test "the pure table is unchanged" {
  assert str_char(9) == str_tab()
  assert str_char(10) == str_newline()
  assert str_char(65) == "A"
  assert one(32)
  assert one(126)
}

test "beyond ASCII" {
  assert one(233)
  assert one(2047)
  assert one(2048)
  assert one(65533)
  assert one(128512)
  assert one(1114111)
  assert str_char(233) == "é"
}

test "a value that is not a Unicode scalar is the empty string" {
  assert str_char(-1) == ""
  assert str_char(55296) == ""
  assert str_char(57343) == ""
  assert str_char(1114112) == ""
}
"""

#: The issue's own reproducer, importing only names that existed before the
#: fix, so on the base revision it compiles and fails on the CR itself rather
#: than on a missing import.
CR_ONLY = """\
use "stdlib/str.rvl" { str_char, str_newline }

test "str_char(13) is a carriage return" {
  let cr = str_char(13)
  assert cr.length() == 1
  assert cr.charCodeAt(0) == 13
  assert cr.concat(str_newline()).length() == 2
}
"""

#: The primitive itself, with no stdlib in the way.
TO_CHAR = """\
fn code(n: Int) -> Int { return n.to_char().charCodeAt(0) }

test "Int.to_char directly" {
  assert code(13) == 13
  assert code(0) == 0
  assert 0.to_char().length() == 1
  assert 65.to_char() == "A"
  assert code(128512) == 128512
  assert (-1).to_char() == ""
  assert 55296.to_char() == ""
  assert 1114112.to_char() == ""
}
"""

TIERS = ("py", "ts", "go", "wasm")
SLOW_TIERS = ("rust", "java")


def _with_stdlib(tmp_path_factory, source: str) -> dict:
    # `use` resolves relative to the importing file, so the stdlib file sits
    # beside the program.
    d = tmp_path_factory.mktemp("str_char_2285")
    (d / "stdlib").mkdir()
    (d / "stdlib" / "str.rvl").write_text(
        STDLIB.read_text(encoding="utf-8"), encoding="utf-8")
    main = d / "main.rvl"
    main.write_text(source, encoding="utf-8")
    return compile_files([str(main)])


@pytest.fixture(scope="module")
def ir(tmp_path_factory):
    return _with_stdlib(tmp_path_factory, PROGRAM)


@pytest.fixture(scope="module")
def cr_only_ir(tmp_path_factory):
    return _with_stdlib(tmp_path_factory, CR_ONLY)


@pytest.fixture(scope="module")
def to_char_ir():
    return compile_source(TO_CHAR, "to_char_2285.rvl")


def test_to_char_is_on_the_builtin_surface():
    assert _BUILTIN_SIG["to_char"] == ("Int", [], "Str")
    assert _BUILTIN_METHODS["to_char"] == 0


def _check(tier: str, ir: dict) -> None:
    status, message = RUNNERS[tier](ir)
    if status == "skip":
        pytest.skip(f"{tier}: {message}")
    assert status == "pass", f"{tier}: {message}"


@pytest.mark.parametrize("tier", TIERS)
def test_str_char_round_trips_on_every_tier(tier: str, ir: dict):
    _check(tier, ir)


@pytest.mark.parametrize("tier", TIERS)
def test_issue_reproducer_on_every_tier(tier: str, cr_only_ir: dict):
    _check(tier, cr_only_ir)


@pytest.mark.parametrize("tier", TIERS)
def test_to_char_on_every_tier(tier: str, to_char_ir: dict):
    _check(tier, to_char_ir)


_SLOW = pytest.mark.skipif(not os.environ.get("REVL_CROSS_TIER_SLOW"),
                           reason="set REVL_CROSS_TIER_SLOW=1 (cargo/javac are slow)")


@_SLOW
@pytest.mark.parametrize("tier", SLOW_TIERS)
def test_to_char_on_every_tier_slow(tier: str, to_char_ir: dict):
    _check(tier, to_char_ir)


# java is absent here on purpose: the java tier cannot compile any program that
# `use`s stdlib/str.rvl yet (javac refuses `dedent`'s untyped list loop, the
# same on the base revision), which is a separate defect from #2285. The
# primitive `str_char` relies on is pinned on java by the test above.
@_SLOW
def test_str_char_round_trips_on_rust(ir: dict):
    _check("rust", ir)
