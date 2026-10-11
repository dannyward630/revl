"""Follow-ups from the review of #2231 / #2245 (issue #2246)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "backends" / "python"))
import replay  # noqa: E402
import runtime  # noqa: E402
from revl.recover_binding import _open_calls  # noqa: E402
from revl.recovery import recover  # noqa: E402
from revl.wal import unresolved_crossings  # noqa: E402

try:  # noqa: SIM105
    import cordis  # noqa: F401
    HAVE_CORDIS = True
except ModuleNotFoundError:  # pragma: no cover - depends on the interpreter
    HAVE_CORDIS = False
needs_cordis = pytest.mark.skipif(not HAVE_CORDIS, reason="needs cordis-py")

_CALL = {"receiver": "s", "method": "m", "args": []}


def _unsettled_wal(path):
    """A WAL with one emission that crossed and was never settled."""
    wal = replay.WriteAheadLog(str(path), ir={}, generation=1).open()
    timeline = replay.Timeline("Svc")
    timeline.attach_wal(wal, {})
    timeline.record_emission("db", "send", (), None, ("test", 1))
    wal.close()
    return str(path)


# --- tail-seal fsync message -------------------------------------------------

def test_seal_torn_tail_fsync_failure_says_durability_not_host_permission(
        tmp_path, monkeypatch):
    path = tmp_path / "torn.wal"
    path.write_bytes(b'{"record": "header"}\n{"record": "ef')

    def _fail(_fd):
        raise OSError("disk gone")
    monkeypatch.setattr(replay.os, "fsync", _fail)
    with pytest.raises(replay.ReplayError) as caught:
        replay._seal_torn_tail(str(path))
    message = str(caught.value)
    assert "host call" not in message
    assert "torn tail" in message and "durable" in message


# --- --require-settled-wal: one named exception ------------------------------

def _driver(wal_path):
    from revl.run import _Driver  # noqa: PLC0415
    return _Driver({}, {}, None, None, lambda: object(), None,
                   wal_path=wal_path, require_settled_wal=True)


def test_direct_driver_on_an_unsettled_wal_raises_the_named_exception(tmp_path):
    from revl.run import UnsettledWalError  # noqa: PLC0415
    wal = _unsettled_wal(tmp_path / "run.wal")
    with pytest.raises(UnsettledWalError, match="unresolved crossings"):
        _driver(wal)


def test_unsettled_exception_stays_a_runtime_error():
    from revl.run import UnsettledWalError  # noqa: PLC0415
    assert issubclass(UnsettledWalError, RuntimeError)


@needs_cordis
def test_cli_maps_the_driver_exception_to_one_line_exit_1(
        tmp_path, monkeypatch, capsys):
    """The CLI pre-check passes (a race: the WAL settles, then is unsettled
    again before the driver reads it), so the driver's own gate fires; the
    CLI must still end with one error line and exit 1, no traceback."""
    import revl.wal as wal_mod  # noqa: PLC0415
    from revl.__main__ import main  # noqa: PLC0415
    wal = _unsettled_wal(tmp_path / "run.wal")
    source = tmp_path / "app.rvl"
    source.write_text("component C { }\n", encoding="utf-8")
    real = wal_mod.unresolved_crossings
    calls = []

    def first_clean(records):
        calls.append(1)
        return [] if len(calls) == 1 else real(records)
    monkeypatch.setattr(wal_mod, "unresolved_crossings", first_clean)
    code = main(["run", "--once", str(source), "--wal", wal,
                 "--require-settled-wal"])
    err = capsys.readouterr().err.strip().splitlines()
    assert code == 1
    assert len(calls) >= 2
    assert len(err) == 1 and err[0].startswith("error: WAL contains unresolved")


def test_cli_pre_check_still_exits_1_with_one_line(tmp_path, capsys):
    """Regression guard only: the pre-check already behaved this way on the
    base, so this test was never shown failing."""
    from revl.__main__ import main  # noqa: PLC0415
    wal = _unsettled_wal(tmp_path / "run.wal")
    source = tmp_path / "app.rvl"
    source.write_text("component C { }\n", encoding="utf-8")
    code = main(["run", "--once", str(source), "--wal", wal,
                 "--require-settled-wal"])
    err = capsys.readouterr().err.strip().splitlines()
    assert code == 1
    assert len(err) == 1 and "Traceback" not in err[0]


# --- seq guard coverage at the sites #2245 touched ---------------------------

def test_reissue_deferred_seqless_flushed_does_not_settle_a_seqless_descriptor(
        tmp_path):
    wal = tmp_path / "run.wal"
    wal.write_text(json.dumps({"record": "flushed"}) + "\n", encoding="utf-8")
    outcome = runtime.reissue_deferred(
        object(), str(wal), [{"record": "deferred-emission", "call": _CALL}])
    assert outcome == {None: "unresolved"}


def test_unresolved_crossings_seqless_flushed_leaves_a_deferred_emission_owed():
    records = [{"record": "deferred-emission", "call": _CALL},
               {"record": "commit-approved"},
               {"record": "flushed"}]
    assert unresolved_crossings(records) == [
        {"kind": "deferred-emission", "seq": None}]


def test_open_calls_seqless_flushed_does_not_close_a_seqless_descriptor():
    records = [{"record": "deferred-emission", "call": _CALL},
               {"record": "flushed"}]
    assert _open_calls(records) == {None: _CALL}


def test_recover_window_path_seqless_flushed_keeps_the_emission_owed(
        tmp_path, monkeypatch):
    """commit-approved with NO activation-complete is the approved-to-discharged
    window, so `recover` takes `_roll_forward_window` (not `_roll_forward`)."""
    import revl.recovery as recovery  # noqa: PLC0415
    path = str(tmp_path / "window.wal")
    replay.WriteAheadLog(path, ir={}, generation=1).open().close()
    with open(path, "a", encoding="utf-8") as handle:
        for record in ({"record": "commit-approved"},
                       {"record": "deferred-emission", "call": _CALL},
                       {"record": "flushed"}):
            handle.write(json.dumps(record) + "\n")
    reached = []
    real = recovery._roll_forward_window
    monkeypatch.setattr(recovery, "_roll_forward_window",
                        lambda *a, **k: reached.append(1) or real(*a, **k))
    report = recover(path)
    assert reached == [1]
    assert report["residue"]["clean"] is False
    assert report["flushed"] == []
    assert [(o["seq"], o["referent"]) for o in report["owedFlushes"]] == [(None, "s.m")]
