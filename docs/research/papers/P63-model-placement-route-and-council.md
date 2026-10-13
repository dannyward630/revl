---
id: P63
title: "Models as Placeable, Checked Effects: Route Conditions and a Council That Never Fabricates Consensus"
theme: agents
kind: full
maturity: partial
status: Declaration, placement ceiling, answer type, per-member inputs, a self-host port and a partial formal row are on main with test suites; no runtime aggregator exists and nothing has been evaluated on users or benchmarks.
fused_with: P62
---

## Pitch

If a model call is a capability-typed crossing that must be placed on a declared role, then, for a component that declares placement, "this confidential input never reaches a cloud model" is a compile-time fact, and a council whose disagreement case has no answer field cannot be made to resolve a split toward allow.

## Abstract

Agent systems choose which model answers a request in host configuration, so a checker that reads the program alone cannot say where a confidential value is sent, and "several models agreed" is a convention a caller trusts. We present two checked constructs in revl, a language with a capability-typed effect boundary. First, `route model on <action>` places an action's model calls on declared roles by the origin class of what the action receives. The block is a permission checked at admission, not a scheduler: a confidential origin routed to an `off_device` role is refused naming the action, the origin and the role, and the value-level ceiling refuses a confidential value that reaches a model crossing through no on-device arm; the exercised cases include a helper-function seam, and coverage of every path is not claimed. A role may also declare the capabilities a call to it can reach, which enters the attenuation product, so a model is accounted as an authority surrogate rather than as inert. Second, a `model council` binds role-placed members under an aggregation word from a closed vocabulary. The council's result type has a `Split` constructor that carries digests of the members' answers and no value of the answer type, so there is no total projection from the result to an answer. Admitting on a tie, counting the floor over responders rather than declared members, a non-total aggregation, and two members on one placement are refused under one guarantee code. We report the rule sets (13 council rules, raised at 22 sites in the checker, and 11 placement declaration rules), the test suites that pin them, and a Lean model of the tie rule. We also state what is not shown: no runtime aggregator exists, `on_device` is a declared claim, and no user study or benchmark has been run.

## Problem and claim

In current agent frameworks and routers the model behind a call is decided by configuration the program cannot see. `docs/design/531-model-placement.md:48-75` lists the three questions a checker cannot be asked: whether a confidential input went to a cloud model, whether a component never leaves the device, and which model produced a value. Ensembles have a parallel problem. Self-consistency, judge models and debate return one answer, and the code that consumes it cannot tell a unanimous result from a tie broken by taking the first member.

The claim has two halves, each narrow. (1) Placement of a model call can be a permission that the compiler checks against the origin lattice (`docs/design/249-taint-provenance.md`, cited from 531), and the check fails closed: an unrouted action in a routed component, a confidential origin with no arm, and an off-device arm all refuse (`src/revl/model_route.py:964-1000`). (2) For a council, the property "disagreement is never resolved toward allow" can be made a property of the types and of a closed rule vocabulary instead of a review convention: `Split` carries no `T` (`docs/design/543-model-council.md:156-166`), the floor is counted over declared members (543:272-292), and spellings that read as safety features (`on_tie allow`, `quorum answered`, `aggregate first`) parse so the refusal can say why (543 section 8).

The paper does not claim that a council improves answer accuracy, that `on_device` matches a physical fact, or that any runtime computes an `Aggregate`. `docs/design/543-model-council.md:524-531` says the last one in so many words.

## Contributions

