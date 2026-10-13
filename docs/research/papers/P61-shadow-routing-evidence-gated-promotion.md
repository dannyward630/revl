---
id: P61
title: "Promotion No Measurement Can Buy: Shadow Routing, an Authority Barrier and Verified Canary for Models and Components"
theme: agents
kind: full
maturity: partial
status: Python tier and the promotion decision procedure ship on main with constructed-evidence tests and mutant runs; five tiers are unwired and no live shadow run has been done.
fused_with: P59, P60
---

## Pitch
A model or component is promoted by replaying captured worlds against the incumbent and the promotion function is built so that no latency or accuracy number can appear in the same expression as a non-empty authority diff.

## Abstract
Progressive-delivery systems promote a new version when metrics such as error rate or latency stay inside a threshold. For a model that can act, a small sample measures the paths traffic happened to take, while capability reach and taint edges are static properties of the program; the rare path that widens authority is the one the sample does not exhibit. We describe a promotion procedure for model and component replacement in which the verdict is split in two phases by a control-flow barrier. Before the barrier are properties of the declaration and of whether the evidence is evidence: the action's route names both roles, every sealed decision entry verifies, the policy and placement digests are pinned, the authority diff is present on every axis and empty on all of them, and every layer of accumulated state is either revertible or carries a tested compensation. Only after the barrier is agreement accumulated, per action class, from replay comparisons of captured worlds. The barrier is also a data barrier: the metric block is not copied across it, and a counter in the verdict reports how often a metric was read (asserted zero on the paths the tests cover). A declared fraction of crossings is served in shadow through a deterministic, order-independent draw; a live promotion reverts on the first attributed divergence, named as an exact (component, realm) and step; zero evidence refuses rather than promotes. We show the rule is shared by four promotion paths in the tree through a registry and a sweep that flags unregistered ones, show a promotion path (the existing canary) that lacked the barrier and recommended promote for a candidate with wider reach, and report non-vacuity runs against mutants. We do not report a live shadow run: every input in the tests is constructed.

## Problem and claim
Canary and shadow tooling (Argo Rollouts, Flagger, Kayenta, traffic mirroring) judges a candidate by metrics. For model-backed actions that is the wrong judge twice. The metrics are samples, and the property that matters, whether the candidate can reach more than the incumbent, is static. And a gate that weighs a latency win against an authority widening can be tuned, by accident or by an optimiser, to approve the widening.

The claim: a promotion gate can be written so that the comparison "latency versus authority" cannot be expressed in it. The design note states the target as "there is no expression in this function in which both values appear" (`src/revl/shadow_promotion.py:1487-1510`, the `decide` docstring). Agreement is accumulated over comparisons of captured worlds, not over a counter, so that a divergence is a name, not a number.

Second claim: the property is checkable and has been checked. The syntax-tree tests assert there is one call to `accumulate`, after the precondition loop; that `Pair` has no `slo` field; and that no precondition names an agreement member (`docs/design/540-shadow-promotion.md:125-200`). A separate registry and sweep keep a third promotion path from escaping the rule (`docs/design/548-authority-precondition.md:80-197`).

Third claim, the empirical hook: the pre-existing canary path recommended `promote` whenever two captured worlds matched, and a candidate with strictly wider capability reach produced an identical timeline and got `promote` (`docs/design/548-authority-precondition.md:27-79`). After the barrier, the same pair is refused and the divergence comparison is never computed (`divergenceRead: false`, `src/revl/mcp/canary.py:602-655`).

## Contributions
1. A two-phase promotion verdict with a control-flow and data barrier: preconditions (route, evidence, policy, authority, state) return before any tally exists; the metric is not carried into `Pair`; a measured `slo_reads` counter is reported in the verdict (`src/revl/shadow_promotion.py:1140-1160,1487-1588`; `docs/design/540-shadow-promotion.md:125-200`).
2. Shadow serving of a declared share, a rational such as 1/20, selected by a keyed hash of the crossing, so a replay shadows what the run shadowed; the incumbent's answer is served and both worlds are captured; the share is not a verdict input (`src/revl/shadow_routing.py:189-320`; `docs/design/558-shadow-scheduling.md:86-140`).
3. Two rules on two sides of promotion: before promotion, threshold over a ratio plus a minimum sample; after promotion, revert on the first attributed divergence regardless of ratio; zero evidence refuses (`docs/design/540-shadow-promotion.md:202-224`; `docs/design/558-shadow-scheduling.md:639-654`).
4. Restore versus compensate: revert reports restored and compensated layers as separate lists and the phrase "rolled back" is not used in the rendered output (`docs/design/540-shadow-promotion.md:225-256`).
5. A shared barrier rule (`AUTHORITY_AXES`, alias table, fail-closed `authority_moved`, `REGISTRY`, `discover`) that binds the four registered promotion paths and flags any unregistered one (none beyond the two exempt modules on d41ee937), plus its application to the canary path that lacked it (`src/revl/promotion_barrier.py:112,135-168,452,472,558`; `tests/test_promotion_barrier_543.py`).
6. Canary as a realm slice: G2 forces the candidate into a separate realm and the revert is the derived LIFO teardown with survivors pinned by a test (`docs/verified-canary.md:14-30,57-82`; `tests/test_canary.py::test_exit_one_of_n_diverges_and_reverts_clean`).

