---
id: P22
title: "Speculation by Default: A Verified Proposal, a Graded Dossier and a Single Commit Between Running Composition and Disk"
theme: effects-replay
kind: full
maturity: partial
status: The proposal and commit loop, undo as a gated change, the gauntlet dossier and a repair loop are shipped with tests; the edit verb existing clients call first still commits by default, two dossier slots are unwired, and no outcome evaluation exists yet.
fused_with:
---

## Pitch

An agent's edit is verified on a per-caller proposal and, on the speculative path, only one explicit commit, re-verified against the live composition, can change what runs or what is on disk, and undo is a recompile through the same gate.

## Abstract

LLM coding agents usually edit by mutating: the tool applies the patch, then a test run or a human finds out whether it was acceptable, and "undo" is a second mutation that nobody checks. We describe the edit loop of revl's agent session, built around three states: the running composition with the exact source it was compiled from (shared by every caller), a per-caller proposal (a speculative working copy), and disk (an export, written only by one verb). A change is applied to the proposal and run through the same admission, lease and quarantine gates a live swap would face, optionally followed by a gauntlet that grades the candidate in an isolated scratch session and returns a dossier separating what was proved, what was tested with counts and what is merely claimed. On the speculative path nothing swaps or writes until an explicit commit, which re-verifies against the composition as it is now and is refused if another caller committed in between, rather than silently undoing that commit. Undo recompiles the target generation's sources through the compile and admission gate, so a generation a stricter checker now rejects cannot be restored by backdoor. A repair loop composes these pieces (fault, causal trace, bisect, candidate, gauntlet, policy, widening check, swap) and is exercised by an unattended end-to-end test. We report what is shipped: 12 speculation tests, a stale-proposal refusal test and an undo-refuses-rejected-target test. We also report the gaps the design doc itself names: `revl_edit` still commits by default, the quarantine and lease gates do not cover undo, two dossier slots are hard-coded pending, and the repair loop does not yet use the canary.

## Problem and claim

Agent tools put "try this" and "do this" in the same call. The design doc states it directly: the loop an agent runs still mutates on the first step (`docs/design/1696-speculation.md:5-11`). A rejected-after-the-fact edit has already been seen by every other client, and the only durable form of the work is a file the agent writes outside the system. Undo, where it exists, is often another unchecked mutation (citation to be checked, product docs).

The claim is about the structure of the loop, not about model quality: (a) a speculative change never swaps and never writes; (b) a commit is the only state change another caller can observe; (c) a commit verifies again, and refuses if the running generation moved; (d) export writes exactly the held source (`docs/design/1696-speculation.md:64-75`). Together with undo being a gated recompile (`docs/generation-history.md:46-65`), this leaves one admission gate that every swap path reaches, the compile and admission gate, instead of one verification design per verb. Quarantine and lease are not on every path (see below).

The claim has a precise boundary, and the paper should state it. "No mutation path bypasses verification" holds for the admission gate: a swap, an edit commit, an undo and a repair all reach it. It does not hold for every gate: `docs/quarantine-tier.md:112-115` says undo and rollback reach the swap with neither the quarantine gate nor the lease check. And the default of the most-used verb is not speculative yet (see Evidence).

## Contributions

