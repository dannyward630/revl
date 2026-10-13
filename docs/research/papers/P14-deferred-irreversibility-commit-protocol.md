---
id: P14
title: "Deferred Irreversibility: A Session Commit Protocol That Enumerates What Cannot Be Undone"
theme: effects-replay
kind: full
maturity: partial
status: "Commit protocol, deferral queue, abort and crash recovery are shipped on the Python tier with tests and a small measurement; witness retention is design-only and no external evaluation exists."
fused_with:
---

## Pitch
Instead of asking a human to approve every agent action, type each action by its declared effect, run the reversible ones freely, queue the deferrable ones, and show one prompt that lists the irreversible set the protocol enumerates, bound to a hash so that what was approved is what fires.

## Abstract
Agent frameworks guard tool use with per-action approval or with apply-then-undo, and neither tells the user what can no longer be taken back. We describe the session commit protocol of the revl language. Every boundary crossing is classified by a declared extern effect: witnessed (revertible with a checked inverse), deferred (an irreversible tail postponed to the session commit point), or immediate (fires at the call, may carry a best-effort compensation). The class is derived from the checked effect type; the design gives neither the runtime nor the harness a path to move a call between classes (a design statement, checked only against the session-commit design document and the gate guide). Deferred calls are lowered to exactly one form, an enqueue of a WAL-logged named-call descriptor, so the queue is the set of irreversible crossings the commit will cause. Commit is a two-step verb: enumerate a manifest, then confirm with its hash; a stale hash is refused. Abort drops the queue at zero cost and replays witnessed inverses. The crash windows covered by the tests (approval to flush, the approved-but-unflushed window, abort) have specified recovery verdicts. Tiers without a session owner refuse deferred calls at emit time rather than degrade silently. In a harness-boundary experiment reported in the project roadmap archive, 75.0 percent of 24 boundary calls (one harness's tool set) were auto-approved with proof and prompts per session fell from 4.7 to 1.9 over six scripted sessions plus one live session. We state what is not yet shown: the experiment is small, the retention policy for witnesses is a design, and only one of six runtimes owns a session.

## Problem and claim
Per-action approval does not scale and trains users to click through. Apply-then-undo hides the fact that some effects (a sent message, an emptied directory) have no undo, and when the undo horizon ends the class of an action silently changes. The usual database answer, two-phase commit with savepoints, assumes the participants can hold a prepared state; an outbound email cannot.

The claim: if the language makes the reversibility class part of the checked effect type, then (1) most agent actions need no prompt, (2) the remaining irreversible set can, by design, be enumerated from the compiler's own audit surface, and (3) one prompt over that set, bound by hash to what will fire, replaces per-action consent. The exhaustiveness argument is a design argument, not a mechanized proof: every crossing is meant to pass through a classified extern, a deferred call has exactly one lowering, and immediate crossings are logged at fire (`docs/design/245-session-commit.md:515-545`).

## Contributions
1. A three-way action classification derived as a type judgment from the declared extern effect, with the deferred modifier as a declared property in the extern slot (`docs/design/245-session-commit.md:259-300`; `src/revl/parser.py:1647-1654`; `docs/harness-gate-guide.md:107-135`).
2. A deferral queue that is session-owned, FIFO, WAL-logged at enqueue and flushed once at commit, with write-ahead honesty (intent logged at enqueue, outcome logged after fire) so a crash between fire and outcome leaves one emission `unknown` rather than falsely done (`docs/design/245-session-commit.md:369-420`).
3. A two-step commit with a manifest hash: enumerate, then confirm; a post-enumeration enqueue or swap changes the hash and the confirm is refused (`docs/design/245-session-commit.md:515-570`; `backends/python/runtime.py:5540-5546`; `tests/test_session_commit.py:251`).
4. An abort path that is exact for classes a and b by design (nothing fired, nothing to offset) and a recovery specification for crash windows, including the approved-but-undischarged window where commit-approved dominates (`docs/design/245-session-commit.md:571-595`; `tests/test_session_commit.py:338,381`).
5. A tier gate: the five tiers without a session owner refuse any call to a deferred extern at emit time, keyed on call sites, because both degradations (fire early, enqueue to nobody) are wrong (`src/revl/session_commit.py:1-30,92-110`; `tests/test_session_commit_tier_gate.py`).
6. Prompts-per-session as a measured quantity: `{commit, perCall, residue}` counters in the manifest (`docs/design/245-session-commit.md:596-614`; `tests/test_session_commit.py:154-196`).
7. Designed, not shipped: a witness retention policy where dropping a witness is a visible class change with a WAL entry and an undo-horizon marker (`docs/design/273-witness-retention.md`). This is future work unless built.

## Related work
| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Database 2PC and savepoints (Gray; Bernstein et al.) (citation to be checked) | Participants prepare, coordinator commits or aborts | The irreversible participant (outbound send) cannot prepare, so it is not executed until commit; the queue is the prepared state |
| Git staging area and `git add -p` | User curates what the commit contains | The set is derived from the checked effect classes, and the confirm is bound to a hash of that set |
| Transactional outbox pattern (microservices) (citation to be checked) | Write the message to a table in the same transaction, relay after commit | Same shape, but typed: the language refuses to compile an unmarked call to a deferred extern, and the manifest is generated from the audit surface |
| Sagas | Run forward, compensate on failure | Deferred class avoids needing compensation at all; compensation is reserved for immediate class |
| Agent coding assistants with approve-each-action or apply-then-undo (commercial assistants; specific systems and versions to be named after checking) (citation to be checked) | Prompt per action or snapshot and revert | One prompt for the irreversible set only; revertible actions are silent, with a stated witness |
| Capability and object-capability prompts (Capsicum, Fuchsia) (citation to be checked) | Authority is explicit | Orthogonal; revl's gate composes capability with reversibility class |
| Optimistic concurrency and speculative execution in OS and database literature | Execute ahead, validate, roll back | The unit that cannot roll back is withheld, not speculated |

## Evidence on main
The tree is revl main at commit 45bec431f. The session-commit design document's header still says "design proposed" (`docs/design/245-session-commit.md:3`), while code and tests show the slices landed; this draft follows the code and the roadmap archive's COMPLETE entry (`docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:251`).

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Three classes as a type judgment | `docs/design/245-session-commit.md:259-300`; `docs/harness-gate-guide.md:107-135` | shipped | Gate guide: class is "the worst class over every crossing its checked reach includes" |
| `deferred` modifier parses on externs | `src/revl/parser.py:1647-1654` | shipped | |
| Session owner holds queue, escrow, live-frame registry; verdict is session-scoped | `backends/python/runtime.py:5157-5175` | shipped (py only) | Docstring: "the gate target ... never the runtime's per-call current frame" |
| Enqueue lowering with WAL entry | `backends/python/runtime.py:4224` (`enqueue_deferred`); `docs/design/245-session-commit.md:369-420` | shipped (py) | Every marked position enqueues, issue #1457 (`docs/design/245-session-commit.md:395-420`); `tests/test_deferred_every_position_1457.py` exists |
| Commit flushes FIFO, witnessed persists, immediates already out | `tests/test_session_commit.py:154` | shipped | Needs the pinned cordis fork; skipped otherwise |
| Abort reverts witnessed and drops deferred | `tests/test_session_commit.py:197` | shipped | same caveat |
| Hash-bound confirm refuses a stale manifest | `tests/test_session_commit.py:251`; `backends/python/runtime.py:5540-5546` | shipped | |
| WAL entry order and crash windows | `tests/test_session_commit.py:283,338,381` | shipped | |
| `revl_commit`, `revl_commit_confirm`, `revl_abort` on MCP | `docs/guide-ai-agents.md:330-350` (tool table row) | shipped | Gated verb `commit` per `docs/design/245-session-commit.md:79-110` |
| Tier gate on five ownerless tiers | `src/revl/session_commit.py:92-110`; `tests/test_session_commit_tier_gate.py:1-30`; `backends/java/emit.py:9831` | shipped | Declared-but-uncalled still emits |
| Prompts-per-session counters | `tests/test_session_commit.py:154-196` (`prompts == {"commit": 1, "perCall": 0, "residue": 0}`) | shipped | |
| Measurement of classes and prompts on a real harness | `docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:274` | partial | Quoted summary of an experiment on a downstream engine; the raw data is not in this tree |
| Witness retention and undo-horizon marker | `docs/design/273-witness-retention.md:1-12`; `docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:498` ("Spec only, implementation follows") | design-only | No `witness-budget`, `droppable` or `witness-dropped` in src or backends |
| Recover re-fires owed deferred emissions through the runtime flush | `tests/test_recover_real_world_1477.py:616` | shipped, policy-gated | A re-fire happens only when the policy file says "recovery may re-issue owed emissions", after a reissue-fence entry; the default stays owed. This contradicts the design document's open question 2 ("never auto-fires", `docs/design/245-session-commit.md:691`) as written, which needs rewording |
| E-Stop interaction: halt strands rather than unwinds | `docs/design/teardown-contract.md:113-150` | shipped | A third verdict, relevant to the commit story |

## Numbers that exist
- 20 of 20 live tests for the commit, abort and crash-in-window cases, reported by the roadmap archive entry for this feature (`docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:251`). This is a test count in prose, not a re-run.
- Harness-boundary experiment (`docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:274`): six scripted corpus sessions plus one live session with a local open-weights model (gpt-oss-20b via LM Studio). Of 24 boundary calls, 75.0 percent auto-approve with proof (class a: 15, b: 3, c: 6). Prompts per session 4.7 before, 1.9 after; filesystem-heavy sessions hit exactly 1. The live session was 100 percent auto-approved (commit 1, perCall 0). n is 24 calls over 7 sessions, which is small, and the sessions were scripted except one.
- No latency, queue-size or flush-failure numbers.

## Paper outline
1. Introduction: approval fatigue and the undo horizon; the one-prompt claim.
2. Effects and classes: the extern effect declarations, class as a type judgment, the worst-over-reach rule.
3. The protocol: session, queue, escrow, two-step commit, manifest hash, abort.
4. Durability: WAL entries, write-ahead honesty, crash windows and verdicts.
5. Exhaustiveness argument and the tier gate.
6. Implementation: the py session owner, MCP verbs, operator gating.
7. Evaluation: prompts per session, class distribution, adversarial exhaustiveness, user study.
8. Related work: 2PC, outbox, sagas, agent assistants, capability prompts.
9. Limits and future work: retention and undo horizon, multi-tier owners.

## Threats to validity and limits
- The only session owner is the py driver; no cross-tier fan-out is owed by the design (`docs/design/245-session-commit.md:672-680`). Five tiers refuse deferred calls.
- A session ends in commit or abort within one driver lifetime; sessions that survive restart are out of scope (`docs/design/245-session-commit.md:681-715`, open question 3). Owed-but-approved emissions are reported by default and not auto-completed; a recovery policy can re-issue them (`tests/test_recover_real_world_1477.py:616`).
- Flush ordering is FIFO only; cross-receiver ordering is not expressible (open question 4).
- Reversal of a witnessed effect does not undo observation, concurrent readers may have seen intermediate state, races are TOCTOU-bounded, and physical confinement belongs to a stronger tier. These caveats are written into the roadmap archive entry for the filesystem module (`docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:246`).
- Class c is unavoidably per-call: mutate-and-answer calls fire immediately; the roadmap archive says the remainder is "the subprocess surface" (`docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:274`). The headline 75.0 percent depends on the tool mix of one harness.
- The measurement was run by the project on its own harness with scripted sessions; an external replication is absent. Tests that exercise the runtime need the pinned cordis fork and skip without it.
- Soundness of the exhaustiveness argument rests on the checker refusing unclassified host calls; it is a compiler-correctness claim and has had bugs. The docs cite fixed escapes #1457 (`docs/design/245-session-commit.md`) and #1707 (`docs/harness-gate-guide.md:123`); an adversarial test set is not yet written.
- No user study of the single prompt exists, and the abort-is-exact property and the crash-window verdict table are not mechanized.
- Statuses here come from reading files; the test suites were not re-run for this draft.

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 30 checked, 6 corrected.
