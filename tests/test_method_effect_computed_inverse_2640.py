"""Issue #2640: prove a bounded computed inverse for list append."""

from pathlib import Path

import pytest

from revl.compiler import compile_source
from revl.errors import RevlError

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "tests" / "fixtures" / "g4_method_append_inverse.rvl").read_text(
    encoding="utf-8")


def _append_step(source: str = SOURCE) -> dict:
    ir = compile_source(source, "g4_method_append_inverse.rvl")
    [ledger] = [c for c in ir["components"] if c["name"] == "LedgerStore"]
    [provide] = [s for s in ledger["body"] if s.get("step") == "provide"]
    [append] = [m for m in provide["methods"] if m["name"] == "append"]
    return next(s for s in append["body"] if s.get("step") == "effect")


def test_same_key_list_append_has_a_proven_inverse_without_capturing_the_preimage():
    step = _append_step()

    assert step["inverse"] == "table"
    assert step.get("undo_captures", []) == []
    assert step["undo"]["kind"] == "if"
    assert step["undo"]["cond"] == {"kind": "name", "id": "known"}


def test_unproven_drop_last_helper_is_refused_with_a_named_g4_reason():
    source = SOURCE.replace(
        "return xs.slice(0, xs.length() - 1)",
        "return xs.slice(1, xs.length())")

    with pytest.raises(RevlError) as excinfo:
        _append_step(source)

    assert getattr(excinfo.value, "code", None) == "G4"
    assert "computed append inverse" in str(excinfo.value)


def _reassigned_key_source() -> str:
    source = SOURCE.replace(
        "      let known = store.get(id) != None",
        "      var key = id\n"
        "      let known = store.get(key) != None\n"
        "      key = \"other\"")
    source = source.replace("store.insert(id, (store.get(id) ?? []).push(msg))",
                            "store.insert(key, (store.get(key) ?? []).push(msg))")
    source = source.replace("store.insert(id, drop_last(store.get(id) ?? []))",
                            "store.insert(key, drop_last(store.get(key) ?? []))")
    return source.replace("store.remove(id)", "store.remove(key)")


@pytest.mark.parametrize("source", [
    SOURCE.replace("store.get(id) != None", 'store.get("other") != None'),
    SOURCE.replace("(store.get(id) ?? []).push(msg)",
                   '(store.get("other") ?? []).push(msg)'),
    SOURCE.replace("drop_last(store.get(id) ?? [])",
                   'drop_last(store.get("other") ?? [])'),
    SOURCE.replace("let known = store.get(id) != None",
                   "var known = store.get(id) != None\n      known = false"),
    _reassigned_key_source(),
    SOURCE.replace(
        "      effect store.insert(id, (store.get(id) ?? []).push(msg))",
        "      effect store.insert(id, [\"between\"])\n"
        "      undo store.remove(id)\n"
        "      effect store.insert(id, (store.get(id) ?? []).push(msg))"),
])
def test_mismatched_or_stale_computed_inverse_is_refused_by_g4(source: str):
    with pytest.raises(RevlError) as excinfo:
        _append_step(source)

    assert excinfo.value.code == "G4"
    assert "computed append inverse" in str(excinfo.value)
