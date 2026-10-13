---
id: P51
title: Auditing Generated Code Against Hand-Written Code on Load-Independent Metrics: Fuel, Allocated Bytes, Allocs/op, Microtask Turns and Element Copies
theme: compiler
kind: empirical
maturity: shipped-evidence
status: Six per-backend audit harnesses and their before/after counts are on main with tests pinning most fixes; there is no uniform cross-backend corpus, no timing validation and one correctness defect found is still open.
fused_with:
---

## Pitch
Counting things that do not depend on machine load (wasmtime fuel, bytes allocated per op, allocs/op, microtask turns, elements copied) let one team audit six emitters against hand-written code in one audit cycle on a machine running a dozen other jobs, and the counts found a quadratic accumulation in four of six backends (Python, TypeScript, Go, Rust), a double-evaluation correctness bug and an 85% dead prelude that timing-based audits would have missed or misattributed.

## Abstract
Compiler back ends are normally audited with wall-clock benchmarks, which are unreliable on shared machines and blind to the cause of a gap. We report a per-backend audit of the code a single compiler (revl) emits for six targets (wasm, Java, TypeScript, Python, Go, Rust), compared against code a competent developer would write by hand for the same semantics. Every default metric is a count whose value does not depend on machine load (the JVM figure is allocated bytes, which do depend on JIT state): wasmtime fuel for wasm, thread-allocated bytes per operation on a JVM, allocs/op and B/op from Go's testing.B, microtask turns and Promise allocations for TypeScript, bytecode, frame and element-copy counts for Python, and counting-allocator allocation counts for Rust. The audits found, among others: persistent push/set/remove lowered as full copies in Python, TypeScript, Go and Rust (for example 500500 element copies against 1000 at n=1000 in Python, 4274103 B against 8192 B at n=1000 in Go, 729599 allocations against 2425 for hand-written Rust self-append); a string lift costing 19 fuel per byte on wasm that became 0 after a zero-copy change; 82 to 86 percent of the emitted wasm core module removed by pruning unreachable functions on the audit's three probes; and a semantic defect, `??` evaluating its left operand twice in Python, found by counting effects. We also report what the counts refuted: a static count of Java allocation sites predicted the wrong winner (221224 B against 286760 B), and a Python opcode counter reports the largest defect at 0.96x because a list copy is one bytecode. We close with the places where the method did not hold: one Rust self-host measurement used wall-clock, and one mirror defect in Go was found but not fixed.

## Problem and claim
Existing compiler-output audits either time a benchmark suite or inspect emitted text. Timing is unusable when other jobs share the machine (the audit host ran about a dozen concurrent jobs), and it says nothing about why a gap exists. Inspecting text finds shapes but cannot say whether a shape costs anything: the Java audit's static count of construction sites reversed when measured.

The claim is narrow and checkable. For each backend there is a metric that (a) is a deterministic count, (b) is blind to host load, and (c) separates the emitter's choice from the language's cost. Using it, an emitter can be compared against a hand-written yardstick that keeps the emitted structure and changes one choice at a time. The same discipline requires negative controls: shapes measured and found already at hand-written cost are written down so they are not re-audited.

We do not claim the counts replace timing in general. We claim they are sufficient to find and fix the defect classes below, and we document the cases where a count is the wrong instrument.

## Contributions
1. A per-backend catalogue of load-independent metrics and the harness that computes each (`bench/codegen/{wasm,java,typescript,python,go,rust}`), each refusing to report a number when the hand-written side stops agreeing with the emitted side (wasm `run.py` variant gate, Go `Test*` functions, TypeScript `STALE`, Rust agreement assertion).
2. A catalogue of emitter defects found by counting, with before/after ratios: quadratic accumulation (concat, push, set, remove, template fold), unneeded async colour, zero-copy lift, unconditional helper preludes, per-call code-point materialisation, boxing of Opt/Result.
3. A semantic bug found by counting effects: `lookup(k) ?? 0` invoked the extern twice on Python, and the mirror defect (right operand evaluated eagerly) exists on Go.
4. A profile-before-fix decomposition for Rust (clone-on-append about 85 percent of the gap, `charAt` about 2.7 percent, build profile ruled out) that redirected a fix that a plausible intuition had gotten wrong (the 28 percent lexer regression).
5. Negative results, including a case where a static count and an executed byte count disagree in sign, and a list of declined optimisations with the measured reason.
6. An account of where the load-independent method failed or was bypassed.

