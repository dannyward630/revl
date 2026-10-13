---
id: P25
title: "An Emergency Stop Is Not an Abort: A Third Teardown Verdict, a Shared Kill-Switch Latch, and a Mechanized Accounting of What Is Left Owed"
theme: lifecycle-swap
kind: full
maturity: partial
status: The halted verdict, the latch protocol on the Python tier and three native placement runners, the conductor and the Lean layer are shipped with tests; the Node tier does not yet honor the latch, wasm is reported statically, the cross-tier conformance fixture does not exist, and no latency or fault-injection measurements exist.
fused_with:
---

## Pitch

An operator emergency stop is a third verdict next to commit and abort: it replays nothing, drops nothing, names the one crossing that may or may not have landed, and a Lean-checked disposition table proves every registered obligation is on exactly one book.

## Abstract

Systems that run effectful agent or service compositions usually offer two ways to end an activation: commit, which discharges its undo obligations, and abort, which replays inverses in reverse order. Both are cooperative. When an operator hits the button during a runaway loop with irreversible effects in flight, unwinding hundreds of brackets is a long answer, and every inverse is another chance to cross the boundary again. We describe the operator E-Stop in revl, a language whose compiler derives teardown from declared inverses. The E-Stop is a third verdict, `halted`. A latch file, read by the same rule in every honoring runtime, makes each seam that dispatches or accepts a boundary crossing refuse new work, including when the latch is malformed. In-flight work is reported as ambiguous, never guessed, and a halted child prints an inventory and dies without a graceful-teardown claim. The Lean development extends the existing LIFO completeness and soundness theorems to the new verdict: the completeness theorem needs no new hypothesis, two corollaries gain an explicit settling hypothesis, and it proves that every (entry kind, verdict) pair is exactly one of replayed, discharged or stranded and that the three books partition the stack under every verdict. The design deliberately gives up the no-residue property of abort and replaces it with "all residue, all of it reported". The py runtime and the go, rust and java placement runners honor the latch today; node and wasm do not yet, and the conductor reports them by name as killed with residue unknown. We have no latency or fault-injection measurements yet.

## Problem and claim

Existing stop mechanisms fall into two families. Cooperative ones (supervisor shutdown, drain, saga compensation) run more code at the worst moment. Hard ones (SIGKILL, a feature-flag kill switch) stop fast but leave no account of what is owed, and a flag only protects the call sites that read it. Neither says which obligations remain and which single operation may have landed.

Claim: an emergency stop is a verdict in its own right, with a total accounting, not a faster abort. The design doc states the trade directly: "An E-Stop trades resource cleanliness for stop latency" (`docs/design/443-estop.md`). Four guarantees are given and no more: bounded latency (no new crossing once the latch is set), nothing invented (zero inverses, compensations or flushes run), total accounting, and at most one ambiguous crossing per activation. It also lists what it does not give: no G7 LIFO completeness (vacuous), no R4 no-residue, no handle release.

A second claim concerns uniformity: the latch rule, including fail-closed on a malformed or unreadable latch, is reimplemented byte-for-byte per tier (`src/revl/estop.py`, `backends/typescript/estop.ts`, the go, rust and java twins), so tiers cannot drift on what an armed latch means. The evidence supports four honoring tiers (py, go, rust, java), not five runtimes; see below.

## Contributions

