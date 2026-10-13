---
id: P68
title: "The Gate Is the Oracle: Scoring LLM Component Generation by Admission, First-Pass Rate and Tokens-to-Green, with a Refusal Column that Leads"
theme: empirical
kind: benchmark
maturity: partial
status: Protocol, report checker, committed corpora and model-free rescoring are on main; the three-host comparison covers 3 of 30 briefs and the pinned-model run is incomplete.
fused_with: P69
---

## Pitch

A code-generation benchmark whose oracle is a deterministic admission gate, scored model-free from committed bytes, with the guarantee's cost (what the gate refuses) as the leading column because a compile-rate leaderboard is maximised by loosening the gate.

## Abstract

Code-generation benchmarks mostly rank models by pass@k against unit tests. We describe a benchmark for a different question: given a runtime whose compiler admits or refuses a component against nine named guarantee gates (G1-G9), does a mediocre model still fail to ship residue, widened capability or unmarked emissions? The oracle is the gate. The headline metric is first-pass admission (K = 1, the file written before the model saw a compiler message), with iterations-to-green and output tokens-to-green as secondary metrics. Scoring is model-free: every number is a re-score of committed generation files with a named compiler commit, under a frozen protocol (EVAL-1) whose `noSelfScore` rule is enforced by a guard, and reports are checked by a program (EVAL-REPORT-1) against a four-rung evidence ladder so a claim cannot stand higher than its evidence. Because a compile-rate leaderboard can be won by loosening the gate, the design puts a recomputed refusal column first and treats a table in which revl wins every column as a finding about the table. On 30 component briefs and one model, typed-checker first-pass was 27/30, 20/30 and 18/30 on three prompt variants against 28/30, 17/30 and 13/30 for the pre-typing control; the project reads tokens-to-green as within run-to-run noise at n=30, and no significance test is committed. The three-host comparison currently has n=3 briefs per host and no independent reproduction.

## Problem and claim

Pass@k against tests ranks models. A runtime that claims the gate still refuses residue, capability widening and unmarked emissions whatever the model's quality (`docs/design/562-framework-benchmark.md` section 1: "the model can be mediocre and the gate still refuses...") is not checked by such a ranking, and a high compile-rate can be bought by removing the gate (same section). Two further problems follow. Benchmark numbers get stated as durable capabilities after one run, and a model grading its own output inflates results.

The claim: (a) using the admission gate as the sole oracle, and scoring only committed bytes with a deterministic grader, removes the grader-equals-generator failure and makes every number replayable at a compiler sha; (b) pairing first-pass rate with a leading refusal column, recomputed from gated ledgers, keeps the metric from being optimised by loosening the gate; (c) a machine-checkable ladder (claimed, measured, demonstrated, supported) refuses over-claims.

The paper does not claim revl wins on compile rate. The project's own docs say revl "may lose this column and that is a valid result" (`bench/hosts.json`, column `admits`).

## Contributions

