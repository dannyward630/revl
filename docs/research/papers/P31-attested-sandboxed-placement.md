---
id: P31
title: Placement Beyond Tier: Capability-Enforced Sandboxes and Hardware-Attested Enclaves as Placement Dimensions
theme: distribution
kind: short
maturity: partial
status: Container-rung sandboxing and the attestation verifier with delivery ledger are shipped and tested on main with synthetic quotes; wasm-cell and microVM rungs do not host components, and no overhead or real-hardware quote exists.
fused_with:
---

## Pitch

A composition language can say, in the same placement file that picks a runtime and a machine, "this component runs inside a kernel-enforced box with no network" or "this component runs only on a peer that proves, with a pinned hardware root, that it is the approved build in an approved enclave", and the plan is refused before anything starts if the declaration or the proof does not hold.

## Abstract

Placement systems usually decide where a component runs (which runtime, which machine). Security properties are a separate concern, checked by a different tool, if at all. We treat two security properties as placement dimensions of the same kind as tier and machine. The first is isolation: a process can be placed in a wasm cell, a container or a microVM with a filesystem and network envelope that defaults to deny, composed with unsandboxed processes over the existing cross-process seam. The envelope is checked at plan time against the component's declared needs, but we state plainly that this check is advisory because host code bodies are opaque; the security boundary is the runtime envelope, and a boot canary probes the boundary from inside and refuses the placement if a should-be-denied attempt succeeds. The seam crosses the container boundary over mutual TLS and a relay that holds no key. The second dimension is attestation: a process may require that its host prove, by a TDX Quote v4 or an SEV-SNP report verified with pure-Python ECDSA up to an operator-pinned root, that it runs an approved bundle with a permitted measurement, and results come back only through a single delivery ledger bound to that admission. We give the refusal catalogue (every refusal named, 23 committed quote fixtures, forged cases re-signed rather than corrupted) and the limits: the container rung hosts only Python components today, the wasm-cell and microVM rungs verify their boundary and then refuse to host, the isolation runtime is a trusted enforcer, the envelope covers filesystem and network only, and the fixtures are not vendor-issued quotes. We report no performance numbers.

## Problem and claim

Existing capability systems in this lineage check a declared envelope and then trust the host code body. revl's own threat model lists "the gate does not sandbox host code" as a non-goal (`docs/threat-model.md:119`; the design note cites it at `docs/design/411-sandbox-placement.md:46`). The check and the enforcement live in different layers. Remote attestation systems have the opposite shape: they prove a fact about a machine and leave the decision of what to do with it to the application.

The claim of this paper is narrow. Putting isolation and attestation into the placement vocabulary has three concrete effects that can be checked in the tree: a plan whose declared needs exceed the grant, whose isolation rung cannot be established, or whose attestation does not verify to a pinned root is refused by name before any process runs; the refusal direction is intended to be uniform (the drivers refuse rather than start a sandboxed process unconfined, and admission is refused on an unverified claim, as the refusal tests pin); and the same placement file composes sandboxed and ordinary processes over one seam. Attestation is a peer admission requirement; no test composes it with a sandboxed process over the seam.

We do not claim that the sandbox is escape-proof, that the plan-time gate proves anything about opaque bodies, or that the attestation chain reaches a real vendor certificate. Each of these is in the limits section and in the design notes' own text.

## Contributions

1. An isolation ladder (wasm-cell, container, microvm) under one manifest surface, where the envelope defaults to deny and an unmappable declaration is a plan-time refusal rather than a silent downgrade (`docs/design/411-sandbox-placement.md:706-734` for the ladder; the unmappable-needs refusal is at `docs/design/411-sandbox-placement.md:485-488` and `docs/design/411-sandbox-placement.md:924`).
2. A two-layer capability model: a runtime layer that enforces filesystem and network resources, and an explicitly advisory plan-time gate over an author-declared needs table (`docs/design/411-sandbox-placement.md:172-232`).
3. A seam transport across the container boundary: TCP with mutual TLS over a per-process seam-only internal network, through a conductor-owned relay that is a blind byte forwarder holding no certificate or key, with a seam-only canary that confirms the transport from inside (`src/revl/seam_relay.py:1-30`, `src/revl/sandbox_runtime.py:621`).
4. A boot canary that reads the kernel from inside the boundary, with an active egress probe, so that a daemon that applies less than requested is detected and the placement refused at boot (`src/revl/sandbox_runtime.py:88-175`; the canary reports and the driver refuses, it does not kill a process).
5. `requires attested_tee` as a fourth placement dimension: a typed requirement, a fail-closed verifier with a named refusal for every gate, and verification of Intel TDX Quote v4 and AMD SEV-SNP reports with pure-Python ECDSA P-256 and P-384 to an operator-pinned root that the placement file cannot name (`docs/tee-attestation-root.md:1-110`, `src/revl/tee_attestation.py:818`).
6. A single delivery ledger: an admission yields an `AttestedRun`, and a result can enter only through it, with the receipt key bound into the attested evidence body (`docs/attested-result-delivery.md:1-60`, `src/revl/tee_attestation.py:1195`).
7. A fenced development verifier: the symmetric-MAC path survives as `DevMacRoot`, which requires `acknowledged_dev_only=True`, labels every verdict it reaches, and is refused outright when a hardware root is required (`docs/tee-attestation-root.md:118-140`, `src/revl/tee_quote.py:1149`).

