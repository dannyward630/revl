"""`make pre-merge` names every suite only CI runs (issue #2210).

CI runs whole backend directories (`pytest backends/<tier>/`), vitest, and the
conformance steps that set `REVL_CROSS_TIER_SLOW`, `REVL_SWEEP_ALL_TIERS` or a
`REVL_REQUIRE_*` switch. tools/pre_merge.sh ran only the `test_emit_*` file of
each tier and set no REVL_ switch, and it did not mention the rest, so a green
local gate said nothing about roughly a thousand backend tests, all of vitest
and the rust/java semantic floor.

These tests read ci.yml with their own small rule, independent of
tools/ci_suites.py, and require `pre_merge.sh --plan` to list every such step
either as run or as SKIPPED with the flag that runs it. `--plan` runs nothing.
"""

from __future__ import annotations

import os
import posixpath
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from _load_by_path import load_by_path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "pre_merge.sh"
HELPER = ROOT / "tools" / "ci_suites.py"
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"


# ------------------------------------------------- the oracle, read from ci.yml

def _targets(run: str) -> list[str]:
    """Every path a pytest call in `run` names, from the repo root."""
    out, cwd = [], "."
    for part in re.split(r"&&|;|\n", run):
        try:
            words = shlex.split(part)
        except ValueError:
            words = part.split()
        if words[:1] == ["cd"] and len(words) > 1:
            cwd = words[1]
        elif any(w.endswith("pytest") for w in words):
            i = next(i for i, w in enumerate(words) if w.endswith("pytest"))
            paths = [w for w in words[i + 1:] if not w.startswith("-")
                     and ("/" in w or w.endswith(".py"))] or ["."]
            out += [posixpath.normpath(posixpath.join(cwd, p)) for p in paths]
    return out


def _ci_only_steps() -> dict[str, dict]:
    """`job/index` of every CI step pre-merge does not run by default."""
    doc = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    found = {}
    def switched(env):
        return any(k in ("REVL_CROSS_TIER_SLOW", "REVL_SWEEP_ALL_TIERS")
                   or k.startswith("REVL_REQUIRE_") for k in env)

    for job, spec in doc["jobs"].items():
        job_env = spec.get("env") or {}
        for i, step in enumerate(spec.get("steps") or []):
            run = str(step.get("run") or "")
            env = step.get("env") or {}
            if not run:
                continue
            targets = _targets(run)
            backend = any(t.startswith("backends") for t in targets)
            vitest = "vitest" in run
            # A job-level switch reaches every pytest the job runs.
            switch = switched(env) or bool(targets and switched(job_env))
            if backend or vitest or switch:
                found[f"{job}/{i}"] = {"run": run, "env": env}
    return found


def _assert_finds_the_suites_the_issue_names(steps: dict[str, dict]) -> None:
    """Positive control: a rule that matched nothing would pass every check
    below. The issue's three kinds each have to be in the set."""
    runs = {k: " ".join(v["run"].split()) for k, v in steps.items()}
    assert any(k.startswith("backend-go/") and "pytest backends/go/" in r
               for k, r in runs.items()), runs
    assert any(k.startswith("backend-typescript/") and "vitest" in r
               for k, r in runs.items()), runs
    assert any("REVL_CROSS_TIER_SLOW" in v["env"] for v in steps.values())
    assert any("REVL_SWEEP_ALL_TIERS" in v["env"] for v in steps.values())
    # The frontend job's `pytest tests/` runs under its job-level
    # REVL_REQUIRE_TIERS=go, which the gate's frontend step does not set.
    assert any(k.startswith("frontend/") and "pytest tests/" in r
               for k, r in runs.items()), runs


# ------------------------------------------------------------- the plan output

