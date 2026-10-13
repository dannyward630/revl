---
id: P52
title: Refuse Rather Than Guess: Importing WIT, OpenAPI, MCP, Cordis and A2A Surfaces as Emission-by-Default Services
theme: compiler
kind: tool-demo
maturity: shipped-evidence
status: Five importers and an export direction are on main with about 250 tests and two executed generator-injection fixes; no corpus-scale evaluation and no measured error rate for the weakening rules.
fused_with:
---

## Pitch
A foreign interface description says nothing about whether an operation can be undone, so an importer that wants a sound effect audit must default every operation to "irreversible", weaken that only on a written positive claim, refuse any signature it would have to guess, and treat its own generated text as an attack surface.

## Abstract
Language bindings and client generators turn an interface description (WIT, OpenAPI, an MCP tool list, an untyped TypeScript plugin, an A2A Agent Card) into typed stubs. They transcribe shapes, but a shape does not say whether a call is read-only, retryable or reversible, and a generator that silently fills the gap makes every later effect audit unsound. We describe five importers in the revl compiler that share one rule: every imported operation is declared `emission` (crosses the system boundary irreversibly) unless a written positive claim says otherwise: an author or engineer assertion written in the generated source next to the operation or, for OpenAPI, a safe HTTP method under RFC 9110. Because a service declaration bounds what its providers may do, the compiler rejects a plain operation backed by an emission extern, so a weakened operation cannot call an emission extern, although the check cannot make a false author claim true. Constructs the importer cannot map faithfully (WIT streams, OpenAPI `allOf`, untyped TypeScript parameters, gRPC) are refused by name with a pointer and a way forward; the Cordis importer's `--mark-unrecovered` mode makes gaps loud instead of fatal. Results from an A2A peer are returned as `Untrusted`, and reach is bounded by endpoint host alone. Treating the generator as an attack surface found two defects in the OpenAPI importer: a newline in document text ended a comment and injected a compiled host-code extern, and a URL credential became a capability token and leaked into the compiled IR. Both are fixed and covered by tests (4 and 11 respectively). The importers total about 6000 lines with about 250 test functions.

## Problem and claim
Existing generators (OpenAPI Generator, wit-bindgen, protobuf and gRPC codegen, MCP client wrappers) are judged on whether the output compiles and round-trips data. They do not answer a second question that matters once the output sits inside a system with an effect audit: what does the generator assert about side effects that the source interface never stated? A generated client for `GET /logout` or `delete-everything: func()` is indistinguishable, at the type level, from one that reads.

The claim: the sound default for an imported operation is the pessimistic one, and the weakening rules can be made small, explicit and auditable. The compiler, not the generator, enforces the pairing between a plain operation and a pure extern. Failure to recover a signature must stop or be marked, never be filled in. The generator's own output is untrusted-input-derived code and needs the same discipline as any template engine.

This is a tool and design paper, not a soundness proof. The claim is bounded by what the docs say: "Safe-by-spec is a claim, not a proof" (`docs/import-openapi.md` section 1).

## Contributions
1. One import rule across five interface languages (WIT, OpenAPI, MCP tool lists, Cordis TS plugins, A2A Agent Cards): service plus extern plus provider, operations default to `emission`, weakening needs a written positive claim (or, for OpenAPI, a safe HTTP method), an unmatched override is an error.
2. A graded evidence table for weakening: a WIT `/// @revl:pure` comment by the interface author or a `--pure` flag by the importing engineer (WIT), a purpose-built author assertion (MCP `readOnlyHint`), the HTTP method under RFC 9110 (OpenAPI), JSDoc `@revl:pure` (Cordis), with strengthening taking one voice and weakening taking unanimity.
3. Refuse-by-name tables for unmappable constructs, with JSON pointer or line and a remedy, plus `--mark-unrecovered` (Cordis) for the untyped-source case.
4. Two generator-injection findings with executed reproducers and fixes: comment-ending newline injecting a compiled extern; URL userinfo becoming a capability token and reaching the IR.
5. The A2A binding: card as a claim, results `Untrusted`, host-only reach bound, exact version claim, no inverse synthesised, Task lifecycle as a four-operation projection with shape-gated replies.
6. Export in the other direction (WIT, client, OpenAPI), so a revl composition can publish the typed surface it consumes.

