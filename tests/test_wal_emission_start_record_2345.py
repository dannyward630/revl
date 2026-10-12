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

Slice 3 journals an `emit` through a required service the same way (the py
`_ServiceProxy` path), settles a body that panics or throws with
`emission-failed` (py `_call_within`), and fsyncs the cut py and the wasm
drain make after a failed fsync, so the cut record cannot come back.
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
    start = wrapper.index('revlRecordEmissionStart("announce", "announce", "")')
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
    assert wrapper.index('RevlEmission::start("announce", "announce", None)') < wrapper.index(
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
    assert wrapper.index('revlRecordEmissionStart("announce", "announce", null)') < wrapper.index(
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


# ---- slice 3: emissions through a required service --------------------------
#
# py journals a call through a required service in `_ServiceProxy` (the same
# `record_emission` + `_call_within` pair). The compiled tiers journal the
# `emit` site itself: start record, then the call, then its outcome.


def _ir_with_service_emission(tier: str) -> dict:
    """The tier's crashproof IR, with the Crasher requiring `log: Log` and
    emitting `log.write("hi")` before its witnessed effect."""
    ir = _crashproof_ir(tier)
    ir["services"]["Log"] = {"methods": {"write": {
        "params": [{"name": "msg", "type": "Str"}], "returns": None, "emission": True}}}
    crasher = ir["components"][0]
    crasher["requires"] = {"log": "Log"}
    crasher["body"].insert(0, {"step": "emit", "expr": {
        "kind": "call", "target": {"kind": "req", "name": "log"}, "method": "write",
        "args": [{"kind": "lit", "value": "hi"}]}})
    return ir


def _in_order(src: str, *needles: str) -> None:
    at = [src.index(n) for n in needles]
    assert at == sorted(at), list(zip(needles, at))


def test_go_service_emission_is_journalled_before_the_call():
    src = _load_emitter("go").emit(_ir_with_service_emission("go"), "crashrecovery",
                                   record=True)
    site = 'revlJournalEmission("log", "write", "Log", func() { log.Write("hi") })'
    assert site in src
    body = src[src.index("func revlJournalEmission("):]
    body = body[:body.index("\n}\n")]
    _in_order(body, "revlRecordEmissionStart(key, method, service)", "body()",
              'revlRecordEmissionOutcome(seq, "emission-complete")')


def test_rust_service_emission_is_journalled_before_the_call():
    src = _rust_source(_ir_with_service_emission("rust"))
    site = src[src.index('RevlEmission::start("log", "write", Some("Log"))'):]
    site = site[:site.index("\n")]
    _in_order(site, "RevlEmission::start", "log.write(", "_revl_em.complete()")


def test_java_service_emission_is_journalled_before_the_call():
    src = _load_emitter("java").emit(_ir_with_service_emission("java"), "revl",
                                     record=True)
    site = src[src.index('revlRecordEmissionStart("log", "write", "Log")'):]
    site = site[:site.index("\n")]
    _in_order(site, "revlRecordEmissionStart", 'log.write("hi")',
              "revlRecordEmissionFailed(_revlEm, _revlT)",
              'revlRecordEmissionOutcome(_revlEm, "emission-complete")')
    assert "public static int revlRecordEmissionStart(" in src


@pytest.mark.parametrize("tier", ["go", "rust", "java"])
def test_service_emission_classifier(tier):
    """Only a call through a required service (`req` target) or an instance
    provision (`instance-get` receiver) is journalled at the site; an extern
    call is journalled by its own wrapper and a host-local method call is not
    an emission crossing at all."""
    emitter = _load_emitter(tier)
    required = {"kind": "call", "target": {"kind": "req", "name": "log"},
                "method": "write", "args": []}
    provision = {"kind": "call", "args": [], "callee": {
        "kind": "field", "name": "charge", "target": {
            "kind": "instance-get", "target": {"kind": "name", "name": "w"},
            "component": "Wallet", "key": "pay", "service": "Pay"}}}
    local = {"kind": "call", "target": {"kind": "name", "name": "m"},
             "method": "get", "args": []}
    field = {"kind": "call", "args": [], "callee": {
        "kind": "field", "name": "get", "target": {"kind": "name", "name": "r"}}}
    extern = {"kind": "call", "args": [], "callee": {"kind": "var", "name": "announce"}}
    if tier == "go":
        emitter._REQ_SERVICE = {"log": "Log"}
        assert emitter._service_emission(required) == ("log", "write", "Log")
        assert emitter._service_emission(provision) == ("pay", "charge", "Pay")
        for node in (local, field, extern):
            assert emitter._service_emission(node) is None
    else:
        assert emitter._service_emission(required, {"log": "Log"}) == ("log", "write", "Log")
        assert emitter._service_emission(provision, {}) == ("pay", "charge", "Pay")
        for node in (local, field, extern):
            assert emitter._service_emission(node, {}) is None


def test_go_service_emission_compiles(tmp_path):
    if GO is None:
        pytest.skip("go toolchain not available")
    module = tmp_path / "svc_go"
    module.mkdir()
    for name in ("go.mod", "go.sum"):
        shutil.copy(GO_SCENARIOS / name, module / name)
    pkg = module / "crashproof"
    pkg.mkdir()
    src = _load_emitter("go").emit(_ir_with_service_emission("go"), "crashrecovery",
                                   record=True)
    assert 'revlJournalEmission("log", "write", "Log"' in src
    (pkg / "gen_crash_recovery_test.go").write_text(src, encoding="utf-8")
    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOPROXY": "off"}
    vet = subprocess.run([GO, "test", "-c", "-o", str(module / "x.test"), "./crashproof/"],
                         cwd=str(module), capture_output=True, text=True, env=env)
    assert vet.returncode == 0, vet.stderr


def test_rust_service_emission_compiles(tmp_path):
    from revl.run_rust import rust_runtime_reason  # noqa: PLC0415
    reason = rust_runtime_reason()
    if reason is not None:
        pytest.skip(f"cordis-rs runtime not available: {reason}")
    crate = tmp_path / "svc_rust"
    (crate / "src").mkdir(parents=True)
    shutil.copy(RUST_SCENARIO / "Cargo.toml", crate / "Cargo.toml")
    shutil.copytree(RUST_SCENARIO / "src" / "bin", crate / "src" / "bin")
    src = _rust_source(_ir_with_service_emission("rust"))
    assert 'RevlEmission::start("log", "write", Some("Log"))' in src
    (crate / "src" / "lib.rs").write_text(src, encoding="utf-8")
    target = Path(os.environ.get("CARGO_TARGET_DIR") or (crate / "target"))
    build = subprocess.run(
        ["cargo", "build", "--lib", "--manifest-path", str(crate / "Cargo.toml")],
        capture_output=True, text=True, env={**os.environ, "CARGO_TARGET_DIR": str(target)})
    assert build.returncode == 0, build.stderr


def test_java_service_emission_compiles(tmp_path):
    from revl.run_java import JAVAC_RELEASE, _working_jdk_bin, java_runtime_reason  # noqa: PLC0415
    reason = java_runtime_reason()
    if reason is not None:
        pytest.skip(f"java runtime unavailable: {reason}")
    jdk_bin = Path(_working_jdk_bin())
    gen = tmp_path / "revl"
    gen.mkdir()
    src = _load_emitter("java").emit(_ir_with_service_emission("java"), "revl", record=True)
    assert 'revlRecordEmissionStart("log", "write", "Log")' in src
    (gen / "Components.java").write_text(src, encoding="utf-8")
    out = tmp_path / "classes"
    out.mkdir()
    stubs = [str(p) for p in (JAVA_DIR / "stubs").rglob("*.java")]
    compiled = subprocess.run(
        [str(jdk_bin / "javac"), "--release", JAVAC_RELEASE, "-d", str(out), *stubs,
         str(gen / "Components.java")], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr


# ---- slice 3: a body that fails writes `emission-failed` ---------------------


def _assert_failed(wal: Path) -> None:
    records = _records(wal)
    starts = [r for r in records
              if r.get("record") == "effect" and r.get("kind") == "emission"]
    assert len(starts) == 1, records
    failed = [r for r in records if r.get("record") == "emission-failed"]
    assert len(failed) == 1 and failed[0]["seq"] == starts[0]["seq"], records
    assert failed[0]["error"]["type"], failed
    assert not any(r.get("record") == "emission-complete" for r in records)
    # still unresolved, as py leaves a failed emission
    assert [c["seq"] for c in wal_core.unresolved_crossings(records)] == [starts[0]["seq"]]


def test_go_body_that_panics_writes_emission_failed(tmp_path):
    if GO is None:
        pytest.skip("go toolchain not available")
    module = tmp_path / "fail_go"
    module.mkdir()
    for name in ("go.mod", "go.sum"):
        shutil.copy(GO_SCENARIOS / name, module / name)
    pkg = module / "crashproof"
    pkg.mkdir()
    shutil.copy(GO_SCENARIOS / "crashproof" / "crash_proof_test.go", pkg)
    (pkg / "gen_crash_recovery_test.go").write_text(_load_emitter("go").emit(
        _ir_with_emission("go", '\n\tpanic("boom")\n'), "crashrecovery", record=True),
        encoding="utf-8")
    out = module / "crashproof.test"
    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOPROXY": "off"}
    build = subprocess.run([GO, "test", "-c", "-o", str(out), "./crashproof/"],
                           cwd=str(module), capture_output=True, text=True, env=env)
    assert build.returncode == 0, build.stderr
    wal = tmp_path / "go.wal"
    proc = subprocess.run([str(out), "-test.run", "TestGoCrashRecoveryProducer"],
                          env={"REVL_WAL": str(wal), "PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True)
    assert proc.returncode != 0 and "boom" in proc.stdout + proc.stderr
    _assert_failed(wal)


def test_rust_body_that_panics_writes_emission_failed(tmp_path_factory, tmp_path):
    binary = _rust_crate(tmp_path_factory, "fail_rust",
                         _ir_with_emission("rust", '\n    panic!("boom")\n'))
    wal = tmp_path / "rust.wal"
    proc = _run_rust(binary, str(wal))
    assert proc.returncode != 0 and "boom" in proc.stderr, proc.stderr
    _assert_failed(wal)


def test_java_body_that_throws_writes_emission_failed(tmp_path):
    from revl.run_java import JAVAC_RELEASE, _working_jdk_bin, java_runtime_reason  # noqa: PLC0415
    reason = java_runtime_reason()
    if reason is not None:
        pytest.skip(f"java runtime unavailable: {reason}")
    jdk_bin = Path(_working_jdk_bin())
    gen = tmp_path / "revl"
    gen.mkdir()
    (gen / "Components.java").write_text(_load_emitter("java").emit(
        _ir_with_emission("java", '\n    throw new IllegalStateException("boom");\n'),
        "revl", record=True), encoding="utf-8")
    out = tmp_path / "classes"
    out.mkdir()
    stubs = [str(p) for p in (JAVA_DIR / "stubs").rglob("*.java")]
    compiled = subprocess.run(
        [str(jdk_bin / "javac"), "--release", JAVAC_RELEASE, "-d", str(out), *stubs,
         str(gen / "Components.java"),
         str(JAVA_DIR / "scenarios" / "crashproof" / "CrashProducer.java")],
        capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    wal = tmp_path / "java.wal"
    proc = subprocess.run([str(jdk_bin / "java"), "-cp", str(out), "CrashProducer"],
                          env={"REVL_WAL": str(wal), "PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True)
    assert proc.returncode != 0 and "boom" in proc.stderr, proc.stdout + proc.stderr
    _assert_failed(wal)
    assert [r for r in _records(wal) if r.get("record") == "emission-failed"][0][
        "error"] == {"type": "IllegalStateException"}


# ---- slice 3: the cut is fsynced, so the record cannot come back -------------


def _fsync_log(monkeypatch, module, calls: list) -> None:
    """The record's fsync fails; every call (and each ftruncate) is logged."""
    def fsync(_fd):
        calls.append("fsync")
        if calls.count("fsync") == 1:
            raise OSError("injected fsync failure")

    real_truncate = os.ftruncate

    def ftruncate(fd, length):
        calls.append("ftruncate")
        real_truncate(fd, length)
    monkeypatch.setattr(module.os, "fsync", fsync)
    monkeypatch.setattr(module.os, "ftruncate", ftruncate)


def test_py_cut_is_fsynced(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "backends" / "python"))
    import replay  # noqa: PLC0415
    path = tmp_path / "run.wal"
    wal = replay.WriteAheadLog(str(path), ir={}, generation=1).open()
    timeline = replay.Timeline("Svc")
    timeline.attach_wal(wal, {})
    calls: list = []
    _fsync_log(monkeypatch, replay, calls)
    with pytest.raises(replay.ReplayError, match="fsync failed"):
        timeline.record_emission("db", "send", (), None, ("test", 1))
    monkeypatch.undo()
    wal.close()
    assert calls == ["fsync", "ftruncate", "fsync"]


def test_wasm_cut_is_fsynced(tmp_path, monkeypatch):
    from revl import run_wasm  # noqa: PLC0415
    path = tmp_path / "run.wal"
    calls: list = []
    with open(path, "w", encoding="utf-8") as handle:
        run_wasm.write_wal_record(handle, run_wasm.wal_header())
        monkeypatch.delenv("REVL_WAL_ALLOW_UNSYNCED", raising=False)
        _fsync_log(monkeypatch, run_wasm, calls)
        with pytest.raises(run_wasm.WALDurabilityError):
            run_wasm.write_wal_record(handle, run_wasm.wal_discharge([0]))
        monkeypatch.undo()
    assert calls == ["fsync", "ftruncate", "fsync"]


# ---- slice 4: the compiled sinks cut a record they could not make durable ----
#
# A file-size limit (RLIMIT_FSIZE, with SIGXFSZ ignored) makes the second
# record's write fail part way, a real fault that leaves a torn record behind
# unless the sink cuts it. The cut is the same `cut` the sink runs after a
# failed fsync.


def _limited(limit: int):
    def preexec():
        import resource  # noqa: PLC0415
        import signal  # noqa: PLC0415
        signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
    return preexec


def _go_build(tmp_path: Path, ir: dict) -> Path:
    if GO is None:
        pytest.skip("go toolchain not available")
    module = tmp_path / "go_mod"
    module.mkdir()
    for name in ("go.mod", "go.sum"):
        shutil.copy(GO_SCENARIOS / name, module / name)
    pkg = module / "crashproof"
    pkg.mkdir()
    shutil.copy(GO_SCENARIOS / "crashproof" / "crash_proof_test.go", pkg)
    (pkg / "gen_crash_recovery_test.go").write_text(
        _load_emitter("go").emit(ir, "crashrecovery", record=True), encoding="utf-8")
    out = module / "crashproof.test"
    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOPROXY": "off"}
    build = subprocess.run([GO, "test", "-c", "-o", str(out), "./crashproof/"],
                           cwd=str(module), capture_output=True, text=True, env=env)
    assert build.returncode == 0, build.stderr
    return out


def _java_build(tmp_path: Path, ir: dict) -> tuple[str, str]:
    from revl.run_java import JAVAC_RELEASE, _working_jdk_bin, java_runtime_reason  # noqa: PLC0415
    reason = java_runtime_reason()
    if reason is not None:
        pytest.skip(f"java runtime unavailable: {reason}")
    jdk_bin = Path(_working_jdk_bin())
    gen = tmp_path / "revl"
    gen.mkdir()
    (gen / "Components.java").write_text(
        _load_emitter("java").emit(ir, "revl", record=True), encoding="utf-8")
    out = tmp_path / "classes"
    out.mkdir()
    stubs = [str(p) for p in (JAVA_DIR / "stubs").rglob("*.java")]
    compiled = subprocess.run(
        [str(jdk_bin / "javac"), "--release", JAVAC_RELEASE, "-d", str(out), *stubs,
         str(gen / "Components.java"),
         str(JAVA_DIR / "scenarios" / "crashproof" / "CrashProducer.java")],
        capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    return str(out), str(jdk_bin / "java")


def _assert_torn_record_is_cut(run, tmp_path: Path) -> None:
    """Run once unlimited to learn where the second record starts, then again
    with the file limited to a few bytes past that point."""
    full = tmp_path / "full.wal"
    first = run(full, None)
    assert first.returncode == 0, first.stdout + first.stderr
    lines = full.read_bytes().split(b"\n")
    assert len(lines) > 2, lines
    header_end = len(lines[0]) + 1
    wal = tmp_path / "torn.wal"
    proc = run(wal, header_end + 7)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "write-ahead log write failed" in proc.stdout + proc.stderr
    # the torn second record was cut: the file is exactly the header
    assert wal.read_bytes() == lines[0] + b"\n"


def test_go_sink_cuts_a_record_it_could_not_write(tmp_path):
    binary = _go_build(tmp_path, _crashproof_ir("go"))

    def run(wal, limit):
        return subprocess.run(
            [str(binary), "-test.run", "TestGoCrashRecoveryProducer"],
            env={"REVL_WAL": str(wal), "PATH": "/usr/bin:/bin"},
            capture_output=True, text=True,
            preexec_fn=_limited(limit) if limit else None)
    _assert_torn_record_is_cut(run, tmp_path)


def test_rust_sink_cuts_a_record_it_could_not_write(tmp_path_factory, tmp_path):
    binary = _rust_crate(tmp_path_factory, "cut_rust", _crashproof_ir("rust"))

    def run(wal, limit):
        return subprocess.run(
            [str(binary)],
            env={"REVL_WAL": str(wal), "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            capture_output=True, text=True,
            preexec_fn=_limited(limit) if limit else None)
    _assert_torn_record_is_cut(run, tmp_path)


def test_java_sink_cuts_a_record_it_could_not_write(tmp_path):
    classpath, java = _java_build(tmp_path, _crashproof_ir("java"))

    def run(wal, limit):
        return subprocess.run(
            [java, "-XX:-UsePerfData", "-Xshare:off", "-cp", classpath, "CrashProducer"],
            env={"REVL_WAL": str(wal), "PATH": "/usr/bin:/bin"},
            capture_output=True, text=True,
            preexec_fn=_limited(limit) if limit else None)
    _assert_torn_record_is_cut(run, tmp_path)


# ---- slice 4: a compensation through a service emission method --------------


def _ir_with_service_compensation(tier: str, compensate: str) -> dict:
    """`emit log.write("hi") compensate log.<compensate>("hi")`: `retract` is
    an `emission` method, `note` is not."""
    ir = _ir_with_service_emission(tier)
    ir["services"]["Log"]["methods"]["retract"] = {
        "params": [{"name": "msg", "type": "Str"}], "returns": None, "emission": True}
    ir["services"]["Log"]["methods"]["note"] = {
        "params": [{"name": "msg", "type": "Str"}], "returns": None, "emission": False}
    ir["components"][0]["body"][0]["compensate"] = {
        "kind": "call", "target": {"kind": "req", "name": "log"}, "method": compensate,
        "args": [{"kind": "lit", "value": "hi"}]}
    return ir


SERVICE_START = {
    "go": 'revlJournalEmission("log", "{m}", "Log"',
    "rust": 'RevlEmission::start("log", "{m}", Some("Log"))',
    "java": 'revlRecordEmissionStart("log", "{m}", "Log")',
}


def _emit_tier(tier: str, ir: dict) -> str:
    if tier == "go":
        return _load_emitter("go").emit(ir, "crashrecovery", record=True)
    if tier == "rust":
        return _rust_source(ir)
    return _load_emitter("java").emit(ir, "revl", record=True)


@pytest.mark.parametrize("tier", ["go", "rust", "java"])
def test_service_compensation_is_journalled_only_for_an_emission_method(tier):
    src = _emit_tier(tier, _ir_with_service_compensation(tier, "retract"))
    assert SERVICE_START[tier].format(m="retract") in src
    src = _emit_tier(tier, _ir_with_service_compensation(tier, "note"))
    assert SERVICE_START[tier].format(m="write") in src
    assert SERVICE_START[tier].format(m="note") not in src


def test_go_service_compensation_compiles(tmp_path):
    ir = _ir_with_service_compensation("go", "retract")
    assert SERVICE_START["go"].format(m="retract") in _emit_tier("go", ir)
    if GO is None:
        pytest.skip("go toolchain not available")
    module = tmp_path / "comp_go"
    module.mkdir()
    for name in ("go.mod", "go.sum"):
        shutil.copy(GO_SCENARIOS / name, module / name)
    pkg = module / "crashproof"
    pkg.mkdir()
    (pkg / "gen_crash_recovery_test.go").write_text(_emit_tier("go", ir), encoding="utf-8")
    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOPROXY": "off"}
    build = subprocess.run([GO, "test", "-c", "-o", str(module / "x.test"), "./crashproof/"],
                           cwd=str(module), capture_output=True, text=True, env=env)
    assert build.returncode == 0, build.stderr


def test_rust_service_compensation_compiles(tmp_path):
    from revl.run_rust import rust_runtime_reason  # noqa: PLC0415
    ir = _ir_with_service_compensation("rust", "retract")
    src = _rust_source(ir)
    assert SERVICE_START["rust"].format(m="retract") in src
    reason = rust_runtime_reason()
    if reason is not None:
        pytest.skip(f"cordis-rs runtime not available: {reason}")
    crate = tmp_path / "comp_rust"
    (crate / "src").mkdir(parents=True)
    shutil.copy(RUST_SCENARIO / "Cargo.toml", crate / "Cargo.toml")
    shutil.copytree(RUST_SCENARIO / "src" / "bin", crate / "src" / "bin")
    (crate / "src" / "lib.rs").write_text(src, encoding="utf-8")
    target = Path(os.environ.get("CARGO_TARGET_DIR") or (crate / "target"))
    build = subprocess.run(
        ["cargo", "build", "--lib", "--manifest-path", str(crate / "Cargo.toml")],
        capture_output=True, text=True, env={**os.environ, "CARGO_TARGET_DIR": str(target)})
    assert build.returncode == 0, build.stderr


def test_java_service_compensation_compiles(tmp_path):
    from revl.run_java import JAVAC_RELEASE, _working_jdk_bin, java_runtime_reason  # noqa: PLC0415
    ir = _ir_with_service_compensation("java", "retract")
    src = _emit_tier("java", ir)
    assert SERVICE_START["java"].format(m="retract") in src
    reason = java_runtime_reason()
    if reason is not None:
        pytest.skip(f"java runtime unavailable: {reason}")
    jdk_bin = Path(_working_jdk_bin())
    gen = tmp_path / "revl"
    gen.mkdir()
    (gen / "Components.java").write_text(src, encoding="utf-8")
    out = tmp_path / "classes"
    out.mkdir()
    stubs = [str(p) for p in (JAVA_DIR / "stubs").rglob("*.java")]
    compiled = subprocess.run(
        [str(jdk_bin / "javac"), "--release", JAVAC_RELEASE, "-d", str(out), *stubs,
         str(gen / "Components.java")], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr


# ---- slice 4: a wired provider, end to end on go ----------------------------

E2E_SOURCE = """
extern emission fn note(msg: Str) -> Unit = @go {
\tprintln("NOTE-RAN " + msg)
\treturn
}

service Log { emission fn write(msg: Str) }

component Logger provides log: Log {
  provide log {
    fn write(msg) {
      emit note(msg)
    }
  }
}

component Caller requires log: Log {
  emit log.write("hi")
}
"""

E2E_HARNESS = """package crashrecovery

import (
\tstdctx "context"
\t"testing"

\tstc "github.com/0xdenny218/stc-go"
)

func TestServiceEmissionEndToEnd(t *testing.T) {
\troot := stc.New()
\tif err := LoadLogger(root).Ready(stdctx.Background()); err != nil {
\t\tt.Fatalf("boot Logger: %v", err)
\t}
\tif err := LoadCaller(root).Ready(stdctx.Background()); err != nil {
\t\tt.Fatalf("boot Caller: %v", err)
\t}
}
"""


def test_go_service_emission_runs_journalled_end_to_end(tmp_path):
    """A Caller emits through a Logger it requires; the provider's body
    (itself an extern emission) runs, and the WAL holds the service crossing
    and the nested extern crossing, each started and completed."""
    from revl.compiler import compile_source  # noqa: PLC0415
    ir = compile_source(E2E_SOURCE, "e2e.rvl")
    src = _load_emitter("go").emit(ir, "crashrecovery", record=True)
    assert 'revlJournalEmission("log", "write", "Log"' in src
    if GO is None:
        pytest.skip("go toolchain not available")
    module = tmp_path / "e2e_go"
    module.mkdir()
    for name in ("go.mod", "go.sum"):
        shutil.copy(GO_SCENARIOS / name, module / name)
    pkg = module / "crashproof"
    pkg.mkdir()
    (pkg / "gen_crash_recovery_test.go").write_text(src, encoding="utf-8")
    (pkg / "e2e_test.go").write_text(E2E_HARNESS, encoding="utf-8")
    out = module / "e2e.test"
    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOPROXY": "off"}
    build = subprocess.run([GO, "test", "-c", "-o", str(out), "./crashproof/"],
                           cwd=str(module), capture_output=True, text=True, env=env)
    assert build.returncode == 0, build.stderr
    wal = tmp_path / "e2e.wal"
    proc = subprocess.run([str(out), "-test.run", "TestServiceEmissionEndToEnd", "-test.v"],
                          env={"REVL_WAL": str(wal), "PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "NOTE-RAN hi" in proc.stdout + proc.stderr
    records = _records(wal)
    starts = {r["label"]: r for r in records
              if r.get("record") == "effect" and r.get("kind") == "emission"}
    assert set(starts) == {"log.write", "note"}, records
    assert starts["log.write"]["boundary"]["detail"]["service"] == "Log"
    # the service crossing starts first, and its body's crossing nests inside
    assert starts["log.write"]["seq"] < starts["note"]["seq"]
    for start in starts.values():
        assert {"record": "emission-complete", "seq": start["seq"]} in records, records
    assert wal_core.unresolved_crossings(records) == []


def test_compiled_sinks_cut_before_the_fsync_failure_stops_the_run():
    """The runtime cut tests fault the write; `/dev/null` cannot show a cut
    after a failed fsync. So pin, per sink, that the fsync-failure arm runs
    the same cut before it stops the run."""
    go = _load_emitter("go").emit(_crashproof_ir("go"), "crashrecovery", record=True)
    go = go[go.index("if err := w.f.Sync(); err != nil && !w.unsynced {"):]
    _in_order(go, "w.cut(start)", 'panic("revl: write-ahead log fsync failed: "')
    rust = _rust_source(_crashproof_ir("rust"))
    rust = rust[rust.index("if let Err(e) = self.file.sync_all() {"):]
    _in_order(rust, "if !self.unsynced {", "self.cut(start);",
              'panic!("revl: write-ahead log fsync failed: {e}");')
    java = _load_emitter("java").emit(_crashproof_ir("java"), "revl", record=True)
    java = java[java.index("revlWalChannel.force(true);"):]
    _in_order(java, "if (!revlWalUnsynced) {", "revlWalCut(start);",
              'throw new java.io.UncheckedIOException("revl: write-ahead log fsync failed", sync);')
