---
id: P38
title: "Right-to-Erasure as a Checkable Program Property: Typed Retention and Signed Erasure Receipts"
theme: security
kind: full
maturity: partial
status: The compile-time refusal and both signed receipts are shipped with tests; the deadline is per policy and not per value, derivatives are declared and not inferred, and no evaluation exists.
fused_with:
---

## Pitch
Erasure evidence becomes two things a reviewer can run: a compile-time refusal when expired data would reach a store, and a signed receipt that lists exactly the copies the compiler knows about and says in its own body what it cannot know.

## Abstract
A right-to-erasure request asks an operator to show that a tenant's data is gone. In practice the evidence is a runbook and an assertion. We describe two artifacts in revl, a typed language for capability-scoped agent programs, that move parts of this obligation into the toolchain. First, `Retained[T, P]` is a qualifier in the same family as `Untrusted[T]` and `Secret[T]`: a named policy declares a deadline, a residence, a legal hold, a set of authorised deleters and the derivative classes it covers, and a value under an expired policy is refused at every crossing the compiler sees as an extern declared with a durable-store capability (db, fs, store, kv, blob, archive, index, cache, queue, wal), including across a service seam and through helper functions; a store reached only from inside a host body is not seen. The comparison instant is one per compile, not a per-value age, and we say so. Second, `revl erase-report --realm` composes realm isolation, the exact withdrawal query, the runtime no-residue proof and the enumeration of boundary crossings into one report, and an optional HMAC-signed receipt over it whose rows can only be crossings the report enumerated. A sibling receipt, `revl retention-receipt`, signs a policy together with the replicas and derivatives an operator names. Both receipts state, inside the signed body, that they prove the measurement is unaltered and not that anything was erased. We report the design corrections that review forced, and list the evaluation we have not run.

## Problem and claim
Erasure tooling usually works on stores: delete by key, tombstone, excise. It cannot say whether the program that wrote the data had any path to a store the tooling does not know about, and the confirmation is a ticket. Language-level privacy work (Jeeves, Hails) restricts who may read a value, not how long it may be kept.

The claim has two parts and both are limited by the repository's own notes. (1) Within the declared boundary, a program that would write a value past its policy's deadline to a store the compiler can see does not compile, unless a legal hold is declared. (2) Within the same boundary, the report names every crossing the realm's components make, with the disposition the report assigned each, and a signature lets a third party check that the list was not altered. Neither claim covers copies made outside revl's boundary or what a remote host did after a crossing. The design note says this in the same words (`docs/design/472-retention-erasure-receipts.md`, "What a receipt proves and what it does not").

The paper's second theme is design history. The retention half of the original request rested on four nouns (sink, time fact, residence and hold vocabulary, derivative relation), and the design note observes that each of them "names something the tree does not have". It measured the premise, found that none of the four existed, then landed a narrower form of three of them and left the fourth declared rather than inferred. That sequence, and the correction after review that the refusal was argument-blind across a service seam, are results worth reporting.

## Contributions
1. A retention policy declaration and a `Retained[T, P]` qualifier, checked at admission, with the refusal derived from the capability a crossing declares and not from an author annotation (`src/revl/retention.py:129`, `src/revl/taint.py:91, 612, 1975`).
2. An interprocedural persistence-reach: a provider's body walk notes which parameter reaches a store, so the caller's refusal follows the value across a service seam with a named path (`src/revl/taint.py:1347-1409, 1647`; `docs/design/472-retention-erasure-receipts.md`, "Corrections after the third review").
3. A legal hold as a declaration that overrides the deadline and turns every replica row of the policy receipt (`revl retention-receipt`) into `withheld:legal-hold`; the realm erase report has no hold concept (`src/revl/retention.py:441-453, 536`).
4. A compliance report that composes realm isolation (G2), the exact withdrawal survivors set, the runtime no-residue proof and the G8 crossing list, scoped to one realm (`docs/erase-report.md:8-77`, `src/revl/erase_report.py:606-685`).
5. Two signed receipts with domain-separated HMAC, a body that carries its own scope of what it does not prove, and a verifier that refuses rows contradicting the word they carry even under a valid MAC (`src/revl/erasure_receipt.py:77-153, 484-655`; `src/revl/retention.py:424-860`).
6. Retention is listed as an admission-kernel path, so a loop that edits a retention policy is a kernel-boundary change, not ordinary tuning (`src/revl/kernel_boundary.py:58-72, 160`). The module does not itself stop such an edit.

