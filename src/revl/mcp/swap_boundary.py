"""The proof obligation at the swap boundary (issue #2277).

`Session.swap` disposes the predecessor generation and boots the successor in
the same process. Disposal running is not the same as the predecessor leaving
nothing behind, so a swap asked to prove its boundary (`prove_boundary=True`)
seals it between the two: after the predecessor's teardown and before the
successor's load, it compares the process against the baseline the session
took before its first generation booted. Any difference refuses the swap by
name, and the session reboots the predecessor so it keeps serving.

What is compared, and the refusal each one raises:

* `residue` and `hostResources`: the R4 teardown checks `unload` reports (the
  four cordis counters, an unresolved compensation, and every host
  `new`/`open` paired with its `drop`/`close` over the driver's whole host
  trace). `RESIDUE_LEFT`. With no
  host trace the pairing cannot run, so it is reported unverified and the swap
  refuses `UNVERIFIED`; a check that did not run is never a pass.
* `escrow`: a witnessed mutation or a deferred emission still pending on the
  session owner. `ESCROW_OPEN`, the gate crate's rule for replacing the extern
  surface under an open escrow.
* `registers`: the process-global runtime registers in `REGISTERS`.
  `REGISTER_DRIFT`. Only the enumerated set is compared; a register added to the
  runtime later is a hole until it is listed here. The two registers the
  runtime fills per generation and never empties (`DISCHARGED`: resolved config
  and decoding grammars) are emptied of the predecessor's own entries first
  (`discharge`), because that residue is the toolchain's to pay, not the
  author's. A refused seal puts them back (`restore`).
* `threads`: a thread alive at the seal that was not alive at the baseline.
  `THREAD_LEFT`.
* `env`: an `os.environ` key added, removed or changed. `ENV_DRIFT`. The proof
  names keys, never values, because the environment carries secrets.
* `modules`: a `sys.modules` entry that appeared since the baseline and is not
  in the generation namespace, the standard library or revl's own toolchain.
  `MODULE_LEFT`.

The proof is py-tier only. Every other tier boots each generation as a child
process, so a same-process swap does not exist there; a caller asking for the
proof on another tier gets `TIER_UNSUPPORTED`. docs/swap.md has the reader's
version of this list.
"""

from __future__ import annotations

import dataclasses
import gc
import os
import sys
import threading
import weakref
from pathlib import Path

TIER_UNSUPPORTED = "TIER_UNSUPPORTED"
RESIDUE_LEFT = "RESIDUE_LEFT"
UNVERIFIED = "UNVERIFIED"
ESCROW_OPEN = "ESCROW_OPEN"
REGISTER_DRIFT = "REGISTER_DRIFT"
THREAD_LEFT = "THREAD_LEFT"
ENV_DRIFT = "ENV_DRIFT"
MODULE_LEFT = "MODULE_LEFT"

#: Every refusal, in the order a refused proof lists them (the first is the
#: refusal's `code`), with the check whose failure raises it. `UNVERIFIED` is
#: raised by a check that did not run, and `TIER_UNSUPPORTED` before any check,
#: so neither has one. `diagnostics.OTHER_CODES` explains each code.
REFUSALS = (
    {"code": TIER_UNSUPPORTED, "check": None},
    {"code": RESIDUE_LEFT, "check": "residue"},
    {"code": RESIDUE_LEFT, "check": "hostResources"},
    {"code": UNVERIFIED, "check": None},
    {"code": ESCROW_OPEN, "check": "escrow"},
    {"code": REGISTER_DRIFT, "check": "registers"},
    {"code": THREAD_LEFT, "check": "threads"},
    {"code": ENV_DRIFT, "check": "env"},
    {"code": MODULE_LEFT, "check": "modules"},
)

#: The process-global mutable registers of `backends/python/runtime.py` the
#: seal compares. Three are left out on purpose, so they are not mistaken for
#: forgotten ones:
#:
#: * `_REALM_LABELS`: an intern table. A label is a stateless `(realm, key)`
#:   identity object that equal realm strings share across the whole process
#:   by design, so a successor reusing its predecessor's label is the intended
#:   behaviour, and the label carries nothing it could pass along.
#: * `_CLOCK_ANCHOR`: the session clock is a ratchet and its anchor outlives a
#:   generation by design (`_SURVIVES_A_FAILED_LOAD` in session.py). A successor
#:   observes a later clock than a fresh process would; the proof does not claim
#:   otherwise.
#: * `_trace`: the primary trace callback is the session's own plumbing. Each
#:   session reinstalls its driver's callback before every step.
REGISTERS = (
    "_revl_grammars", "_ACTIVATING", "_LIVE_INSTANCES",
    "_observers", "_fault_probe", "_SESSION_OWNER", "_ESTOP", "_ESTOP_LATCH",
    "_INFLIGHT", "_LIVE_FRAMES", "RESOLVED_CONFIG", "_pending_config",
    "_STREAM_PARKED", "_STREAM_SWEEPER",
)

