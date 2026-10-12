"""The self-host gate refuses folded names the way the reference does (issue
#2351).

The reference refuses two component names, or two service names, that differ
only in letter case or underscores: inside one program (issues #2224 and #2275)
and, on a hot swap, between an incoming name and a running one (#2309 for
components, #2334 for services). The self-host driver takes a running manifest
too (`selfhost/compile.rvl`, `admit_into` / `compile_to_into`), and before this
it raised no objection to any of these and went on to EMIT the program the
reference refuses. Now each of them is refused under the tag `FOLD` with the
reference's own sentence, byte for byte.

The running composition reaches the self-host as the item-186 row wire
(`revl.manifest.manifest_wire`), the same projection `tests/test_selfhost_
admit_into.py` uses, and the reference is asked the same question with the
compiled IR.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from revl.compiler import compile_source  # noqa: E402
from revl.errors import RevlError  # noqa: E402
from revl.manifest import manifest_wire  # noqa: E402

import test_selfhost_compile as compile_oracle  # noqa: E402
import test_selfhost_lower as lower_oracle  # noqa: E402


@pytest.fixture(scope="module")
def native() -> dict:
    """selfhost/compile.rvl, compiled by the reference and run on python."""
    return compile_oracle._exec_selfhost("selfhost/compile.rvl")


def _refusal(source: str, **kwargs) -> RevlError:
    with pytest.raises(RevlError) as info:
        compile_source(source, "candidate.rvl", **kwargs)
    return info.value


RUNNING_COMPONENT = """service Store {
  fn get(key: Str) -> Str
}

component KVStore provides a: Store {
  provide a {
    fn get(key) = key
  }
}
"""

INCOMING_COMPONENT = """component Kvstore provides b: Store {
  provide b {
    fn get(key) = key
  }
}
"""

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

SERVICE_PAIR = """service KVStore {
  fn get(key: Str) -> Str
}

service Kv_store {
  fn put(key: Str) -> Str
}
"""

COMPONENT_PAIR = """service Store {
  fn get(key: Str) -> Str
}

component KVStore provides a: Store {
  provide a {
    fn get(key) = key
  }
}

