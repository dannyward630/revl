"""The revl toolchain version: one definition, one documented fallback chain.

Every place that reports "the revl version" calls :func:`version`: the
attestation's `checker.compiler`, the gate's `gate_version().language`, the
truc reproducer and bundle `toolVersion`, and the MCP build id.

The chain, in order:

1. the `[project].version` of the `pyproject.toml` beside the source tree this
   package was imported from, when that file names the `revl` project. This
   covers a checkout (installed editable or not, or on `PYTHONPATH=src`) and a
   copied source tree;
2. the installed distribution's metadata (`importlib.metadata.version("revl")`);
3. the string ``"unknown"``.

The tree comes first because an editable install records its version at
install time: an editable install made before a bump, or one of another
checkout, would report a stale version. The tree's pyproject.toml is also what
`tools/build_gate_crate.py` stamps into the Rust gate, so reading it first
keeps the Python and Rust gates on the same `language`. A wheel install is
unaffected: `site-packages/revl/_version.py` has no revl pyproject.toml two
levels up (and the name check refuses another project's), so metadata
answers there.

There is deliberately no hard-coded release number here. A literal goes stale
on the next version bump, and a stale value in `checker.compiler` makes a
verifier misjudge which ruleset signed an attestation (issue #2203).

This module imports nothing from revl, so any module may import it without
pulling more of the compiler onto its import chain (see issue #1780).
"""

from __future__ import annotations

from pathlib import Path

UNKNOWN = "unknown"

# `<repo>/pyproject.toml` for a source checkout (`<repo>/src/revl/_version.py`).
# `None` when the package sits too close to the filesystem root to have one.
_here = Path(__file__).resolve()
_PYPROJECT = (_here.parents[2] / "pyproject.toml"
              if len(_here.parents) > 2 else None)


def _metadata_version() -> str | None:
    try:
        from importlib.metadata import PackageNotFoundError  # noqa: PLC0415
        from importlib.metadata import version as dist_version  # noqa: PLC0415
    except ImportError:
        return None
    try:
        return dist_version("revl") or None
    except PackageNotFoundError:
        return None
    except Exception:  # noqa: BLE001 - broken metadata falls through, never fatal
        return None


def _pyproject_version(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        import tomllib  # noqa: PLC0415 - stdlib, py3.11+

        project = tomllib.loads(path.read_text(encoding="utf-8")).get("project")
    except (OSError, ValueError, ImportError):
        return None
    if not isinstance(project, dict) or project.get("name") != "revl":
        return None
    found = project.get("version")
    return found if isinstance(found, str) and found else None


def version() -> str:
    """The revl version: the source tree's `pyproject.toml`, else installed
    metadata, else ``"unknown"``. Never a hard-coded release."""
    return _pyproject_version(_PYPROJECT) or _metadata_version() or UNKNOWN
