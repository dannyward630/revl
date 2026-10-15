"""Two go-tier component defects, each built and run with the real toolchain.

Issue #2464: stc-go runs a component's `Apply` on a goroutine of its own and
recovers nothing, so a provide method that panicked inside an activation
killed the process. The activation's abort path (the compensations its body
had registered) never ran. The emitted `Apply` now recovers the panic into the
error it returns, so the activation fails like a `fail` step and unwinds.

Issue #2457: a `@go` extern body asks for a package with `//revl:import <path>`.
The directive was hoisted into the import set only on the pure typed-core path;
the component renderers (the placement runner's and `emit`'s) dropped it, so an
extern could not reach `time` and a go inverse that has to wait could only spin.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl.compiler import compile_source  # noqa: E402

GO = shutil.which("go")
GO_SCENARIOS = ROOT / "backends" / "go" / "scenarios"


def _go_emit():
    spec = importlib.util.spec_from_file_location(
        "revl_go_emit_2464", ROOT / "backends" / "go" / "emit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _need_go() -> None:
    if GO is None:
        pytest.skip("go toolchain not available")


def _go_test(tmp_path: Path, package: str, src: str, driver: str = "",
             run: str = "") -> subprocess.CompletedProcess:
    """Build the emitted package in a copy of the scenarios module and run the
    named driver test (only build it when `run` is empty)."""
    module = tmp_path / "mod"
    module.mkdir()
    for name in ("go.mod", "go.sum"):
        shutil.copy(GO_SCENARIOS / name, module / name)
    pkg = module / package
    pkg.mkdir()
    (pkg / f"gen_{package}_test.go").write_text(src, encoding="utf-8")
    if driver:
        (pkg / "drive_test.go").write_text(driver, encoding="utf-8")
    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOPROXY": "off"}
    argv = [GO, "test", "-count=1", "-v", "-run", run or "^$", f"./{package}/"]
    return subprocess.run(argv, cwd=str(module), capture_output=True, text=True, env=env)


# ---- issue #2464: a panic in an activation ---------------------------------

PANIC_DOC = """
extern emission fn note(msg: Str) = @go {
	println("NOTE " + msg)
}
extern emission fn boom() -> Int = @go {
	panic("the provider gave up")
}

service Ops {
  emission fn run(region: Str) -> Int
}

component Agent provides ops: Ops {
  provide ops {
    fn run(region) {
      return emit boom()
    }
  }
}

component Caller requires ops: Ops {
  emit note("start") compensate note("undo-start")
  emit ops.run("r")
}
"""

PANIC_DRIVER = """package pan

import (
	stdctx "context"
	"testing"

	stc "github.com/0xdenny218/stc-go"
)

func TestActivationPanic(t *testing.T) {
	root := stc.New()
	if err := LoadAgent(root).Ready(stdctx.Background()); err != nil {
		t.Fatalf("boot Agent: %v", err)
	}
	err := LoadCaller(root).Ready(stdctx.Background())
	if err == nil {
		t.Fatalf("Caller activated, but its provide call panicked")
	}
	println("CALLER-FAILED " + err.Error())
	println("DRIVER-DONE")
}
"""


def test_a_panicking_provide_method_fails_the_activation_and_runs_its_abort(tmp_path):
    src = _go_emit().emit(compile_source(PANIC_DOC, "pan.rvl"), "pan")
    _need_go()
    proc = _go_test(tmp_path, "pan", src, PANIC_DRIVER, "TestActivationPanic")
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    # the process outlived the panic, which failed the activation ...
    assert "CALLER-FAILED panic: the provider gave up" in output, output
    assert "DRIVER-DONE" in output, output
    # ... and the abort path ran the compensation the body registered first
    assert output.index("NOTE start") < output.index("NOTE undo-start"), output


def test_a_wiring_only_component_keeps_the_plain_apply():
    """A component whose body only wires provide blocks runs no author code in
    `Apply`, so it emits exactly as before (the self-host go port renders that
    slice and must keep byte agreement)."""
    src = _go_emit().emit(compile_source(PANIC_DOC, "pan.rvl"), "pan")
    agent = src[src.index("func Agent() stc.Component {"):]
    agent = agent[:agent.index("\n}\n")]
    assert "Apply: func(ctx *stc.Context) (stc.Inverse, error) {" in agent
    assert "recover()" not in agent
    caller = src[src.index("func Caller() stc.Component {"):]
    caller = caller[:caller.index("\n}\n")]
    assert "(_revlApplyInv stc.Inverse, _revlApplyErr error)" in caller
    assert "recover()" in caller


# ---- issue #2457: `//revl:import` on the component renderers ---------------

NAP_EXTERN = """
extern pure fn nap(ms: Int) -> Int = @go {
	//revl:import time
	//revl:import os
	time.Sleep(time.Duration(ms) * time.Millisecond)
	_ = os.Getpid()
	return ms
}