## Related work
| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| OpenAPI Generator, openapi-typescript | Generates clients from specs; `allOf` is merged by policy | Refuses `allOf`, `anyOf`, untagged `oneOf`, free-form objects by name; no merge policy invented (`docs/import-openapi.md` section 5) |
| wit-bindgen, jco | Generates bindings for the component model | Adds an effect classification the WIT does not carry; refuses `stream<T>`, `future<T>`, `tuple`, callbacks by name (`src/revl/import_wit.py:104-116`) |
| MCP SDK client wrappers | Expose tools as callable functions; annotations pass through as hints | Only explicit `readOnlyHint: true` avoids emission; an absent annotation is not a claim (`docs/mcp-bridge.md` section 2; `src/revl/mcp/schema.py:766-775`) |
| gRPC and protobuf codegen, SWIG | Cross-language stubs from a schema | Same transcription goal; revl adds an upper-bound effect declaration enforced by the compiler against the provider |
| Cordis plugin typing | Types plugin services in TypeScript | revl reads the plugin surface into a service and refuses parameters with no recoverable type rather than defaulting to `any` |
| A2A Agent Card and SDKs | Describe and call remote agents | Treats the card as a claim, refuses unknown versions and gRPC, tags results `Untrusted`, binds reach to host only |
| Generator security research (template injection in codegen, supply-chain issues in code generators) (citation to be checked) | Treats the input spec as data | Shows the spec as code-injection input into a language whose comments run to the newline, and reports the fix |

## Evidence on main
| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Family shape and rule: every imported op is `emission` unless a positive claim | `docs/import-wit.md:1-95`; `docs/import-openapi.md:58-115`; `docs/import-cordis.md:71-95`; `docs/mcp-bridge.md:131-150` | shipped | Rule restated in each doc |
| Compiler rejects plain op backed by emission extern (WIT) | `tests/test_import_wit.py:244` `test_a_plain_operation_backed_by_an_emission_is_rejected` | shipped | |
| Same for OpenAPI, Cordis | `tests/test_import_openapi.py:320` `test_a_plain_operation_backed_by_an_emission_is_rejected`; `tests/test_import_cordis.py:524` `test_a_plain_op_backed_by_emission_is_rejected` | shipped | Test names confirmed present (test bodies not run) |
| An override matching nothing is an error | `tests/test_import_wit.py:236` `test_a_pure_assertion_that_matches_nothing_is_an_error`; `docs/import-openapi.md:128-132` | shipped | |
| WIT streams, futures, tuples, callbacks refused by name | `src/revl/import_wit.py:104-116`; `tests/test_import_wit.py:331` (nested options), `:393` (CLI refusal) | shipped | |
| WIT component edge is a second, narrower boundary | `docs/import-wit.md:223-250`; `backends/wasm/canonical.py:323` (`can_lower_param`) | shipped | The doc marks it a described boundary |
| OpenAPI: safe verbs weaken, PUT/DELETE become `emission idempotent`, others bare `emission` | `docs/import-openapi.md:58-115`; `src/revl/import_openapi.py:81` | shipped | So "emission by default" is accurate only after the safe-verb rule |
| OpenAPI compensate-grade reversal slot | `docs/import-openapi.md:162-245`; `tests/test_import_openapi_compensate_254.py` (13), slice2 (26), tiers (8) | shipped | Documented ceiling: audit surface, best-effort, "restores server state only" |
| OpenAPI refusal table | `docs/import-openapi.md:359-402` | shipped | |
| Cordis refusals and `--mark-unrecovered` | `docs/import-cordis.md:232-271`; `src/revl/import_cordis.py:26`, `:1185`; `tests/test_import_cordis.py:542`, `:554` | shipped | |
| Newline injection in OpenAPI document text; fix `_comment_safe` | `docs/v2.0-roadmap.md:1568`; `src/revl/_doc_text.py:17`; `tests/test_import_openapi_injection_416f.py:80`, `:98`, `:106`, `:114` | shipped | Executed reproducer: injected `@py` extern ran on first `revl run` |
| URL credential became capability token and leaked into IR; fix | `docs/v2.0-roadmap.md:1585`; `src/revl/import_openapi.py:217` (`_authority_split`), `:250` (`_redact_userinfo`), `:1344` (`_net_cap`); `tests/test_import_openapi_url_credential_421_f4.py:82-172` | shipped | Collision: `https://admin:pw1@bank.example.com` and `https://admin:pw2@attacker.example.net` gave the same token `net.admin` |
| A2A card: version claim exact, gRPC refused, plaintext refused, redirect refused at run time | `docs/import-a2a.md:21-72`, `:213-250`, `:272-293`; `src/revl/import_a2a.py` | shipped | |
| A2A results are `Untrusted[Str]`; checker refuses authority-sink flow | `docs/import-a2a.md:35-48`; `tests/test_import_a2a.py:132`, `:138` | shipped | |
| A2A remote call has no inverse; every op `emission` | `docs/import-a2a.md:73-119` | shipped | A remote call outside the teardown guarantee is a stated boundary |
| A2A Task lifecycle: four-op projection, stream-shaped | `docs/design/439-a2a-task-lifecycle.md:1-40`; `src/revl/a2a_task.py:1-40`; `CHANGELOG.md:319-323` | shipped | `docs/import-a2a.md:257` still says the lifecycle is "not answered here"; the design note and the code answer it. Stale doc text |
| Shape-gated replies | `src/revl/a2a_boundary.py:292` (`py_result_gate`), `:331` (`py_task_status_gate`), `:350` (`py_task_parts_gate`), `:413` (`py_task_identity_gate`) | shipped | Function names confirmed at these lines; the gates were not run |
| Export family (WIT, client, OpenAPI) | `src/revl/cli/parser.py:1415`; `src/revl/export_wit.py`; `src/revl/export_client.py`; `src/revl/export_openapi.py` | shipped | Not examined beyond existence and size |
| MCP import trusts only an explicit read-only claim | `src/revl/mcp/schema.py:766` (`import_tools`), `:772-775`; `tests/test_mcp.py:182` | shipped | |
| Test counts | `tests/test_import_wit.py` (28 test functions), `tests/test_import_cordis.py` (39), `tests/test_import_openapi*.py` (56+13+26+8+4+11=118), `tests/test_import_a2a.py` (71) | shipped | Counted by `def test_` per file |

