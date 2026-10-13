---
id: P27
title: Composition as a Row Table: Stable Identity, Layered Patches and Admission-Checked Overlays
theme: lifecycle-swap
kind: full
maturity: partial
status: Row table, layered patches, fold, incremental admission and authority panel are built and tested on main (136 test functions); no evaluation, and runtime activation of a patched composition is not built.
fused_with:
---

## Pitch

A composition is a table of named rows, so a third-party patch is a pure fold that is re-admitted by the same gate as the base, and two providers for one slot are a refusal that only the operator can resolve, never an outcome of file order.

## Abstract

Overlay systems for configuration (Kustomize, Helm values, Compose override files, NixOS modules) resolve conflicts by precedence: the later file wins. A composition whose behaviour changes because someone reordered a list is the failure this paper targets. We present a composition model for revl in which a composition is a set of rows, each with a declared label scoped to its origin and a checked claim set `(key, realm)` that the compiler's provision-disjointness rule (G2) already uses. Patches are four operations (`add`, `remove`, `replace`, `configure`) addressed to a row by label or by provision claim; an address that matches nothing is a refusal, never a no-op. Resolution is a pure fold that never calls the linker's gate (`_link`); it runs a G2 pre-check whose refusals only improve the message. Withdrawals apply before admissions, peer layers that fight over one slot refuse and name both sides, and only the operator's single site layer can decide, by naming both. The folded table is a candidate that goes through the same admission pipeline as any composition, incrementally, so a patch that violates G2 or G3 is refused before anything runs. Rows added by a third party are compiled under an untrusted-author profile on the CLI path (confinement is opt-in in the Python API) unless the operator passes `--trust-host-code`, and an authority panel keyed by row label shows the widening a patch causes, including config-only patches, and prints its own blind spots. All of this is built on main with 136 test functions across four test files for the row, fold, confinement and distribution layers. We have no user study, no performance measurement and no comparison against the overlay tools on a shared task set; we say what is and is not shown.

## Problem and claim

Overlay and module systems let a third party change a deployed composition without forking it. They decide conflicts by order: Compose's later file overrides the earlier, Kustomize applies patches in listed order, and a NixOS option with two definitions is resolved by priority or merge function. The result is that which provider serves a slot can change when a list is reordered, and a patch that targets something that no longer exists often does nothing. The design docs name this as the failure to beat (`docs/design/426-composition-layers.md:80-100`, decision 4; `docs/composition-layers.md:13-19`).

The claim: if a composition is represented as rows with stable identity and a checked claim set, then (1) layering is a pure fold over those rows, (2) the layered result is an ordinary candidate for the existing admission pipeline, so a patch is checked by the existing gate (a written soundness argument for the fold is still missing), and (3) precedence can be removed from provider selection entirely. The design states that the fold is not on the trusted path and that a bug in it can only over-refuse (`docs/composition-layers.md:299-304`); this is not yet tested.

The paper is about the semantics of that model and its admission-side consequences. It is not about packaging or distribution and not about the runtime activation of a patched composition, which the docs say is whole-generation for anything but a pure addition and is blocked by G7, not by effort (`docs/design/426-composition-layers.md:631-650`).

## Contributions

1. A row table with identity decoupled from both file and component: a declared label scoped to an origin (`.` or a package key), a claim set checked against the component header, and component name kept as provenance only. A rename upstream is a non-event, an added provision is reported, a removed provision is a refusal (`docs/composition-rows.md:56-76`; tests `test_label_survives_a_component_rename`, `test_label_survives_an_upstream_surface_addition`, `test_a_removed_provision_is_a_refusal` at `tests/test_composition_rows.py:159`, `:174`, `:194`).
2. Four patch operations with no positional operation, claim-preserving `replace`, typed `configure`, and an unresolved address as a refusal (`docs/composition-layers.md:78-135`; `tests/test_composition_layers.py:199`, `:215`, `:230`).
3. A pure fold with a published peer-conflict table: refuse between peers, merge disjoint `configure`, idempotent double `remove`, and a single operator site layer that resolves by naming both sides (`src/revl/composition.py:2052-2090`, `_peer_rules`; `tests/test_composition_layers.py:276-420`). Withdrawals before admissions make `remove`-then-`add` and `add`-then-`remove` agree (`tests/test_composition_layers.py:429`).
4. Incremental admission of the resolved delta into the already-admitted base, with a `--full` escape hatch and a test that both reach the same manifest while the incremental path compiles fewer components (`src/revl/composition.py:2516-2645`; `tests/test_composition_layers.py:803`).
5. Row-granular confinement and an authority panel: layer rows admit under the untrusted-author profile, grants are key-precise and cannot be written by a stack layer, crossing tokens are re-keyed by row label, a config change carries a value digest, and the headline is fail-closed with an always-printed blind-spots block (`src/revl/authority_panel.py`; `tests/test_composition_confinement.py:96`, `:371`, `:460`, `:478`, `:528`, `:552`).

