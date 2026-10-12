"""`revl mcp serve --print-config` and the doctor line for it (issue #2281).

The config block is only worth printing if the interpreter it names can import
both revl and cordis when the CLIENT starts it, which is with the block's `env`
and nothing from the shell that ran `--print-config`. So the probe must not
inherit PYTHONPATH, and the end-to-end test runs the printed command with
exactly the printed env. The CLI runs in a subprocess with a stub `cordis`
package reachable only through PYTHONPATH, which is the source-checkout case
that has to come out as an `env` key. The other cases inject the probe.
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
from revl.cli.parser import build_parser  # noqa: E402
from revl.doctor import OK, WARN, ProbeResult  # noqa: E402
from revl.mcp import print_config, runtime_gate  # noqa: E402


def _stub_cordis(tmp_path):
    pkg = tmp_path / "stubs" / "cordis"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    return tmp_path / "stubs"


def _shell_env(stubs):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(stubs), str(ROOT / "src")]
        + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    return env


def _print_config(tmp_path, *extra):
    stubs = _stub_cordis(tmp_path)
    proc = subprocess.Popen(
        [sys.executable, "-P", "-m", "revl", "mcp", "serve", "--print-config", *extra],
        cwd=tmp_path, env=_shell_env(stubs), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        # stdin stays open and nothing is written: a server would block here.
        out, err = proc.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise AssertionError("--print-config did not exit: it is serving")
    return proc.returncode, out, err, stubs


def test_print_config_prints_a_valid_block_and_exits_without_serving(tmp_path):
    code, out, err, _ = _print_config(tmp_path)
    assert code == 0, err
    entry = json.loads(out)["mcpServers"]["revl"]
    assert set(entry) <= {"command", "args", "env"}
    assert entry["args"][:5] == ["-P", "-m", "revl", "mcp", "serve"]
    assert entry["args"][5:] == ["--root", os.path.realpath(tmp_path)]


def test_print_config_paths_are_absolute(tmp_path):
    code, out, err, _ = _print_config(tmp_path, "--root", "relative/dir")
    assert code == 0, err
    entry = json.loads(out)["mcpServers"]["revl"]
    assert os.path.isabs(entry["command"]) and Path(entry["command"]).is_file()
    root = entry["args"][entry["args"].index("--root") + 1]
    assert root == os.path.join(os.path.realpath(tmp_path), "relative", "dir")
    for entry_path in entry.get("env", {}).get("PYTHONPATH", "/x").split(os.pathsep):
        assert os.path.isabs(entry_path)


def test_an_env_key_appears_exactly_when_the_interpreter_needs_the_shells_path(tmp_path):
    """Here cordis is reachable through the shell's PYTHONPATH (a stub), and on
    a box with the real runtime installed it is reachable without. The block
    must carry the path itself in the first case and no env in the second,
    never rely on the client inheriting the shell."""
    code, out, err, stubs = _print_config(tmp_path)
    assert code == 0, err
    entry = json.loads(out)["mcpServers"]["revl"]
    bare = subprocess.run([entry["command"], *print_config.PROBE],
                          env={}, capture_output=True).returncode == 0
    if bare:
        assert "env" not in entry
    else:
        assert list(entry["env"]) == ["PYTHONPATH"]
        assert str(stubs) in entry["env"]["PYTHONPATH"].split(os.pathsep)


def test_the_printed_command_works_with_exactly_the_printed_env(tmp_path):
    code, out, err, _ = _print_config(tmp_path)
    assert code == 0, err
    entry = json.loads(out)["mcpServers"]["revl"]
    env = dict(entry.get("env", {}))  # nothing else inherited
    probe = subprocess.run([entry["command"], "-P", "-c", "import cordis, revl"],
                           env=env, capture_output=True, text=True, timeout=120)
    assert probe.returncode == 0, probe.stderr
    again = subprocess.run([entry["command"], *entry["args"], "--print-config"],
                           env=env, cwd=tmp_path, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=120)
    assert again.returncode == 0, again.stderr
    assert json.loads(again.stdout) == json.loads(out)


def test_the_probe_ignores_the_shells_pythonpath(tmp_path):
    (tmp_path / "zz_probe_only_mod.py").write_text("")
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    argv = [sys.executable, *print_config.PROBE[:-1], "import zz_probe_only_mod"]
    assert subprocess.run(argv, env=env, capture_output=True).returncode != 0
    plain = [sys.executable, "-c", "import zz_probe_only_mod"]
    assert subprocess.run(plain, env=env, capture_output=True).returncode == 0


def test_the_gate_probe_inherits_the_environment_reexec_uses(tmp_path, monkeypatch):
    """`reexec` runs the venv with this process's environment, so a venv that
    reaches revl and cordis through PYTHONPATH qualifies for the gate. Only the
    client config probe drops it."""
    stubs = _stub_cordis(tmp_path)
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(stubs), str(ROOT / "src")]))
    assert "-E" not in runtime_gate.GATE_PROBE
    assert runtime_gate.venv_has_cordis(Path(sys.executable))
    bare = subprocess.run([sys.executable, *print_config.PROBE],
                          env={}, capture_output=True).returncode == 0
    assert print_config.runs_ok(print_config.probe_argv(Path(sys.executable))) == bare


def test_doctor_runtime_row_probes_like_the_gate(tmp_path):
    class Seen(doctor.Prober):
        argvs = []

        def module_available(self, name):
            return False

        def run(self, argv, timeout=doctor.PROBE_TIMEOUT, stdin=""):
            self.argvs.append(list(argv))
            return ProbeResult(found=True, returncode=1)

    doctor.check_mcp_runtime(Seen(), tmp_path)
    assert Seen.argvs and Seen.argvs[0][1:] == list(runtime_gate.GATE_PROBE)


# -------------------------------------------------------------- resolution


def _args(*argv):
    return build_parser().parse_args(["mcp", "serve", "--print-config", *argv])


def _checkout(found=True):
    return {"pythonpath": ["/r/src", "/c/src", "/r/backends/python"],
            "cordis": {"found": found, "path": "/c/src", "fetch": None}}


def _config(args, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    code = print_config.run(args, out=out, err=err, **kwargs)
    return code, out.getvalue(), err.getvalue()


def test_no_working_interpreter_is_an_error_not_a_broken_block():
    code, out, err = _config(_args(), options=[Path("/a/python"), Path("/b/python")],
                             ok=lambda argv: False, checkout=_checkout())
    assert code == 1
    assert out == ""
    assert "/a/python" in err and "/b/python" in err and "setup.sh" in err


def test_the_first_candidate_that_imports_both_is_named_without_env():
    code, out, _ = _config(
        _args(), options=[Path("/venv/bin/python"), Path("/sys/python")],
        ok=lambda argv: argv[0] == "/sys/python", checkout=_checkout())
    assert code == 0
    entry = json.loads(out)["mcpServers"]["revl"]
    assert entry["command"] == "/sys/python"
    assert "env" not in entry


def test_a_checkout_only_interpreter_gets_exactly_the_checkout_pythonpath():
    def ok(argv):  # imports both only once the checkout entries are on sys.path
        return "sys.path[:0]" in argv[-1] and "'/c/src'" in argv[-1]

    code, out, _ = _config(_args(), options=[Path("/sys/python")], ok=ok,
                           checkout=_checkout())
    assert code == 0
    entry = json.loads(out)["mcpServers"]["revl"]
    assert entry["env"] == {"PYTHONPATH": os.pathsep.join(_checkout()["pythonpath"])}


def test_a_checkout_without_cordis_is_not_vouched_for():
    code, out, _ = _config(_args(), options=[Path("/sys/python")],
                           ok=lambda argv: "sys.path[:0]" in argv[-1],
                           checkout=_checkout(found=False))
    assert code == 1 and out == ""


# ------------------------------------------------------------ other flags


def test_serve_flags_that_fit_a_config_are_forwarded():
    args = _args("--all-tools", "--grant", "Notify", "--grant", "Mail",
                 "--bind-realm", "A=prod", "--operator-profile", "ops.json",
                 "--author-trust", "trusted", "--root", "/proj")
    code, out, _ = _config(args, options=[Path("/p/python")],
                           ok=lambda argv: True, checkout=None)
    assert code == 0
    argv = json.loads(out)["mcpServers"]["revl"]["args"]
    assert argv[argv.index("--root") + 1] == "/proj"
    assert argv[argv.index("--operator-profile") + 1] == os.path.abspath("ops.json")
    assert argv.count("--grant") == 2 and "Notify" in argv and "Mail" in argv
    assert argv[argv.index("--bind-realm") + 1] == "A=prod"
    assert argv[argv.index("--author-trust") + 1] == "trusted"
    assert "--all-tools" in argv
    assert "--print-config" not in argv


def test_defaults_are_not_forwarded():
    code, out, _ = _config(_args(), options=[Path("/p/python")],
                           ok=lambda argv: True, checkout=None)
    argv = json.loads(out)["mcpServers"]["revl"]["args"]
    assert argv == ["-P", "-m", "revl", "mcp", "serve", "--root", os.getcwd()]


def test_a_listener_flag_is_refused_by_name_not_dropped():
    for flags, name in ((["--http", "127.0.0.1:8000"], "--http"),
                        (["--tls-cert", "c.pem"], "--tls-cert"),
                        (["--allow-host", "h"], "--allow-host")):
        code, out, err = _config(_args(*flags), options=[Path("/p/python")],
                                 ok=lambda argv: True, checkout=None)
        assert code == 1 and out == ""
        assert name in err


def test_a_listener_flag_exits_1_from_the_command_line(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-P", "-m", "revl", "mcp", "serve", "--print-config",
         "--http", "127.0.0.1:8000"],
        cwd=tmp_path, env=_shell_env(_stub_cordis(tmp_path)),
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
    assert proc.returncode == 1 and proc.stdout == ""
    assert "--http" in proc.stderr


# ------------------------------------------------------------------ doctor


class _ProbeImports(doctor.Prober):
    """Interpreters in *good* import both on a plain probe; those in
    *with_path* only once entries are put on sys.path."""

    def __init__(self, good=(), with_path=()):
        self.good = {str(g) for g in good}
        self.with_path = {str(g) for g in with_path}

    def module_origin(self, name):  # cordis is only where the layout puts it
        return None

    def run(self, argv, timeout=doctor.PROBE_TIMEOUT, stdin=""):
        plain = tuple(argv[1:]) == print_config.PROBE
        pathed = argv[-1].startswith("import sys; sys.path[:0]")
        ok = (plain and argv[0] in self.good) or (pathed and argv[0] in self.with_path)
        return ProbeResult(found=True, returncode=0 if ok else 1)


def _row(report):
    return next(c for c in report.checks if c.name == "mcp client config")


def _fake_checkout(tmp_path, *, with_cordis):
    repo = tmp_path / "revl"
    (repo / "src" / "revl").mkdir(parents=True)
    (repo / "backends" / "python").mkdir(parents=True)
    if with_cordis:
        (repo / "backends" / "python" / ".cordis-py" / "src" / "cordis").mkdir(parents=True)
    return repo / "backends"


def test_doctor_reports_the_interpreter_print_config_would_name(tmp_path):
    venv = print_config.candidates(tmp_path / "python")[0]
    row = _row(doctor.diagnose(_ProbeImports(good=[venv]), tmp_path))
    assert row.status == OK
    assert str(venv) in row.detail and "--print-config" in row.detail
    assert "PYTHONPATH" not in row.detail


def test_doctor_reports_the_env_a_checkout_needs(tmp_path):
    backends = _fake_checkout(tmp_path, with_cordis=True)
    python = print_config.candidates(backends / "python")[1]
    row = _row(doctor.diagnose(_ProbeImports(with_path=[python]), backends))
    assert row.status == OK
    assert "PYTHONPATH=" in row.detail and str(backends.parent / "src") in row.detail


def test_doctor_warns_when_no_interpreter_imports_both(tmp_path):
    row = _row(doctor.diagnose(_ProbeImports(), tmp_path))
    assert row.status == WARN
    assert "setup.sh" in row.detail
    assert str(tmp_path / "python" / ".venv") in row.detail


def test_doctor_warns_for_a_checkout_that_has_no_cordis(tmp_path):
    backends = _fake_checkout(tmp_path, with_cordis=False)
    python = print_config.candidates(backends / "python")[1]
    row = _row(doctor.diagnose(_ProbeImports(with_path=[python]), backends))
    assert row.status == WARN
