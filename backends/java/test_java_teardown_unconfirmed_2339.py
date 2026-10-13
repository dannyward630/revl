"""A java runner whose dispose threw did not finish the LIFO unwind (issue #2339).

`src/revl/placement.py::_stop_all` reads `[name] DOWN` as proof the LIFO unwind
finished. All three java runners (`PlacementRunner`, `RealPlacementRunner`,
`RunOnce`) disposed each fiber inside `try { ... } catch (Throwable ignored) {}`
and printed `DOWN` regardless. cordis4j's `Context.dispose` is a plain LIFO of
`Disposable`s that propagates whatever the first failing entry throws and stops
there, so a dispose that threw left every inverse behind it unrun, and the
runner still reported a clean teardown and exited 0.

A dispose that throws is unconfirmed. The runner keeps going down the stack (the
other fibers still get their dispose), then prints one scrubbed
`[name] FATAL teardown incomplete: dispose not confirmed for <labels>` line on
stderr, no residue verdict and no `DOWN`, and halts with a non-zero exit, the
disposition the E-Stop and the boot-failure paths already use.

The java dispose is synchronous, so there is no wait to bound and nothing for
`REVL_TEARDOWN_GRACE` to size (the go runner awaits an asynchronous `Gone`); a
dispose that never returns already leaves no `DOWN`.

The tests drive the real runner on a JVM with a hand-written `revl.Components`
whose second component's inverse throws. `PlacementRunner` and `RunOnce` run
wherever a JDK is. `RealPlacementRunner` needs the real cordis4j classes
(`REVL_CORDIS4J_CLASSES`, built by CI's backend-java job) and skips without them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _path in (ROOT / "src", HERE):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import javac_gate  # noqa: E402

PLACEMENT = HERE / "placement"

needs_jdk = pytest.mark.skipif(javac_gate.JAVA is None, reason=javac_gate.NO_JDK)
_REAL = os.environ.get("REVL_CORDIS4J_CLASSES", "")
needs_real = pytest.mark.skipif(
    javac_gate.JAVA is None or not (_REAL and Path(_REAL).is_dir()),
    reason="needs a JDK and the real cordis4j classes (REVL_CORDIS4J_CLASSES); "
           "CI's backend-java job builds them")

# `Good` loads first, `Bad` second, so the LIFO unwind disposes `Bad` first. Its
# inverse throws; `Good` must still be disposed afterwards.
COMPONENTS = """\
package revl;

import io.cordis4j.core.Context;
import io.cordis4j.core.Disposable;
import io.cordis4j.core.Plugin;

public final class Components {
    private Components() {}

    public static final class GoodPlugin implements Plugin {
        public GoodPlugin() {}
        public Disposable apply(Context ctx) {
            System.out.println("MARK good applied");
            return () -> System.out.println("MARK good disposed");
        }
    }

    public static final class BadPlugin implements Plugin {
        public BadPlugin() {}
        public Disposable apply(Context ctx) {
            System.out.println("MARK bad applied");
            return () -> {
                System.out.println("MARK bad inverse threw");
                throw new IllegalStateException("inverse failed");
            };
        }
    }
}
"""


def _build(work: Path, runners: list[str], classpath: str | None = None) -> Path:
    """javac the stubs (or the real classes on the classpath) + the named runner
    sources + the hand-written Components into one classes dir."""
    gen = work / "gen" / "revl"
    gen.mkdir(parents=True)
    (gen / "Components.java").write_text(COMPONENTS, encoding="utf-8")
    out = work / "out"
    out.mkdir()
    sources = [str(PLACEMENT / "Estop.java")] + [str(PLACEMENT / r) for r in runners]
    cmd = [javac_gate.JAVAC, "--release", javac_gate.RELEASE, "-d", str(out)]
    if classpath is None:
        cmd += [str(s) for s in javac_gate.STUB_SOURCES]
    else:
        cmd += ["-cp", classpath]
    done = subprocess.run(cmd + sources + [str(gen / "Components.java")],
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr
    return out


def _spec(work: Path) -> Path:
    spec = work / "spec.json"
    spec.write_text(json.dumps({
        "name": "p", "module": "revl.Components", "components": ["Good", "Bad"]}))
    return spec


def _held(cmd: list[str]) -> tuple[int, str, str]:
    """Boot a held runner, wait for `UP`, stop it with SIGTERM, and return
    (exit code, stdout, stderr)."""
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    seen: list[str] = []
    try:
        for line in proc.stdout:
            seen.append(line)
            if "] UP" in line:
                break
        else:
            raise AssertionError("never reached UP: " + "".join(seen) + proc.stderr.read())
        proc.terminate()
        rest_out, err = proc.communicate(timeout=120)
    finally:
        if proc.poll() is None:
            proc.kill()
    return proc.returncode, "".join(seen) + rest_out, err


def _assert_unconfirmed(code: int, out: str, err: str) -> None:
    # the failure under test really happened, and the loop kept going past it
    assert "MARK bad inverse threw" in out, (out, err)
    assert "MARK good disposed" in out, (out, err)
    # not a clean teardown: no DOWN, no residue verdict
    assert "] DOWN" not in out, (out, err)
    assert "NO-RESIDUE" not in out and "RESIDUE-LEFT" not in out, (out, err)
    fatal = [line for line in err.splitlines() if "] FATAL " in line]
    assert len(fatal) == 1, err
    assert fatal[0].startswith("[p] FATAL teardown incomplete: dispose not confirmed for "), err
    assert "Bad" in fatal[0] and "Good" not in fatal[0], err
    assert code != 0, (code, out, err)


@needs_jdk
def test_the_stub_runner_does_not_say_down_when_a_dispose_threw(tmp_path):
    out = _build(tmp_path, ["PlacementRunner.java"])
    code, stdout, stderr = _held(
        [javac_gate.JAVA, "-cp", str(out), "PlacementRunner", str(_spec(tmp_path))])
    _assert_unconfirmed(code, stdout, stderr)


@needs_jdk
def test_the_once_runner_does_not_say_down_when_a_dispose_threw(tmp_path):
    out = _build(tmp_path, ["PlacementRunner.java", "RunOnce.java"])
    done = subprocess.run(
        [javac_gate.JAVA, "-cp", str(out), "RunOnce", str(_spec(tmp_path))],
        capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    assert "] UP" in done.stdout, (done.stdout, done.stderr)
    _assert_unconfirmed(done.returncode, done.stdout, done.stderr)


@needs_real
def test_the_real_runner_does_not_say_down_when_a_dispose_threw(tmp_path):
    out = _build(tmp_path, ["RealPlacementRunner.java"], classpath=_REAL)
    code, stdout, stderr = _held(
        [javac_gate.JAVA, "-cp", f"{_REAL}{os.pathsep}{out}", "RealPlacementRunner",
         str(_spec(tmp_path))])
    _assert_unconfirmed(code, stdout, stderr)
