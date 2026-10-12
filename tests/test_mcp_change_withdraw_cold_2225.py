"""`revl_change withdraw` on a cold call plans against what the call carries
(issue #2225).

A cold call is the normal first call of a session: nothing is loaded and the
composition rides in `files`, `source` or `modules`. `_tool_change` used to plan
the withdrawal against the session before that load, so the plan was empty:
`cascade: true` was dropped (the proposal removed only the named component and
its commit failed on the stranded dependent's activation), and a withdrawal
without `cascade` was accepted instead of refused with the cascade hint.

The warm path (`revl_load`, then the same withdraw) is the behaviour to match.
Each cold case runs once per carrier: `files`, `source`, and `source` with the
in-memory `modules` a `use` resolves against.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl.mcp import server as server_mod  # noqa: E402
from revl.mcp.server import handle  # noqa: E402

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("cordis") is None,
    reason="the change verbs boot a composition and need the cordis-py runtime: "
           "install it with `sh backends/python/setup.sh`")

SERVICES = ("service Store { fn get() -> Str }\n"
            "service Api { fn read() -> Str }\n"
            "service Clock { fn now() -> Int }\n"
            "\n")

COMPONENTS = ("component MemStore provides store: Store {\n"
              '  provide store { fn get() = "stored" }\n'
              "}\n"
              "\n"
              "component ApiImpl requires store: Store provides api: Api {\n"
              "  provide api { fn read() = store.get() }\n"
              "}\n"
              "\n"
              "component FixedClock provides clock: Clock {\n"
              "  provide clock { fn now() = 7 }\n"
              "}\n")

SOURCE = SERVICES + COMPONENTS

# the `modules` carrier: the store's text comes from a `use`d module, which
# resolves only when the compile has the in-memory module set
MODULES = {"lib.rvl": 'pub fn label() -> Str { return "stored" }\n'}
MODULE_SOURCE = ('use "lib.rvl" { label }\n' + SERVICES
                 + COMPONENTS.replace('fn get() = "stored"', "fn get() = label()"))

ALL = {"MemStore", "ApiImpl", "FixedClock"}
CARRIERS = ("files", "source", "modules")


def _call(tool: str, arguments: dict) -> dict:
    response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": arguments}})
    return response["result"]["structuredContent"]


def _components() -> set[str]:
    return {c["name"] for c in server_mod.SESSION.ir["manifest"]["components"]}


def _reset() -> None:
    if server_mod.SESSION.loaded:
        server_mod.SESSION.unload()
    server_mod.SESSION.pending_draft = None
    server_mod.SESSION.draft = None
    _call("revl_change", {"discard": True})


@pytest.fixture(autouse=True)
def clean_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    old = server_mod.AUTHORING
    server_mod.set_authoring_trust(roots=(str(tmp_path),))
    _reset()
    yield tmp_path
    _reset()
    server_mod.AUTHORING = old


def _carried(kind: str, tmp_path: Path) -> dict:
    if kind == "files":
        path = tmp_path / "app.rvl"
        path.write_text(SOURCE)
        return {"files": [str(path)]}
    if kind == "source":
        return {"source": SOURCE}
    return {"source": MODULE_SOURCE, "modules": MODULES}


def _cascade(result: dict) -> list[str]:
    return [entry["component"] for entry in (result.get("plan") or {}).get("cascade") or []]


# ------------------------------------------------ cold, cascade: true


@pytest.mark.parametrize("kind", CARRIERS)
def test_a_cold_cascading_withdrawal_plans_the_cascade_and_commits(kind, clean_session):
    result = _call("revl_change", {"withdraw": {"component": "MemStore", "cascade": True},
                                   **_carried(kind, clean_session)})
    assert result["ok"] is True and result["committed"] is False, result
    assert _cascade(result) == ["ApiImpl"], result.get("plan")
    assert result["proposal"]["replacing"] == ["MemStore", "ApiImpl"]
    committed = _call("revl_change", {"commit": True})
    assert committed["ok"] is True and committed["committed"] is True, committed
    assert _components() == {"FixedClock"}


@pytest.mark.parametrize("kind", CARRIERS)
def test_a_cold_one_shot_cascading_withdrawal_commits(kind, clean_session):
    """The issue comment's call 1: the one-shot cold form, `commit: true` in
    the same call, swaps on the first try."""
    result = _call("revl_change", {"withdraw": {"component": "MemStore", "cascade": True},
                                   "commit": True, **_carried(kind, clean_session)})
    assert result["ok"] is True and result["committed"] is True, result
    assert _cascade(result) == ["ApiImpl"]
    assert {(c["component"], c["change"]) for c in result["components"]} == {
        ("MemStore", "removed"), ("ApiImpl", "removed")}
    assert _components() == {"FixedClock"}


# ------------------------------------------------ cold, no cascade


def _warm_refusal(carried: dict) -> dict:
    assert _call("revl_load", carried)["ok"] is True
    warm = _call("revl_change", {"withdraw": "MemStore"})
    _reset()
    return warm


@pytest.mark.parametrize("kind", CARRIERS)
def test_a_cold_stranding_withdrawal_is_refused_like_the_warm_one(kind, clean_session):
    carried = _carried(kind, clean_session)
    warm = _warm_refusal(carried)
    cold = _call("revl_change", {"withdraw": "MemStore", **carried})
    assert cold["ok"] is False and cold["committed"] is False, cold
    assert cold["verified"]["admission"] == "refused"
    assert cold["plan"] == warm["plan"] and _cascade(cold) == ["ApiImpl"]
    assert cold["hint"] == warm["hint"]
    assert "cascade: true" in cold["hint"]
    assert cold["diagnostics"][0]["message"] == warm["diagnostics"][0]["message"]
    assert "would leave 1 component(s) without a provider" \
        in cold["diagnostics"][0]["message"]
    # refused up front: nothing was loaded, so the session is still cold
    assert server_mod.SESSION.loaded is False and cold["loaded"] is False
    assert "nothing was loaded" in cold["note"]


@pytest.mark.parametrize("kind", CARRIERS)
def test_a_cold_leaf_withdrawal_is_not_refused(kind, clean_session):
    """A withdrawal with nothing to strand still goes through on a cold call."""
    result = _call("revl_change", {"withdraw": "FixedClock", "commit": True,
                                   **_carried(kind, clean_session)})
    assert result["ok"] is True and result["committed"] is True, result
    assert result["plan"]["cascade"] == []
    assert _components() == {"MemStore", "ApiImpl"}


# ------------------------------------------------ warm control


def test_the_warm_cascading_withdrawal_is_unchanged(clean_session):
    assert _call("revl_load", {"source": SOURCE})["ok"] is True
    result = _call("revl_change", {"withdraw": {"component": "MemStore", "cascade": True}})
    assert result["ok"] is True and result["committed"] is False, result
    assert _cascade(result) == ["ApiImpl"]
    assert result["proposal"]["replacing"] == ["MemStore", "ApiImpl"]
    assert _call("revl_change", {"commit": True})["committed"] is True
    assert _components() == {"FixedClock"}


def test_the_warm_stranding_withdrawal_is_still_refused(clean_session):
    assert _call("revl_load", {"source": SOURCE})["ok"] is True
    result = _call("revl_change", {"withdraw": "MemStore"})
    assert result["ok"] is False and _cascade(result) == ["ApiImpl"]
    assert "nothing was loaded" not in result["note"]
    assert _components() == ALL
