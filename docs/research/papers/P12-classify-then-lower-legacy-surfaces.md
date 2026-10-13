---
id: P12
title: Classify-then-Lower: Mapping Shell Commands and HTTP APIs onto Reversible Effects
theme: effects-replay
kind: short
maturity: partial
status: Shell classifier and lowering onto the witnessed filesystem catalog ship on the Python tier with tests, and the OpenAPI compensation routes ship; the touch-on-existing-file runtime split could not be found on main, and there is no real-traffic, differential or live-API measurement.
fused_with: P10
---

## Pitch

Give an untyped tool surface a pure, total, two-valued classifier that lowers only what its text shows to be a bare filesystem operation and sends everything else to one honest irreversible effect, so that the unknown case defaults to the safe direction.

## Abstract

Agent tool surfaces such as a shell tool and HTTP APIs are largely opaque: the host sees a string or a verb and must assume the worst, so every call needs approval. We describe classify-then-lower, a pattern where a pure, total function decides before execution whether a call is provably one of a small set of bare operations with known inverses, and if so lowers it onto a catalog of witnessed effects that carry real inverses, otherwise leaving it as a single emission. The design rests on one asymmetry: a false "emission" costs a prompt, a false "witnessed" silently auto-approves an irreversible effect, so every ambiguity resolves to emission. For shell, the classifier recognizes bare mv, rm, mkdir, cp and touch with no flags and no shell metacharacters, and lowers them onto move, rm, mkdir and write with unmove, unrm, rmdir_if_empty and restore. The touch case relies on a runtime split for an existing target that could not be found on main. On a hand-built corpus of 74 commands it lowers 21; real session traffic has not been measured. For HTTP, an OpenAPI importer treats RFC 9110 safe verbs as pure only as a declared claim, and offers per-endpoint compensating reversals (PUT restore from a GET preimage, DELETE recreate, POST delete-created, PATCH refused). A design review showed network reversal cannot be a proof-surface witness, because a witness inverse must be host-local and infallible, so the ceiling is compensate-grade on the audit surface. We report the negative result and what remains unmeasured.

## Problem and claim

An all-emission shell tool prompts on every command even though much agent traffic is filesystem edits in disguise (`backends/python/revl_shell_classify.py:1-8`). Weakening the default needs evidence. Shell text can carry that evidence only if the classifier refuses to interpret anything it cannot prove: any unquoted metacharacter, any flag, any unknown command, a wrong operand count (`backends/python/revl_shell_classify.py:51-82`).

Claim 1: the classifier is pure (no IO, no realpath, no glob, no env), total (never raises) and two-valued ("cannot classify" is a verdict, never a fall-through to witnessed). Confinement and existence are runtime concerns, enforced by the fs bodies it lowers onto.

Claim 2: the same discipline applies to HTTP, but the ceiling differs. A network reversal is fallible and non-local, so it is compensate-grade on the audit surface and never a witness (`docs/design/254-witnessed-network.md:10-60`). The most transferable finding is this negative result: the compiler's rule that a witnessed inverse may only call pure or acquire callees refuses an emitting reversal, and the two ways around it either hide the crossing from audit or regress.

## Contributions

1. A pure, total, two-valued shell classifier with an explicit lowering table and a documented refusal list (`backends/python/revl_shell_classify.py:237-341`; `stdlib/shell.rvl:92-151`).
2. An argument and tests that the classifier errs in the safe direction on a labelled corpus: a test asserts no emission-labelled command is classified witnessed (`tests/test_shell_witnessed_corpus.py:30`; `tools/shell_witnessed_corpus.py`).
3. End-to-end tests that a lowered command persists on commit and reverts on abort, and that an unclassified command registers nothing transactional (`tests/test_shell_witnessed.py:166-210`).
4. An OpenAPI import rule: emission unless the verb is safe by RFC 9110 or a declared human claim says otherwise; safe, idempotent and reversible are three separate claims, each stated in the generated header (`docs/import-openapi.md:58-160`).
5. Per-verb compensate routes with hard refusals for missing legs, a concurrency policy (`If-Match` or explicit best-effort-may-clobber) and a refusal of PATCH (`docs/import-openapi.md:162-245`; `tests/test_import_openapi_compensate_254.py`, `tests/test_import_openapi_compensate_slice2_254.py`, `tests/test_import_openapi_compensate_tiers_254.py`; 13 + 26 + 8 = 47 test functions).
6. A design negative result that network reversal cannot meet the witness bar (`docs/design/254-witnessed-network.md:15-60`).

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| ShellCheck, bashlex (citation to be checked) | Parse or lint shell to find bugs | Classifies for reversibility and refuses by default; no attempt to model shell semantics beyond a bare command |
| OpenAPI/Swagger codegen | Generates clients from specs | Derives an effect class per operation, labels it a claim, and attaches a typed reversal slot |
| Saga compensation for HTTP | Application-written compensating calls | Declared per endpoint with required legs and refusals, placed on a separate audit surface from proofs |
| Stripe idempotency keys | Server-side retry safety | revl treats idempotency as a delivery claim and says idempotent is not reversible (`docs/import-openapi.md:116-140` region) |
| Undo in IDE refactoring engines | Undo for a known edit set | The edit set is recovered from unstructured text, bounded by a refuse-first classifier |
| Rollback shells, container layer undo (citation to be checked) | Snapshot the filesystem around a command | Predicts reversibility before running and uses per-op witnesses instead of a snapshot |

