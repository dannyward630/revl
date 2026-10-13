---
id: P60
title: "Self-Extending Runtime: A Component Proposes a Component, the Embedded Compiler Decides, Failed Health Reverts Residue-Free"
theme: agents
kind: full
maturity: partial
status: Python tier ships Gate.propose with a health-gated swap and named tests; the Rust host cannot swap, re-entrant propose is refused, and no live-model evaluation or performance measurement exists.
fused_with: P59, P61
---

## Pitch
A running program can ask a model for a replacement of one of its own components, have its embedded compiler admit it under a profile in which the author cannot introduce host code or choose its own authority address, hot-swap it with state migration, and revert to the previous generation if the successor is not healthy.

## Abstract
Hot code upgrade is mature (Erlang/OTP releases, blue-green and canary deployment), and so is automated program repair. Combining them for code written by an untrusted generator raises problems neither literature covers: the swap verb in a runtime assumes its caller already trusted the code, and the admission verb assumes the code is additive. We describe `Gate.propose` in revl, a verb that sits in the gap. A candidate is compiled standalone under an untrusted-author profile that forbids new host-code declarations, transitive reach to host code, ungranted services and self-chosen realm placement; a granted set naming the decider is refused before compiling; the swap runs through a post-activation health gate that treats any non-clean activation, including the two non-raising ones (a failed fiber, an unmet requirement), as a rejection and reverts to the previous generation. Live state migrates only across declared, typed channels, and a halted session is reported as halted rather than as a revert. Review of the design found that a name-keyed standing approval could be inherited by a successor that reuses a component name, and that a stale handle could dispatch into the successor; both are closed and tested. The Python tier carries a 24-function test file for the core path and 5 for name substitution. We state the open parts: the Rust tier decides but cannot swap, re-entrant propose is refused rather than supported, host code in granted providers stays trusted, and no live-model campaign has been measured.

## Problem and claim
In most runtimes, replacing a component is a privileged operation done by a human who reviewed the code. In revl the two relevant verbs partition the space wrongly for self-extension: `Session.admit` applies the untrusted-author profile but is additive and refuses replacement, while `Session.swap` replaces a composition but runs the full compiler (`docs/design/334-self-extending-runtime.md:148-200`). The obvious composition, admit then swap, re-opens the host-code escape the profile exists to close.

A second problem is the failure semantics of the swap. An adversarial review found that a successor that fails to activate (a fiber left FAILED, or a requirement left PENDING) did not trigger the rollback, because activation faults are deliberately non-raising; the runtime would serve a broken generation N+1 with generation N already disposed (`docs/design/334-self-extending-runtime.md:34-57`). The headline "reverts to generation N" was false for the general fault until a post-activation health gate was added.

Claim: composing standalone untrusted-profile admission, a forbidden-grant refusal, a health-gated swap with typed state migration, and bindings of standing authority to code rather than names yields a self-extension verb whose failure outcomes are all returned as data and all leave generation N serving or explicitly stranded. The claim is about the revertible envelope, not about the safety of granted providers' host code, which the doc says stays trusted.

## Contributions
1. `Gate.propose`: halt check, forbidden-grant refusal, standalone self-extension compile, health-gated swap, one result object with distinct shapes (HALTED, FORBIDDEN_GRANT, compile refusal with machine-readable why-trace, STATE_UNDISCLOSED, SWAP_REVERTED, swapped with migration) (`src/revl/gate.py:522`, `:906`).
2. The post-activation health gate: any non-clean activation, including non-raising FAILED and PENDING, is a swap rejection routed to the abort path (`docs/design/334-self-extending-runtime.md:34-57`, `src/revl/mcp/session.py:2137`).
3. Authority envelope on proposals: no author-chosen realm placement, and a standing auto-approve rule bound to a per-component signature over body, provides, requires and config, so a successor that reuses a reviewed name does not inherit the review (`docs/design/334-self-extending-runtime.md:652-710`, `src/revl/mcp/session.py:9564`, `tests/test_334_reviewed_name_substitution.py`).
4. Live-state migration only across declared channels; a handle minted for generation N refuses after the generation moves (`docs/design/334-self-extending-runtime.md:830-846`).
5. A bounded evolve loop that turns a refusal into a machine-readable why-trace for a pluggable proposer and retries to a budget (`src/revl/evolve_loop.py:209`, `docs/evolve-loop.md`).
6. An account of design-review findings and their fixes as a case study in what breaks when an untrusted generator drives a hot-swap verb.

