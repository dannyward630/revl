---
id: P06
title: "Effect-Tracked Reactive Streams: Subscriptions as Acquire/Undo Resources With Declared Backpressure"
theme: formal-pl
kind: short
maturity: partial
status: "The v1 stream surface is on main with executed scenario tests on py and, where the toolchain is present, ts, go, java (against a stub API) and rust; durable replay is py only, and no external-workload evaluation or mechanization exists."
fused_with:
---

## Pitch

A subscription is just another acquire/undo resource, so the teardown machinery that already closes files and sockets closes streams too. A compile-time rule plus a cancellation-first `next` make that closure reachable when the provider dies silently, provided the host `close` delivers a terminal (the rule is syntactic).

## Abstract

Reactive stream libraries leave the lifetime of a subscription to convention: the consumer must remember to cancel, a parked consumer can outlive a provider that vanished without a terminal signal, and buffer policy is a runtime configuration. We describe `Stream[T, State]` in revl, an effect-checked language that compiles to six runtimes. A subscription is an `acquire`/`undo` bracket on the owner activation's single LIFO disposer stack, so unloading the owner closes the stream with no stream-specific teardown path. The design review found one critical failure of that argument: a consumer parked in `next` on a silently dead provider makes the bracket inverse unreachable, which deadlocks teardown on the blocking tiers and leaks a fiber on the event-loop tiers. The fix has two parts: `close` is cancellation-first (the park is a race between the next item and the subscription's cancel token), and a compile-time rule refuses any stream source whose declared inverse does not syntactically close it, so provider death is meant to be a terminal event rather than silence; the rule cannot see what a host provider does. Backpressure is a declared policy over a bounded buffer with `error` as the default. The surface covers `map`/`filter`/`take`, `merge`, `every x in sub`, typed events with a dedup window, provider-declared replay and a durable cursor. The test file `tests/test_stream_reactive.py` has 197 test functions, and an exit table requires each of ten stream surfaces on each of six tiers to either lower or refuse by name (a lowering cell checks only that the emitted code contains `Stream`; a refusal cell checks the refusal text). We state the limits: rule 3.6 is syntactic, durable replay exists only on the reference tier, and no external workload has been run.

## Problem and claim

In Reactive Streams, Rx, Akka Streams and Kotlin Flow, a subscription is a first-class runtime object whose cancellation is the consumer's duty. Three failures follow in practice: a forgotten cancel leaks the subscription; a provider that dies without signalling leaves the consumer parked forever; and an unbounded or silently dropping buffer loses data without a trace. These are lifetime and liveness properties, which an effect-checked language with checked teardown should be able to state.

The claim is the design's own core guarantee: "Every admitted stream subscription has an explicit cancellation path, and unloading its owner CLOSES the stream before the owner disappears" (`docs/design/130-stream-reactive-types.md:43-62`). It holds by reuse: the subscription is a `bracket` entry on the owner's LIFO stack, so the existing clean-unload and abort replay run `close`. The work is in showing the inverse is reachable on the admitted shapes and refusing the shapes where it would not be; rule 3.6 covers only the syntactic shape.

The second claim is about completeness across targets. For each stream surface and each of the six tiers, the answer is one of two things, the tier lowers it or refuses it by name, and silence counts as failure (`tests/test_stream_reactive.py:3267-3272`).

## Contributions

1. `Stream[T, State]` with `subscribe ... undo`, `next`, `close`, and state index `Created/Active/Paused/Closed`, where the subscription is a linear bracket (`docs/design/130-stream-reactive-types.md:64-140`, `:166-211`).
2. The reachability argument and its two-part fix: cancellation-first `next` and the no-silent-vanish admission rule 3.6 (`docs/design/130-stream-reactive-types.md:830-905`; `src/revl/lower.py:11696-11709`; `backends/python/runtime.py:6917-6962`).
3. Declared backpressure over a bounded buffer, four policies, `error` default, and a rule that a `block` pause must not spend a `take(n)` budget (`docs/design/130-stream-reactive-types.md:255-312`; `backends/python/tests/test_stream_runtime.py::test_a_block_pause_does_not_spend_the_take_budget`).
4. A six-tier lowering: event-loop tiers race a queue against a cancel future, blocking tiers select on item and cancel signals, wasm refuses by design (`docs/design/130-stream-reactive-types.md:413-455`).
5. A closed exit table, 10 surfaces by 6 tiers, in which every cell lowers or refuses by name. A refusing cell is checked for the surface name; a lowering cell is checked only for the substring `Stream` in the emitted code (`tests/test_stream_reactive.py:3364-3403`).
6. Typed events as a specialization of `Stream[T]` with a schema contract and a bounded dedup window, so one set of teardown properties covers both (`docs/design/130-stream-reactive-types.md:584-608`).
7. Provider-declared replay and a durable cursor on the reference tier, with a fresh-process resume test and a cursor-free control (`backends/python/tests/test_stream_runtime.py::test_a_crashed_consumer_resumes_from_its_durable_cursor_in_a_fresh_process`, `::test_the_same_program_without_the_cursor_loses_the_outage`).

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Reactive Streams specification and RxJava (Rx) (citation to be checked) | Standard `Subscription` with `request(n)` and `cancel()`; backpressure by demand | Cancellation is not the consumer's duty: the checker refuses a `subscribe` with no `undo`, and teardown runs the inverse |
| Akka Streams | Materialized graphs, supervision strategies, backpressure by demand | revl has no graph DSL; single consumer, linear subscription, no implicit multicast (`docs/design/130-stream-reactive-types.md:217-225`) |
| Kotlin Flow and structured concurrency | Cancellation propagates through scope; flows are cold | Same cancellation-first spirit; here it is a checked admission rule and a cross-tier protocol, and `close` is infallible and non-emitting by rule 3.4 |
| Rust async streams (`futures::Stream`) | Cancellation by dropping the future | Dropping is implicit; revl makes the inverse an explicit registered entry that the WAL can describe |
| Elm subscriptions, FRP (Elliott and Hudak) (citation to be checked) | Declarative subscription as a function of model | Different goal: revl models acquisition and release effects, not the dataflow semantics; the design doc says "do not start with a general reactive calculus" (`docs/design/130-stream-reactive-types.md:34-38`) |
| Erlang monitors and `DOWN` messages | Provider death is delivered to the monitor as a message | Closest precedent for "provider death is a terminal event". revl obtains it by a compile-time rule on the source's inverse rather than a runtime monitor |
| Session types and linear types for resources (Rust ownership, linear Haskell) (citation to be checked) | Use-after-close and double-use refused | The `State` index and rule 3.1 do this for subscriptions, with a bounded state set |

