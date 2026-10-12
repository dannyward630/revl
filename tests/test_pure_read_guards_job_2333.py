"""The pure-read guard tests run in their own job on every pull request
(issue #2333).

`frontend` runs `pytest tests/`, but it is main-only (#1679). A guard that reads
nothing but tracked repository text therefore went red on main instead of on
the pull request that broke it: a `.md` string literal added to
tests/test_env_gated_skips_run_somewhere.py reddened main behind a green pull
request. The selector change in the same issue re-runs one of them when its
inputs move; this pins the other half, the guards themselves running in a job
that every pull request has.

A guard belongs on the list only if it needs no `revl` install: it does not
import `revl` (the job does not install revl's dependencies), reads
tracked files, and at most builds scratch git repositories under tmp_path. The
list is explicit and names files, never a glob, so a new guard is a decision in
this file.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"

GUARDS = (
    "tests/test_ci_backend_gate.py",
    "tests/test_ci_census_stale_base_2165.py",
    "tests/test_ci_pr_queue_split_1678.py",
    "tests/test_ci_steps_are_independent.py",
    "tests/test_env_gated_skips_run_somewhere.py",
    "tests/test_every_test_file_runs_in_ci_1465.py",
    "tests/test_frontend_asset_gate_runs_in_ci.py",
    "tests/test_gate_crate_release_path.py",
    "tests/test_gate_dependency_publish_ready.py",
    "tests/test_java_javac_gate_runs_in_ci.py",
    "tests/test_pure_read_guards_job_2333.py",
    "tests/test_required_checks_pinned.py",
    "tests/test_site_wheel_gate_runs_in_ci.py",
    "tests/test_ts_demo_runs_in_ci.py",
    "tests/test_ts_typecheck_gate_runs_in_ci.py",
    "tests/test_windows_smoke_lane_1950.py",
    "tests/test_workflow_action_pins.py",
)


def _workflow() -> dict:
    return yaml.safe_load(CI_YML.read_text(encoding="utf-8"))


def _job() -> dict:
    return _workflow()["jobs"]["pure-read-guards"]


def _guard_step(job: dict) -> dict | None:
    for step in job["steps"]:
        run = step.get("run", "")
        if "pytest" in run and "tests/test_" in run and "pip install" not in run:
            return step
    return None


def args_start(run: str) -> int:
    """Index of the first argument after the pytest options."""
    words = run.split()
    return words.index("no:cacheprovider") + 1


def _imports_revl(source: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] == "revl" for a in node.names):
                return True
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "revl" and node.level == 0:
                return True
    return False


def test_the_job_runs_on_a_pull_request_and_push_and_blocks_nothing():
    """No `if`, so it reports on a pull request and on a push to main; no
    `needs`, so it starts at once; and no other job needs it, so its ~200s
    does not delay a backend job (they all `need` lint)."""
    wf, job = _workflow(), _job()
    triggers = wf.get("on", wf.get(True))
    assert "pull_request" in triggers and "push" in triggers
    assert "if" not in job and "needs" not in job
    assert job["runs-on"] == wf["jobs"]["lint"]["runs-on"]
    for name, other in wf["jobs"].items():
        needs = other.get("needs", [])
        needs = [needs] if isinstance(needs, str) else needs
        assert "pure-read-guards" not in needs, f"{name} waits for the guards"


def test_lint_does_not_run_the_guards():
    """The guards left `lint` because every backend job needs it."""
    for step in _workflow()["jobs"]["lint"]["steps"]:
        assert "pytest" not in step.get("run", ""), step


def test_the_job_runs_each_named_guard():
    step = _guard_step(_job())
    assert step is not None, "the job has no step that runs the guards"
    named = re.findall(r"tests/[A-Za-z0-9_]+\.py", step["run"])
    assert sorted(named) == sorted(set(named)), "a guard is listed twice"
    assert set(named) == set(GUARDS)
    args = step["run"].split()[args_start(step["run"]):]
    assert all(a in GUARDS for a in args), f"only named guard files: {args}"
    assert sum("pytest" in s.get("run", "") and "tests/test_" in s["run"]
               for s in _job()["steps"]) == 1, "one guard step"


def test_the_job_installs_a_pinned_pytest_and_not_revl():
    runs = [s.get("run", "") for s in _job()["steps"]]
    assert any(re.search(r"pip install .*pytest==\d", r) for r in runs)
    assert not any(re.search(r"pip install\s+(-e\s+)?(\.|revl)\b", r)
                   for r in runs), (
        "a guard that needs `revl` is not pure-read; move it out of this list")


@pytest.mark.parametrize("guard", GUARDS)
def test_each_guard_exists_and_does_not_import_revl(guard):
    path = ROOT / guard
    assert path.is_file(), guard
    assert not _imports_revl(path.read_text(encoding="utf-8")), guard


def test_the_import_check_notices_revl():
    """Anti-vacuity: the predicate above fires on the shapes it exists for."""
    assert _imports_revl("import revl.compiler\n")
    assert _imports_revl("from revl import cli\n")
    assert not _imports_revl("import yaml\nfrom pathlib import Path\n")
