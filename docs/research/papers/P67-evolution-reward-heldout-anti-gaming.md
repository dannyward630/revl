---
id: P67
title: "Reward Is a Repository Fact: Conjunctive Retention and a Sealed Held-Out Draw Against Self-Improvement Gaming"
theme: agents
kind: methods
maturity: partial
status: Scorer, sealed draw and mutation evidence are on main with tests; no model-produced trajectory has ever been scored.
fused_with:
---

## Pitch

A self-improvement loop has no scalar to push: the reward is a conjunction of ten facts read from repository artifacts, never the candidate's prose, and it is also scored on a draw whose seed is checked absent from the tracked tree at score time.

## Abstract

Self-improving coding agents are trained or filtered against a reward, and a scalar reward invites the usual failures: weights that trade a false admission against passing tests, a score that is maximised by the empty diff, a held-out set that sits in the repository the candidate can read. We describe the reward and retention rule used by the revl evolution loop. Reward is a conjunction of ten components, each `verified` or `failed`, each read off an artifact the repository owns (the gate crate and its unit tests, the affected suite, the false-admission census, the guarantee-tier matrix, regenerated goldens, the formal ledger, the declared change scope, the documentation gates, a held-out draw, and a monotone progress counter). A trajectory is retained only if all ten verify. There is no weight, no threshold, no third "skipped" value and no exported number. Every key in the candidate submission except the tree, base and scope is dropped by name and reported as `prose_ignored`. The held-out component scores the candidate on a 200-program draw generated at score time from a seed that is refused if it appears anywhere in the tracked tree, behind a six-path fence (five scorer sources and the census baseline file). Mutation evidence: a certifier mutated to admit everything is caught on 35 of 200 draw programs; a surface-keyed shortcut passes a first-version draw clean and is caught 50 times in 200 on the shipped draw. We also report what is not built: eight of nine planned anti-gaming mechanisms, seed custody, and any run against a model-produced trajectory.

## Problem and claim

Reward gaming in self-improvement has three cheap routes that a repository-resident loop makes concrete. First, a scalar or weighted reward is satisfiable in ways the underlying gate refuses: a candidate can commit a false admission and still clear a threshold, because the components are not commensurable and any weight vector is invented (`docs/design/534-evolution-reward.md` section 3). Second, a reward made only of preservation checks is maximised by the empty diff. Third, a scoring set that lives in the repository is readable by the process being scored.

The claim is narrow and mechanical. (a) Reward and retention are one object, a conjunction over a closed component list, with fail-closed handling of every missing tool, timeout, crash and unimplemented probe. (b) No component reads candidate-authored text. (c) "Held out" cannot mean a hidden file in a public repository, so what is withheld is the draw: a function of a seed checked absent from the tree, generated in memory, behind a fence that makes a diff touching the scorer a refusal rather than a score. (d) The residuals are stated: recognition of the draw as generated is 1.00, seed custody is open, and the remaining anti-gaming mechanisms are named demands with no owner.

We do not claim the loop resists a capable adversary. The design doc states that nothing has been run against a trajectory produced by a model.

## Contributions

1. A conjunctive reward and retention rule with ten verified/failed components and a closed failure direction (seven named failure causes each have a test); the rule iterates the component list so an omitted verdict cannot retain (`tools/evolution_reward.py:1346-1362`, `tests/test_evolution_reward.py:167`).
2. A no-scalar export and a prose firewall: the candidate whitelist is three keys, everything else is reported under `prose_ignored` (`tools/evolution_reward.py:248`, `:278`; `tests/test_evolution_reward.py:178`).
3. A re-baseline-proof ratchet for the false-admission allowance: the candidate baseline's bucket ids must be a subset of the base's, closing the path where re-baselining and then checking against the new baseline passes.
4. A sealed held-out draw: seed absent from the tracked tree by `git grep`, in-memory generation, a six-path scorer fence, REFUSED (exit 2) distinct from DIVERGENT (exit 1) (`tools/heldout_scoring.py:125`, `:224`, `:286-290`, `:518`, `:920-935`).
5. An explicit separation versus recognition analysis of surface tells, with a measured fix (separation 0.56 and 0.76 to 0.00) and a measured non-fix (recognition 1.00), plus a mutation experiment showing an attack that succeeds on one draw shape and fails on the next (`docs/design/535-held-out-scoring.md` sections 3.7 and 4.1).
6. A `progress` conjunct so the empty diff is not retained (`docs/design/546-evolution-progress-term.md`; `tools/evolution_reward.py:1310`).

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Goodhart's law; specification gaming catalogues (citation to be checked) | Document proxies that are optimised past their purpose | Gives a concrete anti-proxy construction: no scalar exists to optimise, and the one non-baselinable bucket is a hard conjunct |
| SWE-bench Verified, LiveCodeBench | Hold out or date-split a fixed test set; contamination is managed by recency | The set is generated per run from a seed checked absent from the tracked tree; it is not a file in the repo, though its generator is readable, so secrecy rests on the seed |
| AlphaCode-style filtering by tests | Retains samples that pass generated or given tests | Retention needs ten independent artifact verdicts including conformance, formal ledger and scope, not tests alone |
| RLHF reward-hacking work (reward-model overoptimisation) (citation to be checked) | Learned reward is exploited | No learned component; each verdict is a deterministic tool exit plus a count |
| Contamination studies for code benchmarks (citation to be checked) | Detect train-test overlap after the fact | The draw is never written to the tree, and the seed is checked against the tree before generation; the generator is in the tree, so the draw is not hidden from a reader of the code |
| Mutation testing of test suites | Measures whether tests catch injected faults | Used on the scorer itself: gate mutated to admit all is caught; mutated to admit nothing is refused as vacuous |