The novelty claim is made at the level of the unified account (stream lifetime is not a new mechanism, the one reachability hole and its fix, the closed per-tier exit table), not at the level of any single feature. Bounded buffers and cancel tokens are standard.

## Evidence on main

| Claim | Where | Status | Note |
|---|---|---|---|
| Subscription is a bracket with additive IR keys | `tests/test_stream_reactive.py::test_subscribe_lowers_to_a_bracket_step_with_additive_keys` (`:69`) | shipped | |
| Stream-free programs unchanged | `tests/test_stream_reactive.py::test_non_stream_program_is_byte_identical` (`:88`), `::test_a_stream_free_program_is_byte_identical` (`:3045`) | shipped | |
| Rule 3.2: `subscribe` needs `undo` | `tests/test_stream_reactive.py::test_rule_3_2_subscribe_needs_undo` (`:105`) | shipped | |
| Rule 3.1: single consumer | `tests/test_stream_reactive.py::test_rule_3_1_single_consumer_refuses_a_second_subscribe` (`:115`) | shipped | |
| Rule 3.6: no-silent-vanish | `src/revl/lower.py:11696-11709`; `tests/test_stream_reactive.py:127-215` (four refusal tests: a source inverse that closes a sibling, and subscription inverses that close nothing, close the source, or close a sibling; plus one admit control) | shipped, syntactic | Checks that the source's inverse closes the source; it cannot see what a host provider does |
| Rule 3.4: `next` not in teardown | `tests/test_stream_reactive.py::test_rule_3_4_teardown_may_not_suspend_on_next` (`:141`) | shipped | |
| Cancellation-first `next` | `backends/python/runtime.py:6917-6962`; `backends/python/tests/test_stream_runtime.py::test_cancel_reaches_a_parked_next` (`:184`) | shipped (py) | |
| Provider death is terminal | `backends/python/tests/test_stream_runtime.py::test_provider_death_is_a_terminal` (`:211`) | shipped (py) | |
| Unload closes the stream, LIFO | `backends/python/tests/test_stream_runtime.py::test_unload_closes_the_stream_lifo` (`:149`) | shipped (py) | |
| Chain closes and cancels through combinators | `backends/python/tests/test_stream_runtime.py::test_unload_closes_the_whole_chain_lifo`, `::test_cancel_reaches_a_next_parked_behind_a_filter` | shipped (py) | |
| Four backpressure policies, default `error` | `tests/test_stream_reactive.py::test_every_declared_policy_lowers`, `::test_error_is_the_default_policy_and_the_defaults_stay_absent`; runtime `::test_backpressure_error_default_faults_on_overflow` and the `drop_newest` test beside it | shipped | |
| ts runtime executes | `backends/typescript/test_stream_ts.py` (3 tests) | shipped; skips without node | |
| go runtime executes | `backends/go/test_stream_exec_130.py::test_go_stream_scenario_builds_and_runs` (`:233`) | shipped; skips without a go toolchain | |
| java runtime executes | `backends/java/test_stream_exec_java_130.py` (12 tests), scenarios `stream_130.rvl`, `stream_event_130.rvl` | shipped; skips without a JDK | Against a stub cordis4j API per the file docstring |
| rust runtime executes | `backends/rust/test_emit_rust.py:3786-3806` (asserts "24 passed" from `cargo test`), `backends/rust/scenarios/stream.rs` | shipped; needs cargo | |
| wasm refuses by design | `tests/test_stream_reactive.py::test_wasm_refuses_a_stream_program_with_an_honest_emit_error` (`:268`); `backends/wasm/emit.py:1056` | shipped | |
| Exit table: 10 surfaces x 6 tiers | `tests/test_stream_reactive.py:3364-3403` | shipped | The table has ten surfaces because replay splits into last-n and durable cursor (`:3270-3274`). Lowering cells assert only that the emitted code contains `Stream`. |
| `every x in sub` | `tests/test_stream_reactive.py:1596-1890`; runtime `::test_every_in_delivers_each_item_to_the_body_and_ends_on_the_terminal` | shipped | An acquisition in the body is refused: unbounded stack |
| Typed events, dedup window, schema fault closes subscription | `backends/python/tests/test_stream_runtime.py::test_a_conforming_item_reaches_the_body_and_a_duplicate_is_collapsed`, `::test_a_schema_violation_faults_the_handler_and_closes_the_subscription` | shipped (py exec; shape tests on ts/go/rust/java) | |
| Last-n replay on py, ts, go, java; rust refuses by name | exit table `_EXIT_REFUSALS` (`tests/test_stream_reactive.py:3333-3352`) | shipped | The rust refusal is pending a gate-crate regeneration (comment at `:3346-3348`) |
| Durable cursor, fresh-process resume | `backends/python/tests/test_stream_runtime.py:1723`, control `:1779` | shipped (py only) | Other tiers refuse by name |
| Required `Stream[T]` coeffect | `tests/test_stream_reactive.py:3045-3260`; py only | shipped (py only) | Refused by name elsewhere |
| Roadmap status | `docs/v2.0-roadmap.md:1374` marks the stream item partial with slices 1-5 landed | consistent with this draft | The design doc header is current (`docs/design/130-stream-reactive-types.md:3`) |

