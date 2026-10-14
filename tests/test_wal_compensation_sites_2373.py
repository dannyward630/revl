"""Every compensation site is journalled, on the abort path too (issue #2373).

PR #2372 (issue #2345) made go, rust and java journal a `compensate` called
through a service method the service table marks `emission`, as py's
`_ServiceProxy` does. It reached the activation body, a timer and a plain
provide-method `emit ... compensate ...`, but not the compensation a
computer-use crossing registers inside a UI scope (issue #1369): there the
call was emitted bare, so a crash while it ran left nothing in the WAL.

This file pins the three gaps the issue lists:

1. a compensation inside a UI scope is journalled, on every compiled tier;
2. each compensation site kind (activation body, provide method, UI scope)
   compiles in record mode, on every compiled tier;
3. a real process aborts, runs its compensations, and is killed while one
   of them runs. The kill is deterministic: the provider's own body exits
   with 137 when `REVL_CRASH_AT` names the compensation it was called for.
   The WAL then holds that compensation's start record and no settlement, so
   `unresolved_crossings` names it. The clean control settles every one.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl import wal as wal_core  # noqa: E402
from revl.compiler import compile_source  # noqa: E402

TIERS = ["go", "rust", "java"]
GO = shutil.which("go")
GO_SCENARIOS = ROOT / "backends" / "go" / "scenarios"
RUST_SCENARIO = ROOT / "backends" / "rust" / "scenarios" / "crashproof"
JAVA_DIR = ROOT / "backends" / "java"


def _load_emitter(tier: str):
    spec = importlib.util.spec_from_file_location(
        f"revl_{tier}_emit_2373", ROOT / "backends" / tier / "emit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _emit(tier: str, ir: dict) -> str:
    if tier == "go":
        return _load_emitter("go").emit(ir, "crashrecovery", record=True)
    if tier == "rust":
        return _load_emitter("rust").emit(ir, record=True)
    return _load_emitter("java").emit(ir, "revl", record=True)


def _bodies(go: str, rs: str, java: str) -> str:
    return f"@go {{\n{go}\n}}\n  = @rs {{\n{rs}\n}}\n  = @java {{\n{java}\n}}"


UI_TARGET = """
type UiTarget = {
  application: Str
  window: Str
  role: Str
  name: Str
  evidence: Str
  action: Str
  session: Str
  bounds: Str
  expiry: Int
  confirm: Bool
}
"""

_LOCATE = _bodies(
    '\treturn UiTarget{Application: "a", Window: "w", Role: "r", Name: name}',
    '    UiTarget { application: String::from("a"), window: String::from("w"),'
    ' role: String::from("r"), name: name, evidence: String::new(),'
    ' action: String::new(), session: String::new(), bounds: String::new(),'
    ' expiry: 0, confirm: false }',
    '        return new UiTarget("a", "w", "r", name, "", "", "", "", 0L, false);')
_NOTHING = _bodies("\treturn", "    ()", "        return;")
#: the computer-use crossing that fails, so the UI unit settles
_ACTUATE = _bodies(
    '\tpanic("the substrate could not confirm actuate")',
    '    panic!("the substrate could not confirm actuate")',
    '        throw new RuntimeException("the substrate could not confirm actuate");')
#: the deterministic kill point: exit 137 when REVL_CRASH_AT names `msg`
_CRASH_POINT = _bodies(
    '\tif os.Getenv("REVL_CRASH_AT") == msg {\n\t\tos.Exit(137)\n\t}\n\treturn',
    '    if std::env::var("REVL_CRASH_AT").ok().as_deref() == Some(msg.as_str()) {\n'
    '        std::process::exit(137);\n    }',
    '        if (msg.equals(System.getenv("REVL_CRASH_AT"))) {\n'
    '            Runtime.getRuntime().halt(137);\n        }')

DECLARATIONS = UI_TARGET + f"""
extern emission[ui.find] fn locate(name: Str) -> UiTarget = {_LOCATE}
extern pure fn clear_amount() = {_NOTHING}
extern emission[ui.text] fn type_amount(target: UiTarget, s: Str)
  compensate clear_amount()
  = {_NOTHING}
