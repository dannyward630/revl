"""The pre-commit hook never reports "ok" for a change it ran no test against
(issue #2208).

Every change to a compile-reachable module (parser, typecheck, lower, compiler
and the rest) makes the selector answer FULL. The hook used to run `pytest
tests/` under a 60s ceiling for that answer. The root suite takes about an
hour, so the ceiling always tripped, the hook printed SKIPPED, left `fail=0`
and ended with `pre-commit: ok`: every checker commit landed with zero tests
run.

A FULL selection now runs a defined core subset under the ceiling, reports how
many tests it passed, and refuses the commit when the subset times out, runs no
test, or fails. An affected selection that collects nothing, or whose every
test skips (a machine without a backend's toolchain), does not block the
commit, but the step reads SKIPPED and the hook never ends with a bare ok.
Only pytest's summary line counts: a warning that says "1 passed" is not a
pass.

Each case builds a throwaway repository with the real hook, a stub selector
and a stub pytest, stages a checker-only change, and commits through the hook.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

import pytest

from _load_by_path import load_by_path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "tools" / "hooks"

if sys.platform == "win32":  # the hook is a POSIX shell script
    pytest.skip("the pre-commit hook runs under sh", allow_module_level=True)

CHECKER_CHANGE = "src/revl/lower.py"

# What the real selector prints for a staged src/revl/lower.py.
_FULL_SELECTOR = (
    "print('FULL 1')\n"
    "print('REASON src/revl/lower is core -> full')\n"
    "print('PYTEST tests/')\n"
)
_AFFECTED_SELECTOR = (
    "print('FULL 0')\n"
    "print('REASON src/revl/lower.py (named by 1 test(s))')\n"
    "print('PYTEST tests/test_lower_probe.py')\n"
)
# The stub pytest: `--help` answers at once (the hook probes it for
# pytest-timeout). A real run records its arguments, then behaves as
# HOOK_PYTEST_MODE says.
_PYTEST_MAIN = (
    "import os, sys, time\n"
    "if '--help' in sys.argv:\n"
    "    sys.exit(0)\n"
    "log = os.environ['HOOK_LOG']\n"
    "with open(log, 'a') as f:\n"
    "    f.write('pytest ' + ' '.join(sys.argv[1:]) + '\\n')\n"
    "mode = os.environ['HOOK_PYTEST_MODE']\n"
    "if mode == 'hang':\n"
    "    time.sleep(30)\n"
    "    with open(log, 'a') as f:\n"
    "        f.write('pytest-finished\\n')\n"
    "elif mode == 'pass':\n"
    "    print('540 passed, 1 skipped in 2.09s')\n"
    "elif mode == 'skip':\n"
    "    print('3 skipped in 0.10s')\n"
    "elif mode == 'skip-warn':\n"
    "    print('tests/test_x.py:3: UserWarning: expected 1 passed')\n"
    "    print('3 skipped, 1 warning in 0.10s')\n"
    "elif mode == 'empty':\n"
    "    print('no tests ran in 0.01s')\n"
    "    sys.exit(5)\n"
)
_CONFORMANCE = (
    "import os\n"
    "with open(os.environ['HOOK_LOG'], 'a') as f:\n"
    "    f.write('conformance\\n')\n"
)

BUDGET = 2


def _run(args, cwd, env=None, timeout=120):
    return subprocess.run(args, cwd=str(cwd), env=env, capture_output=True,
                          text=True, timeout=timeout)


def _git(cwd, *args, env):
    proc = _run(["git", *args], cwd, env)
    assert proc.returncode == 0, f"git {' '.join(args)}: {proc.stderr}"
    return proc.stdout.strip()


def _make_python_with_pytest(path: Path) -> Path:
    venv.create(path, with_pip=False, symlinks=True)
    python = path / "bin" / "python"
    purelib = Path(_run([str(python), "-c",
                         "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                        path).stdout.strip())
    package = purelib / "pytest"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(_PYTEST_MAIN, encoding="utf-8")
    return python


@pytest.fixture(scope="module")
def stub_python(tmp_path_factory):
    return _make_python_with_pytest(tmp_path_factory.mktemp("venv") / "venv")


@pytest.fixture
def checkout(tmp_path):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("GIT_") and k not in ("VIRTUAL_ENV", "PYTHONPATH",
                                                     "REVL_HOOK_PYTHON",
                                                     "REVL_HOOK_CORE_TESTS",
                                                     "REVL_HOOK_FULL_BUDGET")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
               HOOK_LOG=str(tmp_path / "hook.log"))
    repo = tmp_path / "repo"
    (repo / "tools" / "hooks").mkdir(parents=True)
    for hook in HOOKS.iterdir():
        target = repo / "tools" / "hooks" / hook.name
        shutil.copy2(hook, target)
        target.chmod(0o755)
    (repo / "tools" / "conformance.py").write_text(_CONFORMANCE, encoding="utf-8")
    (repo / "src" / "revl").mkdir(parents=True)
    (repo / "src" / "revl" / "__init__.py").write_text("", encoding="utf-8")
    (repo / CHECKER_CHANGE).write_text("def lower():\n    return None\n",
                                       encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main", env=env)
    _git(repo, "config", "user.email", "t@example.com", env=env)
    _git(repo, "config", "user.name", "t", env=env)
    _git(repo, "add", "-A", env=env)
    _git(repo, "commit", "-qm", "base", "--no-verify", env=env)
    _git(repo, "config", "core.hooksPath", "tools/hooks", env=env)
    return {"env": env, "repo": repo, "log": tmp_path / "hook.log"}


def _commit_checker_change(c, python, selector, mode):
    """Stage a checker-only change and commit it through the hook."""
    repo = c["repo"]
    (repo / "tools" / "affected_tests.py").write_text(selector, encoding="utf-8")
    _git(repo, "add", "tools/affected_tests.py", env=c["env"])
    _git(repo, "commit", "-qm", "stub selector", "--no-verify", env=c["env"])
    with open(repo / CHECKER_CHANGE, "a", encoding="utf-8") as f:
        f.write("# a comment in the checker\n")
    _git(repo, "add", CHECKER_CHANGE, env=c["env"])
    env = dict(c["env"], REVL_HOOK_PYTHON=str(python),
               REVL_HOOK_FULL_BUDGET=str(BUDGET), HOOK_PYTEST_MODE=mode)
    proc = _run(["git", "commit", "-qm", "checker-only change"], repo, env,
                timeout=90)
    ran = c["log"].read_text(encoding="utf-8").splitlines() if c["log"].exists() else []
    return proc, proc.stdout + proc.stderr, ran


def test_the_real_selector_answers_full_for_a_checker_change():
    """The stub selectors below print what the real one says for this path."""
    affected = load_by_path("affected_tests_2208", ROOT / "tools" / "affected_tests.py")
    sel = affected.select([CHECKER_CHANGE], ROOT)
    assert sel["full"] is True, sel
    assert sel["pytest"] == ["tests/"], sel


def test_a_full_selection_that_runs_out_of_budget_refuses_the_commit(checkout,
                                                                     stub_python):
    proc, out, ran = _commit_checker_change(checkout, stub_python, _FULL_SELECTOR,
                                            "hang")
    assert "pre-commit: ok" not in out, out
    assert proc.returncode != 0, out
    assert "FAILED (the core subset exceeded the %ds budget)" % BUDGET in out, out
    assert "selector: FULL src/revl/lower is core -> full" in out, out
    assert "staged: " + CHECKER_CHANGE in out, out
    assert "--no-verify" in out, out
    assert "pytest-finished" not in ran, ran
    assert "conformance" in ran, ran
    assert "checker-only change" not in _git(checkout["repo"], "log", "--format=%s",
                                             env=checkout["env"])


def test_a_full_selection_runs_the_core_subset_and_says_so(checkout, stub_python):
    proc, out, ran = _commit_checker_change(checkout, stub_python, _FULL_SELECTOR,
                                            "pass")
    assert proc.returncode == 0, out
    runs = [line for line in ran if line.startswith("pytest ")]
    assert len(runs) == 1, ran
    args = runs[0].split()
    assert "tests/test_frontend.py" in args and "tests/test_doc_examples.py" in args, runs
    assert "tests/" not in args, (
        f"the FULL selection ran the hour-long root suite: {runs}")
    assert "ok (core subset only: 540 passed; the full suite did not run)" in out, out


@pytest.mark.parametrize("mode,expected", [
    ("skip", "pytest passed no test"),
    ("skip-warn", "pytest passed no test"),
    ("empty", "pytest collected no tests"),
], ids=["all-skipped", "all-skipped-warning-says-passed", "none-collected"])
def test_a_full_selection_whose_core_subset_runs_no_test_refuses(checkout,
                                                                 stub_python,
                                                                 mode, expected):
    proc, out, _ran = _commit_checker_change(checkout, stub_python, _FULL_SELECTOR,
                                             mode)
    assert "pre-commit: ok" not in out, out
    assert proc.returncode != 0, out
    assert expected in out, out


@pytest.mark.parametrize("mode,expected", [
    ("skip", "SKIPPED (0 passed, 3 skipped: nothing verified)"),
    ("skip-warn", "SKIPPED (0 passed, 3 skipped: nothing verified)"),
    ("empty", "SKIPPED (0 passed, 0 skipped: nothing verified)"),
], ids=["all-skipped", "all-skipped-warning-says-passed", "none-collected"])
def test_an_affected_selection_that_runs_no_test_is_skipped_not_ok(checkout,
                                                                   stub_python,
                                                                   mode, expected):
    """It does not block: a machine without a backend's toolchain skips that
    backend's tests, and blocking would only teach --no-verify. But it is not
    reported as ok either."""
    proc, out, _ran = _commit_checker_change(checkout, stub_python,
                                             _AFFECTED_SELECTOR, mode)
    lines = [line.strip() for line in out.splitlines()]
    assert proc.returncode == 0, out
    assert expected in out, out
    assert "pre-commit: ok" not in lines, out
    assert ("pre-commit: ok, but the affected tests verified nothing "
            "(see SKIPPED above)") in lines, out
