"""Issue #2341: a boot step of the rust placement runner that does not activate is
a `fatal_boot`, not a panic.

`backends/rust/placement_runner/src/main.rs` waited on four activations with
`fiber.try_wait().unwrap()` (a proxy, a served key, a probe) and the component
arm handled its own. `try_wait` returns `Err` for a FAILED fiber and also for a
PENDING one (a dependency never provided), so a probe or a served key whose
provider is missing panicked the runner: a raw panic line, a Rust backtrace
hint, exit 101, and the proxies and components already booted left undisposed.
The go runner takes the same cases through `fatalBoot` (#2254): one scrubbed
FATAL line, the booted fibers disposed in reverse order, exit 1.

Also covered (issue #2356): the boot-failure dispose goes through the same
bounded teardown as the normal one, so a stuck inverse cannot hang a failed
boot.

The source assertion runs everywhere; the live tests drive the real runner
binary (cargo + cordis-rs) in a private CARGO_TARGET_DIR outside the tree.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl import placement  # noqa: E402
from revl.compiler import compile_source  # noqa: E402
from revl.run_rust import rust_runtime_reason  # noqa: E402

_MAIN_RS = ROOT / "backends" / "rust" / "placement_runner" / "src" / "main.rs"

_RUST_REASON = rust_runtime_reason()
needs_cordis_rs = pytest.mark.skipif(
    _RUST_REASON is not None,
    reason=f"needs a resolvable cordis-rs toolchain: {_RUST_REASON}")


def test_no_boot_activation_is_unwrapped():
    """Every activation wait in the runner reports through `fatal_boot`."""
    source = _MAIN_RS.read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("//"))
    unwrapped = re.findall(r"try_wait\(\)\s*\.\s*(?:unwrap|expect)\s*\(", code)
    assert not unwrapped, f"{len(unwrapped)} activation wait(s) still panic on Err"


_DOC = '''
service Vault { fn show(user: Str) -> Str }

extern pure fn mark(what: Str) -> Str = @rs {
	println!("MARK {}", what);
	what
}

component Holder provides vault: Vault {
  let slot = effect mark("applied") undo mark("INVERSE-RAN")

  provide vault {
    fn show(user) { return "shown " + user }
  }
}
'''

# The inverse never returns: the boot-failure dispose has to give up.
_STUCK_DOC = _DOC.replace(
    'println!("MARK {}", what);\n\twhat',
    'if what == "INVERSE-RAN" {\n\t\tprintln!("MARK STUCK");\n'
    '\t\tloop { std::thread::sleep(std::time::Duration::from_secs(3600)); }\n\t}\n'
    '\tprintln!("MARK {}", what);\n\twhat')

# A correct inverse that takes longer than the old 5 s default (issue #2356).
_SLOW_DOC = _DOC.replace(
    'println!("MARK {}", what);\n\twhat',
    'if what == "INVERSE-RAN" { std::thread::sleep(std::time::Duration::from_secs(6)); }\n'
    '\tprintln!("MARK {}", what);\n\twhat')

_BASE_SPEC = {
    "name": "vault", "backend": "rust", "components": ["holder"], "config": {},
    "provides": ["vault"], "proxies": {}, "probe": [],
}


def _build(doc: str, tag: str):
    saved = os.environ.get("CARGO_TARGET_DIR")
    target = None if saved else Path(tempfile.mkdtemp(prefix=f"revl_2341_{tag}_"))
    if target is not None:
        os.environ["CARGO_TARGET_DIR"] = str(target)
    work = Path(tempfile.mkdtemp(prefix="revl_2341_work_"))
    try:
        return placement._build_rust(compile_source(doc), work), target, work
    finally:
        if target is not None:
            os.environ.pop("CARGO_TARGET_DIR", None)
        shutil.rmtree(work, ignore_errors=True)


@pytest.fixture(scope="module")
def binaries():
    built = {}
    targets = []
    try:
        for tag, doc in (("ok", _DOC), ("stuck", _STUCK_DOC), ("slow", _SLOW_DOC)):
            binary, target, _ = _build(doc, tag)
            built[tag] = binary
            if target is not None:
                targets.append(target)
        yield built
    finally:
        for target in targets:
            shutil.rmtree(target, ignore_errors=True)


def _spec_for(kind: str, tmp_path: Path, once: bool) -> dict:
    spec = {**_BASE_SPEC, "once": once}
    if kind == "probe":
        # `ghost` is provided by nobody: the probe plugin stays Pending
        spec["probe"] = [{"key": "ghost", "method": "show", "args": []}]
    else:
        spec["serve"] = {"socket": str(tmp_path / "serve.sock"), "keys": ["ghost"]}
    return spec


def _run(binary: str, tmp_path: Path, spec: dict, env_extra=None, timeout=60):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    env = {k: v for k, v in os.environ.items() if k != "REVL_TEARDOWN_GRACE"}
    env.update(env_extra or {})
    started = time.monotonic()
    try:
        done = subprocess.run([binary, str(path)], capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL, env=env)
    except subprocess.TimeoutExpired as hung:
        pytest.fail(f"the runner did not exit within {timeout}s: {hung.stdout!r}")
    return done, time.monotonic() - started


@needs_cordis_rs
@pytest.mark.parametrize("once", [False, True], ids=["held", "once"])
@pytest.mark.parametrize("kind", ["probe", "serve"])
def test_a_boot_step_that_does_not_activate_is_a_fatal_boot(binaries, tmp_path, kind, once):
    done, _ = _run(binaries["ok"], tmp_path, _spec_for(kind, tmp_path, once))
    both = done.stdout + done.stderr
    assert "panicked" not in both and "FATAL panic" not in both, both
    assert done.returncode == 1, (done.returncode, both)
    fatal = [line for line in done.stderr.splitlines() if "] FATAL " in line]
    assert len(fatal) == 1 and "boot failed loading" in fatal[0], done.stderr
    # no claim that the composition came up or tore down cleanly
    for claim in ("UP", "NO-RESIDUE", "RESIDUE-LEFT", "DOWN"):
        assert f"] {claim}" not in done.stdout, done.stdout
    # what had booted was disposed, its inverse run, before the exit
    assert "MARK applied" in both and "MARK INVERSE-RAN" in both, both
    assert "| holder" in done.stdout and "dispose" in done.stdout, done.stdout


@needs_cordis_rs
def test_the_boot_failure_dispose_is_bounded(binaries, tmp_path):
    """A stuck inverse must not hang a failed boot (#2356): `fatal_boot` gives
    its disposes the same bound as the normal teardown."""
    done, elapsed = _run(binaries["stuck"], tmp_path, _spec_for("probe", tmp_path, False),
                         {"REVL_TEARDOWN_GRACE": "2"}, timeout=30)
    both = done.stdout + done.stderr
    assert "MARK STUCK" in both, both
    assert done.returncode == 1, (done.returncode, both)
    fatal = [line for line in done.stderr.splitlines() if "FATAL teardown incomplete" in line]
    assert len(fatal) == 1 and "holder" in fatal[0], done.stderr
    assert "] DOWN" not in done.stdout, done.stdout
    assert elapsed < 10.0, elapsed


@needs_cordis_rs
def test_a_slow_correct_inverse_ends_in_down_with_the_default_bound(binaries, tmp_path):
    """With the variable unset the runner waits as long as the conductor does
    (30 s less a margin), so a 6 s inverse is a clean teardown (#2356)."""
    done, elapsed = _run(binaries["slow"], tmp_path, {**_BASE_SPEC, "once": True})
    both = done.stdout + done.stderr
    assert done.returncode == 0, (done.returncode, both)
    assert "MARK INVERSE-RAN" in both and "] DOWN" in done.stdout, both
    assert "FATAL" not in done.stderr, done.stderr
    assert elapsed >= 5.5, elapsed


@needs_cordis_rs
def test_the_runner_reports_before_the_conductor_grace_expires(binaries, tmp_path):
    """With the variable set to N the runner gives up before N seconds, so its
    FATAL line is out before the conductor's kill at N can swallow it (#2356)."""
    done, elapsed = _run(binaries["stuck"], tmp_path, {**_BASE_SPEC, "once": False},
                         {"REVL_TEARDOWN_GRACE": "6"}, timeout=30)
    assert done.returncode == 1, (done.returncode, done.stdout + done.stderr)
    assert len([ln for ln in done.stderr.splitlines()
                if "FATAL teardown incomplete" in ln]) == 1, done.stderr
    # the lower limit proves the bound (4 s) was waited; the upper one only
    # guards against a hang, with room for a loaded runner
    assert 3.0 <= elapsed < 10.0, elapsed
