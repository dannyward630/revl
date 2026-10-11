"""The docs state the root suite's size from the tree, not by hand (issue #2217).

CONTRIBUTING.md said "1500+ tests (~60s)", tools/affected_tests.py "~8-minute"
and the pre-commit hook "about an hour", for a suite of about 26,000 collected
tests. The size line is now the `suite-size` docgen block, rendered from the
AST of tests/**/test_*.py and from tests/shard_weights.json, and the other two
sites point at it instead of restating a number.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _load_by_path import load_by_path

ROOT = Path(__file__).resolve().parents[1]
docgen = load_by_path("revl_docgen_suite_size", ROOT / "tools" / "docgen.py")


def _tree(tmp: Path, functions: int, seconds: float) -> Path:
    tests = tmp / "tests"
    (tests / "sub").mkdir(parents=True)
    half = functions // 2
    (tests / "test_a.py").write_text(
        "".join(f"def test_{i}():\n    pass\n" for i in range(half))
        + "def helper():\n    pass\n", encoding="utf-8")
    (tests / "sub" / "test_b.py").write_text(
        "class TestB:\n"
        + "".join(f"    def test_{i}(self):\n        pass\n"
                  for i in range(functions - half)), encoding="utf-8")
    (tests / "shard_weights.json").write_text(
        json.dumps({"seconds": {"tests/test_a.py": seconds}}), encoding="utf-8")
    return tmp


def test_the_block_is_rendered_from_the_tree(tmp_path):
    root = _tree(tmp_path / "a", 12_345, 1900.0)
    assert docgen.suite_size(root) == (12_345, 1900.0)
    body = docgen.block_suite_size("", root)
    assert "more than 10,000 test" in body
    assert "tens of CI minutes" in body


def test_the_text_does_not_move_with_normal_growth(tmp_path):
    small = docgen.block_suite_size("", _tree(tmp_path / "a", 10_001, 1300.0))
    large = docgen.block_suite_size("", _tree(tmp_path / "b", 14_999, 6000.0))
    assert small == large


@pytest.mark.parametrize("functions, seconds", [
    (9_999, 2400.0),    # under the floor
    (12_000, 1100.0),   # under 20 CI minutes
    (12_000, 7300.0),   # over 120 CI minutes
])
def test_a_false_claim_fails_the_check(tmp_path, functions, seconds):
    with pytest.raises(SystemExit):
        docgen.block_suite_size("", _tree(tmp_path, functions, seconds))


def test_contributing_carries_the_generated_block():
    keys = {(key, rel) for key, rel, _, _ in docgen.BLOCKS}
    assert ("suite-size", "CONTRIBUTING.md") in keys
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert docgen.extract(text, "suite-size") == docgen.block_suite_size("")


def test_no_site_restates_the_old_figures():
    sites = {
        "CONTRIBUTING.md": ("1500+ tests", "~60s);"),
        "tools/affected_tests.py": ("~8-minute", "(~8 min)"),
        "tools/hooks/pre-commit": ("about an hour",),
    }
    for rel, stale in sites.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        for phrase in stale:
            assert phrase not in text, f"{rel} still says {phrase!r}"
