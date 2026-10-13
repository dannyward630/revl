---
id: P41
title: "Reach-Completeness: One Bug Class Behind a Campaign of Critical Authority Holes"
theme: security
kind: experience
maturity: partial
status: The completeness harness, the jail path enumeration and the extern reach declaration are shipped with tests; the hole count and the claim that the harness would have caught the original holes are not backed by a replay.
fused_with: P11
---

## Pitch
Almost every critical hole in a capability language's security features had the same shape, a fold that visits one way authority crosses a boundary and misses another, and listing the crossings against the folds in a table turns "did we cover them all" from a review habit into a CI test.

## Abstract
We report on an adversarial review campaign over the shipped security features of a typed capability language, run in three waves in late August and early September 2026. The project's notes count roughly 14 critical holes in the 2026-08-31 review passes (design note 414) and roughly 18 across the three waves (roadmap; the two figures are not reconciled). The seven instances the design note lists had one shape: an authority-derivation surface (an approval-class fold, a reach sweep, a resource refusal at a process seam, an install-origin resolver) was keyed on one crossing kind and silently missed an alternate, so a capability was reached but not seen. We describe the class, give the seven instances the design note lists and the closed list in the roadmap, and present the response: a reach-completeness harness that enumerates crossing kinds and authority surfaces, forces every surface to classify every kind as in scope or exempt with a written reason, and asserts each in-scope cell with a differential (the surface's answer must change when the kind is removed). The shipped harness has 6 crossing kinds, 9 surfaces and 35 in-scope cells. We then apply the same lens to two later pieces of work, a filesystem confinement audit that found three path families bypassing a "single choke point", and a series of secret-registry walk defects across five backends. The second has a recurring failure worth reporting: a fix that bounded a walk by depth was itself the disclosure. We state what the harness does not do: it covers only crossing kinds someone already thought of.

## Problem and claim
Capability and sandbox systems are usually argued sound by a mediation story: every access goes through a monitor. Audits of such systems keep finding the same defect, that the story names one path and the system has another. In revl the monitors are folds over a composition: the approval class fold, the policy reach, the audit boundary, the untrusted-author sweep, the distribution seam refusal, the taint origin fold. Each was written against the crossing its author had in mind.

The claim is narrow and checkable. (1) The defects found in the 2026-08-31 review waves are instances of one class, and the design note lists seven concrete ones (`docs/design/414-reach-completeness.md:11-31`). (2) The class is mechanically checkable for the known crossing kinds by a table of kinds against surfaces in which every cell is a decision, and the harness that does this ships as a test file (`tests/test_reach_completeness.py`; not executed for this draft). (3) The class recurs below the level of crossing kinds, in walks over value shapes, and the same discipline (enumerate, force a decision per cell) is what the later fixes converge on.

We do not claim the harness finds unknown crossing kinds. The design note says so itself: "A crossing kind nobody has thought of is still out of its reach" (`docs/design/414-reach-completeness.md:99-103`).

## Contributions
1. A statement of the class and a list of its instances from three review waves, each pointing at a fix that is on main (seven in the design note, the landed list at `docs/v2.0-roadmap.md:100-120`).
2. The harness design (10 crossing kinds by 7 surfaces, each cell in scope or N/A with a reason) and the shipped version (6 kinds by 9 surfaces) with totality meta-tests and differential in-scope assertions (`tests/test_reach_completeness.py:556`, `:697`, `:711`, `:725`, `:757`).
3. A filesystem confinement case study: a docstring claimed one choke point, an audit found three path families around it plus a check-to-use window, and the fix replaces the claim with an enumeration, `PATH_FAMILIES`, and a scan test that fails if a mutating syscall is reached by any other route (`backends/python/revl_fs_workspace.py:20-60`, `:246`; `tests/test_fs_confinement_families.py:89-145`).
4. A reach declaration on externs, `extern emission(confined: param)`, with a diff that flags a confined extern becoming unconfined or moving its bound (`src/revl/parser.py:1673`, `src/revl/audit_diff.py:379-413`).
5. A lower-level instance study: the secret-registry walk defects, lettered (a) to (r) in the roadmap, where the same "walk visits one shape and misses another" appears per backend, including a depth cap that doubled as the confidentiality bound.

