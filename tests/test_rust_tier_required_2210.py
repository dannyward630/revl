"""A rust test that probes for cargo or cordis-rs by hand fails when rust is required.

Issue #2210. The go tier got this in #2264: `REVL_REQUIRE_TIERS` made an absent
toolchain a failure only for a test that goes through a `revl.test` runner, and
most go tests probe by hand. The rust tests do the same (`shutil.which("cargo")`
in a `skipif`, `rust_runtime_reason()` at module level), so a CI job that lost
cargo, or whose cordis-rs would not resolve from crates.io, skipped them and went
green. The repository-root `conftest.py` now turns that skip into a failure when
the session requires rust and either cargo is off PATH or the skip says cordis-rs
did not resolve.

These tests run real rust test files in a child pytest, once with cargo stripped
from PATH and the tier required, once without it required, and once with cargo
present and a skip that names a cordis-rs resolution failure.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

NODES = (
    # module-level `skipif` on rust_runtime_reason()
    "tests/test_component_name_2200.py::test_a_known_component_still_boots",
    # `skipif(shutil.which("cargo") is None)` on a marker
    "tests/test_host_map_journal_2009.py",
)


def _path_without_cargo() -> str:
    keep = [d for d in os.environ.get("PATH", "").split(os.pathsep)
            if d and not (Path(d) / "cargo").exists()]
    return os.pathsep.join(keep)


def _run(args: list[str], require: str | None, path: str | None = None,
         cwd: Path = ROOT) -> str:
    env = {**os.environ, "PATH": path if path is not None else os.environ.get("PATH", "")}
    env.pop("REVL_REQUIRE_TIERS", None)
    if require is not None:
        env["REVL_REQUIRE_TIERS"] = require
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), str(ROOT)] + [p for p in [env.get("PYTHONPATH", "")] if p])
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
    return result.stdout + result.stderr


@pytest.mark.parametrize("node", NODES)
def test_a_hand_probed_rust_test_fails_when_rust_is_required_and_cargo_is_absent(node):
    no_cargo = _path_without_cargo()
    unrequired = _run([node], "py", no_cargo)
    assert re.search(r"\bskipped\b", unrequired), unrequired
    assert not re.search(r"\b\d+ (failed|error)", unrequired), unrequired

    required = _run([node], "py,rust", no_cargo)
    # a skip raised in setup (a `skipif` marker) reports as an error, one raised
    # in the test body as a failure; both are red
    assert re.search(r"\b\d+ (failed|error)", required), required
    assert "the rust tier is REQUIRED here" in required, required


def test_a_cordis_rs_resolution_skip_fails_when_rust_is_required_and_cargo_is_present(
        tmp_path):
    """cargo is on PATH; only the skip reason says cordis-rs did not resolve."""
    probe = tmp_path / "test_probe_2210.py"
    probe.write_text(textwrap.dedent('''
        import shutil
        import pytest

        def test_resolves():
            assert shutil.which("cargo") is not None  # the probe the root conftest reads
            pytest.skip("needs a resolvable cordis-rs toolchain: "
                        "cargo could not resolve cordis-rs: no matching package")

        def test_the_realm_conformance_spelling():
            assert shutil.which("cargo") is not None
            pytest.skip("cordis-rs: not in the local cargo registry and "
                        "index.crates.io is unreachable")

        def test_other_skip_is_left_alone():
            pytest.skip("node not installed")

        def test_a_by_design_cordis_rs_skip_is_left_alone():
            assert shutil.which("cargo") is not None
            pytest.skip("cordis-rs: the crate did not build offline (cold ~/.cargo?)")
    '''), encoding="utf-8")
    path = os.environ.get("PATH", "")
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "cargo").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (fake / "cargo").chmod(0o755)
    path = os.pathsep.join([str(fake), path])
    args = ["-p", "conftest", "--rootdir", str(tmp_path), str(probe)]

    unrequired = _run(args, "py", path, cwd=tmp_path)
    assert "4 skipped" in unrequired, unrequired

    required = _run(args, "py,rust", path, cwd=tmp_path)
    assert "2 failed, 2 skipped" in required, required
    assert "the rust tier is REQUIRED here" in required, required
    assert "does not resolve" in required and "cargo is on PATH" in required, required
