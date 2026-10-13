---
id: P75
title: "Gating Prose Claims Against the Tree: Claim-Honesty Infrastructure for a Research Codebase"
theme: methods
kind: experience
maturity: shipped-evidence
status: "Five gates and their tests shipped on main, four wired into CI; no catch-rate study, outside baseline or decay-share denominator yet."
fused_with:
---

## Pitch

A roadmap that is prose decays, so every falsifiable sentence in it (a cited test, a cited symbol, a cited path, a marker naming a branch) is resolved against the working tree and git in CI, and every benchmark claim must declare an evidence rung that a program checks.

## Abstract

Research codebases keep their source of truth in prose: a roadmap says which test proves which claim, which branch is in flight, which design is landed. Prose does not fail when the thing it cites is renamed, moved or merged. We describe the claim-honesty layer of revl, a language and compiler whose roadmap is a single document of about 790 KB. The layer has four parts. A marker gate resolves "in flight on branch X" markers against git. A citation gate resolves cited tests, symbols, paths and scoped absence claims against the tree. A vision-document gate resolves the commands, links and paths in the project's public rationale document. A vocabulary-mirror gate lists every closed vocabulary declared in more than one module and fails when copies diverge. On top of the gates sits an evidence ladder for benchmark claims (claimed, measured, demonstrated, supported), enforced by a checker that reads a JSON eval report and refuses any claim that stands higher than its attached evidence, and an epistemic split of the gauntlet dossier's sections into proved, tested and claimed. We report the measured decay that motivated each gate (twelve stale in-flight markers on one day, five reports opened by correcting a sentence that git agreed with), the false-positive counts that decided which rules were thrown away (54 of 58 on one rejected absence rule), and a ratchet whose count must change, in a visible one-line diff, every time the documented debt changes. We also report the project's own failures: three design documents whose status headers were not updated when code for them landed. The gates are advisory-to-blocking by construction; we describe what each cannot decide.

## Problem and claim

Claims about a repository live in prose, and prose is the one artifact no build step reads. The roadmap's own gate says it in its source: git answers questions about branches and shas, but not "does the test this sentence cites still exist" (`tools/check_roadmap_claims.py:3-8`). Existing remedies (doctests, literate programming, artifact badges) attach the check to code. They do not cover a source-of-truth document that cites code.

The claim of the paper is narrow and checkable. (1) A small set of syntactic claim shapes (cited test, cited symbol next to a cited path, cited path, scoped absence, in-flight marker, closed vocabulary declared twice) covers the decay this project measured, and each can be resolved with no model and no judgment. The share of all decay these shapes cover is not measured. (2) Rules that look obvious but are unscoped fail by orders of magnitude, and the paper reports the counts. (3) A ladder of four rungs, enforced by a program that only ever refuses and never promotes, is meant to keep benchmark claims from outrunning their evidence.

The paper is an experience report. It does not claim the gates remove false claims. It claims they detect a class of mechanically detectable decay, shows the cost of each rule, and shows where the project's own documents still disagree with its code.

## Contributions

1. A taxonomy of four mechanically resolvable claim shapes about a tree (test, symbol, path, scoped absence) with the measured reason each is scoped as it is (`tools/check_roadmap_claims.py:19-99`).
2. A marker gate that checks "in flight" markers against git ancestry and remote branches, with an explicit statement of what it cannot know (`tools/check_roadmap_markers.py:1-60`).
3. A vocabulary-mirror gate using exact equality of closed vocabularies across modules, with the measured alternatives rejected (Jaccard >= 0.9 gives 117 pairs; subset gives 424 and 159) (`tools/check_vocabulary_mirrors.py:34-52`).
4. A ratchet plus allow-list design that separates "the citation is right and the tree is the wrong place to look" from "the citation is wrong and the document must be edited", and forces debt to shrink (`tools/check_roadmap_claims.py:105-128`, `tools/roadmap_claim_ratchet.json`).
5. The EVAL-REPORT-1 evidence ladder and its checker, which refuse over-claims at the point a number is stated (`docs/design/478-eval-honesty-protocol.md:116-160`, `tools/check_eval_report.py`).
6. Cautionary data: stale status headers in the project's own design documents.

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Literate programming (Knuth) (citation to be checked) | Interleaves prose and code in one source | The roadmap stays prose; claims in it are resolved against the tree by a separate gate |
| Rust doc tests, Python doctest | Run code examples in docs | Check that cited tests, symbols and paths exist; do not execute them |
| Executable specifications (Cucumber, FitNesse) (citation to be checked) | Make the spec itself run | The spec is a free-form roadmap; only citation-shaped sentences are checkable |
| ACM artifact badges (Available, Evaluated, Reproduced) | Human-awarded badges per artifact | A program computes the highest rung the attached evidence justifies and refuses a higher claim |
| ML reproducibility checklists (Pineau et al.) (citation to be checked) | Self-reported checklist | The checker reads a structured report, requires grader != generator, requires named gates |
| Link checkers, `markdown-link-check` | Check URLs resolve | Also resolve symbols inside files, scoped absences, and git-state markers |
| Claim-evidence-reasoning frameworks (science education) (citation to be checked) | Teach structuring a claim with evidence | Evidence is a machine-checked artifact, not a rhetorical form |

