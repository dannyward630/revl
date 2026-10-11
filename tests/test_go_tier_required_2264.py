"""A go test that probes for the toolchain by hand fails when go is required.

Issue #2264. ``REVL_REQUIRE_TIERS`` made an absent toolchain a failure only for
a test that went through a ``revl.test`` runner, and the go tier was exempt
from it anyway. Most go tests probe the toolchain themselves and skip, so a CI
job that lost go skipped them all and went green.

The repository-root ``conftest.py`` now turns that skip into a failure when the
session requires go and go is not on PATH. These tests run real go test files
in a child pytest with go stripped from PATH, once with the tier required and
once without, and check both outcomes. Each node is one probe shape in use
today: a ``skipif`` marker, a module ``pytestmark`` and an inline
``pytest.skip`` in a backends/go test.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

NODES = (
    "tests/test_run_go.py::test_go_unused_match_arm_payload_still_builds_and_runs",
    "tests/test_go_seam_registry_scrub.py::test_bridge_funnel_suite_passes",
    "backends/go/test_opt_gaps_280.py::test_go_build_and_test_pass",
)


def _path_without_go() -> str:
    """PATH with every directory that holds a `go` binary removed."""
    keep = [d for d in os.environ.get("PATH", "").split(os.pathsep)
            if d and not (Path(d) / "go").exists()]
    return os.pathsep.join(keep)


def _run(node: str, require: str | None) -> str:
    env = {**os.environ, "PATH": _path_without_go()}
    env.pop("REVL_REQUIRE_TIERS", None)
    if require is not None:
        env["REVL_REQUIRE_TIERS"] = require
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", node],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=600,
    )
    return result.stdout + result.stderr


@pytest.mark.parametrize("node", NODES)
def test_a_hand_probed_go_test_fails_when_go_is_required_and_absent(node):
    unrequired = _run(node, None)
    assert "1 skipped" in unrequired, unrequired

    # `all` on one node, an explicit list on the others: same switch
    required = _run(node, "all" if node == NODES[0] else "py,ts,go")
    _assert_red(required)


def _assert_red(output: str) -> None:
    # a skip raised in setup (a `skipif` marker, a fixture) reports as an
    # error, one raised in the test body as a failure; both are red
    assert re.search(r"\b1 (failed|error)\b", output), output
    assert "1 skipped" not in output, output
    assert "the go tier is REQUIRED here" in output, output
