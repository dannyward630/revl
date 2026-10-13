---
id: P34
title: "Version Numbers as Measurements: Derived Semantic Versioning and Compiler-Verified Consumer-Driven Contracts"
theme: distribution
kind: full
maturity: shipped-evidence
status: The drift predicate, version derivation, contract check and registry publish gate are shipped with tests; there is no empirical study on real package histories and no formal soundness statement.
fused_with: P35
---

## Pitch
The version bump a release needs is computed from the interface diff of two compiled compositions, where interfaces carry effects, and a consumer's pinned surface is checked in the provider's CI by the same predicate that the runtime admission gate uses.

## Abstract
Semantic versioning is a promise made by the author, and consumer-driven contract testing is a body of test code written by the consumer. We show both can be replaced by one measurement when the language's compiled interfaces carry effects. In revl, a service interface carries parameter and return types and whether each operation is an emission that crosses an audited boundary, together with its capability scope. One drift predicate is used three ways: at runtime admission to decide whether a hot-swapped service may replace a running one (strict when a running provider is retained, consumer-subtype otherwise); by `revl version --against` to compute the required semver bump (consumer regime); and by `revl contract check` to decide whether a provider still satisfies a consumer's pinned surface (consumer regime). Gaining an emission or widening a capability scope is a major change even when the type shape is compatible, because every consumer's boundary audit changes meaning; losing one is minor. The registry refuses a publish whose declared version is below the computed bump and refuses to publish when the bump cannot be computed, unless the publisher declares an opaque scheme, which is then marked unverified. The evidence is 21 version, 23 federation and 16 admission-relation test functions, plus 30 registry-release and 13 truc-ship test functions for the publish gate (`def test_` counts; parametrised cases not expanded). We have not measured the approach on real package histories; we describe the evaluation that would.

## Problem and claim
A hand-picked version number cannot be checked, and a changed effect profile is invisible to the version systems that track only type shape. Elm derives versions from API diffs, but its interfaces carry no effects; Pact-style contract tests need code per consumer and per provider and run against behaviour, not interface semantics.

The claim: (a) one drift predicate, defined for admission, suffices to compute the bump and to check consumer contracts, so that the version and contract verdicts are the predicate's own verdicts (two agreement tests check this on their fixtures; the admission use runs in a different regime, so the claim covers the consumer-regime uses); (b) making emission gain and capability widening major is the right extension for effect-carrying interfaces; (c) turning the computed bump into a registry rule is cheap once the measurement exists.

The paper claims no more than a mechanism, its soundness argument for the consumer regime, and its tests. It does not claim reduced breakage in practice.

## Contributions
1. A bump derivation as a join over per-operation changes, reading the admission predicate rather than re-implementing it (`src/revl/version.py:100-108`, `derive` at `src/revl/version.py:204`; `docs/derived-versioning.md` rule table).
2. An effect-aware compatibility relation replacing exact service equality at admission, relative to which running components touch the service (consumer, retained provider, none), with a conservative fallback when a key cannot be resolved (`src/revl/admission.py:161`, `src/revl/admission.py:328`, `src/revl/admission.py:358`; `docs/service-compat.md`).
3. Consumer-driven contracts without test code: `revl contract export` projects a consumer's external requirements, `revl contract check` runs the same predicate in the provider's CI, exit 1 on break (`src/revl/federation.py:73`, `src/revl/federation.py:227`; `docs/federation.md`).
4. A registry publish gate: under-bump refused by name, uncheckable bump refused unless the scheme is declared opaque, then marked unverified (`src/revl/registry.py:1181-1235`; `tests/test_registry_releases.py:347`).
5. Agreement tests tying version derivation and contract checking to the drift predicate (`tests/test_derived_version.py:276`, `tests/test_federation.py:338`); admission is not covered by either test.

## Related work
| prior system or line of work | what it does | what revl does differently |
|---|---|---|
| Elm `elm diff` / package bump enforcement | derives MAJOR/MINOR/PATCH from exported API diff | interfaces carry effects; emission gain and capability widening force major with no type change |
| cargo-semver-checks, API Extractor, japicmp (tool list to be checked) | lint a library API diff against a declared bump | one predicate shared with runtime admission; refusal is part of the registry write path |
| Pact consumer-driven contracts | consumer writes expectations as tests, provider replays them | consumer exports its required surface from compiled source; no test code; verdict is a static drift check |
| Protobuf / Avro schema compatibility modes | backward/forward/full checks on data schemas | operation-level variance (contravariant parameters, covariant returns) plus effects and `async`/`commutative` flags |
| Semantic Versioning 2.0.0 | convention, enforced by author | the number is a measurement; over-bumping is allowed, under-bumping refused |
| Research on breaking changes in Maven or npm (for example Raemaekers et al., Ochoa et al.) (citation to be checked) | measures how often semver is violated | motivates the empirical extension below; revl does not yet have such data |