## Related work
| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Argo Rollouts, Flagger, Spinnaker/Kayenta canary analysis (citation to be checked: exact Kayenta paper or blog) | promote or abort from metric analysis against a baseline | the verdict is a replay comparison; no metric is in scope after the barrier; authority diff is a precondition |
| Istio / Envoy traffic mirroring | duplicates traffic to a shadow, compares offline | same idea, but the comparison is over captured worlds with exact attribution and a promotion register that is the thing the verdict lands in |
| GitHub Scientist | runs control and candidate, compares results, reports mismatches | no gating authority diff; no revert-on-first-divergence after cutover |
| Counterfactual / off-policy evaluation in ML ops (citation to be checked: specific references) | estimates a new policy's value from logged data | does not address static authority widening; revl's claim is about what the gate refuses to weigh |
| Canary analysis with statistical tests (e.g. sequential testing) (citation to be checked) | decides on significance | revl states a threshold over a ratio of comparisons and does not defend a value (design note 540, section 9) |
| Capability-safe upgrade (E-lang, Erlang hot upgrade, Fuchsia component updates) (citation to be checked) | controls authority at upgrade by construction | revl joins authority diff to the promotion decision and refuses on an unmeasured axis |

## Evidence on main
| claim | path:line or test | status | note |
|---|---|---|---|
| barrier is control flow: one `accumulate` call after the precondition loop | `src/revl/shadow_promotion.py:1487-1588`; `tests/test_shadow_promotion_518.py::test_the_authority_barrier_survives_a_window_that_would_have_promoted` (line 558) | shipped | AST assertions are described in `docs/design/540-shadow-promotion.md:140-165` |
| metric not carried across: `Pair` has no slo member; counter is incremented in one function | `tests/test_shadow_promotion_518.py:609,620,642` | shipped | `slo_reads` is a measurement of the module's behaviour |
| agreement compares `chosen_digest` and `outcome`, not model digest, fallback depth or sampling | `docs/design/540-shadow-promotion.md:71-124` | shipped | design rationale |
| suppressed prompt binding refuses the window | same, section 2.1 (`binding-suppressed`) | shipped | the confidentiality-fail-open argument |
| scheduler: share is a rational, draw is a keyed hash, share not a verdict input | `src/revl/shadow_routing.py:189-320`; `tests/test_shadow_routing_518.py` (43 test functions) | shipped | observed 52/1000, 250/1000, 517/1000, 1000/1000 for 1/20, 1/4, 1/2, 1/1 (`docs/design/558-shadow-scheduling.md:107-128`); "not a claim" of uniformity |
| action correlation: window for `summarize` offered as `classify` evidence refused as `action-mismatched` | `docs/design/558-shadow-scheduling.md:283-310` (non-vacuity table) | shipped, stamp trusted then derived | sections 3.1 and 12 of that note; derived from a static walk whose premise can refuse |
| register: promotion lands, induced divergence reverts that same promotion, zero evidence shows no 0% or 100% | `src/revl/shadow_register.py:252`; `tests/test_shadow_register_518.py` (23 test functions) | shipped | `docs/design/558-shadow-scheduling.md:555-684` |
| python tier changes which model answers after promotion | `tests/test_shadow_cutover_1192.py` (12 test functions); `backends/python/runtime.py:1132` (`_revl_serve_shadow`) | shipped for python only | other five tiers discard the observer's return (`docs/design/558-shadow-scheduling.md:664-675`) |
| `revl promote` decides from artifacts, exits 0/1/1 for PROMOTE/REFUSE/REVERT | `tests/test_promote_cli_1192.py:247`; `docs/design/558-shadow-scheduling.md:686-854` | shipped | it decides, it does not land |
| shared barrier rule and registry | `src/revl/promotion_barrier.py`; `tests/test_promotion_barrier_543.py` (25 test functions) | shipped | detector is syntactic and "errs wide"; limit stated |
| canary lacked barrier; wider-reach candidate promoted | `docs/design/548-authority-precondition.md:27-79`; `tests/test_promotion_barrier_543.py:500,513` | shipped fix | measured at `6c291ac3` (historical); the two tests pin the verdict on this tree |
| canary as realm slice, derived LIFO revert, survivors | `docs/verified-canary.md`; `tests/test_canary.py` (15 test functions) | shipped, stateless only | stateful canary is not landed |
| signed execution receipts | `CHANGELOG.md:216-219` lists "decided from signed execution receipts" | partial | sealed decision entries are verified by `_verified` (`src/revl/shadow_promotion.py:718`); the receipts path was not traced beyond this and the changelog sentence |

