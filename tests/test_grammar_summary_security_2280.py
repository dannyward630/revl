"""`revl grammar` names the security declaration forms (issue #2280).

The short summary is what an agent reads first. It named `secret` but not
`capability` or `grant`, so an agent working from it could not learn that a
capability declares resource dimensions or that a composition grants reach.
This runs the CLI as a user would and checks that each form appears as a form:
a `capability` declaration line, a `secret` declaration line, and `grant` by
its keyword. A bare word in a comment does not count.
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

FORMS = {
    "capability": r"(?m)^capability \S+\(",
    "secret": r"(?m)^secret \S+ for \S+",
    "grant": r"(?m)\bgrant\b",
}


@functools.lru_cache(maxsize=None)
def _summary() -> str:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    done = subprocess.run([sys.executable, "-m", "revl", "grammar"], cwd=ROOT,
                          env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.mark.parametrize("keyword", sorted(FORMS))
def test_revl_grammar_names_the_security_form(keyword):
    assert re.search(FORMS[keyword], _summary()), (
        f"`revl grammar` does not name the `{keyword}` form")
