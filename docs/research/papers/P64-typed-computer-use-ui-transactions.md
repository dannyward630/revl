---
id: P64
title: "Typed Computer Use: Capability Rungs, Five-Way Reversibility and Honest Non-Invertibility of UI Transactions"
theme: agents
kind: full
maturity: partial
status: Static classification, rungs, target binding, receipt, a failure-keyed compensation run and tier runtimes are on main with tests; there is no real GUI substrate, no end-to-end evaluation and no unconditional confirmation gate.
fused_with:
---

## Pitch

A GUI agent's reach becomes enumerable and its cleanup report truthful if each computer-use verb is an ordinary capability token whose fallback rung is part of the token and whose reversibility class is owned by the registry, with "unknown" treated as irreversible.

## Abstract

Computer-use agents act through screenshots and clicks, so their authority is described as "whatever the GUI permits" and their failures leave residue no tool reports honestly. We describe a design in revl, a language with a capability-typed effect boundary, in which computer-use verbs are ordinary capability tokens in a reserved, closed namespace. The existing authority surfaces (subset checks, the boundary audit, approval policy, taint classes) can read them without new machinery; the design doc notes that this was exercised on two of them (reach and policy selection) and only read on the approval gate and the rest. The fallback ladder from semantic target to selector to pixel is encoded in the token (`ui.click`, `ui.click.selector`, `ui.click.pixel`), so descending the ladder is a second call on a differently named capability, a component's admissible depth is a compile-time fact, and a component that reaches a pixel without the semantic verb is refused as a pixel driver with no ladder. Each verb carries one of five reversibility classes owned by the registry, with `unknown` handled as `irreversible`; a verb with no inverse may not declare one and a verb with an inverse must, both refused at declaration. A transaction over such steps computes a LIFO compensation run keyed on the failing step and reports a non-invertible step as `uncompensated` rather than clean. The postcondition verdict set deliberately has no plain `verified`. We report the registry, the refusal sets, the suites that pin them, a Lean model of the declaration rule, and a runtime that performs the compensation run on the python tier and, per the tier test files, four others. We state what is not shown: nothing is evaluated against a real screen, the order in which an agent loop walks the ladder is out of scope, and the confirmation gate depends on an operator writing a rule.

## Problem and claim

Existing GUI-agent work measures task success on benchmarks and bounds risk by sandboxing or human review. It does not give a program-level answer to three questions: what can this agent reach, what happens to the state it has touched when step three of five fails, and was the click it reports as done actually undone. `docs/design/532-typed-computer-use.md:43-66` states the first as a boundary problem (one token puts the whole desktop behind one audit line) and the second as an input problem (a screen is attacker-influenced content). `docs/design/553-ui-transaction-phases.md:40-76` measures a residue report that used one word, `bare`, for a read, for a click that has no inverse, and for a step whose inverse nobody wrote.

The claim: classification plus refusals, not a new transaction construct, is enough to keep these reports honest. Concretely: (1) rung-in-token makes admissible depth a property of the declaration; (2) a registry-owned five-way class with `unknown` joined to `irreversible` prevents a false cleanliness claim; (3) a failure-keyed LIFO run and a five-state residue split say what was restored, what was only compensated and what could not be.

The paper does not claim that an agent loop tries rung 0 first (`docs/design/532-typed-computer-use.md:280-286` says revl bounds reach, not order), does not claim a click hit the intended control, and does not claim any productivity or accuracy result.

## Contributions

