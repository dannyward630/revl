---
id: P15
title: "What Survives kill -9: The Accumulator as a Write-Ahead Log With Offset, Settled and Residue Verdicts"
theme: effects-replay
kind: full
maturity: shipped-evidence
status: "WAL, recovery, call-tier re-issue and model-versus-world labelling are shipped with crash tests on five tiers and a differential check against a Lean model; no overhead numbers or real-signal kill campaign yet."
fused_with:
---

## Pitch
Most undo systems promise to reverse everything; revl's crash recovery says, per effect, which ones are moot, which can be re-issued from a captured description, and which remain as residue, and it labels a recovery run against a model as modelled, not performed.

## Abstract
A process that dies with `kill -9` takes its in-memory undo closures with it, so the usual picture of crash recovery as "run the inverses again" is wrong. We describe the recovery design of revl, a language whose runtime already keeps an ordered accumulator of committed effects, each paired with its inverse. The accumulator is persisted as a write-ahead log (JSON Lines, one fsync per entry). A fresh process reads it and classifies only boundary state that outlives the dead process: an emission that left the process, or an acquire whose resource persists. In-process inverses are reported as moot. An inverse is re-issued only if it is reconstructible from a description (a named call with captured arguments); closure-only inverses are reported as residue and never pretended to run. Each emission ends as offset (its compensation ran), settled, or residue. Re-issue is graded by three register tiers (read, keyed, declared) and anything unknown gets one fenced at-most-once attempt. Recovery run without the real composition executes against an in-memory model and says so in the verdict and the exit status. On main today, crash tests exist for the Python tier (simulated kill) and for go, java, rust and wasm (real process exit after fsync), and a Lean model of the commit/abort decision is checked against the shipped recovery code on an enumerated corpus of 1620 logs (the model was edited once after 60 of them disagreed; see limits). We state what is not covered: power loss, and a crash between a witnessed mutation and its log entry.

## Problem and claim
Write-ahead logging in databases logs "about to do X, and how to undo it", and recovery replays or reverses the log. Application-level effect systems (sagas, workflow engines, Python `contextlib`-style unwinding) usually either keep their undo in process memory, which is gone after a crash, or persist opaque callbacks that cannot be re-run in a new process.

The claim is narrower and more honest. After a crash only the boundary state matters (`docs/crash-recovery.md:117-150`). Recovery is sound to attempt for an effect only if its inverse can be rebuilt from a description, a named operation plus concrete arguments (`docs/crash-recovery.md:152-190`). Everything else must be reported, not guessed. The verdict is therefore three-valued per crossing (offset, settled, residue) and the report states which world it ran against.

A second claim is about the process, not the algorithm: because the accumulator was already a typed list of (effect, inverse) pairs with explicit non-invertible emissions, the WAL costs the language no new concept. The only new language-level requirement is the reconstructible-from-description rule.

## Contributions
1. The accumulator as a write-ahead log: JSON Lines, fsync per entry, fsync failure fail-closed with truncation of the failed entry, torn tail sealed before any append (`docs/crash-recovery.md:14-65,193-290`).
2. The reconstructible-from-description requirement and the `inverse_descriptor()` split between reconstructible and closure-only inverses, with closure-only inverses surfaced as residue (`docs/crash-recovery.md:152-190,736-749`).
3. Two recovery paths decided by a durable marker: roll forward when activation completed (with steady-state crossings after the marker reported as residue), roll back newest-first when it did not (`docs/crash-recovery.md:403-495`).
4. A call-tier taxonomy for safe re-issue (read, keyed, declared, absent) and a single re-issue seam `World.reissue`, with at-most-once fences written before the attempt (`docs/crash-recovery.md:292-375`).
5. "The model is not the world": every verdict carries `world: model|real`, modelled calls are marked `[modelled, not performed]`, a model run never spends a fence, and exit code 3 means clean-in-the-model but nothing reconciled (`docs/crash-recovery.md:495-543`).
6. Opt-in `--require-settled-wal` refuses to start on a WAL with unsettled emissions, and `revl recover --operator-resolved SEQ` logs a human acknowledgement without claiming an undo (`docs/crash-recovery.md:69-93`).
7. Evidence: crash tests on five tiers and a differential check of the recovery verdict against a Lean model on 1620 enumerated logs (see Evidence on main).