def _plan(*args: str) -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    # Without --plan the script ignores the flag and runs the whole gate.
    assert "--plan) PLAN=1" in text, "tools/pre_merge.sh has no --plan mode"
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", "")
    env.pop("REVL_PREMERGE_WITH", None)
    out = subprocess.run(["sh", str(SCRIPT), "--plan", *args], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=300, check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "nothing was run" in out.stdout, out.stdout + out.stderr
    return out.stdout


def _lines_by_id(stdout: str) -> dict[str, str]:
    lines = {}
    for ln in stdout.splitlines():
        m = re.match(r"\s+ci-only (\S+?): ", ln)
        if m:
            lines[m.group(1)] = ln
    return lines


def test_every_ci_only_suite_is_listed_skipped_with_its_opt_in():
    """The default gate runs none of them (its wall time stays put) and names
    each one, with the CI job that runs it and the flag that runs it here."""
    steps = _ci_only_steps()
    _assert_finds_the_suites_the_issue_names(steps)
    lines = _lines_by_id(_plan())
    for sid in steps:
        job = sid.split("/")[0]
        assert sid in lines, f"pre_merge.sh --plan does not list CI step {sid}"
        line = lines[sid]
        if "covered (runs above as" in line:
            continue
        assert "would run" not in line, line
        assert f"SKIPPED (not opted in; CI job {job} runs it" in line, line
        assert f"--with={job}" in line, line


def test_opted_in_each_suite_runs_or_says_what_is_missing():
    """With --with=all nothing reads as not opted in: a suite either would run
    or is SKIPPED with the missing toolchain named."""
    lines = _lines_by_id(_plan("--with=all"))
    for sid in _ci_only_steps():
        line = lines[sid]
        assert "not opted in" not in line, line
        m = re.search(r"  (would run: \S|SKIPPED \(.{5,}\)|covered \()", line)
        assert m, line


def test_a_run_line_carries_the_ci_switches():
    """backend-go sets REVL_REQUIRE_TIERS=go for the job; the local run of it
    has to set it too, or a go probe that skips is a green here."""
    mod = load_by_path("ci_suites_2210", HELPER)
    suites = {s.id: s for s in mod.ci_suites(CI_YML)}
    go = next(s for s in suites.values()
              if s.job == "backend-go" and "backends/go" in s.targets)
    assert mod.switches(go).get("REVL_REQUIRE_TIERS") == "go"
    slow = next(s for s in suites.values() if "REVL_CROSS_TIER_SLOW" in s.env)
    assert mod.switches(slow)["REVL_CROSS_TIER_SLOW"] == "1"
    java = next(s for s in suites.values() if s.job == "backend-java")
    assert "REVL_CORDIS4J_CLASSES" not in mod.switches(java)  # a runner path
    assert mod._str_env({"REVL_X": True}) == {"REVL_X": "true"}  # as CI exports it


def test_an_unknown_opt_in_name_is_refused():
    """A typo in --with must not leave the suite quietly not opted in."""
    out = subprocess.run([sys.executable, str(HELPER), "--root", str(ROOT), "--list",
                          "--with", "backend-goo"], capture_output=True, text=True,
                         timeout=120, check=False)
    assert out.returncode == 2, out.stdout + out.stderr
    assert "backend-goo" in out.stderr and "backend-go" in out.stderr


# --------------------------------------------- the run path, on a fixture tree

FIXTURE_CI = """
jobs:
  backend-roots-combined:
    env:
      REVL_REQUIRE_TIERS: "zz"
    steps:
      - run: pytest backends/x/ -q
        env:
          REVL_ELSEWHERE: /runner/only/path
"""

FIXTURE_TEST = """
import os
def test_switches():
    assert os.environ["REVL_REQUIRE_TIERS"] == "zz"
    assert os.environ.get("REVL_ELSEWHERE") != "/runner/only/path"
def test_{name}():
    assert {ok}
"""


def _fixture(tmp_path: Path, ok: bool) -> tuple[Path, Path]:
    (tmp_path / "backends" / "x").mkdir(parents=True)
    (tmp_path / "backends" / "x" / "test_x.py").write_text(
        FIXTURE_TEST.format(name="ok" if ok else "bad", ok=ok), encoding="utf-8")
    ci = tmp_path / "ci.yml"
    ci.write_text(FIXTURE_CI, encoding="utf-8")
    wrapper = tmp_path / "pytest-wrapper"
    wrapper.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} -m pytest "
                       "-p no:cacheprovider \"$@\"\n", encoding="utf-8")
    wrapper.chmod(0o755)
    return ci, wrapper


@pytest.mark.parametrize("ok,rc_ok,count", [(True, True, "2 passed"),
                                            (False, False, "1 failed, 1 passed")])
def test_run_executes_the_ci_command_with_its_switches(tmp_path, ok, rc_ok, count):
    ci, wrapper = _fixture(tmp_path, ok)
    env = {k: v for k, v in os.environ.items() if not k.startswith("REVL_")}
    out = subprocess.run([sys.executable, str(HELPER), "--root", str(tmp_path),
                          "--ci", str(ci), "--run", "backend-roots-combined/0",
                          "--pytest", str(wrapper)], capture_output=True, text=True,
                         timeout=300, check=False, env=env)
    assert (out.returncode == 0) is rc_ok, out.stdout + out.stderr
    assert count in out.stdout, out.stdout + out.stderr


# ------------------------------------ the shell mapping of each listed state

STUB = """
import sys
if "--list" in sys.argv:
    rows = [("j/1", "run", "ci-only j/1: a", "pytest a"),
            ("j/5", "run", "ci-only j/5: e", "pytest e"),
            ("j/2", "skip", "ci-only j/2: b", "no cargo"),
            ("j/3", "optout", "ci-only j/3: c", "opt in: --with=j"),
            ("j/4", "covered", "ci-only j/4: d", "runs above as x")]
    for r in rows:
        print("\\t".join(r))
else:
    sys.stdin.read()  # a suite that reads stdin must not eat the list
    print("===== 3 passed in 0.1s =====")
"""


def test_the_gate_counts_each_state(tmp_path):
    text = SCRIPT.read_text(encoding="utf-8")
    start, end = "# >>> ci-only-step", "# <<< ci-only-step"
    assert start in text and end in text, "ci-only-step markers are gone"
    body = text[text.index(start):text.index(end)]
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "ci_suites.py").write_text(STUB, encoding="utf-8")
    script = ("ran=0\nskipped=0\nplanned=0\noptout=0\nfail=0\nPLAN=0\nWITH=\n"
              f"PYTEST=pytest\nPYTHON={shlex.quote(sys.executable)}\nroot=.\n"
              'skip() { printf "  %s  SKIPPED (%s)\\n" "$1" "$2"; skipped=$((skipped + 1)); }\n'
              + body + "ci_only_suites\n"
              'echo "ran=$ran skipped=$skipped optout=$optout fail=$fail"\n')
    out = subprocess.run(["sh", "-c", script], cwd=tmp_path, capture_output=True,
                         text=True, timeout=120, check=False)
    assert "ran=2 skipped=1 optout=1 fail=0" in out.stdout, out.stdout + out.stderr
    assert "ci-only j/1: a  ok (3 passed in 0.1s)" in out.stdout, out.stdout
    assert "ci-only j/2: b  SKIPPED (no cargo)" in out.stdout
    assert "SKIPPED (not opted in; CI job j runs it; opt in: --with=j)" in out.stdout
    assert "j/4" not in out.stdout  # covered is silent outside --plan
