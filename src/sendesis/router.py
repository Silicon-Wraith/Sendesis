"""The router: the only code that chooses a profile for a seat.

Rules from docs/specs/2026-10-02-sendesis-m3.2-router-design.md, section 2. Pure
functions; no model calls. Seats of different roles are independent (one profile
may serve several roles), so each workflow seat is filled on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sendesis.model import REVIEWER_FORBIDDEN_TOOLS, Profile, Role, ValidationFailed, load_profile
from sendesis.workflow import Stage

ACCEPTABLE, PROVISIONAL, REJECTED = "acceptable", "provisional", "rejected"
PLACEHOLDER = "set-me"

StatusFn = Callable[[Role, Profile], tuple[str, list[str]]]


@dataclass(frozen=True)
class Candidate:
    profile_id: str
    verdict: str
    family: str | None = None
    reason: str = ""

    @property
    def usable(self) -> bool:
        return self.verdict in (ACCEPTABLE, PROVISIONAL)


@dataclass(frozen=True)
class Slot:
    label: str
    role_id: str
    seat_index: int


@dataclass(frozen=True)
class Assignment:
    profiles: dict[str, str]
    families: dict[str, str]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class Refusal:
    text: str


def sandbox_problem(role: Role) -> str | None:
    bad = [t for t in role.tools_allowed if t in REVIEWER_FORBIDDEN_TOOLS]
    if bad:
        return f"sandbox unavailable: {role.id} needs {', '.join(bad)}; sandboxed edit and shell seats arrive in M3.3"
    return None


def candidates(role: Role, root: Path, status_fn: StatusFn, *, excluded: dict[str, str] | None = None,
               sandbox: Callable[[Role], str | None] = sandbox_problem) -> list[Candidate]:
    excluded = excluded or {}
    out: list[Candidate] = []
    for pid in role.failover_order:
        try:
            profile = load_profile(root / "profiles" / f"{pid}.yaml", root)
        except (ValidationFailed, FileNotFoundError) as exc:
            out.append(Candidate(pid, REJECTED, None, f"profile file missing or invalid: {exc}"))
            continue
        family = profile.family
        if not profile.enabled:
            out.append(Candidate(pid, REJECTED, family, "disabled"))
            continue
        if pid in excluded:
            out.append(Candidate(pid, REJECTED, family, excluded[pid]))
            continue
        problem = sandbox(role)
        if problem:
            out.append(Candidate(pid, REJECTED, family, problem))
            continue
        if role.provisional:
            if family == PLACEHOLDER:
                out.append(Candidate(pid, REJECTED, family, f"family is the placeholder '{PLACEHOLDER}'"))
            else:
                out.append(Candidate(pid, PROVISIONAL, family))
            continue
        status, reasons = status_fn(role, profile)
        if status == "QUALIFIED":
            out.append(Candidate(pid, ACCEPTABLE, family))
        elif status == "NONE":
            out.append(Candidate(pid, REJECTED, family, "no receipt"))
        else:
            out.append(Candidate(pid, REJECTED, family, f"receipt {status}" + (f": {'; '.join(reasons)}" if reasons else "")))
    return out


def slots(stage: Stage) -> list[Slot]:
    out: list[Slot] = []
    for index, seat in enumerate(stage.seats):
        for _ in range(seat.count):
            out.append(Slot(chr(ord("A") + len(out)), seat.role, index))
    return out


def _options(slot: Slot, cands: dict[str, list[Candidate]], fixed: dict[str, str]) -> list[Candidate]:
    if slot.label in fixed:  # a finished seat keeps its profile, whatever happened since
        return [c for c in cands[slot.label] if c.profile_id == fixed[slot.label]]
    return [c for c in cands[slot.label] if c.usable]


def _fill(seat_slots: list[Slot], cands, fixed, need: int) -> list[Candidate] | None:
    def walk(i: int, picked: list[Candidate]) -> list[Candidate] | None:
        if i == len(seat_slots):
            return picked if len({c.family for c in picked}) >= need else None
        for c in _options(seat_slots[i], cands, fixed):
            found = walk(i + 1, picked + [c])
            if found is not None:
                return found
        return None

    return walk(0, [])


def _refusal(stage: Stage, role_id: str, need: int, seat_slots: list[Slot], cands, fixed) -> Refusal:
    kept = []
    for s in seat_slots:
        if s.label in fixed:
            c = next(c for c in cands[s.label] if c.profile_id == fixed[s.label])
            kept.append((s.label, c.profile_id, c.family))
    open_slots = [s for s in seat_slots if s.label not in fixed]
    word = "family" if need == 1 else "families"
    stuck = next((s for s in open_slots if not any(c.usable for c in cands[s.label])), None)
    if stuck is not None:
        lines = [f"refused: stage {stage.id}: {role_id} needs {need} {word}, 0 acceptable for seat {stuck.label}"]
        rejecting = [stuck]
    else:
        acceptable: dict[str, list[str]] = {}
        for _, pid, fam in kept:
            names = acceptable.setdefault(fam, [])
            if pid not in names:
                names.append(pid)
        for s in open_slots:
            for c in _options(s, cands, fixed):
                names = acceptable.setdefault(c.family, [])
                if c.profile_id not in names:
                    names.append(c.profile_id)
        families = ", ".join(f"{fam}: {', '.join(names)}" for fam, names in acceptable.items()) or "none"
        lines = [f"refused: stage {stage.id}: {role_id} needs {need} {word}, {len(acceptable)} acceptable ({families})"]
        rejecting = open_slots
    lines += [f"  kept: {label} {pid} ({fam})" for label, pid, fam in kept]
    seen: set[tuple[str, str]] = set()
    for s in rejecting:
        for c in cands[s.label]:
            if not c.usable and (c.profile_id, c.reason) not in seen:
                seen.add((c.profile_id, c.reason))
                lines.append(f"  rejected: {c.profile_id}: {c.reason}")
    return Refusal("\n".join(lines))


def assign(stage: Stage, slot_list: list[Slot], cands: dict[str, list[Candidate]], fixed: dict[str, str]) -> Assignment | Refusal:
    profiles: dict[str, str] = {}
    families: dict[str, str] = {}
    warnings: list[str] = []
    for index, seat in enumerate(stage.seats):
        seat_slots = [s for s in slot_list if s.seat_index == index]
        chosen = _fill(seat_slots, cands, fixed, seat.distinct_families)
        if chosen is None:
            return _refusal(stage, seat.role, seat.distinct_families, seat_slots, cands, fixed)
        for s, c in zip(seat_slots, chosen):
            profiles[s.label], families[s.label] = c.profile_id, c.family
            if c.verdict == PROVISIONAL:
                w = f"{seat.role} is provisional: no suite, profile {c.profile_id} not qualified"
                if w not in warnings:
                    warnings.append(w)
    return Assignment(profiles, families, tuple(warnings))


def route(stage: Stage, roles: dict[str, Role], root: Path, status_fn: StatusFn, *, fixed: dict[str, str],
          run_excluded: dict[str, str], slot_excluded: dict[str, dict[str, str]],
          sandbox: Callable[[Role], str | None] = sandbox_problem) -> Assignment | Refusal:
    slot_list = slots(stage)
    cands = {
        s.label: candidates(roles[s.role_id], root, status_fn,
                            excluded={**run_excluded, **slot_excluded.get(s.label, {})}, sandbox=sandbox)
        for s in slot_list
    }
    return assign(stage, slot_list, cands, fixed)
