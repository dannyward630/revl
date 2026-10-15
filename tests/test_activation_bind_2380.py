"""A provide method that returns an activation `let-effect` bind, on java (#2380).

WHAT WAS WRONG. The java tier declares each activation bind as a field of the
provider class. The field's type was read off the acquisition only for a
literal, a record or a list; anything else was `Object`. So
`let got = effect kv.get(4) undo ..` and `fn fetched() = got` on an
`Int`-returning service method emitted `public long fetched() { return
this.got; }` over `private final Object got;`, and javac said "Object cannot be
converted to long". The same program runs on python.

It is not the #2198 defect (component arithmetic lost its `operands`
annotation): that fix landed, and `config.a * 3` here is already emitted
through the typed `revlMul`. The missing piece was the bind's declared type.

WHAT IS EMITTED NOW. A bind that holds no host object takes the acquisition's
surface type: a required-service call's declared return, a free fn's return, a
config field's type, or an operator: arithmetic and unary `-` read off their
`operands` or their operands, a `Str` `+`, a comparison, `&&`, `||` and `!`. A
type the tier cannot spell, and a host acquisition, keep their old declaration.

The same table of answers is held on both tiers: java needs a JDK, python the
cordis-py runtime, and each run skips without its runtime. A skip is not a pass.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JAVA_DIR = ROOT / "backends" / "java"
for _p in (ROOT / "src", ROOT / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from _load_by_path import load_by_path  # noqa: E402

javac_gate = load_by_path("javac_gate", JAVA_DIR / "javac_gate.py")
emit = load_by_path("revl_java_emit_2380", JAVA_DIR / "emit.py").emit

from revl.compiler import compile_source  # noqa: E402

SOURCE = """\
fn seed() -> Int {
  return 6
}

service Kv {
  fn get(k: Int) -> Int
  fn put(k: Int, v: Int) -> Int
}

service Probe {
  fn fetched() -> Int
  fn configured() -> Int
  fn tripled() -> Int
  fn halved() -> Float
  fn seeded() -> Int
  fn labelled() -> Str
  fn joined() -> Str
  fn framed() -> Str
  fn negated() -> Int
  fn sunk() -> Float
  fn flipped() -> Bool
  fn gated() -> Bool
}

component Store provides kv: Kv {
  provide kv {
    fn get(k) = k * 10
    fn put(k, v) = v
  }
}

component Calc requires kv: Kv provides probe: Probe {
  config { a: Int = 7, label: Str = "calc", f: Float = 1.5, on: Bool = true }

  let got = effect kv.get(4) undo kv.put(4, 0)
  let cfg = effect config.a undo kv.put(1, 0)
  let triple = effect config.a * 3 undo kv.put(2, 0)
  let half = effect config.a / 2 undo kv.put(3, 0)
  let seeded = effect seed() undo kv.put(5, 0)
  let name = effect config.label undo kv.put(6, 0)
  let joined = effect config.label + "!" undo kv.put(7, 0)
  let framed = effect `n=${config.a}` undo kv.put(8, 0)
  let negated = effect -config.a undo kv.put(9, 0)
  let sunk = effect -config.f undo kv.put(10, 0)
  let flipped = effect !config.on undo kv.put(11, 0)
  let gated = effect config.on && config.a > 3 undo kv.put(12, 0)

  provide probe {
    fn fetched() = got
    fn configured() = cfg
    fn tripled() = triple
    fn halved() = half
    fn seeded() = seeded
    fn labelled() = name
    fn joined() = joined
    fn framed() = framed
    fn negated() = negated
    fn sunk() = sunk
    fn flipped() = flipped
    fn gated() = gated
  }
}
"""

#: What each provided method answers, on every tier.
EXPECTED = {
    "probe.fetched()": "40",
    "probe.configured()": "7",
    "probe.tripled()": "21",
    "probe.halved()": "3.5",
    "probe.seeded()": "6",
    "probe.labelled()": "calc",
    "probe.joined()": "calc!",
    "probe.framed()": "n=7",
    "probe.negated()": "-7",
    "probe.sunk()": "-1.5",
    "probe.flipped()": "false",
    "probe.gated()": "true",
}

needs_jdk = pytest.mark.skipif(javac_gate.JAVAC is None, reason=javac_gate.NO_JDK)
needs_cordis = pytest.mark.skipif(
    importlib.util.find_spec("cordis") is None,
    reason="the py run needs the cordis-py runtime (backends/python/setup.sh)")


def _java_source() -> str:
    out = emit(compile_source(SOURCE, "activation_bind_2380.rvl"))
    return out if isinstance(out, str) else "\n".join(map(str, out.values()))


def _run_once(tmp_path: Path, backend: str, env: dict) -> dict[str, str]:
    """`revl run --placement --once` on one backend: probe -> answer."""
    (tmp_path / "act.rvl").write_text(SOURCE, encoding="utf-8")
    probes = ", ".join(f'"{p}"' for p in EXPECTED)
    (tmp_path / "act.toml").write_text(
        f'[processes.main]\nbackend = "{backend}"\n'
        f'components = ["Store", "Calc"]\nprobe = [{probes}]\n',
        encoding="utf-8")
    ran = subprocess.run(
        [sys.executable, "-m", "revl", "run", str(tmp_path / "act.rvl"),
         "--placement", str(tmp_path / "act.toml"), "--once"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=1800,
        cwd=ROOT, env=env)
    out = ran.stdout + ran.stderr
    assert ran.returncode == 0, out
    answers = {}
    for line in out.splitlines():
        if "] probe" not in line or "=>" not in line:
            continue
        probe = line.split("|")[1].strip()
        # a Str answer is quoted, and a Bool spelled, in the host's own style
        # ('calc' / "calc", True / true)
        answer = line.split("=>", 1)[1].strip().strip("'\"")
        answers[probe] = {"True": "true", "False": "false"}.get(answer, answer)
    return answers


def test_provider_fields_take_the_acquisition_type():
    java = _java_source()
    for decl in ("private final long got;", "private final long cfg;",
                 "private final long triple;", "private final double half;",
                 "private final long seeded;", "private final String name;",
                 # a `Str` `+` is `Str`, a unary `-` takes its operand's type,
                 # `!` is `Bool` (the template and `&&` rows held already)
                 "private final String joined;", "private final String framed;",
                 "private final long negated;", "private final double sunk;",
                 "private final boolean flipped;", "private final boolean gated;"):
        assert decl in java, decl
    assert "private final Object" not in java


@needs_jdk
def test_activation_binds_compile_on_java():
    javac_gate.compile_check(_java_source(), "activation let-effect binds")


@needs_jdk
def test_java_answers_the_table(tmp_path):
    # The in-repo stub runner: the real-classes runner is consumer-only.
    env = dict(os.environ, REVL_CORDIS4J_CLASSES="")
    env["JAVA_HOME"] = str(Path(javac_gate.JAVA).parents[1])
    assert _run_once(tmp_path, "java", env) == EXPECTED


@needs_cordis
def test_py_answers_the_table(tmp_path):
    assert _run_once(tmp_path, "py", dict(os.environ)) == EXPECTED
