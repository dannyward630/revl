"""Approval metadata attributes host bodies to the source that declared them.

An MCP composition includes operator-sanctioned provider modules as well as the
candidate sent by the agent. Those provider bodies are part of the merged IR,
but must not be described on the approval ticket as agent-authored host code
(issue #2631).
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

from revl.mcp import server  # noqa: E402


_OPERATOR_PROVIDER = (
    "pub extern pure fn operator_helper(x: Str) -> Str = @py { return x }\n"
)

_CANDIDATE_MODULE = (
    "pub extern pure fn candidate_helper(x: Str) -> Str = @py { return x }\n"
)

_CANDIDATE = (
    'use "operator-provider-2631.rvl" { operator_helper }\n'
    'use "candidate-helper-2631.rvl" { candidate_helper }\n'
    "extern pure fn candidate_root(x: Str) -> Str = @py { return x }\n"
    "service S { fn f(x: Str) -> Str }\n"
    "component C provides s: S {\n"
    "  provide s { fn f(x) = operator_helper(candidate_helper(candidate_root(x))) }\n"
    "}\n"
)


@pytest.fixture(autouse=True)
def _trusted_server(monkeypatch, tmp_path):
    from revl.mcp.session import Session

    previous_authoring = server.AUTHORING
    previous_bodies = server._AUTHORED_HOST_BODIES
    monkeypatch.setattr(server, "SESSION", Session())
    monkeypatch.setattr(server, "_AUTHORED_HOST_BODIES", [])
    server.set_authoring_trust(
        host_code=True,
        granted=None,
        providers={os.path.abspath("operator-provider-2631.rvl"):
                   _OPERATOR_PROVIDER},
        roots=(str(tmp_path),),
    )
    yield
    server.AUTHORING = previous_authoring
    server._AUTHORED_HOST_BODIES = previous_bodies


def test_candidate_host_body_metadata_excludes_operator_provider_bodies():
    """The provider body remains in the composition but is not agent code."""
    candidate_module = os.path.abspath("candidate-helper-2631.rvl")

    ir = server._compile(_CANDIDATE, None,
                         {candidate_module: _CANDIDATE_MODULE})

    merged = {entry["name"] for entry in ir["externs"] if entry.get("bodies")}
    authored = {entry["extern"] for entry in server._AUTHORED_HOST_BODIES}
    assert merged == {"candidate_helper", "candidate_root", "operator_helper"}
    assert authored == {"candidate_helper", "candidate_root"}


def test_load_approval_ticket_names_only_candidate_host_bodies(monkeypatch):
    """The load path uses the same per-source report when it shapes a ticket."""
    from revl.mcp.approval import ApprovalRequired

    candidate_module = os.path.abspath("candidate-helper-2631.rvl")
    modules = {candidate_module: _CANDIDATE_MODULE}
    report = {}
    ir = server.compile_under_authoring(_CANDIDATE, None, modules=modules,
                                        report=report)
    ticket = {"hash": "sha256:test", "capabilities": []}

    def load_requires_approval(*_args, **_kwargs):
        raise ApprovalRequired(ticket)

    monkeypatch.setattr(server.SESSION, "load", load_requires_approval)
    result = server._boot(ir, _CANDIDATE, modules, None, True, {},
                          compile_report=report)

    assert result["approvalRequired"] is True
    assert {entry["extern"] for entry in result["ticket"]["unreviewedHostCode"]} == {
        "candidate_helper",
        "candidate_root",
    }


def test_virtual_draft_compile_returns_host_source_provenance():
    """Draft loads pass the exact compile report into the ticket builder."""
    from revl.mcp import edit

    candidate_module = os.path.abspath("candidate-helper-2631.rvl")
    provider_module = os.path.abspath("operator-provider-2631.rvl")
    modules = {
        candidate_module: _CANDIDATE_MODULE,
        provider_module: _OPERATOR_PROVIDER,
    }
    report = {}
    working_set = {"source": _CANDIDATE, "modules": modules}
    ir = edit.compile_virtual(working_set, report=report)

    authored = server._authored_host_bodies(
        ir, _CANDIDATE, modules, report=report)
    assert {entry["extern"] for entry in authored} == {
        "candidate_helper",
        "candidate_root",
    }