extern emission[ui.click] fn actuate(target: UiTarget) = {_ACTUATE}
extern emission fn crash_point(msg: Str) = {_CRASH_POINT}

service Log {{
  emission fn write(msg: Str)
  emission fn retract(msg: Str)
}}
service Ops {{
  emission fn ui(region: Str) -> Int
  emission fn plain(region: Str) -> Int
}}
"""

#: One program with every compensation site kind through `log.retract`:
#: the activation body (Caller), a plain provide method (`plain`) and a
#: computer-use crossing in a UI scope (`ui`).
SITES = DECLARATIONS + """
component Logger provides log: Log {
  provide log {
    fn write(msg) {
      emit crash_point("write")
    }
    fn retract(msg) {
      emit crash_point(msg)
    }
  }
}

component Agent requires log: Log provides ops: Ops {
  provide ops {
    fn ui(region) {
      let t = emit locate("Amount")
      emit type_amount(t, region) compensate log.retract("ui")
      return 1
    }
    fn plain(region) {
      emit log.write(region) compensate log.retract("plain")
      return 1
    }
  }
}

component Caller requires log: Log {
  emit log.write("hi") compensate log.retract("activation")
}
"""

#: A journalled compensation start, per tier, for `log.retract`.
RETRACT_START = {
    "go": 'revlJournalEmission("log", "retract", "Log"',
    "rust": 'RevlEmission::start("log", "retract", Some("Log"))',
    "java": 'revlRecordEmissionStart("log", "retract", "Log")',
}
#: The line a UI-scope crossing registers its compensation on, per tier.
UI_CROSS = {
    "go": 'revlUiCrossVoid(_revlUi, "type_amount"',
    "rust": 'revl_ui_cross(&_revl_ui, "type_amount"',
    "java": '_revlUi.crossUnit("type_amount"',
}
#: A `log.retract(<arg>)` call as each tier emits it; the argument tells the
#: three sites apart.
RETRACT_CALL = {"go": 'Retract("{}")', "rust": 'retract(String::from("{}"))',
                "java": 'retract("{}")'}


def _line_with(src: str, needle: str) -> str:
    lines = [line for line in src.splitlines() if needle in line]
    assert len(lines) == 1, (needle, lines)
    return lines[0]


def _journalled_retract(tier: str, src: str, arg: str) -> bool:
    """Whether the `log.retract(<arg>)` compensation is journalled: its own
    emitted line carries the journal start before the call."""
    call = RETRACT_CALL[tier].format(arg)
    line = _line_with(src, call)
    return RETRACT_START[tier] in line and line.index(RETRACT_START[tier]) < line.index(call)


# ---- 1. a UI-scope compensation is journalled -------------------------------


@pytest.mark.parametrize("tier", TIERS)
def test_ui_scope_compensation_is_journalled(tier):
    src = _emit(tier, compile_source(SITES, "sites.rvl"))
    line = _line_with(src, UI_CROSS[tier])
    assert RETRACT_START[tier] in line, line
    assert _journalled_retract(tier, src, "ui")


@pytest.mark.parametrize("tier", TIERS)
def test_every_compensation_site_kind_is_journalled(tier):
    src = _emit(tier, compile_source(SITES, "sites.rvl"))
    for site in ("activation", "plain", "ui"):
        assert _journalled_retract(tier, src, site), site


@pytest.mark.parametrize("tier", TIERS)
def test_a_non_emission_compensation_in_a_ui_scope_is_not_journalled(tier):
    """py's `_ServiceProxy` wraps only `emission` methods, so neither do the
    compiled tiers, in a UI scope as anywhere else."""
    ir = compile_source(SITES, "sites.rvl")
    ir["services"]["Log"]["methods"]["retract"]["emission"] = False
    src = _emit(tier, ir)
    assert RETRACT_START[tier] not in _line_with(src, UI_CROSS[tier])


# ---- 2. every site kind compiles in record mode -----------------------------


def _go_module(tmp_path: Path, src: str, harness: str | None = None) -> Path:
    module = tmp_path / "sites_go"
    module.mkdir()
    for name in ("go.mod", "go.sum"):
        shutil.copy(GO_SCENARIOS / name, module / name)
    pkg = module / "crashproof"
    pkg.mkdir()
    (pkg / "gen_crash_recovery_test.go").write_text(src, encoding="utf-8")
    if harness is not None:
        (pkg / "abort_test.go").write_text(harness, encoding="utf-8")
    out = module / "sites.test"
    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOPROXY": "off"}
    build = subprocess.run([GO, "test", "-c", "-o", str(out), "./crashproof/"],
                           cwd=str(module), capture_output=True, text=True, env=env)
    assert build.returncode == 0, build.stderr
    return out


#: The crashproof crate's manifest under its own package and binary names. A
#: shared CARGO_TARGET_DIR keys cargo's freshness check on the package name,
#: so reusing `revl_crashproof` / `crash_producer` would leave a stale
#: binary for tests/test_rust_crash_recovery.py, or take one from it.
RUST_PACKAGE = "revl_abort_2373"
RUST_BIN = "abort_producer_2373"


def _rust_manifest() -> str:
    text = (RUST_SCENARIO / "Cargo.toml").read_text(encoding="utf-8")
    for old, new in (('name = "revl_crashproof"\nversion', f'name = "{RUST_PACKAGE}"\nversion'),
                     ('name = "crash_producer"', f'name = "{RUST_BIN}"'),
                     ('path = "src/bin/crash_producer.rs"', f'path = "src/bin/{RUST_BIN}.rs"')):
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text


def _rust_crate(tmp_path: Path, src: str, driver: str | None = None) -> Path:
    crate = tmp_path / "sites_rust"
    (crate / "src" / "bin").mkdir(parents=True)
    (crate / "Cargo.toml").write_text(_rust_manifest(), encoding="utf-8")
    (crate / "src" / "bin" / f"{RUST_BIN}.rs").write_text(
        driver if driver is not None else "fn main() {}\n", encoding="utf-8")
    (crate / "src" / "lib.rs").write_text(src, encoding="utf-8")
    target = Path(os.environ.get("CARGO_TARGET_DIR") or (crate / "target"))
    build = subprocess.run(
        ["cargo", "build", "--bin", RUST_BIN, "--manifest-path", str(crate / "Cargo.toml")],
        capture_output=True, text=True, env={**os.environ, "CARGO_TARGET_DIR": str(target)})
    assert build.returncode == 0, build.stderr
    binary = crate / RUST_BIN
    shutil.copy(target / "debug" / RUST_BIN, binary)
    return binary


def _java_classes(tmp_path: Path, src: str, driver: str | None = None) -> tuple[str, str]:
    from revl.run_java import JAVAC_RELEASE, _working_jdk_bin  # noqa: PLC0415
    jdk_bin = Path(_working_jdk_bin())
    gen = tmp_path / "revl"
    gen.mkdir()
    (gen / "Components.java").write_text(src, encoding="utf-8")
    sources = [str(p) for p in (JAVA_DIR / "stubs").rglob("*.java")]
    sources.append(str(gen / "Components.java"))
    if driver is not None:
        (tmp_path / "AbortProducer.java").write_text(driver, encoding="utf-8")
        sources.append(str(tmp_path / "AbortProducer.java"))
    out = tmp_path / "classes"
    out.mkdir()
    compiled = subprocess.run(
        [str(jdk_bin / "javac"), "--release", JAVAC_RELEASE, "-d", str(out), *sources],
        capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    return str(jdk_bin / "java"), str(out)


def _skip_without(tier: str) -> None:
    if tier == "go" and GO is None:
        pytest.skip("go toolchain not available")
    if tier == "rust":
        from revl.run_rust import rust_runtime_reason  # noqa: PLC0415
        reason = rust_runtime_reason()
        if reason is not None:
            pytest.skip(f"cordis-rs runtime not available: {reason}")
    if tier == "java":
        from revl.run_java import java_runtime_reason  # noqa: PLC0415
        reason = java_runtime_reason()
        if reason is not None:
            pytest.skip(f"java runtime unavailable: {reason}")


@pytest.mark.parametrize("tier", TIERS)
def test_every_compensation_site_kind_compiles(tier, tmp_path):
    src = _emit(tier, compile_source(SITES, "sites.rvl"))
    assert _journalled_retract(tier, src, "ui")
    _skip_without(tier)
    if tier == "go":
        _go_module(tmp_path, src)
    elif tier == "rust":
        _rust_crate(tmp_path, src)
    else:
        _java_classes(tmp_path, src)


# ---- 3. the abort path, killed before a compensation settles ----------------

LOGGER = """
component Logger provides log: Log {
  provide log {
    fn write(msg) {
      emit crash_point("write")
    }
    fn retract(msg) {
      emit crash_point(msg)
    }
  }
}
"""

#: The activation emits `log.write` with a compensation and then fails, so it
#: aborts and Phase 2 runs `log.retract("activation")`.
ACTIVATION_ABORT = DECLARATIONS + LOGGER + """
component Caller requires log: Log {
  emit log.write("hi") compensate log.retract("activation")
  fail "the activation fails after its emission"
}
"""

#: Inside the UI scope `type_amount` registers `log.retract("ui")` and
#: `actuate` fails, so the unit settles and runs it before the failure leaves
#: the method.
UI_ABORT = DECLARATIONS + LOGGER + """
component Agent requires log: Log provides ops: Ops {
  provide ops {
    fn ui(region) {
      let t = emit locate("Amount")
      emit type_amount(t, region) compensate log.retract("ui")
      emit actuate(t)
      return 1
    }
    fn plain(region) {
      return 1
    }
  }
}

