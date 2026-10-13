"""Every `revl test` tier's verdict line carries the number of tests it ran,
in one shape (issue #2286).

py and wasm printed ``N test(s) passed``; ts, rust and go printed "all emitted
tests passed", so a reader of the verdict could not tell a tier that ran zero
tests from one that ran fifty. The count now comes from what the tier actually
ran (vitest's summary, cargo's ``test result:`` lines, go's ``--- PASS`` lines,
a counter in the JVM runner), never from the source's declared tests.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl import compile_source  # noqa: E402
from revl import test as T  # noqa: E402

TWO_TESTS = (
    'fn one() -> Int { return 1 }\n'
    'test "one is one" { assert one() == 1 }\n'
    'test "empty body passes" { }\n'
)

TIERS = ["py", "ts", "rust", "go", "wasm", "java"]


@pytest.mark.parametrize("tier", TIERS)
def test_a_two_test_program_says_2_on_every_available_tier(tier):
    outcome, message = T.RUNNERS[tier](compile_source(TWO_TESTS))
    if outcome == "skip":
        pytest.skip(f"{tier} tier unavailable here: {message}")
    assert outcome == "pass", message
    assert re.search(r"\b2 test\(s\) passed\b", message), message


def test_a_tier_that_ran_nothing_says_0_not_silence():
    outcome, message = T.RUNNERS["py"](compile_source("fn one() -> Int { return 1 }\n"))
    assert outcome == "pass"
    assert re.search(r"\b0 test\(s\) passed\b", message), message


# The count readers, on captured tool output, so the contract is pinned even on
# a runner that has none of the toolchains.

def test_vitest_count_is_read_from_the_summary_not_the_file_list():
    out = ("\x1b[2m Test Files \x1b[22m \x1b[1m\x1b[32m1 passed\x1b[39m (1)\n"
           "\x1b[2m      Tests \x1b[22m \x1b[1m\x1b[32m7 passed\x1b[39m (7)\n")
    assert T._vitest_passed(out) == 7
    assert T._vitest_passed("Tests  1 failed | 4 passed | 1 skipped (6)") == 4
    assert T._vitest_passed("Tests  3 skipped (3)") == 0
    assert T._vitest_passed("no summary here") is None


def test_cargo_count_sums_every_result_line():
    out = ("running 3 tests\ntest result: ok. 3 passed; 0 failed; 0 ignored; "
           "0 measured; 0 filtered out\n"
           "running 0 tests\ntest result: ok. 0 passed; 0 failed; 0 ignored; "
           "0 measured; 0 filtered out\n")
    assert T._cargo_passed(out) == 3
    assert T._cargo_passed("") is None


def test_go_count_is_the_top_level_pass_lines():
    out = ("=== RUN   TestA\n--- PASS: TestA (0.00s)\n=== RUN   TestB\n"
           "--- PASS: TestB (0.00s)\n    --- PASS: TestB/sub (0.00s)\nPASS\n")
    assert T._go_passed(out) == 2
    assert T._go_passed("ok  \trevltest\t0.001s [no tests to run]") == 0


# --- the py, wasm lifecycle and mixed cases, and the cross-check -------------

LIFECYCLE_PROGRAM = (
    "service S {\n  fn inc(k: Int) -> Int\n}\n"
    "component P provides s: S {\n  provide s {\n    fn inc(k) = k + 1\n  }\n}\n"
    'lifecycle test "inc crosses" {\n  load P\n  let d = call s.inc(10)\n'
    "  assert d == 11\n  unload P\n  assert no_residue\n}\n"
)


def _wasm_or_skip(source: str):
    from revl.run_wasm import wasm_runtime_reason  # noqa: PLC0415

    reason = wasm_runtime_reason()
    if reason is not None:
        pytest.skip(f"wasm lifecycle runtime unavailable: {reason}")
    outcome, message = T.RUNNERS["wasm"](compile_source(source))
    if outcome == "skip":
        pytest.skip(f"wasm tier skipped: {message}")
    assert outcome == "pass", message
    return message


def test_a_lifecycle_only_wasm_document_leads_with_the_count():
    message = _wasm_or_skip(LIFECYCLE_PROGRAM)
    assert message.startswith("1 test(s) passed"), message


def test_a_mixed_wasm_document_leads_with_the_total_of_both():
    message = _wasm_or_skip(LIFECYCLE_PROGRAM + TWO_TESTS)
    assert message.startswith("3 test(s) passed"), message


def test_the_wasm_fold_totals_pure_and_lifecycle_without_a_runtime():
    folded = T._combine_wasm_verdicts(
        ("pass", "wasmtime: 2 test(s) passed"),
        ("pass", "1 test(s) passed; cordis-wasm: 1 lifecycle test(s) ran (x)"))
    assert folded == ("pass", "3 test(s) passed; wasmtime: 2 test(s) passed; "
                              "cordis-wasm: 1 lifecycle test(s) ran (x)")


def test_a_py_document_of_only_prop_tests_leads_with_the_total_that_ran():
    source = 'prop test "identity holds" (a: Int) { assert a + 0 == a }\n'
    outcome, message = T.RUNNERS["py"](compile_source(source))
    assert outcome == "pass", message
    assert message.startswith("1 test(s) passed; 1 of 1 prop test(s) held"), message


def test_vitest_count_takes_the_last_tests_line():
    out = "stdout of a test\n Tests  99 passed (99)\n\n Tests  2 passed (2)\n"
    assert T._vitest_passed(out) == 2


def test_cargo_count_ignores_doc_tests():
    out = ("test result: ok. 2 passed; 0 failed; 0 ignored\n"
           "Doc-tests x\ntest result: ok. 5 passed; 0 failed; 0 ignored\n")
    assert T._cargo_passed(out) == 2


def test_a_count_that_disagrees_with_the_collected_tests_fails_the_tier():
    ir = compile_source(TWO_TESTS)
    assert T._count_disagreement("go", 2, ir) is None
    message = T._count_disagreement("go", 1, ir)
    assert message and "ran 1 test(s) but the document has 2" in message