## Numbers that exist

- 197 test functions in `tests/test_stream_reactive.py` (static count of `def test_`; parametrized cases multiply this).
- 56 test functions in `backends/python/tests/test_stream_runtime.py`; 14 in `backends/go/test_stream_exec_130.py`; 12 in `backends/java/test_stream_exec_java_130.py`; 3 in `backends/typescript/test_stream_ts.py`; the rust scenario asserts 24 passing `cargo test` cases (`backends/rust/test_emit_rust.py:3806`).
- Exit table: 10 surfaces by 6 tiers = 60 cells (`tests/test_stream_reactive.py:3391-3395`). The refusing cells are those enumerated in `_EXIT_REFUSALS`; they were not counted.
- No latency, throughput, memory or user-study numbers exist.

## Paper outline

1. Introduction: subscriptions leak and park; the thesis that streams are resources.
2. The surface: subscribe, next, close, state index, combinators, `every`, events.
3. Reuse of teardown: bracket on the LIFO stack, clean unload and abort.
4. The reachability hole: a parked `next` on a silent provider; both tier families; the two-part fix.
5. Admission rules 3.1 to 3.6, with one refusal per rule.
6. Backpressure: bounded buffer, four policies, the take-budget interaction.
7. Six tiers: protocol, the blocking-tier erasure, wasm refusal, the closed exit table.
8. Durability: replay and the cursor, the cross-restart example (`docs/design/130-stream-reactive-types.md:489-560`).
9. Evaluation (a real workload and a stream-specific fault sweep, once run) and limits.
10. Related work.

## Threats to validity and limits

- The design doc says the guarantee for the cross-process case needs both the durable cursor and the required-`Stream[T]` coeffect, and that default subscriptions are `unreconstructible` after a crash: "the honest report is the deliverable, not automatic resurrection" (`docs/design/130-stream-reactive-types.md:489-510`).
- Single consumer only. Multicast is refused and deferred (`:217-225`); this removes the hardest accounting problem rather than solving it.
- Rule 3.6 is syntactic. It refuses `undo other.close()` as the source inverse (`tests/test_stream_reactive.py:127-215`) but cannot know whether the host provider actually delivers a terminal. The design says "host-local channel close, so G5-compatible" (`docs/design/130-stream-reactive-types.md:883-889`); that is an assumption about host code.
- Tier coverage is uneven: wasm refuses everything; rust and java refuse the drain window; durable cursor and required coeffect are py only (`tests/test_stream_reactive.py:3300-3330`). The "six tiers" claim is "lowers or refuses by name", not "behaves identically".
- Several executable tier tests skip when the toolchain is absent (`backends/go/test_stream_exec_130.py:14-17`, `backends/typescript/test_stream_ts.py:17-19`), so a green local run may not have executed them.
- The blocking-tier claim that a thread parked in `next` is observably equivalent to an event-loop fiber is an argument by reference to the async-extern document (`docs/design/130-stream-reactive-types.md:447-453`), not a measurement.
- Nothing is mechanized for streams.
- `every` bodies may not acquire (an unbounded stack otherwise), so some consumers must be restructured; the cost of that was not measured.
- The test clock only covers time-windowed behavior; item delivery is explicit in tests, so wall-clock races are not exercised (`docs/design/130-stream-reactive-types.md:808-826`).
- Citations marked "to be checked" have not been checked.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 23 checked, 4 corrected.
