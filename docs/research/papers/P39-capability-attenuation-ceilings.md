---
id: P39
title: "Capability Attenuation Across Spawn: Parameterized, Resource-Bounded Capabilities With Proved Ceilings"
theme: security
kind: full
maturity: partial
status: In-process spawn attenuation and the Lean ceiling theorems are shipped with tests and a differential oracle; the peer-placement edge and the lease and sandbox slices are design-only and no evaluation exists.
fused_with:
---

## Pitch
A top-level (activation-body) spawn can narrow a child's authority but never widen it, and in the shipped checker that holds for resource parameters and budgets too, because a parameterized capability is a point in a partial order under its token and the same subset check covers path prefixes, hosts and integer ceilings.

## Abstract
Systems that create many instances of a component usually let a spawner hand down whatever it likes, so a component with no authority of its own can act as a capability amplifier. We describe the attenuation rule in revl, a language whose compiler checks capability use at admission. For activation-body spawns, a spawned child's reach must be covered by the capabilities its spawner holds, and the check is closed over the transitive spawn graph; a spawn nested in a `provide` method is bounded by that method's `emission[...]` clause instead. We make capabilities points in a partial order: a pair of a token and a valuation, where valuations carry a path prefix, a discrete value or an integer ceiling (`fs.write(path=...)`, `network.call(host=...)`, `model.complete(calls=3)`). Subsumption is path-prefix containment, equality, or a smaller ceiling, and a child that drops a parent's ceiling is read as unbounded and refused. A Lean 4 development proves the order is a partial order, that any admitted spawn lineage stays covered by the root's declared authority, that ceilings only shrink down a lineage, that a runtime counter derived from a `calls` ceiling cannot be overdrawn beyond the root's ceiling (bytes and time are declared, not metered), and that the unnameable host boundary is never manufactured. A derivation section recomputes held and reach sets from component shapes, and a differential harness compares the model's verdicts against the shipped checker on a corpus (8 rows for this item). We report what is shipped, what the formal model leaves out, and what is still design-only (peer placement as a spawn edge, lease runtime, sandbox mapping).

## Problem and claim
Object-capability systems give least authority by construction, but they say little about what a spawner may pass down once capabilities carry parameters ("write under /tmp/job-42", "at most 3 model calls"). Token-identity checks are all or nothing: the design note measures an unstructured string token compared by identity (`docs/design/294-parameterized-capabilities.md`, "The problem (measured)"). Without a rule, a spawn "inherits everything": a component with no authority of its own can spawn a child that reaches the network (`docs/capability-attenuation.md:6-12`).

The claim: one partial order, one `covers` implementation, used by every fold that compares capabilities, gives a monotone-shrinking lineage for authority and for budgets, and the guarantee can be stated and proved over the same two relations the checker actually runs (a resource fold and a separate ceiling check), not over an idealised one. The paper also argues two design points that fail in obvious implementations: the fold must be done in the boundary's namespace, not the consumer's wiring-key namespace (renaming a key launders a boundary), and a dropped ceiling must read as +infinity.

## Contributions
1. A spawn rule: the child's reach must be covered by the spawner's held capabilities, enforced at admission of every activation-body spawn, closed over the transitive spawn graph, with the offending chain named in the refusal (`docs/capability-attenuation.md`, "The refusal"; `tests/test_spawn_attenuation.py::test_widening_is_transitive_over_the_spawn_graph`).
2. A capability as a point `(T, P)` in a partial order under its token, with a closed registry of three value orders (path, discrete, integer ceiling) and a single `covers` definition (`src/revl/cap_order.py`, module docstring); a bare token reduces to token identity, so parameter-free programs are unchanged.
3. A Lean development of the ceiling guarantees over a lineage: `cap_order_partial`, `attenuation_monotone`, `lineage_ceiling_le`, `budget_never_exceeds_root_ceiling`, `no_star_amplification`, plus `derived_*` versions with held and reach computed from component shapes (`formal/RevL/Theorems/CapCeilings.lean`).
4. A two-relation model of the checker, with a theorem that the ceiling check is not subsumed by the resource fold (`ceiling_check_not_subsumed`, `derived_ceiling_check_not_subsumed`), and an exhibited loss when the fold is run in the wiring-key namespace (`same_key_different_boundary_refused`).
5. `calls`, `size` and `time` are registered ceiling parameters of the same algebra (`src/revl/cap_order.py`, `_REGISTRY`), and `budget.requests` / `budget.bytes` are sugar for `calls` / `size`. Only `calls` is metered by a shipped counter; `size` and `time` are declared and ordered but not metered. `attempts` (retry budget) and `seam_deadline` are proposed for the peer case in design 461 and are not registered. The peer-placement edge is design-only and is stated as such below.

