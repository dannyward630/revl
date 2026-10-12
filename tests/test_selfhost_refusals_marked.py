"""Every reference refusal in the `emit_*_refusals` fixtures is a named port
refusal on the go, java, rust, ts and wasm self-host emitters (issues #2316,
#2353, #2367, #2383).

A self-host emitter has no refusal channel: where its reference raises
`EmitError`, the port must still answer with a `<<UNSUPPORTED-...>>` marker,
the one spelling `tools/selfhost_differential_survey.py` reads as a refusal.
Output the reference refuses that carries no such marker is a silent
difference, which is what these issues found on each tier.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from revl import compile_files  # noqa: E402
from _load_by_path import load_by_path  # noqa: E402

TIERS = ("go", "java", "rust", "ts", "wasm")
DOCUMENTS = sorted(
    str(p.relative_to(ROOT))
    for p in (ROOT / "tests" / "fixtures").glob("emit_*_refusals/*.rvl"))
MARKER = re.compile(r"<<UNSUPPORTED[^>]*>>")


@pytest.fixture(scope="module")
def tiers():
    out = {}
    for tier in TIERS:
        module = load_by_path(f"test_selfhost_emit_{tier}",
                              ROOT / "tests" / f"test_selfhost_emit_{tier}.py")
        out[tier] = (module._load_reference_emit(),
                     module._exec_emitted()[f"emit_{tier}_src"])
    return out


@pytest.mark.parametrize("tier", TIERS)
def test_every_refusal_document_is_marked_by_the_port(tiers, tier):
    reference, port = tiers[tier]
    refused, silent = 0, []
    for rel in DOCUMENTS:
        ir = compile_files([str(ROOT / rel)])
        try:
            reference.emit(ir)
            continue
        except reference.EmitError:
            refused += 1
        if not MARKER.search(port(ir)):
            silent.append(rel)
    # non-vacuity: the fixtures hold refusals for every one of these tiers
    assert refused >= 10, f"only {refused} documents refused on {tier}"
    assert silent == [], f"{tier} port answers these refusals silently: {silent}"


# Issue #2389: on py, rust and java a namespaced provision key either emits the
# reference bytes or carries a named marker. The ports do not mangle the key
# yet, so each one names it (`<<UNSUPPORTED-NAMESPACED-KEY:Comp.key>>`).
NAMESPACED_TIERS = ("py", "rust", "java")
NAMESPACED_SOURCES = ("ISSUE_REPRODUCER", "TWO_NAMESPACES",
                      "ROUTED_NAMESPACED", "KEYWORD_PARTS")


@pytest.fixture(scope="module")
def namespaced_tiers():
    out = {}
    for tier in NAMESPACED_TIERS:
        module = load_by_path(f"test_selfhost_emit_{tier}",
                              ROOT / "tests" / f"test_selfhost_emit_{tier}.py")
        out[tier] = (module._load_reference_emit(),
                     module._exec_emitted()[f"emit_{tier}_src"])
    return out


@pytest.mark.parametrize("tier", NAMESPACED_TIERS)
def test_a_namespaced_key_matches_the_reference_or_is_named(
        namespaced_tiers, tier, tmp_path):
    reference, port = namespaced_tiers[tier]
    sources = load_by_path("test_namespaced_key_emit_1914",
                           ROOT / "tests" / "test_namespaced_key_emit_1914.py")
    silent = []
    for name in NAMESPACED_SOURCES:
        path = tmp_path / f"{name}.rvl"
        path.write_text(getattr(sources, name))
        ir = compile_files([str(path)])
        got = port(ir)
        if got == reference.emit(ir):
            continue
        if "<<UNSUPPORTED-NAMESPACED-KEY:" not in got:
            silent.append(name)
    assert silent == [], f"{tier} port differs silently on: {silent}"


@pytest.mark.parametrize("tier", NAMESPACED_TIERS)
def test_an_unqualified_key_carries_no_namespaced_marker(
        namespaced_tiers, tier):
    """Positive control: the realm corpus document has only flat keys."""
    reference, port = namespaced_tiers[tier]
    ir = compile_files([str(ROOT / "tests" / "fixtures" / "emit_ts_corpus"
                            / "realm_intercept.rvl")])
    got = port(ir)
    assert "<<UNSUPPORTED-NAMESPACED-KEY:" not in got
    assert got == reference.emit(ir)
