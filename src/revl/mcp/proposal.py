"""Proposals: one speculative working copy per caller (issue #1696).

A speculative change (`revl_change` by default, `revl_edit {commit: false}`)
is applied to the caller's proposal and verified against the running
composition (admission, the lease and quarantine gates, optionally the
gauntlet), and then it stops: nothing swaps, nothing is written. Successive
speculative changes build on the same proposal. A commit re-verifies the
proposal against the running composition as it is NOW and swaps it in. A
discard drops it, and the running composition never saw it.

Proposals are keyed by the caller's operator identity (the lease holder), so
two callers of one HTTP server each have their own and neither sees the
other's until it is committed. A proposal records the generation it was built
on. If another commit moved the running composition since, committing the
stale proposal would replay a full working set over that commit and undo it
silently, so the commit is refused and the caller re-proposes.

See docs/design/1696-speculation.md.
"""

from __future__ import annotations

from . import edit as _edit
from . import leases as _leases


def _store(session) -> dict:
    store = getattr(session, "proposals", None)
    if store is None:
        store = {}
        session.proposals = store
    return store


def _key(session) -> str:
    return _leases.holder_identity(session)


def held(session) -> dict | None:
    """The calling operator's proposal, or None."""
    return _store(session).get(_key(session))


def base(session) -> dict | None:
    """The working set a speculative change starts from: the proposal, if any."""
    proposal = held(session)
    return proposal["vs"] if proposal is not None else None


def keep(session, result: dict, replacing) -> dict:
    """Hold the working set a speculative `admit` returned as the caller's
    proposal, and strip it from the result the caller sees."""
    vs = result.pop("_proposal", None)
    if vs is None:
        return result
    proposal = held(session)
    generation = (proposal["generation"] if proposal is not None
                  else getattr(session, "_generation", None))
    replaced = list(proposal["replacing"]) if proposal is not None else []
    replaced += [name for name in replacing if name not in replaced]
    _store(session)[_key(session)] = {"vs": vs, "generation": generation,
                                      "replacing": replaced}
    return {**result, "proposal": {"generation": generation,
                                   "replacing": replaced}}


def discard(session) -> bool:
    return _store(session).pop(_key(session), None) is not None


def stale(session) -> str | None:
    """Why the held proposal may not commit, or None."""
    proposal = held(session)
    now = getattr(session, "_generation", None)
    if proposal is not None and proposal["generation"] != now:
        return (f"the running composition moved since this proposal was built "
                f"(generation {proposal['generation']}, now {now}); committing it "
                "would undo that change. Discard it and propose again")
    return None


def commit(session, verify=None) -> dict:
    """Re-verify the caller's proposal against the running composition and swap
    it in."""
    proposal = held(session)
    if proposal is None:
        return {"ok": False, "committed": False, "diagnostics": [{
            "severity": "error", "code": "REVL", "category": "session",
            "message": "nothing is proposed: make a change first (revl_change "
                       "without `commit`), then commit it"}]}
    why = stale(session)
    if why is not None:
        return {"ok": False, "swapped": False, "diagnostics": [{
            "severity": "error", "code": "REVL", "category": "session",
            "message": why}]}
    before = _edit.running_source(session)
    result = _edit.admit(session, proposal["vs"], before, [],
                         tuple(proposal["replacing"]), verify, commit=True)
    if result.get("swapped"):
        discard(session)
    return result


def annotate(session, result: dict, speculative: bool) -> dict:
    """A refusal made while the caller holds a proposal, carrying the same
    `proposal` block (and `speculative`) a success carries (issue #2230): the
    held proposal is often the whole explanation for the refusal, so it has to
    be visible on it. A refusal leaves the proposal exactly as it was."""
    proposal = held(session)
    if proposal is None or result.get("ok") is not False or "proposal" in result:
        return result
    block = {"generation": proposal["generation"],
             "replacing": list(proposal["replacing"])}
    if stale(session) is not None:  # it cannot commit: say so on the block
        block["stale"] = True
    return {**result, "speculative": speculative, "proposal": block}


