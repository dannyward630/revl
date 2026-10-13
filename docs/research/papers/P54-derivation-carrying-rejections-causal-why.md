---
id: P54
title: Rejections and Lifecycles That Explain Themselves: Derivation-Carrying Diagnostics, Runtime Why and Navigable Refusals
theme: compiler
kind: full
maturity: shipped-evidence
status: Derivation traces, runtime causes with a withdrawal oracle, and navigable refusals are on main with named tests and CLI/MCP surfaces; no agent-side or human-side measurement yet.
fused_with:
---

## Pitch
When a compiler's global guarantees give every fact a unique supplier and force every cascade to terminate, "why did this happen?" can be derived instead of guessed, at compile time (rejections), at run time (lifecycle transitions) and at the policy layer (refusals), and the one place where explaining would leak is handled by making all refusals look the same.

## Abstract
Diagnostics and traces usually report what happened, and leave the cause to the reader or to a monitoring tool that infers it from timing. We describe three explanation mechanisms in revl, a language whose checker enforces unique provision per key and realm (G2) and an acyclic provider graph (G3). First, rejections that come from a whole-program search (an emission fixed point, a dependency cycle, a provider conflict) carry the derivation of the verdict as structured data, and `revl explain` maps any diagnostic code to its guarantee and fix. Second, a run logs every lifecycle transition with its cause; because a lost provision has exactly one supplier and a cascade terminates, the cause is read from the checked graph rather than inferred. The static prediction of a withdrawal cascade (set and LIFO order) is then diffed against the cascade the runtime actually produced, turning each logged withdrawal into a conformance check, with three named defect kinds. Third, every policy refusal carries the nearest allowed space computed from the tables that refused it, with a proof marker that is sound only on facts immutable at the refusal site. An adversarial review of the first design found that these maps let an untrusted author reconstruct the operator's policy; the fix collapses the untrusted view to one non-discriminating verdict, and a matrix test asserts byte-identity across families. On main today: three mechanisms, 27 runtime-why tests, 28 derivation-trace tests, and 15 plus 32 navigable-refusal tests. We report no user or agent study; that is stated as the main gap.

## Problem and claim
Compilers throw away their search. G4 (an emission reaches a method declared plain), G3 (a cycle) and G2 (two providers) are verdicts of whole-composition searches, and the old diagnostic printed the conclusion only. The docs say so directly: the author "had to re-run the search by hand" (`docs/why-traces.md`, opening paragraphs before the example). At run time the problem is the same one level down: the streamed lifecycle trace carries events with no causes (`docs/why-runtime.md:12-17`), and an APM can only reconstruct the because from timing. At the policy layer, denials answered unevenly: some named the fix, several named only the violated rule (survey table at `docs/design/274-navigable-refusals.md:38-66`).

The claim is narrower than "explainable systems are good". It is that three properties of the language make the explanations derived rather than inferred, and that a single constraint (do not leak policy through the explanation) shapes the design of the third mechanism. Provision uniqueness (G2) and acyclicity (G3) make the runtime cause of a withdrawal unique and the cascade finite (`docs/why-runtime.md:18-29`). Because the cause is a graph fact and the transition is an observation, the two are independent and can be compared; a disagreement is always a defect in one of them (`docs/why-runtime.md:158-197`).

