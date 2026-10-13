---
id: P10
title: Witnessed-Inverse Externs: Transactional Host Mutations with Checked Undo
theme: effects-replay
kind: full
maturity: shipped-evidence
status: Mechanism and filesystem catalog ship on the Python tier with a dense test base; the TypeScript tier is partial (weaker guard, no directory-fd syscalls); no overhead or corpus-scale evaluation yet.
fused_with: P12
---

## Pitch

An extern that ships with its own checked inverse makes a host mutation transactional: commit keeps it, abort undoes it newest-first, and the line between reversible and irreversible is something the program engineers rather than something the world fixes.

## Abstract

Languages that track effects classify host actions as irreversible unless the programmer writes a bracket or a compensation, and an agent that edits files therefore asks for approval on every write. We introduce witnessed-inverse externs. A `witnessed[fs]` extern returns a witness and declares an inverse; the compiler registers the inverse automatically, only on the success branch, as a third kind of teardown entry beside acquire and compensate. Unlike an acquire, a witnessed inverse does not run on a clean unload: commit discharges it and drops the witness, abort replays it newest-first in one stack with the bracket entries. The inverse must itself be a host-local, non-emitting, non-witnessed call and its witness must be serializable data, so a crashed session can replay it from a write-ahead log. We describe the design, a filesystem catalog (write, rm, move, mkdir) with copy-on-write preimage capture, and the runtime seam on the Python reference tier. We report what building it taught us: the first runtime replayed mid-session inverses in registration order and silently destroyed pre-session data while reporting no residue; a host-bound registration path registered the inverse nowhere; and a restore that installed whatever sidecar it found could be redirected by a same-user writer. Each became a regression test, and the fixes are stated as inverse-identity checks bound to the bytes captured. We state the limits: reversal does not undo observation, the guard is a runtime refusal not containment, and the ts tier cannot express directory-fd walks.

## Problem and claim

Effect systems classify host actions as reversible or irreversible by declaration (no agent framework was surveyed). The consequence is that every file write counts as an irreversible crossing and needs a prompt, even though a snapshot and a rename would make it undoable. The design doc states the need directly: "every mutation today is an emission, so every one is irreversible by declaration and prompts for approval" (`docs/witnessed-fs.md:3-8`).

The claim: a host mutation declared together with a witness type and an inverse can be treated as a transaction entry. Three properties make this precise. (1) It is not an acquire: the inverse does not replay on a clean unload, and commit discharges it (`docs/design/243-witnessed-externs.md:9-21`). (2) The inverse is checked: it must be classified non-emission and non-witnessed, which excludes infinite regress, and it must be idempotent on replay (rules 3 and 5 of the design doc). (3) The restore installs only the sidecar it captured, which the design checks by (dev, ino) and ctime identity (`docs/witnessed-fs.md:433-482`); this holds under the stated premise that the host holds exclusive sidecar-directory write ownership (`docs/witnessed-fs.md:224-226`).

The argument is that this is a language feature with a runtime contract, not a library, because the compiler owns the Ok-conditional registration and the teardown order.

## Contributions

