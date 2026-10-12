"""A hot-swap can be asked to prove its boundary (issue #2277).

`Session.swap` disposes the predecessor generation and boots the successor in
the same process, with nothing between the two: the R4 residue report `unload`
produces was never consulted at a swap, and nothing compared the process
against where it started. With `prove_boundary=True` the swap seals the
boundary after the predecessor's teardown and before the successor's load. Any
non-baseline value refuses the swap by name and the predecessor is booted again
so it keeps serving; a clean seal carries the proof as `boundary`.

Every test drives the Session API directly, one process, one session: a
composition that answers, a swap asked for the proof, then the same call again
to see which generation is serving. Refusals are asserted by `code` on the
`SessionError` the swap raises, so on a base without the option each test fails
on its own rather than the whole file erroring at import.
"""

from __future__ import annotations

import copy
import importlib.util
import os
import sys
import threading
from pathlib import Path

import pytest

from revl.compiler import compile_source
from revl.mcp.session import Session, SessionError

ROOT = Path(__file__).resolve().parents[1]
_BACKEND = ROOT / "backends" / "python"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("cordis") is None,
    reason="a swap boots a live cordis-py composition; install it with "
           "`sh backends/python/setup.sh` and run under its venv")

#: A component that acquires a host map and releases it: a clean teardown.
CLEAN = """
service Counter { fn next() -> Int }
component CounterSvc provides counter: Counter {
  let m = effect Map.new() undo m.drop()
  provide counter { fn next() = 7 }
}
"""

#: No host acquisition at all, for the driver that captures no host trace.
PLAIN = """
service Counter { fn next() -> Int }
component CounterSvc provides counter: Counter {
  provide counter { fn next() = 7 }
}
"""

#: A service whose one method runs a host body, so a test can make the
#: predecessor do something to the process before the swap.
_HOST = """
extern emission fn host_poke() = @py {{
{body}
    return
}}
service Probe {{ emission fn poke() }}
component ProbeSvc provides probe: Probe {{
  provide probe {{ fn poke() {{ emit host_poke() }} }}
}}
service Counter {{ fn next() -> Int }}
component CounterSvc provides counter: Counter {{
  provide counter {{ fn next() = 7 }}
}}
"""

#: The host stub the witnessed-mutation test renames (and its undo).
WITNESSED = """
type Stash = { path: Str, bak: Str }
type FsError = { code: Str }
extern pure fn unstash(w: Stash) -> Unit = @py {
    import os
    if os.path.exists(w['bak']):
        os.replace(w['bak'], w['path'])
    return
}
extern witnessed[fs] fn stash_path(p: Str) -> Result[Stash, FsError] undo unstash(result) = @py {
    import os
    bak = p + '.bak'
    os.replace(p, bak)
    return Ok({'path': p, 'bak': bak})
}
service Ops { emission fn stash(p: Str) }
component Agent provides ops: Ops {
  provide ops { fn stash(p) { effect stash_path(p) } }
}
service Counter { fn next() -> Int }
component CounterSvc provides counter: Counter {
  provide counter { fn next() = 7 }
}
"""

#: Every check a sealed boundary carries.
CHECKS = {"residue", "hostResources", "escrow", "registers", "threads", "env",
          "modules"}


def _ir(source: str, name: str = "boundary.rvl") -> dict:
    return copy.deepcopy(compile_source(source, name))


def _successor(source: str) -> dict:
    """`source` answering 8 instead of 7, so a swap that landed is visible."""
    return _ir(source.replace("fn next() = 7", "fn next() = 8"))


def _host(body: str) -> str:
    return _HOST.format(body="\n".join("    " + line for line in body.splitlines()))


def _next(session) -> int:
    return session.call("counter", "next")["result"]


def _refused(session, successor: dict, **options) -> SessionError:
    with pytest.raises(SessionError) as caught:
        session.swap(successor, prove_boundary=True, **options)
    return caught.value


@pytest.fixture
def session():
    live = Session()
    yield live
    if live.loaded:
        live.unload()


