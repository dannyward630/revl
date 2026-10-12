"""Issue #2205: one vocabulary for tiers across every `--backend` flag.

`revl emit --backend py` and `revl run --backend python` both used to fail with
`invalid choice`. Every `--backend` now takes either spelling of a tier, and
hands downstream the spelling that command always used (`py` for run, `python`
for emit), so nothing past the parser changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from revl.__main__ import main
from revl.cli.parser import build_parser
from revl.tiers import TIERS, canonical_tier, tier_dir

EXAMPLE = str(Path(__file__).resolve().parents[1] / "examples" / "counter_pair.rvl")


def _backend(*argv: str) -> object:
    return build_parser().parse_args(list(argv)).backend


def test_run_takes_the_directory_spelling_and_keeps_its_own_value():
    assert _backend("run", EXAMPLE, "--backend", "python") == "py"
    assert _backend("run", EXAMPLE, "--backend", "typescript") == "ts"
    assert _backend("run", EXAMPLE, "--backend", "py") == "py"


def test_emit_takes_the_short_spelling_and_keeps_its_own_value():
    assert _backend("emit", EXAMPLE, "--backend", "py") == "python"
    assert _backend("emit", EXAMPLE, "--backend", "ts") == "typescript"
    assert _backend("emit", EXAMPLE, "--backend", "go") == "go"
    # the default is untouched
    assert _backend("emit", EXAMPLE) == "typescript"


def test_emit_with_the_short_spelling_works_end_to_end(tmp_path, capsys):
    out = tmp_path / "out.py"
    assert main(["emit", EXAMPLE, "--backend", "py", "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8").strip()


def test_bundle_and_deploy_accept_both_spellings_in_dir_form():
    parsed = build_parser().parse_args(
        ["bundle", EXAMPLE, "--out", "o", "--backend", "py", "--backend", "rust"])
    assert parsed.backend == ["python", "rust"]
    assert _backend("deploy", "map.toml", "--backend", "ts") == "typescript"
    assert _backend("deploy", "map.toml") == "python"


def test_test_command_keeps_all_and_short_names():
    assert _backend("test", EXAMPLE, "--backend", "all") == "all"
    assert _backend("test", EXAMPLE, "--backend", "typescript") == "ts"


def test_import_commands_keep_their_subsets():
    assert _backend("import", "wit", "x.wit", "--backend", "python") == "py"
    assert _backend("import", "wit", "x.wit") == "wasm"
    with pytest.raises(SystemExit):
        _backend("import", "a2a", "x.json", "--backend", "rust")


def test_deploy_backend_is_validated_at_parse_time(capsys):
    with pytest.raises(SystemExit) as raised:
        _backend("deploy", "map.toml", "--backend", "bogus")
    assert raised.value.code == 2
    err = capsys.readouterr().err
    assert "bogus" in err
    for tier in TIERS:
        assert tier in err


def test_a_refusal_lists_the_canonical_names(capsys):
    with pytest.raises(SystemExit):
        _backend("emit", EXAMPLE, "--backend", "cobol")
    assert "choose from py, ts, rust, java, wasm, go" in capsys.readouterr().err


def test_the_table_maps_every_spelling_to_one_tier():
    for tier, aliases in TIERS.items():
        assert canonical_tier(tier) == tier
        for alias in aliases:
            assert canonical_tier(alias) == tier
    assert tier_dir("py") == tier_dir("python") == "python"
    assert tier_dir("ts") == "typescript"
