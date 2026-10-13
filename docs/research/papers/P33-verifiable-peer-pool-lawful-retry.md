---
id: P33
title: "Verifiable Private Peer Pools: Receipt-Recounted Tiers and Lawful Retry Derived From Effect Class"
theme: distribution
kind: full
maturity: partial
status: Admission, signed receipts, evidence recount, loopback dispatch with a one-result ledger and the tier ladder are shipped with tests; lawful retry is a kernel not wired into dispatch, and nothing runs over a real network.
fused_with:
---

## Pitch
A pool of mutually distrusting operators can promote a peer only on evidence the pool recounts from signed bytes, never on a number the peer reports, and the tier a peer reaches bounds, by the existing effect classification, what work it may ever be sent.

## Abstract
Volunteer and multi-operator execution systems usually admit a worker on identity and then trust either redundant computation or the worker's own reported history to decide how much to rely on it. We describe a private peer pool built into the revl language toolchain in which the promotion step that raises a peer's tier is a checked precondition that fails toward less authority. Peers join on a signed offer pinned to the digest of the pool charter and enter a bottom tier. Promotion is computed: a membership carries no evidence integer, only the digests of execution receipts the pool has verified, where each receipt is signed by the peer and separately attested, over the receipt digest, by an authority named in the charter. Evidence is counted per task, so re-signing the same work buys nothing, and duplicates are kept in the log rather than dropped. A tier is a bound expressed in the effect classification the toolchain already owns, so no second policy engine exists. A separate kernel, the lawful-retry dispatcher, decides per effect class whether a lost attempt is replayed, compensated, handed off or refused, and constructs each replay as a hop that is checked to narrow, not widen, the delegated grant. In the current tree a thirteen-forgery corpus is counted as evidence 0 times out of 13 where the previous gate accepted all of them, and an honest control is counted. The channel is unencrypted and tested only between processes on one machine; only boundary-free compositions are dispatchable today.

## Problem and claim
Pool membership evidence in this class of system is an assertion. In revl's own first version of the pool, `Membership.evidence` was an integer a caller incremented, and the promotion gate compared it to a threshold. A peer that can state its own evidence can state any evidence, and promotion is the gate that raises a member's tier (`docs/design/566-pool-execution-receipts.md`, "The fail-open this closes").

The claim has two halves. First, evidence for promotion can be a pure function of signed bytes the pool verifies itself, with two distinct signers (peer and attesting authority), a verdict that keeps "the arithmetic was true" apart from "the key still confers authority", and deduplication on task identity. Second, the decision of what to do when a peer is lost can be derived from an effect classification the language already computes, with the replay path bracketed by a monotone-authority check, so a retry cannot be used to launder a wider grant.

The paper does not claim a deployed distributed system. The claim is about the decision procedures and their refusal behaviour, demonstrated on single-machine multi-process runs.

## Contributions
1. A recount discipline: in `peer_pool`, the only path to an evidence count is `_evidence_precondition` (called from `promote`), which wraps `pool_receipt.count_evidence` and returns a count or a refusal; `Membership.evidence` is derived and no constructor parameter takes a number (`docs/design/566-pool-execution-receipts.md`, "The count is a precondition, not a stage"; `src/revl/peer_pool.py:1419`).
2. A two-signature receipt (peer signs the work, an attestor named in the charter signs the receipt digest), with a verdict that always carries both attributions and never reduces to a boolean; revocation yields "verified, confers nothing" rather than "forged" (`src/revl/pool_receipt.py`, `tests/test_pool_receipts_524.py::test_a_receipt_under_a_revoked_key_verified_and_confers_nothing`).
3. A non-vacuity corpus: thirteen receipt forgeries (ten distinct links asserted) each refused on a named link, an honest control counted by the same code path, and a test that the corpus passes the pre-change check (`tests/test_pool_receipts_524.py::test_the_corpus_all_clears_the_check_that_existed_before`).
4. Tiers as bounds on an existing taxonomy: `TIER_EFFECT_CEILING` maps tiers to `EffectClass`, and deferred-irreversible and secret-bearing work are reachable from no tier (`src/revl/peer_pool.py:333-352`).
5. A lawful-retry decision table over five effect classes whose replay hop is checked for authority monotonicity and peer eligibility, with an exhausted budget falling to compensate or refuse (`src/revl/lawful_retry.py:226`; 16 unit tests). This is a kernel, not yet wired into dispatch.
6. A one-result delivery ledger whose state machine has no edge back to `dispatched`, with a second delivery refused and logged (`docs/design/567-pool-dispatch.md`, "One result, impossible and visible").

