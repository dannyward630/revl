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
to be outlasted; the live behaviour (a 6 s inverse ends in `DOWN` on rust and
ts; the rust FATAL line precedes the grace) is asserted beside those runners'
own tests, and the bound each runner computes is run standalone below.
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


# ---------------------------------------------------------------------------
# the bound itself, computed by each runner's own function (no timing involved)
# ---------------------------------------------------------------------------
#
# The runner's `teardown_bound` / `teardownBound` / `teardownGraceMs` is cut out
# of its source file and run on its own, so the numbers below are what the real
# function returns, not a model of it.

import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

#: REVL_TEARDOWN_GRACE (None = unset) -> the bound in seconds.
_CASES = [
    (None, 28.0),        # the conductor's 30 s less the 2 s margin
    ("", 28.0),
    ("junk", 28.0),
    ("0", 28.0),
    ("-3", 28.0),
    ("1", 0.5),          # the margin never exceeds half the grace
    ("6", 4.0),
    ("120", 118.0),
    ("100000", 86398.0),  # clamped to a day, as the conductor clamps it
]


def _between(text: str, start: str, end: str) -> str:
    a = text.index(start)
    return text[a:text.index(end, a)]


def _env(value):
    env = {k: v for k, v in os.environ.items() if k != "REVL_TEARDOWN_GRACE"}
    if value is not None:
        env["REVL_TEARDOWN_GRACE"] = value
    return env


def _bounds(cmd, cwd):
    out = {}
    for value, _ in _CASES:
        done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              env=_env(value), timeout=120)
        assert done.returncode == 0, done.stderr
        out[value] = float(done.stdout.strip())
    return out


def _check(bounds):
    for value, expected in _CASES:
        assert bounds[value] == pytest.approx(expected), (value, bounds)


@pytest.mark.skipif(shutil.which("go") is None, reason="needs a go toolchain")
def test_the_go_bound_for_each_grace(tmp_path):
    src = (ROOT / "backends/go/placement_runner/main.go").read_text(encoding="utf-8")
    body = _between(src, "// defaultTeardownGrace is", "// disposeAwaited disposes")
    (tmp_path / "go.mod").write_text("module bound\n\ngo 1.21\n")
    (tmp_path / "main.go").write_text(
        'package main\n\nimport (\n\t"fmt"\n\t"math"\n\t"os"\n\t"strconv"\n\t"time"\n)\n\n'
        + body + '\nfunc main() { fmt.Println(teardownBound().Seconds()) }\n')
    built = subprocess.run(["go", "build", "-o", "bound", "."], cwd=tmp_path,
                           capture_output=True, text=True, timeout=300)
    assert built.returncode == 0, built.stderr
    _check(_bounds([str(tmp_path / "bound")], tmp_path))


@pytest.mark.skipif(shutil.which("rustc") is None, reason="needs rustc")
def test_the_rust_bound_for_each_grace(tmp_path):
    src = (ROOT / "backends/rust/placement_runner/src/main.rs").read_text(encoding="utf-8")
    body = _between(src, "/// The conductor's own default for", "/// The bound on a teardown")
    (tmp_path / "bound.rs").write_text(
        body + '\nfn main() { println!("{}", teardown_bound().as_secs_f64()); }\n')
    built = subprocess.run(["rustc", "-o", "bound", "bound.rs"], cwd=tmp_path,
                           capture_output=True, text=True, timeout=300)
    assert built.returncode == 0, built.stderr
    _check(_bounds([str(tmp_path / "bound")], tmp_path))


def _node_for_ts():
    for candidate in ("/opt/homebrew/bin", None):
        path = shutil.which("node", path=candidate) if candidate else shutil.which("node")
        if not path:
            continue
        done = subprocess.run([path, "--version"], capture_output=True, text=True)
        try:
            major = int(done.stdout.strip().lstrip("v").split(".")[0])
        except ValueError:
            continue
        if major >= 23:
            return path
    return None


@pytest.mark.skipif(_node_for_ts() is None, reason="needs node >= 23 (strips types)")
def test_the_ts_bound_for_each_grace(tmp_path):
    src = (ROOT / "backends/typescript/placement_runner.ts").read_text(encoding="utf-8")
    body = _between(src, "function teardownGraceMs", "// `log`, written synchronously")
    (tmp_path / "bound.ts").write_text(
        body + "\nconsole.log(teardownGraceMs() / 1000)\n")
    _check(_bounds([_node_for_ts(), str(tmp_path / "bound.ts")], tmp_path))


def test_the_conductor_clamps_a_grace_above_a_day(monkeypatch):
    monkeypatch.setenv("REVL_TEARDOWN_GRACE", "100000")
    assert placement._teardown_grace() == placement._TEARDOWN_GRACE_MAX == 86400.0
    monkeypatch.setenv("REVL_TEARDOWN_GRACE", "120")
    assert placement._teardown_grace() == 120.0
    monkeypatch.setenv("REVL_TEARDOWN_GRACE", "junk")
    assert placement._teardown_grace() == placement._TEARDOWN_GRACE


@pytest.mark.parametrize("tier", sorted(_RUNNERS))
def test_the_runner_clamps_to_the_conductors_maximum(tier):
    patterns = {
        "rust": r"const MAX_TEARDOWN_GRACE_SECS: f64 = ([0-9.]+);",
        "go": r"const maxTeardownGrace = ([0-9.]+)",
        "ts": r"const MAX_TEARDOWN_GRACE_S = ([0-9.]+)",
    }
    found = re.search(patterns[tier], _RUNNERS[tier][0].read_text(encoding="utf-8"))
    assert found, f"{tier} runner declares no maximum grace constant"
    assert float(found.group(1)) == placement._TEARDOWN_GRACE_MAX