component KvStore provides b: Store {
  provide b {
    fn get(key) = key
  }
}
"""


@pytest.mark.parametrize("running, incoming", [
    (RUNNING_COMPONENT, INCOMING_COMPONENT),
    (RUNNING_SERVICE, INCOMING_SERVICE),
], ids=["component", "service"])
def test_the_manifest_path_refuses_a_name_folded_onto_a_running_one(
        native, running, incoming):
    ir = compile_source(running, "running.rvl")
    wire = manifest_wire(ir)
    error = _refusal(incoming, manifest=ir)
    assert lower_oracle._classify(error) == "FOLD", error.message
    assert native["admit_into"](incoming, wire) == "FOLD|" + error.message
    assert (native["compile_to_into"](incoming, "py", wire)
            == "REFUSED|FOLD|" + error.message)


@pytest.mark.parametrize("source", [SERVICE_PAIR, COMPONENT_PAIR],
                         ids=["services", "components"])
def test_one_program_with_two_folded_names_is_refused_in_the_reference_words(
        native, source):
    error = _refusal(source)
    assert native["compile_to"](source, "py") == "REFUSED|FOLD|" + error.message
    assert native["admit_into"](source, "") == "FOLD|" + error.message
    assert native["admit"](source) == "FOLD|" + error.message


def test_the_program_fold_comes_before_the_running_fold(native):
    """The reference checks the incoming program's own names first, so a
    candidate carrying both collisions is refused for its own pair."""
    ir = compile_source(RUNNING_SERVICE, "running.rvl")
    incoming = SERVICE_PAIR.replace("KVStore", "KVSTORE_")
    error = _refusal(incoming, manifest=ir)
    assert "collides with service `KVSTORE_`" in error.message, error.message
    assert native["admit_into"](incoming, manifest_wire(ir)) == "FOLD|" + error.message


def test_a_parser_refusal_still_comes_before_a_fold(native):
    """The reference's parser refuses an unclassified extern before its fold
    check runs, so the gate names the extern, not the fold."""
    source = SERVICE_PAIR + 'extern fn f() -> Str = @py { return "x" }\n'
    error = _refusal(source)
    assert "unclassified extern" in error.message, error.message
    assert native["admit"](source).startswith("G8|"), native["admit"](source)
    ir = compile_source(RUNNING_SERVICE, "running.rvl")
    incoming = INCOMING_SERVICE + 'extern fn f() -> Str = @py { return "x" }\n'
    error = _refusal(incoming, manifest=ir)
    assert "unclassified extern" in error.message, error.message
    verdict = native["admit_into"](incoming, manifest_wire(ir))
    assert verdict.startswith("G8|"), verdict


# An earlier extern whose `undo` names no fn draws a LOWERING refusal (G4); a
# later extern with no classification word draws a PARSER refusal (G8), which
# the reference raises first.
G4_THEN_G8 = (
    "extern acquire fn open_ledger(path: Str) -> LedgerHandle undo ghost_fn(1)\n"
    "  = @py { return abs(hash(path)) % 100000 }\n"
    'extern fn f() -> Str = @py { return "x" }\n')


@pytest.mark.parametrize("fold", [True, False], ids=["with_fold", "no_fold"])
def test_a_later_unclassified_extern_outranks_an_earlier_undo_refusal(
        native, fold):
    source = (SERVICE_PAIR if fold else "") + G4_THEN_G8
    error = _refusal(source)
    assert "unclassified extern" in error.message, error.message
    verdict = native["admit"](source)
    assert verdict.startswith("G8|"), verdict


def test_withdrawn_redeclared_and_apart_names_raise_no_fold(native):
    """The positive controls: a swap that withdraws the running component, a
    service redeclared under its exact running name, and names that stay apart
    are all admitted by the reference and draw no FOLD refusal here."""
    ir = compile_source(RUNNING_COMPONENT, "running.rvl")
    compile_source(INCOMING_COMPONENT, "candidate.rvl", manifest=ir,
                   replacing=("KVStore",))
    withdrawn = native["admit_into"](
        INCOMING_COMPONENT, manifest_wire(ir, replacing=("KVStore",)))
    assert not withdrawn.startswith("FOLD|"), withdrawn
    apart = INCOMING_COMPONENT.replace("Kvstore", "Cache")
    compile_source(apart, "candidate.rvl", manifest=ir)
    assert not native["admit_into"](apart, manifest_wire(ir)).startswith("FOLD|")

    svc_ir = compile_source(RUNNING_SERVICE, "running.rvl")
    redeclared = "service KVStore {\n  fn get(key: Str) -> Str\n}\n"
    compile_source(redeclared, "candidate.rvl", manifest=svc_ir)
    verdict = native["admit_into"](redeclared, manifest_wire(svc_ir))
    assert not verdict.startswith("FOLD|"), verdict
    apart_svc = INCOMING_SERVICE.replace("Kvstore", "Cache")
    compile_source(apart_svc, "candidate.rvl", manifest=svc_ir)
    verdict = native["admit_into"](apart_svc, manifest_wire(svc_ir))
    assert not verdict.startswith("FOLD|"), verdict
    # an exact repeat is `duplicate service`, never a fold
    repeat = SERVICE_PAIR.replace("Kv_store", "KVStore")
    assert not native["admit"](repeat).startswith("FOLD|")


ROWLESS_RUNNING = RUNNING_COMPONENT + "\ncomponent Noop {\n}\n"


def _local_component(name: str) -> str:
    return ("service Local {\n  fn get(key: Str) -> Str\n}\n\n"
            f"component {name} provides b: Local {{\n  provide b {{\n"
            "    fn get(key) = key\n  }\n}\n")


def test_the_manifest_path_refuses_a_name_folded_onto_a_rowless_running_one(native):
    """Issue #2289: `component Noop {}` has no provision, requirement, route or
    handoff row, so the wire names it with a presence row, and the self-host
    refuses `NOOP` against it in the reference's words. The same name is a
    replacement and a name that stays apart is admitted, on both sides."""
    ir = compile_source(ROWLESS_RUNNING, "running.rvl")
    wire = manifest_wire(ir)
    assert "Noop" in wire.split(";"), wire
    error = _refusal(_local_component("NOOP"), manifest=ir)
    assert lower_oracle._classify(error) == "FOLD", error.message
    assert native["admit_into"](_local_component("NOOP"), wire) == "FOLD|" + error.message
    for name in ("Noop", "Cache"):
        compile_source(_local_component(name), "candidate.rvl", manifest=ir)
        assert native["admit_into"](_local_component(name), wire) == "", name


def test_a_garbled_presence_row_is_refused_by_name(native):
    """A presence row is a bare name; a row carrying anything else is a wire
    the gate cannot read, and it refuses rather than skip it. A guard: base
    refuses this row too, so it pins that the new row kind stays narrow."""
    verdict = native["admit_into"](_local_component("Cache"), "Kv/a/;No!op")
    assert "unrecognized manifest row `No!op`" in verdict, verdict