component Caller requires ops: Ops {
  emit ops.ui("r")
}
"""

#: case (the compensation the abort owes) -> (program, components in load order)
CASES = {
    "activation": (ACTIVATION_ABORT, ["Logger", "Caller"]),
    "ui": (UI_ABORT, ["Logger", "Agent", "Caller"]),
}
DONE = "ABORT-DONE"


def _assert_abort_wal(wal: Path, killed: bool) -> None:
    """The owed `log.retract` ran on the abort path and is journalled. When
    the process was killed inside it, the start record is on disk with no
    settlement and `unresolved_crossings` names it; otherwise it settled."""
    records = wal_core.read_wal(str(wal))["records"]
    starts = [r for r in records
              if r.get("record") == "effect" and r.get("kind") == "emission"]
    retracts = [r for r in starts if r.get("label") == "log.retract"]
    assert len(retracts) == 1, records
    assert retracts[0]["boundary"]["detail"]["service"] == "Log"
    seq = retracts[0]["seq"]
    settled = {r.get("seq") for r in records
               if r.get("record") in ("emission-complete", "emission-failed")}
    unresolved = {u["seq"] for u in wal_core.unresolved_crossings(records)}
    if killed:
        assert seq not in settled and seq in unresolved, records
    else:
        assert {"record": "emission-complete", "seq": seq} in records, records
        assert seq not in unresolved, records


def _run_case(argv: list[str], wal: Path, crash_at: str | None) -> subprocess.CompletedProcess:
    # the compensation budgets are lifted so no run depends on how fast the
    # box is; the only kill is the deterministic one at REVL_CRASH_AT
    env = {"REVL_WAL": str(wal), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "REVL_COMPENSATION_BUDGET_MS": "3600000",
           "REVL_COMPENSATION_PER_CALL_MS": "3600000"}
    if crash_at is not None:
        env["REVL_CRASH_AT"] = crash_at
    return subprocess.run(argv, env=env, capture_output=True, text=True)


def _check_case(argv: list[str], tmp_path: Path, case: str, killed: bool) -> None:
    wal = tmp_path / f"{case}.wal"
    proc = _run_case(argv, wal, case if killed else None)
    output = proc.stdout + proc.stderr
    if killed:
        assert proc.returncode == 137, output
        assert DONE not in output, output
    elif case == "activation":
        # a failed activation is an abort, not a crash
        assert proc.returncode == 0 and DONE in output, output
    else:
        # the UI unit settles, then its failure leaves the method; on go that
        # failure is a panic the composition does not recover
        assert proc.returncode != 137, output
    _assert_abort_wal(wal, killed)


def _go_harness(components: list[str]) -> str:
    lines = ["package crashrecovery", "", "import (", '\tstdctx "context"',
             '\t"testing"', "", '\tstc "github.com/0xdenny218/stc-go"', ")", "",
             "func TestCompensationAbortPath(t *testing.T) {", "\troot := stc.New()"]
    for name in components[:-1]:
        lines += [f"\tif err := Load{name}(root).Ready(stdctx.Background()); err != nil {{",
                  f'\t\tt.Fatalf("boot {name}: %v", err)', "\t}"]
    last = components[-1]
    lines += [f"\tif err := Load{last}(root).Ready(stdctx.Background()); err == nil {{",
              f'\t\tt.Fatalf("{last} activated, but it fails")', "\t}",
              f'\tprintln("{DONE}")', "}", ""]
    return "\n".join(lines)


@pytest.mark.parametrize("killed", [False, True], ids=["settles", "killed"])
@pytest.mark.parametrize("case", sorted(CASES))
def test_go_abort_path_journals_the_compensation(tmp_path, case, killed):
    source, components = CASES[case]
    src = _emit("go", compile_source(source, f"{case}.rvl"))
    _skip_without("go")
    binary = _go_module(tmp_path, src, _go_harness(components))
    _check_case([str(binary), "-test.run", "TestCompensationAbortPath", "-test.v"],
                tmp_path, case, killed)


def _rust_driver(components: list[str]) -> str:
    keys = ", ".join(f'"{name}": {{}}' for name in components)
    lines = ["use std::process::exit;", "", "fn main() {",
             "    let root = cordis::Context::new();",
             f"    let cfg = serde_json::json!({{ {keys} }});"]
    for name in components[:-1]:
        lines += [f'    let f = revl_crashproof::_revl_load(&root, "{name.lower()}", &cfg)'
                  f'.expect("load {name}");',
                  f'    f.try_wait().expect("{name} did not reach ACTIVE");']
    last = components[-1]
    lines += [f'    let f = revl_crashproof::_revl_load(&root, "{last.lower()}", &cfg)'
              f'.expect("load {last}");',
              "    if f.try_wait().is_ok() {",
              f'        eprintln!("{last} activated, but it fails");',
              "        exit(1);", "    }",
              f'    println!("{DONE}");', "}", ""]
    return "\n".join(lines)


@pytest.mark.parametrize("killed", [False, True], ids=["settles", "killed"])
@pytest.mark.parametrize("case", sorted(CASES))
def test_rust_abort_path_journals_the_compensation(tmp_path, case, killed):
    source, components = CASES[case]
    src = _emit("rust", compile_source(source, f"{case}.rvl"))
    _skip_without("rust")
    binary = _rust_crate(tmp_path, src, _rust_driver(components))
    _check_case([str(binary)], tmp_path, case, killed)


def _java_driver(components: list[str]) -> str:
    lines = ["import io.cordis4j.core.Context;", "",
             "public final class AbortProducer {",
             "    public static void main(String[] args) {",
             "        Context root = new Context();"]
    for name in components[:-1]:
        lines.append(f"        new revl.Components.{name}Plugin().apply(root);")
    last = components[-1]
    lines += ["        try {",
              f"            new revl.Components.{last}Plugin().apply(root);",
              f'            System.err.println("{last} activated, but it fails");',
              "            System.exit(1);",
              "        } catch (RuntimeException expected) {",
              "            // the activation failed: its abort ran",
              "        }",
              f'        System.out.println("{DONE}");',
              "    }", "}", ""]
    return "\n".join(lines)


@pytest.mark.parametrize("killed", [False, True], ids=["settles", "killed"])
@pytest.mark.parametrize("case", sorted(CASES))
def test_java_abort_path_journals_the_compensation(tmp_path, case, killed):
    source, components = CASES[case]
    src = _emit("java", compile_source(source, f"{case}.rvl"))
    _skip_without("java")
    java, classes = _java_classes(tmp_path, src, _java_driver(components))
    _check_case([java, "-cp", classes, "AbortProducer"], tmp_path, case, killed)