1. A three-state model (running composition with held source; per-caller proposal keyed by operator identity; disk as export) with stale-proposal refusal in place of silent overwrite (`src/revl/mcp/proposal.py:1-18`, `src/revl/mcp/proposal.py:71-79`; `docs/design/1696-speculation.md:13-38`).
2. A speculative-by-default change verb (`revl_change`) whose proposal runs the full verification and then stops, with `commit` and `discard` as the only exits (`src/revl/mcp/server.py:1744`; `docs/design/1696-speculation.md:40-62`).
3. Undo as a gated change: the target generation's sources are recompiled through the same gate as a swap, a rejected target is a refusal result with the composition untouched, and every successful mutating response carries its undo call, or `undo: null` with a reason (`docs/generation-history.md:46-90`; `src/revl/mcp/session.py:2937-3010`; `tests/test_undo.py:230`).
4. A graded candidate dossier, `revl_gauntlet`, run in a throwaway scratch session, with an explicit epistemic split into proved, tested (with counts) and claimed (`docs/gauntlet.md:17-35`, `docs/gauntlet.md:115-125`; `tests/test_gauntlet.py:191`).
5. A quarantine tier whose verdicts (passed, trapped, timeout, rejected, deferred, unavailable) come from running the candidate under a wasm component runtime, with an admission hook that applies only where policy requires it (`docs/quarantine-tier.md:74-116`).
6. A repair loop that composes the above with a closed-by-default self-repair policy and a human-ack interrupt on widened reach, with an unattended exit test (`docs/repair-loop.md:19-110`, `docs/repair-loop.md:179-188`; `tests/test_repair_loop.py:234`).

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Git branches and pull requests | Isolate a change until review and merge | The "review" is the machine gate (admission, leases, quarantine, optional gauntlet) and runs on every speculative step, not only at merge |
| Database MVCC and snapshot isolation | Hide uncommitted writes from other readers | Per-caller proposal keyed by operator identity; the commit re-verifies and refuses on generation drift instead of last-writer-wins |
| Hot reload (Vite, React Fast Refresh) | Swap code in place immediately | Swap is the last step, after verification, and reversible by a gated undo |
| Replit and Cursor style apply-then-undo agents (citation to be checked, product docs) | Apply the edit, offer undo | Apply goes to a proposal; undo is a recompile through the gate |
| Nix generations and rollback (citation to be checked) | Atomic switch and rollback of system generations | Rollback re-admits the target through today's checker and can be refused (`docs/generation-history.md:60-65`) |
| Terraform plan and apply | Show a plan, apply against drift-checked state | `revl apply` also refuses on drift and rolls the applied prefix back by derived LIFO inverses (`docs/apply.md:23-70`) |
| SWE-bench Docker harnesses, CI sandboxes | Run a candidate patch in isolation after it exists | The scratch session is an in-process verb the agent calls before commit, and its dossier says what is proved vs only tested |
| Property-based testing | Evidence by sampled inputs | Dossier reports counts per check and lists the unverifiable boundary as "claimed" instead of passing it silently |
| Proof-carrying code and software attestations (citation to be checked) | Ship a proof or attestation with the artifact | The dossier is produced by the gate that also holds the swap, not shipped to a third party; no cryptographic attestation is claimed |
| Pyodide and Wasm isolation | Confine untrusted code | Used as a gate: a trapped probe makes a candidate ineligible, "proven by an actual wasmtime run, not asserted" (`docs/quarantine-tier.md:85-87`) |

## Evidence on main

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Speculative change neither swaps nor writes; builds up; one commit lands it | `tests/test_mcp_speculation_1696.py:96`, `tests/test_mcp_speculation_1696.py:113` | shipped | 12 tests in the file |
| A refused proposal is not held | `tests/test_mcp_speculation_1696.py:126` | shipped | |
| Second caller sees only committed changes | `tests/test_mcp_speculation_1696.py:148` | shipped | "second caller" = another operator identity on one server |
| Stale proposal refused instead of undoing a commit | `src/revl/mcp/proposal.py:71-79`; `tests/test_mcp_speculation_1696.py:163` | shipped | |
| Export writes exactly the held source, never a proposal | `tests/test_mcp_speculation_1696.py:180`, `tests/test_mcp_speculation_1696.py:191`, `tests/test_mcp_speculation_1696.py:197` | shipped | |
| Speculative fill does not boot a draft | `tests/test_mcp_speculation_1696.py:215` | shipped | |
| Undo of a committed change and export reports no inverse | `tests/test_mcp_speculation_1696.py:231`, `tests/test_mcp_speculation_1696.py:240` | shipped | |
| `revl_edit` defaults to commit | `src/revl/mcp/server.py:2136`, `src/revl/mcp/server.py:2156`; `docs/design/1696-speculation.md:50-54` | open gap | the doc says flipping it is slice 2, after callers move |
| Proposal survives reconnect; fork from a proposal | `docs/design/1696-speculation.md:87-88` | designed | slice 3 |
| Undo re-admits through the compile and admission gate; rejected target refused, composition untouched | `src/revl/mcp/session.py:2937-3010`; `tests/test_undo.py:230` | shipped | |
| Every mutating response carries its undo | `docs/generation-history.md:67-90`; `tests/test_mcp_undo_1703.py` (15 tests) | shipped | verbs with no inverse answer `undo: null` with a reason |
| Undo and rollback skip the quarantine and lease gates | `docs/quarantine-tier.md:112-115` | shipped as stated, contradicts the thesis | reaches `Session.swap` under the operator's `undo` authority |
| Gauntlet runs in an isolated scratch session; live composition untouched | `docs/gauntlet.md:115-125`; `tests/test_gauntlet.py:191` | shipped | 9 tests in the file |
| Dossier splits proved / tested / claimed | `docs/gauntlet.md:17-35` | shipped | |
| Fault sweep and inverse round-trip in the dossier | `docs/gauntlet.md:165-180`; `src/revl/mcp/gauntlet.py:252` | partial | both slots hard-coded `pending`; the features exist separately, only the dossier wiring is missing |
| Quarantine verdicts from a real wasmtime run | `docs/quarantine-tier.md:74-88`; `tests/test_quarantine.py:149`, `tests/test_quarantine.py:203` | shipped | needs `wasm-tools` and `wasmtime`; tests skip without them; 20 tests |
| Quarantine gate is opt-in | `docs/quarantine-tier.md:116-118` | shipped | inert with no requiring policy |
| Repair loop end to end, unattended | `tests/test_repair_loop.py:234`; `docs/repair-loop.md:179-188` | shipped | 16 tests in the file; swap leg needs cordis-py |
| Repair loop ends in "swap or canary" | `src/revl/mcp/repair.py:325-370` | partial | only `SwapRemediation` is wired; the canary hook reports `not-wired`; the canary verb exists separately (`tests/test_canary.py`, 15 tests) |
| Plan/apply with drift refusal and derived rollback | `docs/apply.md`; `tests/test_apply.py` (13 tests) | shipped | the plan is checked against itself and reality; an independent oracle is future work (`docs/apply.md:127-130`) |

