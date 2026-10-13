---
id: P03
title: "Keeping a Proof Backbone Honest: Layering, Axiom Gate, Non-Vacuity Registry and Differential Oracle"
theme: formal-pl
kind: methods
maturity: shipped-evidence
status: "The three gate scripts, the registry and the differential oracle are on main with a current census; no gate-firing history, automated mutation study or registry audit exists yet."
fused_with:
---

## Pitch

A clean `#print axioms` does not tell you a theorem says anything. This paper describes the small set of gates (layering, axiom whitelist, a per-theorem non-vacuity registry, a differential oracle against the shipped checker) that were added after an adversarial review found six critical flaws in a Lean model of a real compiler, and what each gate does and does not catch.

## Abstract

Verification projects that mirror a production compiler in a proof assistant tend to fail quietly. A theorem can be axiom-clean and still be true by definition, or true because its hypotheses can never hold together, or true of a model that is stricter or weaker than the compiler it claims to describe. We report on the formal backbone of revl, a language whose compiler enforces a set of named guarantees (G1 to G9 and others) and whose Lean 4 model states them. An adversarial review on 2026-09-02 found six critical flaws, each demonstrated with a compiling Lean probe: a wrong rule for provision disjointness (no notion of realm), a hypothesis the model could not establish, a "semantics" with no state, a differential oracle that imported the model and used none of it, hard fixtures silently excluded from the comparison, and a conclusion that held by construction. We describe the four mechanisms added in response: an import layering (frozen L0, lemma farm, one theorem file per guarantee) enforced by script; an axioms gate with a whitelist of three foundation axioms and a registered-set check; a non-vacuity registry with one row per registered theorem (342 today: 188 instance, 29 necessity, 123 concrete, 2 contentless) and its own gate; and a differential oracle that decides the proved definitions in Lean and compares them to the shipped checker's algebra over a corpus. We report what the gates have caught, describe one mutation (making `Manifest.needs` realm-blind) that the oracle rejects with four mismatched corpus files (stated in the status file; no script re-runs it), and state what the registry cannot detect.

## Problem and claim

Mirror-model proofs fail in three ways the standard hygiene (`sorry`-free, no custom axioms) does not see: vacuous theorems, theorems about a model that has drifted from the implementation, and claims in prose that outrun the statements. The first revl formal layer had all three. Its own status file said the import layering was "enforced by imports, not by hope" while nothing checked it, and the roadmap archive states that only 3 of 25 theorems then carried non-vacuity evidence (`docs/roadmap-archive/13-the-embeddable-compiler-revl-as-a.md:198`).

The claim is narrow and checkable. Three toolchain-free scripts (`layering_gate.py`, `axioms_gate.py`, `nonvacuity_gate.py`) and a differential oracle (`formal/harness/diff_corpus.py`, 8445 lines, with `formal/harness/Oracle.lean`, 3304 lines) turn these failure modes into red builds. The registry checks witness names, not witness content. The evidence for the mechanisms is a dated review with six reproduced flaws and a repair in dependency order. The claim is not that the model is complete. The status file lists what each guarantee does not cover.

The link between model and implementation is differential testing, not extraction. The Lean side decides the proved definitions on a TSV exported from a corpus of revl files; the Python side calls the shipped checker. A mismatch fails `make formal` (`formal/harness/diff_corpus.py:40-56`).

## Contributions

