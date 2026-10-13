---
id: P29
title: Hot-Swapping a Composition Whose Components Run on Different Runtimes
theme: distribution
kind: full
maturity: partial
status: Per-component tier placement and a py-to-py live swap with receiver-side re-admission are shipped and tested on main; no cross-tier swap test, no non-py seam admission, and no latency or gap measurements.
fused_with: P30
---

## Pitch

A running composition can move one component into its own process on another runtime with the cutover verified on the py tier today, and every py seam re-admits the successor against the receiver's own manifest instead of trusting the sender. No service gap has been measured.

## Abstract

Dynamic software updating work moves code between versions of one runtime. Real systems are polyglot: a hot worker wants a native tier while the control plane stays on a scripting tier. We describe a composition model in which each component is placed on one of five runtime tiers (py, node, rust, java, go; wasm placement is refused by design), cross-tier calls ride a Unix-socket or mutual-TLS seam with a canonical wire encoding, and the compile-time guarantees on provision disjointness, acyclicity and inverse-or-emit (G2 to G4; teardown order is G7) are checked once over the whole manifest before the split. A live swap boots a successor in its own process, re-admits it against the running manifest so every consumer call site is re-checked, re-points each consumer proxy under a generation counter so a planned cutover is not read as a provider death, drains in-flight calls against the old provider, and tears the old process down in LIFO order with a printed residue proof. Each py seam re-admits against the receiver's own recomputed state and treats the wire only as a selector, never as a manifest. A swap that fails admission leaves the running composition untouched. The swap is tested py to py; the same operation to other tiers is documented and smoke-covered, not swap-tested. We report the mechanism, the refusals it makes by design (shared processes, network providers, sandboxed components, managed model roles), an adversarial audit that found three unjudged inputs at the seam, and the executed test suites. We do not yet report latency, gap-time or cross-tier state transfer measurements: none exist today.

## Problem and claim

Existing live-update systems assume one runtime and one trust domain. Rolling updates in orchestrators replace whole processes and lose in-memory state; sidecars and RPC bridges move calls across languages but do not re-check the interface of the new provider against every running consumer, and they trust whoever produced the wire message.

Claim: for a statically checked reactive composition, a swap across a process seam can be made a verified operation. The successor is admitted against the running manifest before any consumer is touched, a failed swap is a no-op, and a py seam never accepts a repoint or wiring on the sender's word. On main this is shown py to py. The same operation to another tier is designed on the same seam and is not yet swap-tested. The claim is about the cutover protocol and the admission discipline, not about moving mutable state between tiers (see limits).

## Contributions

1. Per-component tier placement: a `[tiers]` table plus `default_tier` expands to one synthesized process per tier; emission narrows to a placement slice and a plan-time capability gate names the component and tier on refusal; never auto-selected (`src/revl/placement.py:457-510`, `src/revl/placement.py:2823`, `src/revl/placement.py:3066`; `tests/test_tier_placement.py` 18 tests, `tests/test_tier_placement_hardening.py` 13 tests).
2. A live swap protocol: boot, admit against the running manifest, re-point under a generation counter, drain, LIFO teardown with residue proof (`docs/swap.md:30-52`, `docs/swap.md:112-135`). Tested py to py; other tiers use the same seam but have no swap test.
3. A spec-carrying rule: a spec key that carries a security property is carried across the swap or the swap refuses (correlation guard, host-module pins, E-Stop latch), guarded by a test that diffs the two spec literals (`docs/swap.md:60-110`, `tests/test_swap_ref_pins.py`).
4. An admission mesh whose py seams re-admit against receiver-held state, with the audit that the first landed version judged only the selector (`docs/design/337-polyglot-admission-mesh.md:121-160`, tests in `tests/test_swap.py:852-1361`). Non-py seams are designed, not wired.
5. A process-level cycle check: a quotient of an acyclic component DAG by a placement partition can contain a cycle, and the conductor refuses it (`src/revl/placement.py:3265-3340`).

## Related work

| prior system or line of work | what it does | what revl does differently |
|---|---|---|
| Erlang/OTP hot code loading | swaps module versions inside one VM | successor runs in a new process; admission re-checks every consumer first |
| Ginseng, Kitsune, POLUS (DSU for C) (citation to be checked) | patches a running process with state transformers | no in-process patching; process-level cutover, state transfer not claimed |
| OSGi bundle updates | replaces bundles in one JVM | separate processes, seam re-admission |
| Kubernetes rolling update, Istio sidecars | replace pods, route traffic | no admission against consumer call sites, no ordered teardown proof |
| gRPC / Thrift cross-language bridges | typed RPC between languages | the bridge is also the update path, with a generation counter and receiver re-admission |
| Wasm component model | typed cross-language composition in one host | five placeable tiers, process seams, live swap; wasm placement is itself refused (below) |

## Evidence on main