## Related work

| prior system or line of work | what it does | what revl does differently |
|---|---|---|
| gVisor, Firecracker (microVM monitor), Docker seccomp and `--network=none` | Give an operator an isolation primitive per container or VM. The operator decides what to run in it. | The isolation is a column in the placement file next to tier and machine, derived from the composition, and a composition with a sandboxed component still wires it to unsandboxed ones over a checked seam. The composition refuses at plan time when the declared needs exceed the grant. |
| Wasmtime and WebAssembly component sandboxing, Cloudflare Workers isolates | Confinement by construction: no import, no capability. | revl already uses this for its quarantine tier (`docs/quarantine-tier.md:1-60`). The wasm cell is one rung of a ladder and the manifest word is shared with the heavier rungs; the cell refuses what the container reports (opaque reach) rather than quietly meaning something weaker. |
| Fuchsia component sandbox, Landlock, Deno permission flags | Declared capabilities enforced by the OS or runtime per component or process. | The declared set here is a static IR-derived reach (the G4 fixed point) for key-named capabilities, with an explicit split between seam-served capabilities (no OS grant needed) and host-rooted ones (need an OS grant). The needs table for host-rooted ones is an unverified author claim. |
| Intel TDX and AMD SEV-SNP attestation, Intel SGX remote attestation, Azure Attestation, Confidential Containers (citation to be checked) | Produce and verify evidence about an enclave. Verification is a service or a library; policy is the application's. | Verification and policy are one placement word. A requirement names bundle, permitted measurements, region and network posture; the verdict is the verifier's own reason string; a result may only arrive through the run that the admission opened. |
| RATS architecture (RFC 9334) | Defines attester, verifier and relying party roles and evidence/result formats. | revl's verifier lives inside the relying party's placement step, with a pinned root as operator configuration and no placement-file key for it. Mapping to RFC 9334 terms is a writing task, not an implementation claim. |
| Marlin, Occlum (enclave runtimes) (citation to be checked) | Run an application inside an enclave. | They do not decide placement across a heterogeneous composition; revl treats the enclave as one admission condition on a peer. |

## Evidence on main

Test counts are `def test_` functions per file and do not count parametrization. No test was run for this draft.