## Related work
| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Complete mediation (Saltzer and Schroeder, 1975) (citation to be checked) | Design principle: every access is checked | Turns the principle into an enumerated table with a CI test, and reports what escaped it |
| Caja, Joe-E capability audits (citation to be checked) | Audit a subset of a language for capability leaks | Reports the bugs of a shipped capability language across its own folds, not a language subset |
| Reference monitor literature (Anderson 1972) (citation to be checked) | Monitor must be tamperproof, always invoked, verifiable | Gives a concrete "always invoked" check per fold, with documented exemptions |
| Csmith-style compiler fuzzing (Yang et al., PLDI 2011) | Finds bugs by random programs | Not a fuzzer. A completeness checklist over named kinds. Complementary |
| Path traversal CVE classes (symlink, hardlink, TOCTOU) | Catalogue of path escapes | Adds the meta-lesson: the "single choke point" statement was false and was replaced by a tested enumeration |
| Property tests with mutation checks | Show a test can fail | The harness cells are differential (with-kind versus without-kind), which is the same idea applied to a security fold |

Novelty is mostly in the experience report and the differential cell design, not in the idea of enumerating cases.

## Evidence on main
| Claim | path:line or test | Status | Note |
|---|---|---|---|
| The review found one bug class, about 18 critical holes closed across three waves | `docs/v2.0-roadmap.md:94-100`, `CHANGELOG.md:343-349` | shipped (as documentation) | The roadmap says "~18" at `docs/v2.0-roadmap.md:98`; the design note at `docs/design/414-reach-completeness.md:5` says "~14" for the 2026-08-31 passes. The changelog lines give the three waves and no count. No per-hole list sums to 18 in the tree |
| Seven concrete instances of the class | `docs/design/414-reach-completeness.md:11-31` | shipped (as documentation) | Includes membership-versus-subset, the spawn seam, the transitive closure, the nested resource, the same-tier seam, the `..` forge |
| Harness exists with 6 crossing kinds | `tests/test_reach_completeness.py:74-81` (`CROSSING_KINDS`) | shipped | The design note proposed 10 kinds (`docs/design/414-reach-completeness.md:36-53`); the shipped file has 6 |
| 9 surfaces, 35 in-scope cells | `tests/test_reach_completeness.py:556-690` | shipped | Counted from the `SURFACES` table: 9 entries, 35 `IN_SCOPE` values out of 54 cells |
| Totality: each surface classifies every kind; every kind covered; every exemption has a reason | `tests/test_reach_completeness.py:697`, `:711`, `:725` | shipped | |
| Differential per in-scope cell | `tests/test_reach_completeness.py:757`, `:778`, `:796`, `:820`, `:833`, `:881`, `:997` | shipped | Module docstring states the rule (`:30-40`) |
| Fixtures exercise every kind | `tests/test_reach_completeness.py:953` | shipped | |
| Three surfaces agree on a shared zoo | `tests/test_reach_completeness.py:962` | shipped | Includes a fix where two surfaces named the same extern in different namespaces |
| Residual wave from the capstone review, three of four closed in the tree | `docs/v2.0-roadmap.md:132-148` | shipped (as documentation) | Written as consolidated on 2026-09-10 against the tree |
| The fourth residual (the WAL writer sees only kind 1) is now closed for free host externs | `backends/python/runtime.py:1386-1400`, `backends/python/replay.py:1556-1566`, `backends/python/emit.py:2553-2570`, `tests/test_crash_recovery.py:767` | shipped | The roadmap paragraph at `docs/v2.0-roadmap.md:142-149` still calls it open and predates the fix |
| Filesystem jail: choke-point claim replaced by an enumeration | `backends/python/revl_fs_workspace.py:20-60`, `:246`, `:2276` | shipped (py), partial (ts) | |
| Scan test fails on a mutating syscall reached around a guard | `tests/test_fs_confinement_families.py:111`, `:133`, `:145` | shipped | 6 tests in the file |
| Seven findings, executed escapes as regressions | `docs/v2.0-roadmap.md:1612-1620`, `tests/test_fs_confinement_escapes.py` | shipped (py), partial (ts) | The ts tier is "NARROWED, NOT CLOSED" for one finding (node has no `*at()` syscall). 15 tests in the escapes file |
| Extern reach declaration and weakening diff | `src/revl/parser.py:1673`, `src/revl/audit_diff.py:379-413` | shipped | The roadmap archive row says landed 2026-08-30 |
| Secret-registry walk defects (a) to (r) fixed per backend | `docs/v2.0-roadmap.md:1597-1606`; `backends/rust/test_rust_secret_registry.py`; `tests/test_seam_leak_gaps_815.py` | partial | Every item except (k) is marked fixed. (k) is "FOUND, NOT FIXED" (`docs/v2.0-roadmap.md:1599`) |

