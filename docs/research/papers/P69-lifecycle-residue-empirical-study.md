---
id: P69
title: "How Often Do Plugins Leak? A Residue Probe for Raw Cordis Plugins, and What a Compile-Time Lifecycle Gate Would Refuse"
theme: empirical
kind: empirical
maturity: partial
status: The probe and an unload-surface survey are on main with fixtures and a self-check; a first measurement exists only on a self-authored 10-plugin corpus, and the population study has not been run.
fused_with: P68
---

## Pitch

We give a model-free probe that mounts and unmounts any Cordis plugin N times and names which of four runtime categories failed to return to baseline, and we use it to put a number on how often unconstrained plugin code leaks, which is the share a compile-time lifecycle check is designed to refuse.

## Abstract

Plugin runtimes let code be loaded and unloaded while a process runs, and every plugin is trusted to undo what it acquired. Nothing in the host language checks that. We present a residue probe for Cordis, a TypeScript plugin runtime. The probe mounts and unmounts a plugin N cycles on a real Cordis instance and compares four observable categories (registry, provisions, effects, listeners) against a baseline taken before the first mount. A plugin is classified clean, leaked or error, and no model is in the loop, so any corpus can be re-scored for free. The four categories are the same ones a revl composition must prove back at baseline on teardown, so "leaked" is meant to mean "revl would have refused this at compile time or on the exit proof", a mapping we have not tested by experiment. The repository's self-check asserts that the probe separates a clean fixture from a leaky fixture with a known leak set (we read that check and did not run it), and we report a first measurement on a 10-plugin corpus that we wrote ourselves: 4 of 10 leak. We state plainly that this figure shows the probe detects the leaks we planted and is not a population rate. We also survey six agent-framework packages at pinned versions (five projects; LangChain's JavaScript and Python packages are counted separately) for a published way to retire one registered tool: none publishes one, five publish no unload path under the names and paths searched, and one publishes teardown only at toolset scope. We describe the protocol that would turn the instrument into a population study of third-party plugins and of model-written plugins.

## Problem and claim

Hot-loadable plugin systems depend on a discipline: whatever a plugin binds to a long-lived context must be undone by its own teardown. In Cordis the common mistake is attaching a listener, a provision or a sub-plugin to `ctx.root` instead of the plugin's own fiber. That works the first time and leaks on every unload. The cost shows up as growing listener counts and stale services after hot swap, far from the cause.

The claim has two parts. First, the leak class can be measured by a small, deterministic, model-free oracle on the real runtime, with no change to the plugin under test. Second, a language that makes the same four categories a compile-time and exit-time obligation would refuse the plugins this oracle flags. That is a mapping, not yet an experiment. If it holds, the probe's count is a lower bound on the four-category leaks a gate would refuse, because the probe omits resources outside those four categories.

The paper does not claim a population leak rate today. The only measured rate is on a corpus the author wrote. The claim about frameworks is narrower and is checkable: it concerns published API surface at pinned versions, not behaviour.

## Contributions

1. A residue probe for Cordis plugins: N mount/unmount cycles, four categories, three outcomes (clean, leaked, error), exit codes 0/1/2, no model and no cost (`tools/residue-probe/README.md`, `tools/residue-probe/probe.ts`, `tools/residue-probe/run.mjs`).
2. A contract equivalence between the probe and the revl exit proof: each probe category maps to the check in `_Driver._teardown` (`src/revl/run.py:2589-2622`), so a probe-flagged plugin is one revl is expected not to admit (a mapping; see Threats).
3. A scoring path that treats raw TypeScript as a control arm scored on lifecycle correctness rather than compile rate, because raw TypeScript always compiles (`bench/score_raw_ts.py:1-25`, `bench/prompts/raw-ts.md`).
4. A first measurement on a 10-plugin hand corpus (4 leak, 6 clean) with the ordinary mistake behind each leak, labelled as not a population number.
5. A falsifiable survey of unload surface across six agent-framework packages (five projects), one tool host and one control, with a checker that can fail and a written account of the first version being wrong (`bench/framework_unload_survey.py`, `bench/results/framework-bench/unload-survey.json`).

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| LeakCanary, Chrome DevTools heap snapshots | Find leaked objects by heap inspection, per application | The probe checks a declared contract (four named categories) at the plugin boundary of one runtime, deterministic and scriptable, no heap diff to interpret |
| Node EventEmitter MaxListeners warning | Warns when one emitter holds many listeners | The probe reports growth across mount cycles against a pre-mount baseline, and covers provisions, registry and effects as well |
| Empirical studies of Android lifecycle bugs (Liu et al.) (citation to be checked) | Mine leaks in apps and classify causes | We do not mine; we give an oracle and a protocol, and tie the oracle to a compile-time refusal in a language |
| Erlang/OTP supervision | Restarts and cleans up by process isolation | Residue here is in-process shared state; the gate is static plus an exit proof, not isolation |
| Valgrind, sanitizers | Detect native memory leaks at run time | Different resource class (runtime registrations, not memory); same idea of a baseline check at exit |
| Agent tool frameworks (pydantic-ai, semantic-kernel, langchain, OpenAI agents SDK, crewai) | Register tools; unload is out of scope | We measure which of them publish any retirement path at all, at pinned versions, with a checkable artifact |

