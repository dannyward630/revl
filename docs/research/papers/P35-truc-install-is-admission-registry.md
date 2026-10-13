---
id: P35
title: "Install Is Admission: truc, a Package Manager and Git-Backed Registry Where Search Reuses the Admission Predicate"
theme: distribution
kind: tool-demo
maturity: partial
status: Admit-at-add, admit-at-assemble, search-as-admission, evidence-ranked resolve, adapter proposals, reproduce and the bootstrap fixpoint are on main with tests; the trust graph, adapter marketplace, hosted registry, signing and the reuse hint are not, and there is no evaluation.
fused_with: P34
---

## Pitch
A package manager has no install step to secure because fetched source enters a composition only through the same compiler gate that checks your own code, and the registry's search is that gate run as a filter.

## Abstract
Package managers fetch first and discover incompatibility or widened authority later, and they defend the supply chain with signatures and provenance. We describe truc, the component manager of the revl language, and its git-backed registry, built on a different premise: a fetched component is admitted through the compiler's own gate before it joins the assembly, so there is no separate install step. A registry query is the existing admission predicate run as a filter over candidates, with no new compatibility logic. `resolve` ranks the compatible set by declared authority (unbounded flag, capability count, emission count), then interface fit and direct over adapted, then evidence quality, where evidence earns rank only when something outside the publisher vouches for it (a valid attestation or a trusted publisher); an index row that disagrees with the entry's own source is refused, not demoted. When a candidate is refused, resolve can propose a safe adapter, never wire it. Human intent lives in `truc.toml`, proof in `truc.lock`, and `truc reproduce` rebuilds a published component and compares recomputed hashes tier by tier (source, dependency lock, IR, policy surface, backend version, independent pin, attestation, emitted artifact), with exit 0 when no tier mismatches, 1 on a MISMATCH (under `--strict`, also when a tier could not verify), and 2 on a usage or resolution error; cannot-verify is a tier outcome, not an exit code. truc is itself a revl composition and assembles itself as a regenerate-or-red fixpoint. We report the design, the 5-component seed registry, and test evidence; we report no user study, no large-registry measurement and no reuse-rate result.

## Problem and claim
Existing managers split two questions: is this the artifact the publisher published (lockfile hashes, checksum databases, signatures, provenance) and may this artifact do what it will do (usually left to the runtime or to review). A pinned, signed dependency can still widen authority, or can collide with something already in the assembly, and in the managers this paper compares against the failure surfaces at run time (to be checked).

The claim: if components declare their authority and the compiler already decides whether a component fits a composition, then the package manager can delegate both questions to that decision. Install is admission (`docs/registry.md:450`). Search is admission as a filter (`docs/registry-probe.md:1-20`). Ranking prefers the candidate with less declared authority, and the lock row stores the capability set and emission count the assembly admitted, so a lockfile diff shows authority growth in review (`docs/design/truc-architecture.md:295-330`; `src/revl/truc/_host.py:648-649`).

The paper's scope is the ordinary path on main today. It does not claim a trust graph, a marketplace or a hosted registry. Those are designed or proposed and are listed under limits.

## Contributions
1. Admit-at-add and admit-at-assemble: `truc add` plans, admits through `compile_files(..., manifest=running)` in process and vendors only on success; `assemble` re-admits and refuses on vendor hash drift (`src/revl/truc/_host.py:333-375` (`admit_all`) and `src/revl/truc/_host.py:581-650` (`commit_add`); drift check via `plan.drift` in `src/revl/truc/components/assembler.rvl`, `fn assemble`; `tests/test_truc_add_assemble.py:118`, `tests/test_truc_add_assemble.py:136`, `tests/test_truc_add_assemble.py:154`).
2. Search as admission probe: `resolve` calls the same `_service_compatible` predicate and a test compares its include/exclude decision to the real hot-swap gate on every seed Database provider (`src/revl/registry.py:1808-1830`; `tests/test_registry_resolve.py:186`, which runs over the seed Database providers; `tests/test_search_as_admission.py:169` covers only the `examples/` corpus).
3. Least-authority, evidence-aware ranking with verification: authority and fit first, then evidence quality; an index row that contradicts the entry's source is refused; fabricated evidence cannot outrank an honest entry (`src/revl/registry.py:1766`, `src/revl/registry.py:2120`; `tests/test_registry_index_trust.py:113`, `tests/test_registry_index_trust.py:143`, `tests/test_registry_index_trust.py:269`, `tests/test_registry_index_trust.py:300`; `tests/test_registry_evidence.py:187`, `tests/test_registry_evidence.py:210`, `tests/test_registry_evidence.py:244`).
4. Proposed-not-wired adapters: a refused candidate can come back as `compatible-with-adapter`, ranked below direct matches and with error-semantics evidence discounted when the plan merges outcomes (`src/revl/registry.py:1869`, `src/revl/registry.py:2120`; `tests/test_296_resolve_adapter_ranking.py:203`, `tests/test_296_resolve_adapter_ranking.py:225`, `tests/test_296_resolve_adapter_ranking.py:312`, `tests/test_296_resolve_adapter_ranking.py:482`).
5. Intent in `truc.toml`, proof in `truc.lock`, and `truc reproduce`: tier-by-tier recomputation with OK, MISMATCH and cannot-verify, exit 0/1/2, and a `--strict` mode where an unverifiable tier is not a pass (`src/revl/truc/reproduce.py:1-70`, `src/revl/truc/reproduce.py:848-899`; `tests/test_truc_reproduce.py`, 42 test functions).
6. truc assembles truc: its eight components are admitted by its own gate on every boot from a hash-pinned stage-0 lock, and a golden composition makes drift red (`src/revl/truc/truc.lock`; `tests/test_truc_bootstrap.py:90`, `tests/test_truc_bootstrap.py:118`, `tests/test_truc_bootstrap.py:147`).

