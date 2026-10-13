---
id: P23
title: "From Discipline to Type System: What revl Adds to the Cordis Plugin Framework"
theme: lifecycle-swap
kind: position
maturity: partial
status: The guarantee decode table, realms, the balancing pattern, the conformance matrix and the fork audit are on main; local realms are confirmed on four of five language tiers (the fifth depends on a change outside this tree), instance-parametric components exist on one tier, and no comparison against Cordis itself has been run.
fused_with: P01
---

## Pitch

Cordis gives plugin systems revertible effects as a discipline the programmer must respect; revl moves the same hypotheses into a checker, and the interesting question is which guarantees were inherited, which were added, and what that cost on six runtimes.

## Abstract

Cordis is a plugin framework and a paper (a programming paradigm for spatiotemporal composability) that proves strong theorems about revertible effects, but each theorem rests on hypotheses that a library can only ask programmers to respect: every mutation has an inverse, teardown is the reverse of acquisition, a service has one provider, dependencies are acyclic. revl is a language whose checker enforces those hypotheses at compile time, in the way Rust made C++ RAII a type system. This essay separates what revl inherits from what it adds. Using the guarantee decode table in the repository, we classify the gate guarantees G1 to G8 as Cordis-derived (G5 is anchored to a lifecycle-hardening note in `DESIGN.md` rather than to a paper definition), G9 (untrusted data cannot create authority without a declared declassification) as revl-original, and the A and T rule families as a mix of paradigm-derived, standard type theory and revl-original rules, with several origins the documentation itself marks "unconfirmed". We then describe four additions that are not in the paradigm as a discipline: isolation realms and coeffect interception made static (G2 becomes per-key-per-realm), a load-balancing structure (spawn, realms and a router) that resolves a direct tension with provision disjointness, instance-parametric components, and a small backend contract (install effect with inverse, provide and read keys, reactive refresh) that lowers one IR to six Cordis runtimes. On a generated conformance matrix of 61 emitted constructs (one more is refused by the frontend), py, ts and rust have zero refusals, java and go one each, wasm ten, all listed as deliberate tier limits. We report where the runtimes disagreed with the language design (realm identity is the disagreement the repository documents; no teardown-order disagreement was found) and which fork patches are general enough to upstream.

## Problem and claim

A discipline is cheap to adopt and cheap to break. Cordis states its guarantees as theorems conditional on hypotheses (declared access, provision disjointness, acyclicity, inverse for every effect). A plugin author who forgets one gets residue after unload, with no diagnostic. The existing answers in neighbouring systems are runtime supervision (Erlang/OTP), container-style dependency injection (Spring, Guice, Angular DI), module systems with dynamic loading (OSGi), and declarative dependency graphs for infrastructure (Pulumi, Terraform). To our reading, none of them states unload-leaves-no-residue as a static property of the program (the prior-art reading is not yet done; see below).

The claim is narrow and checkable: revl's front end enforces, before anything runs, the hypotheses the Cordis paper's theorems need, and where the paradigm was silent (multi-tenancy, balancing, per-request instances, many runtimes) revl adds constructs whose guarantees are stated against the same checker. The paper does not claim that revl is better than Cordis as a library, nor that every guarantee is mechanized; the decode table says which are enforced in the compiler and which only by construction.

A second claim is about method: a language implemented over six pre-existing runtimes is a stress test of the paradigm, because each runtime had to be hardened and each disagreement (how realm identity works) is a place where the paper's semantics under-determined the library.

## Contributions

