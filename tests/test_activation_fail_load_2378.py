"""Python tier: a `fail` the activation reached fails the bare `load` (issue
#2378), and the `import runtime` refusal's documented reach (issue #2344).

#2378. cordis lands a component whose activation raised as a FAILED fiber with
the error recorded. The emitted lifecycle driver settled the `load` and went on,
so the error surfaced only when a provided key was called, and a test that only
loaded (or loaded and unloaded) passed. go, rust, java and ts fail the `load`
step itself, naming the component and the message (`load E: <message>`).

Only the error a `fail` raises counts. A host body that raises on purpose
still loads quietly, because tests/test_activation_failure_1895.py and
tests/test_lifecycle_refused_open_1859.py load such a component and assert what
it left behind.

#2344. The refusal of `import runtime` in a user `@py` body is a static check
on import statements. It is not a seal on the module object.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from revl.compiler import compile_source
from revl.errors import RevlError

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _load_by_path import load_by_path  # noqa: E402

needs_cordis = pytest.mark.skipif(
    importlib.util.find_spec("cordis") is None,
    reason="`revl test --backend py` needs the cordis-py runtime; install it "
           "with `sh backends/python/setup.sh` and run under its venv",
)

_SERVICE = "service Probe { fn ok() -> Int }\n"

_FAILING = _SERVICE + """
component E provides probe: Probe {
  fail "activation refused on purpose"
  provide probe { fn ok() = 1 }
}

lifecycle test "a failing activation fails the load" {
  load E
  unload E
}
"""

_NESTED = _SERVICE + """
component E provides probe: Probe {
  config { n: Int = 1 }
  if (config.n == 1) {
    fail "nested activation refusal"
  }
  provide probe { fn ok() = 1 }
}

lifecycle test "a nested fail fails the load" {
  load E
}
"""

#: control: the activation holds a `fail` the run does not reach.
_NOT_AT_LOAD = _SERVICE + """
component G provides probe: Probe {
  config { n: Int = 0 }
  if (config.n == 1) {
    fail "never reached"
  }
  provide probe { fn ok() = 1 }
}

lifecycle test "an unreached fail loads" {
  load G
  unload G
}
"""

#: control (issue #1895): a host body that raises at activation still loads.
_HOST_RAISE = _SERVICE + """
type BoxHandle = Opaque
extern acquire fn box_open() -> BoxHandle undo box_close(result)
  = @py { from no_such_module_xyz import thing; return 1 }
extern pure fn box_close(h: BoxHandle) -> Unit = @py { return None }
component B provides probe: Probe {
  let h = effect box_open() undo box_close(h)
  provide probe { fn ok() = 1 }
}
lifecycle test "a host body that raises loads quietly" {
  load B
}
"""


def _run_py(source: str, tmp_path: Path) -> str:
    path = tmp_path / "t.rvl"
    path.write_text(source, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_ROOT / "src"), env.get("PYTHONPATH", "")])
    result = subprocess.run(
        [sys.executable, "-P", "-m", "revl", "test", str(path), "--backend", "py"],
        cwd=_ROOT, env=env, capture_output=True, text=True, timeout=300)
    return result.stdout + result.stderr


def _emit(source: str) -> str:
    emit = load_by_path("emit_py_2378", _ROOT / "backends" / "python" / "emit.py")
    return emit.emit(compile_source(source, "t.rvl"))


def test_a_fail_step_raises_the_marked_error_and_each_load_is_checked():
    text = _emit(_FAILING)
    assert "raise _revl_fail_error('activation refused on purpose')" in text
    assert "_revl_load_failed(_revl_fibers['E'], 'E'," in text
    assert "fail_error as _revl_fail_error" in text


@needs_cordis
def test_a_failing_activation_fails_the_bare_load(tmp_path):
    out = _run_py(_FAILING, tmp_path)
    assert "0 of 1 test(s) passed" in out, out
    assert ("lifecycle test 'a failing activation fails the load': "
            "load E: activation refused on purpose") in out, out


@needs_cordis
def test_a_nested_activation_fail_fails_the_bare_load(tmp_path):
    out = _run_py(_NESTED, tmp_path)
    assert "load E: nested activation refusal" in out, out


@needs_cordis
def test_an_unreached_activation_fail_still_loads(tmp_path):
    out = _run_py(_NOT_AT_LOAD, tmp_path)
    assert "1 test(s) passed" in out, out


@needs_cordis
def test_a_host_body_that_raises_at_activation_still_loads_quietly(tmp_path):
    out = _run_py(_HOST_RAISE, tmp_path)
    assert "1 test(s) passed" in out, out


#: the runtime's own refusal is a plain RuntimeError too ("refused to open
#: boom://..."), and this component also holds a `fail` that is never reached.
#: The load must stay quiet: the error is not a `fail`.
_REFUSED_OPEN_WITH_UNREACHED_FAIL = """
service S { fn ping() -> Int }
component Db provides s: S {
  config { url: Str, strict: Bool = false }
  let p = effect Pool.open(config.url, 2) undo p.close()
  if (config.strict) {
    fail "strict mode refuses"
  }
  provide s { fn ping() = 1 }
}