## Evidence on main

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Citation gate with four rules (test, symbol, path, absent) | `tools/check_roadmap_claims.py:19-48` (rules), `tools/check_roadmap_claims.py:178` (`RULES`); `tests/test_roadmap_claims_gate.py` (45 tests) | shipped | Run with `--check` in CI: `.github/workflows/ci.yml:496` |
| Unscoped absence rule rejected with counts | `tools/check_roadmap_claims.py:50-59` | shipped | 98 unscoped subjects, 58 identifier-shaped, 54 defined in the tree, essentially all of them correct sentences about the language (the gate's own comment) |
| Historical citations skipped by a retrospective cue | `tools/check_roadmap_claims.py:61-70` | shipped | Same excision as the marker gate |
| Allow-list with written reasons (25 entries) and ratchet (count 1) | `tools/roadmap_claim_allowlist.json`, `tools/roadmap_claim_ratchet.json` | shipped | A ratchet entry that stops matching fails `tests/test_roadmap_claims_gate.py` |
| Marker gate, 4 failure rules | `tools/check_roadmap_markers.py:14-45`, `Makefile:41`, `Makefile:52` | shipped | CI invocation at `.github/workflows/ci.yml:460` |
| Marker gate states its limit | `tools/check_roadmap_markers.py:48-60` | shipped | It "cannot tell whether a landed branch actually CLOSED the finding" |
| Vision document gate (command, link, path, tier table) | `tools/check_vision_claims.py:1-50`, `tests/test_check_vision_claims.py` (36 tests), `Makefile:94-95`, `.github/workflows/ci.yml:529-530` | shipped | Includes `--self-test` that plants a rename per rule |
| Vocabulary mirror gate, exact equality | `tools/check_vocabulary_mirrors.py:1-52`, `tests/test_check_vocabulary_mirrors.py` (26 tests), `.github/workflows/ci.yml:385-386` | shipped | Three motivating instances under issue #1285 (#1272, #1276, #1195; in the second, two of three copies had drifted), MIN_TOKENS = 4 |
| Four-rung ladder and report schema | `docs/design/478-eval-honesty-protocol.md:116-160` (status FROZEN, line 3) | shipped | Refines EVAL-1 section 5, "measured is not supported" |
| Ladder checker | `tools/check_eval_report.py:1-35`, `tests/test_check_eval_report.py` (15 tests, e.g. `test_rejects_claim_above_its_evidenced_rung`, `test_rejects_public_claimed_floor`) | shipped | Not a `ci.yml` step: it runs through `tests/test_census_artifact.py` and the census publisher. Checks the report is internally honest, not that numbers are correct (`docs/design/478-eval-honesty-protocol.md:178-190`) |
| Checker is applied before publication | `tools/publish_census_artifact.py:88-98` | shipped | A report that fails is "not published" |
| Epistemic split of the gauntlet dossier | `docs/gauntlet.md:17-37` | partial | Sections are proved / tested / claimed; one sub-entry has status "derived" (teardown). The dossier slots are not yet wired to the tests ("pending slots" in the same document) |
| Doc status inventory | `docs/DOC-STATUS.md:1-30` | shipped | Statuses are human judgement; the document says needs-work is "a statement about the audit, not a known inaccuracy" |
| Design 259 header contradicts code | `docs/design/259-checked-parallel-emissions.md:3` ("design, not implemented"); `src/revl/parallel.py` (349 lines); `tests/test_parallel_259.py` | shipped as counter-evidence | Test header says "Slice 1 is CHECKER-ONLY", so the code is a slice, not the whole design; the header is stale, not wholly false |
| Design 260 header contradicts code | `docs/design/260-emission-cardinality-bounds.md:39`; `src/revl/cardinality.py` (1187 lines); `tests/test_cardinality_260.py`, `tests/test_budget_260.py` | shipped as counter-evidence | Same caveat: slices landed, header not updated |
| Design 438 header contradicts itself | `docs/design/438-petri-reachability.md:3-4` ("Design only: no compiler change") vs `docs/design/438-petri-reachability.md:532` ("Status: landed (issue 171)") | shipped as counter-evidence | The document says do not build the engine, and one linear check landed; the top header is stale, the section header is current |

## Numbers that exist

- Marker decay, measured 2026-09-02: twelve "FIXING on fix/<branch>" markers for branches already landed, five items closed behind a stale marker (`tools/check_roadmap_markers.py:6-9`). Sample: one roadmap, one day.
- Citation decay, measured 2026-09-15: five separate reports opened by correcting a roadmap sentence that git agreed with and the tree did not (`tools/check_roadmap_claims.py:10-13`).
- Rejected absence rule: 98 unscoped "no X" subjects, 58 identifier-shaped, 54 defined in the tree, essentially all correct sentences about the language (`tools/check_roadmap_claims.py:45-59`).
- Path rule widening: 79 judged citations to 498 in one change (issue #1233), with the stale ones held as ratchet debt (`tools/roadmap_claim_ratchet.json`, comment block). Ratchet count is 1 today; allow-list has 25 entries.
- Bare filenames: 172 distinct, 11 resolve to nothing (`tools/check_roadmap_claims.py:83-88`).
- Vocabulary mirror alternatives: Jaccard >= 0.9 gives 117 pairs; strict subset 424 (const+func) and 159 (const only); thresholds below 0.7 chain 27 to 30 declarations; MIN_TOKENS 3 would raise classes from 42 to 68 (`tools/check_vocabulary_mirrors.py:34-52`).
- Test counts for the gates: 45 (claims gate), 36 (vision), 26 (vocabulary), 15 (eval report), counted by `def test`.
- Not available: a time series of how many findings each gate raised over its life. No aggregate false-positive or catch rate over merged PRs exists in the tree.

## Paper outline

1. Introduction: the source-of-truth document and its decay.
2. Claim shapes: the four citation shapes, the marker shape, the vocabulary shape; what is deliberately not checked and the counts that decided it.
3. Debt without drift: allow-list, ratchet, advisory-then-blocking rollout.
4. The evidence ladder: report schema, rungs, never-promote rule, noSelfScore at the report level, the epistemic split in the gauntlet dossier.
5. Evaluation: decay measurements, catch-rate replay, cost, ladder coverage.
6. Failures: stale design headers; what the gates cannot decide.
7. Related work and discussion.

## Threats to validity and limits

- Single project, single team, one roadmap. Generalisation is untested.
- The marker gate "cannot tell whether a landed branch actually CLOSED the finding" (`tools/check_roadmap_markers.py:48-50`). The claims gate checks existence, not that a cited test asserts what the sentence says.
- The ladder checker's green result does not mean "these numbers are true"; it cannot prove the written-down grader identity is the one that graded, or that a named review was genuine (`docs/design/478-eval-honesty-protocol.md:178-190`).
- Rule choices were tuned on the same roadmap they are evaluated on.
- The three stale headers are anecdotes, not a sampled estimate. For 259 and 260 the code is a slice of a larger design, so "contradicts" overstates; "was not updated when slices landed" is accurate.
- The decay numbers are mostly comments and design-document prose on main, not reproducible runs.
- The share of all decay covered by the claim shapes has no denominator.
- The gate's own comment at `tools/check_roadmap_claims.py:55` still calls the roadmap 1.4 MB; the file is about 790 KB.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 50 checked, 13 corrected.