## Related work
| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| E, Caja, Joe-E object capabilities (citation to be checked) | Least authority by reference passing; attenuation by wrapping facets | Attenuation is a static, whole-composition admission check on declared reach, with a refusal that names the chain, not a runtime wrapper |
| Macaroons (Birgisson et al. 2014) (citation to be checked) | Caveats attenuate a bearer token by appending restrictions | Parameters are typed points in a closed order with proved monotonicity along a spawn lineage; no bearer token |
| Biscuit tokens (citation to be checked) | Datalog-checked attenuation blocks | Static check at compile and admission, tied to a component's declared emission surface |
| seL4 capability derivation | Derived capabilities carry reduced rights; kernel enforces | Source-level, per-instance, checked before run; includes numeric ceilings and a `+inf` reading for dropped bounds |
| Capsicum, Fuchsia component framework, Wasm component model (citation to be checked) | Process or component sandboxing with routed capabilities | Authority is a compiler-checked property of the spawn graph; the formal model derives held and reach from component shape |

## Evidence on main
| Claim | path:line or test | status | note |
|---|---|---|---|
| Spawn may narrow, never widen; closes the amplifier hole | `docs/capability-attenuation.md:6-22`; `src/revl/lower.py:18533` (`_check_spawn_attenuation`) | shipped | Applies to activation-body spawns; spawns inside a `provide` method are bounded by G4 `emission[...]` instead (doc, "Scope: the activation-body hole") |
| Transitive closure; held is the spawner's own authority, not its spawn closure | `docs/capability-attenuation.md:35-47`; `tests/test_spawn_attenuation.py::test_widening_is_transitive_over_the_spawn_graph` | shipped | |
| Boundary-namespace fold, key renaming cannot launder | `docs/capability-attenuation.md:56-72`; `tests/test_spawn_attenuation.py::test_renaming_the_wiring_key_cannot_launder_a_boundary`, `::test_a_key_named_boundary_is_not_a_declared_token_of_the_same_name` | shipped | issue #1265 |
| Per-instance least authority | `examples/tenant_attenuation.rvl`; `tests/test_spawn_attenuation.py::test_least_authority_per_instance_is_enforced` | shipped | |
| Parameter order: narrower path admits, wider, sibling, dropped parameter refused | `src/revl/cap_order.py`; `tests/test_parameterized_capabilities.py::test_bridge_narrower_path_admits`, `::test_bridge_wider_path_is_refused`, `::test_bridge_sibling_path_is_refused`, `::test_bridge_dropped_parameter_is_refused` | shipped | Slice 1 |
| Per-instance literal substitution into `config.` parameters | `tests/test_parameterized_capabilities.py::test_per_instance_literal_binding_resolves_into_cone`, `::test_per_instance_unresolved_symbol_refused_fail_closed` | shipped | Slice 2; unresolved symbols compare only to themselves |
| Rejection examples for resource, parameter, budget widening | `examples/rejections/g4_spawn_widens_capability.rvl`, `g4_spawn_widens_parameter.rvl`, `g4_spawn_widens_budget.rvl`; `examples/budget_attenuation.rvl` | shipped | `formal/STATUS.md:70` says the budget refusal comes from the ceiling half alone |
| Partial order, monotone lineage, ceilings shrink, counter bounded, no host manufactured | `formal/RevL/Theorems/CapCeilings.lean:94,105,121,158,171,206`; `formal/STATUS.md:172-178` | shipped | STATUS lists these as proved, with its axiom column per theorem (`propext` alone for `attenuation_monotone`, `no_star_amplification` and `parameter_widening_refused`, otherwise with `Quot.sound`); no `sorry` or `axiom` declaration found by grep in the file |
| Held and reach derived from component shape | `formal/RevL/Theorems/CapCeilings.lean:943-1036` (`derived_*`), `:1238` (`same_key_different_boundary_refused`) | shipped | Under hypothesis `NameableEmission`; L0 fragment cannot spell externs or named functions (`CapCeilings.lean:368-378`) |
| Differential oracle against the checker | `formal/STATUS.md:70` (8 W rows, `attenuation_coverage` ratchet) | shipped | Parse-time canonicalization and `cap_order.disjoint` D2 clause unmodelled (same line) |
| Peer placement as a spawn edge; `dispatch_within_lineage` | `docs/design/461-verifiable-private-peer-pool.md:1-25, 335-375` | designed | The doc says "Design only ... nothing implemented"; no `dispatch_within_lineage` in `CapCeilings.lean` (no `peer` match) |
| Lease runtime, sandbox mapping of `path=` / `host=` (slices 3-5) | `docs/design/294-parameterized-capabilities.md:816-870` (staged plan); `enforced: mount` appears only in that doc | designed | Not verified as landed; no enforcement is claimed beyond admission |