lifecycle test "a refused open is not a fail" {
  load Db with { url: "boom://nope" }
  unload Db
  assert no_residue
}
"""


@needs_cordis
def test_a_runtime_refusal_in_a_component_that_also_holds_a_fail_still_loads(tmp_path):
    out = _run_py(_REFUSED_OPEN_WITH_UNREACHED_FAIL, tmp_path)
    assert "1 test(s) passed" in out, out
    assert "load Db" not in out, out


#: a dependent of a dependency whose activation fails: cordis leaves the
#: dependent PENDING with no error recorded, so only the failing component's
#: `load` fails and the message names it, never the dependent.
_DEPENDENT = """
service Base { fn one() -> Int }
service Top { fn two() -> Int }
component A provides base: Base {
  fail "dependency refused"
  provide base { fn one() = 1 }
}
component B requires base: Base provides top: Top {
  provide top { fn two() = base.one() }
}

lifecycle test "dependent first" {
  load B
  load A
}
"""


@needs_cordis
def test_a_dependent_never_inherits_its_dependencys_failure(tmp_path):
    out = _run_py(_DEPENDENT, tmp_path)
    assert "load A: dependency refused" in out, out
    assert "load B" not in out, out


_IMPORTS_RUNTIME = """
extern pure fn peek() -> Int = @py { import runtime; return 1 }
fn main() -> Int { return peek() }
"""

_REACHES_RUNTIME = """
extern pure fn reached() -> Bool = @py {
    import sys
    return "runtime" in sys.modules
}
test "a host body sees the runtime module object" {
  assert reached()
}
"""


def test_import_runtime_is_refused_in_a_user_host_body():
    with pytest.raises(RevlError) as excinfo:
        compile_source(_IMPORTS_RUNTIME, "t.rvl")
    assert "imports backend module `runtime`" in str(excinfo.value)


@needs_cordis
def test_the_runtime_module_object_stays_reachable_through_sys_modules(tmp_path):
    """Pins the DOCUMENTED #2344 limit (docs/threat-model.md, non-goal 1): the
    refusal is of the import statement; the module object is reachable.

    If that limit is ever closed (host bodies isolated from the runtime module),
    this test is meant to be INVERTED, and the threat-model paragraph rewritten
    with it."""
    out = _run_py(_REACHES_RUNTIME, tmp_path)
    assert "1 test(s) passed" in out, out


def test_the_threat_model_states_the_reach_of_the_import_refusal():
    text = " ".join((_ROOT / "docs" / "threat-model.md").read_text(
        encoding="utf-8").split()).lower()
    assert "the import statement is refused, the module object is reachable" in text
    assert "resolved_config" in text
