"""`revl mcp serve --print-config` and the doctor line for it (issue #2281).

The config block is only worth printing if the interpreter it names can import
both revl and cordis, so the end-to-end test runs the printed command with the
printed args' import probe. The CLI runs in a subprocess with a stub `cordis`
package on PYTHONPATH, so the answer does not depend on this box having the real
runtime installed. The no-interpreter and doctor cases inject the probe.
"""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl import doctor  # noqa: E402
from revl.doctor import OK, WARN, ProbeResult  # noqa: E402
from revl.mcp import print_config  # noqa: E402


def _stub_cordis(tmp_path):
    pkg = tmp_path / "stubs" / "cordis"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    return tmp_path / "stubs"


def _env(stubs):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(stubs), str(ROOT / "src")] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    return env


def _print_config(tmp_path, *extra):
    stubs = _stub_cordis(tmp_path)
    proc = subprocess.Popen(
        [sys.executable, "-P", "-m", "revl", "mcp", "serve", "--print-config", *extra],
        cwd=tmp_path, env=_env(stubs), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        # stdin stays open and nothing is written: a server would block here.
        out, err = proc.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise AssertionError("--print-config did not exit: it is serving")
    return proc.returncode, out, err, _env(stubs)


def test_print_config_prints_a_valid_block_and_exits_without_serving(tmp_path):
    code, out, err, _ = _print_config(tmp_path)
    assert code == 0, err
    block = json.loads(out)
    entry = block["mcpServers"]["revl"]
    assert set(entry) == {"command", "args"}
    assert entry["args"][:5] == ["-P", "-m", "revl", "mcp", "serve"]
    assert entry["args"][5:] == ["--root", os.path.realpath(tmp_path)]


def test_print_config_paths_are_absolute(tmp_path):
    code, out, err, _ = _print_config(tmp_path, "--root", "relative/dir")
    assert code == 0, err
    entry = json.loads(out)["mcpServers"]["revl"]
    assert os.path.isabs(entry["command"]) and Path(entry["command"]).is_file()
    assert entry["args"][entry["args"].index("--root") + 1] == os.path.join(
        os.path.realpath(tmp_path), "relative", "dir")
    assert all(os.path.isabs(a) for a in entry["args"][entry["args"].index("--root") + 1::2])


def test_the_printed_command_imports_revl_and_cordis(tmp_path):
    code, out, err, env = _print_config(tmp_path)
    assert code == 0, err
    command = json.loads(out)["mcpServers"]["revl"]["command"]
    probe = subprocess.run([command, *print_config.PROBE], env=env,
                           capture_output=True, text=True, timeout=120)
    assert probe.returncode == 0, probe.stderr


def test_no_working_interpreter_is_an_error_not_a_broken_block():
    out, err = io.StringIO(), io.StringIO()
    code = print_config.run(["/p"], out=out, err=err,
                            options=[Path("/a/python"), Path("/b/python")],
                            can_import=lambda python: False)
    assert code == 1
    assert out.getvalue() == ""
    assert "/a/python" in err.getvalue() and "/b/python" in err.getvalue()
    assert "setup.sh" in err.getvalue()


def test_the_first_candidate_that_imports_both_is_named():
    out = io.StringIO()
    code = print_config.run(["/p"], out=out, err=io.StringIO(),
                            options=[Path("/venv/bin/python"), Path("/sys/python")],
                            can_import=lambda python: str(python) == "/sys/python")
    assert code == 0
    assert json.loads(out.getvalue())["mcpServers"]["revl"]["command"] == "/sys/python"


# ------------------------------------------------------------------ doctor


class _ProbeImports(doctor.Prober):
    """Every interpreter in *good* imports both; any other cannot launch."""

    def __init__(self, good):
        self.good = {str(g) for g in good}
        self.calls = []

    def run(self, argv, timeout=doctor.PROBE_TIMEOUT, stdin=""):
        self.calls.append(list(argv))
        if argv[0] in self.good and tuple(argv[1:]) == print_config.PROBE:
            return ProbeResult(found=True, returncode=0)
        return ProbeResult(found=True, returncode=1)


def test_doctor_reports_the_interpreter_print_config_would_name(tmp_path):
    venv = print_config.candidates(tmp_path / "python")[0]
    report = doctor.diagnose(_ProbeImports([venv]), tmp_path)
    row = next(c for c in report.checks if c.name == "mcp client config")
    assert row.status == OK
    assert str(venv) in row.detail and "--print-config" in row.detail


def test_doctor_warns_when_no_interpreter_imports_both(tmp_path):
    report = doctor.diagnose(_ProbeImports([]), tmp_path)
    row = next(c for c in report.checks if c.name == "mcp client config")
    assert row.status == WARN
    assert "setup.sh" in row.detail
    assert str(tmp_path / "python" / ".venv") in row.detail
