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


def _carried(kind: str, tmp_path: Path, edit=lambda text: text) -> dict:
    """The composition a cold call carries; `edit` rewrites its source text."""
    if kind == "files":
        path = tmp_path / "app.rvl"
        path.write_text(edit(SOURCE))
        return {"files": [str(path)]}
    if kind == "source":
        return {"source": edit(SOURCE)}
    return {"source": edit(MODULE_SOURCE), "modules": MODULES}


def _broken(text: str) -> str:
    """A compile error: a provide block under a key the component never declares."""
    return text.replace("provide store {", "provide stor {")


def _holed(text: str) -> str:
    """A carried set with one open typed hole (issue #1727: it opens a draft)."""
    return text.replace("fn read() = store.get()", "fn read() = hole[Str]")


def _drafted() -> bool:
    return server_mod._draft.pending(server_mod.SESSION) is not None


@pytest.fixture
def compiles(monkeypatch):
    """The compiles of the CARRIED set the server's door runs: the ones that
    name no manifest. (`revl_edit`'s admission recompiles the patched working
    set and always passes one; that is a different text.)"""
    seen: list[tuple] = []
    real = server_mod.compile_under_authoring

    def counting(source, files, *args, **kwargs):
        if "manifest" not in kwargs and not args:
            seen.append((source, tuple(files or ())))
        return real(source, files, *args, **kwargs)

    monkeypatch.setattr(server_mod, "compile_under_authoring", counting)
    return seen


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


# ------------------------------------------------ issue #2407: refusal wording


@pytest.mark.parametrize("kind", CARRIERS)
def test_a_cold_refusal_does_not_claim_a_running_composition(kind, clean_session):
    """Nothing is loaded after a cold refusal, so there is no running
    composition for the note to call unchanged."""
    cold = _call("revl_change", {"withdraw": "MemStore", **_carried(kind, clean_session)})
    assert cold["ok"] is False and cold["loaded"] is False
    assert server_mod.SESSION.loaded is False
    assert "running composition" not in cold["note"], cold["note"]
    assert "still cold" in cold["note"]


@pytest.mark.parametrize("kind", CARRIERS)
def test_a_cold_compile_error_is_named_and_leaves_the_session_cold(kind, clean_session):
    carried = _carried(kind, clean_session, _broken)
    result = _call("revl_change", {"withdraw": "FixedClock", **carried})
    assert result["ok"] is False and result["committed"] is False, result
    assert result["loaded"] is False and server_mod.SESSION.loaded is False
    assert not _drafted()
    assert "`stor` is not declared" in result["diagnostics"][0]["message"], result
    assert "running composition" not in result["note"], result["note"]


def test_the_warm_refusal_still_says_the_running_composition_is_unchanged(clean_session):
    """The suffix is true when something runs: it stays there."""
    assert _call("revl_load", {"source": SOURCE})["ok"] is True
    result = _call("revl_change", {"withdraw": "MemStore"})
    assert result["ok"] is False
    assert result["note"].endswith("the running composition is unchanged"), result["note"]


def test_a_proposal_held_across_an_unload_is_still_reported(clean_session):
    """A proposal survives `revl_unload` (issue #2230). A cold refusal drops the
    "running composition" suffix, but not the word about the held proposal."""
    assert _call("revl_load", {"source": SOURCE})["ok"] is True
    staged = _call("revl_change", {"withdraw": {"component": "FixedClock"}})
    assert staged["ok"] is True and staged["committed"] is False, staged
    server_mod.SESSION.unload()
    cold = _call("revl_change", {"withdraw": "MemStore", "source": SOURCE})
    assert cold["ok"] is False and cold["loaded"] is False, cold
    assert cold["proposal"]["stale"] is True, cold.get("proposal")
    assert "running composition" not in cold["note"], cold["note"]
    assert "your held proposal is still held" in cold["note"], cold["note"]
    assert "{discard: true}" in cold["note"]


# ------------------------------------------------ issue #2407: holes, drafts


@pytest.mark.parametrize("kind", CARRIERS)
def test_a_holed_carried_set_with_a_stranding_withdrawal_is_refused(kind, clean_session):
    """The plan is made from the carried set even when it has holes: the
    stranding withdrawal is refused up front and no draft is opened."""
    carried = _carried(kind, clean_session, _holed)
    result = _call("revl_change", {"withdraw": "MemStore", **carried})
    assert result["ok"] is False and result["committed"] is False, result
    assert _cascade(result) == ["ApiImpl"]
    assert "cascade: true" in result["hint"]
    assert result["loaded"] is False and server_mod.SESSION.loaded is False
    assert not _drafted()


@pytest.mark.parametrize("kind", CARRIERS)
def test_a_holed_carried_set_with_a_leaf_withdrawal_opens_the_draft(kind, clean_session):
    carried = _carried(kind, clean_session, _holed)
    result = _call("revl_change", {"withdraw": "FixedClock", **carried})
    assert result["ok"] is True and result["committed"] is False, result
    assert result["draft"] is True and _drafted()
    assert server_mod.SESSION.loaded is False


def test_a_held_draft_plans_the_withdrawal_against_the_draft(clean_session):
    """With a draft held, a call carrying nothing plans against the draft:
    unchanged by the cold fix."""
    assert _call("revl_load", {"source": _holed(SOURCE)})["draft"] is True
    refused = _call("revl_change", {"withdraw": "MemStore"})
    assert refused["ok"] is False and _cascade(refused) == ["ApiImpl"], refused
    assert "cascade: true" in refused["hint"]
    assert _drafted() and server_mod.SESSION.loaded is False
    leaf = _call("revl_change", {"withdraw": "FixedClock"})
    assert leaf["ok"] is True and leaf["draft"] is True, leaf
    assert _drafted()


# ------------------------------------------------ issue #2407: one compile


@pytest.mark.parametrize("kind", CARRIERS)
def test_a_cold_withdrawal_compiles_the_carried_set_once(kind, clean_session, compiles):
    """The plan and the load share one compile: a file that changed between two
    reads could otherwise plan one composition and boot another."""
    result = _call("revl_change", {"withdraw": {"component": "MemStore", "cascade": True},
                                   "commit": True, **_carried(kind, clean_session)})
    assert result["ok"] is True and result["committed"] is True, result
    assert len(compiles) == 1, compiles
    assert _components() == {"FixedClock"}


@pytest.mark.parametrize("kind", CARRIERS)
def test_a_cold_withdrawal_that_does_not_compile_compiles_once(kind, clean_session, compiles):
    result = _call("revl_change", {"withdraw": "FixedClock",
                                   **_carried(kind, clean_session, _broken)})
    assert result["ok"] is False and "`stor` is not declared" in \
        result["diagnostics"][0]["message"]
    assert len(compiles) == 1, compiles


def test_a_file_changed_after_the_plan_is_not_read_again(clean_session, monkeypatch):
    """The booted composition is the one that was planned, even if the file is
    rewritten between the plan and the load."""
    path = clean_session / "app.rvl"
    path.write_text(SOURCE)
    real = server_mod.compile_under_authoring

    def then_rewrite(source, files, *args, **kwargs):
        ir = real(source, files, *args, **kwargs)
        path.write_text(SERVICES + COMPONENTS.replace("FixedClock", "OtherClock"))
        return ir

    monkeypatch.setattr(server_mod, "compile_under_authoring", then_rewrite)
    result = _call("revl_change", {"withdraw": {"component": "MemStore", "cascade": True},
                                   "commit": True, "files": [str(path)]})
    assert result["ok"] is True and result["committed"] is True, result
    assert _components() == {"FixedClock"}
