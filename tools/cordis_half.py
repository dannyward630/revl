"""Run the cordis-runtime half of `tests/` for the local pre-merge gate (issue #2207).

The frontend step of tools/pre_merge.sh runs `tests/` from the frontend venv,
which has no cordis-py runtime, so every test that needs it skips there. Before
this step no local gate ran those tests at all: only CI's main-only
`frontend-cordis` job did, so a runtime regression (the issue's mutant turns the
WAL-less abort replay in `SessionOwner.finalize_abort` from LIFO into FIFO)
passed every local gate.

This driver picks the test files to run and the interpreter to run them with:

* Files: when the frontend step ran with `REVL_CORDIS_SKIP_LOG` set,
  tests/conftest.py wrote the node id of every test that skipped naming cordis
  to that log; the files of those node ids are exactly the half that did not
  run. Without a log (the frontend step could not run), the selected test files
  that mention cordis are used instead.
* Interpreter: the first candidate that can import the suite's modules AND the
  pinned cordis-py runtime with its `watchdog` extra. That is the venv
  backends/python/setup.sh builds (the pinned fork, never PyPI `cordis`).

The last line printed is a status the gate reads:

    STATUS ran <n>          pytest ran <n> file(s); the exit code is pytest's
    STATUS none             no selected test needs the runtime (exit 0)
    STATUS missing <why>    files need the runtime and no candidate has it
                            (exit EXIT_MISSING): the gate reports NOT OK
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

EXIT_MISSING = 10

# What `pytest tests/` imports hard (tools/pre_merge.sh `suite_ok`), plus the
# runtime itself and the `watchdog` extra the fork's `cordis.hmr` needs.
REQUIRED_MODULES = ("pytest", "pytest_asyncio", "yaml", "cryptography",
                    "llguidance", "cordis", "watchdog")

SETUP_HINT = ("run `sh backends/python/setup.sh` (pinned cordis-py fork, "
              "CORDIS_PY_PIN, with watchdog) or set REVL_CORDIS_PYTHON")


def missing_modules(python: str) -> list[str] | None:
    """The required modules `python` cannot import; None if it cannot run."""
    if not python or not os.access(python, os.X_OK) or Path(python).is_dir():
        return None
    probe = ("import importlib.util, sys\n"
             f"mods = {REQUIRED_MODULES!r}\n"
             "print(' '.join(m for m in mods if importlib.util.find_spec(m) is None))\n")
    try:
        done = subprocess.run([python, "-c", probe], capture_output=True,
                              text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.split()


def resolve_python(candidates: list[str]) -> tuple[str | None, list[str]]:
    """The first usable candidate, and why each earlier one was rejected."""
    rejected = []
    for cand in candidates:
        if not cand:
            continue
        missing = missing_modules(cand)
        if missing is None:
            rejected.append(f"{cand}: not runnable")
        elif missing:
            rejected.append(f"{cand}: cannot import {', '.join(missing)}")
        else:
            return cand, rejected
    return None, rejected


def files_from_log(log: Path, root: Path) -> list[str]:
    files = set()
    for line in log.read_text(encoding="utf-8").splitlines():
        path = line.strip().split("::", 1)[0]
        if path and (root / path).is_file():
            files.add(path)
    return sorted(files)


def files_from_selection(selection: list[str], root: Path) -> list[str]:
    files = set()
    for node in selection:
        path = root / node.split("::", 1)[0]
        found = sorted(path.rglob("test_*.py")) if path.is_dir() else [path]
        for f in found:
            try:
                if f.is_file() and "cordis" in f.read_text(encoding="utf-8"):
                    files.add(str(f.relative_to(root)))
            except (OSError, UnicodeDecodeError, ValueError):
                continue
    return sorted(files)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--log", help="REVL_CORDIS_SKIP_LOG the frontend step wrote")
    ap.add_argument("--select", default="tests/",
                    help="space-separated pytest selection (fallback without a log)")
    ap.add_argument("--python", action="append", default=[],
                    help="candidate interpreter, in order (repeatable)")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    if args.log and Path(args.log).is_file():
        files = files_from_log(Path(args.log), root)
    else:
        files = files_from_selection(args.select.split(), root)
    if not files:
        print("STATUS none")
        return 0

    python, rejected = resolve_python(args.python)
    if python is None:
        for why in rejected:
            print(f"rejected {why}")
        print(f"{len(files)} test file(s) need the cordis-py runtime and did not run")
        print(f"STATUS missing no cordis-py venv: {SETUP_HINT}")
        return EXIT_MISSING

    cmd = [python, "-m", "pytest", *files, "-q", "-p", "no:cacheprovider"]
    env = dict(os.environ)
    env.pop("REVL_CORDIS_SKIP_LOG", None)
    rc = subprocess.run(cmd, cwd=root, env=env, check=False).returncode
    print(f"STATUS ran {len(files)}")
    # pytest's own codes: 5 is "nothing collected", which here would be a
    # silent pass over files that need the runtime, so it is a failure too.
    return rc if rc != 5 else 1


if __name__ == "__main__":
    sys.exit(main())
