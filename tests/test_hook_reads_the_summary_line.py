"""The pre-commit hook reads pytest's counts from the summary line only.

`pytest_count` used to read the last line of the output. stderr printed after
the summary (a teardown ResourceWarning, an atexit message) is then the last
line: a real pass read as nothing verified, and a stray "1 passed" in that
stderr turned an all-skipped run into a pass. It now anchors on the LAST line
that ends like pytest's summary (" in 0.10s"). With no summary line there is no
count, which reads as UNVERIFIED for an affected selection and as a refusal for
the FULL core subset.

Each case slices the real shell functions out of tools/hooks/pre-commit.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "tools" / "hooks" / "pre-commit"

if sys.platform == "win32":  # the hook is a POSIX shell script
    pytest.skip("the pre-commit hook runs under sh", allow_module_level=True)


def _function(name: str) -> str:
    text = HOOK.read_text(encoding="utf-8")
    start = text.index(f"\n{name}() {{\n") + 1
    return text[start:text.index("\n}\n", start) + 3]


def _sh(body: str, output: str) -> subprocess.CompletedProcess:
    script = (_function("pytest_count") + _function("pytest_ran_tests")
              + _function("pytest_counted") + "fail=0\nunverified=0\n"
              + _function("step") + body)
    return subprocess.run(["sh", "-c", script, "sh", output], capture_output=True,
                          text=True, timeout=60, check=False)


def _count(outcome: str, output: str) -> str:
    return _sh(f'pytest_count {outcome} "$1"\n', output).stdout.strip()


SKIPPED_THEN_STDERR = ("ss.\n3 skipped in 0.10s\n"
                       "sys:1: ResourceWarning: 1 passed handle left open\n")
PASSED_THEN_STDERR = ("....\n4 passed in 0.20s\n"
                      "Exception ignored in atexit callback\n")


def test_stderr_after_the_summary_is_not_a_pass():
    assert _count("passed", SKIPPED_THEN_STDERR) == ""
    assert _count("skipped", SKIPPED_THEN_STDERR) == "3"


def test_stderr_after_the_summary_does_not_hide_a_pass():
    assert _count("passed", PASSED_THEN_STDERR) == "4"


def test_the_last_summary_line_wins_and_its_decoration_is_allowed():
    out = ("1 passed in 0.01s\n"
           "=========== 2 failed, 5 passed in 1.23s (0:00:01) ===========\n")
    assert _count("passed", out) == "5"


def test_a_coloured_summary_is_read():
    # FORCE_COLOR=1 / PY_COLORS=1: escape codes around the counts and after
    # " in 0.02s".
    out = ("\x1b[32m.\x1b[0m\n\x1b[32m\x1b[1m2 passed\x1b[0m\x1b[32m, "
           "\x1b[33m1 skipped\x1b[0m\x1b[32m in 0.02s\x1b[0m\n")
    assert _count("passed", out) == "2"
    assert _count("skipped", out) == "1"


def test_no_summary_line_is_no_count():
    assert _count("passed", "collecting ...\n1 passed handle warning\n") == ""


def test_an_affected_run_with_stderr_after_an_all_skipped_summary_is_skipped():
    # The stub stands in for the affected pytest command: exit 0, all skipped,
    # then stderr that says "1 passed".
    out = _sh('stub() { printf "%s" "$1"; }\n'
              'step "frontend (affected)" pytest_counted stub "$1"\n'
              'echo "fail=$fail unverified=$unverified"\n', SKIPPED_THEN_STDERR)
    assert "SKIPPED (0 passed, 3 skipped: nothing verified)" in out.stdout, out.stdout
    assert "fail=0 unverified=1" in out.stdout


def test_the_core_subset_with_no_real_pass_is_refused():
    out = _sh('pytest_ran_tests 0 "$1"; echo "rc=$?"\n', SKIPPED_THEN_STDERR)
    assert "rc=5" in out.stdout, out.stdout
    assert "nothing checked this change" in out.stdout
