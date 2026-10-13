---
id: P20
title: "Replaying Agent Runs: A Write-Ahead Log That Seals Each Model Decision and States Which Replay Modes the Log Can Support"
theme: effects-replay
kind: full
maturity: partial
status: Sealed model-decision evidence, an offline reader and a replay-readiness planner are shipped on the Python tier with tests; no replay mode is executable and no evaluation exists yet.
fused_with: P18, P19, P21
---

## Pitch

A write-ahead log can seal each model decision as a MAC-covered evidence object and then tell you, mode by mode, whether the log is enough to replay the run exactly, with tools only, with another model, or counterfactually, and which inputs are missing when it is not.

## Abstract

Agent observability tools capture prompts and responses, but they do not say whether a run could be replayed, nor detect a stored decision altered after the fact by a party without the sealing key. We describe an LLM-aware write-ahead log in revl. Each model crossing writes a durable `model-decision` entry; when a run engages evidence sealing, the crossing seals a MAC-covered object binding the model digest, placement, prompt binding, input origins, candidate set, chosen candidate, outcome, sampling, policy digest and fallback depth. An offline reader rebuilds the decision from the log alone and returns no reading when any member has been edited. A readiness planner then evaluates four replay modes (exact, tool-only, model-substitute, counterfactual) against a fixed vocabulary of required inputs and reports, per mode, which inputs the log holds and which are missing. A mode is never reported executable offline. The causal trace treats the model completion as a first-class hop, with a salted prompt digest, host-reported cost fields marked unverifiable, and a per-activation identifier because a produced-sequence number is not a causal proof under concurrency. The evidence is structured as tests that edit each sealed member in the WAL file and require refusal, and a mutation-style test that reintroduces a historical MAC bug and shows the tamper suite reddens. The live executor that would actually run a mode is specified and deferred; response text is never written, so exact and tool-only replay are unreachable from a WAL by design. Test coverage: 56 + 33 + 17 + 13 + 61 test functions across five files; no performance or user-study data exists.

## Problem and claim

Replay of agent runs is commonly assumed to need full capture of prompts and responses. That capture is the exfiltration channel: a prompt may contain secrets, and a stored digest of a short secret is a confirmation oracle. Meanwhile "we logged the decision" is not accountability if the log can be edited without trace.

The claim: a log can carry enough, sealed and content-free, to rebuild what a model decision was (what answered, how the prompt was bound, what candidates existed, under which rule) and to state exactly which replay modes it supports, without storing prompt or response text. A tampered decision yields no reading rather than a reading with a warning.

The claim is not that agent runs can be replayed. On main the live executor does not exist: `revl replay` reports readiness only and `executable` is false for every mode (`src/revl/replay_modes.py:365`; `tests/test_250_replay_modes.py:119`). The paper is about the log format and the readiness contract.

## Contributions

1. A sealed `ModelDecision` evidence object with a closed member list (`BODY_MEMBERS`, `src/revl/model_evidence.py:279`), written at the crossing through a callable sealer so the runtime never holds the key (`docs/design/552-model-decision-replay.md` section 2; `CrossingSealer`, `src/revl/model_evidence.py:1020`).
2. A reader that verifies and reconstructs the decision from the WAL alone and returns no decision when verification fails, including a join check that a genuine seal lifted onto another crossing is refused (`reconstruct`, `src/revl/model_evidence.py:1176`; design doc section 3.1).
3. A readiness planner over four replay modes and a fixed requirement vocabulary (`modelDecisions`, `responseText`, `promptDigest`, `toolCalls`, `seedsAndClock`, `liveComponent`), with an explicit rule that blocked modes name the missing input (`src/revl/replay_modes.py:86`; `docs/design/250-slice3b-replay-modes.md`).
4. Fail-direction discipline: three states for evidence (not sealed, sealed, refused-and-stopped), the refusal written before the raise so a post-mortem can tell "refused" from "never engaged" (design 552 section 1).
5. A causal trace in which the model completion is a hop, with salted prompt digests, secret suppression, honest-degrade fields, and per-activation ids (`src/revl/trace.py`; `docs/design/121-revl-trace.md`; `tests/test_trace_121.py`).
6. A non-vacuity method for tamper tests: generated from `BODY_MEMBERS` and checked by injecting the historical bug (`tests/test_model_evidence_replay_552.py:662`).

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| LangSmith, Langfuse, OpenTelemetry GenAI semantic conventions | Capture prompts, responses, tokens, cost as spans | No prompt or response text is stored; the log entry is sealed and tamper-evident; readiness for replay is stated rather than assumed |
| VCR / cassette capture-and-replay testing (vcrpy, Polly) | Stores HTTP responses to replay in tests | Does not store responses; says which modes are therefore unreachable |
| Temporal event history | Deterministic replay of workflow code from stored event results | Targets nondeterministic model hosts where only a decision summary is kept |
| rr and Pernosco | Whole-process execution capture and replay | Captures at the model boundary only; no process-level determinism |
| SWE-agent style trajectory replay (citation to be checked) | Re-runs or inspects agent trajectories | Not the same layer: this is a log format with integrity, not a trajectory viewer |
| Event sourcing | Rebuild state from an event log | Same shape; the contribution is the sealed model-decision event and the readiness vocabulary |
| Signed transparency logs, Sigstore-style attestation (citation to be checked) | Third-party-verifiable signing | revl uses a shared-secret MAC; the docs say a key holder can seal any well-formed entry |

All citations are unchecked; a related-work pass is still required.