## Related work
| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| SPEC CPU, Renaissance, DaCapo suites | Wall-clock benchmark suites over fixed programs | No timing by default; compares emitted code with a hand-written twin of the same program, attributing a gap to one emitter choice |
| JMH with allocation profiling (gc.alloc.rate.norm) | Per-benchmark allocated bytes on the JVM | Same primitive (thread allocated bytes), used as an emitter audit and paired with a refuted static-count prediction |
| wasmtime fuel metering | Deterministic instruction budget for sandboxing | Used as an exact, load-free cost metric for generated wasm, found by bisecting the fuel limit |
| Go testing.B -benchmem, escape analysis (-gcflags=-m) | allocs/op and escape reports for hand code | Applied to generated Go, with size-scaled pairs (10x input) so a quadratic shows as roughly 100x bytes |
| Mytkowicz et al., "Producing wrong data without doing anything obviously wrong" (ASPLOS 2009) (citation to be checked) | Shows measurement bias from environment | Motivates dropping timing; revl goes further and makes the default report contain none |
| Csmith-style miscompile hunting (Yang et al., PLDI 2011) (citation to be checked) | Random programs to find compiler crashes and wrong code | Counting found a wrong-code class (double evaluation) as a side effect of a performance audit, without a generator |
| Perceus reuse analysis (Reinking et al., PLDI 2021) (citation to be checked); Futhark in-place updates (Henriksen et al., PLDI 2017) (citation to be checked) | Static uniqueness enabling destructive update | The audits are cited as evidence for the uniqueness marker; the audit is evidence for why, not a new analysis (the motivation claim is not re-verified here) |