## Numbers that exist
- Source size: `src/revl/import_wit.py` 1058 lines, `src/revl/import_openapi.py` 1964, `src/revl/import_cordis.py` 1474, `src/revl/import_a2a.py` 1480, plus `src/revl/a2a_boundary.py` 526 and `src/revl/a2a_task.py` 325 (`wc -l` at 45bec431f).
- Test function counts above (def-level, not parametrised cases).
- Injection test: 5 vectors per the roadmap entry (`docs/v2.0-roadmap.md:1568`), 4 test functions (one is parametrised, `label`); URL credential: 11 tests.
- No measurements of import coverage on real-world specs exist. No count of how many public OpenAPI documents are refused (the doc itself says `allOf` "will bite most often").
- No user study and no false-refusal rate.

## Paper outline
1. Motivation: two operations that look the same to a schema.
2. The family rule and the evidence ladder (table).
3. Why the weakened form is still sound: the compiler check, with the rejection message.
4. Refusal tables and `--mark-unrecovered`.
5. The generator as an attack surface: the two findings.
6. A2A: a card as a claim; taint, reach, version, Task lifecycle.
7. Export direction and round-trip.
8. Evaluation (to be done): coverage, false-weakening rate, fuzz.
9. Limits and related work.

## Threats to validity and limits
- Weakening rests on human or author claims the compiler cannot verify. A `GET` that writes remains a lie, "with a verb, a path and an author attached" (`docs/import-openapi.md:155-160`). The result is not verified.
- Idempotent is not reversible: PUT and DELETE are `emission idempotent`, still irreversible for the reversal guarantee.
- The compensate-grade claim is a ceiling: audit surface only, best-effort, and does not undo observation (`docs/import-openapi.md:196-205`).
- A2A: "There is no verified remote badge" (`docs/import-a2a.md:62-72`). `Untrusted` bounds what flows to authority sinks locally; it does not make the peer trustworthy. The remote call is not part of the teardown guarantee, and the docs say so.
- A2A streaming, push notifications, non-text modalities and the `remote` row failure semantics are listed as not projected (`docs/import-a2a.md:252-270`). The Task lifecycle is projected as four operations in code; whether that is complete for real peers is untested.
- The injection findings are from internal audits of the importer; no external adversary study. The audit itself lists other surfaces as unexamined at the time (`docs/v2.0-roadmap.md:1568`): non-py bridge/seam crossings and Python `repr()` injection.
- The type mapping is lossy in places the docs admit: `u64` above 2^63-1 does not survive; WIT `char` widens to `Str`.
- The importers and the checking compiler are one project; "the compiler enforces the pairing" only means as much as the checker's effect propagation, including its documented name-based limits (`docs/mcp-bridge.md` section 1: emissions hidden behind function values are treated as may-emit).

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 32 checked, 10 corrected.