1. A delta table classifying every refusal code (G1 to G9, A family, T1 to T4, taint qualifiers) as Cordis-derived, revl-original or standard type theory, with the cases the repository marks "origin: unconfirmed" kept as such.
2. A description of realms (Sigma-iso) and interception (Sigma-inter) as static constructs: G2 per (key, realm), realm-aware G3, manifest fields, and the reason dynamic realm labels are rejected.
3. An account of the load-balancing tension with G2 and its resolution (N workers in N realms behind one router providing the key in the parent realm).
4. The backend contract and a per-tier audit of fork patches and upstream status, plus a conformance matrix as the acceptance test for "same language, six runtimes".
5. A list of places where runtime behaviour contradicted the language design (local realm support per tier), as data for anyone building a similar front end for a plugin framework.

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Cordis (Koishi ecosystem) and its paper | Plugin paradigm with revertible effects, services, contexts; theorems under hypotheses (exact title and venue of the paper: citation to be checked) | Checks the hypotheses statically; adds the constructs above |
| Erlang/OTP supervisors | Restart policy and process isolation at runtime | No restart semantics; unload residue is refused at compile time. Hot upgrade is covered in P24 |
| Spring, Guice, Angular DI | Dependency resolution and scopes at startup or on demand | Resolution is a linker phase over a whole-composition manifest; G2 and G3 are static even though loading is dynamic |
| OSGi | Dynamic bundle lifecycle, service registry with versions | Structural interface compatibility checked at admission against the running manifest, not version strings (see P34) |
| Rust ownership and RAII | Lexical resource scope enforced by the borrow checker | The checker governs dynamic component scope; the README states this analogy directly |
| Pulumi, Terraform | Declarative dependency graph for resources, destroy order from the graph | Effects are arbitrary program steps with declared inverses; teardown order is derived LIFO and checked |
| Bevy ECS plugins | Plugin registration for an engine at build time | No residue guarantee; not a lifecycle system |