## Evidence on main

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Ten-component list, retention is `all()` over it | `tools/evolution_reward.py:175-188`, `:1346-1362` | shipped | `tests/test_evolution_reward.py:167` |
| No scalar exported | `tests/test_evolution_reward.py:178` | shipped | `docs/design/534-evolution-reward.md` section 3 |
| Candidate whitelist and `prose_ignored` | `tools/evolution_reward.py:137`, `:248`, `:278`, `:1401` | shipped | Seed is an env var, not a key in the submission (`:200`) |
| `false-admission` is never baselinable | `tools/evolution_reward.py:210`; `tools/gate_reference_census.py:1071` | shipped | |
| Conformance component built on existing registers, not a new tool | `docs/design/534-evolution-reward.md` section 5 | shipped | The roadmap's cited tool `tools/gate_verdict_parity.py` never existed; the design documents and tests its absence |
| Sealed draw: seed refusal, fence, in-memory | `tools/heldout_scoring.py:125`, `:286-290`, `:518`; `tests/test_heldout_scoring.py:216`, `:228` (seed-in-tree test) | shipped | 39 test functions in the file by count |
| Mutation evidence | `docs/design/535-held-out-scoring.md` sections 4 and 4.1 | doc-reported, not rerun | Numbers are quoted from the doc |
| Separation enforced, recognition not | `tools/heldout_scoring.py:666`, `:694`, `:935`; `docs/design/535-held-out-scoring.md` section 3.7 | shipped, residual | |
| `progress` conjunct | `tools/evolution_reward.py:1310`; `tests/test_evolution_progress.py` | shipped | |
| CI job `held-out` | `docs/design/535-held-out-scoring.md` section 5, slice 4 | partial | Doc states its first GitHub run was the PR that added it; advisory only |
| Seed custody | `docs/design/535-held-out-scoring.md` section 5 (slice 5) | not built | Rotation is only a stated per-run parameter (section 2.1) |
| Other eight anti-gaming mechanisms | `docs/design/535-held-out-scoring.md` slice 6 and section 6 | not built | Listed as eight "named, unowned demands" |
| Score of a model-produced trajectory | none | not done | `docs/design/534-evolution-reward.md` section 9: "Nothing here has been run against a trajectory produced by a model." |

The abstract's "ten components" and "eight of nine mechanisms not built" both hold: `held-out` and `progress` were added to the original eight.

## Numbers that exist

- Census at the design baseline: 846 programs, 9 baselined divergences (`false-admit/T1` 6, `false-admit/TYPE` 3), no false-admission; 14 s (`docs/design/534-evolution-reward.md` section 1). Later 848 programs, same buckets (`docs/design/535-held-out-scoring.md` section 4.1).
- Held-out real gate, 200 programs: clean, 102 issued admissions, 35 near misses refused by the reference (slice 1); 102 and 50 after the generator change. Certifier mutated to admit everything: divergent, 35 of 200 caught. Admit nothing: refused, exit 2 (doc 535 section 4).
- Surface-keyed shortcut: 0 findings on a slice-1-shaped draw (regenerated after the generator change, so not slice 1's own draw), 50 of 200 on the shipped draw (doc 535 section 4.1). Single seed (the fixture seed), single run per cell.
- Tell separation 0.56 and 0.76 to 0.00; recognition of `closed-vocabulary` 1.00 (doc 535 section 3.7).
- A full scoring run takes about 4 s at 200 programs; the test file runs 26 cases in about 16 s at slice 1 (doc 535 section 4).
- No numbers on any model-generated candidate. None yet.

## Paper outline

1. Introduction: three cheap routes to gaming a repository-resident reward.
2. Design: the conjunction, the ten components, the failure direction, the prose firewall.
3. Ratchets, not freezes: the re-baseline path, the base-side matrix read, the deleted-row case.
4. Held out when the set is public: why "hidden file" fails, the chosen mechanism, the fence, REFUSED versus FAILED.
5. Surface tells: separation (closed) versus recognition (open), the mutation experiment on two draw shapes.
6. Evaluation (still to be run on real candidates) and what is currently only mutation evidence.
7. Residuals: seed custody, the eight unbuilt mechanisms, the conformance tool that never existed as a lesson in citation hygiene.

## Threats to validity and limits

From the docs: "Nothing here has been run against a trajectory produced by a model" (534 section 9). The reward "is only as strong as the gates it reads". The draw "is not" indistinguishable from real programs and recognition is 1.00 (535 section 7). The seed check only shows the seed is not in the repository, not that an operator kept it secret. On a 200-program draw, 0 of the 42 near misses the reference refuses are in-slice, so the `false-admit` predicate cannot fire on that draw (535 section 3.4). The CI job's seed is drawn inside the job, which gives up reproducibility. `progress` rejects real improvements no counter measures (refactors, features). All evidence is on a single codebase and a single gate; generality to other repositories is untested. The sealed-draw claim does not defend against a candidate that controls the machine the gate runs on, nor against training-data exposure.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 20 checked, 9 corrected.
