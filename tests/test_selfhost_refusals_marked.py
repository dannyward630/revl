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
