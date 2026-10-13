---
id: P58
title: "Gating the Operator: G4 for the Management Plane, Per-Verb Policy and Composed Verbs"
theme: agents
kind: full
maturity: partial
status: Operator profiles, per-verb gating and completeness tests ship on main with about 38 unit tests; no bypass study, baseline comparison or agent evaluation yet.
fused_with:
---

## Pitch
The verbs an agent or human uses to swap, undo, commit and halt a running system are effects too, and a per-verb, per-component profile that fails closed on undecidable targets applies to the management plane the discipline G4 applies to components.

## Abstract
Capability systems usually bound what a component may reach. They rarely bound the party operating the system: whoever reaches the management transport is root. This matters once the operator is an LLM agent speaking a tool protocol. We present operator capabilities in revl, an extension of the language's G4 guarantee and the composition-wide boundary policy to the management plane. An operator profile (a small line DSL or JSON) assigns each operator allow and deny grants over management verbs (load, swap, edit, unload, restore, snapshot, undo, commit, approve, override, estop, deploy, call, lease, fork, replay), scoped by glob to components and realms. The gate sits at verb dispatch and requires authorization on every component an action touches, computed from the session's IR before the action runs. Verbs that reach a swap through another verb's machinery are mapped to that verb, but only in the mode that mutates. When the target set cannot be derived, the gate scopes the action to the unnameable whole composition, so only a literal wildcard grant passes. A completeness test fails if any advertised verb is neither gated nor listed as ungated with a reason, and a second test checks that every compiler call in the MCP layer passes an authoring profile. Authorized actions stamp the operator into the result's authority stamp, and into the causal trace for verbs that return one. We describe the design, its decision procedure, the bugs the fail-closed rule removed, and its stated limits. We have no deployment study or adversarial evaluation yet.

## Problem and claim
In many agent-operated systems the management protocol has no authorization model: the same channel that reads state can unload the system. The operator doc states the gap directly: "Anyone who reaches the transport is root over the composition" (`docs/operator-capabilities.md:7-30`).

The claim: management actions can be gated with the same machinery that gates component reach (globs, allow/deny, deny wins, closed by default, a why-trace on refusal), provided three things hold. Each verb declares its target set before it runs. A verb that performs another verb's mutation is gated as that verb. A target set that cannot be derived is treated as the whole composition rather than as no target. The doc says the last point was a real bypass: "make the target derivation fail and the gate stopped gating" (`docs/operator-capabilities.md:455-467`).

## Contributions
1. A gate table with four rows placing operator capability beside G4 (component authority), boundary policy (composition authority) and lineage (provenance) (`docs/operator-capabilities.md:28-34`).
2. An operator profile language with allow, deny, mint ceilings, credentials and revocation, in a DSL and an equivalent JSON form (`docs/operator-capabilities.md:44-127`; `src/revl/mcp/operator.py` parser).
3. Per-verb target derivation: swap targets only components whose IR entry changes; whole-composition verbs (unload, estop, deploy) are deliberately unscoped so a halt cannot be partial (`docs/operator-capabilities.md:370-432`).
4. Composed verbs and an enforcement rule: `revl_ship` and `revl_repair` gate as `swap` when they apply; a new verb that can reach swap, load, unload, restore, rollback, undo or estop must be mapped by hand, and the stated rule is in the code comment (`src/revl/mcp/operator.py:186-193`). The completeness test (`tests/test_mcp_authority_gate.py:467-495`) checks only that each advertised verb appears in one of the two tables, not that a verb reaching swap is mapped to swap.
5. Fail-closed undecidable targets, for the operator gate and for component leases (`src/revl/mcp/operator.py:1455-1463`; `tests/test_mcp_authority_gate.py:179-196`).
6. Separation of privileges inside approval: `approve`, `override` and `estop` are distinct verbs, so one voter in a quorum has no one-operator bypass (`docs/operator-capabilities.md:395-412, 420-425`).
7. Attribution and reversibility on the management plane: authorized actions stamp the operator into the result (and into the trace where the verb returns one), and mutating responses carry their exact undo (`docs/operator-capabilities.md:483-501`; `docs/mcp-reference.md:148-160`).

## Related work
| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Kubernetes RBAC and admission control | Verbs on API resources; admission webhooks run per request | Target set is derived from the candidate's IR diff (what the swap actually changes), and an undecidable derivation refuses |
| sudo / polkit | Per-command privilege rules | Subjects are components and realms of a typed composition, with deny-wins and a why-trace |
| OPA Gatekeeper, Terraform Sentinel | Policy-as-code over proposed changes | The policy language is the same one that bounds component reach; verbs that reach swap through other verbs are gated by a hand-written name mapping, which a membership test keeps complete |
| Teleport session policy | Access to infrastructure sessions | Verb-level, per-component, with quorum and break-glass as separate verbs |
| MCP authorization | Transport-level auth for servers (citation to be checked) | Authorization of the verb on the objects it touches, not only of the caller |
| Capability-secure OS and language work (Capsicum, E, Joe-E) (citation to be checked) | Bound what code can reach | Extends the same discipline to the party operating the composition |

