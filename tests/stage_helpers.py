"""Helpers for router, failover and stage tests: fixture roles, workflows, a git root, scripted seats."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from sendesis.seat import Outcome, SeatResult

GOOD = {"role_id": "x", "findings": [], "checks": [{"id": "injection", "outcome": "no_findings"}]}


def add_role(root: Path, role_id: str, *, order, kind: str = "reviewer", tools=("read", "search"), suite: bool = False) -> None:
    """A role copied from security-reviewer.yaml with a new id, failover order, kind and tools.
    Without `suite`, the qualification block is removed, so the role is provisional."""
    data = yaml.safe_load((root / "roles" / "security-reviewer.yaml").read_text())
    data.update(id=role_id, kind=kind, failover_order=list(order))
    data["tools"]["allowed"] = list(tools)
    if not suite:
        data.pop("qualification", None)
    (root / "roles" / f"{role_id}.yaml").write_text(yaml.safe_dump(data, sort_keys=False))


def write_workflow(root: Path, wid: str, seats: list[dict]) -> Path:
    (root / "workflows").mkdir(exist_ok=True)
    path = root / "workflows" / f"{wid}.yaml"
    data = {"id": wid, "version": "0.1.0", "description": "Fixture workflow for tests.",
            "stages": [{"id": "review", "seats": seats}]}
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def git_init(root: Path) -> None:
    """Make `root` a git repository with one commit and `.sendesis/` ignored."""
    (root / ".gitignore").write_text(".sendesis/\n")
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "fixture"]):
        subprocess.run(["git", *args], cwd=root, check=True, stdin=subprocess.DEVNULL, capture_output=True)


def result(outcome: Outcome, **kw) -> SeatResult:
    return SeatResult(outcome, reason=kw.pop("reason", outcome.value), **kw)


def ok() -> SeatResult:
    return SeatResult(Outcome.OK, output=dict(GOOD), input_tokens=10, output_tokens=5, wall_s=1.0)


def scripted(plan: dict[str, list]):
    """plan maps a profile id to the SeatResults (or callables taking cwd) it returns, in order."""
    calls = []

    def seat_fn(role, profile, message, cwd, timeout_s):
        calls.append((role.id, profile.id, message))
        item = plan[profile.id].pop(0)
        return item(cwd) if callable(item) else item

    seat_fn.calls = calls
    return seat_fn
