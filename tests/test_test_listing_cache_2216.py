"""Issue #2216: `tools/affected_tests.py` caches its listing of tests/ on the
root and a hash of the entry names in the directory, so any change to them
lists the directory again, and an unchanged directory is listed once. The
cache lives in the selector, so every caller of `select()` gets it."""

from __future__ import annotations

from pathlib import Path

from _load_by_path import load_by_path

ROOT = Path(__file__).resolve().parents[1]
at = load_by_path("affected_tests", ROOT / "tools" / "affected_tests.py")


def _tree(tmp_path: Path, *names: str) -> Path:
    tests = tmp_path / "tests"
    tests.mkdir(parents=True)
    for name in names:
        (tests / name).write_text("", encoding="utf-8")
    return tmp_path


def _glob(root: Path):
    return sorted((root / "tests").glob("test_*.py"))


def _counting(monkeypatch):
    """Count the selector's real listings while its cache answers the rest."""
    calls = []
    original = at._list_test_files

    def listing(root):
        calls.append(root)
        return original(root)

    monkeypatch.setattr(at, "_list_test_files", listing)
    return calls


def test_the_key_changes_when_an_entry_is_added(tmp_path):
    root = _tree(tmp_path, "test_a.py")
    before = at._test_listing_key(root)
    (root / "tests" / "test_b.py").write_text("", encoding="utf-8")
    assert at._test_listing_key(root) != before


def test_the_key_changes_when_an_entry_is_renamed_or_removed(tmp_path):
    root = _tree(tmp_path, "test_a.py", "test_b.py")
    first = at._test_listing_key(root)
    (root / "tests" / "test_b.py").rename(root / "tests" / "test_c.py")
    second = at._test_listing_key(root)
    (root / "tests" / "test_c.py").unlink()
    third = at._test_listing_key(root)
    assert len({first, second, third}) == 3


def test_the_key_ignores_file_contents_and_names_the_root(tmp_path):
    """The listing reads names only, so an edit to a test is not an input; two
    roots with the same names are still two keys."""
    root = _tree(tmp_path / "one", "test_a.py")
    before = at._test_listing_key(root)
    (root / "tests" / "test_a.py").write_text("x = 1\n", encoding="utf-8")
    assert at._test_listing_key(root) == before
    other = _tree(tmp_path / "two", "test_a.py")
    assert at._test_listing_key(other) != before


def test_an_unchanged_directory_is_listed_once(tmp_path, monkeypatch):
    root = _tree(tmp_path, "test_a.py", "helper.py")
    calls = _counting(monkeypatch)
    assert at._test_files(root) == _glob(root)
    assert at._test_files(root) == _glob(root)
    assert len(calls) == 1


def test_a_changed_directory_is_listed_again(tmp_path, monkeypatch):
    root = _tree(tmp_path, "test_a.py")
    calls = _counting(monkeypatch)
    at._test_files(root)
    (root / "tests" / "test_b.py").write_text("", encoding="utf-8")
    assert [p.name for p in at._test_files(root)] == ["test_a.py", "test_b.py"]
    assert len(calls) == 2


def test_a_caller_cannot_change_the_cached_listing(tmp_path):
    root = _tree(tmp_path, "test_a.py")
    at._test_files(root).clear()
    assert at._test_files(root) == _glob(root)


def test_a_root_without_tests_falls_through_to_the_glob(tmp_path, monkeypatch):
    calls = _counting(monkeypatch)
    assert at._test_files(tmp_path) == []
    assert at._test_files(tmp_path) == []
    assert len(calls) == 2


def test_select_answers_from_the_cache_on_a_second_ask(monkeypatch):
    """The point of the cache: `select()` itself, asked twice about one file,
    lists tests/ once, and gives the same answer both times."""
    monkeypatch.setattr(at, "_TEST_FILES_CACHE", {})
    calls = _counting(monkeypatch)
    first = at.select(["src/revl/a2a_boundary.py"], ROOT)
    assert len(calls) == 1
    assert at.select(["src/revl/a2a_boundary.py"], ROOT) == first
    assert len(calls) == 1