## Evidence on main
| Claim | path:line or test | Status | Note |
|---|---|---|---|
| Gap statement and gate comparison table | `docs/operator-capabilities.md:7-34` | shipped | |
| Profile DSL and JSON | `docs/operator-capabilities.md:44-127`; `tests/test_mcp_operator.py:92, 102` | shipped | |
| Deny wins; closed by default | `docs/operator-capabilities.md:75-79`; `tests/test_mcp_operator.py:172` | shipped | |
| Verb to MCP tool map | `src/revl/mcp/operator.py:52-180` | shipped | |
| Swap targets only changed components | `docs/operator-capabilities.md:372-378`; `tests/test_mcp_operator.py:155-170`; `tests/test_mcp_authority_gate.py:130-160` | shipped | |
| Composed verbs gated as swap, rehearsal ungated | `src/revl/mcp/operator.py:190-215`; `tests/test_mcp_authority_gate.py:316-347` | shipped | |
| Completeness guard over advertised verbs | `tests/test_mcp_authority_gate.py:467-495` | shipped | Fails on a verb in neither list, and on a stale entry |
| Every compiler call in the MCP layer carries a profile | `tests/test_mcp_authority_gate.py:523-577` | shipped | AST walk over `src/revl/mcp/` with a short exception list |
| Undecidable target set fails closed | `src/revl/mcp/operator.py:1455-1463`; `tests/test_mcp_operator.py:238`; `tests/test_mcp_authority_gate.py:179-210` | shipped | `may swap on *` still proceeds |
| Cold-load exemption narrowed to non-emitting activation | `src/revl/mcp/operator.py:1426-1450` | shipped | Exemption is argued in the code comment, not tested here |
| E-Stop is its own verb, whole composition | `docs/operator-capabilities.md:379-386`; `docs/design/443-estop.md` | shipped (gate); estop mechanics not read | |
| `approve` / `override` separation and quorum | `docs/operator-capabilities.md:257-350, 395-412`; `docs/design/471-quorum-approval.md` | shipped per docs; not read in depth | Docs state `require N of M` is "advisory against an operator who has collected the key material itself" |
| Mint ceilings enforced at `session._mint_grant` | `docs/operator-capabilities.md:128-232`; `src/revl/mcp/session.py:8440` | shipped per docs | Existing profiles with no `may mint` line still mint broadly; the doc says so |
| Authority stamp and trace event | `docs/operator-capabilities.md:483-501`; `tests/test_mcp_operator.py:260` | shipped | |
| Exact undo on mutating responses; `undo: null` with a reason otherwise | `docs/mcp-reference.md:148-160` | shipped per docs | Covers sources and manifest, not running state |
| Tiered disclosure, `revl_verbs` index | `docs/mcp-reference.md:9, 307-335`; `src/revl/mcp/disclosure.py` | shipped | |
| Profile live reload; HTTP per-request operator | `docs/operator-capabilities.md:233-256` | shipped per docs | |

The verb names in the abstract's catalogue each appear in `src/revl/mcp/server.py` and in `TOOL_VERB` or `COMPOSED_TOOL_VERB` in `src/revl/mcp/operator.py`. The operator mapping and the reference tables were read; not every handler was.

## Numbers that exist
- 19 test functions in `tests/test_mcp_operator.py`, 19 in `tests/test_mcp_authority_gate.py` (`rg -c "def test"`; not run).
- The reference doc says the MCP server's verb count is produced by `python3 tools/docgen.py --show mcp-verb-count` (`docs/mcp-reference.md:9`). It was not run; the number is not quoted here.
- No decision latency, no profile-size study, no attack results. None yet.

## Paper outline
1. Introduction: root-over-transport and agents as operators.
2. Three gates: component, composition, operator (table).
3. Profile language and decision procedure.
4. Target derivation per verb; whole-composition verbs; composed verbs.
5. Undecidable means refuse: the bypass and the fix.
6. Completeness by construction: the verb-accounting test and the compiler-door test.
7. Separation of approve, override and estop; mint ceilings.
8. Attribution and exact undo; disclosure tiers.
9. Evaluation (bypass study, expressiveness comparison, agent runs).
10. Related work, limits.

## Threats to validity and limits
- Opt-in: "With no `--operator-profile`, `session.operator` is `None` and every verb is ungated" (`docs/operator-capabilities.md:503-511`). Read-only and diagnostic verbs are never gated, so reading state and source is not protected by the profile.
- Mint bounds are per operator and adopted per operator: until an operator declares a first `may mint` line, `approve` implies minting any capability for any number of uses within the session; the doc "say[s] plainly" this (`docs/operator-capabilities.md:206-231`).
- Quorum limits, quoted: the count is "a count of authenticated credentials, one per request. It is still not a count of people" and is "advisory against an operator who has collected the key material itself" (`docs/operator-capabilities.md:340-350`).
- Completeness is enforced by tests over the advertised verbs and a list of ungated verbs with reasons; a reviewer must trust that the ungated reasons are right (`tests/test_mcp_authority_gate.py:440-465`).
- Gate correctness depends on target derivation compiling the candidate; the design chooses refusal over deferral, which costs availability for subject-scoped operators.
- The proxy without a profile is advisory (see P57); the same holds for any deployment that skips the profile.
- Several bugs this paper presents as fixed (undecidable derivation, composed verbs, renaming swap) show the mechanism was found incomplete in practice; the evaluation must be honest that completeness is empirical.
- The quorum, estop and mint sections rest on the docs and have not been checked against `src/revl/mcp/quorum.py` or `src/revl/mcp/approval_ceilings.py` in depth.

## Fact-check
Claims in this draft were checked against revl main at commit 45bec431f: 19 checked, 10 corrected.