## Evidence on main
| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Wasm audit measured in fuel, no timings | `docs/v2.0-roadmap.md:1707`; `bench/codegen/wasm/README.md:1-12` | shipped | Harness plus `results.json` committed |
| Wasm string lift 19 fuel/byte to 0, guarded by allocator floor | `docs/v2.0-roadmap.md:1708`; `backends/wasm/canonical.py:835` (`$__canon_lift_str`) | shipped | "echo 19.000 to 0.000 fuel/byte, flat 49 fuel" (roadmap line 1708) |
| 82 to 86 percent of emitted wasm core removed by pruning unreachable functions; reachability sweep declines on ref.func, call_indirect, table, elem | `backends/wasm/emit.py:7154` (`prune_unreachable_funcs`), `:7036` (`_UNSWEEPABLE`); `selfhost/emit_wasm.rvl:2348` (`prune_preamble`) | shipped | echo 3483 to 503 B in the audit (`docs/v2.0-roadmap.md:1709`); the "85 percent" figure is a three-probe figure |
| Arena reclaim gated by a soundness check | `backends/wasm/canonical.py:959` (`_arena_safe`); `backends/wasm/test_heap_reclaim_432e.py`; `backends/wasm/test_heap_growth_432e.py` | shipped | |
| Java audit by thread allocated bytes, 15-sample minimum, openjdk 26.0.2 | `docs/v2.0-roadmap.md:1718`, `:1731`; `bench/codegen/java/README.md:1-30` | shipped | Header was corrected after a macOS java stub misled the probe |
| Java `String.format` to concat chain, 508968 vs 40040 B/op | `docs/v2.0-roadmap.md:1731`; `backends/java/emit.py:4542` (`_format_java`) | shipped | |
| Java static count reversed by execution: 221224 vs 286760 B/op, ratio 0.77 | `docs/v2.0-roadmap.md:1723`, `:1731`; `bench/codegen/java/cases/list_push` | shipped | Closed as a negative result |
| Java router, config constants, stdlib gating | `backends/java/emit.py:8823`, `:3865`, `:1804` | shipped | |
| TS async colour per function, excess turns to 0 for sync arms | `backends/typescript/emit.py:3540` (`_renders_await`), `:3636`; `bench/codegen/typescript/results/counts.txt` (match-sync-arms) | shipped | `counts.txt` still lists 2.0 turns / 4.0 promises excess per op (24 turns, 48 promise allocations in total) for `match-in-async-fn`, where one arm genuinely suspends |
| TS string helper memo, n=1600: 5121600 to 1600 code points | `backends/typescript/emit.py:4687`; `backends/typescript/tests/str_scan_memo.test.ts`; `docs/v2.0-roadmap.md:1745` (before values); `counts.txt` string-scan table (after values only) | shipped | `counts.txt` alone does not show the before column |
| TS destructive push via frontend unique marker | `backends/typescript/emit.py:3798`; `backends/typescript/tests/unique_writes.test.ts` | shipped | |
| Python audit with opcode, frame, tracemalloc and element-copy counters; opcode counter blind to the main defect (0.96x) | `bench/codegen/python/README.md`; `docs/v2.0-roadmap.md:1754` | shipped | |
| Python `??` double evaluation fixed | `docs/v2.0-roadmap.md:1761`; `tests/test_71_codegen_perf_findings.py` | shipped | "200 extern invocations per 100 uses" |
| Go `??` mirror defect: right operand eager | `backends/go/emit.py:6895-6900` (`revlOptOr(left, right)`); `backends/go/emit.py:10669`; `docs/v2.0-roadmap.md:1768`; `backends/go/test_emit_go.py:636` | shipped as defect, not fixed | The test pins the eager spelling. Still open at 45bec431f as far as could be found |
| Go audit via testing.B allocs/op, B/op; all eight findings landed | `docs/roadmap-archive/13-the-embeddable-compiler-revl-as-a.md:220`; `bench/codegen/go/README.md` | shipped | 10x input gives 101x bytes for push, 84x for map set |
| Go shared ownership analysis; scan loops; string accumulators | `src/revl/ownership.py`; `backends/go/emit.py:7898` (`_v3_str_accumulators`), `:8082` (`_v3_scan_loops`) | shipped | Use of `src/revl/ownership.py` by the Go emitter was not checked |
| Rust audit under counting allocator, agreement asserted | `bench/codegen/rust/README.md`; `docs/v2.0-roadmap.md:1787`; `bench/codegen/rust/census.py` | shipped | The README has no census numbers; the roadmap's census percentage is not reproduced in the cited sources and is treated as unverified |
| Rust self-append through concat: 729599 allocations against 2425 hand-written | `docs/v2.0-roadmap.md:1791`; `backends/rust/emit.py:8498`, `:8629` | shipped | Fixed 2026-09-05 (`7831b8c5`); the fixed count is not stated in the cited sources. The fix is in `_v3_self_append_inplace` (`emit.py:5049`, per the roadmap), not at `:8498` or `:8629` |
| Rust accepted residual with measured reason | `tests/test_116_rust_perf_accepted.py` | shipped | |
| Rust lexer decomposition and the fix sequence 17x to 1.37x slower than CPython | `docs/bench-selfhost.md:244`, `:310-347`, `:433-455`; `docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:567-571` | shipped | See the limits: this is wall-clock |