## Related work

| prior system or line of work | what it does | what revl does differently |
|---|---|---|
| Kustomize (bases, overlays, strategic merge and JSON patches) | Patches resolve by listed order; a patch whose target is missing fails or is skipped depending on the patch type (citation to be checked) | Peer conflicts refuse; unresolved address always refuses; result re-admitted by a soundness gate |
| Helm values and subcharts | Later `-f` file overrides earlier; no notion of a slot with one provider | Slot (provision claim) is the unit; second provider is G2 refusal |
| Docker Compose override files | Files merged in order, later wins | Same objection as above; revl has no ordering semantics for providers |
| NixOS module system | Options typed, with priorities (`mkForce`, `mkDefault`) and merge functions; conflicting definitions of a non-mergeable option are an error | Closest prior art for refusal on conflict. revl differs in that the patched composition is then checked for authority and effect safety, not only type-correct, and rows have origin-scoped identity |
| Jsonnet, CUE, Dhall | Pure configuration languages; CUE unification fails on conflicting values | Pure-fold and conflict-as-error are shared ideas. revl's patch target is a component with a checked claim set, not a value tree |
| Terraform modules and overrides | Module composition plus `_override.tf` files; plan shows diff before apply | Plan-before-apply is the analogue of the authority panel; revl's panel is computed from the admission result with a declared trust basis, not from provider diffs |
| Overlay filesystems | Upper layer shadows lower | Shadowing is exactly what revl declines to do for providers |
| Vagrantfile layering | Later config blocks override earlier | Same as Compose |

NixOS modules and CUE are the nearest relatives. The novelty claim is the combination: identity by origin-scoped label, patch addressed to a checked claim, and re-admission through an effect and authority gate, not any one of those.

## Evidence on main

| claim | path:line or test | status | note |
|---|---|---|---|
| Row table with label identity scoped to origin | `docs/composition-rows.md:45-92`; `src/revl/composition.py:136-240` (`Row`), `src/revl/composition.py:61-83` | shipped | `tests/test_composition_rows.py:208`, `:221` for parse-time duplicate and cross-origin same label |
| Claim assertion checked against header; removed provision refuses | `docs/composition-rows.md:93-110`; `src/revl/composition.py:396-417` | shipped | tests at `tests/test_composition_rows.py:194`, `:438` |
| Row-level G2 pre-check names rows; `_link` still runs G2 | `src/revl/composition.py:789-816` | shipped | `tests/test_composition_rows.py:292` |
| Four ops, no positional op, replace claim-preserving | `docs/composition-layers.md:78-100`; `tests/test_composition_layers.py:185`, `:199` | shipped | |
| Unresolved address refuses | `docs/composition-layers.md:121-135`; `tests/test_composition_layers.py:215`, `:230` | shipped | |
| Peer conflict table, permutation independence | `src/revl/composition.py:2052-2090`; `tests/test_composition_layers.py:276`, `:287`, `:306`, `:319`, `:331`, `:342`, `:351` | shipped | |
| Site layer resolves, exactly one site layer, `resolve` illegal in stack | `tests/test_composition_layers.py:364`, `:383`, `:396`, `:405`, `:418` | shipped | |
| Withdrawals before admissions (order independence) | `docs/composition-layers.md:291-298`; `tests/test_composition_layers.py:429` | shipped | |
| Fold is not on the trusted path | `docs/composition-layers.md:299-304`; `src/revl/composition.py:789-800` | shipped as design property | No test deliberately corrupts the resolver; exit test 8 in the design (`docs/design/426-composition-layers.md:1466-1527`) names it and no test with that name was found. The fold calls `_check_disjoint` (`src/revl/composition.py:1496`, `src/revl/composition.py:1896`), so it is not gate-free; the over-refusal claim also does not cover incremental admission, which takes the delta from the fold output (`_resolved_delta`, `src/revl/composition.py:2516-2547`; `admit_composition`, `src/revl/composition.py:2581-2645`) |
| Typed `configure` (unknown field, wrong type, non-config row) | `tests/test_composition_layers.py:486`, `:497`, `:506` | shipped | |
| `granted` and `place` cannot be written by a stack layer | `tests/test_composition_layers.py:572`, `:653` | shipped | |
| Incremental admission, `--full` escape hatch | `src/revl/composition.py:2581-2645`; `tests/test_composition_layers.py:803`, `:829`, `:853`, `:893` | shipped | Equivalence is tested on small fixtures only |
| Per-root profile split; layer externs refused, first-party admitted in one call | `tests/test_composition_confinement.py:96`, `:116`, `:154` | shipped | Confinement is opt-in in `admit_composition(confine=True)`; the CLI composition path passes `confine=True` (`src/revl/cli/document.py:186`) |
| Authority panel: config digest token, fail-closed headline, blind spots | `src/revl/authority_panel.py:183-348`; `tests/test_composition_confinement.py:371`, `:460`, `:478`, `:528`, `:552` | shipped | |
| `--accept` acknowledgement for panel tokens | `src/revl/authority_panel.py:346` prints the text; `src/revl/cli/parser.py:366-370` has `--accept` for `audit --diff` | partial | The `composition` subcommand (`src/revl/cli/parser.py`, about lines 276-330) has no `--accept` option; it exists only on `audit` (`src/revl/cli/parser.py:366-370`) and `dash` (`src/revl/cli/parser.py:2476`). The panel text tells the operator to use `--accept`, which `revl composition --panel` does not parse. The acknowledgement path is not claimed |
| Mandatory lock pin and vendored-dir jail | `docs/composition-layers.md:370-388`; `tests/test_composition_distribution.py:86-184` | shipped | package apply and stack check: `tests/test_truc_apply_stack_check.py:114-318` |
| Activation of replace/remove is whole-generation | `docs/composition-layers.md:340-345`; `docs/design/426-composition-layers.md:631-650` | designed (limit) | Stated as G7, not effort |
| Per-key re-resolution and partial dispose | none | not built | follow-on |
| `variant` clause | `docs/composition-rows.md:785-790` | not built | parse error by design |

