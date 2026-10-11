"""One definition of "the revl version" (issue #2203).

There used to be four, with three different fallbacks. With no installed
metadata (the `PYTHONPATH=src` pattern, a copied source tree), the attestation's
`checker.compiler`, the gate's `language` and the truc reproducer all fell back
to a hard-coded "2.0.0", while `revl doctor` read `pyproject.toml`. After any
version bump they disagreed, and an attestation claimed the wrong compiler.

The first two tests run against a copy of the source tree whose `pyproject.toml` names a
version no literal could match, with the installed `revl` metadata hidden. Every
former implementation, by import path, must report what
`revl._version.version()` reports, and that must be the tree's own version. An
attestation made in that tree must stamp it. The tree's version also beats
stale installed metadata, as an editable install made before a bump has.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# A version the tree's pyproject.toml carries in the copy. No literal fallback
# anywhere in the source can equal it.
BUMPED = "9.8.7.dev2203"

_DRIVER = r'''
import importlib.metadata as md
import json
import sys

_real = md.version


def _hidden(name):
    # The uninstalled case: no `revl` distribution metadata.
    if name == "revl":
        raise md.PackageNotFoundError(name)
    return _real(name)


md.version = _hidden

import revl  # noqa: E402

assert revl.__file__.startswith(sys.argv[1]), revl.__file__

out = {"revl_file": revl.__file__}
try:
    from revl._version import version
    out["single"] = version()
except ImportError as exc:
    out["single"] = "ImportError: %s" % exc

from revl import attest, bundle, doctor, gate  # noqa: E402
from revl.mcp import identity  # noqa: E402
from revl.truc import reproduce  # noqa: E402

out["former"] = {
    "revl.attest.compiler_version": attest.compiler_version(),
    "revl.attest.checker_identity()['compiler']":
        attest.checker_identity()["compiler"],
    "revl.gate._language_version": gate._language_version(),
    "revl.gate.gate_version()['language']": gate.gate_version()["language"],
    "revl.truc.reproduce._toolchain_version": reproduce._toolchain_version(),
    "revl.bundle._toolchain_version": bundle._toolchain_version(),
    "revl.doctor.revl_version": doctor.revl_version(),
    # build_id is `revl-<version>`; strip the prefix to compare the version.
    "revl.mcp.identity.build_id": identity.build_id()[len("revl-"):],
}

src = """
service Database { emission fn execute(sql: Str) -> Int }
service Cache { emission[db] fn put(key: Str, value: Str) }