#: Registers the runtime fills for each generation and never empties: the
#: config each component resolved (secret fields included), keyed by component
#: name, and the decoding grammars each emitted module states, keyed
#: `Service.method`. That is the toolchain's own residue, not the author's, so
#: before comparing, the session withdraws the PREDECESSOR's entries
#: (`owned_keys`, `discharge`) and the seal names them in `detail.discharged`.
#: A successor registers both for itself (its components resolve their config
#: at activation, its module registers its grammars when it is emitted). A
#: refused seal restores what was withdrawn before the predecessor is booted
#: again (`restore`), so the tables end where the swap found them.
DISCHARGED = ("RESOLVED_CONFIG", "_revl_grammars")

#: The `sys.modules` prefix every emitted generation registers under
#: (`run._Driver._gen_prefix`). The driver evicts these itself and emitted
#: modules never import one another, so they are the generation namespace.
_GENERATION_PREFIX = "revl_run_gen"


@dataclasses.dataclass(frozen=True)
class Snapshot:
    """The process state the seal compares, taken at one instant."""

    registers: dict
    threads: frozenset
    env: dict
    modules: frozenset
    discharged: dict


def take(runtime) -> Snapshot:
    """Snapshot the process for a later `seal`. Cheap: a fingerprint per
    register, the live thread idents, a copy of the environment and the
    `sys.modules` keys. Threads are held as the objects themselves, so a
    thread ident the OS reuses cannot pass a new thread off as a baseline one.
    """
    return Snapshot(
        registers={name: _fingerprint(getattr(runtime, name, None))
                   for name in REGISTERS},
        threads=frozenset(threading.enumerate()),
        env=dict(os.environ),
        modules=frozenset(sys.modules),
        discharged={name: {key: id(value) for key, value
                           in (getattr(runtime, name, None) or {}).items()}
                    for name in DISCHARGED},
    )


def _fingerprint(value):
    """Identity of a register's contents: which objects it holds, not their
    state. A container is the frozenset of what it holds (a dict by key and
    value identity), so `_drifted` can ask what is NEW; anything else is the
    value itself, or its identity.

    Identity is `id()`, which CPython reuses once an object is collected. A new
    object that lands at a collected baseline object's address, under the same
    key, would read as the baseline one. Holding the baseline objects to rule
    that out would keep weakly held frames alive, so the limit is stated
    instead (docs/swap.md)."""
    if isinstance(value, dict):
        return frozenset((repr(key), id(item)) for key, item in value.items())
    if isinstance(value, (weakref.WeakSet, list, tuple, set)):
        return frozenset(id(item) for item in list(value))
    if value is None or isinstance(value, (str, int, float, bool)):
        return ("value", value)
    return ("object", id(value))


def _drifted(before, after) -> bool:
    """Whether a register holds something now that it did not hold at the
    baseline. A container only drifts by GAINING an entry: one the baseline
    held that has since been collected (a weakly held frame of an earlier
    session) is not something the predecessor left behind."""
    if isinstance(before, frozenset) and isinstance(after, frozenset):
        return bool(after - before)
    return before != after


def seal(baseline: Snapshot, runtime, residue: dict, owner,
         withdrawn: dict | None = None) -> dict:
    """The boundary proof: compare the process now against `baseline`.

    `residue` is the session's R4 report for the disposed generation
    (`checks`, `detail` and `unverified`, as `Session._residue_checks` returns
    them). `owner` is the disposed generation's session owner, or None.
    `withdrawn` is what `discharge` took out of the `DISCHARGED` tables; the
    proof names its keys, never its values (a config value can be a secret).

    Returns `{noResidue, checks, detail}`, with `unverified` when a check could
    not run and `refusals` when anything is off baseline. `noResidue` is true
    only when every check ran and passed."""
    discharged = {name: sorted((str(key) for key in entries))
                  for name, entries in (withdrawn or {}).items() if entries}
    # a disposed generation's frames can sit in reference cycles until the
    # collector runs; unreachable, they reach nothing, so collect them first
    gc.collect()
    now = take(runtime)
    r4 = residue["checks"]
    checks = {"residue": all(ok for name, ok in r4.items()
                             if name != "hostResources")}
    if "hostResources" in r4:
        checks["hostResources"] = r4["hostResources"]
    escrowed, queued = _pending(owner)
    drifted = sorted(name for name in REGISTERS
                     if _drifted(baseline.registers.get(name),
                                 now.registers[name]))
    threads = _threads_left(baseline)
    env = sorted(key for key in set(baseline.env) | set(now.env)
                 if baseline.env.get(key) != now.env.get(key))
    modules = _modules_left(baseline, now)
    checks.update({
        "escrow": not (escrowed or queued),
        "registers": not drifted,
        "threads": not threads,
        "env": not env,
        "modules": not modules,
    })
    detail = {
        "residue": residue["detail"],
        "discharged": discharged,
        "escrowed": escrowed,
        "queued": queued,
        "registers": drifted,
        "threads": threads,
        "env": env,
        "modules": modules,
    }
    unverified = list(residue.get("unverified") or ())
    proof = {"noResidue": all(checks.values()) and not unverified,
             "checks": checks, "detail": detail}
    if unverified:
        proof["unverified"] = unverified
    named = refusals(proof)
    if named:
        proof["refusals"] = named
    return proof


