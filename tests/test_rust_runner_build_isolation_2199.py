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
import time
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
    # every staged crate builds against the one resolved lock, so a new key
    # neither re-resolves from the index nor drifts to other versions
    key = Path(outcome).name.rsplit("_", 1)[1]
    staged_lock = target_dir / "revl-runner-crates" / key / "Cargo.lock"
    assert staged_lock.read_bytes() == (target_dir / "revl-runner-lock" / "Cargo.lock").read_bytes()
    assert Path(again).stat().st_mtime_ns == stamp, \
        "rebuilding identical inputs relinked the binary"


# ---------------------------------------------------------------- go runner
#
# The go half of #2199: `_build_go` wrote emitted/gen.go and bridge_gen.go
# into the tree (gitignored, so `--ignored` is what sees them) and built every
# composition into the one backends/go/placement_runner/revl_placement_runner.

GO_RUNNER_DIR = "backends/go/placement_runner"
needs_go = pytest.mark.skipif(shutil.which("go") is None, reason="go not installed")


def _status_ignored(subdir: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain", "--ignored", "--", subdir],
        capture_output=True, text=True, check=True).stdout


@pytest.fixture
def go_stage(tmp_path, monkeypatch):
    """A private staging root outside the tree. GOCACHE is the caller's (the
    lane sets a private one); the stage is removed with tmp_path."""
    stage = tmp_path / "go_stage"
    monkeypatch.setenv("REVL_GO_RUNNER_STAGE", str(stage))
    return stage


@needs_go
def test_the_go_build_never_writes_the_source_tree(go_stage, tmp_path, monkeypatch):
    real_go = shutil.which("go")
    record = tmp_path / "status_during_go_build.txt"
    shim = tmp_path / "bin"
    shim.mkdir()
    wrapper = shim / "go"
    wrapper.write_text(
        "#!/bin/sh\n"
        f"git -C '{ROOT}' status --porcelain --ignored -- '{GO_RUNNER_DIR}' >> '{record}'\n"
        f"exec '{real_go}' \"$@\"\n", encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{shim}{os.pathsep}{os.environ['PATH']}")

    before = _status_ignored(GO_RUNNER_DIR)
    work = tmp_path / "work"
    work.mkdir()
    binary = _placement._build_go(_ir("user_cache.rvl"), work)

    assert record.exists(), "the go wrapper was never invoked"
    during = record.read_text(encoding="utf-8")
    new_lines = set(during.splitlines()) - set(before.splitlines())
    assert not new_lines, (
        "the go runner's source dir was written while go ran:\n" + "\n".join(sorted(new_lines)))
    assert _status_ignored(GO_RUNNER_DIR) == before, "the go build left the tree changed"
    assert Path(binary).exists(), binary
    assert Path(binary).resolve().is_relative_to(go_stage.resolve())


@needs_go
def test_different_go_compositions_get_different_binaries(go_stage, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    cache = _placement._build_go(_ir("user_cache.rvl"), work)
    counter = _placement._build_go(_ir("counter_pair.rvl"), work)
    assert cache != counter, "two go compositions were built into one shared binary"
    assert Path(cache).exists() and Path(counter).exists()

    stamp = Path(cache).stat().st_mtime_ns
    again = _placement._build_go(_ir("user_cache.rvl"), work)
    assert again == cache, "identical inputs must reuse the content-hashed binary"
    assert Path(again).stat().st_mtime_ns == stamp, \
        "rebuilding identical inputs relinked the binary"


# ------------------------------------------------------------------ pruning


def test_pruning_keeps_the_recent_the_current_and_the_young(tmp_path):
    root = tmp_path / "stage"
    old = time.time() - 3600
    for i in range(12):
        key = root / f"k{i:02d}"
        key.mkdir(parents=True)
        (tmp_path / f"artifact_k{i:02d}").write_text("x")
        os.utime(key, (old + i, old + i))  # k11 is the most recent
    young = root / "young"
    young.mkdir()
    os.utime(root / "k00", (old - 10, old - 10))  # oldest, but the current build

    removed = _placement._prune_staged(
        root, "k00", lambda key: [tmp_path / f"artifact_{key}"], keep=4, min_age=600)

    left = sorted(p.name for p in root.iterdir())
    # the 4 most recent are young + k11..k09; k00 is current; k01..k08 go
    assert left == ["k00", "k09", "k10", "k11", "young"], left
    assert sorted(removed) == [f"k{i:02d}" for i in range(1, 9)]
    assert not (tmp_path / "artifact_k05").exists()
    assert (tmp_path / "artifact_k10").exists()


def test_a_reused_key_is_touched_so_it_survives_pruning(tmp_path):
    root = tmp_path / "stage"
    key = root / "reused"
    key.mkdir(parents=True)
    os.utime(key, (0, 0))
    _placement._stage_tree(key, {"a.txt": b"same"})
    assert time.time() - key.stat().st_mtime < 60
