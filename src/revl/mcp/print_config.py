"""`revl mcp serve --print-config`: the MCP client config block (issue #2281).

A client needs a command and args to start the server, and the one value a
human cannot guess is the interpreter: it has to import both `revl` and
`cordis`, and which one does is installation specific. This module finds it by
asking each candidate to import both, and prints the block for it. Nothing here
opens stdio or starts a server.

Candidates, in order: the runtime venv `backends/python/setup.sh` builds, then
the interpreter running this command. `revl doctor` reports the same answer
through `candidates`, so the two cannot disagree.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Callable, Iterable, TextIO

from .._paths import backends_root, venv_python

#: What a candidate has to run for the server to be fully usable from it.
PROBE = ("-P", "-c", "import cordis, revl")


def candidates(python_dir: Path | None = None) -> list[Path]:
    """The interpreters to try, runtime venv first, without duplicates."""
    python_dir = python_dir or backends_root() / "python"
    found: list[Path] = []
    for path in (venv_python(python_dir / ".venv"), Path(sys.executable)):
        if path not in found:
            found.append(path)
    return found


def can_import_both(python: Path) -> bool:
    """Whether *python* exists and imports `revl` and `cordis`."""
    from . import runtime_gate  # noqa: PLC0415 - lazy

    return runtime_gate.venv_has_cordis(python)


def working_interpreter(options: Iterable[Path],
                        can_import: Callable[[Path], bool] = can_import_both,
                        ) -> Path | None:
    """The first of *options* that imports both, or None."""
    for python in options:
        if can_import(python):
            return python
    return None


def build_config(python: Path, roots: Iterable[str]) -> dict:
    """The client config block. Every path in it is absolute."""
    args = ["-P", "-m", "revl", "mcp", "serve"]
    for root in roots:
        args += ["--root", os.path.abspath(root)]
    return {"mcpServers": {"revl": {"command": str(python), "args": args}}}


def run(roots: Iterable[str] | None, *, out: TextIO | None = None,
        err: TextIO | None = None,
        options: list[Path] | None = None,
        can_import: Callable[[Path], bool] = can_import_both) -> int:
    """Print the block and return 0, or say why there is none and return 1.
    *roots* defaults to the current directory, the project the session works on."""
    out = out or sys.stdout
    err = err or sys.stderr
    options = options if options is not None else candidates()
    python = working_interpreter(options, can_import)
    if python is None:
        tried = ", ".join(str(p) for p in options)
        setup = backends_root() / "python" / "setup.sh"
        print(f"error: no interpreter can import both revl and cordis "
              f"(tried {tried}). Fix: sh {setup}, then run this again",
              file=err)
        return 1
    block = build_config(python, list(roots or []) or [os.getcwd()])
    print(json.dumps(block, indent=2), file=out)
    return 0
