---
id: P45
title: Quorum Approval With a Durable Decision Graph and an Override That Is Not a Vote
theme: security
kind: short
maturity: partial
status: Protocol, verbs, receipt, signed casts and HTTP transport are on main with tests; the count is of credentials, never of people, and there is no attack evaluation, overhead measurement or related-work survey yet.
fused_with: P55, P26
---

## Pitch
A group approval for an irreversible agent action is only as good as the claim "these were N distinct principals, bound to this exact question", so revl logs every counted vote and every vote-protocol refusal in a durable graph, makes the emergency override a separate authority that is never counted as a quorum, and states precisely that the count is of credentials and not of people.

## Abstract
Agents that call tools with irreversible effects are usually gated by a single yes/no approval. Multi-party schemes exist in banking and wallets, but an agent runtime adds a particular weakness: the approver channel is a session that may bind only one operator, so "N approvals" can degrade into one caller asserting N names. We describe the quorum approval mechanism of revl, a language and runtime for agent compositions. A policy clause `require N of {a, b, c}` is parsed fail-closed. Votes are bound to a hash of the exact candidate composition, to a round and to the ticket's own expiry, and a proposer cannot satisfy its own question. Every counted vote and every refusal the vote protocol makes is an append-only row in a write-ahead log, so a refused probe leaves a trace. Escalation, revocation and an emergency override are operator verbs; the override has its own authority, is logged as `satisfiedBy: "override"` with the count it really had, and requires a reason. An admission receipt is derived at the moment the authority is spent, as a join over the log rather than a second copy, and a verifier re-derives it. Casts are bound first to a credential digest and then to an ECDSA P-256 signature over the question, with expiry and revocation. We pin the residual honestly: a caller holding two private keys still satisfies a two-of-M rule from one session, as a named expected-admission test. We report the test suites and no field data.

## Problem and claim
Single-party approval tickets show that one operator's session said yes, not that one human did. Moving to N-of-M raises three questions that a vote counter alone does not answer. Are the votes distinct principals or one operator's assertions? Are they about the same question the authority is spent on? And what happens on the emergency path that skips the count? A path that admits a crossing without quorum and does not say so, in the design note's words, "is worse than no path at all" (`docs/design/471-quorum-approval.md:73-95`).

The claim: a quorum for agent actions is a decision graph, not a counter. Distinctness, binding to one candidate hash, proposer exclusion and the override are each enforced as logged refusals or as a distinct authority, and no admission path (standing grant, auto-approve rule, lease gate) may widen a quorum-gated crossing. The strength of the identity binding is graded and stated: name, credential digest, signature, authenticated HTTP request.

The claim is not that the count is a count of people. Once casts are signed, the design note says the rule is "advisory against an operator who has collected the key material itself" (`docs/design/471-quorum-approval.md:646-648`). The sentence is about a deployment that reads the rule with `sign` on, not about the count alone.

