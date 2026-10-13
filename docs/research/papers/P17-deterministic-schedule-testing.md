---
id: P17
title: "Seeded Deterministic Interleaving Tests for Lifecycle Operations, With Auto-Mocks Derived From Declarations"
theme: effects-replay
kind: short
maturity: partial
status: "Seeded scheduler, shrinker and auto-mocks are shipped on the Python reference tier with tests; no bug-finding or coverage measurements, and the deadlock check has no test."
fused_with: P16
---

## Pitch
A seed is the tape a deterministic chooser reads at every scheduling decision, so a failing lifecycle interleaving is a short integer vector that replays to the same schedule, and a greedy shrink over that vector reached one non-canonical choice in the worked example.

## Abstract
Concurrent compositions of components fail for a reason that failure-point testing does not cover: independent lifecycle operations, activation and teardown of different components, run in an order the author never pictured. Existing schedule explorers (CHESS, PCT, Loom, Shuttle) need to control a nondeterministic runtime, and most capture-and-replay tools fix an order after the fact. We describe schedule testing in revl, a language whose reference runtime has no wall clock, no threads, and cooperative waits only. A seeded PRNG indexes the canonically sorted ready set at each decision; the sequence of chosen indices is the schedule, so the same seed replays the identical interleaving. For each completed schedule the harness checks residue (reusing the fault sweep's four snapshot deltas plus unreleased host resources), deadlock (a fiber that can never activate), and stability of the observable end state against the canonical sequential run, which includes the order of irreversible emissions. A failing choice vector is shrunk by a greedy pass in the delta-debugging style, toward the canonical index 0, and printed as the reproduction. Separately, the auto-mock facility derives in-memory providers from service declarations, where emissions are counted and never crossed; schedule testing does not yet run against those mocks. The scheduler ships on the Python reference tier with 17 tests; its alphabet is two operations (activate, teardown), exploration is sampled rather than exhaustive, and the capability and use-after-withdrawal checks are not yet substantive. We report the design, the checked properties, the limits, and a worked two-consumer example whose emission-order divergence minimizes to a single non-canonical choice.

## Problem and claim
Lifecycle bugs in a plugin-style composition (leaked registrations, order-dependent emissions, stranded consumers) depend on which independent component comes up or goes down first. A fault sweep that splices a `fail` into every step finds failure points but runs one fixed order. Testing interleavings normally needs either a controlled scheduler over a nondeterministic runtime, or flaky stress runs.

The claim: when the runtime is deterministic by construction, interleaving testing reduces to choosing an order for the harness-issued lifecycle operations. A seed then is a complete, replayable description of the schedule, the ready set has a canonical order so index 0 means the same thing on every replay, and the properties to check are the ones the language already defines oracles for (residue, deadlock, observable end state).

The claim is deliberately narrow. It covers two lifecycle atoms on one tier, with sampling, not a proof that no interleaving violates a property. The design doc says so itself (see limits).

## Contributions
1. A seed-as-tape scheduler: a seeded PRNG indexes the ready set sorted by (operation-kind rank, fiber load-order index, name), with a canonical always-index-0 baseline and a replay chooser built from a saved choice vector (`src/revl/schedule.py:92-105`, `src/revl/schedule.py:199-234`).
2. A per-schedule property check over completed schedules: residue-free, no deadlock, stable observable end state versus the canonical run, where the fingerprint includes the ordered emission sequence (`src/revl/schedule.py:269-325`, `docs/schedule-testing.md:62-92`).
3. A greedy shrink over the choice vector in the delta-debugging style: drop trailing choices, then reset each choice toward index 0, keeping a change only if it fails with the same signature (`src/revl/schedule.py:463` (`minimize`), `docs/schedule-testing.md:94-115`). The code is one-choice-at-a-time, not ddmin.
4. A teardown gate that restricts explored schedules to valid reverse-dependency orders, so every explored schedule is a legal one (`docs/schedule-testing.md:49-55`).
5. Auto-mocks: a typed, seeded, deterministic in-memory provider per `service` declaration, with `emission` operations counted and not crossed (`src/revl/mocks.py:1-34`, `src/revl/mocks.py:97-158`, `docs/auto-mocks.md:1-10`).

## Related work
| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| CHESS (Musuvathi et al., OSDI 2008) (citation to be checked) and PCT (Burckhardt et al., ASPLOS 2010) (citation to be checked) | Systematic or randomized scheduling of threads with preemption bounds, for finding concurrency bugs in programs with a nondeterministic scheduler | The runtime has no threads or wall clock, so no scheduler interposition is needed; the schedule is the order of harness-issued lifecycle operations, and the oracles are lifecycle properties (residue, withdrawal) rather than data races |
| Loom and Shuttle (Rust) | Permutation testing of a program's atomics and threads under a model scheduler | Operates on declared compositions, not on user code with shared memory; the alphabet is activate and teardown of declared components |
| FoundationDB deterministic simulation; Antithesis | Whole-system deterministic simulation with fault injection and replay from a seed | Same replay-from-seed idea; revl gets determinism from the language runtime rather than a simulated OS or hypervisor, so the claim is much smaller in reach and much cheaper to run |
| Jepsen | Black-box fault and partition testing of distributed systems with history checkers | Not distributed, and checks declared lifecycle invariants, not linearizability |
| TLA+ and explicit-state model checking | Exhaustive exploration of an abstract model | Executes the real py runtime for every schedule; sampled, not exhaustive, with no partial-order reduction yet |
| Property-based testing with shrinking (QuickCheck, Hypothesis) | Shrinks failing inputs | Shrinks a choice vector, the same idea the fault module already applies to test arguments (`docs/schedule-testing.md:96-99`) |
| Mock generation from interfaces (Mockito, mock servers from OpenAPI) (citation to be checked) | Stubs from a type or schema, usually returning fixed values | Responses come from the type-directed generators in `src/revl/fault.py` that `src/revl/mocks.py:53` (`gen_value`) reuses, seeded per operation; emission-classified operations are counted rather than executed, because the language already classifies them |

## Evidence on main
Tree: revl main at commit 45bec431f.

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| `--schedule-seeds N` samples N interleavings plus a baseline; `--schedule-seed S` replays one | `docs/schedule-testing.md:13-16`; `src/revl/schedule.py:513-556`; `src/revl/test.py:1424` (`schedule_command`) | shipped | Seeds are `range(N)` (`src/revl/schedule.py:536`), so "sampled" means seeds 0..N-1 |
| Seed is a tape over the canonically sorted ready set | `docs/schedule-testing.md:26-36`; `src/revl/schedule.py:92-105,202-215` | shipped | |
| Same seed replays the identical schedule | `test_same_seed_reproduces_the_same_schedule` (`tests/test_schedule_testing.py:173`) | shipped | Compares choices, atoms, emissions and fingerprint, not bytes; needs cordis-py, otherwise skipped |
| Different seeds reach different interleavings | `test_seeds_explore_distinct_interleavings` (`tests/test_schedule_testing.py:186`) | shipped (one assert is vacuous) | 40 seeds on a 3-component fixture. The `or canonical == ...` clause is always true, so only `len(schedules) > 1` tests anything; that the canonical order is reachable is not tested |
| An order-dependent bug is found, minimized and reproducible | `test_order_dependent_issue_is_found_and_reproducible` (`tests/test_schedule_testing.py:200`) | shipped | Asserts the minimized vector has exactly one non-zero choice |
| An order-invariant composition passes every seed | `test_order_invariant_composition_passes_every_seed` (`tests/test_schedule_testing.py:221`) | shipped | 60 seeds plus baseline = 61 schedules |
| Residue-free check per completed schedule | `src/revl/schedule.py:269`; `test_completed_schedule_is_residue_free` (`tests/test_schedule_testing.py:231`) | shipped | Reuses `src/revl/fault.py` snapshot deltas |
| Deadlock check | `src/revl/schedule.py:315-318`; `src/revl/schedule.py:161` (`stuck_fibers`) | partial | Code on main; no test touches it. The `test_check_properties_*` tests cover only residue (`tests/test_schedule_testing.py:144`) and unstable state (`:134`), not deadlock |
| Stable final state including emission order | `src/revl/schedule.py:255-266,323-324`; `test_fingerprint_folds_emission_order` (`tests/test_schedule_testing.py:124`) | shipped | Strict equality only, so it flags any order dependence. The commutativity skip that design open question 2 recommends (`docs/design/295-schedule-testing.md:319-330`) is not implemented: no code reads a `commutative` flag in `src/revl/schedule.py`, and line 334 names it only inside a message |
| Teardown order correctness | `docs/schedule-testing.md:49-55` | shipped by construction | The gate is tested (`test_teardown_gated_on_dependents`, `tests/test_schedule_testing.py:84`); the order itself is not checked as a property, since explored schedules cannot violate it |
| No use-after-withdrawal | `src/revl/schedule.py:294-305` | placeholder | The function returns an empty list; the docs describe it as a guard for future finer atoms (`docs/schedule-testing.md:87-92`) |
| Per-fiber capability violation check | `docs/schedule-testing.md:57-60`; `docs/design/295-schedule-testing.md:269-271` | designed (conditional) | Ships in v1 only if the runtime enforces per-fiber capability at emit, otherwise the first follow-on (`docs/design/295-schedule-testing.md:265-271`, open question 3) |
| Intra-activation atoms (resume, complete, fire) | `docs/schedule-testing.md:57-60` | designed | Follow-on |
| Exhaustive or partial-order-reduced exploration | `docs/design/295-schedule-testing.md:280-286` | designed | Follow-on, framed as the upgrade from "sampled" to "none violates" |
| Py tier only; missing runtime is a skip, not a pass | `docs/schedule-testing.md:117-126`; `test_command_skips_without_cordis` (`tests/test_schedule_testing.py:153`) | shipped | |
| Auto-mocks per service declaration, typed and seeded | `src/revl/mocks.py:53-60`; `docs/auto-mocks.md:1-10`; `test_gen_value_is_seeded_deterministic` (`tests/test_auto_mocks.py:368`) | shipped | |
| Emissions counted, not crossed | `src/revl/mocks.py:97-158`; `tests/test_auto_mocks.py:605` | shipped | |
| Mock world is reproducible across runs | `test_mock_world_is_reproducible_across_runs` (`tests/test_auto_mocks.py:627`) | shipped | |
| Property tests derived from interfaces | not located in `docs/auto-mocks.md` or `src/revl/mocks.py` | not found | Not claimed |

## Numbers that exist
- `tests/test_schedule_testing.py` has 17 test functions (counted by `rg -c "^def test"`). `tests/test_auto_mocks.py` has 29. Whether they pass in CI was not checked here.
- The fixtures: ORDERED (3 components) and CLEAN (3 components) in `tests/test_schedule_testing.py:33-47`. The doc's worked example reports a minimized vector `[0, 1, 0, 0, 0, 0]` (`docs/schedule-testing.md:105-108`); the test asserts exactly one non-zero entry.
- Sampling sizes used in tests: 40 and 60 seeds. Default is 200 (`src/revl/schedule.py:510`).
- No measurements of bug-finding rate, schedule coverage, minimization ratio or runtime cost.

## Paper outline
1. Introduction: lifecycle interleavings as a missing test axis; the claim and its narrow scope.
2. Background: the deterministic py reference runtime, the fault sweep and its oracles.
3. Design: atoms, ready-set order, seed tape, teardown gate, properties.
4. Minimization and reproduction: delta-debugging over the choice vector, the worked example.
5. Auto-mocks: derived providers, counted-not-crossed emissions, how they would compose with the scheduler.
6. Evaluation: mutants, detection rate, coverage against full enumeration (to be run).
7. Related work, limits, and the partial-order-reduction follow-on.

## Threats to validity and limits
- Sampled, not exhaustive. The design doc: v1 "does not enumerate the full state space or apply partial-order reduction" (`docs/design/295-schedule-testing.md:261-264`). A clean run says "we did not hit one", not "none exists".
- Two atoms only. The finer turns (resume of an in-flight await, completion of a Job, firing of a timer) are the documented follow-on (`docs/schedule-testing.md:57-60`). Whether most real concurrency bugs live there is not measured.
- Capability and use-after-withdrawal checks are not substantive today (see the evidence table) and are not claimed.
- The stability property is strict equality with the sequential run. Two independent components that each emit once will be reported as divergent, since the fixture ORDERED is exactly that. Whether this is a bug or an intended order-independence is the author's call; the design lists this as open question 2 (`docs/design/295-schedule-testing.md:319-330`).
- Python tier only; determinism rests on the cordis-py cooperative substrate. Other tiers are not covered.
- A comment in the fault module still lists schedule exploration as out of scope (`src/revl/fault.py:597-600`); it is stale relative to this feature.
- The py prototype's dependency on an earlier runtime slice is described in `docs/design/295-schedule-testing.md:102-119`. The code exists, so the paper cites the code, not the roadmap tick (`docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:595`).

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 30 checked, 12 corrected.
