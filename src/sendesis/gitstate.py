"""Git checks and resets for stage seats (M3.2 spec, section 3).

A stage starts only on a clean tree. A reviewer seat must leave the tree as it found
it. A worker seat that fails over is reset to its starting commit, and only the
untracked files it created are removed; ignored files are never touched.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(Exception):
    pass


@dataclass(frozen=True)
class Snapshot:
    head: str
    untracked: frozenset[str]
    status: str


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if r.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed in {cwd}: {r.stderr.strip()}")
    return r.stdout


def is_clean(cwd: Path) -> bool:
    return _git(cwd, "status", "--porcelain") == ""


def snapshot(cwd: Path) -> Snapshot:
    head = _git(cwd, "rev-parse", "HEAD").strip()
    untracked = frozenset(p for p in _git(cwd, "ls-files", "--others", "--exclude-standard", "-z").split("\0") if p)
    return Snapshot(head, untracked, _git(cwd, "status", "--porcelain"))


def unchanged(cwd: Path, snap: Snapshot) -> bool:
    return snapshot(cwd) == snap


def reset_to(cwd: Path, snap: Snapshot) -> None:
    _git(cwd, "reset", "-q", "--hard", snap.head)
    for rel in sorted(snapshot(cwd).untracked - snap.untracked):
        path = Path(cwd) / rel
        if path.is_file() or path.is_symlink():
            path.unlink()
