---
id: P70
title: "Green That Measures Nothing: Dead Test Switches, Silent Skips and Typechecked Demos That Never Run"
theme: empirical
kind: empirical
maturity: shipped-evidence
status: "Guard, switch and CI wiring shipped on main with tests; one-laptop before/after measurement exists, no history series or external replication yet."
fused_with: P47
---

## Pitch

A skip is the same colour as a pass, so tests gated behind a switch no CI job sets, a toolchain no CI job installs, or a demo that is only typechecked report green while measuring nothing. We classify the gate shapes, measure what executing them costs and finds, and give a guard that makes each shape a build failure.

## Abstract

Test suites fail silently in a way dashboards do not show: a correct test is gated behind an environment variable, a filesystem probe or a toolchain that continuous integration never provides, so every test reports skipped, and skipped is green. We report an experience from a multi-backend compiler repository where this happened three times in one quarter. One job ran `pytest tests/` without cordis-py installed, so 398 tests across 81 modules executed nowhere. A cross-tier suite had its slow probes gated behind a variable set in no workflow, so the Rust and Java halves never ran and two Java correctness defects sat under assertions that already covered them. A TypeScript demo asserted an impossible answer for months because CI typechecked it but never ran it. We describe four gate shapes (unset variable, filesystem probe, right variable in the wrong job, typechecked-only file), the audit that found them, and a static guard that reads the workflow files and fails when a switch, a toolchain or a test file is not exercised by a job that can fail the build. Executing the skipped tests of the cross-tier file on one machine moved it from 30 s with 93 passed and 94 skipped to 6 min 31 s with 180 passed and 5 skipped: the pass count rose by 87, and the totals at the two ends differ by two tests that the source does not explain. We state what the guard does not catch, and which instances remain open.

## Problem and claim

A test that is skipped reports no failure. In a repository that supports six code-generation tiers, each needing its own toolchain, "skip when the toolchain is absent" is the right local behaviour and the wrong CI behaviour: a job that installed the toolchain and still skips has a broken provisioning step, and nothing says so. The same holds for slow tests gated behind an opt-in variable that nobody opts into.

The claim: this is a class with a small number of recognisable shapes, most of its documented instances were found by tripping over a defect the dead suite already covered rather than by looking for the class, and it can be closed by two cheap mechanisms. One is a switch that turns "toolchain absent" into a failure for the tiers a job has provisioned. The other is a static check that every gate and every tier test is wired to a job that can fail the build.

The claim is not that the guard is complete. The guard's own docstring lists what it does not catch.

## Contributions

