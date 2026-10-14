"""A `requires` key nothing in the composition provides (issue #2386).

The compiler admits it (a host service, a `--providers` model host or a
placement remote may provide it), and `revl_check` answered with every
guarantee passing and said nothing about the key. Adding the component to a
running composition was then refused by the swap health gate as "the successor
fiber is PENDING", without naming the key. `revl_check` now warns with the
unmet key, its service and the fix, without changing `admissible`, and the
swap refusal names the same key.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl.mcp import server as server_mod  # noqa: E402
from revl.mcp.server import handle  # noqa: E402

KV = ("service Kv { fn get(k: Str) -> Str }\n"
      "component Store provides kv: Kv {\n"
      "  provide kv { fn get(k) = k }\n"
      "}\n")
# the recorded slip: the service name used as the requirement key, on the
# component that provides that service itself
AUDIT = ("service Audit { fn record(msg: Str) -> Str\n fn count() -> Int }\n"
         "component AuditLog requires Audit: Audit provides audit: Audit {\n"
         "  let log = effect Map.new() undo log.drop()\n"
         "  provide audit {\n"
         "    fn record(msg) { let k = msg\n effect log.insert(k, msg)\n"
         "      undo log.remove(k)\n return k }\n"
         "    fn count() = log.size()\n"
         "  }\n"
         "}\n")
# a consumer that names the provided service under the wrong key
READER = ("component Reader requires store: Kv provides audit: Audit {\n"
          "  provide audit {\n"
          "    fn record(msg) = store.get(msg)\n"
          "    fn count() = 0\n"
          "  }\n"
          "}\n")
AUDIT_SERVICE = "service Audit { fn record(msg: Str) -> Str\n fn count() -> Int }\n"


def _call(tool: str, arguments: dict) -> dict:
    response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": arguments}})
    return response["result"]["structuredContent"]


@pytest.fixture(autouse=True)
def clean_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    old = server_mod.AUTHORING
    server_mod.set_authoring_trust(roots=(str(ROOT), str(tmp_path)))
    yield tmp_path
    if server_mod.SESSION.loaded:
        server_mod.SESSION.unload()
    server_mod.AUTHORING = old


def test_check_names_a_requirement_nothing_provides():
    checked = _call("revl_check", {"source": KV + AUDIT})
    assert checked["ok"] is True, checked
    self_check = checked["selfCheck"]
    # a warning, not a verdict: the key may come from outside the composition
    assert self_check["admissible"] is True, self_check
    assert self_check["summary"]["pass"] == 9
    assert self_check["unmetRequirements"] == [{
        "component": "AuditLog", "key": "Audit", "service": "Audit",
        "fix": "`AuditLog` already provides `Audit` as `audit`, and a "
               "component does not require the service it provides, so drop "
               "`requires Audit`"}]
    assert "`AuditLog` requires `Audit: Audit`, which nothing in the " \
           "composition provides" in self_check["note"]
    assert self_check["note"].startswith("warning: ")
    assert "would stay PENDING" in self_check["note"]


@pytest.mark.parametrize("example, keys", [
    ("examples/app/notes.rvl", ["webui"]),
    ("examples/placement/gate_consumer.rvl", ["gate"]),
])
def test_an_example_met_outside_the_composition_stays_admissible(example, keys):
    checked = _call("revl_check", {"files": [str(ROOT / example)]})
    assert checked["ok"] is True, checked
    self_check = checked["selfCheck"]
    assert self_check["admissible"] is True, self_check
    assert [r["key"] for r in self_check["unmetRequirements"]] == keys


def test_another_providers_key_is_named_before_dropping_the_requirement():
    # Cache provides Kv itself AND Store provides it: the likely intent is to
    # require Store's key, not to drop the requirement
    cache = ("component Cache requires backing: Kv provides kv: Kv {\n"
             "  provide kv { fn get(k) = k }\n"
             "}\n")
    store = KV.replace("provides kv: Kv", "provides store: Kv") \
              .replace("provide kv {", "provide store {")
    checked = _call("revl_check", {"source": store + cache})
    unmet = checked["selfCheck"].get("unmetRequirements")
    assert unmet and unmet[0]["key"] == "backing", checked
    assert unmet[0]["fix"] == ("`Kv` is provided by `Store` under the key "
                               "`store`, and a requirement is matched by key: "
                               "write `requires store: Kv`")


def test_check_points_at_the_key_the_service_is_provided_under():
    wrong_key = ("component Reader requires Kv: Kv provides audit: Audit {\n"
                 "  provide audit {\n"
                 "    fn record(msg) = msg\n"
                 "    fn count() = 0\n"
                 "  }\n"
                 "}\n")
    checked = _call("revl_check", {"source": KV + AUDIT_SERVICE + wrong_key})
    unmet = checked["selfCheck"].get("unmetRequirements")
    assert unmet and unmet[0]["key"] == "Kv", checked
    assert "`Kv` is provided by `Store` under the key `kv`" in unmet[0]["fix"]
    assert "`requires kv: Kv`" in unmet[0]["fix"]


def test_a_met_requirement_stays_admissible():
    checked = _call("revl_check", {"source": KV + AUDIT_SERVICE
                                   + READER.replace("requires store:",
                                                    "requires kv:")
                                   .replace("store.get", "kv.get")})
    assert checked["selfCheck"]["admissible"] is True, checked
    assert "unmetRequirements" not in checked["selfCheck"]


def test_pending_reason_tells_an_absent_provider_from_one_that_did_not_come_up():
    from revl.mcp.authoring_loop import pending_reason  # noqa: PLC0415

    ir = {"components": [
        {"name": "Store", "requires": {}, "provides": {"kv": "Kv"}},
        {"name": "Reader", "requires": {"kv": "Kv", "Audit": "Audit"},
         "provides": {"audit": "Audit"}},
    ]}
    reason = pending_reason(ir, ir["components"][1], resolved=set())
    assert "`Reader` requires `kv: Kv`, whose provider did not come up" in reason
    assert "`Reader` requires `Audit: Audit`, which nothing in the " \
           "composition provides" in reason
    assert "drop `requires Audit`" in reason


@pytest.mark.skipif(importlib.util.find_spec("cordis") is None,
                    reason="a swap needs the cordis-py runtime: install it "
                           "with `sh backends/python/setup.sh`")
def test_the_swap_refusal_names_the_unmet_key():
    assert _call("revl_load", {"source": KV})["ok"] is True
    refused = _call("revl_edit", {"edits": [{"append": AUDIT}]})
    assert refused["ok"] is False, refused
    message = refused["diagnostics"][0]["message"]
    assert "successor fiber is PENDING" in message
    assert "`AuditLog` requires `Audit: Audit`, which nothing in the " \
           "composition provides" in message, message
    assert "drop `requires Audit`" in message