## Numbers that exist

- Test counts by `rg -c "^def test"` on the tree (not run for this draft): speculation 12, gauntlet 9, quarantine 20, repair loop 16, apply 13, undo 12, mcp undo 15, canary 15.
- Generation history is bounded: `HISTORY_LIMIT` 64 (`src/revl/mcp/session.py:390`; `docs/generation-history.md:30-33`).
- The gauntlet lifecycle example in the doc shows `checks: 5, passed: 5` as a schema illustration, not a measured result (`docs/gauntlet.md:65-70`).
- No measurements on real agents: no task success rate, no regression-catch rate, no latency of the speculative path, no comparison against apply-then-test.

## Paper outline

1. Introduction: "try" and "do" are the same call; the claim and its boundary.
2. The three states, the proposal, the commit; guarantees (a) to (d).
3. Verification stages: admission, lease, quarantine, gauntlet; what each can and cannot show.
4. Undo as a gated change; the undo contract on every mutating response; where undo is deliberately weaker.
5. The graded dossier: proved, tested, claimed; isolation of the scratch session.
6. Composition: the repair loop and its closed-by-default policy.
7. Evaluation: verify-before-commit against apply-then-test on seeded defects, a multi-caller overwrite count, repair-loop outcomes.
8. Limits and open gaps (edit default, undo exceptions, pending slots).
9. Related work and conclusion.

## Threats to validity and limits

- The thesis "no mutation path bypasses verification" is stronger than the code: undo and rollback bypass the quarantine and lease gates by documented design (`docs/quarantine-tier.md:112-115`), and `revl_edit` commits by default (`src/revl/mcp/server.py:2136`).
- The gauntlet isolates a candidate from the live composition, not from the host: host-body externs run in the server's process; the docs call isolation "not a licence to run what the gate refuses" (`docs/gauntlet.md:127-137`). The wasm substrate is what confines, and only where the toolchain exists and the candidate's boundary types lower (Float, Map, resource handles and function values are deferred, `docs/quarantine-tier.md:158-164`).
- The "claimed" section lists the extern boundary rather than checking it. The dossier shape is stable, but two of the three evidence kinds that would shrink "claimed" are not wired.
- A speculative undo guarantee is byte-for-byte on sources and manifest only; running state is not part of that promise (`docs/generation-history.md:73-74`).
- `revl apply` verifies a plan against its own predicted outcome (`docs/apply.md:127-130`).
- Per-caller proposals are keyed by operator identity on one server; this is not a distributed system and the paper should not claim it.
- All current evidence is tests written by the project team; there is no study with external agents or users.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 20 checked, 6 corrected.
