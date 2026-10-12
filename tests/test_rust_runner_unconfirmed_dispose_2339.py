"""Issue #2339: the rust placement runner does not call an unconfirmed dispose a
clean teardown.

`src/revl/placement.py` reads `DOWN` as the runner's proof that its LIFO unwind
finished. The rust runner discarded `dispose()`'s result and printed `DOWN`
regardless, and had no bound at all. Now a dispose that fails, or that does not
settle inside the bound (`REVL_TEARDOWN_GRACE` seconds, default 5), ends the
process with one scrubbed FATAL line on stderr, no residue verdict, no `DOWN`,
and exit 1. This drives the real runner binary (cargo + cordis-rs) in a private
CARGO_TARGET_DIR outside the tree.
"""

from __future__ import annotations

import json
import os
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

_RUST_REASON = rust_runtime_reason()
pytestmark = pytest.mark.skipif(
    _RUST_REASON is not None,
    reason=f"needs a resolvable cordis-rs toolchain: {_RUST_REASON}")

# The inverse never returns: the runner's bounded teardown has to give up.
_STUCK_DOC = '''
service Vault { fn show(user: Str) -> Str }

extern pure fn mark(what: Str) -> Str = @rs {
	if what == "INVERSE-RAN" {
		println!("MARK STUCK");
		loop { std::thread::sleep(std::time::Duration::from_secs(3600)); }
	}
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

_SPEC = {
    "name": "vault", "backend": "rust", "components": ["holder"], "config": {},
    "provides": ["vault"], "proxies": {}, "probe": [], "once": True,
}


@pytest.fixture(scope="module")
def binary():
    saved = os.environ.get("CARGO_TARGET_DIR")
    # An already-set CARGO_TARGET_DIR is the caller's to keep (and reuse).
    target = None if saved else Path(tempfile.mkdtemp(prefix="revl_2339_target_"))
    if target is not None:
        os.environ["CARGO_TARGET_DIR"] = str(target)
    work = Path(tempfile.mkdtemp(prefix="revl_2339_work_"))
    try:
        yield placement._build_rust(compile_source(_STUCK_DOC), work)
    finally:
        if target is not None:
            os.environ.pop("CARGO_TARGET_DIR", None)
            shutil.rmtree(target, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


def _run(binary: str, tmp_path: Path, once: bool, grace: str | None):
    spec = tmp_path / "stuck.json"
    spec.write_text(json.dumps({**_SPEC, "once": once}))
    env = {k: v for k, v in os.environ.items() if k != "REVL_TEARDOWN_GRACE"}
    if grace is not None:
        env["REVL_TEARDOWN_GRACE"] = grace
    started = time.monotonic()
    done = subprocess.run([binary, str(spec)], capture_output=True, text=True,
                          timeout=60, stdin=subprocess.DEVNULL, env=env)
    return done, time.monotonic() - started


@pytest.mark.parametrize("once", [False, True], ids=["held", "once"])
def test_a_dispose_that_does_not_settle_is_not_a_clean_teardown(binary, tmp_path, once):
    done, elapsed = _run(binary, tmp_path, once, "1")
    both = done.stdout + done.stderr
    assert "MARK STUCK" in both, both
    assert "] DOWN" not in done.stdout, done.stdout
    assert "NO-RESIDUE" not in done.stdout and "RESIDUE-LEFT" not in done.stdout, done.stdout
    fatal = [line for line in done.stderr.splitlines() if "] FATAL " in line]
    assert len(fatal) == 1 and "holder" in fatal[0], done.stderr
    assert done.returncode == 1, both


def test_the_teardown_bound_follows_revl_teardown_grace(binary, tmp_path):
    done, elapsed = _run(binary, tmp_path, False, "1")
    assert done.returncode == 1, done.stdout + done.stderr
    assert elapsed < 4.0, elapsed
