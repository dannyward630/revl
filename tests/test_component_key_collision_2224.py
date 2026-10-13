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


# Issue #2275: two SERVICE names that differ only in letter case or underscores.
# The rust tier names a service's dispatch fn `_revl_dispatch_<snake>`, so
# `KVStore` and `Kvstore` both define `_revl_dispatch_kvstore` (E0428), and the
# java tier writes `Components$KVStore.class` and `Components$Kvstore.class`,
# one file on a case-insensitive file system. Refused by the same fold.

SERVICE_PAIR = """service KVStore {
  fn get(key: Str) -> Str
}

service Kvstore {
  fn put(key: Str) -> Str
}

component A provides a: KVStore, b: Kvstore {
  provide a {
    fn get(key) = key
  }
  provide b {
    fn put(key) = key
  }
}
"""


def test_the_checker_refuses_two_services_naming_both():
    with pytest.raises(RevlError) as info:
        compile_source(SERVICE_PAIR, "svc.rvl")
    error = info.value
    assert error.line == 5, error
    assert ("service `Kvstore` collides with service `KVStore` (line 1)"
            in error.message), error.message
    assert "reduce to `kvstore`" in error.message
    assert "Rename one of the two services" in (error.hint or "")


def test_the_rust_dispatch_fn_reduction_is_covered_by_the_fold():
    """The rust tier names the dispatch fn after `_snake(service)`; any two
    service names it merges must fold to one key."""
    emit = _rust_emit()
    names = ["KVStore", "Kvstore", "KvStore", "Kv_store", "HTTPServer",
             "HttpServer", "Store", "Stores"]
    for a in names:
        for b in names:
            if emit._snake(a) == emit._snake(b):
                assert compiler.component_name_fold(a) == compiler.component_name_fold(b)


def test_services_that_stay_apart_and_an_exact_repeat_keep_their_answers():
    apart = SERVICE_PAIR.replace("Kvstore", "KVStores")
    document = compile_source(apart, "svc.rvl")
    assert [s for s in document["services"]] == ["KVStore", "KVStores"]
    repeat = ("service KVStore {\n  fn get(key: Str) -> Str\n}\n"
              "service KVStore {\n  fn put(key: Str) -> Str\n}\n")
    with pytest.raises(RevlError) as info:
        compile_source(repeat, "svc.rvl")
    assert "duplicate service `KVStore`" in str(info.value)
    assert "collides with" not in str(info.value)


def test_the_multi_file_path_refuses_two_services_across_files(tmp_path):
    first = tmp_path / "a.rvl"
    second = tmp_path / "b.rvl"
    first.write_text("service KVStore {\n  fn get(key: Str) -> Str\n}\n",
                     encoding="utf-8")
    second.write_text("service Kvstore {\n  fn put(key: Str) -> Str\n}\n",
                      encoding="utf-8")
    with pytest.raises(RevlError) as info:
        compile_files([str(first), str(second)])
    error = info.value
    assert Path(error.filename).name == "b.rvl"
    assert "service `Kvstore` collides with service `KVStore`" in error.message
    assert "a.rvl:1" in error.message