## Evidence on main

Tree: revl main at commit 45bec431f.

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Probe mounts/unmounts N cycles and reports four categories | `tools/residue-probe/README.md:1-60`, `tools/residue-probe/probe.ts` | shipped | README gives the field mapping to `run.py`; Node >= 23.6 |
| Probe separates clean from leaky fixture | `tools/residue-probe/test.mjs:29-60`, `tools/residue-probe/fixtures/clean-plugin.ts`, `tools/residue-probe/fixtures/leaky-plugin.ts` | shipped | Leaky fixture must leak exactly {registry, provisions, effects, listeners}; listener count must grow per cycle. Run via `npm test` in that directory; not run for this draft |
| Same contract as the revl exit proof | `src/revl/run.py:2589-2622` | shipped | registry, provisions, effects, listeners checks, plus extra checks (inverse residue, models) the probe does not have |
| Probe is blind to host resources and function correctness | `tools/residue-probe/README.md:39-43`, `bench/results/hand-corpus/summary.md` (Method note) | shipped (as a stated limit) | A plugin can be probe-clean and miss its brief |
| Raw-ts scored as clean / leaked / error | `bench/score_raw_ts.py:1-25`, `:45` | shipped | `DEFAULT_CYCLES = 5` |
| Raw-ts is the control arm of the same briefs | `bench/prompts/raw-ts.md:1-40`, `bench/specs.json` | shipped | 30 specs |
| Hand-corpus result: 4/10 leak, categories registry 2, provisions 3, effects 4, listeners 1 | `bench/results/hand-corpus/summary.md` | shipped | 6 cycles per plugin. Authored by this repository, by hand (`bench/framework_bench.py:455-468`) |
| The report itself marks that number as non-population | `bench/framework_bench.py:462-467`, `tests/test_framework_bench.py:323-328` | shipped | The test requires the caveat to be rendered |
| Model-written raw-ts on a pinned local model: 1/6 "carry residue" | `bench/results/pinned-three-host/summary.md` | partial | The one cell is a 900 s runner timeout on `03-user-cache`, not a leak. 0/6 leaked. Do not quote 17% |
| Unload survey: of 6 agent-framework packages (5 projects), 0 publish a per-registration retirement, 5 publish no unload path, 1 publishes per-toolset teardown | `bench/results/framework-bench/report.md` ("Unload paths across the ecosystem"), `bench/results/framework-bench/unload-survey.json` | shipped | Pinned versions listed there; tool host (MCP SDK 1.30.0) and control (cordis 4.0.0-rc.10) excluded from the denominator |
| Survey claims are checked against the published artifact and the checker can fail | `bench/framework_unload_survey.py:403` (`check_claim`), `:536` (`check`), `tests/test_framework_unload_survey_tarslip.py` | shipped | The report notes that an earlier keyword version was wrong and was deleted |
| MCP SDK registration handle has `remove()` that is name-scoped, not resource-scoped | `bench/hosts.json:163-174`, `bench/results/framework-bench/unload-survey.json` (mcp.d.ts:289, a logged hit; the tarball is not in the tree, so the line was not re-fetched) | shipped | A presence claim: a symbol exists, not that it releases anything |
| MCP third host probed for residue | `bench/mcp_host/probe.mjs`, `bench/results/pinned-three-host/summary.md` | partial | 4/6 clean, 2/6 could not be probed (generated code did not parse) |
| revl is compile-gated so no leaking component reaches a corpus | `bench/results/framework-bench/report.md` table, residue row | partial | Stated by the report; no experiment yet takes the 4 leaky plugins, expresses them in revl and shows each refused |