1. A closed `Ui` verb registry (`screen.observe`, `ui.find`, `ui.click`, `ui.text`, `ui.download`) in a reserved namespace with no coordinate primitive and no generic `ui.act`, so the existing capability surfaces apply unchanged (`src/revl/ui_family.py:52-122`; `docs/design/532-typed-computer-use.md:67-131`).
2. Rung-in-token ladder: `ui.<verb>.selector` and `.pixel`, a fourth level refused, and a per-component prefix-closure check over the audit reach (`src/revl/ui_family.py:124-220`; `docs/design/532-typed-computer-use.md:184-278`; `tests/test_ui_ladder_rungs_521.py`).
3. A five-way reversibility class owned by the registry, total over admissible spellings (including rungs, which inherit their verb's class), with `unknown` and `irreversible` joined as `NO_INVERSE` (`src/revl/ui_family.py:351-400`; `tests/test_ui_transaction_classification_522.py`).
4. Two declaration refusals under G4: a no-inverse verb may not declare `compensate`, a compensatable verb must (`docs/design/538-ui-transactions.md:197-247`), with a Lean model of the rule (`formal/STATUS.md:64`).
5. A five-state residue split (`untouched`, `restored`, `compensated`, `uncompensated`, `unregistered`) with the weakest part as aggregate, and `compensation_run(steps, failed_at)` computing the LIFO run keyed on the failing step (`src/revl/ui_transaction.py:264-300, 441-523`; `tests/test_ui_transaction_run_1369.py:154-176`).
6. A postcondition verdict set with no plain `verified`, with a read bound to its step by target provenance (`src/revl/ui_transaction.py:694`; `docs/design/553-ui-transaction-phases.md:223-252`; `tests/test_ui_transaction_phases_522.py:465`).

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Commercial computer-use agent APIs (citation to be checked) | Let a model drive a desktop or browser through screenshots and input events | The reach is declared as capability tokens in the program and audited before running; there is no coordinate primitive in the language (532:67-131). |
| Benchmarks: WebArena, OSWorld, Mind2Web (citation to be checked) | Measure task success of agents on web and desktop tasks | Not a benchmark. Specifies a static contract on what a program may reach and how failures are reported; no success rate is claimed. |
| Accessibility APIs (UIA, AXUIElement), Selenium, Playwright, Sikuli (citation to be checked) | Offer semantic, selector and image-based targeting | Treats the three targeting styles as three capability rungs with different failure directions: rung 0 fails closed, rungs 1 and 2 hit something (532:172-182). |
| Sagas and compensating transactions (Garcia-Molina and Salem) (citation to be checked) | Run compensations in reverse order after a failure | Compensation exists only where the registry says an inverse exists; irreversible and unknown steps report `uncompensated`, and a declared `compensate` on them is refused (538:197-247). |
| Effect systems and reversible computing (citation to be checked) | Track effects or require inverses | Class is assigned to host verbs the language cannot see inside, by a registry the author cannot lower (538:105-121). |
| Prompt-injection defences via taint tracking (citation to be checked) | Mark untrusted inputs | `screen` is a source class and `ui` a sink class derived from the granting side (532:288-310; `tests/test_ui_taint_classes_521.py`). |

## Evidence on main

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Reserved closed namespace, unscoped verbs refused under G8 | `src/revl/ui_family.py:52-122, 240`; `tests/test_ui_capability_namespace_521.py` (15 test functions; doc says 20 tests) | shipped | Count difference is from parametrization |
| Audit enumerates reached UI tokens with no new reporting code | `docs/design/532-typed-computer-use.md:378-411` | shipped | Cardinality reads UNBOUNDED |
| Rungs in token, prefix-closure, fourth level refused | `src/revl/ui_family.py:124-220`; `docs/design/532-typed-computer-use.md:227-278`; `tests/test_ui_ladder_rungs_521.py` (25; doc says 26) | shipped | Run-time order not claimed |
| A rung inherits its verb's reversibility class and taint role | `src/revl/ui_family.py:382-399`; `docs/design/532-typed-computer-use.md:574` (slice 3 paragraph) | shipped | |
| Taint: `screen` source, `ui` sink | `docs/design/532-typed-computer-use.md:288-377, 529-545`; `tests/test_ui_taint_classes_521.py` (21; doc says 20) | shipped | Derived classes are profile-gated on `taint_strict` (532:523-541) |
| `UiTarget` value with registry-owned fields; targets must originate in a producing crossing | `src/revl/ui_family.py:615-730`; `docs/design/565-ui-target-binding.md`; `tests/test_ui_target_binding_521.py`, `tests/test_ui_target_provenance_1371.py` | shipped | Does not check field values (532:597-622) |
| UI action receipt, four outcomes incl. `unresolved` | `src/revl/ui_action.py`; `tests/test_ui_action_receipt_521.py` | shipped (module) | Unsigned; no surface emits a receipt yet (532:624-650) |
| Five classes, total over spellings, `unknown` treated as irreversible | `src/revl/ui_family.py:351-380`; `tests/test_ui_transaction_classification_522.py` | shipped | `confirm-required` has no verb born in it (538:248-265) |
| R1/R2 declaration refusals under G4 | `docs/design/538-ui-transactions.md:197-247` | shipped | |
| Lean model of A5 (compensation accompanies emission) at every declared computer-use token | `formal/STATUS.md:64`; `formal/RevL/Theorems/A5_CompensationAccompaniesEmission.lean` | partial | Row notes it does not model scope/session caveats or the witnessed/irreversible classes' own rules |
| Five residue states, weakest-part aggregate | `src/revl/ui_transaction.py:225, 264-300`; `docs/design/553-ui-transaction-phases.md:78-97` | shipped | `unregistered` unreachable from an admitted program (553:424) |
| Phase eligibility table | `src/revl/ui_transaction.py:193-210` | shipped | A static reading; no phase executes in the table |
| LIFO compensation run keyed on failure; five-step oracle | `src/revl/ui_transaction.py:441-523`; `tests/test_ui_transaction_run_1369.py:154-176` | shipped | Control `compensateOrder` is not failure-keyed |
| The run is performed at runtime on the python tier, and mirrored on ts, go, rust, java | `docs/design/538-ui-transactions.md:397-580`; `tests/test_ui_transaction_runtime_1369.py` (13); `backends/rust/test_ui_transaction_rust_1369.py`; `backends/java/test_ui_transaction_java_1369.py`; `backends/typescript/tests/ui_transaction.test.ts`; `backends/go/scenarios/emitted/ui_transaction/exec_test.go` | shipped (per tier) | 538:518-580 says the ts, go, rust and java tiers run the unit, and their test files exist; 538:546 has a stale "the other four tiers have no unit yet", and 538:654-655 says only python executes. The doc contradicts itself. No backend test was run for this draft |
| Operator-side confirmation via `capability ui.click requires approval` in `revl audit --policy` | `docs/design/538-ui-transactions.md:378-396`; `tests/test_ui_transaction_phases_522.py` | shipped | Absence of a rule is silence (538:631-637) |
| Flagship integrated demo | `docs/design/551-flagship-demo.md:30-75`; `tests/test_flagship_demo_525.py` (8 test functions) | partial | Doc: ten steps, 46 assertions; it names the pieces it cannot show |
| Real GUI substrate, handle resolution, check-to-use race closure | `docs/design/538-ui-transactions.md:627-674` | designed, not built | Open |

## Numbers that exist

- 5 verbs, 5 classes, 3 rungs (0, 1, 2), 5 residue states (`src/revl/ui_family.py:57, 351-358, 124`; `src/revl/ui_transaction.py`).
- Test function counts by `def test_` on main: 15, 25, 21, 33, 20, 15, 41, 17, 13, 12, 25, 16, 4 across the ui test files (`tests/test_ui_*.py`), 8 for the flagship demo. These count tests, not users or tasks.
- Non-vacuity measurements quoted in the docs, against named older commits: slice 1, 7 failed and 13 passed without the parser hook; slice 2, 16 of 20 failed; slices 3 and 4 as in `docs/design/532-typed-computer-use.md:506-640` (sample is the suite).
- Five-step oracle: failure at step 3 runs steps 2 and 1 in that order; steps 4 and 5 are `untouched` (`tests/test_ui_transaction_run_1369.py:154-176`).
- Measured false word: an earlier demo's erase report listed 7 crossings as 1 compensated and 6 bare, where the 6 included a read (`docs/design/553-ui-transaction-phases.md:40-76`).
- Flagship demo: 10 steps, 46 assertions (`docs/design/551-flagship-demo.md:30-34`).
- No task success rate, latency, false-refusal rate, user-study or real-application number exists.

## Paper outline

1. Introduction: unbounded reach and dishonest cleanup in computer-use agents.
2. Threat model: attacker-influenced screens, spoofable accessibility metadata, a substrate outside the language.
3. Computer use as capabilities: the registry, the namespace, no coordinate primitive, audit for free.
4. The ladder in the token: failure directions per rung, prefix closure, what is not claimed about order.
5. Reversibility classes: registry ownership, `unknown` equals `irreversible`, refusals R1 and R2.
6. Transactions as classification: eligibility table, five residue states, failure-keyed LIFO run, runtime on several tiers.
7. Postconditions and targets: no plain `verified`, `UiTarget` binding and provenance, the receipt.
8. Evaluation: suites, non-vacuity runs, Lean A5 row, flagship demo, plus a substrate study still to be done.
9. Related work, limits, discussion.

## Threats to validity and limits

- `docs/design/532-typed-computer-use.md:665-694` section 12: the audit enumerates declared tokens, it cannot verify a host body reaches only the boundary its declaration names; the claim that every authority surface reads a UI verb "for free" was exercised on two surfaces (G8 reach, policy selection) and only read on the approval gate, `secret K for C` and the partial order.
- `docs/design/538-ui-transactions.md:627-674`: nothing stops a click no operator rule covers; the check-to-use race is open (a `UiTarget` is carried by value, not a resolved handle); only `compensate` executes; a step with no bound postcondition starts no run; class assignments are judgements, "a finer answer needs a finer verb".
- `docs/design/553-ui-transaction-phases.md:400-440`: the plan reads one method body and does not follow a callee; `unregistered` is unreachable from an admitted program.
- The strongest postcondition word is `verified-against-untrusted-read`. It raises confidence and establishes nothing about the business effect.
- The UI action receipt is unsigned, and no revl surface emits one yet (`docs/design/532-typed-computer-use.md`, slice 5 paragraph).
- All evidence is author-written tests and design docs. There is no independent evaluation and no real GUI under test.
- Claims above about tiers rest on documents and test names; no test was run for this draft.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 17 checked, 3 corrected.
