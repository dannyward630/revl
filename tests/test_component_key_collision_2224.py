"""Two component names that differ only in letter case or underscores are
refused by the checker, naming both (issue #2224).

The rust emitter snake-cases a component name (`backends/rust/emit.py::_snake`)
for its `pub fn` plugin and for the key `plugin_by_name`, `_revl_load` and the
placement spec name it by. `KVStore` and `Kvstore` both become `kvstore`, so a
program declaring the two failed `cargo build` with E0428 (`kvstore` defined
twice); had the fns been named apart, one key would still have shadowed the
other in the plugin table. The java tier keeps the spelling but writes one class
file per component, and on a case-insensitive file system the run died with
`NoClassDefFoundError ... (wrong name: revl/Components$KvstorePlugin)`. Python,
typescript, go and wasm ran it. A program that runs on four tiers and breaks on
two is refused at the checker, so the answer is the same on every tier.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl import compiler  # noqa: E402
from revl.compiler import compile_files, compile_source  # noqa: E402
from revl.errors import RevlError  # noqa: E402

TIERS = ["python", "typescript", "rust", "java", "go", "wasm"]


def _program(*names: str) -> str:
    out = ["service Store {", "  fn get(key: Str) -> Str", "}", ""]
    for index, name in enumerate(names):
        out += [f"component {name} provides k{index}: Store {{",
                f"  provide k{index} {{",
                "    fn get(key) = key",
                "  }",
                "}",
                ""]
    return "\n".join(out)


def _rust_emit():
    path = ROOT / "backends" / "rust" / "emit.py"
    spec = importlib.util.spec_from_file_location("revl_test_2224_rust_emit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Pairs the issue and the measured tiers break on: one rust plugin key, or one
# class file on a case-insensitive file system, or both.
COLLIDING = [
    ("KVStore", "Kvstore"),     # rust `kvstore`, java case-only
    ("KvStore", "Kv_store"),    # rust `kv_store`
    ("KvStore", "KVSTORE"),     # java case-only
    ("HTTPServer", "HttpServer_"),
    ("A_B", "AB"),              # no tier merges it; refused as too close
]


@pytest.mark.parametrize("first,second", COLLIDING)
def test_the_checker_refuses_the_pair_naming_both(first, second):
    with pytest.raises(RevlError) as info:
        compile_source(_program(first, second), "kv.rvl")
    error = info.value
    assert error.line == 11, error
    assert f"component `{second}` collides with component `{first}` (line 5)" in error.message
    assert f"reduce to `{compiler.component_name_fold(first)}`" in error.message
    assert "Rename one of the two components" in (error.hint or "")


def test_names_that_stay_apart_still_compile():
    """The control: `KvStore` and `Store` share a suffix, not a key."""
    document = compile_source(_program("KvStore", "Store", "KVStores"), "kv.rvl")
    assert [c["name"] for c in document["components"]] == ["KvStore", "Store", "KVStores"]


def test_an_exact_repeat_keeps_its_own_diagnostic():
    with pytest.raises(RevlError) as info:
        compile_source(_program("KVStore", "KVStore"), "kv.rvl")
    assert "duplicate component `KVStore`" in str(info.value)
    assert "collides with" not in str(info.value)


def test_the_multi_file_path_refuses_across_files(tmp_path):
    first = tmp_path / "a.rvl"
    second = tmp_path / "b.rvl"
    first.write_text(_program("KVStore"), encoding="utf-8")
    second.write_text("component Kvstore provides other: Store {\n"
                      "  provide other {\n    fn get(key) = key\n  }\n}\n",
                      encoding="utf-8")
    with pytest.raises(RevlError) as info:
        compile_files([str(first), str(second)])
    error = info.value
    assert Path(error.filename).name == "b.rvl"
    assert "component `Kvstore` collides with component `KVStore`" in error.message
    assert "a.rvl:5" in error.message


def test_the_fold_covers_the_rust_emitters_own_reduction():
    """The checker's key is coarser than the rust emitter's: any two names the
    emitter snake-cases to one key fold to one key here. Checked against the
    emitter's function as it stands on disk, so a change to `_snake` that made
    it merge names the fold keeps apart fails here rather than at cargo."""
    emit = _rust_emit()
    names = ["KVStore", "Kvstore", "KvStore", "Kv_store", "KV_Store", "kv_store",
             "HTTPServer", "HttpServer", "Http_Server", "IOHub", "IoHub", "Store",
             "A1B", "A1b", "a1_b", "Loop", "Loop_", "LOOP", "DBPool", "DbPool",
             "Db_Pool"]
    # `_snake` is the plugin-table key, `_snake_fn` the `pub fn` identifier
    # that rustc refused as defined twice (E0428)
    for reduce in (emit._snake, emit._snake_fn):
        for a in names:
            for b in names:
                if reduce(a) == reduce(b):
                    assert compiler.component_name_fold(a) == compiler.component_name_fold(b), (
                        f"rust emits `{a}` and `{b}` as one `{reduce(a)}` "
                        f"({reduce.__name__}), but the checker would admit the pair")
    assert emit._snake("KVStore") == emit._snake("Kvstore") == "kvstore"
    assert emit._snake_fn("Loop") == "loop_" != emit._snake_fn("Loop_")


@pytest.mark.parametrize("tier", TIERS)
def test_every_tier_refuses_the_pair(tier, tmp_path):
    """The same answer on all six tiers, through `revl emit`."""
    source = tmp_path / "kv.rvl"
    source.write_text(_program("KVStore", "Kvstore"), encoding="utf-8")
    run = subprocess.run(
        [sys.executable, "-m", "revl", "emit", "--backend", tier, str(source),
         "-o", str(tmp_path / f"out.{tier}")],
        capture_output=True, text=True, timeout=300, cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert run.returncode != 0, f"{tier} emitted the colliding pair:\n{run.stdout}"
    assert "component `Kvstore` collides with component `KVStore`" in run.stderr, run.stderr
    assert not (tmp_path / f"out.{tier}").exists()


def _census_certify():
    spec = importlib.util.spec_from_file_location(
        "revl_test_2224_census", ROOT / "tools" / "gate_reference_census.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_admission_certify()


def test_the_census_mirror_of_the_certifier_withholds_the_pair():
    """`tools/gate_reference_census.py` mirrors the crate's certifier, which now
    folds component names. Without the fold the mirror certifies a pair the
    reference refuses, and the census would report the crate's withheld
    verdict as a divergence."""
    certify = _census_certify()
    def pair(first: str, second: str) -> str:
        return ("service S {\n  fn a(x: Int) -> Int\n}\n"
                f"component {first} provides s: S {{\n  provide s {{ fn a(x) = x }}\n}}\n"
                f"component {second} provides t: S {{\n  provide t {{ fn a(x) = x }}\n}}\n")
    assert certify(pair("KVStore", "Store"))
    assert not certify(pair("KVStore", "Kvstore"))
    assert not certify(pair("A_B", "AB"))
