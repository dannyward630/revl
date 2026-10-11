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
    root = _tree(tmp_path, 2345, 1900.0)
    assert docgen.suite_size(root) == (2345, 1900.0)
    body = docgen.block_suite_size("", root)
    assert "more than 2,000 test functions" in body
    assert "about\n30 minutes of test time in CI" in body


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