## Numbers that exist
- Harness size: 6 crossing kinds, 9 surfaces, 35 in-scope of 54 cells, 15 test functions (`tests/test_reach_completeness.py`, counted from the file).
- Seven concrete instances in the design note; "about 14" in the design note and "about 18" in the roadmap.
- Jail ts suite, quoted from the roadmap: against the pre-fix module the new suite fails 18 of 25 (`docs/v2.0-roadmap.md:1612`). The suite is `backends/typescript/tests/fs_confinement_escapes.test.ts`, which has 25 `it`/`test` blocks, so the denominator matches.
- Rust depth bound, quoted from the roadmap: a nine-level map emits zero secret marks, eight levels emits one (`docs/v2.0-roadmap.md:1603`). Go: from four nested map levels and deeper the leaf printed bare (`leaf=deep-canary-9999`), and the registered needle count saturated at 15 (`docs/v2.0-roadmap.md:1602`).
- Nothing else. There is no rate of holes per review hour, no count of holes the harness found, and no measurement of how many of the roughly 18 the harness would have caught.

## Paper outline
1. Introduction: capability systems fail by omission; the monitor that watches one door.
2. Setting: what a crossing, a surface and a fold are in revl, in one page and one figure.
3. The campaign and the class: three waves, the seven instances, the common shape.
4. The harness: kinds, surfaces, cells, totality tests, differential cells. Design-versus-shipped differences stated.
5. Case study A, the jail: a false "single choke point" claim, three families, the enumeration and the scan test.
6. Case study B, the secret walks: cycles, depth as disclosure, variant payloads, Map entries, declared shapes. The self-recurrence: a fix note exempted two backends and was wrong for both.
7. Reach declarations and the weakening diff.
8. What it does not catch: unknown kinds, and what the review passes still found afterwards.
9. Related work and lessons.

## Threats to validity and limits
- The harness's own note: "Not a fuzzer and not a proof" and unknown crossing kinds are out of reach (`docs/design/414-reach-completeness.md:99-103`).
- The hole count is the project's own count, from a review the same team ran. No external replication.
- The "about 18" and "about 14" figures disagree in the sources, and no tree document lists 18.
- The shipped harness is smaller on the kind axis than the design (6 versus 10). Two design kinds (same-tier and cross-tier seams) are folded into one `seam` kind; deferred emission and witnessed crossings are not columns. Whether that is a deliberate scope decision or a gap is not stated in the file.
- The harness shows that each in-scope cell depends on its kind. It does not show the surface is correct about what it does with the kind.
- The ts jail tier is explicitly not closed for one finding.
- The roadmap text on the secret-walk defects is long-form prose by the fixers. Counts and reproductions in it are self-reported and were not rerun for this draft. The walk defects are a neighbouring shape (value walks and termination), not the same class as the crossing-kind folds.
- The argument that depth-bounded walks are a regression is local to registries that must register every leaf; it is not a general claim about bounded walks.
- Not yet done: replay the harness against the pre-fix tree for each of the seven instances, build a per-hole ledger, and mutate each fold to confirm the matching cell goes red.

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 36 checked, 5 corrected.
