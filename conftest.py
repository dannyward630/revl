"""Repository-wide pytest hook: a required tier's missing toolchain is a failure.

Issue #2264. ``REVL_REQUIRE_TIERS`` (src/revl/test.py) turns an absent-toolchain
skip into a failure, but only for a test that goes through a ``revl.test``
runner. Most go tests do not: they probe ``shutil.which("go")`` themselves and
call ``pytest.skip``, in a ``skipif`` marker, a fixture or the test body. So a
CI job that lost its go toolchain skipped every one of them and still went
green, because a skip is green.

This hook looks at what actually happened rather than at how the test raised
its skip, so a marker, a fixture and a test body are all covered. When the
session is REQUIRED to have a tier (``REVL_REQUIRE_TIERS`` names it, or
``all``), that tier's toolchain is not on PATH, and a test in a file that
probes for the toolchain reports SKIPPED, the skip becomes a failure that says
so. "Probes" means the file itself spells the probe (``which("go")`` or
``go_runtime_reason(``); a probe hidden in a helper module another file
imports is not seen.

It lives at the repository root so it covers ``tests/`` and ``backends/go/``
alike. It never fires where the toolchain is installed, and never fires where
the tier is not required: a laptop without go still skips with a reason.
``tests/test_go_tier_required_2264.py`` runs it end to end.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import pytest

#: Same variable `revl.test.REQUIRE_TIERS_ENV` reads. Parsed here directly so
#: this file imports nothing from revl: it is loaded by every pytest run in the
#: repository, including jobs whose interpreter is not the one under test.
_REQUIRE_ENV = "REVL_REQUIRE_TIERS"

#: tier -> (the binary that proves its toolchain is present, the probe a test
#: file uses to look for it). Only go is here: it is the one tier whose tests
#: probe the toolchain directly AND that CI requires (see
#: tests/test_env_gated_skips_run_somewhere.py, `_TIER_NOT_REQUIRED_IN_CI`).
_PROBES: dict[str, tuple[str, re.Pattern[str]]] = {
    "go": ("go", re.compile(r"""which\(\s*["']go["']\s*\)|go_runtime_reason\(""")),
}

#: tier -> was its toolchain absent when the session started. Measured once,
#: so a test that monkeypatches `shutil.which` cannot change the answer.
_ABSENT: dict[str, bool] = {}

_PROBING_FILES: dict[str, bool] = {}


def _required(raw: str) -> set[str]:
    names = {n for n in raw.replace(",", " ").split() if n}
    return set(_PROBES) if "all" in names else names & set(_PROBES)


def pytest_configure(config: pytest.Config) -> None:
    _ABSENT.clear()
    for tier in _required(os.environ.get(_REQUIRE_ENV, "")):
        binary, _probe = _PROBES[tier]
        _ABSENT[tier] = shutil.which(binary) is None


def _probes(path: str, tier: str) -> bool:
    key = f"{tier}:{path}"
    if key not in _PROBING_FILES:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            text = ""
        _PROBING_FILES[key] = bool(_PROBES[tier][1].search(text))
    return _PROBING_FILES[key]


def _missing_required_tier(item: pytest.Item) -> str | None:
    """The required tier whose absent toolchain this item's file probes for."""
    path = str(getattr(item, "path", "") or item.fspath)
    for tier, absent in sorted(_ABSENT.items()):
        if absent and _probes(path, tier):
            return tier
    return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call):
    outcome = yield
    report = outcome.get_result()
    if not report.skipped or hasattr(report, "wasxfail"):
        return
    tier = _missing_required_tier(item)
    if tier is None:
        return
    reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else report.longrepr
    report.outcome = "failed"
    report.longrepr = (
        f"the {tier} tier is REQUIRED here ({_REQUIRE_ENV}) but `{_PROBES[tier][0]}` "
        f"is not on PATH, so this test would have measured nothing and reported "
        f"green. It skipped with: {reason}"
    )
