"""Issue #2445: the conductor reacts to a runner that cannot boot.

Every runner prints `[name] FATAL <detail>` and exits non-zero when its boot
fails (#2435). The conductor used to count only `UP` lines, so a runner that
died before `UP` cost the whole 60 second wait and was then reported as
"processes did not come up: <names>", with the runner's own error visible only
in the pumped trace. It now ends the wait as soon as a child has printed a
FATAL line or exited without `UP`, names that child with its error and exit
code on stderr, and fails the placement without opening the swap REPL.

The first group uses the stubbed-child pattern of `tests/test_distribute.py`.
The last test boots the real python runner with a spec that makes its boot
fail.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl import placement  # noqa: E402

APP = str(ROOT / "examples" / "user_cache.rvl")
PLACEMENT = str(ROOT / "examples" / "placement" / "user_cache.toml")

# Far below the 60 s the conductor used to wait, far above any scheduling noise.
FAST = 20.0


class _FakeProc:
    """A Popen double. `code` is None while the child is alive; `terminate`
    and `kill` end it with 0 so the teardown does not wait on it."""

    def __init__(self, name, lines, code):
        self.stdout = io.StringIO("".join(f"[{name}] {line}\n" for line in lines))
        self.stdin = io.StringIO()
        self._code = code

    def poll(self):
        return self._code

    def wait(self, timeout=None):
        return self._code if self._code is not None else 0

    def terminate(self):
        if self._code is None:
            self._code = 0

    kill = terminate


def _run(monkeypatch, capsys, bad_lines, bad_code, once):
    """Run user_cache with `consumer` failing as given and `provider` healthy.

    `once` is True, False (stdin is not a tty: the scripted swap path) or
    "tty" (the interactive path, with its prompt answered by EOF)."""
    monkeypatch.setattr(placement, "_cordis_py_installed", lambda: True)
    if once == "tty":
        monkeypatch.setattr(placement, "_interactive", lambda: True)

        def eof(prompt=""):
            raise EOFError

        monkeypatch.setattr("builtins.input", eof)
        once = False

    def fake_popen(cmd, **kwargs):
        name = json.loads(Path(cmd[-1]).read_text(encoding="utf-8"))["name"]
        if name == "consumer":
            return _FakeProc(name, bad_lines, bad_code)
        return _FakeProc(name, ["UP", "DOWN"], 0)

    monkeypatch.setattr(placement.subprocess, "Popen", fake_popen)
    started = time.monotonic()
    rc = placement.run_placement([APP], PLACEMENT, once=once)
    return rc, time.monotonic() - started, capsys.readouterr().err


@pytest.mark.parametrize("once", [True, False, "tty"])
def test_a_fatal_line_ends_the_wait_and_names_the_runner(monkeypatch, capsys, once):
    rc, elapsed, err = _run(monkeypatch, capsys,
                            ["FATAL RuntimeError: boot failed loading Consumer"],
                            None, once)
    assert elapsed < FAST, elapsed
    assert rc == 1
    assert ("error: process consumer failed to boot: "
            "RuntimeError: boot failed loading Consumer") in err, err
    assert "did not come up" not in err, err


@pytest.mark.parametrize("once", [True, False, "tty"])
def test_an_exit_before_up_ends_the_wait_with_the_exit_code(monkeypatch, capsys, once):
    rc, elapsed, err = _run(monkeypatch, capsys, [], 7, once)
    assert elapsed < FAST, elapsed
    assert rc == 1
    assert ("error: process consumer failed to boot: "
            "exited with code 7 before it reported up") in err, err


def test_the_fatal_line_and_the_exit_code_are_both_reported(monkeypatch, capsys):
    rc, elapsed, err = _run(monkeypatch, capsys,
                            ["FATAL RuntimeError: out of room"], 1, True)
    assert elapsed < FAST, elapsed
    assert rc == 1
    assert ("error: process consumer failed to boot: "
            "RuntimeError: out of room (exit code 1)") in err, err


def test_a_child_that_says_up_then_exits_is_not_a_boot_failure(monkeypatch, capsys):
    """The `UP` line is read before the exit is judged: a runner that comes up
    and is gone by the time the conductor looks has booted."""
    rc, _, err = _run(monkeypatch, capsys, ["UP", "DOWN"], 0, True)
    assert rc == 0, err
    assert "failed to boot" not in err, err


# ---------------------------------------------------------------------------
# the real python runner
# ---------------------------------------------------------------------------

_APP = """\
service Cache { fn get(key: Str) -> Str }

component MemCache provides cache: Cache {
  provide cache { fn get(key) = "v:" + key }
}

component Consumer requires cache: Cache {}
"""

_TOML = """\
[processes.provider]
components = ["MemCache"]

[processes.consumer]
components = ["Consumer"]
"""


def test_a_real_runner_that_cannot_boot_fails_the_placement_fast(
        tmp_path, monkeypatch, capsys):
    """The consumer's spec names a source file that does not exist, so the real
    runner prints its FATAL line and exits 1 before `UP`."""
    if not placement._cordis_py_installed():
        pytest.skip("cordis-py runtime not installed (sh backends/python/setup.sh)")
    app = tmp_path / "app.rvl"
    app.write_text(_APP, encoding="utf-8")
    toml = tmp_path / "app.toml"
    toml.write_text(_TOML, encoding="utf-8")

    real_popen = subprocess.Popen

    def popen(cmd, **kwargs):
        spec_path = Path(cmd[-1])
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        if spec["name"] == "consumer":
            spec["files"] = [str(tmp_path / "missing.rvl")]
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
        return real_popen(cmd, **kwargs)

    monkeypatch.setattr(placement.subprocess, "Popen", popen)
    started = time.monotonic()
    rc = placement.run_placement([str(app)], str(toml), once=True)
    elapsed = time.monotonic() - started
    err = capsys.readouterr().err
    assert rc == 1
    assert "error: process consumer failed to boot: " in err, err
    assert "missing.rvl" in err and "(exit code 1)" in err, err
    assert elapsed < 30.0, elapsed
