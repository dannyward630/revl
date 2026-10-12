"""The host body never runs unless its start record reached disk (issue #2345).

Slice 2 of #2345. The py tier journals every host-extern emission before it
calls the host (`Timeline.record_emission`, backends/python/replay.py) and
settles it with `emission-complete` after (`_call_within`). The go, rust and
java record sinks only wrote witnessed discharge-descriptors, which come after
the mutation, so an `extern emission fn` body ran with nothing on disk.

Each compiled tier now wraps an `extern emission fn` in record mode: the
declared name writes the `effect`/`emission` start record (fsync'd, failing
closed), runs the body, then writes `emission-complete`. The proof is a body
that reads `$REVL_WAL` itself and reports whether its own start record is
already in the file when it runs.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from revl import wal as wal_core  # noqa: E402

SEEN = "START-RECORD-ON-DISK"
NOT_SEEN = "START-RECORD-MISSING"


def _load_emitter(tier: str):
    spec = importlib.util.spec_from_file_location(
        f"revl_{tier}_emit_2345b", ROOT / "backends" / tier / "emit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BODY_KEY = {"go": "go", "rust": "rs", "java": "java"}


def _crashproof_ir(tier: str) -> dict:
    path = ROOT / "backends" / tier / "scenarios" / "crashproof" / "crashproof.ir.json"
    return copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))


def _ir_with_emission(tier: str, body: str) -> dict:
    """The tier's crashproof IR plus one `extern emission fn announce() -> Int`
    the Crasher activation emits before its witnessed effect."""
    ir = _crashproof_ir(tier)
    ir["externs"].append({"name": "announce", "class": "emission", "params": [],
                          "returns": "Int", "bodies": {BODY_KEY[tier]: body}})
    crasher = ir["components"][0]
    crasher["body"].insert(0, {"step": "emit",
                               "expr": {"kind": "fn", "name": "announce", "args": []}})
    return ir


def _records(wal: Path) -> list[dict]:
    return wal_core.read_wal(str(wal))["records"]


def _assert_journalled(wal: Path) -> None:
    records = _records(wal)
    starts = [r for r in records
              if r.get("record") == "effect" and r.get("kind") == "emission"]
    assert len(starts) == 1, records
    assert starts[0]["label"] == "announce"
    assert {"record": "emission-complete", "seq": starts[0]["seq"]} in records
    assert wal_core.unresolved_crossings(records) == []


# ---- go -------------------------------------------------------------------

GO = shutil.which("go")
GO_SCENARIOS = ROOT / "backends" / "go" / "scenarios"
GO_BODY = """
\tlog, _ := os.ReadFile(os.Getenv("REVL_WAL"))
\ttext, needle, seen := string(log), `"kind":"emission"`, false
\tfor i := 0; i+len(needle) <= len(text); i++ {
\t\tseen = seen || text[i:i+len(needle)] == needle
\t}
\tif seen {
\t\tprintln("START-RECORD-ON-DISK")
\t} else {
\t\tprintln("START-RECORD-MISSING")
\t}
\treturn 1
"""


def _go_source() -> str:
    return _load_emitter("go").emit(_ir_with_emission("go", GO_BODY),
                                    "crashrecovery", record=True)


def test_go_emission_extern_is_journalled_before_its_body():
    src = _go_source()
    wrapper = src[src.index("func announce() int64 {"):]
    wrapper = wrapper[:wrapper.index("\n}\n")]
    start = wrapper.index('revlRecordEmissionStart("announce")')
    assert start < wrapper.index("revlEmission_announce()")
    assert wrapper.index("revlEmission_announce()") < wrapper.index(
        'revlRecordEmissionOutcome(_revlEm, "emission-complete")')


@pytest.fixture(scope="module")
def go_producer(tmp_path_factory):
    if GO is None:
        pytest.skip("go toolchain not available; the go start-record proof needs it")
    module = tmp_path_factory.mktemp("emission_go")
    for name in ("go.mod", "go.sum"):
        shutil.copy(GO_SCENARIOS / name, module / name)
    pkg = module / "crashproof"
    pkg.mkdir()
    shutil.copy(GO_SCENARIOS / "crashproof" / "crash_proof_test.go", pkg)
    (pkg / "gen_crash_recovery_test.go").write_text(_go_source(), encoding="utf-8")
    out = module / "crashproof.test"
    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOPROXY": "off"}
    build = subprocess.run([GO, "test", "-c", "-o", str(out), "./crashproof/"],
                           cwd=str(module), capture_output=True, text=True, env=env)
    if build.returncode != 0:
        pytest.fail(f"building the go emission producer failed:\n{build.stderr}")
    return out


def test_go_body_runs_after_its_start_record_is_on_disk(go_producer, tmp_path):
    wal = tmp_path / "go.wal"
    proc = subprocess.run(
        [str(go_producer), "-test.run", "TestGoCrashRecoveryProducer"],
        env={"REVL_WAL": str(wal), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert SEEN in proc.stderr and NOT_SEEN not in proc.stderr, proc.stderr
    _assert_journalled(wal)


# ---- rust -----------------------------------------------------------------

RUST_SCENARIO = ROOT / "backends" / "rust" / "scenarios" / "crashproof"
RUST_BODY = """
    let log = std::fs::read_to_string(std::env::var("REVL_WAL").unwrap_or_default())
        .unwrap_or_default();
    if log.contains("\\"kind\\":\\"emission\\"") {
        eprintln!("START-RECORD-ON-DISK");
    } else {
        eprintln!("START-RECORD-MISSING");
    }
    1