component PgCache requires db: Database provides cache: Cache {
  provide cache { fn put(key, value) { emit db.execute(`INSERT ${key}`) } }
}
component Front requires cache: Cache { }
"""
verdict = attest.run_gate(source=src, filename="<string>")
att = attest.make_attestation(verdict.ir, b"test-signer-secret-2203",
                              verdict=verdict,
                              now="2026-10-11T00:00:00+00:00")
out["attestation_compiler"] = att["checker"]["compiler"]
ok, reason = attest.verify_attestation(att, b"test-signer-secret-2203",
                                       verdict.ir)
out["attestation_verifies"] = ok
print("RESULT " + json.dumps(out, sort_keys=True))
'''


def _bumped_tree(dest: Path) -> Path:
    """A copy of `src/revl` beside a `pyproject.toml` whose version is
    `BUMPED`. `backends/` and `stdlib/` are linked in, so the copied package
    resolves them as a checkout does."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    bumped, count = re.subn(r'(?m)^version\s*=\s*"[^"]+"',
                            f'version = "{BUMPED}"', text, count=1)
    assert count == 1, "pyproject.toml has no [project] version line"
    (dest / "pyproject.toml").write_text(bumped, encoding="utf-8")
    shutil.copytree(ROOT / "src" / "revl", dest / "src" / "revl",
                    ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("backends", "stdlib"):
        if (ROOT / name).exists():
            (dest / name).symlink_to(ROOT / name, target_is_directory=True)
    return dest / "src"


@pytest.fixture(scope="module")
def uninstalled_result(tmp_path_factory) -> dict:
    tree = tmp_path_factory.mktemp("bumped_tree")
    src = _bumped_tree(tree)
    driver = tree / "driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src)
    env.pop("PYTHONHOME", None)
    proc = subprocess.run(
        [sys.executable, str(driver), str(src.resolve())],
        cwd=str(tree), env=env, capture_output=True, text=True, check=False)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")]
    assert proc.returncode == 0 and lines, (
        f"driver failed (exit {proc.returncode}):\n{proc.stderr[-3000:]}")
    return json.loads(lines[-1][len("RESULT "):])


def test_every_former_implementation_returns_the_single_version(
        uninstalled_result):
    single = uninstalled_result["single"]
    values = {"revl._version.version": single, **uninstalled_result["former"]}
    disagree = {path: value for path, value in values.items()
                if value != BUMPED or value != single}
    assert not disagree, (
        f"every implementation should report the tree's version {BUMPED!r}, "
        f"which is what revl._version.version() reads; these do not: "
        f"{disagree}")


def test_attestation_stamps_the_real_version_not_a_literal(uninstalled_result):
    assert uninstalled_result["attestation_verifies"] is True
    assert uninstalled_result["attestation_compiler"] == BUMPED, (
        f"checker.compiler is {uninstalled_result['attestation_compiler']!r}; "
        f"the tree's version is {BUMPED!r}")


def _stale_metadata(monkeypatch, stale: str) -> None:
    """Installed metadata reporting `stale` for revl, as an editable install
    made before a version bump (or of another checkout) does."""
    import importlib.metadata as md

    real = md.version

    def recorded(name):
        return stale if name == "revl" else real(name)

    monkeypatch.setattr(md, "version", recorded)


def test_tree_pyproject_beats_stale_installed_metadata(monkeypatch, tmp_path):
    """An editable install records its version at install time. When the
    source tree's pyproject.toml says otherwise, the tree is the truth: it is
    what `tools/build_gate_crate.py` stamps into the Rust gate, so the Python
    gate and every attestation must report the same value."""
    from revl import _version, attest, bundle, gate
    from revl.mcp import identity
    from revl.truc import reproduce

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        f'[project]\nname = "revl"\nversion = "{BUMPED}"\n', encoding="utf-8")
    _stale_metadata(monkeypatch, "0.0.1")
    monkeypatch.setattr(_version, "_PYPROJECT", pyproject)

    assert _version.version() == BUMPED
    assert attest.compiler_version() == BUMPED
    assert attest.checker_identity()["compiler"] == BUMPED
    assert gate.gate_version()["language"] == BUMPED
    assert reproduce._toolchain_version() == BUMPED
    assert bundle._toolchain_version() == BUMPED
    assert identity.build_id() == f"revl-{BUMPED}"


def test_doctor_follows_the_tree_when_installed_metadata_is_stale(
        monkeypatch, tmp_path):
    """`revl doctor` printed the editable install's recorded version while
    every other surface reported the tree's, so the doctor header and the
    attestation disagreed after a bump. It must answer through
    `_version.version()` like the rest."""
    from revl import _version, doctor

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        f'[project]\nname = "revl"\nversion = "{BUMPED}"\n', encoding="utf-8")
    _stale_metadata(monkeypatch, "0.0.1")
    monkeypatch.setattr(_version, "_PYPROJECT", pyproject)

    assert doctor.revl_version() == _version.version() == BUMPED
    assert doctor.diagnose().revl_version == BUMPED


def test_doctor_agrees_with_the_single_version_in_a_wheel_layout(
        monkeypatch, tmp_path):
    from revl import _version, doctor

    _stale_metadata(monkeypatch, "3.1.4")
    monkeypatch.setattr(_version, "_PYPROJECT", tmp_path / "pyproject.toml")
    assert doctor.revl_version() == _version.version() == "3.1.4"


def test_wheel_layout_falls_back_to_installed_metadata(monkeypatch, tmp_path):
    """A wheel install has no revl pyproject.toml two levels above the
    package (site-packages/revl/_version.py), so metadata answers there. A
    pyproject.toml of another project at that spot is not revl's version."""
    from revl import _version

    _stale_metadata(monkeypatch, "3.1.4")
    monkeypatch.setattr(_version, "_PYPROJECT", tmp_path / "pyproject.toml")
    assert _version.version() == "3.1.4"
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "other"\nversion = "5.0.0"\n', encoding="utf-8")
    assert _version.version() == "3.1.4"


def test_no_metadata_and_no_revl_pyproject_is_unknown(monkeypatch, tmp_path):
    import importlib.metadata as md

    from revl import _version

    def hidden(name):
        raise md.PackageNotFoundError(name)

    monkeypatch.setattr(md, "version", hidden)
    monkeypatch.setattr(_version, "_PYPROJECT", tmp_path / "pyproject.toml")
    assert _version.version() == "unknown"
    # a pyproject that names another project is not revl's version
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "other"\nversion = "5.0.0"\n', encoding="utf-8")
    assert _version.version() == "unknown"