## Related work
| prior system or line of work | what it does | what revl does differently |
|---|---|---|
| BOINC / volunteer computing result validation (redundant execution, quorum) (citation to be checked for the exact mechanism) | trusts agreement among replicas to validate results | evidence is a signed receipt attested by a charter-named authority; no redundancy needed to count it, but also no claim the result is correct, only admissible |
| Ray, Dask, Golem schedulers (citation to be checked) | place work on workers, retry on failure by policy | retry is decided by effect class and refused when it would widen authority or exceed a budget; a worker's tier bounds the class it may be sent |
| Byzantine fault tolerance (PBFT and descendants) | tolerates f faulty replicas by voting | no consensus; one operator holds the charter and the admit, revoke and attest key sets are separate |
| Temporal retry policies | per-activity retry settings chosen by the author | disposition derived from the effect classification; replays are monotone-narrowing hops |
| Sigstore / transparency logs | signed, publicly auditable statements about artifacts | receipts are cited in the promotion entry so a third party can recheck the count; no public log |
| Gossip membership (SWIM and similar) | decentralised liveness | explicitly out of scope; membership is a charter plus roster (`docs/design/480`, "Scope: three primitives, not a P2P monolith") |

## Evidence on main
| claim | path:line or test | status | note |
|---|---|---|---|
| Evidence is the number of verified receipt digests, no assertable count | `src/revl/peer_pool.py:904-916`, `src/revl/peer_pool.py:1419`; `tests/test_peer_pool_admission.py:349` (`test_an_evidence_count_cannot_be_stated_at_all`) | shipped | |
| Two signatures: peer over work, attestor over receipt digest | `docs/design/566-pool-execution-receipts.md` "A receipt is two signatures"; `src/revl/pool_receipt.py:242`, `src/revl/pool_receipt.py:284`, `src/revl/pool_receipt.py:387` | shipped | |
| Self-attestation refused before charter keys consulted | `docs/design/566-pool-execution-receipts.md` | shipped (doc); not individually checked in a named test | corpus includes "a peer attesting its own work" |
| Thirteen forgeries, 0 of 13 counted, ten distinct links asserted; honest control counted | `tests/test_pool_receipts_524.py:379`, `tests/test_pool_receipts_524.py:412`, `tests/test_pool_receipts_524.py:422` (the corpus tuple is at about lines 353-375); `docs/design/566-pool-execution-receipts.md` "Non-vacuity" | shipped | the design note says twelve and lists twelve categories; the corpus has thirteen entries and omits "a receipt whose body names another peer" from its list |
| Dedup on task, order-independent, duplicates kept in the log | `tests/test_pool_receipts_524.py:443`, `tests/test_pool_receipts_524.py:459`, `tests/test_pool_receipts_524.py:479` | shipped | |
| Revoked key: verified but confers nothing | `tests/test_pool_receipts_524.py:557`, `tests/test_pool_receipts_524.py:586` | shipped | |
| Shared-key member can accumulate no evidence | `tests/test_pool_receipts_524.py:608` | shipped | |
| Join gate: admit authority checked before the join is parsed, charter pinned by digest, nonce unspent | `docs/design/550` trust-progression table; `tests/test_peer_pool_admission.py` (45 tests) | shipped | |
| Tier ladder keyed on `EffectClass` | `src/revl/peer_pool.py:333-360`, `src/revl/peer_pool.py:1695` | shipped | |
| Promotion CLI | `tests/test_pool_promotion_cli_1198.py` (25 tests) | shipped | |
| Signed task envelope, bundle digest, one-result ledger, state machine | `docs/design/567-pool-dispatch.md`; `src/revl/pool_dispatch.py` (1717 lines); `tests/test_pool_dispatch_524.py` (38), `tests/test_pool_bundle_1198.py` (10) | shipped | loopback, two processes, one machine |
| Concurrency of pool state (withdrawal during flight) | `tests/test_pool_state_concurrency_1198.py` (8) | shipped | two real processes force the interleaving |
| Liveness probe | `src/revl/pool_health.py`; `tests/test_pool_health_1198.py` (17) | shipped | |
| Lawful-retry decision table | `src/revl/lawful_retry.py:226-307`; `tests/test_lawful_retry.py` (16) | kernel only | not called from any pool module: the pool modules reference `dispatch_on_loss` only in comments and docstrings (`src/revl/pool_dispatch.py:320`, `src/revl/pool_dispatch.py:744`; `src/revl/peer_pool.py:120`, `src/revl/peer_pool.py:941`, `src/revl/peer_pool.py:1650`), and the only caller outside `lawful_retry` is a test in `tests/test_tee_attestation.py:714` |
| Monotone authority along delegation and retry chains | `src/revl/peer_authority.py`; `tests/test_peer_authority_monotonicity.py` (21) | shipped kernel | defined in the capability-ceilings work; here it is a dependency |
| Signed peer offer and eligibility match | `src/revl/peer_offer.py`; `tests/test_peer_offer.py` (24) | shipped kernel | |
| Dispatch classifies the effect class from the audited boundary, never from a flag | `docs/design/567-pool-dispatch.md` "The effect class is derived, never declared" | shipped | only boundary-free compositions are dispatchable |

