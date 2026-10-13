---
id: P26
title: Spent Authority Must Outlive the Generation: Seven Hot-Swap and Reload Bypasses in an Agent Approval Gate
theme: lifecycle-swap
kind: experience
maturity: shipped-evidence
status: Fixes and per-bypass regression tests for seven generation-boundary bypasses are on main; no study design, detector or survey yet.
fused_with: P55, P45
---

## Pitch

Where a hot-reloadable agent runtime rebuilt its approval state per generation, a spent single-use or budgeted approval came back to life. We catalogue seven such bypasses found in one audit wave and the one rule that closes them: key authority state to the rule or the content digest, never to the generation.

## Abstract

Agent runtimes let an operator approve an irreversible action once, or install a standing auto-approve rule with a use count and a time-to-live. They also let the running program be swapped, rolled back, unloaded and reloaded, or forked, usually by tools the agent itself can call. We report an audit of this seam in revl's session layer, in which the approval state was built per generation. Seven defects followed one pattern: state that belongs to a rule, a grant or a program was stored on, or reset with, the generation, so a boundary crossing renewed authority the operator had already spent. A spent `uses` budget came back on every swap; the same budget came back on unload and reload; a fork started with a fresh budget; the activation-time spend path never wrote its counter back; a consumed single-use typed approval was re-seeded unspent into each successor; a deferral queue was orphaned in the dead owner so a queued irreversible send was lost while the verdict still read clean; and a gauntlet evidence dossier keyed by component name admitted a different program with the same name. Each fix has a named regression test on main; the distillation tests among them skip without the pinned cordis fork. The rule we extract is that authority state is keyed to the rule text or the content digest and settled at each owner boundary, and that carrying state forward may only narrow what a crossing can do. We also state what the fixes do not cover. We have no measurement of how often these bypasses are reachable by an agent in practice.

## Problem and claim

Approval designs usually fix the question "who may say yes" and "how is a yes bound to a request". They say less about identity over time. If the runtime supports live update, the question "is this the same approval" depends on what the state is keyed on. Erlang-style `code_change` hands state across a swap by convention; capability systems treat revocation as the hard problem; allowlist approval in agent clients is per session. None of these name the failure mode where a boundary crossing, not an attacker action in the usual sense, quietly renews a bounded permission.

Claim: for this class, most defects are state-key or carry-direction errors. Two keys are correct: the rule (its canonical text) for budgets and review binds, and the component's content digest for evidence. In the seven cases catalogued here the generation is not a correct key for authority state, and the direction of any carry-over must be monotone (spent stays spent, the reviewed set stays as narrow as it was). The deferral-queue defect (item 508) is a missing carry, not a key error. The roadmap entries for the seven items (498, 500-504, 508) give the failure direction for each, which is mostly permissive (over-authorization) and, for the deferral queue, a lossy and falsely clean verdict.

## Contributions

1. A catalogue of seven generation-boundary bypasses (items 498, 500, 501, 502, 503, 504, 508), each with the state, the boundary, the failure direction and the fix. A rollback-pointer defect (item 497) is a recovery-path analog and is not counted among the seven.
2. The keying rule: budgets and review binds are keyed by `rule.to_dsl()` (`src/revl/mcp/session.py:8155`, `src/revl/mcp/session.py:8982`) and persist through `_persist_auto_spend` (`src/revl/mcp/session.py:5978`); dossiers are keyed by `(name, content digest)`; single-use approvals are settled back onto the session state at the generation boundary. Whether the budget persists beside the policy binding was not checked.
3. A test pattern, one test per boundary (swap, rollback, unload/reload, fork) per state kind, with a never-spent control and a "narrowing only" control.
4. A negative result: a fork must carry no approval but must carry the state that refuses one.
5. An accounting of exceptions: evidence is deliberately session-scoped (a dossier dies on unload) while budgets are not, and a failed load must not roll back the approval state, because a spend is committed before the activation body can fire it.

## Related work

| prior system or line of work | what it does | what revl does differently |
|---|---|---|
| Capability revocation and macaroon-style caveats (citation to be checked) | attenuation only; expiry is a caveat checked at use | budget and ttl are mutable state; the paper is about where that state lives |
| Erlang/OTP `code_change` | the programmer hands state across a release upgrade | the carry is a list the session owner enforces; the defect catalogue shows what omission of one entry cost |
| Allowlist approval in agent tool clients | per-session or persistent allow rules, little generation concept | rule-bound budgets and a review bind that suspend a rule when its glob grows |
| Dynamic software updating literature (Ginseng, Kitsune) (citation to be checked) | state transformation correctness for live update | the object is authority state, whose safe direction is only narrowing |
| Saga state across deployments | compensation state must survive redeploys | same durability need, applied to consumed approvals and the deferral queue |

## Evidence on main