## Evidence on main

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| The pitch "revertible effects as a discipline, revl makes them a type system" | `README.md:36-41`; `docs/guide-humans.md:8-12` | shipped (positioning text) | Rhetorical claim; the checks it refers to are below |
| Origin classification of G1 to G9, A, T | `docs/guarantees.md:1-76` | shipped | G1 to G8 Cordis-derived, G1 to G4 and G6 to G8 with paper anchors, G5 anchored to the `DESIGN.md` lifecycle hardening (PR #39), not a paper definition; G9 revl-original; A2, A6, A9 origins marked unconfirmed |
| Realms and interception implemented | `docs/design-v2-realms.md:1-12`, `docs/design-v2-realms.md:58-101`; `examples/tenants.rvl`; `tests/test_realms.py`, `tests/test_realm_conformance.py` | shipped on py and ts, wasm substrate | Doc says "runtime-verified on cordis-py and cordis v4"; rust, java, go not stated there |
| Realm lowering quirk on rust | `docs/design-v2-realms.md:113-122` | partial (open per the doc) | The doc says the #1543 label-registry fix covers py and TS; the same paragraph says rust still collides: "two keys in one realm collide there until the rust emitter is changed". Re-check on current main before relying on it |
| Dynamic realm labels rejected on soundness grounds | `docs/design-v2-realms.md:64-72` (rejection); `docs/design-v2-realms.md:40-52` (placeholder form) | shipped | The placeholder form added in issue #1728 (`tests/test_realm_placeholder_1728.py`) is the admitted alternative |
| Load balancing tension with G2 and resolution | `docs/distribution-model.md:1-46`; `tests/test_router_runtime.py`, `tests/test_multi_realm_require.py` | shipped (pattern and stdlib Router) | Routing on py/ts/rust (item 167); wasm and go via item 173; java "has the emitter and awaits an upstream cordis4j release" |
| Backend contract and six tiers | `docs/v2.0-roadmap.md:268-300`; `README.md:170-172` | shipped | Roadmap says the five language tiers (py, ts, rust, java, go) are at 0 matrix gaps; wasm has gaps |
| Conformance matrix with drift gate | `docs/conformance.md:96-110`, `docs/conformance.md:370-382`; `tests/test_conformance_matrix.py` | shipped | 61 emitted constructs (1 more refused by the frontend); 19 executed, 42 compile-only; wasm 10 deliberate limits |
| Fork status audit | `docs/design/backend-runtime-fork-status-2026-09.md` (matrix and per-tier sections) | shipped (reference doc) | Dated 2026-09-08; rust pinned ^0.3; two java PR specs not built (no JRE) |
| Local realms on other tiers | `docs/notes/runtime-parity-local-realms.md:59-67`, `docs/notes/runtime-parity-local-realms.md:166-185`; `docs/design-v2-instances.md:179-200` | partial (the note predates the wasm change) | The note: four of five tiers can do it, wasm cannot (runtime change needed). The later section (`docs/design-v2-instances.md:179`) says all five are verified and that the wasm gap was closed by a realm-prefix change in the cordis-wasm repository, which is not in this tree. Unverified here; "verified on five tiers" is not shown false, only unverified |
| Instance-parametric components, phase 1 | `docs/design-v2-instances.md:1-9`; `tests/test_instances_exec.py` (executed on cordis-py); `SpawnHandle` at `backends/python/runtime.py:1701` | partial | Implemented on cordis-py only; phases 2 to 5 (other four tiers) not done per the doc header |
| Capability attenuation on spawn | `docs/capability-attenuation.md` (no status line); code in `src/revl/parser.py`, `src/revl/lower.py`, `src/revl/cap_order.py` | unverified | Doc has no status line; code is present, tests not checked for this draft |

## Numbers that exist

- 61 constructs in the conformance corpus (1 more refused by the frontend), 6 emitters plus the self-host tier: py 61 ok, ts 61, rust 61, java 60 (1 deliberate), wasm 51 (10 deliberate), go 60 (1 deliberate), self-host 59 (2 deliberate); 0 real gaps (`docs/conformance.md:104-110`). 19 executed, 42 compile-only (`docs/conformance.md:112`).
- Fork audit, 2026-09-08: python 3 patches carried, all submitted in one open upstream PR (geohotstan/cordis-py#1); go 1 additive patch (2 files); java 2 PR specs; rust none; ts and wasm out of the matrix scope (`docs/design/backend-runtime-fork-status-2026-09.md`).
- Origin counts in the decode table can be tallied from `docs/guarantees.md`; no one has done it yet.

## Paper outline

1. Introduction: the C++ RAII to Rust ownership analogy, stated as a hypothesis with its limits (revl governs dynamic component scope, not lexical scope).
2. Cordis in one page: contexts, services, fibers, revertible effects, the theorems and their hypotheses.
3. The decode table: what was inherited (G1 to G8), what was added (G9, taint, A3, A5, T3, T4), what is standard.
4. Four additions: realms and interception, balancing as spawn plus realms plus router, instance-parametric components, attenuation on spawn.
5. Six runtimes: the backend contract, the conformance matrix, fork and upstream status, the disagreements found.
6. What the type system cannot say: residue outside effects, host calls, the claims that are checked only by tests.
7. Related work and conclusion.

## Threats to validity and limits

- This is a position paper; the thesis that "type system beats discipline" is argued by example, not measured. Without a seeded-defect comparison against Cordis it stays an opinion.
- Several origins in the decode table are "unconfirmed" in the docs themselves; the paper must not claim a paper anchor for them.
- Instance-parametric components are implemented on one tier. The local-realm parity note is reconnaissance and states that no compiler or backend behaviour was changed; the later section claims all five tiers, including a wasm change made in another repository that this tree cannot check.
- Load balancing is a pattern plus a stdlib router, not a scheduler; java routing depends on upstream work. `docs/distribution-model.md` describes itself as a framing and design document.
- Conformance is mostly compile-only (42 of 61); 19 are executed. "Same language on six runtimes" is therefore partly a claim about generated code that compiles.
- revl has no restart policy, so the comparison with Erlang/OTP supervisors must stay at the level of lifecycle, not fault tolerance.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 13 checked, 6 corrected.