## Related work
| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| npm, Cargo lockfiles | Pin versions and content hashes; resolve by semver | Lock rows also store the declared capability set and emission count the assembly accepted; admission decides fit, not a version range (`docs/design/truc-architecture.md:295-330`) |
| Nix | Reproducible builds from content-addressed inputs | `truc reproduce` rebuilds one published component through the compiler and compares eight tiers; it does not claim Nix-style whole-system reproducibility |
| Deno permissions | Run-time flags grant authority to a script | Authority is declared in the component and checked at assemble time; ranking prefers the smaller declared set |
| Sigstore, SLSA provenance (citation to be checked) | Who built it, from what, with what signature | Signatures are an optional evidence facet that earns rank only when verified; the stance is "unsigned-but-gate-verified beats signed-but-unverified" (`docs/registry.md:502-516`) |
| Go module checksum database (citation to be checked) | Transparency log of module hashes | The independent pin tier compares the project's own lock against the registry, to catch a substitution the registry made and re-indexed (`src/revl/truc/reproduce.py:30-36`) |
| Unison content-addressed code (citation to be checked) | Definitions identified by hash | Not content-addressed by definition; components are whole files with hashes in the index, and compatibility is structural, not name-or-hash identity |
| Capability-aware dependency work (for example work on permission manifests for packages) (citation to be checked) | Report or restrict package permissions | The compiler already enforces the declared set, so the manager adds no policy logic |

## Evidence on main
| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Install is admission; resolve executes nothing | `docs/registry.md:446-459` | shipped | Stance; backed by tests below |
| Fetched component admitted before it joins | `src/revl/truc/_host.py:333-375`; `tests/test_truc_add_assemble.py:118` | shipped | Refused component never written to `trucs/`, lock or `truc.toml` |
| Hash drift refused at assemble | `tests/test_truc_add_assemble.py:154`; `src/revl/truc/components/assembler.rvl` (`fn assemble`, `plan.drift`) | shipped | |
| Search uses admission predicate with no new logic | `src/revl/registry.py:36`, `src/revl/registry.py:58`, `src/revl/registry.py:1808-1830`; `docs/registry-probe.md:1-30`; `tests/test_registry_resolve.py:186` | shipped | The probe verdict file calls the probe "YES"; later code and tests confirm |
| Ranking: least authority, fit, then evidence | `src/revl/registry.py:1766-1790`, `src/revl/registry.py:2120-2175`; `tests/test_registry_resolve.py:99` | shipped | The test comment notes the seed registry ships no attestation, so evidence does not separate seed entries |
| Evidence earns rank only if verified | `src/revl/registry.py:2120` (docstring); `tests/test_registry_index_trust.py:269`, `tests/test_registry_index_trust.py:300`, `tests/test_registry_index_trust.py:340`, `tests/test_registry_index_trust.py:362` | shipped | |
| Evidence bundle per component | `docs/registry.md:44-65`; `src/revl/registry_evidence.py`; `tests/test_registry_evidence.py:161` | shipped | A missing facet is `unavailable`, never faked |
| Non-blocking policy verdict on candidates | `src/revl/registry.py:2106`, `src/revl/registry.py:2120` (`wouldBeRefused`, `policyPreview`) | shipped | Prediction only; absence is not an approval. No dedicated test file was opened |
| Adapter proposals in resolve | `tests/test_296_resolve_adapter_ranking.py:203-312` | shipped | Marketplace of verified adapters is not built |
| Trust graph and trusted-mediator marking | `docs/design/296-adapter-synthesis.md:909-912` ("the mediator marking does not exist yet") | proposed | `docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:593` lists it as external proposals, folded into the adapter work; no design beyond that sentence |
| `truc reproduce` tiers and exit codes | `src/revl/truc/reproduce.py:848-899`; `tests/test_truc_reproduce.py:67`, `tests/test_truc_reproduce.py:104`, `tests/test_truc_reproduce.py:123`, `tests/test_truc_reproduce.py:141`, `tests/test_truc_reproduce.py:279`, `tests/test_truc_reproduce.py:453`, `tests/test_truc_reproduce.py:555`, `tests/test_truc_reproduce.py:599` | shipped | |
| truc assembles truc | `tests/test_truc_bootstrap.py:90`, `tests/test_truc_bootstrap.py:147`; `src/revl/truc/bootstrap/` | shipped | Design doc slice 5 marked landed |
| Reuse hint | `docs/registry.md:22`, `docs/registry.md:498-500` | designed | "not yet wired"; exit test unchecked |
| Hosted registry, accounts, signing as a publish gate, version-range resolve | `docs/registry.md:502-516` | declined or later | Listed as non-goals |
| `docs/design/truc-architecture.md` header says "design only" | `docs/design/truc-architecture.md:3` | stale | Contradicted by the code and tests above; cite the code, not this header |

