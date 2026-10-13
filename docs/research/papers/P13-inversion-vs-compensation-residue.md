---
id: P13
title: Inversion Is Not Compensation: Reversal Classes and Honest Residue
theme: effects-replay
kind: full
maturity: partial
status: The teardown contract and the Python tier ship with tests; the six-tier conformance gate is only partly verified, and there are no measurements, saga baseline comparison or mutation study yet.
fused_with:
---

## Pitch

A rollback that ran every undo is not a rollback that restored the world: revl types three reversal forms (bracket inverse, witnessed inverse, compensation), runs them in two phases that never let a best-effort failure cut short a provable one, and refuses to call a session clean while any owed offset did not land.

## Abstract

Saga-style systems treat compensation as the rollback mechanism and report success when the compensating steps have been dispatched. We argue that this conflates three different things: an inverse that restores state, an inverse that restores state only if a witness captured at forward time still holds, and a second boundary crossing chosen to offset a first one that cannot be recalled. We describe the teardown contract of the revl language, in which each entry on a per-activation LIFO stack has one of three kinds (bracket, transactional, compensation), abort runs in two phases (all provable inverses to completion, then bounded best-effort compensations), failures in either phase are logged and the walk continues, and every failure, skipped step and abandoned in-flight call becomes a typed residue entry in one schema shared by the abort path and crash recovery. A session boundary report is not clean while a compensation was owed and did not land. We also report a bug class the first design missed: an inverse that ran without reverting, caught by journaling the host-map keys a bracket touches (issue #1945). The contract is implemented on the py reference tier with a scoped UI-transaction unit, ported to the other five tiers for the registration half (the design doc describes the port; the tier code was not checked), covered by a cross-tier sweep (#1511, whose live compiled-tier runs need toolchains), and states per tier what bound it can actually deliver. We do not claim that residue-free means the world is clean; the docs list what recovery does not promise. No user study or production measurement exists yet.

## Problem and claim

In sagas and workflow engines, a failed step triggers compensating actions, and the transaction manager reports the saga as compensated. Two things are hidden. First, a compensation is itself a fallible external call, and its failure is usually a log line or a retry loop, not part of the verdict. Second, a compensation is not an inverse: a "delete" after an "insert" does not un-issue the insert, and anything that observed the insert (a trigger, a replica, a webhook, a person) has already seen it. revl's own docs say it plainly: a `compensate` clause is "a second boundary crossing chosen to offset the first", and running one "appends a new `emission` step to the timeline" (`docs/replay.md:130-150`).

The claim is narrow and checkable. A teardown algorithm that (1) separates reversal forms by the surface they land on (proof or audit), (2) orders them so best-effort work cannot interrupt proof-grade work, (3) continues past every failure and logs it, and (4) makes the verdict depend on that log, gives a rollback report whose "clean" is a statement about named obligations, not about the absence of exceptions. The second claim is a negative one: even "every inverse ran" is not "every inverse reverted", and the contract needs an observation that checks the effect, not only the call.

## Contributions

1. A three-kind accumulator (bracket, transactional, compensation) on one LIFO stack, with a table of what each kind does on clean unload, on abort, on an operator halt, whether it may emit in teardown, and whether it may fail (`docs/design/teardown-contract.md:42-59`).
2. A two-phase abort: Phase 1 replays bracket and transactional entries to completion with continue-and-log, Phase 2 runs compensations newest first under a deadline checked between calls, and every skipped or failed entry is a residue entry (`docs/design/teardown-contract.md:61-111`, `:151-188`; Python implementation `backends/python/runtime.py:3527-3585`).
3. A uniform residue schema (`restore-residue`, `bracket-fault`, `compensation-residue`, `unreconstructible`, plus two E-Stop kinds) shared by the abort path and `revl recover`, with an outcome field that distinguishes failed, not-attempted and unknown (`docs/design/teardown-contract.md:504-585`).
4. A verdict rule: a session boundary report carries a fifth check, `compensations`, and `noResidue` is false while an owed compensation did not land (`docs/design/teardown-contract.md:449-458`; `tests/test_declared_compensate_positions.py:269`).
5. A per-tier statement of how much of the Phase-2 bound each of six runtimes can deliver (none, abandon-the-wait, interruptible-only, and a guest-code epoch deadline on wasm with host imports not preemptible), rather than one claimed guarantee (`docs/design/teardown-contract.md:189-269`).
6. The "ran is not reverted" finding: a per-frame and per-map journal that judges net host-map state after teardown, which turned a green `assert no_residue` into a `bracket-fault` of type `NotReversed` (`docs/design/teardown-contract.md:460-502`; `tests/test_method_effect_reversed_1945.py`).

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Sagas (Garcia-Molina and Salem, SIGMOD 1987) (citation to be checked) | Long-running transaction as a sequence of subtransactions with compensating subtransactions run in reverse order | Compensation is one of three typed kinds, run only after all provable inverses finish, discharged (never run) on commit, and its failure is part of the verdict |
| Temporal / Cadence saga patterns | Application code registers compensations in a list, runs them on failure; failures are the developer's problem | The compiler derives which crossings are compensated, bare or unresolved (three audit states) and refuses a clean verdict while one is owed |
| AWS Step Functions and Camunda compensation handlers (citation to be checked) | Declarative compensation steps per task; completion of the handler is treated as undone | No claim of undo: compensation is audit-surface, the original emission stays counted as a crossing that left the system |
| Compensating transactions pattern, cloud design patterns catalog (citation to be checked) | Guidance: make compensations idempotent, expect failure | Same guidance made structural: arguments captured at registration, WAL descriptors, idempotency requirement stated (design 247, decision 5), residue entry when absent |
| WS-BPEL compensation handlers and long-running transactions (citation to be checked) | Scoped compensation handlers, default compensation order | Two-phase order and the proof/audit split are the new part; scope is the activation, with a scoped abort for UI transactions |
| Database undo/redo logging (ARIES, Mohan et al. 1992) (citation to be checked) | Physical/logical undo with compensation log entries (CLRs) | A CLR is an inverse the log treats as infallible (ARIES description not re-checked here). revl keeps that class (bracket, G5) and adds the case ARIES cannot have: a world action that may fail and cannot be undone |

The difference to emphasise: as the table describes them (descriptions not yet checked against the sources), none of these systems distinguishes an inverse from an offset in the type, orders proof before intent, or feeds compensation failure back into the success verdict.

## Evidence on main

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Three entry kinds on one stack, per-kind behaviour table | `docs/design/teardown-contract.md:42-59` | designed and shipped on py | Doc header says "design locked (decisions approved 2026-08-26)" |
| Two-phase abort, continue-and-log, deadline between calls | `backends/python/runtime.py:3527-3585` (`_drain_phase2`, `_run_compensations`), `:3590` (the phase-1 residue helper) | shipped (py) | Python deadline is checked before each compensation, "never mid-call" (`backends/python/runtime.py:3537-3540`) |
| Phase 1 failure severities: `bracket-fault` vs `restore-residue` | `docs/design/teardown-contract.md:168-188`; `backends/python/runtime.py:2518` (`_phase1_kind`) | shipped (py) | A bracket fault is "contract-grade": the proof surface lied |
| Compensation discharged, never run, on clean unload | `docs/design/teardown-contract.md:358-386`; `tests/test_declared_compensate_positions.py:143` | shipped (py) | Fixes the placeholder that ran compensations on every teardown (`docs/design/247-compensate.md:68-71`) |
| TCK respec of A5 into a5a (discharge) and a5b (two-phase abort) | `tck/spec.py:184`, `:201`, `:331-349`; `docs/contract-errata.md:1184-1202` | shipped | Conformance cases exist; not re-run |
| Third audit state `unresolved` and session residue surfacing | `tests/test_compensation_residue_surfacing.py:90`, `:133`, `:166`, `:196` | shipped | Tests need a live cordis-py composition for the runtime half; the classifier tests do not |
| Owed-but-not-landed compensation makes `noResidue` false | `docs/design/teardown-contract.md:449-458`; `tests/test_declared_compensate_positions.py:269` | shipped (py) | Test needs the pinned cordis fork; a skip is not a pass |
| One compensation per crossing; site-spelled replaces declared | `docs/design/teardown-contract.md:427-447` (issue #1902) | shipped on 5 tiers per doc | Not independently run |
| Cross-tier sweep fails a tier that drops a declared compensation | `tests/test_sweep_compensations_1511.py:123`, `:130`, `:139`, `:145`, `:151`, `:281` | shipped | Unit tests of the sweep logic; compiled-tier live tests at `:275` need toolchains |
| Escrowed undo failure is residue and the rest still run | `tests/test_finalize_abort_residue_1473.py:103` | shipped | Session abort path |
| "Ran is not reverted": journal, `NotReversed` fault | `docs/design/teardown-contract.md:460-502`; `tests/test_method_effect_reversed_1945.py:111`, `:121`, `:128`, `:138`, `:148`, `:245` | shipped (py) | Journal observes host Maps only; "otherwise stays the author's word" (`docs/design/teardown-contract.md:499-501`) |
| Compensation never reported as an inverse; step-back splits `compensationsRan` from `inversesRan` | `docs/replay.md:130-150`; `backends/python/replay.py` | shipped | `tests/test_replay.py` pins growth of the emission list (named by the doc; not opened) |
| Fault harness reports emissions as notes, never "reverted" | `docs/fault-tests.md:167-195` | shipped | |
| Model is not the world: recover marks modelled results and exits 3 when only a model ran | `docs/crash-recovery.md:495-540` | shipped | Issue #1477 |
| What recovery does not promise | `docs/crash-recovery.md:736-751` | shipped | |
| Refusal that keeps ownership rather than a replacement with uncertain cleanup | `docs/lifecycle-contract.md:148-183` | shipped | `Session.rearm_teardown`, `strand_teardown` |
| wasm tier: compiled dispatch chain, epoch deadline around each Phase-2 call | `docs/design/teardown-contract.md:270-356` | shipped, with stated gaps | Host-import calls not preemptible; site-spelled `compensate` in a method body is a hard EmitError |
| Go abandons the wait with `outcome: unknown`; java preempts only interruptible points and abandons go-style only when the interrupt is not honored; rust and ts have no in-call preemption (between-compensation check only); wasm host imports are not preemptible | `docs/design/teardown-contract.md:189-269` | specified; tier code not opened | Treat as specified, not verified |

## Numbers that exist

None yet for this paper's claims. No residue rate, no overhead, no count of compensations owed versus landed over a corpus. Existing counts are test names, not measurements. The provisional Phase-2 defaults (5000 ms total, 1000 ms per call) are explicitly provisional (`docs/design/teardown-contract.md:352-353`, `:835`).

## Paper outline

1. Introduction: the saga verdict problem; three examples where "compensated" lies.
2. Background: revl activations, the accumulator, proof surface versus audit surface (G4, G5, G8).
3. The reversal taxonomy: bracket, transactional, compensation; the table.
4. The teardown algorithm: two phases, continue-and-log, the deadline and what each tier can honestly bound.
5. The residue schema and the verdict rule; three audit states; E-Stop as a third disposition that strands instead of unwinding.
6. Ran is not reverted: the journal and issue #1945.
7. Recovery and the model-is-not-the-world rule; what recovery does not promise.
8. Evaluation: mutation kill rate, saga-baseline fault injection, per-tier conformance table (all to be done).
9. Related work and limits.

## Threats to validity and limits

- The docs state the limits themselves: recovery "does not promise state was restored"; a bare emission is not undone; closure-only inverses are reported, not reconstructed (`docs/crash-recovery.md:736-751`). The #1945 journal "observes host Maps only; a service's own host state ... stays the author's word" (`docs/design/teardown-contract.md:499-501`).
- Python and TypeScript cannot preempt a hung synchronous compensation; a hung call holds the abort until the host returns ("The honest limitation, stated once", `docs/design/teardown-contract.md:209-215`). This is a bound, not a guarantee.
- Go and Java abandonment means two compensations can run concurrently and an emission may land after the abort reports; outcome is `unknown` and reconciling it is an open question (`docs/design/teardown-contract.md:229-260`, `:843`).
- Wasm: site-spelled `compensate` inside a method body is refused; the accumulator is fixed at activation time.
- Tests that exercise the runtime need the pinned cordis fork and skip without it; a skip is not evidence. The conformance cases a5a and a5b exist in `tck/spec.py`, but passing on all five non-py tiers has not been verified.
- The ordering of the two phases (Phase 2 acts only on what Phase 1 could not reverse, with no data hazard because arguments are captured at registration, `docs/design/teardown-contract.md:151-167`) is not stated as a theorem. `formal/RevL/Semantics.lean` models the verdicts and proves count and partition facts (`replays_or_discharges`, `disposition_trichotomy`, `halted_strands_every_kind`, `teardown_length`, `phase_lengths_add`), but none states the Phase-2-after-Phase-1 ordering or its data independence.
- The comparison to saga frameworks is on verdict honesty, not on throughput or developer effort. Whether declaring `compensate` per extern is a burden is unmeasured; there is no user data.
- Idempotency of compensations is stated as a requirement and left to the author (design 247, decision 5; a typed key is deferred).
- Selection risk: the strongest evidence is one language's own contract. Claims are framed as a design point with a measured failure class, not a universal.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 35 checked, 8 corrected.
