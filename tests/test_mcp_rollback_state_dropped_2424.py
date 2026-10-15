"""Issue #2424: `revl_rollback` must say which live state it drops.

A rollback restores the previous generation's code through `respawn`, a cold
start: the generation it leaves is not carried into the one it returns to.
`revl_undo` reports what that discards (issue #2346: `stateDropped.components`
and a `note`); a rollback discards the same kind of state and used to say
nothing. These tests hold it to the undo's shape: the same `stateDropped`
member, the same `components` list, a `note` only when something is lost.

They drive a live composition, so they need the cordis-py runtime; the gate is
a per-test marker.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl.mcp.server import handle  # noqa: E402

needs_runtime = pytest.mark.skipif(
    importlib.util.find_spec("cordis") is None,
    reason="a rollback drives a live composition; install the runtime with "
           "`sh backends/python/setup.sh`")


SERVICE = (
    "service Meter { fn log(label: Str)\n"
    "                fn get(label: Str) -> Opt[Str]\n"
    "                fn version() -> Int }\n")


def _meter(version: int) -> str:
    return SERVICE + (
        "component MeterBook provides meter: Meter {\n"
        "  let store = effect Map.new() undo store.drop()\n"
        "  provide meter {\n"
        "    fn log(label) { effect store.insert(label, label) "
        "undo store.remove(label) }\n"
        "    fn get(label) = store.get(label)\n"
        f"    fn version() = {version}\n"
        "  }\n"
        "}\n")


STATELESS = (
    "service Clock { fn now() -> Int }\n"
    "component Fixed provides clock: Clock {\n"
    "  provide clock { fn now() = 1 }\n"
    "}\n")


def _call(tool: str, arguments: dict) -> dict:
    response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": arguments}})
    return response["result"]["structuredContent"]


def _meter_call(method: str, *args) -> dict:
    return _call("revl_call", {"key": "meter", "method": method,
                               "args": list(args)})


@pytest.fixture(autouse=True)
def _fresh_server_session():
    from revl.mcp import server as server_mod

    server_mod.UNDO_STACK.clear()
    yield
    if server_mod.SESSION.loaded:
        server_mod.SESSION.unload()
    server_mod.UNDO_STACK.clear()


def _swapped_with_state() -> None:
    """Load generation 1, swap to generation 2, then record state in it."""
    assert _call("revl_load", {"source": _meter(1)})["ok"] is True
    assert _call("revl_swap", {"source": _meter(2)})["ok"] is True
    assert _meter_call("version")["result"] == 2
    for label in ("l1", "l2"):
        assert _meter_call("log", label)["ok"] is True
    assert _meter_call("get", "l1")["result"] == "l1"


@needs_runtime
def test_rollback_reports_the_live_state_it_drops():
    _swapped_with_state()
    rolled = _call("revl_rollback", {})
    assert rolled["ok"] is True and rolled["rolledBack"] is True, rolled
    assert _meter_call("version")["result"] == 1
    # the rollback started generation 1 cold: the labels are gone ...
    assert _meter_call("get", "l1")["result"] is None
    # ... and the result says so, in the undo dossier's shape
    dropped = rolled["stateDropped"]
    assert dropped["components"] == ["MeterBook"], dropped
    assert "MeterBook" in dropped["note"] and "cold" in dropped["note"]


@needs_runtime
def test_rollback_with_no_live_state_reports_nothing_dropped():
    assert _call("revl_load", {"source": _meter(1)})["ok"] is True
    assert _call("revl_swap", {"source": _meter(2)})["ok"] is True
    rolled = _call("revl_rollback", {})
    assert rolled["ok"] is True, rolled
    assert rolled["stateDropped"] == {"components": []}, rolled

    _call("revl_unload", {})
    assert _call("revl_load", {"source": STATELESS})["ok"] is True
    assert _call("revl_swap", {"source": STATELESS.replace("= 1", "= 2")}
                 )["ok"] is True
    rolled = _call("revl_rollback", {})
    assert rolled["ok"] is True, rolled
    assert rolled["stateDropped"] == {"components": []}, rolled


@needs_runtime
def test_rollback_names_a_component_the_restored_generation_withdraws():
    """A component the previous generation does not have goes down with the
    rollback, so it is named even when it holds no state."""
    assert _call("revl_load", {"source": STATELESS})["ok"] is True
    successor = STATELESS + (
        "service Echo { fn ping() -> Int }\n"
        "component Pinger provides echo: Echo {\n"
        "  provide echo { fn ping() = 7 }\n"
        "}\n")
    swapped = _call("revl_swap", {"source": successor})
    assert swapped["ok"] is True, swapped
    rolled = _call("revl_rollback", {})
    assert rolled["ok"] is True, rolled
    assert rolled["stateDropped"]["components"] == ["Pinger"], rolled


@needs_runtime
def test_an_unreadable_live_state_says_so_and_the_rollback_still_runs(
        monkeypatch):
    from revl.mcp.session import Session

    _swapped_with_state()

    def broken(self):
        raise RuntimeError("frame registry unavailable")

    monkeypatch.setattr(Session, "live_state_components", broken)
    rolled = _call("revl_rollback", {})
    assert rolled["ok"] is True and rolled["rolledBack"] is True, rolled
    assert _meter_call("version")["result"] == 1
    dropped = rolled["stateDropped"]
    assert dropped["components"] == []
    assert "frame registry unavailable" in dropped["note"]


BROKEN_ACTIVATION = (
    SERVICE + "component MeterBook provides meter: Meter {\n"
    "  let store = effect Map.new() undo store.drop()\n"
    "  provide meter { fn log(label) { effect store.insert(label, label) "
    "undo store.remove(label) }\n"
    "                  fn get(label) = store.get(label)\n"
    "                  fn version() = 0 }\n"
    "  fail \"activation cannot complete\"\n"
    "}\n")


@needs_runtime
def test_a_rollback_refused_after_the_teardown_reports_the_state_it_dropped():
    """The activation gate refuses a rollback to a generation that does not
    activate, but only after the teardown: the running generation is rebooted
    cold, its live state is gone, and the refusal says which components."""
    assert _call("revl_load", {"source": BROKEN_ACTIVATION})["ok"] is True
    assert _call("revl_swap", {"source": _meter(2)})["ok"] is True
    assert _meter_call("log", "l1")["ok"] is True
    assert _meter_call("get", "l1")["result"] == "l1"

    refused = _call("revl_rollback", {})
    assert refused["ok"] is False
    assert "swap rejected" in refused["diagnostics"][0]["message"]
    # the running generation keeps serving, but cold ...
    assert _meter_call("version")["result"] == 2
    assert _meter_call("get", "l1")["result"] is None
    # ... and the refusal names what that restart discarded
    dropped = refused["stateDropped"]
    assert dropped["components"] == ["MeterBook"], dropped
    assert "MeterBook" in dropped["note"] and "refused" in dropped["note"]


@needs_runtime
def test_a_rollback_with_nothing_to_restore_carries_no_report():
    """A refusal that ran nothing dropped nothing, so it names nothing. This is
    a regression guard, not a fix check: it passes on origin/main too."""
    assert _call("revl_load", {"source": _meter(1)})["ok"] is True
    refused = _call("revl_rollback", {})
    assert refused["ok"] is False
    assert "stateDropped" not in refused


@needs_runtime
def test_a_rollback_that_faults_after_the_teardown_reports_the_state_it_dropped(
        monkeypatch):
    """Issue #2444: a fault that is not a `SessionError`, raised after the
    teardown (here the activation gate itself breaks), still follows a cold
    restart of the running generation. The answer names what that discarded."""
    from revl.mcp.session import Session

    _swapped_with_state()

    def broken(self, *args, **kwargs):
        raise RuntimeError("health gate unavailable")

    monkeypatch.setattr(Session, "_assert_successor_activated", broken)
    faulted = _call("revl_rollback", {})
    assert faulted["ok"] is False, faulted
    assert "health gate unavailable" in faulted["diagnostics"][0]["message"]
    # the running generation keeps serving, but cold ...
    assert _meter_call("version")["result"] == 2
    assert _meter_call("get", "l1")["result"] is None
    # ... and the answer names what that restart discarded
    dropped = faulted["stateDropped"]
    assert dropped["components"] == ["MeterBook"], dropped
    assert "MeterBook" in dropped["note"]


@needs_runtime
def test_a_rollback_that_faults_before_the_teardown_carries_no_report(
        monkeypatch):
    """The generation counter did not move, so nothing was dropped. A guard,
    not a fix check: it passes on origin/main too."""
    from revl.mcp.session import Session

    _swapped_with_state()

    def broken(self, *args, **kwargs):
        raise RuntimeError("plan unavailable")

    monkeypatch.setattr(Session, "_plan_swap", broken, raising=False)
    faulted = _call("revl_rollback", {})
    assert faulted["ok"] is False, faulted
    assert "stateDropped" not in faulted
    assert _meter_call("get", "l1")["result"] == "l1"