## Numbers that exist
- 23 theorems in the capability-ceilings row of `formal/STATUS.md:70`; the file `CapCeilings.lean` has 49 top-level `theorem` declarations (rg count), so the 23 is the STATUS count of the guarantee set, not a file count. State which one when citing.
- 8 differential-oracle rows for this item (`formal/STATUS.md:70`).
- Test counts by `def test` grep: 14 in `tests/test_spawn_attenuation.py`, 14 in `tests/test_parameterized_capabilities.py` (the second file uses parametrized cases, so executed cases are higher; the tests were counted, not run).
- No performance, scale or usability numbers exist.

## Paper outline
1. Introduction: the amplifier hole and the claim.
2. The rule: held, reach, spawn graph, boundary namespace (why keys cannot be compared).
3. Parameterized capabilities as a partial order; the three value orders; additivity.
4. Budgets as ceilings; the +infinity reading of a dropped ceiling; two independent relations.
5. Formalisation in Lean: lineage, theorems, derivation from shapes, non-vacuity theorems, oracle.
6. Evaluation: refusal corpus, laundering attacks, per-tenant example.
7. Related work.
8. Limits: what is enforced versus declared; design-only parts.

## Threats to validity and limits
- The rule applies to activation-body spawns. A spawn nested in a `provide` method relies on G4 (`docs/capability-attenuation.md`, "Scope").
- Held is deliberately the spawner's own authority, not its spawn closure; this is a design choice that refuses some safe programs.
- The model is partial: the L0 fragment has no externs or named functions, the `NameableEmission` hypothesis appears on theorems, and canonicalization and a disjointness clause are unmodelled (`formal/RevL/Theorems/CapCeilings.lean:368-378`; `formal/STATUS.md:70`).
- The oracle covers verdict agreement on a finite corpus, not equivalence of checker and model. The trusted base includes the Python checker and parser canonicalization.
- The Lean spend model does not subtract a parent's pre-spawn spend from its budget (`formal/RevL/Theorems/CapCeilings.lean:46-48`), and bytes and time have no shipped counter, so the model does not claim they are metered (`CapCeilings.lean:50-54`).
- Parameters are static literals or config symbols; fully dynamic values are only declared and audited, not compared (design note 294, "Surface").
- Declared parameters are not enforced by an OS sandbox until the sandbox bridge lands; the design note keeps a checked / enforced / declared ledger for this reason.
- The peer-placement edge is design-only and carries no claim here.
- No user study, adoption data, or corpus-based precision evaluation exists.

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 45 checked, 8 corrected.