## Evidence on main

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| A model crossing writes one `model-decision` entry after its effect | `tests/test_250_model_decision_wal.py:95` | shipped | Slice 3a |
| No prompt or response text reaches the WAL | `tests/test_250_model_decision_wal.py:137` | shipped | |
| Pre-3a WAL bytes unchanged | `tests/test_250_model_decision_wal.py:227` | shipped | |
| Retries counted on one decision; exhausted budget still writes | `tests/test_250_model_decision_wal.py:248`, `tests/test_250_model_decision_wal.py:269` | shipped | |
| Entry invisible to partition and recover | `tests/test_250_model_decision_wal.py:325` | shipped | |
| Four modes planned; none executable offline | `tests/test_250_replay_modes.py:107`, `tests/test_250_replay_modes.py:119` | shipped | Readiness only |
| Exact and tool-only never plannable without response text | `tests/test_250_replay_modes.py:135` | shipped | By design |
| Model-substitute and counterfactual plannable when decisions are logged | `tests/test_250_replay_modes.py:125` | shipped | "plannable" means informable, not runnable |
| Sealed evidence written by a real run, read back, and refused on any edit | generated tamper suite (`tests/test_model_evidence_replay_552.py:662` is the injected MAC-bug test; the lifted-seal join check is `tests/test_model_evidence_replay_552.py:634`); `docs/design/552-model-decision-replay.md` section 5 | shipped (py tier only) | The design doc states 53 cases; there are 33 test functions in the file, the rest presumably parametrised |
| Refusal written before the raise, so the artifact names the crossing | `tests/test_model_evidence_replay_552.py:337` (`test_the_refusal_reaches_the_artifact_before_the_run_stops`) | shipped | |
| Engaged with no durable sink refuses | `tests/test_model_evidence_replay_552.py:385` | shipped | |
| Placement cross-checked with the model route table | `tests/test_model_evidence_replay_552.py:758`, `tests/test_model_evidence_replay_552.py:799` | shipped | |
| `revl replay --evidence-key` verifies and reconstructs | `src/revl/cli/parser.py:1939-1950` | shipped | |
| Verifier and sealer fail closed on each check their tests cover | `tests/test_model_evidence_517.py` (56 test functions) | shipped | |
| Trace hop with provenance, salted digest, no text field | `src/revl/trace.py:1-40`; `tests/test_trace_121.py` (61) | shipped | |
| Per-activation id | `src/revl/why_runtime.py:142`; `src/revl/run.py:1451`; `tests/test_trace_121.py:705` | shipped | Honest-degrade gating (`tests/test_trace_121.py:666`) and the fiber-local token were not verified |
| Live executor (`revl replay branch`) running a mode | `docs/design/250-slice3b-replay-modes.md` section "The live executor (deferred, with its requirements)" | designed, deferred | Roadmap item 250 (`docs/v2.0-roadmap.md:1390`) still lists `revl replay branch` as deferred |
| Exact and tool-only replay | `docs/design/250-slice3b-replay-modes.md` | not reachable by design | response text never written |
| Seed and clock captured | `docs/design/250-slice3b-replay-modes.md` | not built | counterfactual without it is "a divergent continuation, not a controlled A/B" |
| Non-py tiers write evidence | `docs/design/552-model-decision-replay.md` section 6 | not built | reads as "not sealed" |
| `revl canary` names the differing evidence member | `docs/design/552-model-decision-replay.md` section 6 | not built | Slice 4 |

## Numbers that exist

None as measurements. Test-function counts from `rg -c` (not run): 17 (`tests/test_250_model_decision_wal.py`), 13 (`tests/test_250_replay_modes.py`), 56 (`tests/test_model_evidence_517.py`), 33 (`tests/test_model_evidence_replay_552.py`), 61 (`tests/test_trace_121.py`). The 552 design doc states "53 tests, all passing, no skips" for its file; they were not run for this draft.

## Paper outline

1. Introduction: replay is assumed, accountability is assumed; both are unmeasured. State the narrow claim.
2. Threat model: prompt text as exfiltration channel, confirmation oracle on digests, shared-secret MAC limits.
3. The WAL entry: Slice 3a decision entries and what they leave out.
4. Sealed evidence: members, sealer-as-callable, three states, fail direction.
5. Reading back: verify, reconstruct, join check, no reading on failure.
6. Replay modes as a readiness lattice: requirement vocabulary, plannable vs executable.
7. Causal trace of model hops: honest degrade, activation ids.
8. Evaluation: tamper suite with injected bug, overhead, (if built) live executor results.
9. Related work, limits.

## Threats to validity and limits

- No mode is executable. The docs say "`executable` always false offline" and "Reading a decision back is not re-executing it".
- The cryptographic claim is weak and the docs say so: the threat model is a shared-secret one, a holder of the key can seal any well-formed entry, there is no key management, rotation or distribution, and the construction has not had a cryptographic review.
- The provider is trusted for what only it can see: model digest, placement digest, candidate set and prompt binding are declared, not observed.
- Only the py tier writes evidence; other tiers read as "not sealed".
- Host-reported cost, tokens and model name are marked unverifiable in the trace.
- A WAL with no `model-decision` entry cannot be told from a run that made no completion.
- Prompt digest across runs is meaningful only in the unsalted `content-address` mode, which is legal only for inputs with no secret or confidential origin.
- The "counterfactual" mode in this paper is the planning question; the question-answering counterfactual is a separate paper (P19).

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 55 checked, 7 corrected.