## Numbers that exist

- 4 of 10 hand-authored raw Cordis plugins leak, 6 cycles each; leaks by category registry 2, provisions 3, effects 4, listeners 1. Source `bench/results/hand-corpus/summary.md`. n = 10, written by the repository author, 4 planted by design. This is a detection check, not a rate.
- Pinned-model run (Ornith-1.5-35B-A3B Q4_K_M, local, 5 cycles): raw-ts 5/6 clean, 0/6 leaked, 1/6 did not mount (timeout). Source `bench/results/pinned-three-host/summary.md`. n = 6 of 30 specs (the `results.jsonl` rows; the report's headline table says n=3 per host, which contradicts the data and is not used here). No leak was observed; the sample says nothing about rate.
- Same run, MCP host: 4/6 clean, 0/6 leaked, 2/6 unprobeable. Same source, n = 6.
- Framework survey: 6 agent-framework packages (5 projects), 0 per-registration retirement, 5 none at all, 1 toolset-scoped. Source `bench/results/framework-bench/report.md`, `bench/results/framework-bench/unload-survey.json`. n = 6, pinned versions.
- No result from a corpus of third-party plugins. None yet. No result from a full 30-spec model run of raw-ts: `bench/results/hand-corpus/summary.md` says that run "requires a funded `cline` run" and was not made.

## Paper outline

1. Introduction. Hot-loading plugins and the unwritten teardown contract; the research question; headline numbers once a third-party corpus exists.
2. Background. Cordis fibers, contexts, the four categories; why `ctx.root` is the common mistake.
3. The probe. Method, baseline and warmup semantics, outcomes, limits (host resources not covered).
4. Contract equivalence with the revl exit proof, and what "would have refused" means precisely.
5. Study design and corpora: third-party plugins, model-written plugins, hand corpus as probe validation.
6. Results. Rates by category, growth versus fixed offset, error class, refusal experiment.
7. Ecosystem survey of unload surface. Method, the failed first version, results.
8. Threats to validity.
9. Related work and conclusion.

## Threats to validity and limits

- The only measured rate is from a corpus we wrote, with leaks we planted. The repository's own report says it "demonstrates that the probe detects the leaks we planted, not what rate a population leaks at" (`bench/framework_bench.py:462-467`).
- The pinned-model "1/6" is a timeout. Quoting it as a leak rate would be an error.
- The probe covers four categories. It does not see host-resource leaks (pools, maps) or timers and sockets, and it says nothing about functional correctness (`bench/results/hand-corpus/summary.md`, Method note).
- "Revl would have refused" is a mapping of categories, not an experiment on equivalent programs. It is also self-referential: the probe was built from the same contract revl enforces, so agreement is by construction.
- A failed mount is counted as residue-carrying because revl would not admit it; that choice inflates the leak rate relative to a pure leak count and must be reported separately.
- The in-tree golden `UserCache` check in `tools/residue-probe/test.mjs` notes that its fiber stays pending and never activates, so its "no residue" result is weak evidence; an activated case is needed. Probe false positives (a plugin that legitimately keeps a root-level provision by design) and false negatives (timers, sockets) are not yet measured.
- Framework survey `absent` verdicts are scoped to the paths and names searched; several frameworks keep a plain mutable dict a caller can reach into (stated in the report). Presence of `remove()` is not evidence it releases resources.
- Pinned versions age; the survey is a snapshot. The Cordis version is a release candidate (4.0.0-rc.10 in the survey, rc.8 pinned in the probe README), so results may not transfer to a stable release.
- Cordis has a small plugin ecosystem; a third-party corpus may be small or biased toward plugins that need no injected services.
- The framework report states nobody outside the repository has run the suite.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 31 checked, 4 corrected.
