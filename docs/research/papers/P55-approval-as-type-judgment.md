---
id: P55
title: Approval as a Type Judgment: Auto-Approve-Unless-Irreversible for Agent Tool Use
theme: agents
kind: empirical
maturity: partial
status: Mechanism, tests and a formal model row are on main; there is no measurement of prompt burden or of false auto-approvals yet.
fused_with: P45, P26
---

## Pitch
An agent harness can decide "ask the human or not" from the checked effect class of each call at one chokepoint, bind every yes to a hash of exactly what it approves, and so prompt only for actions the checker cannot show are revertible or deferrable.

## Abstract
Agent harnesses decide which tool calls need a human with allowlists of tool names or with self-declared hints such as "read-only". Both fail the same question: which actions escaped? We present a permission policy in which the decision is a type judgment. A call's class is the worst class over every boundary crossing its checked reach contains: (a) revertible, because the checker found a registered inverse; (b) deferrable, because its typing forbids it from firing before a commit prompt; (c) immediate, an emission with neither. Policy rules name boundary capabilities and component globs, not tool names, and a new tool is classified by the checker rather than by a list entry. Class (a) proceeds silently, (b) is enumerated at commit, and (c) returns a ticket whose hash covers the call, its arguments and the reach closure of the code it runs; a yes is single-use, expires, dies when any provider in the closure changes, and is spent durably before the action fires. The decision sits in one function, so replay and activation bodies cannot route around it. Approval is also a typed effect in the language (`await approval`), and repeated approvals in the ledger can be offered back as a typed, budgeted, revocable policy rule with a dry-run blast radius. We describe the mechanism and the tests that pin it, and we state plainly that this paper has no prompt-count measurement and no safety-side measurement yet.

## Problem and claim
Current permission systems for tool-using agents are lists. A list of safe tool names cannot enumerate the side effects of a permitted tool, and a hint such as read-only is a claim by the tool author. The user then sees either a prompt for every call, which trains approval by reflex, or a broad standing grant, which removes the check. A prompt whose answer is a boolean held in harness memory can also be replayed for a different call, outlive the code it approved, or be spent twice.

The claim is narrow. If the effect class of a call is derived by the checker, and the policy can read only that class, then (1) the calls that proceed without a per-call prompt are those the checker proves revertible (class a) or deferrable (class b, which waits for the commit prompt; class a also depends on its inverse succeeding, `docs/design/246-auto-approve.md:137-142`), and (2) an action missing from the enumeration is a compiler bug, not a policy gap (`docs/design/246-auto-approve.md:577`). The yes is as checked as the no: it is bound to a hash, so what the human approved is exactly what fires.

We do not claim fewer prompts than every alternative on every workload; no such measurement exists here. The design doc names its own caveats: reversal does not undo observation, concurrent-writer races are time-of-check bounded, a compensated crossing still left the system (`docs/design/246-auto-approve.md:599-606`).

## Contributions
1. A decision table over three derived action classes, evaluated at a single chokepoint inside `Session.call` (not keyed on tool names), with the class map computed per generation over every provide-method and every activation body, so load and swap are gated as boundary calls too (`docs/design/246-auto-approve.md:108-250`; `src/revl/mcp/approval.py:214`).
2. A ticket and ledger discipline: exact-hash tickets over a reach closure, outstanding-ticket table that refuses hashes the server never issued, consume-before-fire durable spend in the WAL, cross-session and cross-component replay refused, a join of spend to emission so an owed action is visible (`docs/design/246-auto-approve.md:251-300,476-542`; `src/revl/wal.py:244`).
3. Approval as a typed effect: `capability C requires approval` owned by the operator's policy file, `await approval[C]` yielding an unforgeable `Approval[C]`, and a checker obligation that a crossing carries a covering `with` edge; the formal model states the same floor (`docs/design/246-auto-approve.md:359-475`; `formal/RevL/Theorems/G4_ApprovalFloor.lean`; `tests/test_approval_typed.py`).
4. Approval distillation: repeated approval shapes in the ledger are offered back as a typed `AutoApproveRule` that an operator could have written by hand, with a never-standing clause, a budget, attribution, revocation and a blast radius computed by a pure fold over past decisions; prompts per session is the intended evaluation metric (`docs/design/251-approval-distillation.md:99-450`; `src/revl/distill.py:370`).