## Evidence on main

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Classifier pure, total, two-valued | `backends/python/revl_shell_classify.py:10-27,237-341`; `tests/test_shell_witnessed.py:113` (`test_shell_classify_is_pure`) | shipped (py); ts present, untested here | a ts classifier exists at `backends/typescript/revl_shell_classify_ts.ts`, bound by `stdlib/shell.rvl:115-117` (`= @ts ref classify`) |
| Lowering table mv/rm/mkdir/cp/touch | `backends/python/revl_shell_classify.py:40-48`; `tests/test_shell_classify.py:67-115`; `tests/test_shell_witnessed.py:74-82` | shipped | names are checked against the fs catalog |
| Refusals: metachar, flags, expansion in double quotes, line continuation | `tests/test_shell_classify.py:164-407` (29 test functions in file) | shipped | includes a test that an expansion would run a different operand (`tests/test_shell_classify.py:211`) |
| touch splits at runtime | `backends/python/revl_shell_classify.py:332-336` (flag set), `backends/typescript/revl_shell_classify_ts.ts:315`; docs claim the split at `stdlib/shell.rvl:33-35` and the classifier docstring at `backends/python/revl_shell_classify.py:48-50` | unverified on main | the flag is set on both tiers, but no consumer of `create_only` was found in `backends/python/revl_shell_host.py`, `stdlib/shell.rvl` or `src/`. Until one is found, a touch of an existing file has no verified route to a prompt |
| Commit persists, abort reverts, fallback registers nothing | `tests/test_shell_witnessed.py:166`, `:190`, `:210` | shipped | |
| No emission label lowers, on a corpus | `tests/test_shell_witnessed_corpus.py:30` (`test_no_dangerous_false_witnessed`), `:25` (`test_every_corpus_label_matches`); `tools/shell_witnessed_corpus.py` | shipped (tests present; not re-run) | 74 labelled commands, hand built; this says nothing about commands outside the corpus |
| OpenAPI: emission unless safe or claimed | `docs/import-openapi.md:58-115`; `src/revl/import_openapi.py` | shipped | the claim is stored, not checked |
| Compensate routes PUT/DELETE/POST, PATCH refused | `docs/import-openapi.md:162-245`; the three compensate test files named above; `docs/design/254-witnessed-network.md:181-184` (slices 1 to 3 landed: slice 1 py, slices 2 to 3 incl. ts and rust tiers) | shipped | ceiling is compensate-grade |
| Witnessed network write as proof surface | `docs/design/254-witnessed-network.md:22-83`, `:593` | designed, withdrawn | the doc says slice 1 as first drafted "cannot compile" (`:41`) and the proof-surface form is superseded (`:83`); the future construct is not delivered |

## Numbers that exist

- Hand-built shell corpus: 74 commands, 21 labelled witnessed, 53 labelled emission, i.e. 28.4 percent (counted by grep of the `CORPUS` tuples in `tools/shell_witnessed_corpus.py`; the file was not executed and the tests were not run). The file itself says the real number "comes from real sessions" via a harness not yet wired and that the corpus is hand-built to mirror agent traffic.
- 29 test functions in `tests/test_shell_classify.py`, 7 in `tests/test_shell_witnessed.py`, 3 in the corpus test (function counts; several are parametrized, so case counts are higher and not measured here).
- 47 test functions across the three compensate test files (13 + 26 + 8 by grep; count only).
- No latency, prompt-reduction or user-study numbers exist.

## Paper outline

1. The asymmetry: false prompt versus false approval.
2. Classifier contract: pure, total, two-valued; the lowering table.
3. What it refuses and why (quotes, expansions, flags, continuations).
4. Runtime split for touch and the delegation of confinement to the fs bodies.
5. HTTP: safe, idempotent, reversible as three claims; per-verb routes; refusals.
6. The negative result: why a network witness cannot exist under host-local inverse rules.
7. Evaluation: corpus fraction, safe-direction test, real traffic (not yet run), differential shell test, spec corpus.
8. Related work and limits.

## Threats to validity and limits

- The classifier is an allowlist of five commands, not an exhaustive shell model. The evidence supports "total and conservative", not exhaustive coverage of shell.
- The 28.4 percent figure is on a corpus the authors wrote and labelled; it says nothing about real traffic. The tool file says as much.
- Safe-by-spec is "a claim, not a proof" (`docs/import-openapi.md:86-92`); a GET that writes is invisible. The doc also says "idempotence is not reversibility" and that no document proves either.
- Reversal over a network "is not un-observation"; webhook subscribers and side-effect emails persist (`docs/import-openapi.md:195-205` region).
- A concurrent PUT is clobbered unless the endpoint exposes an ETag; best-effort-may-clobber is a legal outcome.
- The classifier does not check the filesystem, so a lowered command can still fail at runtime or fall back; the lowering relies on the jail described in P11 for confinement.
- A PUT restore assumes the GET preimage is faithful; the generator's equivalence caveat names soft deletes and re-stamped ids (`src/revl/import_openapi.py:1390`).
- The touch-on-existing-file split has no verified runtime on main, so the touch lowering is not supported by shipped code until a consumer of `create_only` is found or written.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 22 checked, 6 corrected.
