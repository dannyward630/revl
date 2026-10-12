"""The pure-read guard tests run in `lint`, which runs on every pull request
(issue #2333).

`frontend` runs `pytest tests/`, but it is main-only (#1679). A guard that reads
nothing but tracked repository text therefore went red on main instead of on
the pull request that broke it: a `.md` string literal added to
tests/test_env_gated_skips_run_somewhere.py reddened main behind a green pull
request. The selector change in the same issue re-runs one of them when its
inputs move; this pins the other half, the guards themselves running in a job
that every pull request has.

A guard belongs on the list only if it is PURE-READ: it does not import `revl`
(the `lint` job installs no `revl`), so it reads files and runs nothing of the
product. The list is explicit and names files, never a glob, so a new guard is
a decision in this file.
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
    "tests/test_lint_runs_the_pure_read_guards_2333.py",
    "tests/test_required_checks_pinned.py",
    "tests/test_site_wheel_gate_runs_in_ci.py",
    "tests/test_ts_demo_runs_in_ci.py",
    "tests/test_ts_typecheck_gate_runs_in_ci.py",
    "tests/test_windows_smoke_lane_1950.py",
    "tests/test_workflow_action_pins.py",
)


def _lint_job() -> dict:
    return yaml.safe_load(CI_YML.read_text(encoding="utf-8"))["jobs"]["lint"]


def _guard_step(job: dict) -> dict | None:
    for step in job["steps"]:
        run = step.get("run", "")
        if "pytest" in run and "tests/test_" in run and "pip install" not in run:
            return step
    return None


def _imports_revl(source: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] == "revl" for a in node.names):
                return True
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "revl" and node.level == 0:
                return True
    return False


def test_lint_has_no_job_condition_so_it_runs_on_a_pull_request():
    assert "if" not in _lint_job()


def test_lint_runs_each_named_guard():
    step = _guard_step(_lint_job())
    assert step is not None, "the lint job has no step that runs the guards"
    named = re.findall(r"tests/[A-Za-z0-9_]+\.py", step["run"])
    assert sorted(named) == sorted(set(named)), "a guard is listed twice"
    assert set(named) == set(GUARDS)
    assert "*" not in step["run"], "name the files, no globs"


def test_the_guard_step_survives_an_earlier_red_gate():
    """#1358: a plain step is skipped by any red step above it."""
    job = _lint_job()
    steps = [s for s in job["steps"] if "pytest" in s.get("run", "")]
    assert steps, "no pytest step in lint"
    for step in steps:
        assert step.get("if") == "${{ !cancelled() }}", step


def test_lint_installs_a_pinned_pytest_and_not_revl():
    runs = [s.get("run", "") for s in _lint_job()["steps"]]
    assert any(re.search(r"pip install pytest==\d", r) for r in runs)
    assert not any("pip install -e" in r for r in runs), (
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
