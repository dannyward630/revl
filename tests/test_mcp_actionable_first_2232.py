"""The fields a client acts on come first in a tool result's text (issue #2232).

A tool result carries `trace`, `verified` and `loopAxes` measured in kilobytes,
and the short fields a client acts on (`ok`, `note`, `disk`, `next`, `hint`)
used to land after them, so a client with a result-size cap never saw them.
`handle` now serializes the text payload with those keys first. Only key order
changes: every key and value is kept, and `structuredContent` is the payload
object itself.
"""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl.mcp import server as server_mod  # noqa: E402
from revl.mcp.server import _actionable_first, handle  # noqa: E402

ORDER = ["ok", "note", "disk", "next", "hint"]


# ------------------------------------------------------------------ unit

def test_the_five_keys_come_first_in_a_fixed_order():
    payload = {"trace": [1], "hint": "h", "verified": True, "next": "n",
               "loopAxes": {}, "disk": {"inSync": True}, "note": "x", "ok": True}
    shaped = _actionable_first(payload)
    assert list(shaped)[:5] == ORDER


def test_every_key_and_value_is_kept_and_the_rest_keep_their_order():
    payload = {"zeta": 1, "ok": True, "trace": [2], "hint": "h", "alpha": {"b": 1, "a": 2}}
    shaped = _actionable_first(payload)
    assert shaped == payload
    assert list(shaped) == ["ok", "hint", "zeta", "trace", "alpha"]
    assert list(shaped["alpha"]) == ["b", "a"]


def test_absent_keys_are_skipped_not_invented():
    shaped = _actionable_first({"trace": [], "disk": {}, "x": 1})
    assert list(shaped) == ["disk", "trace", "x"]


def test_the_input_is_not_mutated():
    payload = {"trace": [], "ok": True}
    _actionable_first(payload)
    assert list(payload) == ["trace", "ok"]


@pytest.mark.parametrize("value", [None, [1, 2], "text", 7, ("ok",)])
def test_a_non_dict_passes_through(value):
    assert _actionable_first(value) is value


# ----------------------------------------------------------- end to end

pytestmark_e2e = pytest.mark.skipif(
    importlib.util.find_spec("cordis") is None,
    reason="the change verbs boot a composition and need the cordis-py runtime "
           "(install it with `sh backends/python/setup.sh`)")


@pytest.fixture
def tenants(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    old = server_mod.AUTHORING
    server_mod.set_authoring_trust(roots=(str(tmp_path),))
    path = tmp_path / "tenants.rvl"
    shutil.copy(ROOT / "examples" / "tenants.rvl", path)
    yield path
    if server_mod.SESSION.loaded:
        server_mod.SESSION.unload()
    server_mod.SESSION.pending_draft = None
    server_mod.SESSION.draft = None
    server_mod.AUTHORING = old


def _result(tool: str, arguments: dict) -> dict:
    response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": arguments}})
    return response["result"]


@pytestmark_e2e
def test_a_committed_withdraw_leads_with_the_actionable_fields(tenants):
    loaded = _result("revl_load", {"files": [str(tenants)]})
    assert loaded["structuredContent"]["ok"] is True, loaded
    _result("revl_change", {"withdraw": {"component": "TenantAStore", "cascade": True}})
    result = _result("revl_change", {"commit": True})
    payload = result["structuredContent"]
    assert payload["ok"] is True and payload.get("committed") is True, payload
    text = result["content"][0]["text"]

    # the text is the same payload, only reordered
    assert json.loads(text) == payload
    # `ok` is the first key
    assert list(json.loads(text))[0] == "ok"
    assert text.lstrip("{\n ").startswith('"ok"')
    # and the two a client must see survive a cap of 400 characters
    head = text[:400]
    assert '"note"' in head, head
    assert '"disk"' in head, head
