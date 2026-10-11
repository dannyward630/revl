"""`revl_check` says where the held source stands against disk (issue #2241).

After a commit that has not been exported, `revl_check {session: true}` (the
usual verification call) answered `ok: true` with no disk state, and
`revl_check {files: [path]}` compiled the stale file on disk and answered
green, so commit-then-check read as done while the file was unchanged. The
check now carries the same `disk` block and export note the change loop does
(#2032), and a `files` check of a held, differing file says it read disk.
A cold check, with nothing loaded, is unchanged.
"""

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl.mcp import server as server_mod  # noqa: E402
from revl.mcp.server import handle  # noqa: E402

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("cordis") is None,
    reason="the change verbs boot a composition and need the cordis-py runtime "
           "— install it with `sh backends/python/setup.sh`")


def _call(tool: str, arguments: dict) -> dict:
    response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": arguments}})
    return response["result"]["structuredContent"]


@pytest.fixture(autouse=True)
def clean_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    old = server_mod.AUTHORING
    server_mod.set_authoring_trust(roots=(str(tmp_path),))
    yield tmp_path
    if server_mod.SESSION.loaded:
        server_mod.SESSION.unload()
    server_mod.SESSION.pending_draft = None
    server_mod.SESSION.draft = None
    server_mod.AUTHORING = old


@pytest.fixture
def tenants(clean_session):
    path = clean_session / "tenants.rvl"
    shutil.copy(ROOT / "examples" / "tenants.rvl", path)
    return path


def _committed(path: Path) -> None:
    assert _call("revl_load", {"files": [str(path)]})["ok"]
    assert _call("revl_change", {"withdraw": {"component": "TenantAStore",
                                              "cascade": True}})["ok"]
    assert _call("revl_change", {"commit": True})["ok"]


def test_session_check_after_commit_reports_stale_disk(tenants):
    """(a) the verification call no longer reads as done over unchanged disk."""
    _committed(tenants)
    out = _call("revl_check", {"session": True})
    assert out["ok"] is True
    assert out["disk"]["inSync"] is False
    assert out["disk"]["stale"] == [str(tenants)]
    assert "revl_export" in out["note"]


def test_files_check_after_commit_says_it_read_disk(tenants):
    """(b) the stale file compiles green, and the answer says disk differs."""
    _committed(tenants)
    out = _call("revl_check", {"files": [str(tenants)]})
    assert "differs from the session's held source" in out["note"]
    assert "revl_export" in out["note"]
    # one coherent note: the ride's own export note did not replace or join it
    assert out["note"].count("revl_export") == 1
    assert out["disk"]["inSync"] is False


def test_session_check_after_export_is_in_sync(tenants):
    """(c) once exported the check reports in sync and carries no export note."""
    _committed(tenants)
    assert _call("revl_export", {})["ok"]
    out = _call("revl_check", {"session": True})
    assert out["disk"] == {"inSync": True, "stale": []}
    assert "revl_export" not in (out.get("note") or "")
    files = _call("revl_check", {"files": [str(tenants)]})
    assert "revl_export" not in (files.get("note") or "")


def test_cold_files_check_is_unchanged(tenants):
    """(d) nothing loaded: no `disk` block and no note, as before."""
    out = _call("revl_check", {"files": [str(tenants)]})
    assert out["ok"] is True
    assert "disk" not in out
    assert "note" not in out


def test_unrelated_file_and_scratch_checks_carry_disk_without_export_note(
        tenants, clean_session):
    """A check of something the session does not hold is advice about that
    candidate, not about the held source: it gets `disk`, not the export note."""
    _committed(tenants)
    other = clean_session / "other.rvl"
    other.write_text("service S { fn f() -> Int }\n"
                     "component C provides s: S { provide s { fn f() = 1 } }\n",
                     encoding="utf-8")
    for args in ({"files": [str(other)]},
                 {"source": other.read_text(encoding="utf-8")}):
        out = _call("revl_check", args)
        assert out["disk"]["inSync"] is False
        assert out["disk"]["stale"] == [str(tenants)]
        assert "revl_export" not in (out.get("note") or "")