@pytest.mark.parametrize("tier", TIERS)
def test_every_tier_refuses_the_service_pair(tier, tmp_path):
    source = tmp_path / "svc.rvl"
    source.write_text(SERVICE_PAIR, encoding="utf-8")
    run = subprocess.run(
        [sys.executable, "-m", "revl", "emit", "--backend", tier, str(source),
         "-o", str(tmp_path / f"out.{tier}")],
        capture_output=True, text=True, timeout=300, cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert run.returncode != 0, f"{tier} emitted the colliding services:\n{run.stdout}"
    assert "service `Kvstore` collides with service `KVStore`" in run.stderr, run.stderr
    assert not (tmp_path / f"out.{tier}").exists()


def test_the_census_mirror_withholds_two_folded_services():
    certify = _census_certify()
    def pair(first: str, second: str) -> str:
        return (f"service {first} {{\n  fn a(x: Int) -> Int\n}}\n"
                f"service {second} {{\n  fn b(x: Int) -> Int\n}}\n")
    assert certify(pair("KVStore", "Store"))
    assert not certify(pair("KVStore", "Kvstore"))


# Issue #2276: a hot-swap's incoming component against the running components
# the admission keeps. A single compile refuses `KVStore` with `Kvstore`; a
# hot-swap adding `Kvstore` to a composition holding `KVStore` must too, unless
# it withdraws `KVStore`.

RUNNING = """service Store {
  fn get(key: Str) -> Str
}

component KVStore provides a: Store {
  provide a {
    fn get(key) = key
  }
}
"""

INCOMING = """component Kvstore provides b: Store {
  provide b {
    fn get(key) = key
  }
}
"""


def test_a_hot_swap_refuses_a_name_folded_onto_a_running_component():
    running = compile_source(RUNNING, "running.rvl")
    with pytest.raises(RevlError) as info:
        compile_source(INCOMING, "incoming.rvl", manifest=running)
    error = info.value
    assert Path(error.filename).name == "incoming.rvl"
    assert error.line == 1, error
    assert ("component `Kvstore` collides with running component `KVStore`"
            in error.message), error.message
    assert "reduce to `kvstore`" in error.message
    assert 'replacing=("KVStore",)' in (error.hint or ""), error.hint


def test_a_hot_swap_that_withdraws_the_running_component_is_admitted():
    running = compile_source(RUNNING, "running.rvl")
    document = compile_source(INCOMING, "incoming.rvl", manifest=running,
                              replacing=("KVStore",))
    assert [c["name"] for c in document["components"]] == ["Kvstore"]


def test_a_hot_swap_with_a_name_that_stays_apart_is_admitted():
    running = compile_source(RUNNING, "running.rvl")
    document = compile_source(INCOMING.replace("Kvstore", "Cache"),
                              "incoming.rvl", manifest=running)
    assert [c["name"] for c in document["components"]] == ["Cache"]


# Issue #2334: a hot-swap's incoming SERVICE against the running composition's
# services. A running service is never withdrawn by an admission (an incoming
# service of the same name redeclares it, gated by the replacement relation), so
# an incoming service whose name folds onto a running one under a different
# spelling leaves the composition holding the pair a single compile refuses.

RUNNING_SERVICE = """service KVStore {
  fn get(key: Str) -> Str
}

component A provides a: KVStore {
  provide a {
    fn get(key) = key
  }
}
"""

INCOMING_SERVICE = """service Kvstore {
  fn put(key: Str) -> Str
}

component B provides b: Kvstore {
  provide b {
    fn put(key) = key
  }
}
"""


def test_a_hot_swap_refuses_a_service_folded_onto_a_running_service():
    running = compile_source(RUNNING_SERVICE, "running.rvl")
    with pytest.raises(RevlError) as info:
        compile_source(INCOMING_SERVICE, "incoming.rvl", manifest=running)
    error = info.value
    assert Path(error.filename).name == "incoming.rvl"
    assert error.line == 1, error
    assert ("service `Kvstore` collides with running service `KVStore`"
            in error.message), error.message
    assert "reduce to `kvstore`" in error.message
    assert "`KVStore`" in (error.hint or ""), error.hint


def test_a_hot_swap_refuses_a_folded_service_through_compile_files(tmp_path):
    running = compile_source(RUNNING_SERVICE, "running.rvl")
    incoming = tmp_path / "incoming.rvl"
    incoming.write_text(INCOMING_SERVICE.replace("Kvstore", "Kv_store"),
                        encoding="utf-8")
    with pytest.raises(RevlError) as info:
        compile_files([str(incoming)], manifest=running, replacing=("A",))
    error = info.value
    assert Path(error.filename).name == "incoming.rvl"
    assert ("service `Kv_store` collides with running service `KVStore`"
            in error.message), error.message


def test_a_hot_swap_redeclaring_or_adding_apart_services_keeps_its_answer():
    running = compile_source(RUNNING_SERVICE, "running.rvl")
    apart = compile_source(INCOMING_SERVICE.replace("Kvstore", "Cache"),
                           "incoming.rvl", manifest=running)
    assert sorted(apart["services"]) == ["Cache", "KVStore"]
    # the exact name is a redeclaration, which the replacement relation admits
    # when it keeps every running toucher's operations
    redeclared = compile_source(
        "service KVStore {\n  fn get(key: Str) -> Str\n}\n",
        "incoming.rvl", manifest=running)
    assert sorted(redeclared["services"]["KVStore"]["methods"]) == ["get"]
