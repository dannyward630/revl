---
id: P11
title: Confining Undo on a Hostile Filesystem
theme: effects-replay
kind: empirical
maturity: shipped-evidence
status: Seven audit findings are fixed on main with executed reproducers and regression tests on the Python and TypeScript tiers; the swapper measurement is a single run, the Node tier narrows but does not close the directory-swap window, and there is no external baseline comparison.
fused_with: P41
---

## Pitch

If an undo is derived automatically from a captured witness, the undo is itself an attacker-steerable write, and we show seven concrete ways it escaped its workspace jail, how each was closed, and the one race window that a runtime without `*at()` syscalls can only narrow.

## Abstract

Systems that make agent file operations reversible capture a witness for each mutation and later replay a derived inverse: rename the saved preimage back, unpark the deleted file. We argue that the inverse is a second write path whose source, sidecar directory and destination all need the same confinement as the forward write, and that checking only the destination is the natural mistake. We report an adversarial audit of the witnessed filesystem module of a typed effect language, with seven findings, each reproduced with executed output before it was fixed. The most severe: both pure inverses guarded only their destination, so a forged witness made a capability-free function move an outside file into the workspace and destroy it at its origin. Others: symlinked sidecar directories that redirected snapshots outside the root, hardlink write-through, a write time-of-check/time-of-use race, lexical path covering in placement, and NUL bytes escaping the declared error contract. The fixes share one structure: an enumerated set of path families that every path must pass, a table-driven totality wrapper, sidecar-only inverse sources, a directory-fd walk with O_NOFOLLOW, and a landing check that makes a witness true rather than atomic. We compare a Python tier that removes the check-to-use window on the write path with a Node tier that only narrows it (no `openat` family), and state the residual. A tier-parity test over an 18-case path-observation corpus asserts no py/ts divergence; it covers observation, not mutation. A reproduced 3396-attempt swapper run on the Node tier produced zero diversions, against a diversion within 88 attempts before the fix; zero is not a proof.

## Problem and claim

Reversible-effect designs (sagas, undo logs, transactional file systems) usually treat the inverse as trusted infrastructure. In an agent setting the writer is untrusted by premise: the roadmap says so about the workspace jail, and contrasts it with the host-file jail where the author already controls the bytes (`backends/python/revl_fs_workspace.py:116-128`). Then a witness (a serializable description naming the preimage) becomes an input to a privileged rename, and witnesses are replayed by `revl recover` from a write-ahead log, so a forged WAL entry reaches the same primitive with no source code at all (`docs/v2.0-roadmap.md:1612-1620`, F1 "Second vector (unrun)").

Claim: confinement of undo needs three things beyond confining the forward write. (1) Every path that reaches a syscall, including inverse sources and sidecar directories, must come from an enumerated guard family, and a test must fail when a fifth family is added silently. (2) The result of a mutation must be verified true after the fact (identity of the inode written), because "atomic against a concurrent unlink" is a promise a jail cannot keep against an untrusted writer. (3) Where a platform cannot express the strong control, the residual must be named in the docs and test results, not claimed equivalent.

This is an experience and measurement report, not a new algorithm. Its value is the taxonomy, the reproducers, and the evidence that a first design which "routes everything through one choke point" had three families that did not.

## Contributions

1. A taxonomy of seven escape routes for derived inverses and their witnesses (F1 to F7), each with an executed reproducer and a regression test (`docs/v2.0-roadmap.md:1612-1620`; `tests/test_fs_confinement_escapes.py`, 15 test functions; ts peer with 25 tests).
2. One path-family enumeration (`PATH_FAMILIES`, `READ_HELPERS`) shared by the Python and TypeScript tiers, a table-driven totality wrapper, and an AST scan that fails if a body performs a raw mutation or a syscall argument did not come from a guard (`backends/python/revl_fs_workspace.py:246-275`, `:388`, `:421`; `tests/test_fs_confinement_families.py:111-185`).
3. A witnessed-write design that is truthful rather than atomic: a post-write re-walk compares `(st_dev, st_ino)`, a lost race is `Err(ERACE)`, no inverse is registered, no residue is left (`backends/python/revl_fs_workspace.py:97-109,1355-1370`; `tests/test_fs_confinement_escapes.py:366-432`).
4. Expected-before checks on the inverse side: the sidecar `restore` installs and the garbage sidecar `unrm` installs must be the ones captured (regular file, one link, same inode and ctime), checked before and after the rename (`docs/witnessed-fs.md:433-526`; `tests/test_fs_restore_sidecar_identity_1016.py`, `tests/test_fs_unrm_sidecar_identity_1038.py`).
5. A tier-parity test: an 18-case path-observation corpus run through the emitted Python and TypeScript bodies over one workspace, with an assertion that the answers match case for case (`tests/test_fs_observation.py:238` case list, `:612` test).
6. A stated residual: the Node tier narrows but does not close the intermediate-directory swap around `renameSync`; the Python tier removes it with a directory-fd walk using `O_NOFOLLOW` (`docs/witnessed-fs.md:620-640` region, caveat list at `:604`; `docs/v2.0-roadmap.md:1616`).

## Related work

| Prior system or line of work | What it does | What revl does differently |
|---|---|---|
| Capsicum, pledge/unveil, WASI preopens | Capability confinement of the process or of handles | Confines a language-level undo whose inputs are data (witnesses) that can be forged or replayed from a log; not a process sandbox, and the docs say so (`docs/witnessed-fs.md:604-640`) |
| openat2 / RESOLVE_BENEATH, libpathrs (citation to be checked) | Kernel or library primitive for race-free resolution | revl uses the same discipline on Python via dir fds and shows where a runtime without it (Node) falls short |
| TOCTOU literature, symlink-race CVEs | Characterizes check-then-use races | Gives an executed swapper measurement for a concrete tier and a post-condition check instead of a promise of atomicity |
| Sagas, compensation, Git-style undo logs | Define inverses at the application level | Treats the derived inverse as an untrusted-input surface and audits it |
| ZFS/btrfs snapshots | Whole-volume rollback below the application | Per-effect inverse with identity checks of sidecars; no filesystem support needed |
| Deno permissions (citation to be checked) | Path-scoped permission prompts | Orthogonal; revl's jail is checked inside the stdlib bodies |

