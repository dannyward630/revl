"""`revl_source` reads a held buffer by its name, and its stdlib answer says
what it is (issues #2322, #2184).

#2322: `revl_source {symbol: "plain.rvl"}`, naming the file the session loaded,
was read as a declaration called `plain` and refused with "no top-level
declaration matches `plain`". Nothing read a whole held buffer, `source:10` on a
file-loaded composition told a READ to name the one to edit in `target`, and a
bare call listed the stdlib and nothing of what the session held.

#2184: the empty `source` counted as no source (truthiness), the stdlib listing
said `packaged: true` for a root that is not there, the tool description
promised a stdlib answer only "with nothing loaded", and `concat` was refused
without the `Str.concat` it was meant for.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl.mcp import server as server_mod  # noqa: E402
from revl.mcp import stdlib as stdlib_mod  # noqa: E402
from revl.mcp.server import handle  # noqa: E402

needs_runtime = pytest.mark.skipif(
    importlib.util.find_spec("cordis") is None,
    reason="the session tools need the cordis-py runtime: install it with "
           "`sh backends/python/setup.sh`")

PLAIN = """service Kv {
  fn get(key: Str) -> Str
}

component Store provides kv: Kv {
  provide kv {
    fn get(key: Str) -> Str = key
  }
}
"""


def _call(tool: str, arguments: dict) -> dict:
    response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": arguments}})
    return response["result"]["structuredContent"]


def _message(result: dict) -> str:
    return " ".join(str(d.get("message", ""))
                    for d in result.get("diagnostics") or [])


@pytest.fixture
def session(tmp_path):
    """A clean session, authoring trusted under `tmp_path`."""
    if server_mod.SESSION.loaded:
        server_mod.SESSION.unload()
    old = server_mod.AUTHORING
    server_mod.set_authoring_trust(roots=(str(tmp_path),))
    try:
        yield
    finally:
        server_mod.AUTHORING = old
        if server_mod.SESSION.loaded:
            server_mod.SESSION.unload()


@pytest.fixture
def plain(tmp_path, session):
    path = tmp_path / "plain.rvl"
    path.write_text(PLAIN, encoding="utf-8")
    return path


@needs_runtime
def test_a_loaded_file_is_read_whole_by_its_name(plain):
    assert _call("revl_load", {"files": [str(plain)]})["ok"] is True
    for spelling in ("plain.rvl", str(plain), "plain"):
        result = _call("revl_source", {"symbol": spelling})
        assert result["ok"] is True, (spelling, result)
        assert result["kind"] == "buffer", result
        assert result["buffer"] == str(plain), result
        assert result["text"] == PLAIN, result
        assert result["lines"] == len(PLAIN.splitlines()), result


@needs_runtime
def test_inline_source_is_read_whole_as_source(session):
    assert _call("revl_load", {"source": PLAIN})["ok"] is True
    result = _call("revl_source", {"symbol": "source"})
    assert result["ok"] is True, result
    assert result["kind"] == "buffer" and result["text"] == PLAIN, result


def test_a_files_argument_is_read_whole_too(plain):
    result = _call("revl_source", {"symbol": "plain.rvl", "files": [str(plain)]})
    assert result["ok"] is True, result
    assert result["kind"] == "buffer" and result["text"] == PLAIN, result


@needs_runtime
def test_a_declaration_name_still_reads_the_declaration(plain):
    assert _call("revl_load", {"files": [str(plain)]})["ok"] is True
    result = _call("revl_source", {"symbol": "Store"})
    assert result["ok"] is True and result["kind"] == "component", result
    missing = _call("revl_source", {"symbol": "nothere.rvl"})
    assert missing["ok"] is False, missing
    assert "no top-level declaration matches" in _message(missing), missing


@needs_runtime
def test_a_read_is_not_told_to_edit(plain):
    assert _call("revl_load", {"files": [str(plain)]})["ok"] is True
    for symbol in ("source:10", "source"):
        result = _call("revl_source", {"symbol": symbol})
        assert result["ok"] is False, result
        message = _message(result)
        assert "target" not in message and "edit" not in message, message
        assert str(plain) in message and "no inline source" in message, message


@needs_runtime
def test_a_bare_call_lists_the_held_buffers(plain):
    assert _call("revl_load", {"files": [str(plain)]})["ok"] is True
    result = _call("revl_source", {})
    assert result["ok"] is True and result["kind"] == "stdlib", result
    held = result["held"]
    assert [b["buffer"] for b in held] == [str(plain)], held
    assert held[0]["symbols"] == {"Kv": "service", "Store": "component"}, held
    assert held[0]["lines"] == len(PLAIN.splitlines()), held


def test_a_bare_call_with_nothing_held_has_no_held_block(session):
    result = _call("revl_source", {})
    assert result["ok"] is True and "held" not in result, result


# -- #2184 ------------------------------------------------------------------

def test_an_empty_source_is_a_source():
    assert server_mod._stdlib_only({"source": ""}) is False
    assert server_mod._names_no_source({"source": ""}) is False
    assert server_mod._names_no_source({}) is True


def test_an_empty_source_is_read_as_its_own_buffer(session):
    result = _call("revl_source", {"symbol": "list_sort", "source": ""})
    assert result["ok"] is False, result
    assert "packaged" not in _message(result), result


def test_a_held_draft_is_read_by_the_handler(session):
    """The handler, not just the predicate: a draft is read, never the stdlib."""
    server_mod.SESSION.pending_draft = {"vs": {"source": PLAIN, "modules": {}}}
    try:
        declared = _call("revl_source", {"symbol": "Store"})
        assert declared["ok"] is True and declared["kind"] == "component", declared
        whole = _call("revl_source", {"symbol": "source"})
        assert whole["ok"] is True and whole["kind"] == "buffer", whole
        bare = _call("revl_source", {})
        assert bare["kind"] == "stdlib" and bare["held"][0]["buffer"] == "source"
        unknown = _call("revl_source", {"symbol": "list_sort"})
        assert unknown["ok"] is False
        assert "packaged" not in _message(unknown), unknown
    finally:
        server_mod.SESSION.pending_draft = None


def test_a_held_draft_is_not_the_stdlib(monkeypatch):
    monkeypatch.setattr(server_mod._draft, "pending",
                        lambda session: {"vs": {"source": PLAIN}})
    assert server_mod.SESSION.loaded is False
    assert server_mod._stdlib_only({}) is False
    assert server_mod._stdlib_only({"symbol": "Store"}) is False


def test_the_listing_does_not_claim_a_missing_root_is_packaged(monkeypatch,
                                                                tmp_path):
    missing = tmp_path / "no-stdlib"
    monkeypatch.setattr(stdlib_mod._paths, "stdlib_root", lambda: missing)
    catalogue = stdlib_mod.catalogue()
    assert catalogue["packaged"] is False and catalogue["modules"] == []
    if server_mod.SESSION.loaded:
        server_mod.SESSION.unload()
    result = _call("revl_source", {})
    assert result["ok"] is False, result
    assert "not installed" in _message(result), result


def test_the_listing_of_the_real_root_is_packaged():
    catalogue = stdlib_mod.catalogue()
    assert catalogue["packaged"] is True and catalogue["modules"], catalogue
    assert all(m["packaged"] is True for m in catalogue["modules"])


def test_a_bare_method_name_is_refused_with_the_qualified_one(session):
    result = _call("revl_source", {"symbol": "concat"})
    assert result["ok"] is False, result
    assert "`Str.concat`" in _message(result), result


def test_the_description_does_not_limit_the_listing_to_nothing_loaded():
    tool = next(t for t in server_mod.TOOLS if t["name"] == "revl_source")
    assert "With nothing loaded and no" not in tool["description"]
    assert "buffer" in tool["description"]
    symbol = tool["inputSchema"]["properties"]["symbol"]["description"]
    assert "with nothing loaded" not in symbol and "buffer" in symbol


# -- review follow-ups -------------------------------------------------------

def _two(tmp_path):
    a, b = tmp_path / "a" / "plain.rvl", tmp_path / "b" / "plain.rvl"
    for path in (a, b):
        path.parent.mkdir()
        path.write_text(PLAIN, encoding="utf-8")
    return a, b


def test_a_name_declared_in_two_buffers_keeps_its_ambiguity(session, tmp_path):
    """`Store` is declared in two files and one of them is `Store.rvl`: the
    name is a declaration (twice), not a request for that buffer."""
    a, b = tmp_path / "Store.rvl", tmp_path / "other.rvl"
    a.write_text(PLAIN, encoding="utf-8")
    b.write_text(PLAIN.replace("Kv", "Kw"), encoding="utf-8")
    result = _call("revl_source", {"symbol": "Store", "files": [str(a), str(b)]})
    assert result["ok"] is False, result
    assert "more than one declaration" in _message(result), result


def test_two_buffers_matching_one_name_are_refused_with_both(session, tmp_path):
    a, b = _two(tmp_path)
    result = _call("revl_source", {"symbol": "plain.rvl",
                                   "files": [str(a), str(b)]})
    assert result["ok"] is False, result
    message = _message(result)
    assert "2 held buffers" in message and str(a) in message and str(b) in message
    one = _call("revl_source", {"symbol": str(a), "files": [str(a), str(b)]})
    assert one["ok"] is True and one["buffer"] == str(a), one


@pytest.mark.parametrize("extra", [{"comments": False}, {"with": ["deps"]},
                                   {"with": ["knowledge"]}])
def test_a_buffer_read_refuses_declaration_options(plain, extra):
    result = _call("revl_source", {"symbol": "plain.rvl",
                                   "files": [str(plain)], **extra})
    assert result["ok"] is False, result
    assert "read whole" in _message(result), result


def test_a_loaded_file_beats_a_dependency_with_its_basename():
    from revl.mcp import edit

    vs = {"files": ["/w/plain.rvl"], "files_content": {"/w/plain.rvl": PLAIN},
          "dependencies": {"/w/lib/plain.rvl": "service Dep {\n}\n"}}
    read = edit.read_buffer(vs, "plain.rvl")
    assert read["buffer"] == "/w/plain.rvl" and read["text"] == PLAIN, read


def test_a_dependency_buffer_is_read_whole():
    from revl.mcp import edit

    dep = "service Dep {\n}\n"
    vs = {"files": ["/w/plain.rvl"], "files_content": {"/w/plain.rvl": PLAIN},
          "dependencies": {"/w/lib/dep.rvl": dep}}
    read = edit.read_buffer(vs, "dep.rvl")
    assert read["buffer"] == "/w/lib/dep.rvl" and read["text"] == dep, read
    assert read["kind"] == "buffer" and read["lines"] == 2, read