1. A third teardown verdict `halted` with a stranded disposition (registered, not run, not dropped, keeps inverse and witness), and the rule that a halt is shaped like a crash so `revl recover` reconciles it (`docs/design/443-estop.md`, "Open question 3").
2. A Lean extension: G7 completeness and soundness hold for `.halted` unchanged with an empty replay set; the disposition trichotomy and the book-length partition hold under every verdict; two corollaries gained an explicit `settles` hypothesis, shown load-bearing by counter-instance and by an equation with no hypothesis (`bracket_replays_exactly_when_settling`).
3. A one-latch cross-tier protocol (contract E1 to E8 in `docs/design/443-estop-tier-contract.md`): one reader rule, every seam consults it, unarmed is free, an in-flight registry, one inventory line, an idle watcher, die where it stands, no self-halt.
4. A multi-process conductor that distinguishes populations (honoring tiers, no-seam tiers killed with residue UNKNOWN, static wasm) and counts UNKNOWN lines in the residue total, so the report is incomplete by exactly the processes it names.
5. An authority model: `estop` is its own operator verb, subject-scoped over the whole running composition, with no in-language surface, and `runtime.estop()` refuses without an operator token.
6. A halt is seen by other processes as peer death, not as a halt: consumers of a halted provider unwind gracefully by the existing R2/R3 rules.

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Erlang/OTP supervision and shutdown | ordered cooperative shutdown with timeouts, then brutal kill | the brutal path is named, accounted and typed as a verdict; the kill is paired with an inventory |
| Crash-only software (Candea and Fox) (citation to be checked) | stop by crashing; recovery is the only path | same shape on purpose (a halt looks like a crash to recovery), but the halt also publishes what is owed and which crossing is ambiguous, and Lean proves the books balance |
| Saga / compensation (Garcia-Molina and Salem) | compensating steps after failure | a halt runs no compensation; compensations are stranded and named |
| Circuit breakers (Hystrix, Resilience4j), feature flags as kill switches | refuse calls at instrumented sites | the check is placed at the crossing seams, including expression-position emits (issue #1504 tests, which skip without the pinned cordis fork), and the latch reader fails closed on a malformed latch |
| Kubernetes cordon/drain, Chaos Mesh | cooperative evacuation or fault injection | not an eviction; no workload code runs after the button |
| IEC 60204 emergency stop categories | hardware stop categories with defined residual energy | an analogous category split for software: stop without unwinding, with residual state enumerated |
| Two-phase commit uncertain state | in-doubt participants resolved by the coordinator | a single named in-doubt crossing, resolved by idempotency key or by hand (existing item 309 behaviour) |
| seL4 and verified-OS work | proofs about kernel behaviour | the proof is about the accounting table, not the host code; scope is narrower |

## Evidence on main

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Third verdict, kinds' dispositions | `formal/RevL/Semantics.lean:56-149` (`Verdict.halted`, `strandedUnder`, `disposition_trichotomy` at 135, `halted_strands_every_kind` at 147) | shipped | |
| Book lengths partition the stack under every verdict | `formal/RevL/Semantics.lean:279` (`book_lengths_add`) | shipped | |
| G7 for the halt column | `formal/RevL/Theorems/G7_LifoComplete.lean:233` (`estop_replays_nothing`), `formal/RevL/Theorems/G7_LifoComplete.lean:262` (`estop_strands_everything`), `formal/RevL/Theorems/G7_LifoComplete.lean:272` (`estop_strands_the_bracket`), `formal/RevL/Theorems/G7_LifoComplete.lean:293` (`settles_iff_not_halted`) | shipped | |
| Proof status table | `formal/STATUS.md:152-169`; 18 rows tagged "G7 / item 443" | shipped | all rows read "proved"; the Lean build was not run for this draft |
| Latch vocabulary, tier set | `src/revl/estop.py:42` (`TIERS_WITH_ESTOP = {py, go, rust, java}`), `src/revl/estop.py:58` (`TIERS_STATIC_ESTOP = {wasm}`) | shipped | ts not in the set |
| py seams | `backends/python/runtime.py:3097` (`_estop_check`), `backends/python/runtime.py:3208` (`estop`), `backends/python/runtime.py:3279` (`estop_from_latch`), `backends/python/runtime.py:3300` (`estop_residue`) | shipped | |
| py bridge refuses remote calls | `backends/python/bridge.py:885-894` | shipped | |
| go, rust, java readers and seams | `backends/go/placement_runner/estop/estop.go`; `backends/go/placement_runner/bridge/bridge.go:116`; `backends/rust/placement_runner/src/estop.rs`; `backends/java/placement/Estop.java`; `backends/java/test_estop_java.py` | shipped | native test suites exist; they were not run for this draft |
| ts reader and bridge seams | `backends/typescript/estop.ts`; `backends/typescript/bridge.ts:30-32`, `backends/typescript/bridge.ts:640`, `backends/typescript/bridge.ts:842` | partial | reader and seams landed; no watcher, not in `TIERS_WITH_ESTOP`; `docs/design/443-estop-node-tier.md` frames joining as an open architect decision |
| Expression-position emits are gated | `tests/test_estop_crossing_gate_1504.py` (9 tests; skip without the pinned cordis fork) | shipped | the file says a skip is not a pass |
| Conductor halts a placement and names every component | `tests/test_estop_conductor_443.py` (8 tests), `tests/test_estop_native_tiers_443.py` (7) | shipped | stubbed-child pattern |
| Core py behaviour | `tests/test_estop_443.py` (29 tests), `tests/test_estop_thread_safety_1487.py` (3) | shipped | |
| Recovery reads what neither discharge nor abort settled | `tests/test_estop_settled_by_recover_1477.py` (6) | shipped | |
| Operator authority | `src/revl/mcp/operator.py:133` (`revl_estop`: `estop`), `src/revl/mcp/session.py:3964` (`Session.estop`), `src/revl/mcp/session.py:3991` (`estop_report`) | shipped | |
| Residue kinds `estop-stranded`, `estop-ambiguous` | `docs/design/teardown-contract.md:539-545` | shipped | |
| Cross-tier conformance fixture `tck/estop/` | `docs/design/443-estop-tier-contract.md:176-205` | designed | `tck/` has no `estop` directory on main |
| wasm static inventory | `docs/design/443-estop-tier-contract.md` (per-tier table); `src/revl/estop.py:44-57` | partial | constants and population label exist; the projection code was not verified |

## Numbers that exist

- 18 formal-status rows tagged "G7 / item 443" (`formal/STATUS.md`). `docs/design/443-estop.md` says only that four further theorems pin the settling hypothesis.
- Test counts per file are listed above (29, 9, 8, 7, 6, 3). No latency, throughput or fault-injection numbers exist. `REVL_ESTOP_HALT_WINDOW` defaults to 2 s (`docs/design/443-estop.md`, conductor section); that is a configured bound, not a measurement.

## Paper outline

1. Introduction: the stop nobody models; commit, abort and what an operator actually needs.
2. Background: derived LIFO teardown, G7, R4, the WAL and `revl recover`.
3. The halted verdict: table, four guarantees and three non-guarantees.
4. Mechanization: trichotomy, partition, the settling hypothesis made load-bearing, the halt cut and at-most-one ambiguity.
5. One latch, many runtimes: E1 to E8, fail-closed, unarmed-free, seams, idle watcher.
6. The conductor and honest reporting of populations (honoring, killed, static).
7. Authority: operator verb, no in-language surface, peer-death semantics.
8. Evaluation: latency, fault injection, conformance across tiers.
9. Related work, limits.

## Threats to validity and limits

- The docs say the unwinding trade is real: handles, connections and leases stay held until exit or recovery. Brackets are closure-only on every tier, so recovery reports them as unreconstructible ("What stays open" in the tier contract).
- The formal layer is tier-independent and proves accounting over a model of the stack; it does not prove that any runtime's seams cover every crossing path. Issue #1504 shows a real miss that was fixed by test, which is evidence against claiming completeness.
- "Bounded latency" is a design property with a configured 2 s inventory window, not a measured one.
- The node tier "kept dispatching crossings until it died" under a placement halt (report text in `docs/design/443-estop.md`); wasm is static. A reader must not read "five runtimes" as uniform enforcement.
- A halted provider is seen as peer death by consumers; a halt does not propagate. Remote tasks on peers keep running (tier contract, "What stays open").
- The latch is a file: a hostile process with write access to the directory can arm it (denial of service) or remove it before a watcher reads it. The docs call the missing control socket a deliberate choice; no threat analysis exists.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 17 checked, 4 corrected.
