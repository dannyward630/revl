"""Issue #2199: building the rust placement runner is isolated per composition.

Before the fix `_build_rust` wrote each composition's emitted components module
over the COMMITTED `backends/rust/placement_runner/src/components.rs`, ran
cargo, and put the golden back afterwards; every composition built into the one
`target/debug/revl_placement_runner`. Two concurrent builds raced on both, and a
run killed mid-build left the checkout dirty.

These drive the real build (cargo + cordis-rs) into a private CARGO_TARGET_DIR
outside the tree:

- the tree is unchanged not only after the build but WHILE cargo runs (a cargo
  wrapper on PATH records `git status` at the moment cargo is invoked);
- two different compositions get two different binaries, and building the same
  composition again reuses its binary untouched.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl import placement as _placement  # noqa: E402
from revl.compiler import compile_source  # noqa: E402
from revl.run_rust import rust_runtime_reason  # noqa: E402

_RUST_REASON = rust_runtime_reason()
needs_cordis_rs = pytest.mark.skipif(
    _RUST_REASON is not None,
    reason=f"needs a resolvable cordis-rs toolchain: {_RUST_REASON}")

RUNNER_DIR = "backends/rust/placement_runner"


def _ir(example: str) -> dict:
    path = ROOT / "examples" / example
    return compile_source(path.read_text(encoding="utf-8"), path.name)


def _status() -> str:
    return subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                          capture_output=True, text=True, check=True).stdout


@pytest.fixture(scope="module")
def target_dir():
    """One private cargo target dir for the module (deps compile once), outside
    the tree, removed afterwards."""
    path = Path(tempfile.mkdtemp(prefix="revl_2199_target_"))
    saved = os.environ.get("CARGO_TARGET_DIR")
    os.environ["CARGO_TARGET_DIR"] = str(path)
    try:
        yield path
    finally:
        if saved is None:
            os.environ.pop("CARGO_TARGET_DIR", None)
        else:
            os.environ["CARGO_TARGET_DIR"] = saved
        shutil.rmtree(path, ignore_errors=True)


@needs_cordis_rs
def test_the_build_never_writes_the_source_tree(target_dir, tmp_path, monkeypatch):
    real_cargo = shutil.which("cargo")
    record = tmp_path / "status_during_build.txt"
    shim = tmp_path / "bin"
    shim.mkdir()
    wrapper = shim / "cargo"
    wrapper.write_text(
        "#!/bin/sh\n"
        f"git -C '{ROOT}' status --porcelain >> '{record}'\n"
        f"exec '{real_cargo}' \"$@\"\n", encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{shim}{os.pathsep}{os.environ['PATH']}")

    before = _status()
    work = tmp_path / "work"
    work.mkdir()
    binary = _placement._build_rust(_ir("outcome.rvl"), work)

    assert record.exists(), "the cargo wrapper was never invoked"
    during = record.read_text(encoding="utf-8")
    assert RUNNER_DIR not in during, (
        "the source tree was modified while cargo ran:\n" + during)
    assert Path(binary).exists(), binary
    assert _status() == before, "the build left the tree changed"
    assert not str(Path(binary).resolve()).startswith(str((ROOT / RUNNER_DIR).resolve())), \
        "with CARGO_TARGET_DIR set the binary must land there, not in the tree"


@needs_cordis_rs
def test_different_compositions_get_different_binaries(target_dir, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    outcome = _placement._build_rust(_ir("outcome.rvl"), work)
    counter = _placement._build_rust(_ir("counter_pair.rvl"), work)
    assert outcome != counter, "two compositions were built into one shared binary"
    assert Path(outcome).exists() and Path(counter).exists()

    stamp = Path(outcome).stat().st_mtime_ns
    again = _placement._build_rust(_ir("outcome.rvl"), work)
    assert again == outcome, "identical inputs must reuse the content-hashed binary"
    assert Path(again).stat().st_mtime_ns == stamp, \
        "rebuilding identical inputs relinked the binary"
