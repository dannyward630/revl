"""Per-compile work that cannot matter is skipped (issues #2195 and #2197).

Two checks ran on every compile whatever the program held:

* #2197: `realm_placeholders.bind` walked the whole component AST through
  `__dict__` looking for `realm(?name)`, which almost no program writes. The
  parser now records whether it built one (`Program.has_realm_placeholder`)
  and `bind` walks only when it did.
* #2195: `_check_user_py_body_imports` globbed `backends/python` before
  looking for an `@py` body, once per module per compile. It now returns
  before the glob when there is no `@py` body, and the module-name set is
  cached once per process, keyed by the directory and its mtime. The
  module's origin (a realpath of its path and of the stdlib) is asked only
  when it has a ref, an asset or an `@py` body, so the admission round-trip
  the bench times no longer touches the filesystem beyond one `stat`.

These tests count calls; none of them measures time. Each would fail before
the change: the walk and the glob both ran for a program with neither.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

import revl.compiler as compiler
import revl.realm_placeholders as realm_placeholders
from revl.admit_profile import AdmissionProfile
from revl.compiler import compile_files, compile_source
from revl.errors import RevlError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from _load_by_path import load_by_path  # noqa: E402

# examples/tenants.rvl: components with literal realms, no placeholder, no @py
TENANTS = (ROOT / "examples" / "tenants.rvl").read_text(encoding="utf-8")
PLACEHOLDERS = (TENANTS.replace('realm("tenant_a")', "realm(?a)")
                .replace('realm("tenant_b")', "realm(?b)"))
BOTH = (("a", "tenant_a"), ("b", "tenant_b"))

PY_BODY = """
extern pure fn steal(x: Str) -> Str = @py {
    import revl_fs_workspace
    return x
}
"""

LIB = 'pub fn label() -> Str { return "lib" }\n'
MAIN = ('use "lib.rvl" { label }\n'
        "service Tool { fn describe() -> Str }\n"
        "component T provides tool: Tool {\n"
        "  provide tool { fn describe() = label() }\n"
        "}\n")


def _isolation(ir: dict) -> dict:
    return {c["name"]: c.get("isolate") for c in ir["manifest"]["components"]}


@pytest.fixture
def walks(monkeypatch):
    """Count every `_placeholders` call, recursive ones included."""
    calls = []
    real = realm_placeholders._placeholders

    def counted(node, out):
        calls.append(1)
        real(node, out)

    monkeypatch.setattr(realm_placeholders, "_placeholders", counted)
    return calls


@pytest.fixture
def name_sets(monkeypatch):
    """Count every `_backend_python_module_names` call."""
    calls = []
    real = compiler._backend_python_module_names

    def counted():
        calls.append(1)
        return real()

    monkeypatch.setattr(compiler, "_backend_python_module_names", counted)
    return calls


def _write_two_modules(tmp_path: Path) -> str:
    (tmp_path / "lib.rvl").write_text(LIB, encoding="utf-8")
    main = tmp_path / "main.rvl"
    main.write_text(MAIN, encoding="utf-8")
    return str(main)


# ---------------------------------------------------------------------------
# #2197: the realm-placeholder walk
# ---------------------------------------------------------------------------

def test_the_parser_records_whether_a_placeholder_was_built():
    from revl.parser import Parser
    assert Parser(TENANTS, "tenants.rvl").parse().has_realm_placeholder is False
    assert Parser(PLACEHOLDERS, "t.rvl").parse().has_realm_placeholder is True
    route = ("service KV { fn get(k: Str) -> Str }\n"
             "component C provides kv: KV {\n"
             "  isolate kv in realms(?a, \"b\")\n"
             "  provide kv { fn get(k) = k }\n"
             "}\n")
    assert Parser(route, "r.rvl").parse().has_realm_placeholder is True


def test_compile_source_without_a_placeholder_does_not_walk(walks):
    ir = compile_source(TENANTS, "tenants.rvl")
    assert walks == []
    assert _isolation(ir)["TenantAStore"] == {"kv": "tenant_a"}


def test_compile_files_without_a_placeholder_does_not_walk(walks, tmp_path):
    compile_files([_write_two_modules(tmp_path)])
    assert walks == []


def test_a_placeholder_is_still_walked_and_bound(walks):
    profile = AdmissionProfile.untrusted_author((), BOTH)
    ir = compile_source(PLACEHOLDERS, "tenants.rvl", profile=profile)
    assert len(walks) > 0
    assert _isolation(ir)["TenantAStore"] == {"kv": "tenant_a"}
    assert _isolation(ir)["TenantBApp"] == {"kv": "tenant_b"}


def test_an_unbound_placeholder_is_still_refused(walks):
    with pytest.raises(RevlError) as caught:
        compile_source(PLACEHOLDERS, "tenants.rvl")
    assert caught.value.code == "G2"
    assert realm_placeholders.UNBOUND in caught.value.message
    assert len(walks) > 0


def test_a_program_built_outside_the_parser_is_still_walked(walks):
    """`has_realm_placeholder` is `None` on a Program the parser did not build,
    and `bind` then walks as before rather than assume there is nothing."""
    from revl.parser import Program
    realm_placeholders.bind(Program("x.rvl"), None)
    assert len(walks) > 0


# ---------------------------------------------------------------------------
# #2195: the backends/python glob
# ---------------------------------------------------------------------------

def test_compile_source_without_a_py_body_does_not_glob(name_sets):
    compile_source(TENANTS, "tenants.rvl")
    assert name_sets == []


def test_compile_files_without_a_py_body_does_not_glob(name_sets, tmp_path):
    compile_files([_write_two_modules(tmp_path)])
    assert name_sets == []


def test_a_py_body_is_still_checked(name_sets, tmp_path):
    with pytest.raises(RevlError, match="imports backend module `revl_fs_workspace`"):
        compile_source(PY_BODY)
    assert len(name_sets) == 1
    source = tmp_path / "main.rvl"
    source.write_text(PY_BODY, encoding="utf-8")
    with pytest.raises(RevlError, match="imports backend module `revl_fs_workspace`"):
        compile_files([str(source)])
    assert len(name_sets) >= 2


def _body_importing(name: str) -> str:
    return PY_BODY.replace("revl_fs_workspace", name)


def test_the_name_set_is_globbed_once_and_follows_a_changed_tree(monkeypatch, tmp_path):
    """The set is cached per process, keyed by the directory and its mtime: a
    repeat compile does not glob again, a module added to the tree is refused
    on the next compile, and a different `backends_root` gets its own set."""
    backends = tmp_path / "backends"
    tree = backends / "python"
    tree.mkdir(parents=True)
    (tree / "fake_backend_a.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(compiler, "backends_root", lambda: backends)

    globs = []
    real_glob = Path.glob

    def counted_glob(self, pattern, *args, **kwargs):
        if Path(self) == tree:
            globs.append(pattern)
        return real_glob(self, pattern, *args, **kwargs)

    monkeypatch.setattr(Path, "glob", counted_glob)

    for _ in range(3):
        with pytest.raises(RevlError, match="backend module `fake_backend_a`"):
            compile_source(_body_importing("fake_backend_a"))
    assert globs == ["*.py"]

    # not a backend module yet: the stdlib-import case compiles
    compile_source(_body_importing("fake_backend_b"))
    (tree / "fake_backend_b.py").write_text("", encoding="utf-8")
    # pin a distinct mtime so a coarse filesystem clock cannot hide the change
    stamp = tree.stat().st_mtime_ns + 2_000_000_000
    os.utime(tree, ns=(stamp, stamp))
    with pytest.raises(RevlError, match="backend module `fake_backend_b`"):
        compile_source(_body_importing("fake_backend_b"))
    assert globs == ["*.py", "*.py"]

    monkeypatch.undo()
    # the real tree again: its own key, its own set
    compile_source(_body_importing("fake_backend_b"))
    with pytest.raises(RevlError, match="backend module `revl_fs_workspace`"):
        compile_source(PY_BODY)


def test_an_admission_round_trip_does_not_walk_the_filesystem(monkeypatch):
    """The bench scenario (`bench/admission_latency.py`): a candidate compiled
    against the running manifest. It used to cost about 60 `lstat` calls and
    two directory scans per admission; it now makes no `lstat` and no scan
    (one `stat` remains, locating the shipped stdlib for the search path)."""
    al = load_by_path("admission_latency", ROOT / "bench" / "admission_latency.py")
    running = al.build_running()
    al.admit_once(running)
    calls = {"lstat": 0, "scandir": 0, "stat": 0}
    for name in calls:
        real = getattr(os, name)

        def counted(*args, _real=real, _name=name, **kwargs):
            calls[_name] += 1
            return _real(*args, **kwargs)

        monkeypatch.setattr(os, name, counted)
    al.admit_once(running)
    assert calls["lstat"] == 0 and calls["scandir"] == 0, calls
    assert calls["stat"] <= 1, calls
