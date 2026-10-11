"""The knowledge index parses a file once, however many comments it has
(issue #2191).

`index_text` anchors every comment block to its declaration or member. It used
to parse the whole file again for each commented declaration and re-format the
enclosing span once per comment, so `revl_check` time grew with comments x
file size. The parse count of indexing (and of a whole `revl_check`) must not
depend on the number of comments, and the entries must be exactly what they
were before the change.
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl import formatter, knowledge  # noqa: E402
from revl.diagnostics import GUARANTEES  # noqa: E402
from revl.mcp import knowledge_index  # noqa: E402
from revl.mcp.server import handle  # noqa: E402
from revl.parser import Parser  # noqa: E402

CODES = set(GUARANTEES)


def _source(n: int) -> str:
    """n commented fns, each with two commented statements, and a service
    whose n method signatures are commented."""
    parts = ["// The file as a whole.\n"]
    for i in range(n):
        parts.append(f"// what f{i} does\n"
                     f"fn f{i}(x: Int) -> Int {{\n"
                     f"    // step one of f{i}\n"
                     f"    let y = x + {i}\n"
                     f"    // step two of f{i}\n"
                     f"    return y * 2\n"
                     f"}}\n\n")
    parts.append("service Counter {\n")
    for i in range(n):
        parts.append(f"    // bump {i}\n"
                     f"    fn bump{i}(by: Int) -> Int\n")
    parts.append("}\n")
    return "".join(parts)


@pytest.fixture
def counted(monkeypatch):
    calls = {"parse": 0, "format": 0}
    parse = Parser.parse
    fmt = formatter.format_source

    def counting_parse(self, *a, **k):
        calls["parse"] += 1
        return parse(self, *a, **k)

    def counting_format(*a, **k):
        calls["format"] += 1
        return fmt(*a, **k)

    monkeypatch.setattr(Parser, "parse", counting_parse)
    monkeypatch.setattr(formatter, "format_source", counting_format)
    return calls


def _index_counts(counted, n: int) -> dict:
    counted["parse"] = counted["format"] = 0
    entries = knowledge.index_text("big.rvl", _source(n), None, CODES)
    assert len(entries) == 4 * n
    return dict(counted)


def test_index_parses_once_whatever_the_comment_count(counted):
    small, large = _index_counts(counted, 3), _index_counts(counted, 30)
    assert small["parse"] == large["parse"] == 1, (small, large)


def test_fingerprint_formats_each_span_once(counted):
    # 3 fns + 3 service methods + the service and fn decls themselves: the
    # spans are distinct, and a span shared by several comments is formatted
    # once. Comments inside fn bodies anchor to the fn (no members), so the
    # fn span is shared by three comments.
    n = 10
    counts = _index_counts(counted, n)
    assert counts["format"] == 2 * n, counts


def test_index_of_working_set_parses_once_per_buffer(counted):
    vs = {"files": ["a.rvl"], "files_content": {"a.rvl": _source(12)}}
    counted["parse"] = 0
    entries = knowledge_index.index_of(vs, None)
    assert len(entries) == 4 * 12
    assert counted["parse"] == 1, counted


def _check_parses(counted, n: int) -> int:
    counted["parse"] = 0
    response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "revl_check",
                                  "arguments": {"source": _source(n)}}})
    checked = response["result"]["structuredContent"]
    assert checked["ok"], checked
    assert checked["knowledge"]["entries"] == 4 * n, checked["knowledge"]
    return counted["parse"]


def test_revl_check_parse_count_is_flat_in_comments(counted):
    small, large = _check_parses(counted, 2), _check_parses(counted, 25)
    assert small == large, (small, large)


# Digests of the entries on the base commit (84e0357df), before the change.
# "notes" pins examples/app/notes.rvl as it was then: an edit to that example
# legitimately moves its digest. Recompute it with `_digest` on the edited
# file, and check first that the edit is the only change to `index_text`'s
# inputs (a change to the indexer itself must keep the old digest).
NOTES = ROOT / "examples" / "app" / "notes.rvl"
EXPECTED = {
    "synthetic": "19d6ce55d9db324a81458455c11f215b751947bcd828de6ca5174becff93d69d",
    "notes": "18f44eed19329fa62029e399c4b8f486da2234fecb1ab88fba654506c1d0ebf2",
}


def _digest(entries) -> str:
    return hashlib.sha256(json.dumps(entries, sort_keys=True)
                          .encode("utf-8")).hexdigest()


def test_entries_are_byte_identical_to_before():
    got = {"synthetic": _digest(knowledge.index_text("big.rvl", _source(6), None, CODES)),
           "notes": _digest(knowledge.index_text(
               "examples/app/notes.rvl", NOTES.read_text(encoding="utf-8"), None, CODES))}
    assert got == EXPECTED