| claim | path:line or test | status | note |
|---|---|---|---|
| `[tiers]` placement expands to per-tier processes | `src/revl/placement.py:457-510` (expand_tiers at 480) | shipped | design stages 1 to 3 (surface, slice, capability gate) have code at `src/revl/placement.py:2823`, `:3066`, `:5053`; stage 4 has a boundary check at `src/revl/placement.py:3213`; stage 5 (distributability report, demo and determinism exit) was not verified |
| swap boots, admits, re-points, drains, proves no residue | `docs/swap.md:30-52`; `tests/test_swap.py:494-517` | shipped, py to py only | the test runs `swap MemCache --to py`. The docs call other tiers "the same operation over the same seam" (`docs/swap.md:225-229`); no gated test swaps to node, rust, go or java. The doc header says "implemented (2026-08-23)" |
| the REPL verb is the documented driver | `docs/swap.md:1-18` | shipped | not a `revl swap` subcommand. An MCP `revl_swap` verb also exists (`src/revl/mcp/`, `docs/component-leases.md:71`); it was not traced to this protocol |
| generation counter keeps planned cutover from reading as death | `docs/swap.md:112-135`; `tests/test_swap.py:164-226` | shipped | |
| failed swap leaves composition serving | `tests/test_swap_transactional_1446.py` (9 tests) | shipped | one process, py tier |
| refusals: shared process, network provider, sandboxed, managed model role | `docs/swap.md:93-108`, `docs/swap.md:139-175`; `tests/test_swap.py:581` | shipped | |
| seam 1 (repoint) and seam 2 (boot wiring) re-admit on py | `docs/design/337-polyglot-admission-mesh.md:411-430`; wiring at `src/revl/_process_runner.py:703-759` and `src/revl/placement.py:1970` (`seam_readmission`); tests `tests/test_swap.py:852-1361` | shipped on py | the design's "fully expressible on a homogeneous py fleet today" is at `docs/design/337-polyglot-admission-mesh.md:446` |
| non-py receivers re-admit | `docs/design/337-polyglot-admission-mesh.md:432-450` | designed | the rust gate crate exists: `crates/revl-gate` exports `admit` and `admit_into` (generated, drift-gated, `crates/revl-gate/tests/admit.rs`). No non-py seam calls it on main, so seam wiring is designed. The design doc's "neither exists" (`docs/design/337-polyglot-admission-mesh.md:430-431`) is stale |
| remote handoff seam (seam 3) | `docs/design/337-polyglot-admission-mesh.md:284-312` | designed | needs a trust anchor, deferred |
| two-phase admission with `(generation, surfaceEpoch)` and forward recovery | `docs/design/460-two-phase-admission-forward-recovery.md:386-400`; `tests/test_admit_two_phase.py` (42 test functions) | partial, py | session admission of per-turn source, not the cross-tier swap path. The header says "Design only: nothing implemented" (`docs/design/460-two-phase-admission-forward-recovery.md:10`); the status paragraph lands classification, CAS, forward finalize and the journal-served seam; the live runtime re-plug "remains the runtime half" |
| spawn, instance accessor, hot swap (migrate-state) on six tiers | `docs/backends-roadmap.md:23`, `docs/backends-roadmap.md:46` | shipped per doc | the table at `docs/backends-roadmap.md:8-14` still says go has "no spawn yet" (line 14); the doc contradicts itself. migrate-state is within one runtime (line 46) |
| py-to-py swap runs as a repeatable exit test | `docs/swap.md:200-215`; `tests/test_e3_demo.py` | shipped | docs state the demo is py to py |
| other tiers covered by a placement smoke, not a swap test | `ci/placement_smoke.sh:1-40` | partial | smoke boots `--once` across py/node/rust/go/java seams; a search of `tests/` and `ci/` finds no swap to node, rust, go or java |
| process-quotient cycle check | `src/revl/placement.py:3265-3340` (process_graph, `_find_process_cycle`, process_cycle_refusal) | shipped | |
| wasm placement | `docs/design/363-per-component-tier-placement.md:526-566`; `src/revl/placement.py:533-547` | refused by design | the conductor refuses `wasm` with a redirect; "no wasm placement until the substrate grows a real placement runner" |

## Numbers that exist

- Test counts by function name: 18 (`tests/test_tier_placement.py`), 13 (`tests/test_tier_placement_hardening.py`), 32 (`tests/test_swap.py`, `def test` count, parametrization not counted), 9 (`tests/test_swap_transactional_1446.py`), 42 (`tests/test_admit_two_phase.py`). These are counts of test functions, not pass rates; no test was run for this draft.
- No latency, cutover-gap, throughput or memory measurements anywhere in the cited docs.
- Five placeable tiers exist plus wasm, which is refused for placement. The docs say every tier is at 0 conformance gaps (`docs/backends-roadmap.md:8-14`); the generated sweep in `docs/conformance.md` was not opened.

## Paper outline

1. Introduction: polyglot compositions and why live update stops at the language boundary.
2. Model: components, providers, tiers, the G2 to G4 checks done once.
3. Placement: the `[tiers]` surface, slicing, capability gate, process-quotient cycles.
4. The swap protocol: boot, admit, re-point with generations, drain, residue proof.
5. Seam admission: selector not manifest, the three unjudged inputs found by audit.
6. What a swap carries or refuses.
7. Evaluation (to be built): gap, latency, failure injection.
8. Related work and limits.

## Threats to validity and limits

- The mesh doc says: "The design does not pretend the polyglot mesh is buildable end-to-end now" (`docs/design/337-polyglot-admission-mesh.md:448-450`). Admission at a seam runs on py today.
- The swapped component must be alone in its process and not a network provider (`docs/swap.md:139-175`). Mid-stream handoff of in-flight calls is deferred; calls drain against the old provider.
- Shadow verification before cutover is deferred (`docs/swap.md:230-238`).
- Probes are not re-run on the successor by design.
- The mesh re-admits, it does not confine: a tier that owns its host can corrupt its own gate (`docs/design/337-polyglot-admission-mesh.md:592-594`).
- State transfer across tiers is not documented as built, and cross-tier swap is not tested. Any reading of "state migration" or "hot swap on six tiers" beyond the within-runtime mechanism overstates what the swap docs show.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 60 checked, 11 corrected.