The closest framing in the literature is "undo is a privileged operation"; no published audit of an automatically derived inverse was found (citation to be checked).

## Evidence on main

| Claim | path:line or test | Status | Note |
|---|---|---|---|
| F1 inverse source escape fixed on py and ts | `docs/v2.0-roadmap.md:1613` region (item 422); `stdlib/fs.rvl:267-300`; `backends/python/revl_fs_workspace.py:1097` (`resolve_sidecar`); `tests/test_fs_confinement_escapes.py:101-136` | shipped | stdlib `restore` comment states both endpoints are confined; the executed "steal and destroy" reproducer was run on the ts tier |
| F2 sidecar symlink dirs | `backends/python/revl_fs_workspace.py:1004`; `tests/test_fs_confinement_escapes.py:157-175` | shipped | |
| F3 hardlink refusal `EMULTILINK` | `backends/python/revl_fs_workspace.py:1282`, `:1313`; `tests/test_fs_confinement_escapes.py:196-216` | shipped | stated cost: legit hardlinked files cannot be witnessed-written |
| F4 TOCTOU: py removed, ts narrowed | `backends/python/revl_fs_workspace.py:1254`; `tests/test_fs_confinement_escapes.py:242`; `backends/typescript/tests/fs_confinement_swapper.ts` | partial | residual named in `docs/witnessed-fs.md:620-640` region |
| F5 lexical covering in placement | `src/revl/placement.py:775` (`_fs_covers`, canonicalizes both sides; non-canonical mounts refused where they enter), `tests/test_sandbox_placement_411.py:841` | shipped | the roadmap's `src/revl/placement.py:485` pointer is stale |
| F6 NUL path and totality | `backends/python/revl_fs_workspace.py:388`, `:421`; `tests/test_fs_confinement_escapes.py:304-333` | shipped | |
| F7 stdlib shadowing made visible | roadmap item 422 F7 text; `tests/test_stdlib_search_path.py` | shipped (narrowed) | residual: audit still prints `stdlib:` prefix for a stand-in |
| Truthful write, `ERACE` | `backends/python/revl_fs_workspace.py:97-109,1355`; `tests/test_fs_confinement_escapes.py:366-432` | shipped | |
| Inverse-side identity checks (#1016, #1038) | `docs/witnessed-fs.md:433`, `:483`; `tests/test_fs_restore_sidecar_identity_1016.py`, `tests/test_fs_unrm_sidecar_identity_1038.py` | shipped | |
| Early refusal where dir fds do not exist | `tests/test_fs_dirfd_unsupported_1946.py` | shipped | Windows case |
| Tier parity, 18 cases | `tests/test_fs_observation.py:238`, `:612` | shipped (test present; not re-run) | observation half only; mutation parity is by shared enumeration plus scan |

## Numbers that exist

- Seven findings, F1 critical, F2 and F3 high, F4 medium, F5 low/medium, F6 low, F7 info (`docs/v2.0-roadmap.md:1612-1618`). Sample: one audit.
- Ts regression suite against the pre-fix module: "fails 18 of 25" (roadmap item 422 text, not re-run). 25 `test`/`it` cases in `backends/typescript/tests/fs_confinement_escapes.test.ts`, confirmed by grep.
- Ts swapper experiment: diversion within 88 attempts before; 3396 attempts over an 8 s window with zero diversions after (roadmap item 422, F4). One run each, as reported in the roadmap; the roadmap does not name the machine.
- Tier-parity corpus: 18 cases (counted in `tests/test_fs_observation.py:238`); the test asserts no divergence (not re-run).
- Python test counts (`def test_` grep; not pass results): 15 in the escapes file, 6 in the families file, 10 in the #1016 file, 12 in the #1038 file.

## Paper outline

1. Introduction: undo as a write path; threat model (untrusted workspace writer, forged witness, same-UID racer).
2. Background: witnessed externs, sidecars, receipts.
3. The audit: method, seven findings with reproducers.
4. Design of the fixes: path families, totality, sidecar-only sources, dir-fd walk, truthful write, inverse-side identity.
5. Cross-tier parity and the Node residual.
6. Evaluation: reproducer table, swapper, parity corpus, scan mutation analysis (not yet run).
7. Lessons: tests that asserted the choke point on the paths that already used it; what negative results held.
8. Related work and limits.

## Threats to validity and limits

- The docs say: "Confinement here is a runtime refusal, not physical containment" and the guard "is not a sandbox around the whole process" (`docs/witnessed-fs.md` caveats, line 604 onward).
- Reversal does not undo observation by a concurrent reader (same caveats).
- The audit was done by the project; no external replication. Findings were reproduced by the authors.
- The Node tier is narrowed, not closed; the swapper result is statistical evidence of absence on one machine.
- The wasm, go, rust and java tiers are not applicable because fs bodies exist for py and ts only (roadmap F6 text).
- Some audit items (F5, F7) are about placement and import resolution rather than the filesystem inverse; including them dilutes the filesystem focus.
- Only the Python tier has the directory-fd walk; the TypeScript tier does not.

## Fact-check

Claims in this draft were checked against revl main at commit 45bec431f: 27 checked, 4 corrected.