## Numbers that exist
- Non-vacuity table (the first three rows share the same twenty pairs): PROMOTE (agreement 1.00, 20 pairs, 20 slo blocks supplied, 0 read), REVERT with one relocated step (0.95), the same window with worlds stripped PROMOTE, no evidence REFUSE, and the action-mismatch trio. Source `docs/design/558-shadow-scheduling.md:283-310`, n = 20 constructed pairs.
- Share selection over 1000 crossings: 52, 250, 517, 1000 for 1/20, 1/4, 1/2, 1/1 (`docs/design/558-shadow-scheduling.md:107-128`). A later run selected 7 of 20 at 1/4 (`:534-553`).
- Mutation check for the barrier: without the canary change, 4 failed / 22 passed / 1 skipped; with two mutants (`check_path` returning None, `authority_moved` reading absent as empty), 10 failed / 16 passed / 1 skipped (`docs/design/548-authority-precondition.md:208-226`).
- Registry sweep (historical: origin/main at d41ee937, not re-run on 45bec431f) selects six modules: four registered, two exempt (`docs/design/548-authority-precondition.md:112-118`).
- Test counts: the docs quote 83 for `test_shadow_promotion_518` and 48 for `test_shadow_routing_518`; on this tree there are 63 and 43 `def test_` lines, presumably parametrisation and later edits differ. Counts should be quoted from a pytest run, not from either.
- No live shadow: "Nothing here has been run against a real shadow" (`docs/design/540-shadow-promotion.md`, section 9). The python cutover test uses constructed answers.

## Paper outline
1. Introduction: why metrics cannot gate an agent; the canary that promoted a wider candidate.
2. Model: roles, route table, sealed decision entries, captured worlds.
3. The two-phase verdict and the barrier; the shapes of fail-closed refusals (table of 14 links).
4. Shadow serving and action correlation: share, stamp, derivation.
5. Authority diff on five canonical axes; the registry and sweep; canary retrofit.
6. Restore versus compensate and the promotion register; zero-evidence rule.
7. Evaluation: non-vacuity, mutation, injected-divergence study, metric-gate baseline.
8. Related work. 9. Limits and future work (stateful canary, five tiers, activation identity).

## Threats to validity and limits
Quoted from the docs:
- Every input in the test file is constructed, and "Nothing here has been run against a real shadow" (`docs/design/540-shadow-promotion.md`, section 9; `docs/design/558-shadow-scheduling.md:311-340`).
- Five tiers are unwired and for them "a promotion does not change which model answers a call" (`docs/design/558-shadow-scheduling.md:664-675`).
- The captured worlds are the declared worlds of a static walk, not a live activation's trace (`:826-842`).
- "A sealed window is evidence of a schedule and of answers, not of an activation"; "a REFUSE means a statement about the evidence, not about the models"; `slo_reads` being 0 "proves the metric was not consulted, not that it could not be" (`:826-842`).
- The `agreement-ledger` and `placement-history` compensation classes are "this note's judgement, not a measurement" (`docs/design/540-shadow-promotion.md`, section 9).
- The sweep "is a ratchet against the ordinary case of a path being added, not a proof that none can escape" (`docs/design/548-authority-precondition.md`).
- Authority diff is supplied, not computed, in the gate itself; the canary computes it from `audit_diff` over the G8 boundary surface, so its completeness is that surface's.
- The selection draw is a scheduling draw and not a security boundary; no uniformity claim.
- One activation per window; accumulating across activations is not designed (`docs/design/558-shadow-scheduling.md:534-553`).
- Stateless canary only.
- Much of the evidence is the author's own tests on the author's own gate; an external baseline is needed.

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 34 checked, 6 corrected.