1. A taxonomy of four gate shapes with an instance of each from one repository: an environment variable set nowhere; a filesystem probe (`node_modules` absent) in place of a variable; the right variable set in the wrong job; and a file that is typechecked but never executed.
2. A static guard, `tests/test_env_gated_skips_run_somewhere.py`, that reads the CI workflow files and fails when a variable that tests read is set nowhere, set only in a job that does not run the reading test, or when a tier test is not run by a step requiring its tier; plus the guard's own check that it cannot skip.
3. A runtime switch, `REVL_REQUIRE_TIERS`, and a marker type (`Absent`) that turn only the "toolchain not installed" kind of skip into a failure while leaving by-design refusals as skips (`src/revl/test.py:175-215`).
4. A measured cost and yield of executing the skipped tests: one file, 30 s to 6 min 31 s, 93 to 180 passes, 87 more passes, one failure found (Java structural equality) and fixed before the flip.
5. A negative result on conformance validators: they stop at compile depth, so a cross-tier value question cannot be answered by the corpus, which is why a typechecked demo could be wrong for months.

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Flaky test studies (Luo et al., Google's flakiness reports) (citation to be checked) | Study tests that fail nondeterministically | This is the opposite failure: a test that cannot fail because it does not run |
| Mutation testing | Checks whether tests detect injected faults | Cheaper and coarser: asks whether the test is executed at all in any job |
| Vacuity detection in model checking (Kupferman-Vardi) (citation to be checked) | Detects specifications that pass trivially | Same idea at the CI-gate layer: a green that holds for the wrong reason |
| CI configuration smell studies (citation to be checked) | Catalogue misconfigurations in CI files | We tie each smell to a real hidden defect and a measured execution cost, and give a guard that is itself tested |
| Skip audits in a single job (junit skip counts) | Count skips per run | Cross-references every switch tests read against every job that runs the reading file, which a per-run count cannot see (the "right variable, wrong job" shape) |

## Evidence on main

Tree: revl main at commit 45bec431f. The relevant roadmap entries are 430, 433, 446 and 453 in `docs/v2.0-roadmap.md`. Item 430 has no heading of its own; it appears only in the prose of 446.

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Dead test switch class, audit of genuine gates vs overrides | `docs/v2.0-roadmap.md:1864-1866` | shipped | 17 `skipif` decorators for `REVL_CROSS_TIER_SLOW` across two files; of four "dead" switches, one dead and three overrides |
| Item 430: one job ran `pytest tests/`, no cordis-py installed, 398 tests across 81 modules ran nowhere | `docs/v2.0-roadmap.md:1864` | documented finding | No item 430 heading exists; the count appears only in the prose of 446 and was not recomputed |
| Item 433: slow cross-tier switch set in no CI job; Java `Int / Int` integer division and Float `==` inversion survived | `docs/v2.0-roadmap.md:1729`, `docs/v2.0-roadmap.md:1864` | shipped | Fixed 2026-09-02; Java half was verified by inspection at the time (no JDK found), later run on a real JDK (`docs/v2.0-roadmap.md:1874`) |
| Second shape, filesystem probe: `RUNNERS["ts"]` needs `node_modules/.bin/vitest`, no test job ran `npm ci` | `docs/v2.0-roadmap.md:1868`, `tests/test_env_gated_skips_run_somewhere.py:36-60` | shipped | The BigInt detail is in the guard docstring (`tests/test_env_gated_skips_run_somewhere.py:40-50`): a live `TypeError` sat under the skip until two contributors with `node_modules` tripped over it |
| Third shape, right variable wrong job (found by audit): `REVL_CORDIS4J_CLASSES` set in `backend-java`, read by `tests/test_realm_conformance.py` | `docs/v2.0-roadmap.md:1870`, `.github/workflows/ci.yml` (comment near 2250-2260), `tests/test_env_gated_skips_run_somewhere.py:714` | partial | Explicitly not closed; held as a known wrong-job registry entry |
| Measured: 30 s / 93 pass / 94 skip to 6m31 / 180 pass / 5 skip; 87 newly run | `docs/v2.0-roadmap.md:1872` | shipped | One arm64 laptop, one file; intermediate steps 3m53 (128 pass) and 4m53 (156 pass). Not a CI measurement. Totals do not add: 93+94=187 at baseline, 180+5=185 at the flip; two tests are unaccounted for in the source text |
| Full matrix produced exactly one failure, fixed before the flip | `docs/v2.0-roadmap.md:1874` | shipped | `test_probe_executes_identically_slow[java-structural equality]`; the earlier "no JDK" premise was wrong because the JDK was keg-only and off `PATH` |
| The slow switch is now live in CI | `.github/workflows/ci.yml:2292` | shipped | Set on the step that runs the cross-tier files |
| Tier tests required to run with their toolchain | `.github/workflows/ci.yml:2305`, `.github/workflows/ci.yml:2346`, `src/revl/test.py:175-215` | shipped | `REVL_REQUIRE_TIERS` is `py,ts,go,rust`; java and wasm are not required (comment at `.github/workflows/ci.yml:2295-2304`) |
| Guard: every env gate set in CI or declared local | `tests/test_env_gated_skips_run_somewhere.py:671` (`test_every_env_gate_in_tests_is_set_in_ci_or_declared_local`) | shipped | Also `tests/test_env_gated_skips_run_somewhere.py:696` stale-declaration check, `tests/test_env_gated_skips_run_somewhere.py:772` local declarations need a reason |
| Guard: gate set in a job that actually runs the reading file | `tests/test_env_gated_skips_run_somewhere.py:714` | shipped | |
| Guard: every tier test file run by a step requiring its tier | `tests/test_env_gated_skips_run_somewhere.py:1013` | shipped | Exemptions enumerated with reasons at `tests/test_env_gated_skips_run_somewhere.py:849`, checked by `tests/test_env_gated_skips_run_somewhere.py:1055` |
| Guard credits a step only if it can fail the build; `if: false`, `continue-on-error`, run-time-selected targets credit nothing | `tests/test_env_gated_skips_run_somewhere.py:1101`, `tests/test_env_gated_skips_run_somewhere.py:1118`, `tests/test_env_gated_skips_run_somewhere.py:1174`, `tests/test_env_gated_skips_run_somewhere.py:1202` | shipped | Parametrised tests |
| Guard cannot itself skip | `tests/test_env_gated_skips_run_somewhere.py:1225` | shipped | The guard once used `importorskip` and skipped on a matrix without PyYAML |
| Guard that CI-set gates are also set on the local pre-merge path | `tests/test_env_gated_skips_run_somewhere.py:1598`, `tests/test_env_gated_skips_run_somewhere.py:1622` | shipped | |
| Typechecked demo asserted an impossible answer, `node demo.ts` ran nowhere | `docs/v2.0-roadmap.md:1888-1892`, `backends/typescript/demo.ts` | shipped | Fixed in PR #243; the python demo had run in CI |
| Demo step now unconditional, ordered after `npm ci`, exits non-zero on failure | `tests/test_ts_demo_runs_in_ci.py:68`, `tests/test_ts_demo_runs_in_ci.py:78`, `tests/test_ts_demo_runs_in_ci.py:89`, `tests/test_ts_demo_runs_in_ci.py:106` | shipped | Verified non-vacuous by deleting the step: three of four checks red (`docs/v2.0-roadmap.md:1892`) |
| Conformance validators stop at compile depth | `docs/v2.0-roadmap.md:1894`, `tools/conformance.py`, `tools/validate.py` | shipped (as a finding) | Taken from the roadmap text; not independently re-derived from the tool files |
| wasm demo still never executes in CI | `docs/v2.0-roadmap.md:1896` | open (not implemented) | Allowed by a single exemption string in the `backend-wasm` job |
| Earlier general hazard section | `docs/v2.0-roadmap.md:526-533` | shipped | "the hazard is never a red test, it is a test that was never collected" |

## Numbers that exist

- 30 s, 93 passed, 94 skipped; 3m53, 128 passed (node_modules); 4m53, 156 passed (plus slow switch); 6m31, 180 passed, 5 skipped (plus JDK). 87 tests newly run. Source `docs/v2.0-roadmap.md:1872`. n = 1 file, 1 machine, 1 run per configuration; no variance reported. The totals disagree: 93+94=187 at baseline, 180+5=185 at the flip; the source does not explain the two missing tests.
- 398 tests across 81 modules not executed in CI before item 430. Source `docs/v2.0-roadmap.md:1864`. Count as stated in the roadmap; not recomputed.
- 17 `skipif` decorators on `REVL_CROSS_TIER_SLOW`, in 2 files. Source `docs/v2.0-roadmap.md:1866`.
- 1 failing probe out of the full five-tier matrix once everything ran. Source `docs/v2.0-roadmap.md:1874`.
- 2 Java correctness defects found under already-written assertions (item 433, R1 and R2). Source `docs/v2.0-roadmap.md:1864`, `docs/v2.0-roadmap.md:1729`.
- Of the documented instances, the unset-variable cases (430, 433) and the typecheck-only case (453) were found by tripping over a defect; the filesystem probe was found while measuring; the wrong-job case was found by audit (446).
- Not measured: how many silently skipped tests exist in comparable repositories, the false-positive rate of the guard, time-to-detection before versus after the guard. None yet.

## Paper outline

1. Introduction. The incident, why skip equals pass, summary of the three occurrences and the measured yield.
2. Setting. A compiler with six backends, per-tier toolchains, cross-tier "one source, compare values" tests.
3. Four gate shapes, each with its instance and how it was found.
4. The audit. Separating real gates from overrides ("one dead switch plus three overrides").
5. The mechanisms: the require-tiers switch with the `Absent` marker; the static guard; the guard's self-check and the non-vacuity check on the demo step.
6. Measurement. Cost and yield of executing the skipped tests; the one failure; the wrong "no JDK" premise.
7. What conformance validators cannot answer, and the demo case.
8. Limits and open instances. Related work.

## Threats to validity and limits

- The measurements are one laptop, one file, one run per configuration; the source labels them as measured on an arm64 laptop. They are not CI timings.
- All instances are from one repository and were reported by the people who fixed them. No external prevalence data.
- The guard does not catch a toolchain-probe skip for a tier outside the `revl.test` runners, `pytest.importorskip` elsewhere, or anything it cannot see in the workflows; its docstring says so (`tests/test_env_gated_skips_run_somewhere.py:1-60`).
- The rule "conformance CI fails if a tier is unavailable" holds only for tiers named in `REVL_REQUIRE_TIERS` for that step (`py,ts,go,rust`). Java and wasm are not required yet, so a missing JDK or wasm substrate still reads green there.
- One right-variable-wrong-job instance (`REVL_CORDIS4J_CLASSES`) and the wasm demo are explicitly left open on main.
- The Java defects were first verified by emitted-code inspection and later by execution on a real JVM; the earlier "no JDK on this machine" statement was a wrong premise.
- The 398 / 81 figure comes from roadmap prose and has not been independently recomputed.
- The two-test gap between the baseline and final totals is unexplained, so the figure of 87 more passes is quoted as a pass-count difference only.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 46 checked, 9 corrected.