"""
MUTATION = "MUTATION-RAN"


def _rust_source(ir: dict) -> str:
    return _load_emitter("rust").emit(ir, record=True)


def _rust_crate(tmp_path_factory, label: str, ir: dict) -> Path:
    """Build the crashproof producer crate around a freshly emitted lib."""
    from revl.run_rust import rust_runtime_reason  # noqa: PLC0415
    reason = rust_runtime_reason()
    if reason is not None:
        pytest.skip(f"cordis-rs runtime not available; the rust proof needs it: {reason}")
    crate = tmp_path_factory.mktemp(label)
    shutil.copy(RUST_SCENARIO / "Cargo.toml", crate / "Cargo.toml")
    shutil.copytree(RUST_SCENARIO / "src" / "bin", crate / "src" / "bin")
    (crate / "src" / "lib.rs").write_text(_rust_source(ir), encoding="utf-8")
    target = Path(os.environ.get("CARGO_TARGET_DIR") or (crate / "target"))
    build = subprocess.run(
        ["cargo", "build", "--bin", "crash_producer",
         "--manifest-path", str(crate / "Cargo.toml")],
        capture_output=True, text=True, env={**os.environ, "CARGO_TARGET_DIR": str(target)})
    if build.returncode != 0:
        pytest.fail(f"building the rust producer failed:\n{build.stderr}")
    binary = target / "debug" / "crash_producer"
    out = crate / "crash_producer"
    shutil.copy(binary, out)
    return out


def _run_rust(binary: Path, wal: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(binary)],
                          env={"REVL_WAL": wal, "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                          capture_output=True, text=True)


def test_rust_emission_extern_is_journalled_before_its_body():
    src = _rust_source(_ir_with_emission("rust", RUST_BODY))
    wrapper = src[src.index("fn announce() -> i64 {"):]
    wrapper = wrapper[:wrapper.index("\n}\n")]
    assert wrapper.index('revl_record_emission_start("announce")') < wrapper.index(
        "_revl_emission_announce()")


def test_rust_body_runs_after_its_start_record_is_on_disk(tmp_path_factory, tmp_path):
    binary = _rust_crate(tmp_path_factory, "emission_rust", _ir_with_emission("rust", RUST_BODY))
    wal = tmp_path / "rust.wal"
    proc = _run_rust(binary, str(wal))
    assert proc.returncode == 0, proc.stderr
    assert SEEN in proc.stderr and NOT_SEEN not in proc.stderr, proc.stderr
    _assert_journalled(wal)


def test_rust_sink_opens_before_the_first_mutation(tmp_path_factory):
    """The rust sink used to open on its first record, which follows the first
    witnessed mutation. It now opens when the component is built, so a log
    that refuses fsync (`/dev/null`) stops the run before the mutation."""
    ir = _crashproof_ir("rust")
    begin = next(e for e in ir["externs"] if e["name"] == "beginRow")
    begin["bodies"]["rs"] = '\n    eprintln!("MUTATION-RAN");\n    Ok("row#1".to_string())\n'
    binary = _rust_crate(tmp_path_factory, "eager_rust", ir)
    proc = _run_rust(binary, "/dev/null")
    assert proc.returncode != 0, proc.stderr
    assert "write-ahead log fsync failed" in proc.stderr
    assert MUTATION not in proc.stderr, proc.stderr


# ---- java -----------------------------------------------------------------

JAVA_DIR = ROOT / "backends" / "java"
JAVA_BODY = """
    String log = "";
    try {
        log = new String(java.nio.file.Files.readAllBytes(
                java.nio.file.Paths.get(System.getenv("REVL_WAL"))),
                java.nio.charset.StandardCharsets.UTF_8);
    } catch (java.io.IOException e) {
        log = "";
    }
    System.err.println(log.contains("\\"kind\\":\\"emission\\"")
            ? "START-RECORD-ON-DISK" : "START-RECORD-MISSING");
    return 1L;