## Numbers that exist
- Wasm: echo of a 4 KiB string 77900 to 4174 fuel in one copy-removal step (73726 saved per call), then flat 49 fuel at 16 B, 256 B and 4 KiB after the zero-copy lift (`docs/v2.0-roadmap.md:1708`); `List[Int]` crossing 46 to 8 fuel per element (roadmap:1710); 9-part template 20 to 4 fuel per byte (roadmap:1711); emitted echo core 3483 to 436 B with all fixes (roadmap:1709). Single host (wasmtime 47.0.3, macOS arm64), fuel exact so no variance.
- Java: `String.format` 508968 vs 40040 B/op; router 5.33x to 2.00x; class-file bytes measured at 42 to 66 percent of the compiled unit on the three files the audit named (roadmap:1731). Minimum over 15 samples, openjdk 26.0.2 (roadmap:1718). Router 5.33x to 2.00x (roadmap:1721).
- TypeScript: string scan n=1600, 5121600 to 1600 code points (`bench/codegen/typescript/results/counts.txt`); `xs.push(e)` spread copies n(n-1)/2 elements before the unique marker, 0 after.
- Python: element copies at n=1000, 500500 vs 1000 (quadratic, x4.0 per doubling against x2.0); after the shared marker five of six probes match hand-written (`docs/v2.0-roadmap.md:1769`). `list_sort` was cubic (x7.9 per doubling).
- Go: Collect 100 allocs / 42225 B at N=100, 1001 allocs / 4274103 B at N=1000 against 1 alloc / 896 B and 1 alloc / 8192 B; Tally 3990 allocs / 19168881 B at 1000 keys; Opt-in-list 209 to 9 allocations (`docs/roadmap-archive/13-the-embeddable-compiler-revl-as-a.md:220-275`).
- Rust: concat self-append 729599 allocations / 97.2 MB vs 2425 / 212 KB hand-written (roadmap:1791).
- Rust lexer, self-host corpus (8 files, 27832 characters): 351.43 ms to 28.12 ms (12.5x), allocations 12085346 to 289177 (`docs/bench-selfhost.md:433-455`). These are wall-clock medians on one host assumed idle, not counts.
- No cross-backend table of the same program on all six backends exists; the six harnesses use different programs.

## Paper outline
1. Introduction: the shared-machine problem, the claim, the defect classes.
2. Method: choosing a count per backend, the yardstick rule (change one choice), agreement gates, STALE reporting.
3. Per-backend metrics and harnesses (table).
4. Findings: accumulation, async colour, boundary copies, dead preludes, boxing, string materialisation.
5. A correctness bug found by counting effects (Python and Go `??`).
6. Negative results and measurements that reversed a prediction (Java sites vs bytes; Python opcode counter; Rust profile before fix).
7. Where the method did not hold (wall-clock use in the Rust self-host table, JIT effects on Java counts, unfixed Go defect).
8. Related work and discussion.

## Threats to validity and limits
- "Load independent" is a property of the count, not a guarantee of stability. The JVM numbers are allocated bytes, but the roadmap itself notes that a boxed `==` is scalar-replaced by C2 escape analysis (40 B/op both sides) and that load distorts JIT compilation (`docs/v2.0-roadmap.md:1718`, `:1722`). A byte count under JIT depends on warmup and on the JDK version.
- The Rust native lexer slowdown was once described as "measured, slow, not explained". That text is stale: `docs/bench-selfhost.md:310` explains it (clone-on-append about 85 percent) and `:433-455` shows the fix (17x slower to 1.37x slower than CPython). The docs still carry the old "17x" sentences at `:255` and `:653`, which a reader may mistake for current state.
- The Rust lexer timings are wall-clock medians; the project's own Rust audit says a duration on a loaded machine is not evidence (`bench/codegen/rust/README.md`). The paper must separate those rows from the count rows.
- Hand-written yardsticks are written by the same team that wrote the emitter. The README for Java states it "keeps the emitted structure and changes only the one emitter choice", which is a design for attribution, not an independence guarantee.
- Findings are specific to this compiler's persistent-collection semantics. Quadratic accumulation follows from lowering a persistent `push` as a copy; other languages lower it differently by construction.
- The audits were run on 2026-09-02 and several emitters changed after. The Go `??` defect and the TS `match-in-async-fn` excess are still present or partially present.
- No claim is made about generated-code speed relative to other compilers; only emitted-versus-hand-written within revl.
- The catalogue is not uniform across backends: the six harnesses measure different programs with different metrics.

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 50 checked, 11 corrected.
