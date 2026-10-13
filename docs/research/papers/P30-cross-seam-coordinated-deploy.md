---
id: P30
title: Attested Deploy and Coordinated Rollback Across Seams, With a Machine-Boundary Refusal
theme: distribution
kind: full
maturity: partial
status: Attestation chain, coordinated prepare/commit/abort, boundary taxonomy and federation are shipped and tested on main; the SSH leg is tested through shims only and there is no fault-injection evaluation or replicated coordinator.
fused_with: P29
---

## Pitch

An in-process rollback theorem does not cross a process seam, so a deploy tool should re-hash on the receiver, coordinate per-process rollback honestly, and refuse the machine boundary it cannot yet protect.

## Abstract

Deployment tools usually apply a change and report success. When the change is a reactive composition split across processes, the guarantee a single process gives (LIFO rollback with a residue proof) does not extend to the whole: a peer's inverses live in the peer. We describe `revl deploy`, which separates what it guarantees from what it does not. It guarantees the chain: the receiver re-hashes source, IR, capability policy and runtime evidence against its own disk and checks the signature under a key the receiver itself holds (HMAC, so verification is only meaningful inside one trust domain), and a COMMIT receipt re-measures the loaded bytes at load time. It guarantees per-process residue freedom on the abort path, which is modelled and proved in Lean (R4, `formal/RevL/Theorems/R4_NoResidue.lean`). It does not guarantee cross-process atomicity as one theorem, so the coordinator runs prepare, commit and abort over per-process-atomic units, writes the abort decision durably first, and reports an unreachable peer as unresolved, never rolled back. A boundary taxonomy (process, container, machine) fixes what teardown is worth across each, and a machine boundary is opened only under a pinned SSH host key. Irreversible crossings are held until a durable federation-commit marker exists, and plans that cannot be held are refused. Py and node seams carry sealed correlation envelopes, with replay refusal keyed on mutual-TLS identity. We present the design, the executed suites (83 test functions in `tests/test_deploy_118.py`, 11 hostile-wire test functions) and the explicit non-goals: no replicated WAL, no quorum coordinator, and symmetric signatures only inside one trust domain.

## Problem and claim

Rolling out a composition across processes or hosts fails in a specific way: the coordinator cannot undo what a peer did, and a lying or vanished peer is indistinguishable from a slow one. Tools that report "rolled back" for a peer they cannot reach overclaim.

Claim: an incremental path to cross-host rollback is honest if each step states its ceiling. Admission is evidence re-derived on the receiver, rollback is coordinated over per-process units that each own their inverses, and every boundary the system cannot protect is refused by name. The paper claims this discipline and its mechanisms, not a distributed commit protocol.

## Contributions

1. Attested admission: the receiver re-hashes artifacts and ignores self-declared hashes (`SELF_DECLARED_IGNORED`); chain links refuse by name (`docs/deploy.md:38-95`).
2. A load-measured COMMIT receipt and a hard conductor comparison that closes the PREPARE/COMMIT TOCTOU window (`docs/deploy.md:164-208`, `src/revl/deploy.py:1211`, `src/revl/deploy.py:1279`).
3. A coordinated protocol over per-process-atomic units: abort written durably first, reverse-ledger-order ABORT messages, outcomes `never-committed / applied / rolled-back-clean / rolled-back-with-residue / unresolved` (`docs/deploy.md:352-388`, `src/revl/deploy.py:3123`).
4. A boundary taxonomy with a teardown promise per boundary, the machine boundary refused unless a host key is pinned (`docs/deploy.md:485-528`, `src/revl/deploy.py:4085-4140`).
5. Federation: irreversible crossings deferred behind a durable commit marker, a non-deferrable crossing refused at plan time, stranded participants settled by the existing recovery rule or failed closed (`docs/deploy.md:389-443`, `src/revl/deploy.py:3440`, `src/revl/deploy.py:3615`).
6. Seam hardening: sealed HMAC correlation envelope on py and node bridges, replay freshness keyed on handshake-proved mTLS identity, resource crossings refused, wire kind resolved against declared cases, a hostile-wire TCK (`CHANGELOG.md:397-415`, `CHANGELOG.md:492-495`, `tests/test_hostile_wire_tck.py`).

## Related work

| prior system or line of work | what it does | what revl does differently |
|---|---|---|
| Kubernetes rollouts, Spinnaker | health-gated rollout, rollback by redeploying the old version | rollback is each participant's own LIFO inverse with a residue proof; unreachable peers are reported unresolved |
| Terraform | plan and apply with state file | admission re-derives evidence on the receiver; no desired-state diff |
| Two-phase commit, Paxos Commit (citation to be checked) | atomic commit with a coordinator log | here the coordinator holds no inverses and no replicated log yet; the limits are stated |
| Sagas (citation to be checked) | compensating actions per step | compensations are derived inverses owned by the participant |
| Temporal | durable workflow execution | the durable decision entry is minimal; no workflow engine |
| Nix deploy-rs / NixOps | hash-addressed closures pushed over SSH | receiver re-hash plus signed load-time receipt; pinned host key mandatory |
| in-toto, SLSA (citation to be checked) | signed supply-chain metadata | chain bound to capability policy and runtime evidence, verified on the receiving disk |