## Related work
| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Claude Code permission modes and per-tool allow/deny rules (citation to be checked, exact current docs) | User or settings list tool names and path patterns; modes broaden what runs without asking | Policy rules name boundary capabilities and component globs (`capability C requires approval`; `AutoApproveRule`, `src/revl/policy.py:332`), not tools. The class is derived from the checked reach. A new tool is classified by the checker, not by whoever edits the list |
| macOS TCC, Android runtime permissions, UAC | Prompt per capability class at first use, remembered as a boolean | Per-call, hash-bound, single-use ticket over the code's reach closure; invalidated by a change to any provider it reaches |
| OAuth consent screens | Scope list shown once, token bearer | The yes is bound to a hash of the call and consumed durably before the effect |
| Allowlist approval in agent frameworks (LangChain, OpenAI Agents SDK human-in-the-loop hooks) (citation to be checked) | Callback per tool call, decision is the developer's code | Decision is the language's; no callback decides, and a dropped callback fails closed |
| MCP tool annotations (`readOnlyHint`, `destructiveHint`) | Server-declared hints, advisory | Class is derived by the checker; no hint is read |
| Rust `unsafe` as a boundary marker | Marks where the programmer takes responsibility | Same idea of a marked boundary, but the marked set is enumerated on the audit surface and gates a runtime decision |
| Capability systems and object-capability prompts (Capsicum, Joe-E style powerboxes) (citation to be checked) | Authority by designation; a powerbox mediates grants | Grant is typed and tied to effect class; distillation turns repeated grants into a reviewable rule |
| Transactional / checkpoint rollback for agents (VM snapshot, filesystem revert) | Revert the disk | Cannot say which network packets left. Class (b) has exactly one lowering, the enqueue, so the queue is the set the commit will cause |

## Evidence on main
| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Decision table, three classes, worst class over reach | `docs/design/246-auto-approve.md:108-143`; `src/revl/mcp/approval.py:214` (`ClassMap`) | shipped | Design doc header says "design proposed, revised after review"; code and tests exist |
| Class map classifies each op and activation reach from checked facts | `tests/test_approval_policy.py:134,143` | shipped | |
| Witnessed effect auto-approves silently; all-(a)/(b) session fully auto | `tests/test_approval_policy.py:169,184` | shipped | |
| Class (c) prompts once, fires once, second identical call re-prompts | `tests/test_approval_policy.py:205` | shipped | |
| Compensated emission still class (c) | `tests/test_approval_policy.py:386` | shipped | |
| Activation body cannot dodge the prompt | `tests/test_approval_policy.py:429,493,525` | shipped | Closes the "move the emission into activation" bypass |
| Replay path goes through the same chokepoint | `tests/test_approval_policy.py:602`; `src/revl/mcp/session.py:5159` | shipped | |
| Unknown ticket hash refused; enabled policy requires journaling | `tests/test_approval_policy.py:635,648` | shipped | Design: "Refuse, don't degrade" |
| No policy configured is byte-identical | `tests/test_approval_policy.py:660` | shipped | |
| Double approve never over-mints | `tests/test_approval_policy.py:243,354` | shipped | Found by the 2026-09 MCP audit, advisory text in `docs/v2.0-roadmap.md:1639` |
| Typed approval surface (`requires approval`, `await approval`, `with`) | `tests/test_approval_typed.py` (15 tests); `docs/design/246-auto-approve.md:359-475` | shipped (name-is-the-capability spelling; the dotted `emission[production.payment]` form is not) | Design doc itself flags this at line 376 ("Shipped reality") |
| Formal floor for approval-required crossings | `tests/test_formal_approval_row.py:1`; `formal/RevL/Theorems/G4_ApprovalFloor.lean` | shipped | Not re-run; the module docstring was read |
| Gate default-on in `revl mcp serve`, three policies (auto, advisory, off) | `docs/harness-gate-guide.md:21-23`; `tests/test_approval_gate_default_1706.py` (13 tests) | shipped | |
| Spend/emission join in the WAL | `src/revl/wal.py:244`; `tests/test_approval_emission_session_path_1781.py` (6 tests) | shipped | |
| Standing grants bounded by uses and TTL, never-standing clause | `CHANGELOG.md:176-180,231-238`; `tests/test_standing_approval.py` (17), `tests/test_distill_enforcement.py` (31) | shipped | |
| Distiller: shape key, typed rule, cannot-distill verdicts, blast fold | `src/revl/distill.py:370,467`; `tests/test_distill.py` (18), `tests/test_distill_metrics.py` | shipped | Design 251 header still says "No implementation"; the code and CHANGELOG disagree with it, the code wins |
| MCP verb for distillation offers | `src/revl/mcp/server.py:2618,5119` (`revl_distillation_offers`) | shipped | Only the offers verb was opened; the verbs for approve, revoke, escalate and quorum were not independently opened |