The honest scope: the oracle checks the withdrawal cascade of one composition on one run, not the whole runtime, and the navigable-refusal maps are verified by structural tests, not by an agent benchmark (the design's own "bench delta" test is not on main).

## Contributions
1. Derivation-carrying rejections: G4, G3 and G2 diagnostics carry a `WhyTrace` of `TraceStep`s as data (chain or set shape, best-effort locations, shortest deterministic witness), rendered for humans, emitted in `--json-diagnostics`, and handed over MCP; collecting the evidence is observationally invisible to the verdict. `revl explain <code>` gives the guarantee and fix per code.
2. Runtime why: a v2 JSONL trace where every settled load, withdraw and emit transition carries a cause (`boot`, `requirements`, `trigger`, `provider-withdrawn`, `liveness-expired`, `transport-fault`), a cause-chain walk (`revl why`), and an additive schema (v1 events still parse).
3. The withdrawal oracle: the static `withdraw` prediction (exact set, LIFO order) diffed against the logged cascade, with defects `missing-teardown`, `unexpected-teardown`, `order-mismatch`, exposed as `revl run --withdraw` and `revl why --check`.
4. Navigable refusals: a `navigate` entry beside every wired policy refusal (family, blocked flag, alternatives each tagged by who enacts it, proof marker), covering taint sinks, boundary policy and seven further families, with `clears-this-gate` forbidden on runtime-mutable operands.
5. The untrusted-author leak analysis and its fix: a single non-discriminating verdict, redaction by fact class, and a byte-identity matrix test across families, including redacted-versus-genuinely-blocked.
6. Structured refusals with a next call (`next: {tool, arguments, ready}`) and a usage error that is distinct from a composition verdict, in the MCP surface.

## Related work
| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Why-provenance in Datalog (Buneman et al., "Why and Where" (citation to be checked); Green et al. provenance semirings (citation to be checked)) | Marks which input facts support a derived fact | The provenance is attached to a compiler verdict and a lifecycle edge, and is checked by a second, independent observation (the oracle) |
| Dapper, OpenTelemetry, APM causal inference (citation to be checked) | Reconstruct request causality from propagated context or timing | No propagation or guess: the cause of a withdrawal is read from a graph the checker proved unique and acyclic. The OTel export is a projection, not the source |
| Elm and Rust error messages (citation to be checked) | Human-oriented hints per error | Evidence is data, not a pre-formatted string; the same object feeds terminal, JSON and MCP consumers |
| Differential testing and test oracles (citation to be checked, e.g. McKeeman) | Compare two implementations | Compares a compile-time proof with a runtime observation of the same composition, so neither side needs a third arbiter (`docs/why-runtime.md:158-197`) |
| Explainable-AI and counterfactual explanation (citation to be checked) | Explain model outputs | Not related to models; the nearest analogue is the "nearest allowed" alternative, computed from the refusing tables rather than learned |
| Information-flow and side-channel work on error oracles (padding-oracle style attacks; Denning-style flow) (citation to be checked) | Error behaviour can leak secrets | The refusal explanation itself is the oracle; the design collapses it to one verdict and tests indistinguishability |

## Evidence on main
| Claim | path:line or test | Status | Note |
|---|---|---|---|
| G4/G3/G2 rejections carry the derivation as data | `docs/why-traces.md:34-70` (WhyTrace, TraceStep), `src/revl/why.py` (154 lines); `tests/test_why_traces.py::test_g4_multi_hop_chain_is_the_whole_derivation`, `test_g3_three_component_cycle_path`, `test_g2_conflict_names_both_providers_and_both_locations` | shipped | 28 test functions in the file |
| Trace never changes a verdict or the first line | `docs/why-traces.md:170-184`; `tests/test_why_traces.py::test_g4_first_line_is_unchanged`, `test_rejections_without_a_search_carry_no_trace` | shipped | The first-line invariant is tested for G4 |
| Trace reaches MCP and `--json-diagnostics` | `tests/test_why_traces.py::test_json_diagnostics_carry_the_trace`, `test_mcp_check_passes_the_trace_to_agents` | shipped | |
| `revl explain` covers every guarantee | `tests/test_why_traces.py::test_explain_every_guarantee_has_a_fix`; `docs/why-traces.md:185-224` | shipped | A subset of codes is deliberately "no diagnostic code" (same page) |
| Runtime trace with causes, schema v2, v1 still parses | `docs/why-runtime.md:35-122`; `src/revl/why_runtime.py:43` (`SCHEMA_VERSION = 2`); `tests/test_why_runtime.py::test_v1_fixture_still_parses_and_conforms`, `test_trace_round_trips_through_jsonl` | shipped | py tier only for tracing |
| Cause-chain walk (`revl why`) | `src/revl/why_runtime.py:401`; `tests/test_why_runtime.py::test_cause_chain_follows_a_withdrawal_to_its_root`, `test_cause_chain_follows_a_load_to_boot` | shipped | Truncated traces reported, not crashed |
| Withdrawal oracle with three defect kinds | `src/revl/why_runtime.py:322,527`; `tests/test_why_runtime.py::test_oracle_flags_a_missing_teardown`, `test_oracle_flags_an_unexpected_teardown`, `test_oracle_flags_an_order_mismatch` | shipped | Defects are produced by synthetic traces in these tests |
| Oracle on a real runtime cascade | `tests/test_why_runtime.py` (the `--withdraw` run test) | shipped | One composition; needs the cordis py runtime |
| Navigable refusal mechanism, closed family enum, proof marker | `src/revl/navigate.py:35-67,119`; `docs/design/274-navigable-refusals.md:1-40` | shipped | |
| Untrusted-author collapse and indistinguishability | `src/revl/navigate.py:53-57`; `tests/test_274_navigable_refusals.py::test_untrusted_author_matrix_is_mutually_indistinguishable`, `test_redacted_operator_only_is_byte_identical_to_genuine_blocked`; `tests/test_274_navigable_slice2.py::test_untrusted_matrix_across_new_policy_families_is_byte_identical` | shipped | The matrix in the slice-1 test has four members; slice 2 adds the other families |
| `clears-this-gate` never on a mutable operand | `tests/test_274_navigable_refusals.py::test_clears_this_gate_never_on_a_mutable_operand`, `test_soundness_sweep_over_wired_families_finds_no_live_clears`; `tests/test_274_navigable_slice2.py::test_no_clears_marker_sits_on_a_live_operand` | shipped | |
| All families wired | `docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:517` (marked complete) | shipped (per roadmap text; tests above are the check) | The design doc header still says "slice 1" (`docs/design/274-navigable-refusals.md:29`); the roadmap and slice-2 tests are newer |
| Navigation is additive and leaves first lines and census bytes alone | `tests/test_274_navigable_refusals.py::test_first_line_and_census_are_byte_identical_with_navigate`, `test_navigate_is_an_additive_json_key_only` | shipped | |
| Refusal carries its next call; usage error distinct | `tests/test_mcp_refusal_next_1691.py` (docstring lines 1-12); `docs/mcp-reference.md:75,103` (the `next` shape; lines 405-418 cover the disk-sync block, not this) | shipped | |
| Agent reaches compliance in fewer steps with navigation | design only: "The bench delta" at `docs/design/274-navigable-refusals.md:575-576` | designed | Not run on main |

## Numbers that exist
- Test counts, from `grep -c '^def test'` of test functions: `tests/test_why_traces.py` 28, `tests/test_why_runtime.py` 27, `tests/test_274_navigable_refusals.py` 15, `tests/test_274_navigable_slice2.py` 32. These count tests, not results of an experiment, and the tests were not run for this count.
- Schema: `SCHEMA_VERSION = 2` (`src/revl/why_runtime.py:43`), 3 event kinds (`docs/why-runtime.md:55`). Cause kinds: the code emits six (`boot`, `trigger`, `requirements`, `provider-withdrawn`, `liveness-expired`, `transport-fault`; `src/revl/why_runtime.py:148-241`), while `docs/why-runtime.md:55` says four. This paper follows the code.
- 3 searches covered by derivation traces (G4, G3, G2); 14 refusal families in the closed enum (`src/revl/navigate.py:37-41`; the roadmap says all are wired).
- Behavioural measurements (agent step counts, human debugging time, oracle detection rate on seeded runtime bugs): none yet.

## Paper outline
1. Introduction: three places a system throws away its reason, and the uniqueness that lets us keep it.
2. Background: G2/G3/G4 in one page; what "supplier" and "cascade" mean.
3. Derivation-carrying rejections: WhyTrace data model, shortest deterministic witness, the "never changes a verdict" invariant.
4. Runtime why: causes as graph facts, schema v2 and additive evolution, cause-chain walk.
5. The withdrawal oracle: prediction versus observation, independence argument, defect kinds, and what it does not promise.
6. Navigable refusals: nearest allowed space, enactor tags, the immutable-operand rule for the proof marker.
7. The leak: the adversarial review finding, the collapse, the indistinguishability test; the documented exception.
8. Evaluation: tests as spec, oracle mutation study, agent benchmark.
9. Related work and limits.

## Threats to validity and limits
- The docs' own limits: the oracle "checks the withdrawal cascade, not the whole run"; "A conforming run is not a proof of the runtime"; a "cascade never triggered is never checked"; `--withdraw` is a one-shot, not a live command (`docs/why-runtime.md:199-215`).
- Independence of prediction and observation is the whole value (`docs/why-runtime.md:210-215`). The cause label is still read from the provider graph, so the oracle cannot catch a wrong graph, only a runtime that disagrees with it.
- Tracing needs the cordis py runtime; the trace vocabulary and oracle are pure but only the py tier writes the trace (`docs/why-runtime.md:216-221`).
- Derivation traces explain only searches; a direct verdict has no trace (`docs/why-traces.md:170-184`). Only the first culprit is traced, so the trace is one worked example, not all of them.
- The leak result is a matrix test over a finite set of families and operations, not a proof, and the design review that found it was internal. Byte-identity over a finite matrix is evidence, not proof. The admit-profile family is an acknowledged exception: it enumerates the author's own granted set (`docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:517`).
- The adversarial review itself is not in the tree; the only trace on main is the CRITICAL comment in `src/revl/navigate.py` and the roadmap text.
- No evidence yet that agents or people benefit; "refusal is a map, not a wall" is a design principle on main, not a measured effect.
- The design doc header lags (slice 1 wording) while the roadmap text says all families landed. This paper follows the roadmap plus the slice-2 tests.

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 19 checked, 6 corrected.
