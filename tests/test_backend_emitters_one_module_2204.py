"""Issue #2204: every backend ships a top-level module named `emit`.

A bare `import emit` answers with whichever backend directory is first on
`sys.path`, so each loader in the process used to work around the name by
hand, each with its own module object and so its own `EmitError` class. The
wasm quarantine loader also left `backends/wasm` first on `sys.path` (it and
`backends/wasm/canonical.py` both inserted it and never took it out), so the
next bare `import emit` in the process got the wasm emitter.

Now one loader, `revl.placement.backend_emit_module`, binds each tier's
emitter under `revl_<tier>_emit`. Two tiers are two modules; every caller of
one tier gets the same module; and loading them leaves the bare name and
`sys.path` alone.
"""

from __future__ import annotations

import ast
import copy
import importlib.machinery
import importlib.util
import sys
import types
from pathlib import Path

import pytest

from _backend_import import backend_emitter
from revl import bundle, compile_source, gate, placement, run_java, run_wasm
from revl import test as revl_test
from revl._paths import backends_root
from revl.mcp import quarantine

ROOT = Path(__file__).resolve().parents[1]
WASM_DIR = str((ROOT / "backends" / "wasm").resolve())


def _norm(entry: str) -> str:
    try:
        return str(Path(entry).resolve())
    except OSError:
        return entry


@pytest.fixture
def clean_import_state(monkeypatch):
    """A `sys.path` without the wasm backend directory, and a sentinel under
    the bare name `emit`, both restored afterwards."""
    monkeypatch.setattr(sys, "path", [p for p in sys.path if _norm(p) != WASM_DIR])
    sentinel = types.ModuleType("emit")
    monkeypatch.setitem(sys.modules, "emit", sentinel)
    return sentinel


def test_two_backends_emitters_are_two_modules_each_shared_by_every_loader(
        clean_import_state):
    path_before = list(sys.path)
    by_tier = {}
    for tier, gate_name in (("python", "py"), ("wasm", None), ("java", "java")):
        loads = [placement.backend_emit_module(tier), bundle._emitter(tier),
                 backend_emitter(tier)]
        if gate_name is not None:
            loads.append(placement._emit_gate_module(gate_name))
        if tier == "wasm":
            canonical = quarantine._load_canonical()
            assert canonical is not None
            loads.append(canonical._emit_mod)
        first = loads[0]
        assert all(m is first for m in loads), (
            f"the {tier} emitter is loaded as {len({id(m) for m in loads})} "
            "different modules, so an `except EmitError` in one caller does "
            "not catch another caller's refusal")
        assert sys.modules[f"revl_{tier}_emit"] is first
        assert Path(first.__file__).resolve() == (backends_root() / tier / "emit.py").resolve()
        by_tier[tier] = first

    assert len({id(m) for m in by_tier.values()}) == 3
    assert by_tier["python"].EmitError is not by_tier["wasm"].EmitError
    # the bare name is nobody's: neither emitter shadowed the other under it
    assert sys.modules["emit"] is clean_import_state
    assert sys.path == path_before


def test_loading_canonical_leaves_sys_path_and_the_bare_name_alone(
        clean_import_state):
    """The issue's reproducer: after `quarantine._load_canonical()` a bare
    `import emit` resolved to `backends/wasm/emit.py`."""
    path_before = list(sys.path)

    canonical = quarantine._load_canonical()

    assert canonical is not None
    assert sys.path == path_before, (
        "loading canonical.py added to sys.path: "
        f"{[p for p in sys.path if p not in path_before]}")
    assert sys.modules["emit"] is clean_import_state
    found = importlib.machinery.PathFinder.find_spec("emit", sys.path)
    origin = _norm(found.origin) if found is not None and found.origin else None
    assert origin != str(Path(WASM_DIR) / "emit.py"), (
        f"a bare `import emit` now answers with the wasm emitter ({origin})")
    # and canonical refuses with the class every other wasm caller catches
    assert canonical.EmitError is placement.backend_emit_module("wasm").EmitError


def test_an_emitter_from_another_tree_does_not_take_the_shared_name(
        tmp_path, monkeypatch, clean_import_state):
    """A `root` that is not the default tree gets its own module name. Bound
    under `revl_wasm_emit`, it displaced the module canonical.py reuses by
    that name, and canonical then held a second `EmitError` class."""
    real = placement.backend_emit_module("wasm")
    monkeypatch.setattr(placement, "_EMIT_MODULES", dict(placement._EMIT_MODULES))
    other = tmp_path / "backends"
    (other / "wasm").mkdir(parents=True)
    (other / "wasm" / "emit.py").write_text(
        "class EmitError(ValueError):\n    pass\n\n\ndef emit(ir):\n    return {}\n",
        encoding="utf-8")

    fake = placement.backend_emit_module("wasm", root=other)
    try:
        assert fake is not real
        assert fake.__name__ != "revl_wasm_emit"
        assert sys.modules["revl_wasm_emit"] is real
        assert placement.backend_emit_module("wasm", root=other) is fake
        canonical = quarantine._load_canonical()
        assert canonical is not None
        assert canonical.EmitError is real.EmitError
    finally:
        if sys.modules.get(fake.__name__) is fake:
            sys.modules.pop(fake.__name__)
        sys.modules["revl_wasm_emit"] = real