1. A third reversal form with explicit semantics: abort-only replay, commit-time discharge and witness GC, one LIFO stack shared with bracket entries (`docs/design/243-witnessed-externs.md:9-21`; Python seam at "Slice 2a as implemented", points 1-3; test `tests/test_witnessed_abort_lifo.py:252`).
2. Static rules: effect-position only, Ok-conditional registration, inverse classification, serializable witness (design doc, "Correctness rules 243 must enforce").
3. A filesystem catalog as the first instance, with copy-on-write preimage capture for write and rename-into-garbage for rm (`docs/witnessed-fs.md:20-53`; `stdlib/fs.rvl:349`, `:401`, `:429`, `:448`).
4. Mid-session per-tool-call registration with newest-first drain, and the data-loss defect that motivated it (design doc, point 5; `tests/test_witnessed_abort_lifo.py:131-210`).
5. Inverse-identity checks and receipts: restore installs only the sidecar it captured; a write receipt carries previous and new digests bound onto the witness (`docs/witnessed-fs.md:433-482`, `:378-432`; `tests/test_fs_restore_sidecar_identity_1016.py`; `tests/test_fs_witnessed_receipt_binding_623.py:108`, `:130`, `:198`).
6. A statement of where the guarantee stops, taken from the docs (`docs/witnessed-fs.md:604-645`).

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Sagas (Garcia-Molina and Salem, SIGMOD 1987) (citation to be checked) | Long transactions as steps with programmer-written compensations, run after failure. | The compensation is declared on the extern, registered by the compiler, replayed in one LIFO order, and checked for classification (`src/revl/lower.py:3911-3968`); idempotence is declared, and its checking is a designed gate, not shipped. Commit discharges it. |
| Transactional file systems (Windows TxF, deprecated) and snapshot file systems (Btrfs, ZFS, APFS clones) (citation to be checked) | Provide atomic multi-file operations or point-in-time snapshots at the OS layer. | Works on a stock file system, per tool call, in-process. It uses APFS `clonefile` only as a cheap preimage when available and falls back to a copy (`docs/witnessed-fs.md:46-50`). |
| Software transactional memory | Rolls back memory effects by logging. | The effects are host mutations that STM cannot see; the log is a durable WAL of named inverse calls with captured arguments (design doc rule 4). |
| Resource brackets (Haskell `bracket`, Python context managers, Java try-with-resources) | Release a handle on every exit. | A bracket releases on clean exit too; a witnessed entry must not (design doc table, lines 9-21). Lowering a mutation as a bracket would restore deleted files on every successful run. |
| Container image layers, Nix, rollback-capable shells | Make a whole environment roll-back-able by copy-on-write layers. | Reversal is scoped to the individual calls of one session, with an enumerated residue list for what is not reversible. |
| Database undo logs (ARIES-style) (citation to be checked) | Per-entry undo with LSNs for crash recovery. | Same family. The difference is that the log entry is a typed call on a host extern, and the language admits only inverses that pass the classification rule. |
| Cordis disposer model (the runtime revl's Python tier builds on) | Newest-first disposal of effects on unload. | Adds the transactional entry kind and the commit-versus-abort discriminator on top of the same stack. |

No benchmark comparison against these exists.

## Evidence on main

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Witnessed is a fourth extern class; contextual keyword; capability-scoped | `docs/design/243-witnessed-externs.md:24-45`, `:115-123`; `src/revl/parser.py:109-119` | shipped | |
| Imported witnessed externs parse | `src/revl/parser.py:7005-7022` | shipped | contradicts `docs/witnessed-fs.md:646-668`, which still calls it deferred; the gate is deferred to lowering |
| Entry kind: abort replays, commit discharges and GCs | design doc "Slice 2a as implemented" points 1-3; runtime `Frame.transactional` at `backends/python/runtime.py:3868`; `tests/test_witnessed_wal_recover.py:91`, `:110` | shipped (py) | |
| Single LIFO stack with bracket and transactional entries | `tests/test_witnessed_abort_lifo.py:252` asserts order `w4 a3 w2 a1` | shipped (py) | |
| Mid-session inverses parked and drained newest-first | `backends/python/runtime.py:3930` (`transactional_method`), `:3372`; `tests/test_witnessed_abort_lifo.py:131`, `:153`, `:174`, `:192` | shipped (py) | design doc says rust, java and wasm are LIFO "by construction" and that ts and go drain their parked list newest-first (`docs/design/243-witnessed-externs.md:176-210`); not verified on those tiers |
| Catalog: write, rm, move, mkdir with Result witnesses and Ok-conditional registration | `stdlib/fs.rvl:349-448`; `tests/test_fs_stdlib.py:248`, `:261`, `:272`, `:282`, `:298` | shipped (py) | |
| Commit persists, abort reverts residue-free, out-of-root write refused | `tests/test_fs_stdlib.py:310`, `:335`, `:357` | shipped (py) | |
| Residue lists enumerate committed and aborted crossings | `tests/test_fs_stdlib.py:389`, `:421` | shipped (py) | |
| Inverse identity: restore installs only the captured sidecar | `docs/witnessed-fs.md:433-482`; `tests/test_fs_restore_sidecar_identity_1016.py` | shipped (py); ts test file exists but was not run | ts test named in the doc: `backends/typescript/tests/fs_restore_sidecar_identity.test.ts` |
| Receipt binding with prev and new digests, expected-before guard | `docs/witnessed-fs.md:378-432`; `tests/test_fs_witnessed_receipt_binding_623.py:108-262` | shipped (py), opt-in surface `revl.fs` | |
| Host-bound registration path fixed | `docs/witnessed-fs.md:566-603`; `tests/test_fs_witnessed_ambient_abort_1071.py` | shipped | test file name taken from the doc; not opened |
| A local mutating inverse is verified, not claimed | `docs/crash-recovery.md:375-399` | designed | the doc proposes a combined register and inverse-roundtrip evidence floor and states local mutating inverses are "permanently declared" under the strong floor; no test for the combined rule was found |
| Six-tier teardown of witnessed inverses | `CHANGELOG.md:166-172` | claimed | the changelog says six tiers; the fs docs describe the confinement pass as shipped on py and ts (`docs/witnessed-fs.md:604-645`). The six-tier claim is unverified. |

## Numbers that exist

- Test counts for the fs surface: `tests/test_fs_stdlib.py` has 15 test functions; `tests/test_witnessed_abort_lifo.py` has 5 (3 named reproducers, one deep overlapping chain, one mixed bracket and transactional unwind); `tests/test_fs_witnessed_receipt_binding_623.py` has 20; `tests/test_fs_confinement_escapes.py` has 15. These are counts of test functions, not pass rates.
- Bug counts from the docs: at least five distinct defects found after the first implementation (FIFO drain, host-bound registration, restore sidecar identity #1016, unrm garbage sidecar #1038, guarded host inverse #1054), plus the confinement list covered in P11. These come from the documents, not from a systematic audit.
- None yet: overhead of preimage capture (clonefile versus copy), WAL size per call, time to abort versus number of mutations, and a corpus-scale abort-correctness result.

## Paper outline

1. Introduction: reversibility as an engineered property; why a write needs a prompt today.
2. The three reversal forms: acquire, compensate, witnessed. Table of replay on unload, abort, commit.
3. Language surface and static rules: classification of inverse, Ok-conditional registration, witness as data.
4. Runtime contract: commit versus abort discriminator, one LIFO stack, parked mid-session entries, WAL descriptors.
5. The filesystem catalog: preimage capture, garbage directory, receipts.
6. What broke: FIFO drain data loss, host-bound registration, sidecar identity. Each as a failing test, then the invariant.
7. Evaluation: overhead, abort correctness corpus, recovery sweep (to be done).
8. Limits and related work.

## Threats to validity and limits

From `docs/witnessed-fs.md:604-645` (paraphrased where short):
- "Reversal does not undo observation": a concurrent reader already saw the intermediate state.
- A hardlinked target is refused, not written, so legitimately hardlinked files cannot be witnessed-written.
- A write needs read access to its target, because the preimage is captured from the same descriptor.
- Confinement is a runtime refusal, not physical containment; it holds only for ops that go through the catalog bodies.
- The ts tier has no `*at()` syscalls: it walks components with `lstat` and narrows but does not close an intermediate-directory swap around a rename. The ts preimage is a copy, not an O(1) clone.

Further, from the same documents:
- The docs say the host must hold "exclusive sidecar-directory write ownership" for committed-sidecar cleanup, and that no boolean argument can prove this premise (`docs/witnessed-fs.md:224-226`).
- Process-lifetime root binding has no unbind, and post-crash recovery must re-establish the root independently (`docs/witnessed-fs.md:156-165`).
- A lying `undo idempotent` would be caught only by the proposed inverse-roundtrip evidence floor, which is designed and not shipped (`docs/crash-recovery.md:375-399`).
- The catalog is one domain (files). Shell and HTTP lowering is the subject of P12.
- The bug list comes from the project's own dogfooding, so it may undercount defects no one hit.
- The design doc's status line still reads "Implementation in slices" (`docs/design/243-witnessed-externs.md:3`) although the later slices have landed; this draft follows the code.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 70 checked, 9 corrected.
