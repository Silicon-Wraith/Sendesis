from pathlib import Path

import pytest

from sendesis.gitstate import GitError, is_clean, reset_to, snapshot, unchanged
from stage_helpers import git_init


def repo(tmp_path: Path) -> Path:
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.txt").write_text("one\n")
    git_init(root)
    return root


def test_clean_and_dirty(tmp_path: Path):
    root = repo(tmp_path)
    assert is_clean(root)
    (root / "a.txt").write_text("two\n")
    assert not is_clean(root)


def test_ignored_files_do_not_make_the_tree_dirty(tmp_path: Path):
    root = repo(tmp_path)
    (root / ".sendesis").mkdir()
    (root / ".sendesis" / "x.json").write_text("{}")
    assert is_clean(root)


def test_unchanged_detects_edits_and_new_files(tmp_path: Path):
    root = repo(tmp_path)
    snap = snapshot(root)
    assert unchanged(root, snap)
    (root / "new.txt").write_text("x")
    assert not unchanged(root, snap)


def test_reset_removes_only_files_the_seat_created(tmp_path: Path):
    root = repo(tmp_path)
    (root / "pre.txt").write_text("was here before the seat")
    (root / ".sendesis").mkdir()
    (root / ".sendesis" / "keep.json").write_text("{}")
    snap = snapshot(root)
    (root / "a.txt").write_text("changed by the seat\n")
    (root / "deep" / "er").mkdir(parents=True)
    (root / "deep" / "er" / "made.py").write_text("x = 1\n")
    reset_to(root, snap)
    assert (root / "a.txt").read_text() == "one\n"
    assert not (root / "deep" / "er" / "made.py").exists()
    assert (root / "pre.txt").exists() and (root / ".sendesis" / "keep.json").exists()


def test_not_a_repository_raises(tmp_path: Path):
    with pytest.raises(GitError):
        snapshot(tmp_path)
