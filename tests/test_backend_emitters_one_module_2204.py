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

import importlib.machinery
import sys
import types
from pathlib import Path

import pytest

from _backend_import import backend_emitter
from revl import bundle, placement
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