| claim | path:line or test | status | note |
|---|---|---|---|
| Sandbox is a manifest surface (`[processes.<p>.sandbox]`, `[sandbox]` sugar, `[sandbox.needs]`), default deny, tier-form sugar splits into `sandbox_<component>` | `src/revl/placement.py:480` (`expand_tiers`); `tests/test_sandbox_placement_411.py` (65 tests, e.g. `test_sandbox_sugar_splits_component_into_its_own_process`, `test_envelope_defaults_to_deny_all`, `test_no_sandbox_is_byte_identical_expansion`) | shipped | the design note quotes older line numbers; current code is at line 480 |
| Plan-time gate is advisory and refuses declared mismatches and out-of-vocabulary needs | `src/revl/placement.py:1532` (`sandbox_capability_gate`); tests `test_gate_net_need_against_no_net_is_refused`, `test_gate_missing_needs_entry_is_admitted_advisory_default`, `test_gate_out_of_vocabulary_need_is_fail_closed` in `tests/test_sandbox_placement_411.py` | shipped | the missing-entry test pins the advisory limit |
| Structural refusal of resource-typed values crossing a sandboxed seam | `src/revl/placement.py:1676` (`sandbox_crossing_check`); test `test_crossing_an_unresolvable_type_fails_closed` and a field-path naming test | shipped | |
| Container rung: envelope to flags (`--network=none`, `--read-only`, `--cap-drop=ALL`, no-new-privileges), preflight, canary, teardown, py runner inside | `src/revl/sandbox_runtime.py:341` (`container_flags`), `src/revl/sandbox_runtime.py:857` (`ContainerDriver`); `tests/test_sandbox_container_rung_411.py` (64 tests, e.g. `test_net_none_derives_a_network_namespace_with_no_egress`, `test_an_open_egress_refuses`, `test_a_writable_root_filesystem_refuses`) | shipped for py components | `test_a_non_py_backend_in_a_container_refuses`: other backends refuse. Whether the live tests ran green is not established; they are gated on a docker runtime (`test_the_docker_gate_is_read_bare_and_carried_by_the_live_tests` in `tests/test_sandbox_seam_transport_411.py:498`) |
| Active egress canary, not an interface list | `src/revl/sandbox_runtime.py:137` (the `_EGRESS_PY` probe to TEST-NET-1) and the comment at `src/revl/sandbox_runtime.py:115-135` | shipped | the comment gives the reason: a `--network=none` namespace still shows address-less tunnel stubs |
| Seam across the container boundary over a relay that holds no key | `src/revl/seam_relay.py:1-30`; `src/revl/sandbox_runtime.py:621` (`SeamRelayManager`); `tests/test_seam_relay_411.py` (`test_the_relay_imports_nothing_outside_the_standard_library`, `test_the_relay_forwards_bytes_both_ways_blindly`), `tests/test_sandbox_seam_transport_411.py` (`test_the_seam_only_canary_confirms_the_boundary_from_inside`, `test_a_sandbox_on_the_bridge_fails_the_isolation_clause`) | shipped | live ones need docker |
| Approval request from inside a sandbox reaches the operator through the conductor | `src/revl/placement.py:1415` (`sandbox_approval_rows`); `test_the_approval_channel_round_trips_from_a_sandbox` (`tests/test_sandbox_seam_transport_411.py:423`) | shipped | |
| wasm-cell rung: substrate verified in-cell, then refuses to host a component | `src/revl/sandbox_runtime.py:1362` (`evaluate_cell`), `src/revl/sandbox_runtime.py:1410` (`WasmCellDriver`, docstring "is item 411 Stage 4, not built"); `tests/test_sandbox_wasmcell_rung_411.py` (18 tests) | partial | hosting a component in a cell is not built |
| microVM rung: gated on /dev/kvm, boots and confirms the boundary in-VM, then refuses to host | `src/revl/sandbox_runtime.py:1841` (`MicroVMDriver`), refusal text at `src/revl/sandbox_runtime.py:1918-1937`; `tests/test_sandbox_microvm_rung_411.py` (25 tests) | partial | the module docstring says the live boot is verified on a hosted KVM lane; that lane's result cannot be confirmed from the tree |
| Quarantine tier: candidate runs in a wasm sandbox before admission; verdicts passed, trapped, timeout, rejected, deferred | `docs/quarantine-tier.md:1-60`; `src/revl/mcp/quarantine.py:38-60`; `tests/test_quarantine.py` (20 tests) | shipped (v1), skips cleanly without the wasm toolchain | |
| TDX Quote v4 and SEV-SNP report verified with ECDSA P-256 and P-384 to a pinned root | `src/revl/tee_quote.py:476` (`ecdsa_verify`), `src/revl/tee_quote.py:1066` (`HardwareRoot`), `src/revl/tee_quote.py:1397` (`verify_quote`); `tests/test_tee_quote.py` (31), `tests/test_tee_hardware_root.py` (41) | shipped (with synthetic quotes) | the doc says the fixtures "are not Intel- or AMD-issued quotes" (`docs/tee-attestation-root.md:269-272`) |
| `report_data` binds the evidence body; stated measurement is compared to the hardware register | `docs/tee-attestation-root.md:42-64`; `src/revl/tee_attestation.py:494` (`evidence_report_data`); test `test_a_permitted_measurement_the_hardware_does_not_report_is_refused` (`tests/test_tee_hardware_root.py:238`) | shipped | |
| Debug-enabled TD or guest refused unless root built with `permit_debug=True` | `src/revl/tee_quote.py:1477`, `src/revl/tee_quote.py:1515`; test `test_a_debuggable_td_is_refused_however_well_it_is_signed` (`tests/test_tee_hardware_root.py:284`) | shipped | |
| Fail-closed verifier with ten ordered gates, replay ledger, refused proof does not burn the challenge | `src/revl/tee_attestation.py:818-960`; tests `test_a_consumed_challenge_is_refused_the_second_time`, `test_a_refused_proof_does_not_burn_the_challenge` (`tests/test_tee_hardware_root.py:293`, `:302`); `tests/test_tee_attestation.py` (73) | shipped | |
| Placement-file spelling (`[processes.<p>.attest]`), no key for a root | `docs/attested-tee-placement.md:1-80`; `src/revl/placement.py:875` (`parse_tee_requirement`), `src/revl/placement.py:1010` (`admit_peer_for_process`); `tests/test_placement_attested_tee.py` (44) | shipped | |
| One delivery ledger; receipt key bound into the attested body | `docs/attested-result-delivery.md:1-60`; `src/revl/tee_attestation.py:1195` (`AttestedRun`), `src/revl/tee_attestation.py:1261` (`open_attested_run`), `src/revl/tee_attestation.py:1181` (`receipt_key_binding`); `tests/test_tee_result_delivery.py` (45) | shipped | |
| Dev MAC root labelled and refused when hardware required | `src/revl/tee_quote.py:1149-1200` (`DevMacRoot`, `DEV_ROOT_NOTE`, `require_production_root`); `test_requiring_a_hardware_root_refuses_the_development_verifier_outright` (`tests/test_tee_hardware_root.py:457`) | shipped | |
| Vendor DER certificate chain | `docs/tee-attestation-root.md:278-298` (listed as still open) | designed only | a one-hop `PlatformEndorsement` stands in |