## Related work
| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Erlang/OTP hot code upgrade (release handling, `code_change`) (citation to be checked) | Swap modules and migrate state under operator control; code is trusted | The code is untrusted and generated; admission precedes the swap; typed handoff declared on both sides or the swap refuses |
| Kubernetes rolling update, Argo Rollouts canary and rollback (citation to be checked) | Metric-driven rollout and rollback of container images | The health gate is in-process and checks that declared provides resolve and no fiber is FAILED or PENDING; no traffic metric is used; residue is checked through witnessed inverses |
| Genetic improvement; GenProg, Repairnator (citation to be checked) | Generate patches validated by tests | Validation is capability admission plus health, not test passage; repair is bounded by a policy that is closed by default (`docs/repair-loop.md`) |
| SWE-agent, Copilot Workspace (citation to be checked) | An agent edits a repository, a human merges | The agent edits a running composition inside an envelope; the runtime reverts on rejection |
| Voyager skill library (citation to be checked) | Model writes reusable skills into a library executed in the same process | Skill code may not declare host code, may not reach ungranted services, and cannot call the admission verb |
| Dynamic software updating research (Ginseng, Kitsune, DSU generally) (citation to be checked) | Safe update points, state transformers, type-safe updates | Related; the state-compat gate is similar in aim. revl adds the generator as adversary, so the update surface itself is an attack surface |

