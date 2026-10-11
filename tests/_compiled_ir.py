"""One compile of a self-host document per test session (issue #2192).

About twenty test modules compile `selfhost/lower.rvl` with `compile_files`
for the same IR, at about 6 s of CPU each, and CI shards run several of them
in one process. `compiled_ir(path)` compiles once and hands every later caller
its own copy of the same IR.

The IR is kept pickled, under a SHA-256 key over every input of the build
(`cache_key`):

  * the path as given, since that is the spelling `compile_files` sees;
  * the bytes and path of the document and of every file it names, followed
    transitively: `use "..."` modules, `ref SYM from "..."` host modules,
    `@backend file "..."` bodies and `asset "..."` files. Each target is tried
    where the compiler may resolve it: beside the naming file, under each
    `REVL_IMPORT_PATH` entry, and under the stdlib's parent;
  * every file of the stdlib directory and of the `revl` package the process
    actually imports (not the tree's `src/revl` by name: a test process can
    import another one), so a compiler change is a new key;
  * the module names in `backends/python`, which the compiler reads to refuse
    inline Python that shadows one;
  * `REVL_IMPORT_PATH` itself, the Python version and this file's FORMAT.

Not followed: the model document a `revl gen-types` header names. No document
compiled through here carries one; a caller that compiles one must not use this.

Every call returns `pickle.loads` of the stored bytes, so a caller that
mutates its IR changes nobody else's (about 0.1 s, against 6 s to compile).

The in-process copy is always on. When pytest's cache provider is enabled,
tests/conftest.py also points `configure()` at a directory under the pytest
cache dir, and the pickles are written there too, so the next session, or
another worker of the same run, starts warm. A write goes to a temporary file
in the same directory and is moved into place with `os.replace`, which is
atomic, so a parallel worker never reads a partial file. A file that does not
load, or carries another key, is a miss and is rebuilt.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

FORMAT = 1

# The file a document names: `use "./lexer.rvl" { ... }`,
# `ref SYM from "./host.py"`, `= @py file "./body.py"`, `asset "./a.tpl"`.
# A match inside a comment or a string only adds an input, which costs a miss
# at worst.
_NAMES_FILE = re.compile(r'\b(?:use|from|file|asset)\s+"([^"]+)"')

_memory: dict[str, bytes] = {}
_cache_dir: Path | None = None


@dataclass(frozen=True)
class Inputs:
    """Where the compiler reads from, besides the document itself."""
    package_dir: Path
    stdlib_dir: Path
    backends_python: Path
    import_path: tuple[str, ...]


def live_inputs() -> Inputs:
    """The inputs of the `revl` this process imports."""
    import revl  # noqa: PLC0415
    from revl._paths import backends_root, stdlib_root  # noqa: PLC0415
    entries = os.environ.get("REVL_IMPORT_PATH", "").split(os.pathsep)
    return Inputs(
        package_dir=Path(revl.__file__).resolve().parent,
        stdlib_dir=Path(stdlib_root()).resolve(),
        backends_python=Path(backends_root()).resolve() / "python",
        import_path=tuple(e.strip() for e in entries if e.strip()))


def configure(cache_dir: Path | None) -> None:
    """Keep a copy on disk in `cache_dir`, or (None) in memory only."""
    global _cache_dir
    _cache_dir = Path(cache_dir) if cache_dir is not None else None


def _import_closure(root: Path, inputs: Inputs) -> list[Path]:
    """`root` and every file it names, transitively, sorted."""
    bases = [Path(e) for e in inputs.import_path] + [inputs.stdlib_dir.parent]
    seen: set[Path] = set()
    pending = [root.resolve()]
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue  # stays in the key as missing
        for target in _NAMES_FILE.findall(text):
            pending.append((path.parent / target).resolve())
            pending.extend((base / target).resolve() for base in bases
                           if (base / target).is_file())
    return sorted(seen)


def _tree_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts)


def _feed(digest, label: str, path: Path) -> None:
    digest.update(f"{label}\0{path}\0".encode())
    try:
        digest.update(path.read_bytes())
    except OSError:
        digest.update(b"\0missing\0")
    digest.update(b"\0")


def cache_key(root: str | Path, inputs: Inputs | None = None) -> str:
    """The SHA-256 over every input that decides what `root` compiles to."""
    inputs = inputs or live_inputs()
    digest = hashlib.sha256()
    digest.update(f"format {FORMAT}\0python {sys.version}\0root {root}\0".encode())
    digest.update(f"import path {inputs.import_path!r}\0".encode())
    for path in _import_closure(Path(root), inputs):
        _feed(digest, "doc", path)
    for path in _tree_files(inputs.stdlib_dir):
        _feed(digest, "stdlib", path)
    for path in _tree_files(inputs.package_dir):
        _feed(digest, "revl", path)
    names = sorted(p.stem for p in inputs.backends_python.glob("*.py"))
    digest.update(f"backends/python {names!r}\0".encode())
    return digest.hexdigest()


def _read(path: Path, key: str) -> tuple[bytes, dict] | None:
    """The stored bytes and the IR they hold, or None for a miss."""
    try:
        blob = path.read_bytes()
        stored_key, ir = pickle.loads(blob)
    except Exception:  # noqa: BLE001 - a bad file is a miss, never an error
        return None
    return (blob, ir) if stored_key == key else None


def _write(directory: Path, prefix: str, path: Path, blob: bytes) -> None:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=path.name, suffix=".tmp")
    except OSError:
        return
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(blob)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return
    # An older build of the same document is never read again: its key named
    # sources that have since changed. Dropping it keeps one file per
    # document. A worker still on the old key only misses.
    for stale in directory.glob(f"{prefix}-*.pickle"):
        if stale != path:
            try:
                stale.unlink()
            except OSError:
                pass


def _compile_files(root: Path) -> dict:
    from revl import compile_files  # noqa: PLC0415
    return compile_files([str(root)])


def compiled_ir(root: str | Path,
                compile: Callable[[Path], dict] = _compile_files,
                inputs: Inputs | None = None) -> dict:
    """`compile_files([str(root)])`, built once per key; a fresh copy per call."""
    root = Path(root)
    key = cache_key(root, inputs)
    blob = _memory.get(key)
    if blob is not None:
        return pickle.loads(blob)[1]
    # The file name: the document's stem and path as given, then the key.
    where = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    prefix = f"{root.stem}-{where}"
    disk = _cache_dir / f"{prefix}-{key[:32]}.pickle" if _cache_dir else None
    stored = _read(disk, key) if disk is not None else None
    if stored is not None:
        _memory[key] = stored[0]
        return stored[1]
    blob = pickle.dumps((key, compile(root)), protocol=pickle.HIGHEST_PROTOCOL)
    if disk is not None:
        _write(_cache_dir, prefix, disk, blob)
    _memory[key] = blob
    return pickle.loads(blob)[1]