## Numbers that exist

- 23 committed quote fixtures and 4 endorsement fixtures, with the verdict each must reach listed in `tests/fixtures/tee/manifest.json` (counted from the JSON keys; `docs/tee-attestation-root.md:263` says 23). Forged cases are re-signed, not byte-flipped.
- Test function counts are listed in the table above; the sum over the sandbox and TEE files named there is 443 `def test_` functions, and parametrized cases add more. These are test counts, not a coverage claim.
- Timing: `tools/ecdsa_timing_demo.py`, one loaded machine, measured the pure-Python signer about 8% slower on high-weight nonces and the OpenSSL-backed signer within 0.3% (`docs/tee-attestation-root.md:256-260`). The doc calls this a demonstration of the difference, not a proof and not a test. Signing is not the attestation-verification path, so this is a side remark at most.
- Launch cost for the rungs: the design note gives "~100ms-1s launch" for the container as an estimate (`docs/design/411-sandbox-placement.md`, ladder table). It is not a measurement. No measured numbers for any rung exist in the tree.

## Paper outline

1. Introduction. Placement decides where; security is usually elsewhere. The gap between auditing host reach and enforcing it.
2. Background. The placement file, the seam, G4 capability reach, the G8 audit surface.
3. Isolation as a placement dimension. Manifest surface, ladder, default deny, refusals that name the gap. The two capability layers and why the plan-time gate is advisory.
4. Crossing the boundary. Seam over mTLS through a blind relay; the canary; the approval channel.
5. Attestation as a placement dimension. The requirement, the ten gates, the pinned root, `report_data` binding, debug refusal, the fenced development verifier, the delivery ledger.
6. Evaluation. Refusal catalogue (fixtures), escape-attempt table, overhead numbers (if produced).
7. Limits and related work.

## Threats to validity and limits

- The isolation runtime is a trusted enforcer. The design says revl "cannot verify the daemon applied" the flags; the canary "probes examples, not the policy: detection of gross non-enforcement, not verification of the enforcer" (`docs/design/411-sandbox-placement.md:567-600` region).
- The envelope vocabulary is filesystem and network only. Environment, exec, ipc and device authority are not enforced; an env-injected secret survives every flag, which is why spec narrowing is a stage-1 requirement (same note, surface section).
- The plan-time gate is advisory. A missing or understated `[sandbox.needs]` entry defaults to "needs nothing" and is admitted. Net allowlists ("only api.example.com") are not offered; `net` is `none` or `all`.
- Confinement bounds reach, not misuse of granted reach: a sandboxed component can still leak through the seam-served `log` key. That residual belongs to information-flow work and to composition policy.
- Only Python components run in a container today. Wasm-cell and microVM drivers verify their boundary and then refuse to host. The paper must not be read as if all three rungs host components.
- Attestation fixtures are synthetic. The doc says what a genuine quote needs (a per-platform key chained to a live vendor service) and that the fixtures prove the parser and the root logic, not a vendor relationship. The `bundle` field is a label; no hardware format measures it, so the operator's permitted-measurement set carries the meaning.
- `report_data` binds what the workload said; the measurement comparison against the hardware register is what makes that safe, and that is the one place a reviewer will push.
- Pure-Python curve arithmetic is not constant-time; verification inputs are public so this is harmless there, and signing has a `revl[crypto]` backend. The verifier is not a constant-time implementation.
- Whether the docker-gated live tests (`tests/test_sandbox_seam_transport_411.py`, `tests/test_sandbox_container_rung_411.py`) were green on any commit is not established by the tree.
- Prior-art positioning against commercial confidential-computing stacks is from general knowledge and not checked.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 27 checked, 6 corrected.