## Evidence on main
| Claim | path:line or test | Status | Note |
|---|---|---|---|
| `Gate.propose` returns distinct data outcomes; refusal is data | `src/revl/gate.py:522-626`, `:906-1135` | shipped | |
| Forbidden-grant refusal fires before compile; decider reachable through a `requires` edge or any service name is also refused | `src/revl/gate.py:670` (`_forbidden_decider_grant`), `:983`; tests `test_forbidden_grant_rejects_a_granted_decider_service`, `test_forbidden_grant_fires_before_compiling`, `test_forbidden_grant_rejects_a_decider_under_any_service_name`, `test_forbidden_grant_reaches_the_decider_through_a_requires_edge` in `tests/test_self_extending_334.py:433-553` | shipped | The name check inspects the granted set only; the structural check runs on the composed IR against the known crossings `host_admit` and `host_admit_all` (`_DECIDER_EXTERNS`, comment block above it). A decider written as a fresh-named extern is declared out of scope in that comment |
| Untrusted candidate cannot declare an extern, reach a host extern, or reach an ungranted service | `tests/test_self_extending_334.py:357-410` | shipped | |
| Failed or pending successor reverts to generation N | `test_edge1_failed_activation_reverts_to_gen_N`, `test_edge1_pending_requirement_reverts_to_gen_N`, `test_edge1_activation_error_reverts_to_gen_N`, `test_swap_health_gate_reverts_failed_and_pending_directly` (`tests/test_self_extending_334.py:229-315`) | shipped | Needs the cordis-py runtime per the repair-loop doc; not run here |
| Residue-free revert and post-swap fault revert | `test_happy_path_self_extending_loop_reverts_residue_free` (`:166`), `test_edge2_post_swap_call_fault_reverts_residue_free` (`:578`), crash tests (`:627`, `:670`) | shipped | |
| Live state migrates or the swap reverts; state not declared on both sides is refused before teardown | `tests/test_self_extending_334.py:806-921` | shipped | The design text for slice 3 says generational migration; the code now passes `migrate="declared"` (`src/revl/gate.py:1090`). The paper must follow the code |
| Name-substitution of a reviewed component does not inherit an auto-approve rule | `src/revl/mcp/session.py:9564` (`_component_signature`, the content digest the bind uses), `tests/test_334_reviewed_name_substitution.py` (5 test functions) | shipped | "three of them fail on the predecessor" is the doc's claim (`docs/design/334-self-extending-runtime.md:917`); not re-run |
| Realm self-placement refused on the untrusted-author path | `src/revl/admit_profile.py:426` (`self_extension`), `check_no_realm_placement` at `:209`, called once at `:916` | shipped | One call site |
| Stale handle refuses after generation moves | `tests/test_334_propose_handle_binding.py` (7 test functions, matching the design note's "seven"; `docs/design/334-self-extending-runtime.md:830-846`) | shipped | The generation check runs before the key check |
| Structured why-trace to proposer, retry to budget | `src/revl/evolve_loop.py:209`, `docs/evolve-loop.md:46-60`, `tests/test_evolve_loop.py:134,174,187` | shipped | The proposer is a seam, not a model; tested with a scripted proposer |
| Bounded self-repair within declared bounds, closed by default, widening stops for a human | `docs/repair-loop.md`, `src/revl/mcp/repair.py`, `tests/test_repair_loop.py` (16 test functions, e.g. `:172`, `:234`, `:291`) | shipped (v1) | The status rests on the code and tests |
| Hot-swappable scoring service walked on the real runtime | `docs/design/525-webapp-slice3-differentiated.md`, `tests/test_app_hotswap_725.py` (11 test functions) | shipped | Uses `Session.swap` directly, not `Gate.propose`; not a propose measurement |
| Demo: a running system rewrites a component; a broken answer is refused and never queued | `demo/self_evolve.py`, `demo/evolve_bridge.py`, `tests/test_self_evolution.py` | shipped | The demo admits against the running manifest and applies after the call returns; it is the earlier mechanism, not `Gate.propose` |
| Rust host | `docs/design/334-self-extending-runtime.md` (the 2026-09-14 re-verification) | partial | Rust can decide and fail closed but cannot swap; blocked on the native emitter |
| Re-entrant propose | same doc | designed | Refused by the forbidden-grant rule, not supported |

## Numbers that exist
- `tests/test_self_extending_334.py`: 24 test functions; the v2.0 roadmap row for this work says 25 passed at c225445a (`docs/v2.0-roadmap.md`). Counts differ because of parametrisation or later changes; re-run before citing.
- `tests/test_334_reviewed_name_substitution.py`: 5 tests, 3 failing before the fix per the design note.
- `tests/test_repair_loop.py`: 16 test functions. `tests/test_evolve_loop.py`: 12.
- Slice 3 defect: migration reported `migrated: True` with `resources: 0` in capture mode (`docs/design/334-self-extending-runtime.md`, slice 3 paragraph).
- Measured before the slice 5 fix: a swapped-in `BillerInvoice` crossing fired under an operator's rule with zero tickets raised (same doc, slice 5 paragraph).
- No latency, no swap pause time, no throughput, no success rate of any proposer, no number of proposals from a real model.

## Paper outline
1. Introduction: self-extension, why admit-then-swap is unsafe.
2. Background: revl admission profiles, session swap, witnessed effects and inverses.
3. The gap between two verbs; the propose design.
4. Trust boundary: what is checked, what is not (granted providers' host bodies).
5. Failure semantics: the health gate, halt dominance, residue and the crash half (write-ahead log).
6. Authority leakage found in review: realm choice, name substitution, stale handle, unreported state transfer.
7. The loop: why-trace, budgets, bounded repair.
8. Evaluation (to run).
9. Limits and related work.

## Threats to validity and limits
- The design says it plainly: revl guarantees compile-time admission and a revertible envelope, "not a sandbox around a granted provider's host body" (`docs/design/334-self-extending-runtime.md:32-33`). New agent-introduced host code needs the operator gate or confinement.
- Only witnessed effects revert. "none of this reverts an effect that was NOT witnessed" (same doc, residue section).
- The health gate checks activation, not behaviour; a candidate that activates cleanly and computes the wrong thing is admitted. Behavioural validation belongs to the promotion controller (P59), not to this verb.
- The first swap design was found wrong by review before it was built; a reviewer may ask what remains unfound. The attack list has only been reviewed by the project's own reviewers so far.
- The scoring-service walk and the self-evolve demo do not exercise `Gate.propose`; they are not evidence for it.
- Test counts in the roadmap, design notes and files disagree; re-run and report named counts.
- The evolve loop bounds retries by the declared budget (`docs/evolve-loop.md:12-14`, `:36-46`).
- The forbidden-grant structural check keys on the known decider crossings (`host_admit`, `host_admit_all`). A fresh-named admit extern from an operator is out of scope by the code's own comment, so the grant rule is not a general guarantee against new host code.
- Requires the cordis-py runtime for activation tests, so results are Python-tier only.
- No authoring loop on a live model has been measured; the evidence is a scripted proposer.

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 24 checked, 8 corrected.