## Related work
| prior system or line of work | what it does | what revl does differently |
|---|---|---|
| ARIES (Mohan et al., 1992) (citation to be checked) | redo/undo logging with LSNs, compensation log entries, for a DBMS that owns its pages | The log is application-level; the "page" is the outside world, which recovery cannot read back. Recovery reports residue instead of assuming it can redo. |
| Crash-only software (Candea and Fox, HotOS 2003) | one stop path (crash), one start path (recover) | Same stance on start/stop. revl adds a verdict about what the restart cannot repair. |
| Sagas (Garcia-Molina and Salem, 1987) and compensating transactions | compensations chosen by the application | Compensations are checked at compile time to exist (G4 inverse-or-emit), and recovery pairs each emission with the compensation that offset it (`offsets` field, `docs/crash-recovery.md:637-645`). |
| Temporal / durable execution (event sourcing, deterministic replay) | recovery by replaying deterministic code from history | revl never re-enters the dead runtime; it re-issues named calls from the log. No determinism requirement on user code, at the price of residue for closures. |
| ALICE (Pillai et al., OSDI 2014), CrashMonkey (Mohan et al., OSDI 2018) | find crash-consistency bugs in applications and file systems | Those tools test an application's use of the file system. Here the recovery engine itself is tested against enumerated logs (formal A8 row). |
| Erlang let-it-crash, supervision trees | restart policy, state loss accepted | Adds a typed account of which external effects the lost state had already caused. |
| Idempotency keys (Stripe, Kleppmann DDIA ch. 11) | client-supplied key lets the server dedupe | The `keyed` register tier is exactly this contract; the declared and absent tiers cover the cases without it. |

## Evidence on main
Tree: revl main at commit 45bec431f.

| claim | path:line or test | status | note |
|---|---|---|---|
| Accumulator persisted as a WAL, fsync per entry | `docs/crash-recovery.md:193-200`; `backends/python/replay.py:2279` (`WriteAheadLog`) | shipped | JSON Lines; header, generation, effect, descriptor entries |
| fsync failure stops the crossing; failed entry truncated; opt-out logged | `docs/crash-recovery.md:25-65`; `tests/test_wal_fsync_fail_closed_2345.py` | shipped | opt-out is `--allow-unsynced-wal` (py) or `REVL_WAL_ALLOW_UNSYNCED=1` (go, rust, java; wasm at `src/revl/run_wasm.py:128`) |
| Torn tail sealed before append | `src/revl/wal.py:342-343`; `tests/test_wal_torn_tail_535.py` (8 tests) | shipped | issue 535: unsealed append merged a fence into the torn line and re-ran an inverse |
| Emission start/complete/failed entries, "failure does not prove nothing reached the world" | `docs/crash-recovery.md:14-24`; `tests/test_wal_emission_start_*_2345.py` | shipped | py tier; go/rust/java wrap `extern emission fn` the same way (`docs/crash-recovery.md:36-50`) |
| `--require-settled-wal` | `src/revl/run.py:112,1239,2690`; `docs/crash-recovery.md:69-76` | shipped | py single-process backend only (`src/revl/run.py:2694`) |
| Operator acknowledgement | `docs/crash-recovery.md:78-85`; `tests/test_emission_settlement_2183.py:160` (writes `operator-resolved` entries); `tests/test_recovery_seqless_settled_2231.py` | shipped | tests named, not re-run |
| Reconstructible vs closure-only inverse descriptors | `backends/python/replay.py:2050` (`inverse_descriptor`), `:2416` | shipped | |
| Outlives-the-process policy is stated and defaults to unknown | `backends/python/replay.py:1977` (`_OUTLIVES_HINTS`); `docs/crash-recovery.md:140-150` | shipped | a name-hint policy, see limits |
| Roll forward / roll back / steady-state residue | `src/revl/recovery.py:793` (`_roll_forward`), `:297` (`recover`), `:632` (`_steady_state_residue`); `tests/test_crash_recovery.py` (39 tests) | shipped | |
| Offset pairing for compensated emissions | `src/revl/recovery.py:2073-2210` (`offset_by`) | shipped | |
| Three call tiers plus absent, re-issue seam | `docs/crash-recovery.md:292-375`; `src/revl/recovery.py:96` (`_replay_tier`), `:1517` (`_reissue_permitted`); `tests/test_idempotent_inverse_309.py` (25 tests) | shipped | `_replay_tier` returns read, free (declared) or fenced, and does not promote `keyed` (`src/revl/recovery.py:96-110`); keyed is a forward re-issue concept. `shape-proven` was removed (`docs/crash-recovery.md:303-316`), not built |
| Model vs real world labelling, exit codes 0/1/3 | `docs/crash-recovery.md:495-541` | shipped | tests not individually opened for each exit code |
| Real-process crash on go, java, rust, wasm | `tests/test_go_crash_recovery.py` (2 tests, `os.Exit`), `tests/test_java_crash_recovery.py` (4, `Runtime.halt`), `tests/test_rust_crash_recovery.py` (2, `process::exit(137)`), `tests/test_wasm_crash_recovery.py` (2, `os._exit`) | shipped, toolchain-gated | each skips with a reason if the toolchain is missing |
| Python tier crash test is simulated | `tests/test_crash_recovery.py:14,214` | shipped | "a simulated kill -9 mid-activation" writes the WAL and drops memory; no real signal |
| Tier-agnostic reader agrees with py writer | `tests/test_wal_core_agrees_with_py_replay.py` (6 tests) | shipped | |
| A8 commit/abort decision and at-most-once across crash cuts, as Lean theorems | `formal/RevL/Theorems/A8_WalDischarge.lean:103-440` | shipped | the file itself marks several theorems "specification-agreement" or "definitional" (header lines 40-58) |
| Verdict differential-tested on 1620 logs | `formal/STATUS.md:66,69`; `formal/harness/diff_corpus.py:4972-5060` | shipped | enumerated: 9 shapes, depth up to 2 (54 content sequences) x 3 discharge x 2 fence x 5 trailers = 1620, by arithmetic from `_WAL_SHAPES`, `_WAL_DEPTH`, `_WAL_TRAILERS` |

