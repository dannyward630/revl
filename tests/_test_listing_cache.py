"""A session cache for the selector's listing of `tests/` (issue #2216).

`tools/affected_tests.py::_test_files` globs and sorts `tests/test_*.py` every
time it is called, and `select()` calls it once per word heuristic, about 22
times per changed file. `tests/test_affected_tests.py` asks `select()` about
several hundred paths, so most of its wall time went to listing the same
directory again. On the files `playground/build_wheel.py` reads, the cache
cut the selector's time by about two thirds and gave the same answer for
every file.

The listing depends only on the entry names in `<root>/tests`, so the key is
the root plus a SHA-256 of those names. Adding, removing or renaming any entry
changes the key and the original function runs again. A hit returns a fresh
list, so a caller that mutates its result cannot change the cache.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


def listing_key(root: Path) -> tuple[str, str]:
    """The root, and a SHA-256 of every entry name in `<root>/tests`.

    Raises OSError when `<root>/tests` cannot be listed."""
    names = sorted(os.fsencode(n) for n in os.listdir(root / "tests"))
    digest = hashlib.sha256(b"\0".join(names)).hexdigest()
    return str(root), digest


def cached_test_files(original):
    """Wrap `_test_files` so each distinct listing is computed once.

    The cache belongs to the wrapper, which lives as long as the module that
    installs it: one pytest session."""
    cache: dict[tuple[str, str], tuple[Path, ...]] = {}

    def test_files(root: Path):
        try:
            key = listing_key(root)
        except OSError:
            return original(root)
        hit = cache.get(key)
        if hit is None:
            hit = cache[key] = tuple(original(root))
        return list(hit)

    return test_files
