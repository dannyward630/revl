"""issue #2263: a lifecycle `load C` keeps the declared config defaults.

The go lifecycle renderer built `CConfig{...}` from only the fields the `load`
step named, so every unnamed field read as Go's zero value instead of the
default written in `config { ... }`. py and ts already loaded with the
defaults. The fix fills every unnamed field from `DefaultCConfig()` (and
passes `DefaultCConfig()` itself when the step names none), in one expression
so a named field's value still sees every test binding.

Each case runs as a real `revl test` on go, py and ts (toolchain-gated, skip
with a reason). Two emit-only checks pin the go shape without a toolchain.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from revl import compile_files  # noqa: E402
from backends.go import emit as go_emit  # noqa: E402

REPRO = """\
service Base { fn get() -> Int }
component C provides base: Base {
  config { start: Int = 40 }
  provide base { fn get() = config.start }
}
lifecycle test "load uses the config default" {
  load C
  let v = call base.get()
  assert v == 40
  unload C
}
"""

# One of two fields named: `step` keeps its default 2, so 50 - 2.
PARTIAL = """\
service Base { fn get() -> Int }
component C provides base: Base {
  config { start: Int = 40, step: Int = 2 }
  provide base { fn get() = config.start - config.step }
}
lifecycle test "load keeps the unnamed field default" {
  load C with { start: 50 }
  let v = call base.get()
  assert v == 48
  unload C
}
"""

# No config at all on a two-field component: both defaults, 40 - 2.
NO_CONFIG = """\
service Base { fn get() -> Int }
component C provides base: Base {
  config { start: Int = 40, step: Int = 2 }
  provide base { fn get() = config.start - config.step }
}
lifecycle test "load with no config keeps every default" {
  load C
  let v = call base.get()
  assert v == 38
  unload C
}
"""

# A named field read from a test binding called `_cfg`: the go load must not
# introduce a local that shadows it. `step` keeps its default, so 7 - 2.
BINDING = """\
service Base { fn get() -> Int }
service Src { fn seed() -> Int }
component S provides src: Src {
  provide src { fn seed() = 7 }
}
component C provides base: Base {
  config { start: Int = 40, step: Int = 2 }
  provide base { fn get() = config.start - config.step }
}
lifecycle test "a named field reads a test binding" {
  load S
  let _cfg = call src.seed()
  load C with { start: _cfg }
  let v = call base.get()
  assert v == 5
  unload C
  unload S
}
"""

CASES = {"repro": REPRO, "partial": PARTIAL, "no_config": NO_CONFIG, "binding": BINDING}


def _skip_reason(backend: str) -> str | None:
    if backend == "go":
        return None if shutil.which("go") else "go not installed"
    if backend == "ts":
        vitest = ROOT / "backends" / "typescript" / "node_modules" / ".bin" / "vitest"
        return None if vitest.exists() else "vitest not installed in backends/typescript"
    try:
        import cordis  # noqa: F401, PLC0415
    except ImportError:
        return "cordis-py not installed"
    return None


def _revl_test(backend: str, path: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-m", "revl", "test", "--backend", backend, str(path)],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)


@pytest.mark.parametrize("backend", ["go", "py", "ts"])
@pytest.mark.parametrize("case", sorted(CASES))
def test_lifecycle_load_keeps_config_defaults(case, backend, tmp_path):
    reason = _skip_reason(backend)
    if reason:
        pytest.skip(reason)
    src = tmp_path / f"{case}.rvl"
    src.write_text(CASES[case], encoding="utf-8")
    res = _revl_test(backend, src)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert f"[{backend}] pass:" in res.stdout, out


def test_go_lifecycle_load_starts_from_defaults(tmp_path):
    src = tmp_path / "partial.rvl"
    src.write_text(PARTIAL, encoding="utf-8")
    go = go_emit.emit(compile_files([str(src)]), "probe")
    assert "LoadC(root, CConfig{Start: 50, Step: DefaultCConfig().Step})" in go


def test_go_lifecycle_load_without_config_uses_defaults(tmp_path):
    src = tmp_path / "no_config.rvl"
    src.write_text(NO_CONFIG, encoding="utf-8")
    go = go_emit.emit(compile_files([str(src)]), "probe")
    assert "LoadC(root, DefaultCConfig())" in go