## Numbers that exist
- Test counts on main: `tests/test_approval_policy.py` 21, `tests/test_approval_typed.py` 15, `tests/test_approval_gate_default_1706.py` 13, `tests/test_standing_approval.py` 17, `tests/test_distill.py` 18, `tests/test_distill_enforcement.py` 31, `tests/test_470_approval_gate.py` 22, `tests/test_502_approval_replay.py` 5, `tests/test_427_approval_fold_bypasses.py` 11 (counted on `def test_`).
- No prompt-count measurement, no false-auto-approve count and no effect of distillation on prompts is published in the tree.

## Paper outline
1. Introduction: prompt fatigue and the allowlist's blind spot; the claim.
2. Background: action classes (witnessed, deferred, immediate), the audit surface, the commit protocol.
3. The decision table and its single chokepoint; activation and replay as bypass routes.
4. Tickets: hash over reach closure, single-use, consume-before-fire, crash cuts.
5. Approval as a typed effect and the operator-owned requirement; the formal floor.
6. Approval distillation: shape key, typed rule, blast radius, soundness.
7. Evaluation (to be done): prompt counts against independent baselines, a safety-side suite.
8. Limits and related work.

## Threats to validity and limits
- There is no measurement in this paper. Any prompt-count claim needs an independent baseline and a corpus not written by the authors; a safety-side measurement (false auto-approvals per class) is also needed, since prompt reduction only matters if no irreversible action auto-approved.
- The (c) class is dominated by the subprocess surface; the design says shell remains "an all-emission surface" until a separate item lands (`docs/design/246-auto-approve.md:603-605`).
- Auto-approval of class (a) rests on a registered inverse. A failed restore surfaces a prompt (`docs/design/246-auto-approve.md:137-142`), which is honest but means "auto-approved" is conditional.
- Self-approval (`docs/design/246-auto-approve.md:562`): with no operator profile bound, the agent that receives a ticket can answer it. The gate guide states that with no operator profile nobody can answer under `auto`, and `advisory` lets any identity answer with a warning (`docs/harness-gate-guide.md:21-22`).
- Reversal does not undo observation; concurrent-writer races are time-of-check bounded (`docs/design/246-auto-approve.md:599-601`).
- Single-use is stated as consume-before-fire in the WAL; which layers are atomic on main still has to be stated precisely, and the lock was not opened for this draft.
- Distillation widens consent by design; its safety argument is the design doc's, plus tests. No external review of the soundness section.
- Class derivation is only as strong as the extern classification, which for host code is the author's declaration. An untrusted-author admission profile narrows this.
- The unforgeability of `Approval[C]` rests on a source comment (`src/revl/lower.py:15250`), not on a test.

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 29 checked, 5 corrected.
