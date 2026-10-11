"""Issue #2196: `revl compile` does not import the subsystems it never runs.

Every `revl` spawn used to import every subcommand's handler module at the top
of `revl.__main__`, so a plain compile paid for `revl.run` (asyncio, ssl),
`revl.test`, the composition resolver and the OpenAPI importer before it read
its first file. The check runs a real spawn under `-X importtime`, which names
every module the process imports, and asserts none of those were loaded.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "counter_pair.rvl"

#: Modules a module compile has no use for. Each one is imported by the
#: subcommand that needs it, inside that subcommand's handler.
DEFERRED = (
    "asyncio",
    "ssl",
    "revl.run",
    "revl.test",
    "revl.composition",
    "revl.import_openapi",
    "revl.distribute",
    "revl.cli.change",
    "revl.cli.interop",
    "revl.cli.observe",
    "revl.cli.promote",
    "revl.cli.slo",
)


def _imported_by(argv: list[str], cwd: Path) -> tuple[subprocess.CompletedProcess, set[str]]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(ROOT / "src"), env.get("PYTHONPATH", "")) if part)
    # a coverage start hook would import modules of its own into the spawn
    env.pop("COVERAGE_PROCESS_START", None)
    proc = subprocess.run(
        [sys.executable, "-X", "importtime", "-P", "-m", "revl", *argv],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=300,
        check=False)
    modules = {line.rsplit("|", 1)[-1].strip()
               for line in proc.stderr.splitlines()
               if line.startswith("import time:")}
    return proc, modules


def test_compile_spawn_does_not_import_subcommand_only_modules(tmp_path):
    out = tmp_path / "ir.json"
    proc, modules = _imported_by(["compile", str(EXAMPLE), "-o", str(out)],
                                 tmp_path)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert json.loads(out.read_text(encoding="utf-8"))["components"]
    # the probe itself works: the compiler is in the list it reads
    assert "revl.compiler" in modules and "revl.parser" in modules
    loaded = sorted(name for name in DEFERRED if name in modules)
    assert loaded == [], f"`revl compile` imported {loaded}"


def test_run_backend_names_are_the_ones_revl_run_checks():
    """`revl run --help` lists the backends from `revl._run_backends`; the
    runtime still validates `--backend` against `revl.run.KNOWN_BACKENDS`.
    They must stay one tuple, not two copies that can drift."""
    from revl import _run_backends, run  # noqa: PLC0415

    assert run.KNOWN_BACKENDS is _run_backends.KNOWN_BACKENDS
    assert run.RUNNABLE_BACKENDS is _run_backends.RUNNABLE_BACKENDS