1. A frozen model-free scoring protocol, EVAL-1: passAtK = 1 headline, grader is the compiler, deterministic, committed input, enforced by `assert_model_free` (`docs/eval-protocol.md:1-60`, `:61-89`; `bench/rescore.py:110`; `tests/test_rescore_no_self_score.py`). Per task, EVAL-1 scores three named hard gates (`compiles`, `pinnedInterfaces`, `noResidueForRawBaseline`, `docs/eval-protocol.md:97-115`); the nine G1-G9 gates are the compiler's guarantees, cited in `docs/design/562-framework-benchmark.md` section 1.
2. A machine-checked report schema and four-rung evidence ladder (EVAL-REPORT-1) with a checker that refuses over-claims and never promotes (`docs/design/478-eval-honesty-protocol.md:127-172`; `tools/check_eval_report.py`; `tests/test_check_eval_report.py`, 15 test functions by count).
3. A tokens-to-green metric: output tokens across all attempts up to and including the admitted one, with retries counted, plus as-run dollars (`bench/tokens.py`; `bench/results/tokens-to-green.md`).
4. A runtime-axis benchmark design, FRAMEWORK-BENCH-1: one pinned local model, one 30-brief task set, three hosts, the refusal column leading and recomputed never transcribed, asymmetries stated in the host entries (`docs/design/562-framework-benchmark.md`; `bench/hosts.json`).
5. An empirical result from the syntax-2.0 acceptance run: the project reads typed checking as costing the model no first-pass accuracy within run-to-run variance (no significance test is committed; the typed arm is higher on v2 and v2host), on 30 briefs and one model (`docs/roadmap-archive/02-done-dependency-order-as-built.md:58`; the two `summary.md` files).

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| HumanEval, MBPP (pass@k) | Samples k programs, passes if any passes hidden tests | Headline is K = 1 admission; later attempts reported separately and labelled |
| SWE-bench, LiveCodeBench, BigCodeBench | Repository or contest tasks scored by tests; rank models | Axis under test is the runtime, not the model; oracle is a static gate with named guarantees |
| MultiPL-E | Translates tests across languages | Compares hosts on leak behaviour and refusals, not on translated tests |
| Aider polyglot leaderboard | Edit success with a feedback loop | Feedback-loop results exist (iterations-to-green) but are secondary and never labelled pass@1 |
| DevBench, AgentBench (citation to be checked) | Agentic and development-lifecycle task suites | Tasks are single components with pinned interfaces; each has hard named gates |
| Evaluation reporting checklists (e.g. model cards, datasheets) (citation to be checked) | Human-read disclosure | A program decides whether a report obeys the protocol before numbers are stated |

## Evidence on main

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Headline is first-pass (K = 1), grader is the compiler, model-free | `docs/eval-protocol.md:24-60`; `bench/rescore.py:110`, `:235` | shipped | Protocol frozen 2026-09-06 |
| noSelfScore enforced mechanically | `tests/test_rescore_no_self_score.py:66`, `:75`, `:87`, `:98` | shipped | The doc says it cannot prove a review happened |
| Four-rung ladder and report checker | `docs/design/478-eval-honesty-protocol.md:127-172`; `tools/check_eval_report.py` | shipped | Refuses over-claims only |
| Tokens-to-green table | `bench/results/tokens-to-green.md` | shipped, proxy | Token counts are a BPE-shaped estimate; model counts were never kept for these corpora |
| syntax-2.0 acceptance, two 30 x 3 runs | `bench/results/typed-deepseek-v4-pro/summary.md`, `bench/results/baseline-deepseek-v4-pro/summary.md` | shipped | Single model |
| Three-host benchmark design with refusal column leading | `docs/design/562-framework-benchmark.md` sections 1-3; `bench/hosts.json` | designed, partly built | |
| Three-host pinned-model run | `bench/results/framework-bench/report.md`; `bench/results/pinned-three-host/summary.md` | partial | "run over 3 of 30 briefs ... every three-host number carries n=3"; the framework host cells read "not run". The pinned summary also probes an MCP host (4/6 clean, 0/6 leaked, 2/6 not probed), which the report does not show; the two artifacts disagree on that host |
| Unload-path survey of 6 agent frameworks | `bench/results/framework-bench/report.md`, `bench/framework_unload_survey.py` | shipped | 0 of 6 publish per-registration unload (n=6, pinned versions) |
| Paired head-to-head with clustered bootstrap CIs and McNemar tests | none | not present | No such code exists in `bench/`, `tools/`, `tests/` or `docs/` |
| Independent reproduction | `bench/results/framework-bench/report.md` | not done | "nobody outside this repository has run the suite" |

## Numbers that exist

Sample size is 30 briefs per cell, one model (DeepSeek V4 Pro), one run per cell, committed under `bench/results/`.

First-pass compile, as run (`summary.md` in each run directory):

| prompt variant | typed checker | pre-typing control |
|---|---|---|
| v1 | 27/30 | 28/30 |
| v2 | 20/30 | 17/30 |
| v2host | 18/30 | 13/30 |