The design note's own build-status header marks slices S1 to S6 as built (`docs/design/426-composition-layers.md:1-60`) and the tests above exist.

## Numbers that exist

- 136 test functions in `tests/test_composition_rows.py` (34), `tests/test_composition_layers.py` (66), `tests/test_composition_confinement.py` (29) and `tests/test_composition_distribution.py` (7), counted by `def test_` pattern, not by running pytest. Treat it as an inventory, not a pass count.
- Two measured bugs in a downstream engine's composition that rows turn into compile errors: a composition listing 31 components with a transitively used one missing, and a console panel printing nine names while the live boot served thirty-one keys (`docs/composition-rows.md:100-106`). Sample size 2, anecdotal.
- 18 exit tests specified in the design (`docs/design/426-composition-layers.md:1470-1527`). Test docstrings cite exit tests 1 to 5, 9, 12, 18 (`tests/test_composition_rows.py:12-30`), the order half of 8 (`tests/test_composition_layers.py:430`), 13 (`tests/test_composition_confinement.py:592`, `:609`) and 15 (`tests/test_composition_distribution.py:129`); a full mapping was not done.
- No timing and no incremental-versus-full cost measurement. The design says "On a 200-row composition that is seconds, not milliseconds" (`docs/design/426-composition-layers.md:626-628`); that is an estimate, not a measurement.

## Paper outline

1. Introduction: precedence as the root cause of overlay surprises; the claim.
2. Background: the admission pipeline, G2 provision disjointness, G3, the untrusted-author profile.
3. Rows: identity, origins, claim assertion, upstream change cases.
4. Layers: four levels, four operations, addressing, refusal-never-no-op.
5. Resolution: pure fold, peer table, site layer, ordering argument, why the gate is not in the fold.
6. Admission: incremental delta, equivalence, escape hatch, activation limit (G7).
7. Authority: confinement per row, grants, panel, three critical findings from design review (CRITICAL A and B at `docs/design/426-composition-layers.md:828-885`, and the third in section 9.3 at `docs/design/426-composition-layers.md:1177`) and how they compose.
8. Evaluation: scenario comparison, determinism property test, incremental cost, seeded-attack detection (to be built).
9. Related work.
10. Limits and future work (activation, `variant`, token granularity).

## Threats to validity and limits

- The panel is not complete. The design prints blind spots always: token granularity (a crossing that widens which paths it reaches produces no new token), first-party host bodies read by declaration not inspection, and unbounded externs (`docs/design/426-composition-layers.md:1070-1090`).
- `touches` is "not a security property" (`docs/composition-layers.md:194-205`).
- `--trust-host-code` forfeits a clean headline and the trust basis becomes CLAIMED (`docs/composition-layers.md:346-368`).
- Activation is whole-generation for anything but a pure add. The paper cannot claim hot patching.
- The provenance block's VERIFIED column waits on a registry feature; everything registry-sourced prints under CLAIMED (`docs/design/426-composition-layers.md`, build status).
- Invariant I2 (a distributable row must not import another row's source) does not hold for the project's own sources.
- `replace` is claim-preserving by rule; changing claims requires `remove` plus `add`. That is a design choice that may reject legitimate use.
- All fixtures are small. Nothing is measured on a real third-party ecosystem of layers.
- The descriptions of Kustomize, NixOS and the other tools come from general knowledge and have not been checked against their current documentation.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 19 checked, 4 corrected.