"""


def _java_source() -> str:
    return _load_emitter("java").emit(_ir_with_emission("java", JAVA_BODY), "revl", record=True)


def test_java_emission_extern_is_journalled_before_its_body():
    src = _java_source()
    wrapper = src[src.index("public static long announce() {"):]
    wrapper = wrapper[:wrapper.index("\n    }\n")]
    assert wrapper.index('revlRecordEmissionStart("announce")') < wrapper.index(
        "_revl_emission_announce()")


@pytest.fixture(scope="module")
def java_producer(tmp_path_factory):
    from revl.run_java import JAVAC_RELEASE, _working_jdk_bin, java_runtime_reason  # noqa: PLC0415
    reason = java_runtime_reason()
    if reason is not None:
        pytest.skip(f"java runtime unavailable; the java start-record proof needs it: {reason}")
    jdk_bin = Path(_working_jdk_bin())
    work = tmp_path_factory.mktemp("emission_java")
    gen = work / "revl"
    gen.mkdir()
    (gen / "Components.java").write_text(_java_source(), encoding="utf-8")
    out = work / "classes"
    out.mkdir()
    stubs = [str(p) for p in (JAVA_DIR / "stubs").rglob("*.java")]
    compiled = subprocess.run(
        [str(jdk_bin / "javac"), "--release", JAVAC_RELEASE, "-d", str(out), *stubs,
         str(gen / "Components.java"),
         str(JAVA_DIR / "scenarios" / "crashproof" / "CrashProducer.java")],
        capture_output=True, text=True)
    if compiled.returncode != 0:
        pytest.fail(f"compiling the java emission producer failed:\n{compiled.stderr}")
    return str(out), str(jdk_bin / "java")


def test_java_body_runs_after_its_start_record_is_on_disk(java_producer, tmp_path):
    classpath, java = java_producer
    wal = tmp_path / "java.wal"
    proc = subprocess.run([java, "-cp", classpath, "CrashProducer"],
                          env={"REVL_WAL": str(wal), "PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert SEEN in proc.stderr and NOT_SEEN not in proc.stderr, proc.stderr
    _assert_journalled(wal)


# ---- py and the wasm drain: a record whose fsync failed is not left behind --


def _fail_fsync(_fd):
    raise OSError("injected fsync failure")


def test_py_record_whose_fsync_failed_is_cut_from_the_file(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "backends" / "python"))
    import replay  # noqa: PLC0415
    path = tmp_path / "run.wal"
    wal = replay.WriteAheadLog(str(path), ir={}, generation=1).open()
    timeline = replay.Timeline("Svc")
    timeline.attach_wal(wal, {})
    before = path.read_bytes()
    monkeypatch.setattr(replay.os, "fsync", _fail_fsync)
    with pytest.raises(replay.ReplayError, match="fsync failed"):
        timeline.record_emission("db", "send", (), None, ("test", 1))
    wal.close()
    assert path.read_bytes() == before
    assert [r["record"] for r in _records(path)] == []


def test_wasm_record_whose_fsync_failed_is_cut_from_the_file(tmp_path, monkeypatch):
    from revl import run_wasm  # noqa: PLC0415
    path = tmp_path / "run.wal"
    with open(path, "w", encoding="utf-8") as handle:
        run_wasm.write_wal_record(handle, run_wasm.wal_header())
        before = path.read_bytes()
        monkeypatch.setattr(run_wasm.os, "fsync", _fail_fsync)
        monkeypatch.delenv("REVL_WAL_ALLOW_UNSYNCED", raising=False)
        with pytest.raises(run_wasm.WALDurabilityError):
            run_wasm.write_wal_record(handle, run_wasm.wal_discharge([0]))
        monkeypatch.undo()
        # the next record lands right after the header, with no gap
        run_wasm.write_wal_record(handle, run_wasm.wal_activation_complete())
    assert path.read_bytes().startswith(before)
    assert [r["record"] for r in _records(path)] == ["activation-complete"]