Tokens-to-green, recomputed against compiler `f959e5e` (`bench/results/tokens-to-green.md`): admitted 23/30, 23/30, 24/30 for typed v1, v2, v2host and 22/30, 21/30, 23/30 for the control. Mean estimated output tokens-to-green 133 to 170 per cell (low is baseline v1 at 133; high is baseline v2host at 170); 136 admitted components overall, mean 149 (median 130); as-run cost $0.0271 to $0.0659 per cell, $0.2917 total.

The three columns are prompt variants (v1, v2, v2host; `bench/run.py:4`, `bench/README.md:73`), not three hosts, and the comparison arm is the pre-typing checker control, not a TypeScript baseline. The "typed vs untyped within noise" statement is the project's own reading ("equal-or-better within run-to-run variance", `docs/roadmap-archive/02-done-dependency-order-as-built.md:58`); no significance test is committed.

Three-host run: n=3 briefs (the report drops `01-kv-provider`, `03-user-cache` and `04-migrator` from every host because one host's answer came from the reasoning channel); the revl cell reports 22/30 first-pass on `v1` from a corpus produced by a different model, not the pinned one; median 8192 output tokens (n=6) for the pinned model, which equals the sampling cap `max_output_tokens: 8192` in `bench/hosts.json`. That is probably a ceiling effect (our inference, not stated as such in the doc); the report does say 3 of 8 injection attempts spent the whole output cap on the reasoning channel, which is consistent with it. Throughput 24.3 t/s was measured on a loaded machine against 51.4 quoted. Raw TS hand corpus: 4/10 plugins leak, which the doc says "is not a population rate" (ten plugins this repository wrote). Pinned-model small run (`bench/results/pinned-three-host/summary.md`): revl v2 first-pass 3/6. Raw-TS: 0/6 leaked, 5/6 clean, and 1/6 "carries residue" only because that cell failed to mount (a 900 s runner timeout); the summary headline counts it as residue, so it is reported here as a mount failure, not a leak. The pinned model there is `hf.co/ornith-ai/Ornith-1.5-35B-A3B-GGUF:Q4_K_M`, not DeepSeek V4 Pro.

## Paper outline

1. Introduction: why pass@k cannot check a runtime guarantee, and why compile rate is gameable.
2. Protocol: model-free re-scoring, K = 1, noSelfScore, hard named gates, the ladder.
3. The report checker and what a green check does and does not mean.
4. Metrics: first-pass admission, iterations-to-green, tokens-to-green with retries counted.
5. Benchmark design: one model, one task set, three hosts, asymmetry stated, refusal column leading and recomputed.
6. Results: syntax-2.0 acceptance (typed vs control), tokens-to-green, three-host table, unload-path survey.
7. Threats and limits, including the first survey version that was wrong and was deleted.

## Threats to validity and limits

From the docs: "Compile-rate is necessary, not sufficient" and "One model ≠ 'several models'" (`bench/README.md` caveats, around line 563). "A model's own judgement ... is never evidence" (EVAL-1 section 3) applies, so semantic correctness of admitted files is not measured; the README suggests spot-checking. Token counts are a proxy and the model's own counts were not kept. The control arm shares the 30 briefs with the typed arm and seven specs were adjusted to be satisfiable under the checker (README), so brief authorship is by the project. The task set is authored by this repository; a curriculum of 266 tasks exists but retiring n=30 is "a named remaining gate". The raw-TS asymmetry means residue and admits are different questions. The measured throughput run was taken on a contended machine and "does not reproduce the quoted one". The framework host was selected by criteria the project wrote, and a third-party-framework column is not yet run. The injection-escape column has a runner (`bench/injection_escape.py`) but only 5 revl attempts were scored (2 complied, 0 escaped; 3 of 8 excluded for hitting the output cap), so it cannot yet rate escape; admission latency is not run in the report. All claims sit at the `measured` rung, none at `demonstrated`. The central anti-loosening argument (loosen the gate on purpose and show the refusal column exposes it) is argued, not yet run. Benchmark contamination by the public repository is not addressed; the held-out draw idea in P67 applies to the gate census, not to these 30 briefs.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 14 checked, 7 corrected.
