"""The one table of tier names (issue #2205).

A tier has a canonical short name (`py`, `ts`, ...) and may be spelled by the
name of its `backends/<dir>` directory (`python`, `typescript`). Commands used
to pick one spelling each, so a `--backend` copied from `revl run` into
`revl emit` failed, and every tier-keyed table grew its own alias map.

This module has no imports beyond the standard library's `argparse`, so the
argument parser can use it without loading any runtime (issue #2196).
"""

from __future__ import annotations

import argparse
from typing import Callable, Iterable

#: canonical tier name -> the other names that mean the same tier.
TIERS: dict[str, tuple[str, ...]] = {
    "py": ("python",),
    "ts": ("typescript",),
    "rust": (),
    "java": (),
    "wasm": (),
    "go": (),
}

#: canonical tier name -> its `backends/<dir>` directory name.
TIER_DIRS: dict[str, str] = {
    "py": "python",
    "ts": "typescript",
    "rust": "rust",
    "java": "java",
    "wasm": "wasm",
    "go": "go",
}

#: every accepted spelling -> canonical name.
_CANONICAL: dict[str, str] = {
    spelling: tier
    for tier, aliases in TIERS.items()
    for spelling in (tier, *aliases)
}


def canonical_tier(name: str) -> str:
    """The canonical name for any spelling of a tier.

    Raises `argparse.ArgumentTypeError` (a `ValueError`) naming the canonical
    tiers when `name` is not one of them."""
    try:
        return _CANONICAL[name]
    except KeyError:
        raise argparse.ArgumentTypeError(
            f"unknown tier {name!r} (choose from {', '.join(TIERS)})") from None


#: every accepted spelling -> its `backends/<dir>` directory name.
SPELLING_DIRS: dict[str, str] = {
    spelling: TIER_DIRS[tier] for spelling, tier in _CANONICAL.items()}


def short_tier(name: str) -> str:
    """The canonical short name for any spelling; an unknown name comes back
    unchanged, for report code that labels whatever it was handed."""
    return _CANONICAL.get(name, name)


def tier_dir(name: str) -> str:
    """The `backends/<dir>` directory name for any spelling of a tier."""
    return TIER_DIRS[canonical_tier(name)]


def tier_type(allowed: Iterable[str] | None = None, *, spelling: str = "short",
              extra: tuple[str, ...] = ()) -> Callable[[str], str]:
    """An argparse `type=` that takes either spelling of a tier.

    `allowed` is the command's own subset of canonical names (all tiers when
    None); `extra` are non-tier values it also takes (`all`). `spelling` is
    what the command hands downstream: `"short"` for `py`, `"dir"` for
    `python`. Downstream code therefore sees the value it always saw.
    """
    subset = tuple(TIERS) if allowed is None else tuple(allowed)
    unknown = [t for t in subset if t not in TIERS]
    if unknown or spelling not in ("short", "dir"):
        raise ValueError(f"bad tier_type arguments: {unknown or spelling!r}")
    shown = ", ".join((*subset, *extra))

    def convert(name: str) -> str:
        if name in extra:
            return name
        tier = _CANONICAL.get(name)
        if tier is None or tier not in subset:
            raise argparse.ArgumentTypeError(
                f"invalid tier {name!r} (choose from {shown})")
        return TIER_DIRS[tier] if spelling == "dir" else tier

    convert.__name__ = "tier"
    return convert


def tier_metavar(allowed: Iterable[str] | None = None,
                 extra: tuple[str, ...] = ()) -> str:
    """The `{a,b,c}` help label for a `--backend` with this subset."""
    subset = tuple(TIERS) if allowed is None else tuple(allowed)
    return "{" + ",".join((*subset, *extra)) + "}"
