"""A module's services and components bind to the module's own names (issue #2451).

`_apply_module_privacy` renames a colliding type or fn apart per module, and
`_rewrite_module` then rewrites every reference to it inside that module. It
rewrote fns, externs, types, events and fn/test bodies, but never a service or
a component. So with a document that declares `type In = { z: Str }` and
`service Other { fn get() -> In }`, and imports a module carrying its own `In`,
the document's `In` became `In__m0` while `Other.get` kept the bare `In`, which
is the imported `{ a: Int }`. Nothing was reported. The imported module's own
services were skipped the same way, and a component calling the document's own
colliding helper was refused with a misleading "not a declared requirement".

The rule is the one the module-merge pass already applies to fns and types:
inside a module, a name refers to that module's own declaration. Each module's
services and components now bind to that module's declarations. The binding is
read through the IR, and through the emitted py and ts.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

from revl import compile_files
from revl.errors import RevlError

ROOT = Path(__file__).resolve().parents[1]

LIB = '''pub type In = { a: Int }
pub type Row = { i: In }
pub service Store {
  fn put(r: Row) -> Str
}
'''

# the issue's document, verbatim
DOC = '''use "./lib.rvl" { Store }

type In = { z: Str }

service Other { fn get() -> In }

service Front { fn go() -> Str }

component App requires store: Store provides front: Front {
  provide front {
    fn go() = store.put({ i: { a: 1 } })
  }
}
'''

PROVIDER = DOC + '''
component OtherKit provides other: Other {
  provide other {
    fn get() = { z: "s" }
  }
}
'''

# the colliding name written inside a component's provide
PROVIDE_ANNOTATED = DOC + '''
component OtherKit provides other: Other {
  provide other {
    fn get() -> In {
      let v: In = { z: "s" }
      return v
    }
  }
}
'''

# the imported module is a pure dependency (`mk`), so it is merged and its own
# private `In` is renamed apart too; its service must follow it
LIB_PRIVATE = '''type In = { a: Int }
pub fn mk() -> Int { return 1 }
pub service Store {
  fn peek() -> In
}
'''

DOC_PRIVATE = '''use "./lib.rvl" { Store, mk }

type In = { z: Str }

service Other { fn get() -> In }
'''

LIB_FN = '''fn helper() -> Int { return 1 }
pub fn mk() -> Int { return helper() }
'''

DOC_FN = '''use "./lib.rvl" { mk }

fn helper() -> Int { return 2 }

service Front { fn go() -> Int }

component App provides front: Front {
  provide front {
    fn go() = CALL
  }
}
'''


LIB_BOOL = '''fn helper() -> Bool { return false }
pub fn mk() -> Int { return helper() ? 1 : 0 }
'''

# the colliding helper is called inside an emit's conditional `with` clause
DOC_APPROVAL = '''use "./lib.rvl" { mk }

fn helper() -> Bool { return true }

extern emission[pay] fn charge(amount: Int) -> Int requires approval = @py { return 1 }

service Pay { emission[pay] fn run(n: Int) -> Int }

component Worker provides task: Pay {
  let a = await approval[pay] { reason: "one" }
  let b = await approval[pay] { reason: "two" }
  provide task { fn run(n) { emit charge(n + mk()) with helper() ? a : b return 1 } }
}
'''

def _compile(tmp_path: Path, lib: str, doc: str) -> dict:
    (tmp_path / "lib.rvl").write_text(lib, encoding="utf-8")
    main = tmp_path / "doc.rvl"
    main.write_text(doc, encoding="utf-8")
    return compile_files([str(main)])


def _emit(tier: str, ir: dict) -> str:
    sub = {"py": "python", "ts": "typescript"}[tier]
    spec = importlib.util.spec_from_file_location(
        f"emit_2451_{tier}", ROOT / "backends" / sub / "emit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.emit(json.loads(json.dumps(ir)))


def _returns(ir: dict, service: str, op: str) -> str:
    return ir["services"][service]["methods"][op]["returns"]


def _fields(ir: dict, type_name: str) -> dict:
    return ir["types"][type_name]["fields"]


def _ts_interface(ts: str, name: str) -> str:
    match = re.search(r"export interface " + re.escape(name) + r" \{\n(.*?)\n\}",
                      ts, re.S)
    assert match, f"no `interface {name}` in the ts output"
    return match.group(1).strip()


# ------------------------------------------------------------ the defect

def test_a_document_service_returns_the_document_s_own_type(tmp_path):
    ir = _compile(tmp_path, LIB, DOC)
    own = _returns(ir, "Other", "get")
    assert _fields(ir, own) == {"z": "Str"}
    # the carried `In` keeps its bare name and its own fields
    assert _fields(ir, "In") == {"a": "Int"}
    assert _fields(ir, "Row") == {"i": "In"}
    assert ir["services"]["Store"]["methods"]["put"]["params"] == [
        {"name": "r", "type": "Row"}]


def test_the_ts_service_interface_names_the_document_s_own_type(tmp_path):
    ir = _compile(tmp_path, LIB, DOC)
    ts = _emit("ts", ir)
    match = re.search(r"export interface Other \{\n  get\(\): (\w+)\n\}", ts)
    assert match, "no `interface Other` in the ts output"
    assert _ts_interface(ts, match.group(1)) == "z: string"
    assert _ts_interface(ts, "In") == "a: bigint"


def test_a_provider_of_the_document_service_compiles_on_py_and_ts(tmp_path):
    """Before the fix the provider's `{ z: "s" }` was checked against the
    carried `{ a: Int }` and refused."""
    ir = _compile(tmp_path, LIB, PROVIDER)
    assert _fields(ir, _returns(ir, "Other", "get")) == {"z": "Str"}
    assert "return {'z': 's'}" in _emit("py", ir)
    assert 'return {z: "s"}' in _emit("ts", ir)


def test_the_colliding_name_inside_a_component_s_provide(tmp_path):
    ir = _compile(tmp_path, LIB, PROVIDE_ANNOTATED)
    assert _fields(ir, _returns(ir, "Other", "get")) == {"z": "Str"}
    py = _emit("py", ir)
    assert "v = {'z': 's'}" in py
    ts = _emit("ts", ir)
    match = re.search(r"get\(\): (\w+)\n", ts)
    assert match and _ts_interface(ts, match.group(1)) == "z: string"


def test_an_imported_module_s_service_follows_its_own_renamed_type(tmp_path):
    """Both private `In`s are renamed apart. Before the fix both services kept
    the bare `In`, which named no type at all."""
    ir = _compile(tmp_path, LIB_PRIVATE, DOC_PRIVATE)
    assert _fields(ir, _returns(ir, "Other", "get")) == {"z": "Str"}
    assert _fields(ir, _returns(ir, "Store", "peek")) == {"a": "Int"}
    assert "In" not in ir["types"]


def test_a_component_calls_the_document_s_own_colliding_helper(tmp_path):
    """Before the fix the provide body kept the bare `helper` while the fn was
    renamed apart, and the component was refused as missing a requirement."""
    ir = _compile(tmp_path, LIB_FN, DOC_FN.replace("CALL", "helper() + mk()"))
    # the document is the first module of the merge, so its `helper` is `__m0`
    own = next(fn for fn in ir["functions"] if fn["name"] == "helper__m0")
    assert own["body"] == [
        {"step": "return", "expr": {"kind": "lit", "value": 2}}]
    assert "helper__m0() + mk()" in _emit("py", ir)
    assert "helper__m0() + mk()" in _emit("ts", ir)


def test_an_emit_s_with_clause_calls_the_document_s_own_colliding_helper(tmp_path):
    """The `with <expr>` approval clause is walked too. Left bare, the
    document's `helper` in `helper() ? a : b` was not rewritten to `__m0`, and
    the component was refused as missing a requirement. Typed approvals run on
    the py tier only (ts refuses them by name), so py is the emitted check."""
    ir = _compile(tmp_path, LIB_BOOL, DOC_APPROVAL)
    assert '"name": "helper__m0"' in json.dumps(ir["components"])
    assert "helper__m0()" in _emit("py", ir)

def test_a_provider_returning_the_carried_shape_is_refused(tmp_path):
    """The carried `{ a: Int }` no longer stands in for the document's `In`:
    the provider is checked against `{ z: Str }`."""
    with pytest.raises(RevlError) as excinfo:
        _compile(tmp_path, LIB, PROVIDER.replace('{ z: "s" }', "{ a: 1 }"))
    assert "has missing `z`; unknown `a`" in str(excinfo.value)


# ------------------------------------------------------------ controls

def test_control_no_collision_keeps_every_bare_name(tmp_path):
    doc = (DOC.replace("type In = { z: Str }", "type Mine = { z: Str }")
           .replace("fn get() -> In", "fn get() -> Mine"))
    ir = _compile(tmp_path, LIB, doc)
    assert _returns(ir, "Other", "get") == "Mine"
    assert sorted(ir["types"]) == ["In", "Mine", "Row"]
    assert "get(): Mine" in _emit("ts", ir)


def test_control_a_collision_only_in_fns_leaves_services_alone(tmp_path):
    ir = _compile(tmp_path, LIB_FN, DOC_FN.replace("CALL", "mk()"))
    assert _returns(ir, "Front", "go") == "Int"
    assert sorted(fn["name"] for fn in ir["functions"]) == [
        "helper__m0", "helper__m1", "mk"]
    assert "return mk()" in _emit("py", ir)