1. `route model` and `model role`: a placement permission keyed by the origin lattice, with 11 declaration refusals and one value-side ceiling that uses a single admitting path for a confidential value (`docs/design/531-model-placement.md:141-170, 210-250`; `tests/test_model_placement_512.py`, `tests/test_model_ceiling_514.py`).
2. A closed sum `Answer[T]` and `Aggregate[T]` whose `Split` and `Inquorate` constructors carry digests, with a match-exhaustiveness rule, so no total projection to `T` exists (`src/revl/model_answer.py:26-60, 388`; `docs/design/543-model-council.md:128-190`).
3. A council declaration with 13 rules (raised at 22 sites in `model_council.py`) that each name a safe-looking spelling, split across two guarantee codes by a one-sentence rule: `G-MODEL-PLACE` when the subject is a role, `G-COUNCIL-SPLIT` otherwise (`docs/design/557-council-disagreement.md:94-134`; `src/revl/model_council.py:137-150, 575-600`).
4. Per-member origin ceilings: a council's ceiling for an origin is the join over members that receive it, so a local adversary can read what a cloud proposer cannot (`docs/design/543-model-council.md:327-404`; `src/revl/model_council.py:263`).
5. A model role enters the capability attenuation product through `reaches [...]` (`docs/design/541-model-in-attenuation.md:25-40`; `tests/test_model_attenuation_519.py`).
6. A Lean model `RevL.ModelCouncil.SplitOK` bridged to the checker's verdict on the tie rule, and `RevL.ModelPlace.PlaceOK` for placement, both with a differential corpus (`formal/RevL/Theorems/ModelCouncil.lean:16-91` for SplitOK; `formal/RevL/Theorems/ModelPlacement.lean:34-108` for PlaceOK; `formal/STATUS.md:58-59, 389-394`).

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| LLM routers (RouteLLM (citation to be checked), LiteLLM routers) | Pick a model per request to trade cost against quality, at run time | Placement is a permission checked at admission; a router may recommend, revl decides whether the destination is allowed (`docs/design/531-model-placement.md:30-47`). |
| Ensembling and judging (self-consistency, LLM-as-judge, multi-agent debate) (citations to be checked) | Combine several samples or models into one answer | The combined result is a sum type with an explicit non-answer case; the aggregation rule is a closed word, never user code (`docs/design/543-model-council.md:522-550`, non-goals). |
| Byzantine fault tolerance and quorum systems (citation to be checked) | Vote with a floor over the replica set so faulty members cannot shrink the quorum | Same floor discipline (declared, not answering, members) imposed statically on a model council; `quorum answered` is refused by name. No claim of fault-tolerance proofs. |
| Information-flow type systems (JIF, FlowCaml, taint tracking) (citation to be checked) | Label values and check flows to sinks | A model call is a sink class whose destination is a declared role with a residence bit; the ceiling is the join over council members. |
| Guardrail classifiers and constitutional classifiers (citation to be checked) | Filter prompts and outputs with a learned model | revl states a structural property, not a learned one; no filter is run. |
| Capability attenuation and object capabilities | Bound what a callee can reach | A model is treated as an authority surrogate, folded into the same attenuation product as a spawn edge (`docs/design/541-model-in-attenuation.md:25-40`). |

## Evidence on main

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| `model role NAME on_device/off_device` and `route model on <action> { origin -> role }` | `docs/design/531-model-placement.md:76-117`; `tests/test_model_placement_512.py` (19 test functions; doc says 19 tests) | shipped | Contextual identifiers, no lexer change |
| Confidential origin routed to an `off_device` role refused naming action, origin, role | `docs/design/531-model-placement.md:174-208`; `tests/test_model_ceiling_514.py:117-140` | shipped | |
| Value-side ceiling, one admitting path, verdicts `unrouted`/`unplaced`/`off_device` | `src/revl/model_route.py:964-1000`; `docs/design/531-model-placement.md:210-250` | shipped | Fires only for `confidential`; `secret` is judged elsewhere (531:273-281) |
| Ceiling survives a helper-fn seam | `docs/design/531-model-placement.md:282-288` (`models_at`) | shipped | 531:628-648 (section 10) says what is not verified and what is exercised, and claims no completeness |
| Placement is a permission, no IR | `docs/design/531-model-placement.md:299`; `tests/test_1311_model_routes_not_in_ir.py` | shipped | |
| Council declaration, 13 rules (22 raise sites in model_council.py) | `src/revl/model_council.py:137-150, 575-600`; `docs/design/543-model-council.md:437-480`; `tests/test_model_council_516.py` (77 test functions) | shipped | The doc later says 17 refusals are ported to the gate (543:758-768, 556) |
| `Split` carries no answer; digests only | `src/revl/model_answer.py:26-60`; `docs/design/543-model-council.md:156-166` | shipped (types) | |
| Match must name `Split` and `Inquorate` | `src/revl/model_answer.py:388`; `docs/design/543-model-council.md:713-735` | shipped | Measured on a commit hash in the doc: 1 of 6 programs admits, 5 refused |
| Floor counted over declared members | `tests/test_model_council_516.py:422-433` (`floor == 3`, `== 2`) | shipped (static value) | The number is computed; nothing asks members at run time |
| `G-COUNCIL-SPLIT` code, fix line, tier-matrix row | `docs/design/557-council-disagreement.md:41-60, 262-318`; `tests/test_council_disagreement_1190.py` (31 test functions) | shipped | |
| Per-member `reads <origin>`, per-origin ceiling | `docs/design/543-model-council.md:327-404`; `src/revl/model_council.py:263` | shipped | |
| Self-host port of council refusals | `docs/design/556-model-council-selfhost.md`; `docs/design/543-model-council.md:758-768` | shipped | |
| Formal: tie rule `SplitOK`, placement `PlaceOK` | `formal/RevL/Theorems/ModelCouncil.lean:16-91` (SplitOK); `formal/RevL/Theorems/ModelPlacement.lean:34-108` (PlaceOK); `tests/test_formal_council_split_1811.py` (11 test functions); `tests/test_formal_model_place_1811.py` (10); `formal/STATUS.md:58-59` | partial | STATUS says the row is deliberately silent on the other council refusals and on the value-level ceiling |
| Model role in attenuation product | `docs/design/541-model-in-attenuation.md:25-40`; `tests/test_model_attenuation_519.py` (19); `src/revl/lower.py:9176-9198` | shipped | Slice status in 541 is mixed ("slice 5 is partial") |
| A runtime that asks members and computes an `Aggregate` | `docs/design/543-model-council.md:524-531` | not present | Stated as a non-goal |