## Related work
| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| GDPR Art. 17 tooling, DSAR platforms (citation to be checked) | Discover and delete data across stores, produce a ticket | The artifact is derived from the program's declared boundary, so a store the program cannot reach is not in scope and one it can reach is a row |
| Datomic excision, tombstoning, crypto-shredding (citation to be checked) | Remove or make unreadable data in one store | Not a store feature; revl refuses the write and enumerates crossings |
| Verified deletion research (Vale; Bohen) (citation to be checked) | Prove a storage layer deletes | Orthogonal. revl states it does not prove destruction on the other side of a crossing |
| Data lineage (Apache Atlas) | Observed lineage of data flows | Declared and checked at compile time, but with a closed derivative vocabulary instead of inferred lineage |
| Jeeves, Hails (citation to be checked) | Policy-agnostic privacy on reads | Policy here is a time and residence dimension at write sinks, orthogonal to confidentiality and trust |
| Differential-privacy accountants | Budgeted disclosure | Different problem; listed only to mark the boundary |
| Signed attestations such as in-toto (citation to be checked) | Sign build and supply-chain facts | Same construction family; the novelty is the content: a measurement whose body disclaims erasure |

Honest framing: individual ingredients are old. What is new is the composition into one reviewable toolchain output, and the discipline that the signed body refuses to claim more than it measured.