## Numbers that exist
- Seed registry: 5 components (`registry/components/`: audited_database, mysql_database, pg_database, readonly_database, user_cache). Sample size for any claim about ranking is therefore tiny.
- Probe: 5 candidate providers, 3 admitted and 2 refused, per `docs/registry-probe.md` (one consumer, one key). Reproduced by `tests/test_search_as_admission.py:169`, which runs on the `examples/user_cache.rvl` corpus, not the seed registry.
- Test function counts by file (name-pattern count, not run): truc_reproduce 42, registry_releases 30, truc_name_jail 23, bundle 32, adapter_predicate 26, resolve_adapter_ranking 17, truc_bootstrap 17, registry_resolve 11, registry_index_trust 11, truc_apply_stack_check 13, truc_ship 13, truc_add_assemble 7, registry_evidence 6.
- Roadmap archive rows quote 17 tests for `truc reproduce` at landing and 15 for `revl bundle` (`docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:605`, `docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:621`); the file now has more.
- No reuse rate, no token cost per path (the registry doc names both as planned measurements, `docs/registry.md:461-470`), no latency table for resolve on a large registry. None yet.

## Paper outline
1. Motivation: two questions package managers conflate, and the run-time failure they leave.
2. The premise: admission as the single decision; truc is a composition that calls the gate.
3. Walkthrough: add (accepted, refused G2), assemble, drift refusal.
4. Resolve: search as admission, ranking, evidence rules, refused index rows, adapter proposals.
5. Reproduce: eight tiers, three outcomes, strict mode, the independent pin.
6. Dogfood: truc assembles truc; regenerate-or-red.
7. Evaluation (to be written): reuse rate, attack cases, resolve latency.
8. Limits and related work.

## Threats to validity and limits
- The seed registry has 5 entries and no attestation; the ranking test says mysql and pg tie on authority, fit and evidence and are separated by source length and name (`tests/test_registry_resolve.py:99-112`). Evidence ranking is exercised mostly by synthetic registries in `tests/test_registry_evidence.py`.
- The registry doc states that an entry's extern classifications are trusted, not verified (G8 caveat, `docs/registry.md:456-459`). Admission checks structure and declared authority; it does not check that a declared effect class is honest. Every response carries this in `assumptions`.
- The stance "the registry needs no trust beyond availability" is stated in the doc. The same doc declines authenticated publisher identity, so continuity checks compare self-asserted labels (`docs/registry.md:509-512`). Publisher trust is a caller-supplied set.
- Resolve reads the current release only; frozen history is stored but is not a selectable set.
- The registry is a git repository on disk. Nothing here shows behavior with many authors, name squatting or a hosted index.
- `truc reproduce` rebuilds with the current toolchain; a toolchain drift is reported as a mismatch or cannot-verify, which is honest but means a user must keep the toolchain in step.
- The trust graph and the verified-adapter marketplace appear only as external proposals in the roadmap archive (`docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:593`, `docs/roadmap-archive/12-post-v2-0-horizon-strategy-review.md:603`). A reader will compare the abstract with the status tags, so the abstract is kept to the shipped path.
- The lock makes authority growth reviewable; it does not prevent a wider candidate from being chosen.

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 60 checked, 11 corrected.