def _drop_fails(monkeypatch):
    """The predecessor's map is never released: its `drop` raises. The undo
    still runs, so the four cordis counters drain, but the host trace has a
    `new` with no `drop` (the compiler already refuses an `undo` that is not
    the release, so this is how a release goes missing at run time)."""
    import runtime

    def fail(self):
        raise RuntimeError("injected: the map would not drop")

    monkeypatch.setattr(runtime.Map, "drop", fail)


def test_swap_refuses_when_predecessor_leaves_residue(session, monkeypatch):
    session.load(_ir(CLEAN))
    assert _next(session) == 7
    _drop_fails(monkeypatch)
    refusal = _refused(session, _successor(CLEAN))
    assert refusal.code == "RESIDUE_LEFT", refusal
    assert refusal.boundary["checks"]["hostResources"] is False
    [unreleased] = refusal.boundary["detail"]["residue"]["unreleased"]
    assert "new() with no drop()" in unreleased
    assert refusal.boundary["noResidue"] is False
    # the base generation keeps serving
    assert _next(session) == 7
    monkeypatch.undo()


def test_clean_swap_carries_boundary_proof(session):
    session.load(_ir(CLEAN))
    state = session.swap(_successor(CLEAN), prove_boundary=True)
    boundary = state["boundary"]
    assert boundary["noResidue"] is True, boundary
    assert set(boundary["checks"]) == CHECKS
    assert all(boundary["checks"].values()), boundary["checks"]
    assert "refusals" not in boundary and "unverified" not in boundary
    assert _next(session) == 8
    # and a second proven swap seals against the same baseline
    again = session.swap(_ir(CLEAN), prove_boundary=True)
    assert again["boundary"]["noResidue"] is True, again["boundary"]
    assert _next(session) == 7


def test_swap_without_host_trace_refuses_unverified(session):
    session.load(_ir(PLAIN))
    del session._driver.host_events     # a driver that captured no host trace
    refusal = _refused(session, _successor(PLAIN))
    assert refusal.code == "UNVERIFIED", refusal
    assert refusal.boundary["unverified"] == ["hostResources"]
    assert "hostResources" not in refusal.boundary["checks"]
    assert refusal.boundary["noResidue"] is False
    assert _next(session) == 7


def test_swap_refuses_escrow_open(session, tmp_path):
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("deliverable", encoding="utf-8")
    session.load(_ir(WITNESSED), record=True)
    session.call("ops", "stash", [str(artifact)])   # witnessed, not committed
    assert not artifact.exists()
    refusal = _refused(session, _successor(WITNESSED))
    assert refusal.code == "ESCROW_OPEN", refusal
    assert refusal.boundary["detail"]["escrowed"] >= 1
    assert _next(session) == 7
    # the mutation is still the session's to settle: an abort reverts it
    assert session.abort()["aborted"]
    assert artifact.read_text(encoding="utf-8") == "deliverable"


def test_boundary_refuses_register_drift(session):
    """A trace observer subscribed while generation N was live and never
    unsubscribed. A user `@py` body cannot import the runtime (the backend-
    import jail refuses it), so the subscription is made from here, inside N's
    lifetime, through the runtime's own `add_trace`."""
    import runtime

    session.load(_ir(PLAIN))
    unsubscribe = runtime.add_trace(lambda event: None)
    try:
        refusal = _refused(session, _successor(PLAIN))
        assert refusal.code == "REGISTER_DRIFT", refusal
        assert refusal.boundary["detail"]["registers"] == ["_observers"]
        assert _next(session) == 7
    finally:
        unsubscribe()


def test_boundary_refuses_thread_left(session):
    stop = threading.Event()
    sys.modules["_revl_test_2277_stop"] = stop   # how the host body reaches it
    session.load(_ir(_host(
        "import sys, threading\n"
        "stop = sys.modules['_revl_test_2277_stop']\n"
        "threading.Thread(target=stop.wait, name='left-by-gen-n').start()")))
    try:
        session.call("probe", "poke")
        refusal = _refused(session, _successor(_host("pass")))
        assert refusal.code == "THREAD_LEFT", refusal
        assert refusal.boundary["detail"]["threads"] == ["left-by-gen-n"]
        assert _next(session) == 7
    finally:
        stop.set()
        for thread in threading.enumerate():
            if thread.name == "left-by-gen-n":
                thread.join()
        del sys.modules["_revl_test_2277_stop"]