## Evidence on main
| Claim | path:line or test | status | note |
|---|---|---|---|
| Design note with the measured premise, the landed slice, three review rounds of corrections | `docs/design/472-retention-erasure-receipts.md` | shipped (doc) | The note's early sections say the retention half is design-only and later sections say it landed, so quote the landed section |
| `retention <name> { until, residence, hold, deleters, derivatives }` and `Retained[T, P]` | `src/revl/retention.py:1-80, 210-400`; `src/revl/taint.py:91` | shipped | stripped to base type, IR byte-identical for programs without it (`tests/test_retention_472.py:306`) |
| Persistence sink set derived from capability scope | `src/revl/retention.py:129-143` | shipped | `fs` is both a source and a sink class |
| Single evaluation instant per compile, `REVL_RETENTION_AS_OF` override | `src/revl/retention.py:407-419`; `tests/test_retention_472.py:444, 451` | shipped | weaker than a per-value age; module docstring says so |
| Refusal on declaration and on flow, `G-RETAIN` | `src/revl/taint.py:612, 1975`; `docs/guarantees.md:97`; `examples/rejections/gretain_expired_at_persistence_sink.rvl` | shipped | fixture deadline is 2020 so it refuses under any clock |
| Refusal across a service seam, through a helper, at a non-first argument | `tests/test_retention_472.py:212-270` | shipped | four tests were red before the seam fix, per the note |
| Legal hold overrides | `tests/test_retention_472.py:264, 278, 285, 546` | shipped | |
| `G-RETAIN` not part of G9 | `tests/test_retention_472.py:329, 351` | shipped | |
| Erase report: runtime no-residue proof, crossings, survivors | `docs/erase-report.md:21-77`; `src/revl/erase_report.py:606-799`; `tests/test_erase_report.py` (22), `_network_254` (8), `_relay_1707` (6) | shipped | exit 1 on unknown realm, residue, or breached realm |
| Signed realm receipt, opt-in via `--receipt-key` | `src/revl/erasure_receipt.py:77-153, 359-470`; `docs/erase-report.md:134-189` | shipped | `tests/test_erasure_receipt.py` (45) |
| Row dispositions: `revertible`, `compensated`, `unresolved`, `bare`; in-process `reclaimed`, `residue`, `unproven` | `src/revl/erasure_receipt.py:97-112, 303-342` | shipped | tri-state fixed after second review |
| Verifier refuses contradictory bodies even with valid MAC | `src/revl/erasure_receipt.py:484-606` | shipped | |
| Scope is a member of the signed body | `src/revl/erasure_receipt.py:118-153`; `tests/test_retention_472.py:683` | shipped | |
| Policy receipt and CLI verb `revl retention-receipt` | `src/revl/retention.py:424-1032`; `src/revl/cli/retention.py:159-253`; `src/revl/__main__.py:1481-1489`; `tests/test_retention_receipt_cli_472.py` (21) | shipped | The design note's "No CLI verb yet" line is stale on main; the verb exists |
| Residence checked against supplied rows only | `src/revl/retention.py:1-80`; `tests/test_retention_472.py:524` | shipped, narrow | no placement fact derived |
| Derivatives declared from a closed vocabulary (summary, index, embedding, backup, export, cache), reported `covered` / `not-covered` | `src/revl/retention.py:351-385`; `tests/test_retention_472.py:409-425, 498, 515, 594` | shipped, declared not inferred | |
| Requester must be a member of the policy's `deleters` | `tests/test_retention_472.py:533, 621` | shipped | |
| Retention in the admission kernel | `src/revl/kernel_boundary.py:58-72, 160` | shipped | |
| Domain separation from the erasure receipt (test 638); canonical bytes and key rule taken from attest (test 648) | `tests/test_retention_472.py:638, 648`; `docs/design/472-retention-erasure-receipts.md` ("The signature is domain separated") | shipped against the erasure receipt and attest | the design note says `deploy._receipt_mac` still differs and is reported, not fixed (design note `:225`; the function is at `src/revl/deploy.py:508` on main, not the note's `:473-489`) |

The test-function count for `tests/test_retention_472.py` is 57 by a grep of `def test_`. Some are parametrized, so the executed count differs. The tests were counted for this draft, not run.

## Numbers that exist
- Static counts of test functions: retention 57, erasure receipt 45, erase report 22 plus 8 plus 6, retention CLI 21. These are counts, not pass results.
- Source sizes for scale: `src/revl/retention.py` 1032 lines, `erasure_receipt.py` 717, `erase_report.py` 1066, design note 568.
- No measurements of compile-time cost, refusal precision or recall, receipt size, or operator effort exist.

## Paper outline
1. Introduction: erasure as a runbook; two artifacts; scope.
2. Background: revl's realms, boundary surface (G8), qualifier family.
3. Retention policy and the refusal: sinks from capability scope, evaluation instant, hold, seam reach.
4. The erase report and receipts: rows, dispositions, verifier checks, domain separation.
5. What a receipt proves: the signed scope text and the limits on external copies and derivatives.
6. Design history: why the original request's retention half was not taken as written, what was supplied, what three reviews corrected.
7. Evaluation: seeded violations, case study, verifier interoperability.
8. Discussion: what the compiler can and cannot know; relation to lineage and deletion proofs.
9. Related work and conclusion.

## Threats to validity and limits
- The retention deadline is per declared policy at one compile instant, not per value. The `src/revl/retention.py` module docstring says it is not a runtime age fact about an individual value.
- Derivatives are declared against a closed list; "nothing proves that a particular boundary crossing wrote a summary of a particular `Retained` value" (same docstring).
- Residence is checked against rows the caller supplies; "nothing here can refuse a host from storing bytes in a region it did not declare".
- A receipt does not prove anything was erased. `docs/erase-report.md:183-189` and the signed scope in `src/revl/erasure_receipt.py:118-153` say so. A reader will take the title "Right-to-Erasure ... Property" as a larger claim, so the abstract leads with the limits.
- Compensation is not inversion (`docs/erase-report.md:83-90`): a compensated crossing still left the system.
- The refusal only sees writes through externs with a declared durable-storage capability; a store reached by an extern declared under another capability is invisible to it. This is a host-body-opacity limit.
- A clock-dependent refusal means the same source compiles one day and not the next; reproducibility depends on `REVL_RETENTION_AS_OF`.
- Evidence is self-authored. The review rounds noted in the design note were internal.
- The two receipt kinds are siblings, not versions; readers may confuse them. A comparison table is needed.
- Still to evaluate: seeded violations across store shapes, a hand-checked crossing enumeration on a real composition, coverage of indirect callables, and an independent verifier written from `docs/revl-attest.md`.

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 50 checked, 9 corrected.