## Numbers that exist
- 1620 enumerated WAL scenarios where the outcome, applied set and residue of `recovery.recover` agree with the Lean model: `formal/STATUS.md:66`. The sample is exhaustive over the stated shape space, not a sample of real crashes.
- Test counts by function name (not pass rates; nothing was re-run): `tests/test_crash_recovery.py` 39, `tests/test_wal_torn_tail_535.py` 8, `tests/test_idempotent_inverse_309.py` 25, go 2, java 4, rust 2, wasm 2.
- Lean A8 file: 21 top-level `theorem` declarations. `formal/STATUS.md:66` gives 18 in its theorems column. The two counts do not match and are not reconciled.
- No performance numbers (WAL overhead per effect, fsync cost, recovery time) exist.

## Paper outline
1. Introduction: closures die with the process; what a restart can honestly say.
2. Background: the accumulator, inverse-or-emit (G4), compensation is not inversion.
3. The WAL: entry format, durability rules, torn tails, fail-closed fsync.
4. Reconstructible from description: descriptors, closure-only, the outlives policy.
5. Recovery: roll forward, roll back, steady-state residue, offset pairing, nested crossings and placement runs.
6. Safe re-issue: call tiers, fences, the World seam, the operator knob.
7. Model versus world: labels, exit codes, fences never spent by a model run.
8. Evaluation: crash tests on five tiers, the 1620-log differential against the Lean model, overhead (not yet measured), real-kill campaign (not yet run).
9. Limits and related work.

## Threats to validity and limits
- The Python crash test is a simulated kill (`tests/test_crash_recovery.py:14`). The other four tiers use a clean process exit after fsync, not SIGKILL and not power loss.
- `docs/crash-recovery.md:736-749` says recovery does not promise state was restored, does not reconstruct closure-only inverses, and does not undo a bare emission.
- Recovery without `--composition` runs against `DictWorld`; the verdict "is a proof about the model" (`docs/crash-recovery.md:492`; the no-`--composition` default is at `:502`).
- The Lean model covers the abort path only; the roll-forward `flush-residue` surface, cascading abort and escrow are "not covered and not claimed" (`formal/STATUS.md:66,69`).
- The 1620-log agreement was reached by editing the model. `formal/STATUS.md:1685` states that 60 of the 1620 scenarios disagreed (the model called a legacy `effect` re-issue clean where `recover` fences and reports residue) and that the model was changed to match the reference. The oracle found a real divergence, but the agreement reported is post-fix, not an independent prediction.
- The 1620 logs are enumerated at depth 2; deeper interactions are untested by that corpus.
- Several Lean theorems are specification-agreement or definitional by the file's own account, so they pin drift rather than prove depth.
- Durability is "a floor rather than a theorem" in the Lean file: power loss and fsync reaching disk are host obligations that no in-tree test settles. A witnessed mutation whose log entry is written after the forward extern returns is not covered (`formal/RevL/Theorems/A8_WalDischarge.lean`, header, "Not covered").
- `--require-settled-wal` and the opt-out flag are py-single-process only.
- The outlives-the-process decision is name-based and the language "cannot know this in general" (`docs/crash-recovery.md:145-150`).
- No baseline (saga engine, persisted closures) has been run on the same crash scenarios.

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 45 checked, 7 corrected.