# ---------------------------------------------------------------------------
# the loaders that were left over from the first slice
# ---------------------------------------------------------------------------

#: A document every tier but wasm refuses (a `validated` extern crossing).
REFUSED = """
type Call = { tool: Str, args: Str }
type AgentTurn = Final(Str) | ToolCalls(List[Call])

extern emission[model] validated fn complete(h: Str) -> AgentTurn = @py {
  return {"kind": "Final", "value": "x"}
}

service Counter { fn next() -> Int }

component CounterSvc provides counter: Counter {
  provide counter { fn next() = 42 }
}
"""

#: A document every tier lowers.
PLAIN = """
service Counter { fn next() -> Int }
component CounterSvc provides counter: Counter {
  provide counter { fn next() = 42 }
}
"""

#: An async function whose body a test can corrupt into a refusal.
ASYNC_FN = """
extern emission async fn aop(x: Str) -> Str = @py { return x }
  = @ts { return x }
fn caller(x: Str) -> Str {
  let a = aop(x)
  return a
}
service ARun { emission async fn go(x: Str) -> Str }
component Agent provides arun: ARun {
  provide arun { async fn go(x) = emit caller(x) }
}
"""

#: gate tier spelling -> backend directory, for the tiers that refuse REFUSED
REFUSING = (("py", "python"), ("ts", "typescript"), ("rust", "rust"),
            ("java", "java"), ("go", "go"))


def _forbid_fresh_exec(monkeypatch):
    """Fail on any `spec_from_file_location`, so a site that re-executes an
    emitter instead of reusing the cached module cannot pass. The caller warms
    the shared loader first."""
    def _boom(*args, **kwargs):
        raise AssertionError(f"an emitter was exec'd afresh: {args[:2]}")
    monkeypatch.setattr(importlib.util, "spec_from_file_location", _boom)


@pytest.mark.parametrize("tier", ["python", "typescript", "rust", "java", "go", "wasm"])
def test_test_py_emitter_is_the_shared_module(tier, monkeypatch):
    shared = placement.backend_emit_module(tier)
    _forbid_fresh_exec(monkeypatch)
    assert revl_test._emitter(tier) is shared
    assert sys.modules[f"revl_{tier}_emit"] is shared


def test_run_wasm_emitter_is_the_shared_module(monkeypatch):
    shared = placement.backend_emit_module("wasm")
    _forbid_fresh_exec(monkeypatch)
    assert run_wasm._wasm_emitter() is shared
    assert run_wasm._wasm_emitter() is run_wasm._wasm_emitter()


@pytest.mark.parametrize("tier,directory", REFUSING)
def test_gate_refusal_is_the_shared_modules_own_class(tier, directory):
    """The gate used to exec the emitter on every call, so the `EmitError` it
    caught was a class no other loader held."""
    shared = placement.backend_emit_module(directory)
    ir = compile_source(REFUSED, "agent.rvl")
    with pytest.raises(gate.TierRefusal) as caught:
        gate._emit_for_tier(ir, tier)
    assert isinstance(caught.value.__cause__, shared.EmitError)


@pytest.mark.parametrize("tier,directory", REFUSING + (("wasm", "wasm"),))
def test_gate_does_not_exec_the_emitter_again_per_call(tier, directory, monkeypatch):
    placement.backend_emit_module(directory)
    ir = compile_source(PLAIN, "plain.rvl")
    gate._emit_for_tier(ir, tier)
    _forbid_fresh_exec(monkeypatch)
    assert gate._emit_for_tier(ir, tier) == gate._emit_for_tier(ir, tier)


def _fresh_emitter(directory: str):
    path = backends_root() / directory / "emit.py"
    spec = importlib.util.spec_from_file_location(f"fresh_{directory}_emit", path)
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    return fresh


def _outcome(call):
    """What an emit did, as a comparable value: its output, or its refusal."""
    try:
        return ("ok", call())
    except gate.TierRefusal as refusal:
        return ("refused", str(refusal))
    except Exception as refusal:  # noqa: BLE001 - the fresh module's own EmitError
        return ("refused", str(refusal))


