"""Issue #2356: the placement runners' teardown bound follows the conductor's.

The conductor (`src/revl/placement.py`) waits `_TEARDOWN_GRACE` (30 s) for a
child's `DOWN` before killing it. The go, rust and ts runners bounded an
awaited dispose by `REVL_TEARDOWN_GRACE` with a 5 s default, so a correct
inverse taking 5 to 30 s was reported as a failed teardown, and with the
variable set the runner and the conductor fired at the same moment, so the
conductor's kill could swallow the runner's FATAL line.

Each runner now defaults to the conductor's value (the single source) and
gives up a fixed margin before it. This file pins that the three runners carry
the conductor's default and a positive margin that leaves the conductor first
to be outlasted; the live behaviour (a 6 s inverse ends in `DOWN`; the FATAL
line precedes the grace) is asserted beside each runner's own tests.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl import placement  # noqa: E402

_RUNNERS = {
    "rust": (ROOT / "backends/rust/placement_runner/src/main.rs",
             r"const DEFAULT_TEARDOWN_GRACE_SECS: f64 = ([0-9.]+);",
             r"const TEARDOWN_MARGIN_SECS: f64 = ([0-9.]+);"),
    "go": (ROOT / "backends/go/placement_runner/main.go",
           r"const defaultTeardownGrace = ([0-9.]+) \* time\.Second",
           r"const teardownMargin = ([0-9.]+) \* time\.Second"),
    "ts": (ROOT / "backends/typescript/placement_runner.ts",
           r"const DEFAULT_TEARDOWN_GRACE_S = ([0-9.]+)",
           r"const TEARDOWN_MARGIN_S = ([0-9.]+)"),
}


@pytest.mark.parametrize("tier", sorted(_RUNNERS))
def test_the_runner_defaults_to_the_conductors_grace(tier):
    path, default_re, _ = _RUNNERS[tier]
    found = re.search(default_re, path.read_text(encoding="utf-8"))
    assert found, f"{tier} runner declares no default teardown grace constant"
    assert float(found.group(1)) == placement._TEARDOWN_GRACE


@pytest.mark.parametrize("tier", sorted(_RUNNERS))
def test_the_runner_stops_a_margin_before_the_grace(tier):
    path, _, margin_re = _RUNNERS[tier]
    found = re.search(margin_re, path.read_text(encoding="utf-8"))
    assert found, f"{tier} runner declares no teardown margin constant"
    assert 0 < float(found.group(1)) < placement._TEARDOWN_GRACE
