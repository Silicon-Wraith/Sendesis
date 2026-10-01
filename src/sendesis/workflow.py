"""Workflow files. M3.1 loads and validates them; the compiler arrives in M3.3."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sendesis.model import _load_checked


@dataclass(frozen=True)
class Seat:
    role: str
    count: int = 1
    distinct_families: int = 1
    blind: bool = False


@dataclass(frozen=True)
class Stage:
    id: str
    seats: tuple[Seat, ...]
    inner_loop: dict | None
    loops: dict | None
    gate: dict | None
    evidence: tuple[str, ...]
    network: str
    writes: tuple[str, ...]
    budgets: dict
    skippable: bool


@dataclass(frozen=True)
class Workflow:
    path: Path
    sha256: str
    id: str
    version: str
    description: str
    stages: tuple[Stage, ...]
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


def load_workflow(path: Path, root: Path) -> Workflow:
    data, sha = _load_checked(path, root, "workflow.json")
    stages = tuple(
        Stage(
            id=s["id"],
            seats=tuple(Seat(x["role"], x.get("count", 1), x.get("distinct_families", 1), x.get("blind", False)) for x in s.get("seats", [])),
            inner_loop=s.get("inner_loop"),
            loops=s.get("loops"),
            gate=s.get("gate"),
            evidence=tuple(s.get("evidence", [])),
            network=s.get("network", "none"),
            writes=tuple(s.get("writes", [])),
            budgets=s.get("budgets", {}),
            skippable=s.get("skippable", True),
        )
        for s in data["stages"]
    )
    return Workflow(path, sha, data["id"], data["version"], data["description"], stages, data)