## Numbers that exist

- 11 declaration rules for `route model` (`docs/design/531-model-placement.md:141-170`). Ten are refused under `G-MODEL-PLACE`; rule 9 (the `secret` origin) is refused under `G-SECRET-FLOW`, so "11 placement refusals" overstates the code.
- 13 declaration rules for `model council` (22 `raise` sites in `src/revl/model_council.py`), 11 under `G-COUNCIL-SPLIT` and 2 under `G-MODEL-PLACE` (`docs/design/557-council-disagreement.md:94-134`).
- Test function counts by `def test_` on main: 77 (`test_model_council_516.py`), 31 (`test_council_disagreement_1190.py`), 19 (`test_model_placement_512.py`), 24 (`test_model_ceiling_514.py`), 19 (`test_model_attenuation_519.py`), 11 and 10 (formal tests). Parametrized tests expand beyond these counts; the docs quote 19 and 24 for the first two placement slices, matching.
- Non-vacuity measurements quoted in the docs: slice 1 of placement, 18 failed and 1 passed against an older commit; slice 2, 13 failed and 11 passed (`docs/design/531-model-placement.md:537-565`). Sample size is the test suite itself, not a user population.
- Council exit clause measured on one commit: of six programs carrying the same two-member council, one admits and five are refused (`docs/design/543-model-council.md:713-725`).
- The 9 `agree-G-MODEL-PLACE` differential rows and 1 `agree-G-COUNCIL-SPLIT` row (`formal/STATUS.md:58-59`). These are single digits and are not coverage.
- No accuracy, latency, cost or user-study numbers exist.

## Paper outline

1. Introduction: model choice is invisible to checkers; consensus is a convention.
2. Background: revl capability boundary, origin lattice, residence bit.
3. Placement: `model role`, `route model`, the permission vs. scheduler argument, 11 refusals, fail-closed verdicts.
4. The value ceiling: one admitting path, helper seam, why `secret` is not judged here.
5. The council: `Answer`/`Aggregate`, `Split` without a payload of type `T`, digests, floor over declared, abstain vs block, Inquorate vs Split.
6. Per-member inputs and the ceiling join; role reach in attenuation.
7. Refusing safe-looking spellings: the 13 rows and the two-code rule.
8. Evaluation: rule suites, non-vacuity runs, differential corpus, Lean model, plus a corpus study and runtime experiments still to be done.
9. Related work and limits.

## Threats to validity and limits

- `docs/design/543-model-council.md:524-531`: there is no runtime aggregator; a program can write `Agreed(plan)` itself beside a declared council, so the tie between a type and a particular council is by convention.
- `docs/design/531-model-placement.md:628-648` (section 10): `on_device` is a declared claim, not a physical fact; the eleven declaration decisions are not proved complete; coverage of every path by which a confidential value reaches a model crossing is not claimed.
- A component that declares no `route model` is unmoved by the ceiling (531:289-297). Placement is opt-in.
- Weighting, retries and user-supplied aggregation are non-goals, so the construct cannot express legitimate weighted ensembles.
- The Lean row covers only the tie outcome (`formal/STATUS.md:59`).
- Evidence is design docs plus unit tests written by the author; independent evaluation is absent. Many "measured" claims quote a single commit.
- Mixing placement and council in one paper invites the request for a runtime result; splitting into a placement paper and a short council paper is the fallback.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 24 checked, 6 corrected.