## Evidence on main

| claim | path:line or test | status | note |
|---|---|---|---|
| attestation chain, admission re-hash | `docs/deploy.md:38-95`; `tests/test_deploy_118.py` (83 test functions) | shipped | |
| receipts signed | `docs/deploy.md:139-163` | shipped, HMAC-SHA256 | the signature is symmetric and cross-domain use is refused until an Ed25519 upgrade (`docs/deploy.md:139-146`); HMAC-SHA256 is named at `docs/deploy.md:150` |
| load-measured COMMIT receipt | `tests/test_deploy_commit_receipt_118.py`, `tests/test_deploy_commit_runner_118.py` | shipped | |
| coordinated PREPARE/COMMIT/ABORT | `docs/deploy.md:352-388`; `src/revl/deploy.py:3123` (run_deploy) | shipped | |
| runner as a real process | `tests/test_deploy_runner_process_118.py` (12 tests) | shipped | stdio, local child |
| `via = ssh` leg with pinned host key | `src/revl/deploy.py:4116-4127`, scp staging and `known_hosts` pin at `src/revl/deploy.py:2455-2513`; `tests/test_deploy_ssh_command_118.py`, `tests/test_deploy_ssh_transport_118.py` | shipped against shims, status contested | tests use a fake `ssh` and `scp` shim on one disk, no live remote. `docs/deploy.md:550-560` still lists the SSH seam as "not landed", while the code and the MCP docstring call it landed |
| machine boundary refused without pinned key | `src/revl/deploy.py:4121-4140`; `docs/deploy.md:485-528` | shipped | |
| container boundary participant | `docs/deploy.md:529-548` | shipped | a seam-carrying container target is still refused (`docs/deploy.md:556-558`) |
| federation commit, stranded settle | `docs/deploy.md:389-443`; `src/revl/deploy.py:3440`, `src/revl/deploy.py:3615` | shipped | `tests/test_deploy_118.py` and `tests/test_deploy_map_118.py` reference `federation_admission` and `settle_stranded`; those tests were not read line by line |
| MCP `revl_deploy` | `src/revl/mcp/deploy.py:1-30`; `tests/test_mcp_deploy_476.py`; `src/revl/mcp/operator.py:134-149` | shipped | rehearsal default verified (`apply` absent or false mutates nothing). The approval gate is injected as a callable and was not traced; no quorum or drift check on this verb was found, only the operator grant |
| distributability audit | `docs/interop-bridge.md:346-360`; `src/revl/distribute.py`; `tests/test_distribute.py` | shipped | |
| seam deadlines | `docs/seam-deadlines.md:113-131`; `src/revl/placement.py:94-98`, `src/revl/placement.py:1173` | partial | the doc lists the py runner wiring, a TCK clause and the fault-sweep mode as not built |
| hostile-wire TCK | `tests/test_hostile_wire_tck.py` (11 tests) | shipped | |
| replicated WAL, quorum coordinator | `docs/deploy.md:560-568` | not built | stated by the doc |
| hardware attestation | `docs/deploy.md:568` | not built | out of scope |

## Numbers that exist

- Test function counts: 83 (`tests/test_deploy_118.py`), 12 (`tests/test_deploy_runner_process_118.py`), 11 (`tests/test_hostile_wire_tck.py`). These are function counts for those files only, not the whole deploy suite, and not pass rates; no test was run for this draft.
- No latency, overhead or failure-injection statistics in the cited docs.

## Paper outline

1. Introduction: the rollback theorem stops at the process.
2. What the deploy guarantees and does not (the three-way split).
3. The attestation chain and receiver re-hash; the load-measured receipt.
4. Coordinated protocol and outcome algebra.
5. Boundaries and their teardown promises; refusing the machine boundary.
6. Federation and deferred irreversible crossings.
7. Seam hardening and the hostile-wire TCK.
8. Evaluation (to be built).
9. Related work, limits.

## Threats to validity and limits

- The deploy does not guarantee cross-process atomicity as one theorem and does not defend against a lying receiver: a signed lie is detectable and non-repudiable, not impossible (`docs/deploy.md:25-36`).
- Symmetric signatures: a verifier that can check can forge; fine inside one trust domain only. The paper cannot claim cross-domain deploy.
- No replicated WAL, no partition-safe coordinator (`docs/deploy.md:560-568`). A machine that disappears takes the accumulator, closures and WAL with it; the only verdict is unresolved.
- R4 is proved for the abort path only (`formal/STATUS.md:69`).
- A container target that carries a seam is not supported yet.
- The SSH leg is tested through shims in the cited tests.
- The federation tests exist but were not read line by line.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 60 checked, 6 corrected.
