"""The backend names `revl run` accepts, with no runtime import.

`revl.run` re-exports both tuples. They live here so the argument parser
(`revl.cli.parser`) can list them in `revl run --help` without importing
`revl.run`, which pulls asyncio, ssl and subprocess into every CLI spawn
(issue #2196).
"""

from __future__ import annotations

KNOWN_BACKENDS = ("py", "ts", "rust", "java", "wasm", "go")

# py boots cordis-py in-process (`revl.run._Driver`); ts/rust/java/wasm/go each
# boot the composition as a *separate process* over the same bridge seam
# (run_ts.py, run_rust.py, run_java.py, run_wasm.py, run_go.py): ts a node
# process on cordis v4, rust a cordis-rs binary, java a JVM on cordis4j, wasm
# the cordis-wasm runtime on wasmtime, go the stc-go placement runner. On every
# non-py tier --once (boot -> LIFO teardown -> no-residue proof -> exit) is
# wired, each behind its own runtime-availability gate (skip-with-reason, never
# a green run that booted nothing).
RUNNABLE_BACKENDS = ("py", "ts", "rust", "java", "wasm", "go")