## Evidence on main
| claim | path:line or test | status | note |
|---|---|---|---|
| Rule table: added is minor, removed is major, param narrowed major, return widened major, emission gained major, emission lost minor | `docs/derived-versioning.md` table; `tests/test_derived_version.py:70-185` | shipped | |
| Capability scope widened is major, narrowed minor | `tests/test_derived_version.py:200`, `tests/test_derived_version.py:215` | shipped | |
| Service `commutative` flip and arity change are major | `tests/test_derived_version.py:230`, `tests/test_derived_version.py:245` | shipped | |
| Bump is the real predicate's verdict, not a copy | `tests/test_derived_version.py:276`; `src/revl/version.py:108` | shipped | |
| Next version is computed from a current version | `tests/test_derived_version.py:269` (parametrised) | shipped | |
| Audit documents rejected as `--against` input | `tests/test_derived_version.py:365` | shipped | |
| Consumer regime (`providers_retained=False`) | `src/revl/version.py:100`; `docs/derived-versioning.md` "The consumer regime" | shipped | |
| Admission relation replaces exact equality; touchers identified; conservative fallback | `src/revl/admission.py:161`, `src/revl/admission.py:328`, `src/revl/admission.py:358`; `tests/test_service_compat.py` (16 tests); `docs/service-compat.md` | shipped | |
| Registry refuses under-bump by name, leaves registry untouched | `tests/test_registry_releases.py:347`; `src/revl/registry.py:1229` | shipped | `docs/derived-versioning.md` ("Relationship to the registry", lines 104-111) describes the phase-2 gate as where the measurement "becomes a rule", not as shipped. The doc is stale relative to the code |
| Over-bump is not a contradiction | `tests/test_registry_releases.py:312` | shipped | |
| Uncheckable bump refused under the default scheme | `tests/test_registry_releases.py:411` | shipped | opaque scheme marks the release "cannot verify" |
| Same gate reached from `truc ship` | `tests/test_truc_ship.py:351` | shipped | |
| Consumer surface pins only external requirements | `tests/test_federation.py:84` | shipped | |
| Contract break and pass cases, CLI exit behaviour | `tests/test_federation.py:118-200`, `tests/test_federation.py:410-479` | shipped | 23 tests in file |
| Contract verdict agrees with drift predicate | `tests/test_federation.py:338` | shipped | |
| Adapter probe for a break (satisfied-via-adapter) | `src/revl/federation.py:122`; `tests/test_federation.py:230-326` | shipped, extra | could be a section or a separate paper |
| The provider's CI enumerates registered consumers automatically | `docs/federation.md` "Where it sits" says the surface "is the artifact a registry would hold" | designed | no registry storage of consumer surfaces found in `src/revl/registry.py`; the CI loop is left to the user |
| "Split-brain safe" | not found for this mechanism | not supported | split-brain handling is in the deploy work (`docs/design/118-revl-deploy.md`, federation section), not in `contract check`; the claim is dropped |

## Numbers that exist
- Test counts (`grep -c "def test_"`): derived version 21, federation 23, service-compat 16, registry releases 30, truc ship 13. Parametrised tests are undercounted.
- The registry-releases and truc-ship tests exercise under-bump refusal (single cases).
- No measurement on real code bases, no false-positive or false-negative rate, no timing. None yet for everything empirical.

## Paper outline
1. Introduction: versions as promises; effects as the missing dimension.
2. Interfaces that carry effects: emission, capability scope, `async`, `commutative`.
3. One predicate, three uses: admission (strict or consumer regime, depending on whether a provider is retained), version derivation and contract check (consumer regime); why the consumer regime is independent of current wiring.
4. Bump rules and why emission gain is major.
5. Consumer-driven contracts without tests: surface projection, check, adapter probe.
6. Registry enforcement and the opaque-scheme escape.
7. Evaluation: agreement tests, then the empirical study (to be done).
8. Limits and related work.

## Threats to validity and limits
- The docs say `revl version` only measures the bump (`docs/derived-versioning.md`, "Relationship to the registry"), and consumer behaviour beyond the interface is out of reach: a provider that keeps its signature but changes meaning is a patch.
- Only the surface the compiler sees is covered; a consumer that does not export its surface is not protected.
- Registry authority is "whoever can write the registry directory" (`src/revl/registry.py:967`); there is no signed publisher identity yet, and publisher continuity is "continuity of a self-asserted label" and "not authentication" (`src/revl/registry.py:986-987`, and the refusal text at `src/revl/registry.py:1246`).
- The semantic choice that emission gain is major is a design decision, not a theorem; maintainers may disagree. The rationale is the one given in `docs/derived-versioning.md` (rule table, lines 26-27), backed by tests at `tests/test_derived_version.py:118` and `tests/test_derived_version.py:131`.
- Opaque-scheme publishing bypasses the check, with only a flag marking it.
- Evaluation is test-suite level; there is no field data. No claim of fewer outages is made.
- Admission is outside the two agreement tests, so agreement with the admission use is not tested.
- The registry is a git-backed directory, small by any ecosystem's standards.

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 18 checked, 4 corrected.