def test_boundary_refuses_env_drift(session, monkeypatch):
    key = "REVL_TEST_2277_LEFT"
    monkeypatch.delenv(key, raising=False)
    session.load(_ir(_host(f"import os\nos.environ[{key!r}] = 'secret'")))
    try:
        session.call("probe", "poke")
        refusal = _refused(session, _successor(_host("pass")))
        assert refusal.code == "ENV_DRIFT", refusal
        assert refusal.boundary["detail"]["env"] == [key]
        assert "secret" not in repr(refusal.boundary)   # keys, never values
        assert _next(session) == 7
    finally:
        os.environ.pop(key, None)


def test_boundary_refuses_module_left(session, tmp_path, monkeypatch):
    """A module a host body imported under generation N that is neither the
    generation's own, the standard library nor revl's toolchain stays cached
    process-wide, so the successor could import N's copy of it."""
    name = "revl_test_2277_left"
    (tmp_path / f"{name}.py").write_text("STATE = []\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    session.load(_ir(_host(f"import {name}")))
    try:
        session.call("probe", "poke")
        refusal = _refused(session, _successor(_host("pass")))
        assert refusal.code == "MODULE_LEFT", refusal
        assert refusal.boundary["detail"]["modules"] == [name]
        assert _next(session) == 7
    finally:
        sys.modules.pop(name, None)


#: A component with resolved config. The runtime keeps every component's
#: resolved config (secret fields included) and never empties it.
CONFIGURED = """
service Counter { fn next() -> Int }
component CounterSvc provides counter: Counter {
  config { a: Int = 7 }
  provide counter { fn next() { return config.a } }
}
"""

#: The same service from a component with no config at all.
UNCONFIGURED = """
service Counter { fn next() -> Int }
component OtherSvc provides counter: Counter {
  provide counter { fn next() = 8 }
}
"""


def test_the_predecessors_resolved_config_is_withdrawn_not_refused(session):
    """The resolved-config table is the toolchain's residue, not the author's:
    the seal withdraws the predecessor's entry rather than refusing every
    composition that declares `config`, and the successor no longer sees the
    values its predecessor ran with."""
    import runtime

    session.load(_ir(CONFIGURED))
    assert runtime.resolved_config("CounterSvc") == {"a": 7}
    state = session.swap(_ir(UNCONFIGURED), prove_boundary=True)
    boundary = state["boundary"]
    assert boundary["noResidue"] is True, boundary
    assert boundary["detail"]["discharged"] == {"RESOLVED_CONFIG": ["CounterSvc"]}
    assert runtime.resolved_config("CounterSvc") is None
    assert _next(session) == 8


def test_a_realm_placement_seals_clean(session):
    """Realm labels are a process-wide intern table of stateless identities,
    shared across generations by design, so a placement does not refuse."""
    realm = CLEAN.replace("  let m =",
                          '  isolate counter in realm("billing")\n  let m =')
    session.load(_ir(realm))
    state = session.swap(_successor(realm), prove_boundary=True)
    assert state["boundary"]["noResidue"] is True, state["boundary"]
    assert _next(session) == 8


def test_proof_on_another_tier_refuses_tier_unsupported(session):
    session.load(_ir(CLEAN))
    refusal = _refused(session, _successor(CLEAN), backend="go")
    assert refusal.code == "TIER_UNSUPPORTED", refusal
    assert _next(session) == 7
    assert session._generation == 1    # nothing was torn down


def test_swap_without_the_option_is_unchanged(session, monkeypatch):
    """No proof asked: the leaky predecessor's swap lands exactly as it always
    has, and the answer carries no `boundary`."""
    session.load(_ir(CLEAN))
    _drop_fails(monkeypatch)
    state = session.swap(_successor(CLEAN))
    assert "boundary" not in state
    assert _next(session) == 8
    monkeypatch.undo()
