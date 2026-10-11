"""The knowledge index lexes a file a fixed number of times, and the marked
note import parses each file once (issue #2250, follow-ups of #2191).

`index_text` parsed once since #2191, but `nested.span` still lexed the whole
file again for every comment on a member (a service operation, a provide
block's method, a type's field), so indexing still grew with member comments x
file size. `notes.import_marked` parsed the file again (and once more for the
anchor's declaration) for every marked note. Both counts must not depend on
the number of comments, and the answers must be what they were.
"""

import hashlib
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl import knowledge, lexer, parser  # noqa: E402
from revl.diagnostics import GUARANTEES  # noqa: E402
from revl.mcp import notes as notes_mod  # noqa: E402
from revl.parser import Parser  # noqa: E402

CODES = set(GUARANTEES)


def _source(n: int) -> str:
    """A service, a component's provide block and a record type, each with n
    members, and a comment above every member."""
    parts = ["// The file as a whole.\n",
             "service Counter {\n"]
    for i in range(n):
        parts.append(f"    // bump {i}\n"
                     f"    fn bump{i}(by: Int) -> Int\n")
    parts.append("}\n\n"
                 "// A counter that adds.\n"
                 "component Adder provides counter: Counter {\n"
                 "  provide counter {\n")
    for i in range(n):
        parts.append(f"    // add {i}\n"
                     f"    fn bump{i}(by) = by + {i}\n\n")
    parts.append("  }\n}\n\n"
                 "type Wide = {\n")
    for i in range(n):
        parts.append(f"  // field {i}\n"
                     f"  f{i}: Int,\n")
    parts.append("}\n")
    return "".join(parts)


@pytest.fixture
def counted(monkeypatch):
    """Calls of the lexer and parser entry points. The parser binds `lex` at
    import, everything else imports it from `revl.lexer` when it runs, so both
    names are counted."""
    calls = {"lex": 0, "parse": 0}
    lex = lexer.lex
    parse = Parser.parse

    def counting_lex(*a, **k):
        calls["lex"] += 1
        return lex(*a, **k)

    def counting_parse(self, *a, **k):
        calls["parse"] += 1
        return parse(self, *a, **k)

    monkeypatch.setattr(lexer, "lex", counting_lex)
    monkeypatch.setattr(parser, "lex", counting_lex)
    monkeypatch.setattr(Parser, "parse", counting_parse)
    return calls


def _index_counts(counted, n: int) -> dict:
    text = _source(n)
    counted["lex"] = counted["parse"] = 0
    entries = knowledge.index_text("wide.rvl", text, None, CODES)
    assert len(entries) == 3 * n + 2
    members = [e for e in entries if "." in (e["anchor"]["symbol"] or "")]
    assert len(members) == 3 * n, [e["anchor"]["symbol"] for e in entries]
    return dict(counted)


def test_index_lex_count_is_flat_in_member_comments(counted):
    small, large = _index_counts(counted, 3), _index_counts(counted, 30)
    assert small["lex"] == large["lex"] <= 2, (small, large)
    assert small["parse"] == large["parse"] == 1, (small, large)


def _marked(n: int) -> str:
    """`_source(n)` with a rendered note above every member and declaration."""
    out, count = [], 0
    for line in _source(n).split("\n"):
        stripped = line.strip()
        if stripped.startswith(("fn ", "service ", "component ", "f")) \
                and not stripped.startswith("// "):
            indent = line[:len(line) - len(line.lstrip())]
            note_id = f"k_{count:012x}"
            count += 1
            out += [f"{indent}// note {note_id}:", f"{indent}// body {count}",
                    f"{indent}// [{note_id}]"]
        out.append(line)
    return "\n".join(out)


def _import_counts(counted, monkeypatch, n: int) -> tuple[dict, list]:
    text = _marked(n)
    vs = {"source": None, "files": ["wide.rvl"],
          "files_content": {"wide.rvl": text}, "modules": {}}
    anchored = []

    def recording_add(session, vs, note, symbol, **kw):
        anchored.append(symbol)
        return {"symbol": symbol}

    # only the anchoring of each marked block is counted here; recording the
    # note (`add`) resolves its symbol on its own
    monkeypatch.setattr(notes_mod, "add", recording_add)
    session = types.SimpleNamespace()
    notes_mod.clear(session)
    counted["lex"] = counted["parse"] = 0
    notes_mod.import_marked(session, vs)
    return dict(counted), anchored


def test_import_marked_parses_once_per_file(counted, monkeypatch):
    (small, few), (large, many) = (_import_counts(counted, monkeypatch, 3),
                                   _import_counts(counted, monkeypatch, 30))
    assert len(few) == 3 * 3 + 2 and len(many) == 3 * 30 + 2, (few, many)
    assert small["parse"] == large["parse"] == 1, (small, large)
    assert small["lex"] == large["lex"] <= 2, (small, large)


# Digests taken on the base commit (perf/2191-parse-once at a57ad149f), before
# the change: the entries, and the symbols the marked notes anchor to. A
# change to `_source` or `_marked` moves them; recompute both on the commit
# before the change being tested, never on the change itself.
EXPECTED = {
    "index": "9a0cbf3a7709ae5dbf37e89b41b97785c69eb1fccc5e4d7305d039390d839fb4",
    "marked": "2d82de74fab64450cbbbd6d720f5c9a4b1876d714392b760f7332d9bc5908eb8",
}


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True)
                          .encode("utf-8")).hexdigest()


def test_answers_are_byte_identical_to_before(counted, monkeypatch):
    got = {"index": _digest(knowledge.index_text("wide.rvl", _source(5), None, CODES)),
           "marked": _digest(_import_counts(counted, monkeypatch, 5)[1])}
    assert got == EXPECTED
