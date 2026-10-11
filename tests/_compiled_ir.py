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
  * every file of the stdlib directory, read on every call, since the
    compiler reads those from disk when it compiles;
  * the `revl` package the process actually imports (not the tree's
    `src/revl` by name: a test process can import another one), hashed ONCE
    per process (`pin_package` runs in tests/conftest.py's pytest_configure).
    The compile runs the code this process imported, not what is on disk now,
    so the key names that code. If the package changes on disk while the
    session runs (an edit in a worktree), the process stops using the disk
    copy: what it compiles from then on is built by old code, or a mix through
    lazy imports, and must not reach the next session under any key;
  * the module names in `backends/python`, which the compiler reads to refuse
    inline Python that shadows one;
  * `REVL_IMPORT_PATH` itself, the Python version and this file's FORMAT.

Not followed: the model document a `revl gen-types` header names. No document
compiled through here carries one; a caller that compiles one must not use this.
The stdlib and backends directories come from `revl._paths`, so a test that
patches `revl.compiler.stdlib_root` (or `backends_root`) to another tree is not
covered either, and must call `compile_files` itself.

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
# package dir -> {"signature": stat signature at pin, "digest": its hash}.
_package_pin: dict[Path, dict] = {}


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


def _stat_signature(files: list[Path]) -> tuple:
    out = []
    for path in files:
        try:
            st = path.stat()
            out.append((str(path), st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((str(path), None, None))
    return tuple(out)


def pin_package(package_dir: Path) -> None:
    """Record `package_dir` as this process first saw it: the hash of its
    content and the stat signature of its files, both at once.

    The content is hashed here, at session start, not at the first
    `cache_key`: an edit in between that keeps size and mtime (`cp -p`,
    `rsync -t`, `touch -r`) would otherwise be hashed as the new content while
    the process runs the old code. The signature only detects later drift."""
    package_dir = Path(package_dir).resolve()
    if package_dir in _package_pin:
        return
    files = _tree_files(package_dir)
    signature = _stat_signature(files)
    digest = hashlib.sha256()
    for path in files:
        _feed(digest, "revl", path)
    _package_pin[package_dir] = {"signature": signature,
                                 "digest": digest.hexdigest()}


def package_drifted(package_dir: Path) -> bool:
    """Whether `package_dir` changed on disk since it was pinned."""
    package_dir = Path(package_dir).resolve()
    pin_package(package_dir)
    signature = _stat_signature(_tree_files(package_dir))
    return signature != _package_pin[package_dir]["signature"]


def package_digest(package_dir: Path) -> str:
    """The hash of `package_dir`'s files when this process pinned it."""
    package_dir = Path(package_dir).resolve()
    pin_package(package_dir)
    return _package_pin[package_dir]["digest"]


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
    digest.update(f"revl {package_digest(inputs.package_dir)}\0".encode())
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
    inputs = inputs or live_inputs()
    key = cache_key(root, inputs)
    blob = _memory.get(key)
    if blob is not None:
        return pickle.loads(blob)[1]
    # The file name: the document's stem and path as given, then the key.
    where = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    prefix = f"{root.stem}-{where}"
    disk = _cache_dir / f"{prefix}-{key[:32]}.pickle" if _cache_dir else None
    if disk is not None and package_drifted(inputs.package_dir):
        disk = None  # this process's compiler is no longer the one on disk
    stored = _read(disk, key) if disk is not None else None
    if stored is not None:
        _memory[key] = stored[0]
        return stored[1]
    blob = pickle.dumps((key, compile(root)), protocol=pickle.HIGHEST_PROTOCOL)
    if disk is not None:
        _write(_cache_dir, prefix, disk, blob)
    _memory[key] = blob
    return pickle.loads(blob)[1]