Status wording: an earlier description of this work said "kernels proven in isolation; transport remains". That is stale. The status block of `docs/design/480` says the kernels landed and that live dispatch remains; `docs/design/567-pool-dispatch.md` (lines 4, 26, 84) says a TCP channel, dispatcher, ledger and `revl run --pool private` have landed. "Proven" overstates the tests, which are unit and process-level, not proofs. The accurate remainder is: no network beyond loopback, no confidentiality, and lawful retry not wired in.

## Numbers that exist
- Forgery corpus: 13 forged receipts (the tuple in `tests/test_pool_receipts_524.py`), 0 counted, 10 distinct refusal links asserted by `test_every_forged_receipt_is_refused_on_its_named_link`, honest control 1 of 1 counted, two honest plus one forgery does not reach three (`test_two_honest_receipts_and_one_forgery_do_not_reach_three`). The "Non-vacuity" block of `docs/design/566-pool-execution-receipts.md` says 12 and ">= 8"; that block is stale. These are corpus counts, not a measured rate.
- Test counts by file (counted with `grep -c "def test_"`, so parametrised cases are undercounted): admission 45, identity 43, receipts 17, dispatch 38, bundle 10, promotion CLI 25, health 17, concurrency 8, lawful retry 16, authority monotonicity 21, offer 24.
- Sizes: `src/revl/peer_pool.py` 2238 lines, `src/revl/pool_dispatch.py` 1717, `src/revl/pool_receipt.py` 612, `src/revl/lawful_retry.py` 307.
- No latency, throughput, overhead or scale numbers exist.

## Paper outline
1. Introduction: promotion on asserted evidence is a fail-open; the pool and its three key sets.
2. Background: the effect classification and the monotone-authority invariant. The spawn-side theorems live in the capability-ceilings work; the replay hop is tested, not proved.
3. Join and tier ladder: trust progression table and failure direction of every arrow.
4. Receipts and the recount: two signatures, attribution verdicts, per-task dedup, order independence.
5. Dispatch and the one-result ledger: task envelope, bundle digest, write-ahead dispatch, derived effect class.
6. Lawful retry: decision table, monotone replay hop, peer selection, budget exhaustion.
7. Evaluation: forgery corpus, non-vacuity, a two-machine run (not yet done).
8. Limits and related work.

## Threats to validity and limits
- The docs state the channel carries no transport security: "nothing on it is secret, and the artifact source crosses in the clear" and that "Nothing here proves anything about a hostile network" (`docs/design/567-pool-dispatch.md`, "The channel, and what it is not").
- Authority monotonicity "bounds RECEIPT of authority, not USE" and budgets are opaque scalars, not a rate limiter (`docs/design/480`, "Honest limits").
- An attestation says a result is admissible, not that it is correct. A malicious peer with a valid attestor can still return wrong but admissible output if the attestor is careless.
- All promotion evidence is only as good as the charter-named attestor; the pool has one operator, so this is not open federation.
- Only boundary-free (pure) compositions are dispatchable, which is the weakest class. The strongest claims (idempotent and witnessed tiers) have no end-to-end demonstration.
- Lawful retry is not wired into the dispatcher: the ledger marks a lost task `orphaned` and defers (`src/revl/pool_dispatch.py:320`).
- The `identity_mode` default is `mixed`, and a mixed pool still admits a shared-key join, which leaves a fail-open on the admission path (`docs/design/566-pool-execution-receipts.md`, "What is left").
- "Never widen" for the replay hop is a tested property, not a proved one. The named Lean theorems (`attenuation_monotone` at `formal/RevL/Theorems/CapCeilings.lean:105`, `lineage_ceiling_le` at line 121) are about spawn lineage, not peer replay; the replay hop is checked only by Python code and tests (`src/revl/lawful_retry.py:200-220`, `tests/test_peer_authority_monotonicity.py`).
- The pool design explicitly rejects marketplace, gossip, reputation and settlement; readers from peer-to-peer venues may read that as a narrow system.

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 17 checked, 9 corrected.