1. A three-level layering (L0 frozen, L1 lemma farm, L2 one file per guarantee, no cross imports) enforced by `formal/scripts/layering_gate.py`, which also fails on modules outside the root import and on missing modules.
2. An axioms gate that fails on `sorryAx`, on any axiom outside `propext`, `Classical.choice`, `Quot.sound`, and on any registered theorem with no `#print axioms` line (`formal/scripts/axioms_gate.py:1-74`).
3. A non-vacuity registry: every registered theorem has a row with a kind (`instance`, `necessity`, `contentless`, `concrete`) and named witness theorems that are themselves registered, with rules that block self-witnessing and block using `concrete` to opt out (`formal/scripts/nonvacuity_gate.py:1-52`). Contentless theorems are kept visible as findings and printed on every run.
4. A differential oracle whose Lean side `decide`s the proved model and whose Python side calls the shipped checker, with disagreement buckets that are gate failures and ledgers that can only shrink for absence buckets.
5. A case study: the six-flaw adversarial review, the nine-step ordered repair, and the follow-up correction of 2026-10-07 to the claim that all nine exit steps had landed, because G9 walk coverage had never been one of them.

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| CompCert (Leroy) | Proves the compiler against a semantics, extracted OCaml is the artifact | revl proves a model of selected guarantees and tests the shipped Python checker against it; no extraction, so the gap is measured, not closed |
| CakeML | Verified end to end in HOL4, bootstrapped | Same contrast; revl's claim is about keeping a partial model honest, not about end-to-end correctness |
| seL4 | Refinement proofs between spec and C | revl has no refinement; the differential oracle plays the role of an empirical refinement check over a finite corpus |
| Mathlib linters, `#print axioms` practice | Hygiene checks on declarations | The registry adds a check that axiom printing cannot do: each theorem must name registered witnesses. It does not check that the witnesses inhabit the hypotheses (see limits). The layering gate enforces module discipline for parallel authors |
| Vacuity detection in model checking (Kupferman and Vardi) | Detects specifications satisfied vacuously | Applies the same idea to theorem hypotheses in a proof assistant, by naming witness theorems and checking the naming, rather than by an automatic mutation of the property (citation to be checked for the closest prior work in interactive provers) |
| Mutation testing for specifications | Mutates the spec or program to see if checks notice | revl does one hand-chosen mutation per review plus in-Lean "verdict flips" witnesses; it is not an automated mutation framework |
| Csmith, YARPGen (compiler testing) | Random program generation against compilers | The oracle corpus is revl's own examples and fixtures, not generated programs |
| Coq extraction | Executable code from proofs | Explicitly not used; `formal/STATUS.md:779` calls the attached items "extraction, not theorem" where it applies |

## Evidence on main

| Claim | Where | Status | Note |
|---|---|---|---|
| Layering rules are stated and enforced by script, run first in the gate | `formal/STATUS.md:3-14`; `formal/scripts/layering_gate.py:1-50`; `formal/scripts/run_gate.sh:1-8`, `:28-30` | shipped | Steps 1 and 2 need no Lean toolchain and always run |
| L0 is five files, 784 lines; L1+L2 are 11763 lines | `formal/RevL/*.lean`, `formal/RevL/*/*.lean` (line counts) | shipped | |
| Axioms gate: no `sorryAx`, no project axiom, registered set must match | `formal/scripts/axioms_gate.py:23-60`; `formal/CheckAxioms.lean:1-14` | shipped | |
| 342 theorems registered in `formal/CheckAxioms.lean` | `grep -c '^#print axioms' formal/CheckAxioms.lean` | shipped | |
| Registry kinds: 188 instance, 29 necessity, 123 concrete, 2 contentless | `formal/scripts/nonvacuity.tsv` (second column) | shipped | Counted from the file |
| Two contentless theorems labelled, not counted as proof | `formal/scripts/nonvacuity.tsv:38`, `:136`; `formal/STATUS.md:28-34`, `:2258` | shipped | `RevL.G5.teardown_registers_nothing`, `RevL.A8.outcome_trichotomy` |
| Gate rules: witness must be registered, no self-witness, `concrete` must be cited | `formal/scripts/nonvacuity_gate.py:38-52` | shipped | |
| Realm-blind `Manifest.needs` makes the oracle fail with four mismatched corpus files | `formal/STATUS.md:49` | partial | The status file states it; no cited text states the build and axioms-gate results for the mutant, and no script re-runs the mutation |
| Six critical findings found by compiling Lean probes | `docs/roadmap-archive/13-the-embeddable-compiler-revl-as-a.md:191-197` (review header line 191; C1 to C6 at lines 192-197) | shipped (as a written account) | Each has a re-check paragraph pointing at current lines |
| Oracle Lean side decides proved definitions; Python side calls `src/revl/cap_order` | `formal/harness/diff_corpus.py:44-56`; `formal/harness/Oracle.lean:1-3` | shipped | |
| Disagreeing buckets are fatal; absence buckets are ledgered and shrink-only | `formal/harness/diff_corpus.py:57-70` | shipped | |
| Per-row non-vacuity witnesses that flip a verdict | `formal/STATUS.md:281`, `:290`, `:297`, `:401`, `:409` | shipped | For example `RevL.G5Classified.g5_row_not_vacuous` |
| Coverage map per guarantee, with gap kind (modelling limit vs unbuilt work) | `formal/STATUS.md:36-76` | shipped | |
| Later correction: nine steps closed the G9 rule, not the walk | `docs/roadmap-archive/13-the-embeddable-compiler-revl-as-a.md:191`; `formal/STATUS.md:99-107` | shipped | `RevL.G9Coverage.coversBodyB` and the `GC` row |
| Toolchain pin | `formal/lean-toolchain` | shipped | `leanprover/lean4:v4.33.1` |