@pytest.mark.parametrize("tier,directory", REFUSING + (("wasm", "wasm"),))
def test_gate_shared_module_emits_what_a_fresh_one_does(tier, directory):
    """The gate used to take a fresh module per call. The java and go
    emitters hold module-global render state, so this alternates a refused and
    a plain program over the shared module and compares every call with a
    module that never saw the other program. State one program left behind
    would change the next one's bytes."""
    programs = {"refused": compile_source(REFUSED, "agent.rvl"),
                "plain": compile_source(PLAIN, "plain.rvl")}
    want = {name: _outcome(lambda ir=ir: _fresh_emitter(directory).emit(ir))
            for name, ir in programs.items()}
    assert want["plain"][0] == "ok"
    for name in ("refused", "plain", "refused", "plain"):
        got = _outcome(lambda ir=programs[name]: gate._emit_for_tier(ir, tier))
        assert got == want[name], f"{tier}: {name} program differs after the one before it"


def test_a_refusal_mid_function_does_not_leak_the_py_colour_into_the_next_emit():
    """`_emit_functions` set `_PY_IN_ASYNC` and `_PY_AWAIT_LOCALS` per function
    and cleared them only on the normal exit, so an `EmitError` inside an async
    function's body left them set for the next `emit` on the same module. That
    module is now shared. No program changes its bytes through the leaked flag
    today (a component body does not read it), so the state itself is what is
    asserted, with the bytes of the following emit checked as well."""
    ir = compile_source(ASYNC_FN, "a.rvl")
    bad = copy.deepcopy(ir)
    caller = next(f for f in bad["functions"] if f["name"] == "caller")
    assert caller.get("async") is True
    caller["body"][-1]["expr"] = {"kind": "bogus"}
    plain = compile_source(PLAIN, "plain.rvl")

    module = _fresh_emitter("python")
    with pytest.raises(module.EmitError, match="unsupported expression kind"):
        module.emit(bad)
    assert module._PY_IN_ASYNC is False
    assert module._PY_IN_ARROW is False
    assert module._PY_AWAIT_LOCALS == set()
    assert module.emit(plain) == _fresh_emitter("python").emit(plain)
    assert module.emit(ir) == _fresh_emitter("python").emit(ir)


def test_the_stateful_loaders_stay_fresh():
    """The java and go emitters hold module-global render state, and
    `run_java._java_emitter` and `placement._tier_emitter` hand each caller a
    fresh module of them on purpose. Sharing one would change behaviour, so
    this pins the decision: they are NOT the cached module."""
    shared = placement.backend_emit_module("java")
    first = run_java._java_emitter()
    assert first is not shared and first is not run_java._java_emitter()
    java = backends_root() / "java" / "emit.py"
    one = placement._tier_emitter("revl_java_emit", java)
    assert one is not shared
    assert one is not placement._tier_emitter("revl_java_emit", java)


#: src/revl functions that exec a module by path, and why each is not a second
#: emitter loader (or, for the three emitter ones, why it stays one).
BY_PATH_SITES = {
    ("src/revl/placement.py", "backend_emit_module"): "the one cached loader",
    ("src/revl/placement.py", "_tier_emitter"):
        "java and go build steps: module-global render state, fresh on purpose",
    ("src/revl/run_java.py", "_java_emitter"):
        "module-global render state, fresh on purpose",
    ("src/revl/_process_runner.py", "_funnel"): "loads confidential.py, not an emitter",
    ("src/revl/mcp/quarantine.py", "_load_by_path"): "loads canonical.py, not an emitter",
    ("src/revl/wal.py", "_py_replay"): "loads replay.py, not an emitter",
    ("src/revl/test.py", "_wasm_lifecycle_module"): "loads lifecycle.py, not an emitter",
}


def _by_path_sites() -> set[tuple[str, str]]:
    found = set()
    for path in sorted((ROOT / "src" / "revl").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = str(path.relative_to(ROOT))

        def walk(node, scope):
            for child in ast.iter_child_nodes(node):
                inner = scope
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    inner = child.name
                if (isinstance(child, ast.Call)
                        and getattr(child.func, "attr", getattr(child.func, "id", ""))
                        == "spec_from_file_location"):
                    found.add((rel, scope))
                walk(child, inner)

        walk(tree, "<module>")
    return found


def test_no_src_function_execs_an_emitter_by_path_except_the_recorded_ones():
    """Issue #2204: the by-path loaders under src/revl, each with its own
    module and its own `EmitError`. A new one fails here until it goes through
    `placement.backend_emit_module` or is recorded, with the reason."""
    sites = _by_path_sites()
    assert sites == set(BY_PATH_SITES), (
        f"new: {sorted(sites - set(BY_PATH_SITES))}; "
        f"gone: {sorted(set(BY_PATH_SITES) - sites)}")
