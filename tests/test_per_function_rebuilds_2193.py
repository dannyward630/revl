"""Per-function rebuilds of module-wide sets stay linear (issue #2193).

Three places rebuilt a set the size of the module once for every function:
the body namespace in `lower._lower_fns`, the visible set in
`lower._refuse_callable_shadowing`, and the retention summary copy in
`ownership._visible`. Each costs O(F), so a module of F functions paid O(F^2).

Wall-clock is never asserted. Each test counts the elements the compiler
touches in one shared, module-sized object while it compiles a module of F
functions, and checks that 4x the functions costs at most 5x the work. A
per-function rebuild costs about 16x.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Set
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl import compile_source  # noqa: E402
from revl import compiler, ownership  # noqa: E402

SMALL, LARGE = 10, 40


def _module(n: int) -> str:
    """`n` functions, each calling the previous one through a local."""
    lines = ["fn f0(x: Int) -> Int { return x }"]
    for i in range(1, n):
        lines.append(
            f"fn f{i}(x: Int) -> Int {{ let y = x + 1\n return f{i - 1}(y) }}")
    return "\n".join(lines) + "\n"


class _CountingScope(Set):
    """A module's `fn_scopes` value that counts every element read from it."""

    def __init__(self, names) -> None:
        self._names = frozenset(names)
        self.reads = 0

    def __contains__(self, name) -> bool:
        self.reads += 1
        return name in self._names

    def __iter__(self):
        for name in self._names:
            self.reads += 1
            yield name

    def __len__(self) -> int:
        return len(self._names)


class _CountingSummary(Mapping):
    """A retention summary that counts every entry read from it."""

    def __init__(self, summary: dict) -> None:
        self._summary = summary
        self.reads = 0

    def __getitem__(self, name):
        self.reads += 1
        return self._summary[name]

    def __iter__(self):
        for name in self._summary:
            self.reads += 1
            yield name

    def __len__(self) -> int:
        return len(self._summary)


def _scope_reads(monkeypatch, n: int) -> int:
    """Element reads of the shared `fn_scopes` value while `n` fns lower."""
    real = compiler.check_and_lower
    scopes: list = []

    def install(program, *args, **kwargs):
        # one shared value for every fn of the module, as compile_files does
        scope = _CountingScope({fn.name for fn in program.fn_decls}
                               | {ext.name for ext in program.externs})
        for fn in program.fn_decls:
            program.fn_scopes[id(fn)] = scope
        scopes.append(scope)
        return real(program, *args, **kwargs)

    monkeypatch.setattr(compiler, "check_and_lower", install)
    compile_source(_module(n), "scale.rvl")
    monkeypatch.undo()
    assert len(scopes) == 1
    return scopes[0].reads


def _summary_reads(monkeypatch, n: int) -> int:
    """Entry reads of the retention summary while `n` fns are annotated."""
    real = ownership.retention_summary
    summaries: list = []

    def counting(functions):
        summary = _CountingSummary(real(functions))
        summaries.append(summary)
        return summary

    monkeypatch.setattr(ownership, "retention_summary", counting)
    compile_source(_module(n), "scale.rvl")
    monkeypatch.undo()
    assert len(summaries) == 1
    return summaries[0].reads


@pytest.mark.parametrize("reads", [_scope_reads, _summary_reads],
                         ids=["fn_scopes", "retention_summary"])
def test_module_wide_reads_grow_linearly(monkeypatch, reads):
    small = reads(monkeypatch, SMALL)
    large = reads(monkeypatch, LARGE)
    assert small > 0
    assert large <= 5 * small, (
        f"{LARGE} fns read {large} elements, {SMALL} fns read {small}: "
        f"{large / small:.1f}x for {LARGE // SMALL}x the functions")


def test_scope_is_read_once_per_lowering_site(monkeypatch):
    # the body namespace and the shadowing check each read the shared scope
    # once per module, so the total is a small multiple of its size
    assert _scope_reads(monkeypatch, LARGE) <= 3 * LARGE


def test_module_still_compiles_to_the_same_functions():
    ir = compile_source(_module(LARGE), "scale.rvl")
    names = [fn["name"] for fn in ir["functions"]]
    assert names == [f"f{i}" for i in range(LARGE)]