def refusals(proof: dict) -> list:
    """The refusals a proof raises, each named once, in `REFUSALS` order."""
    failed = {name for name, ok in proof["checks"].items() if not ok}
    named: list = []
    for row in REFUSALS:
        raised = (row["check"] in failed if row["check"] is not None
                  else row["code"] == UNVERIFIED and bool(proof.get("unverified")))
        if raised and row["code"] not in named:
            named.append(row["code"])
    return named


def owned_keys(ir: dict) -> dict:
    """The keys a generation's own load writes into each `DISCHARGED` table,
    read off its IR: a component resolves its config under its component name
    (the emitted `Frame` is named after it), and the emitted module registers a
    grammar under `Service.method` for every service method that states a
    `response_grammar` (emit.py `_grammar_registry`)."""
    components = frozenset(component["name"]
                           for component in ir.get("components") or ()
                           if isinstance(component, dict) and component.get("name"))
    grammars = frozenset(
        f"{svc_name}.{m_name}"
        for svc_name, svc in (ir.get("services") or {}).items()
        for m_name, spec in ((svc or {}).get("methods") or {}).items()
        if isinstance(spec, dict) and spec.get("response_grammar"))
    return {"RESOLVED_CONFIG": components, "_revl_grammars": grammars}


def discharge(baseline: Snapshot, runtime, owned: dict) -> dict:
    """Withdraw the predecessor's own entries (`owned`, from `owned_keys`) from
    each `DISCHARGED` table, and return them, `{table: {key: value}}`, for
    `restore`.

    Only a key the predecessor's IR names is touched, so another session's
    entry under another name never is. Of those, an entry still holding the
    very object it held at `baseline` was not written by this session's
    generations (it is an earlier session's, left behind), so it stays too.
    The tables are keyed by name, so a second live session with a component
    of the SAME name shares the entry; the runtime cannot tell the two apart
    and neither can this."""
    withdrawn: dict = {}
    for name in DISCHARGED:
        table = getattr(runtime, name, None)
        if not isinstance(table, dict):
            continue
        before = baseline.discharged.get(name, {})
        taken = {}
        for key in sorted(owned.get(name, ()), key=str):
            if key in table and before.get(key) != id(table[key]):
                taken[key] = table.pop(key)
        if taken:
            withdrawn[name] = taken
    return withdrawn


def restore(runtime, withdrawn: dict) -> None:
    """Put back what `discharge` withdrew, for a seal that refused: the
    predecessor is booted again and finds the tables as the swap found them."""
    for name, entries in (withdrawn or {}).items():
        table = getattr(runtime, name, None)
        if isinstance(table, dict):
            table.update(entries)


def _pending(owner) -> tuple:
    """How many escrowed entries and deferred emissions the owner still holds."""
    if owner is None:
        return 0, 0
    return (len(getattr(owner, "_escrow", None) or ()),
            len(getattr(owner, "_queue", None) or ()))


def _threads_left(baseline: Snapshot) -> list:
    """Threads alive now that were not alive at the baseline, by name."""
    return sorted(t.name for t in threading.enumerate()
                  if t not in baseline.threads and t.is_alive())


def _modules_left(baseline: Snapshot, now: Snapshot) -> list:
    """`sys.modules` entries that appeared since the baseline and are not the
    generation namespace, the standard library or revl's toolchain."""
    roots = _toolchain_roots()
    return sorted(name for name in now.modules - baseline.modules
                  if not _tolerated_module(name, roots))


def _tolerated_module(name: str, roots: tuple) -> bool:
    if name.startswith(_GENERATION_PREFIX):
        return True
    if name.partition(".")[0] in sys.stdlib_module_names:
        return True
    module = sys.modules.get(name)
    if module is None:
        return True   # gone again: nothing is left
    path = getattr(module, "__file__", None)
    if path is None:
        return False
    real = os.path.realpath(path)
    return any(real.startswith(root + os.sep) for root in roots)


def _toolchain_roots() -> tuple:
    """revl's package, the py backend and the cordis runtime: code the toolchain
    imports lazily, which is not anything a generation brought in."""
    from .._paths import backends_root  # noqa: PLC0415

    roots = [Path(__file__).resolve().parents[1], backends_root() / "python"]
    cordis = sys.modules.get("cordis")
    cordis_file = getattr(cordis, "__file__", None)
    if cordis_file:
        roots.append(Path(cordis_file).resolve().parent)
    return tuple(os.path.realpath(root) for root in roots)