## Numbers that exist

- 342 registered theorems; registry data rows 342 (188 instance, 29 necessity, 123 concrete, 2 contentless). Source: `formal/CheckAxioms.lean`, `formal/scripts/nonvacuity.tsv`.
- Six critical findings, each demonstrated with a compiling probe; nine ordered exit steps. Source: `docs/roadmap-archive/13-the-embeddable-compiler-revl-as-a.md`, lines 191-197 (review dated 2026-09-02).
- Historical snapshots: 152 registered theorems at the 2026-09-02 landing (line 191); 175 registry rows at the re-check (line 199); 12 new witness theorems (line 203). The 342 is current.
- "Only 3 of 25 theorems carried non-vacuity evidence" before the registry (line 198).
- Mutation example: four corpus files mismatch when `Manifest.needs` ignores the realm (`formal/STATUS.md:49`). One mutation.
- Oracle census figures quoted in `formal/STATUS.md`, for example 182 G rows, 25 P rows, 1620 O rows, 281 confinement rows (lines 38-66). These move with the corpus; the gate prints the current totals.
- Size of the harness: `formal/harness/diff_corpus.py` 8445 lines, `formal/harness/Oracle.lean` 3304 lines.
- No numbers exist yet for time to run the gate, how often each gate has fired in the git history, or how many theorem commits the registry blocked.

## Paper outline

1. Introduction: mirror proofs lie quietly; the six flaws in one table.
2. Background: revl's guarantees, the model, the corpus.
3. The four mechanisms: layering, axioms gate, registry, differential oracle. One page each with the failure it targets.
4. Case study: the adversarial review and ordered repair; the correction of G9 coverage.
5. What the gates miss: contentless theorems found by the registry, coverage versus rule, prose claims.
6. Evaluation: gate firing history, mutation study, registry audit.
7. Related work and discussion: extraction versus differential testing; cost of maintenance.
8. Conclusion.

## Threats to validity and limits

- The model covers a small fragment. The review found roughly 600 lines of Lean against about twenty body forms and twenty expression nodes at the time; the model has grown (L0 is 784 lines now) but `formal/STATUS.md:36-76` still lists modelling limits per guarantee, and A3 and T1 to T3 have no theorem ("out of scope by kind", `formal/STATUS.md:63`, `:68`).
- Several oracle rows are, in the docs' own words, "the rule on the corpus, not the coverage of the checker's walk" (G9, G-RETAIN, G-SECRET rows, `formal/STATUS.md:56-76`). The agreement is over a finite corpus the project itself wrote.
- Registry rows state that witnesses exist and are named; the gate does not check that a witness instantiates a given theorem's hypotheses. That judgement is human.
- Two registered theorems are contentless. G5 still proves nothing about a `sneakyUndo`; the review marks it "A PARTIAL, NOT A FIX" (`docs/roadmap-archive/13-the-embeddable-compiler-revl-as-a.md:197`).
- The mutation evidence is one hand-picked mutation plus per-row flip witnesses. It is not a mutation-testing study.
- The status text corrected itself once ("all nine exit steps" over-claimed, 2026-10-07), which raises the question of what else overclaims; a sampled audit of registry rows would address it.
- CI is not a source of evidence here: the gate is run locally via `make formal` and the pre-merge script (exit code 77 means skipped, not passed; `formal/scripts/run_gate.sh:38-46`). No CI history is claimed.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 45 checked, 9 corrected.
