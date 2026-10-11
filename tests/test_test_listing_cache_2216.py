"""Issue #2216: the session cache for the selector's tests/ listing keys on the
names in the directory, so any change to them recomputes the listing, and an
unchanged directory is listed once."""

from __future__ import annotations

from pathlib import Path

from _test_listing_cache import cached_test_files, listing_key


def _tree(tmp_path: Path, *names: str) -> Path:
    tests = tmp_path / "tests"
    tests.mkdir(parents=True)
    for name in names:
        (tests / name).write_text("", encoding="utf-8")
    return tmp_path


def _glob(root: Path):
    return sorted((root / "tests").glob("test_*.py"))


def _counting():
    calls = []

    def original(root):
        calls.append(root)
        return _glob(root)

    return cached_test_files(original), calls


def test_the_key_changes_when_an_entry_is_added(tmp_path):
    root = _tree(tmp_path, "test_a.py")
    before = listing_key(root)
    (root / "tests" / "test_b.py").write_text("", encoding="utf-8")
    assert listing_key(root) != before


def test_the_key_changes_when_an_entry_is_renamed_or_removed(tmp_path):
    root = _tree(tmp_path, "test_a.py", "test_b.py")
    first = listing_key(root)
    (root / "tests" / "test_b.py").rename(root / "tests" / "test_c.py")
    second = listing_key(root)
    (root / "tests" / "test_c.py").unlink()
    third = listing_key(root)
    assert len({first, second, third}) == 3


def test_the_key_ignores_file_contents_and_names_the_root(tmp_path):
    """The listing reads names only, so an edit to a test is not an input; two
    roots with the same names are still two keys."""
    root = _tree(tmp_path / "one", "test_a.py")
    before = listing_key(root)
    (root / "tests" / "test_a.py").write_text("x = 1\n", encoding="utf-8")
    assert listing_key(root) == before
    other = _tree(tmp_path / "two", "test_a.py")
    assert listing_key(other) != before


def test_an_unchanged_directory_is_listed_once(tmp_path):
    root = _tree(tmp_path, "test_a.py", "helper.py")
    files, calls = _counting()
    assert files(root) == _glob(root)
    assert files(root) == _glob(root)
    assert len(calls) == 1


def test_a_changed_directory_is_listed_again(tmp_path):
    root = _tree(tmp_path, "test_a.py")
    files, calls = _counting()
    files(root)
    (root / "tests" / "test_b.py").write_text("", encoding="utf-8")
    assert [p.name for p in files(root)] == ["test_a.py", "test_b.py"]
    assert len(calls) == 2


def test_a_caller_cannot_change_the_cached_listing(tmp_path):
    root = _tree(tmp_path, "test_a.py")
    files, _ = _counting()
    files(root).clear()
    assert files(root) == _glob(root)


def test_a_root_without_tests_falls_through_to_the_original(tmp_path):
    files, calls = _counting()
    assert files(tmp_path) == []
    assert files(tmp_path) == []
    assert len(calls) == 2