## Contributions
1. A fail-closed policy clause `require N of {a, b, c}` where duplicate approvers, `*`, a zero count, an empty set, a count above the set size and unknown trailers are parse errors (`docs/design/471-quorum-approval.md:125-150`).
2. A vote protocol with a fixed refusal order (malformed vote, expired, closed, the question's own outcome, stale candidate, unknown approver, proposer, duplicate voter), each logged before it is raised, and a closed set of nine WAL entry kinds that the log refuses to extend (`docs/design/471-quorum-approval.md:213-272`).
3. One predicate, `_multi_party_rules`, that every consent path consults, so a standing grant, a distilled auto-approve rule or a lease cannot admit a quorum-gated crossing with zero votes; a lease-specific bridge re-derives its proof from the ledger (`docs/design/471-quorum-approval.md:150-212`; `src/revl/mcp/session.py:6600`).
4. An override that is a different authority (its own operator verb, `override`), requires a reason, refuses decided questions, and closes as `satisfiedBy: "override"` with the real count (`docs/design/471-quorum-approval.md:274-320`, `docs/design/471-quorum-approval.md:357-397`).
5. A receipt derived at admission time as a join over the log, with a verifier that re-derives it and separates a digest forgery from a binding forgery (`src/revl/mcp/quorum.py:620-700`).
6. A graded identity binding for casts: credential digest, ECDSA P-256 signature over a canonical message covering request, round, action and vote, expiry and revocation checked before verification, and one pinned expected admission for the residual (`docs/design/471-quorum-approval.md:449-648`).

## Related work
| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Multi-signature wallets (e.g. Bitcoin P2SH multisig, Gnosis Safe) (citation to be checked) | M-of-N signatures over a transaction | Votes are kept as a graph including refusals; override is a separate authority; the unit is an agent crossing bound to a composition hash, not a transaction |
| Four-eyes principle, separation of duties (Clark and Wilson 1987) (citation to be checked) | A second person must approve | Proposer exclusion is applied to the policy: a rule the proposer leaves unsatisfiable is refused at the crossing |
| Threshold cryptography (Shamir secret sharing, threshold signatures) | Cryptographic quorum, no single holder | No threshold crypto; the quorum is a protocol-level count of distinct principals, with the limits stated |
| Paxos / Raft quorums | Replicas agree on a value | Not replica agreement; humans authorizing one effect. Same word, different problem |
| PagerDuty / chat-ops approvals, GitHub required reviewers (citation to be checked) | N reviewers click approve | Binding to a candidate hash, expiry latch, durable refusals, receipt that a verifier can re-derive |
| Kubernetes admission webhooks | Policy decision at an admission point | Webhooks decide per request; here the decision is multi-party, stateful and receipted |
| Break-glass access (e.g. clinical, cloud IAM) (citation to be checked) | Emergency bypass with audit | The bypass is its own verb, cannot be folded into approve, and the log entry cannot be mistaken for a quorum |

No survey of agent-framework approval features has been done. The novelty claim needs one. The external rows above are not checked against sources.

## Evidence on main
| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Quorum clause parses and refuses meaningless forms | `tests/test_471_quorum_approval.py:200-264` (`test_dsl_refuses_a_quorum_that_cannot_mean_what_it_says`) | shipped | DSL and JSON forms |
| Two distinct votes admit, one does not | `tests/test_471_quorum_approval.py:277` | shipped | Exit test of the quorum feature |
| Proposer cannot satisfy alone | `tests/test_471_quorum_approval.py:340` | shipped | |
| No grant or auto rule widens a quorum | `tests/test_471_quorum_approval.py:423-511`; `src/revl/mcp/session.py:6600` | shipped | `_multi_party_rules` |
| Lease gate takes the vote path and re-derives proof | `tests/test_471_quorum_approval.py:624-819` | shipped | |
| Decision graph kinds closed; WAL refuses unknown kind | `tests/test_471_quorum_approval.py:1253` | shipped | nine kinds |
| Quorum log entries consume no WAL sequence | `tests/test_471_quorum_approval.py:1227` | shipped | |
| Denial, unreachable count, timeout, escalate, revoke | `tests/test_471_quorum_approval.py:951-1100`; `tests/test_471_quorum_slice2.py:521-583` | shipped | |
| Override: reason required, own verb, refuses decided question | `tests/test_471_quorum_approval.py:1003-1053`; `tests/test_471_quorum_slice2.py:303-380`, `tests/test_471_quorum_slice2.py:453` | shipped | |
| Receipt minted at admission, verified by re-derivation, forgeries refused | `tests/test_471_quorum_slice2.py:620-820`; `src/revl/mcp/quorum.py:620-700` | shipped | |
| Credential-digest binding: asserting two names is not two votes | `tests/test_979_quorum_identity_binding.py:144-250` | shipped | |
| Signed cast not replayable across question, action, vote, name | `tests/test_979_signed_cast_binding.py:222-336` | shipped | |
| Expiry and revocation before verification | `tests/test_979_signed_cast_binding.py:457-534` | shipped | |
| Residual pinned as expected admission | `tests/test_979_signed_cast_binding.py:607` | shipped | Reds when the transport closes it |
| HTTP transport binds each cast to one authenticated request | `docs/mcp-http-transport.md:140-156`; `tests/test_mcp_http_transport.py:455` (`test_a_quorum_is_gathered_from_distinct_authenticated_callers`) | shipped (test skips without the cordis-py runtime) | Doc and test body read; test not run |
| Shipped as a feature | `CHANGELOG.md:231` | shipped | issues #865, #974, #994, #1019, #1035 |

## Numbers that exist
- Test functions by `def test` count: 56 in `tests/test_471_quorum_approval.py`, 12 in `tests/test_979_quorum_identity_binding.py`. Counts of definitions, not of parametrized cases or of a green run.
- `tests/test_471_quorum_slice2.py` holds 46 `def test` definitions and `tests/test_979_signed_cast_binding.py` holds 20 (66 together; counted by grep, not run).
- Nine WAL entry kinds (`docs/design/471-quorum-approval.md:246-272`).
- No latency, overhead, usability or attack-success numbers. None yet.

## Paper outline
1. Introduction: why single-party tickets are not enough, and what a naive quorum gets wrong.
2. Threat model: proposer, voters, a caller who holds some credentials, a replay observer.
3. The clause and the protocol: refusal order, distinctness, binding to a candidate hash.
4. The decision graph: closed entry kinds, refusals as rows, seq-free consent facts.
5. No widening: one predicate over all consent paths; the lease bridge.
6. The override as a different authority.
7. Receipt as a join and its verifier.
8. Identity binding ladder: name, digest, signature, authenticated request; the pinned residual.
9. Evaluation: attack-to-test table, mutation results, overhead.
10. Related work and limits.

## Threats to validity and limits
- Design note, Decision 5/8: the count is of credentials. Holding two named approvers' private keys satisfies a two-of-M rule from one session; this is pinned as an expected admission (`tests/test_979_signed_cast_binding.py:607`). Over HTTP it is "a count of distinct authenticated credentials, one per request. It is not a count of people" (`docs/mcp-http-transport.md:154-156`).
- Over stdio a session binds one operator (`docs/design/471-quorum-approval.md:321-333`), so stdio quorums are driven by `as_token` in tests.
- Evidence is test suites written by the implementers; no independent red team.
- Only vote-protocol refusals are log rows; DSL parse errors are not.
- The override trusts whoever holds the `override` verb; the design makes it visible, not impossible.
- Quorum is inert against an operator who controls the policy file; policy provenance is out of scope here (see P55).
- Test counts are definitions, not a green run. The HTTP quorum test skips without the cordis-py runtime and has not been run for this draft. A user study is out of scope.

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: about 45 checked, 7 corrected.