service Napper {
  fn nap(ms: Int) -> Int
}

component Sleepy provides napper: Napper {
  provide napper {
    fn nap(ms) {
      return nap(ms)
    }
  }
}
"""

#: The same document with a lifecycle test, which keeps it on `emit`'s live
#: stc-go renderer instead of the combined one.
NAP_LIFECYCLE = NAP_EXTERN + """
lifecycle test "the extern waits with time.Sleep" {
  load Sleepy
  let got = call napper.nap(5)
  assert got == 5
  unload Sleepy
  assert no_residue
}
"""


def _import_block(src: str) -> list[str]:
    block = src[src.index("import (") + len("import ("):]
    return [line.strip() for line in block[:block.index(")")].splitlines() if line.strip()]


def test_placement_hoists_an_extern_import(tmp_path):
    ir = compile_source(NAP_EXTERN, "nap.rvl")
    gen = _go_emit().emit_placement(ir, "emitted").split("\f", 1)[0]
    imports = _import_block(gen)
    assert '"time"' in imports and '"os"' in imports, imports
    assert "//revl:import" not in gen
    _need_go()
    from revl import placement  # noqa: PLC0415

    assert Path(placement._build_go(ir, tmp_path)).exists()


@pytest.mark.parametrize("doc", ["combined", "live"])
def test_emit_hoists_an_extern_import_once(doc, tmp_path):
    source = NAP_EXTERN if doc == "combined" else NAP_LIFECYCLE
    src = _go_emit().emit(compile_source(source, "nap.rvl"), "nap")
    imports = _import_block(src)
    for path in ('"time"', '"os"'):
        assert imports.count(path) == 1, imports
    _need_go()
    run = "" if doc == "combined" else "."
    proc = _go_test(tmp_path, "nap", src, run=run)
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    if doc == "live":
        assert "--- PASS" in output, output


# ---- issue #2482: an aliased `//revl:import` on the component renderers ----

ALIAS_EXTERN = """
extern pure fn nap(ms: Int) -> Int = @go {
	//revl:import tm "time"
	//revl:import str "strings"
	tm.Sleep(tm.Duration(ms) * tm.Millisecond)
	return ms + int64(len(str.Repeat("x", 2)))
}

service Napper {
  fn nap(ms: Int) -> Int
}

component Sleepy provides napper: Napper {
  provide napper {
    fn nap(ms) {
      return nap(ms)
    }
  }
}
"""

ALIAS_LIFECYCLE = ALIAS_EXTERN + """
lifecycle test "the extern reaches time and strings through aliases" {
  load Sleepy
  let got = call napper.nap(5)
  assert got == 7
  unload Sleepy
  assert no_residue
}
"""


def test_placement_hoists_an_aliased_extern_import(tmp_path):
    ir = compile_source(ALIAS_EXTERN, "alias.rvl")
    gen = _go_emit().emit_placement(ir, "emitted").split("\f", 1)[0]
    imports = _import_block(gen)
    assert 'tm "time"' in imports and 'str "strings"' in imports, imports
    _need_go()
    from revl import placement  # noqa: PLC0415

    assert Path(placement._build_go(ir, tmp_path)).exists()


@pytest.mark.parametrize("doc", ["combined", "live"])
def test_emit_hoists_an_aliased_extern_import_once(doc, tmp_path):
    source = ALIAS_EXTERN if doc == "combined" else ALIAS_LIFECYCLE
    src = _go_emit().emit(compile_source(source, "alias.rvl"), "alias")
    imports = _import_block(src)
    for spec in ('tm "time"', 'str "strings"'):
        assert imports.count(spec) == 1, imports
    assert not any('""' in line for line in imports), imports
    _need_go()
    run = "" if doc == "combined" else "."
    proc = _go_test(tmp_path, "alias", src, run=run)
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output
    if doc == "live":
        assert "--- PASS" in output, output