| claim | path:line or test | status | note |
|---|---|---|---|
| 498 swap renewed rule budget; budget now persisted per rule | `docs/roadmap-archive/14-web-platform-maturity-make-ordinary-web.md` (item 498); `src/revl/mcp/session.py:8135-8190` (`_install_auto_approve_rules`), `src/revl/mcp/session.py:5978` (`_persist_auto_spend`); `tests/test_distill_enforcement.py` (`test_exhausted_uses_budget_survives_a_swap` at 480, `test_lapsed_ttl_is_not_resurrected_by_a_swap` at 545) | shipped | tests need the pinned cordis fork and skip without it |
| 500 activation-path spend not written back | `src/revl/mcp/session.py:5998` (`_commit_spends`); `tests/test_distill_enforcement.py:613`, `:638`, `:657` | shipped | |
| 502 consumed single-use typed approval re-armed | `src/revl/mcp/session.py:1336` (`_settle_approval_spend`), `src/revl/mcp/session.py:1363` (`_install_session_owner`); `tests/test_502_approval_replay.py` (5 tests: control, unload/reload, swap, rollback, fresh grant) | shipped | |
| 503 unload/reload renewed budget and review bind | `src/revl/mcp/session.py:4580` (`_reset` keeps `_auto_spend` and `_auto_reviewed`; it clears `_ledger` at 4649 and `_gauntlet_dossiers` at 4676); `tests/test_distill_enforcement.py:697`, `:761`, `:784`, `:860` | shipped | |
| 504 fork renewed budget | `src/revl/mcp/session.py:4425-4432` (branch carries `_auto_spend`, `_auto_reviewed`, `_auto_reviewed_sig`); `tests/test_distill_enforcement.py:734`, `:809`, `:826`, `:888`, `:945` | shipped | `test_a_fork_still_carries_no_approval` pins the narrowing-only rule |
| 508 swap orphaned deferral queue; now moved | `src/revl/mcp/session.py:1411-1412` (`self._owner._queue = prev._queue; prev._queue = []`, inside `_install_session_owner` at 1363); `tests/test_247_second_pass_dataloss.py:523` (survives swap), `:554` (move not copy), `:573` (abort drops it), `:615` (commit marks it flushed) | shipped | |
| 501 dossier bound to content digest | `src/revl/mcp/session.py:1574` (the dossier writer), `src/revl/mcp/session.py:1591` (`_enforce_evidence`); `tests/test_290_dossier_content_binding.py` (8 tests incl. `test_a_dossier_does_not_admit_a_different_body_under_the_same_name`, `test_the_evidence_does_not_survive_unload`) | shipped | |
| Failed load does not refund approval state | `src/revl/mcp/session.py:408-428` (comment and list including `_auto_spend`, `_ledger`, `_approval_grants`) | shipped | |
| Roadmap items 497-508 marked done, descriptions give the failure direction | `docs/roadmap-archive/14-web-platform-maturity-make-ordinary-web.md` | shipped | |

## Numbers that exist

- Seven defects in one audit wave, all dated 2026-09-13 in the roadmap entries. Test counts per file: 5 (`tests/test_502_approval_replay.py`), 31 (`tests/test_distill_enforcement.py`, of which 14, at lines 480 to 945, concern these boundaries), 8 (`tests/test_290_dossier_content_binding.py`), 14 (`tests/test_247_second_pass_dataloss.py`, 4 on the queue carry). Counts are `def test_` lines; the tests were not run for this draft.
- Item 500's text reports a measured reproduction: a `uses=2` rule whose crossing sat in an activation body fired across four consecutive swaps and accumulated 5 emissions. That is the only exploit magnitude available.
- No data on how the bugs were found (human audit, tool, agent) is available; we make no claim about discovery method.

## Paper outline

1. Introduction: approval is a statement about identity over time.
2. Setting: session, generation, owner, rules, grants, typed approvals, deferral queue.
3. The seven bypasses: state, boundary, direction, fix, test, in a single table then short narratives.
4. The keying rule and the narrowing-only rule, with the three justified exceptions (session-scoped evidence, no refund on failed load, no approval carried by fork).
5. Making the class mechanical: field classification and mutation check.
6. Survey of other systems (if done).
7. Limits and related work.

## Threats to validity and limits

- One codebase, one audit wave, one author team. Seven is a count of what was found, not of what exists. There is no estimate of residual bugs.
- The failure-direction claims come from the roadmap entries' own analysis; the entries and the code carry sites were read but the reproducers were not executed.
- Quorum item 499 is excluded: its defect is an ordering rule (a lapse overwrote a decided outcome), not a generation key.
- The distillation tests skip without the cordis fork, so a green run of a minimal environment proves nothing about them.
- Some reachability depends on a deployment where the agent can call `unload`, `load`, `swap`, `rollback` as tools; item 502 says these are ordinary tool verbs, not gated by the `approve` verb. A deployment with those verbs operator-gated narrows the impact.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 23 checked, 7 corrected.