def _declares(vs: dict, name: str) -> bool:
    from . import symbols  # noqa: PLC0415

    try:
        symbols.resolve(vs, name)
    except symbols.SymbolError as error:
        # only a miss is absence; an ambiguous name is declared (twice)
        return not str(error).startswith("no top-level declaration matches")
    return True


def _names(vs: dict) -> list[str]:
    from . import symbols  # noqa: PLC0415

    out = []
    for key, text in symbols.buffers(vs):
        try:
            out += [decl.name for decl in symbols.declarations(text, key[1])
                    if decl.name not in out]
        except symbols.SymbolError:
            continue
    return out


def _named_symbols(arguments: dict) -> list[str]:
    """Every top-level declaration an edit addresses by name."""
    from . import symbols  # noqa: PLC0415

    out = []
    for edit in arguments.get("edits") or ():
        symbol = edit.get("symbol") if isinstance(edit, dict) else None
        if not isinstance(symbol, str) or not symbol.strip():
            continue
        if edit.get("target") and ":" not in symbol:
            symbol = f"{edit['target']}:{symbol}"
        try:
            out.append(symbols._top_and_rest(symbol)[0])
        except symbols.SymbolError:
            continue
    return out


#: The miss `symbols.resolve` raises; the only refusal `removed_named` reads.
_MISS = "no top-level declaration matches `{}`"


def removed_named(session, arguments: dict, error) -> str | None:
    """The name an edit addressed whose miss is `error`, when the running
    composition declares it and the held proposal no longer does: a staged
    change removed it. Any other refusal (a clash, a bad range) is None, and
    keeps its own message."""
    proposal = held(session)
    if proposal is None:
        return None
    running = _edit.running_source(session)
    for symbol in _named_symbols(arguments):
        if str(error) == _MISS.format(symbol) \
                and not _declares(proposal["vs"], symbol) \
                and _declares(running, symbol):
            return symbol
    return None


def removed_refusal(session, symbol: str) -> tuple[str, list]:
    """What a change that names `symbol` is told when the held proposal
    removed it (issue #2230): the name exists in the running composition, so
    "no declaration matches" would be false. The change still resolves against
    the proposal, by design, so it stays refused, and says how to proceed. A
    stale proposal cannot commit, so it is offered only the discard."""
    from . import remedy as _remedy  # noqa: PLC0415

    proposal = held(session)
    running = _names(_edit.running_source(session))
    still = set(_names(proposal["vs"]))
    # a qualified name can move buffers and leave no top-level name missing
    gone = ", ".join(f"`{name}`" for name in running if name not in still) \
        or f"`{symbol}`"
    head = (f"`{symbol}` was removed by your held proposal: a staged change "
            f"removed {gone} (proposal built on generation "
            f"{proposal['generation']}). The running composition still has it, "
            "but a change builds on the held proposal, where it no longer "
            "exists. ")
    discard_call = _remedy.call("revl_change", {"discard": True})
    if stale(session) is not None:
        return (head + "The proposal is stale (the running composition moved "
                "since it was built), so it cannot commit: drop it with "
                "revl_change {discard: true}, or name a declaration the "
                "proposal still has"), [discard_call]
    return (head + "Commit the proposal with revl_change {commit: true} (no "
            "intent), drop it with revl_change {discard: true}, or name a "
            "declaration the proposal still has"), \
        [_remedy.call("revl_change", {"commit": True}), discard_call]


def touched_since(session, proposal_vs: dict) -> list[dict]:
    """What the proposal changes relative to the running composition."""
    return _edit._touched(_edit.running_source(session), proposal_vs)


__all__ = ["held", "base", "keep", "discard", "stale", "commit", "annotate",
           "removed_named", "removed_refusal", "touched_since"]
