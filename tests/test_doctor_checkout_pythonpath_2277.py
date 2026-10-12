"""`revl doctor` prints the PYTHONPATH a source checkout needs (issue #2277).

A checkout is not installed, so booting a composition from it needs three
entries on the path: `<revl>/src`, cordis-py's `src` and `<revl>/backends/python`.
Doctor builds that line from real directories under a fake checkout layout, so
the assertions name real paths and do not depend on this box's own checkout.
"""

import json
import os
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl import doctor  # noqa: E402


class _NoCordisProber(doctor.Prober):
    """The real prober, except that `cordis` is not importable here, so the
    result depends only on the fake layout."""

    def module_origin(self, name):
        return None if name == "cordis" else super().module_origin(name)


def _fake_checkout(tmp_path, *, with_cordis):
    repo = tmp_path / "revl"
    (repo / "src" / "revl").mkdir(parents=True)
    (repo / "backends" / "python").mkdir(parents=True)
    if with_cordis:
        (repo / "backends" / "python" / ".cordis-py" / "src" / "cordis").mkdir(parents=True)
    return repo


def _entries(result):
    return result["export"].split("#")[0].strip().removeprefix("export PYTHONPATH=")


def test_checkout_prints_the_three_real_entries(tmp_path):
    repo = _fake_checkout(tmp_path, with_cordis=True)
    result = doctor.checkout_pythonpath(_NoCordisProber(), repo / "backends", env={})
    want = [str(repo / "src"),
            str(repo / "backends" / "python" / ".cordis-py" / "src"),
            str(repo / "backends" / "python")]
    assert result["pythonpath"] == want
    assert result["export"] == "export PYTHONPATH=" + shlex.quote(os.pathsep.join(want))
    assert result["cordis"] == {"found": True, "path": want[1], "fetch": None}
    assert "#" not in result["export"]
    for entry in want:
        assert Path(entry).is_dir()


def test_missing_cordis_says_where_it_is_expected_and_how_to_fetch(tmp_path):
    repo = _fake_checkout(tmp_path, with_cordis=False)
    result = doctor.checkout_pythonpath(_NoCordisProber(), repo / "backends", env={})
    expected = repo / "backends" / "python" / ".cordis-py" / "src"
    setup = repo / "backends" / "python" / "setup.sh"
    assert result["cordis"] == {"found": False, "path": str(expected),
                                "fetch": f"sh {setup}"}
    assert str(expected) in result["export"]
    assert "cordis-py not found" in result["export"]
    assert f"sh {setup}" in result["export"]


def test_cordis_env_override_is_followed_like_setup_sh(tmp_path):
    repo = _fake_checkout(tmp_path, with_cordis=False)
    other = tmp_path / "elsewhere" / "src" / "cordis"
    other.mkdir(parents=True)
    result = doctor.checkout_pythonpath(
        _NoCordisProber(), repo / "backends", env={"CORDIS_PY": str(tmp_path / "elsewhere")})
    assert result["cordis"]["found"] is True
    assert result["pythonpath"][1] == str(tmp_path / "elsewhere" / "src")


def test_an_installed_wheel_layout_has_nothing_to_export(tmp_path):
    pkg = tmp_path / "site-packages" / "revl"
    (pkg / "backends" / "python").mkdir(parents=True)
    assert doctor.checkout_pythonpath(_NoCordisProber(), pkg / "backends", env={}) is None


def test_diagnose_text_and_json_carry_the_line(tmp_path):
    repo = _fake_checkout(tmp_path, with_cordis=True)
    report = doctor.diagnose(_NoCordisProber(), repo / "backends")
    line = report.checkout["export"]
    assert line in doctor.render_text(report)
    assert doctor.to_json(report)["checkout"]["export"] == line
    assert json.dumps(doctor.to_json(report))


class _CordisAtProber(doctor.Prober):
    """The real prober with `cordis` importable from a chosen file, as in a venv
    where it is installed editable from some other clone."""

    def __init__(self, origin):
        self._origin = origin

    def module_origin(self, name):
        return self._origin if name == "cordis" else super().module_origin(name)


def test_cordis_already_importable_elsewhere_is_used_when_no_clone_exists(tmp_path):
    repo = _fake_checkout(tmp_path, with_cordis=False)
    pkg = tmp_path / "venv-clone" / "src" / "cordis"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    result = doctor.checkout_pythonpath(
        _CordisAtProber(str(pkg / "__init__.py")), repo / "backends", env={})
    assert result["cordis"] == {"found": True,
                                "path": str(tmp_path / "venv-clone" / "src"),
                                "fetch": None}
    assert result["pythonpath"][1] == str(tmp_path / "venv-clone" / "src")
    assert "cordis-py not found" not in result["export"]


def test_relative_cordis_py_resolves_against_backends_python(tmp_path):
    repo = _fake_checkout(tmp_path, with_cordis=False)
    clone = repo / "backends" / "python" / "my-clone" / "src" / "cordis"
    clone.mkdir(parents=True)
    result = doctor.checkout_pythonpath(
        _NoCordisProber(), repo / "backends", env={"CORDIS_PY": "my-clone"})
    assert result["cordis"]["found"] is True
    assert result["pythonpath"][1] == str(repo / "backends" / "python" / "my-clone" / "src")
    # the relative name is not taken against the process's working directory
    missing = doctor.checkout_pythonpath(
        _NoCordisProber(), repo / "backends", env={"CORDIS_PY": "no-such-clone"})
    assert missing["cordis"]["found"] is False
    assert missing["cordis"]["path"] == str(
        repo / "backends" / "python" / "no-such-clone" / "src")
