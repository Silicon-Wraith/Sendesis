"""Running one seat slot until it succeeds, refuses or stops (M3.2 spec, section 3).

INVALID gets one retry on the same profile; RATE_LIMIT excludes the profile for the
rest of the run; any other failure excludes it for this seat only. Before each
attempt the whole stage is routed again, so the family rule holds after every
failover. An untyped exception, or a reviewer that changed the tree, stops the stage
and is never failed over.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from sendesis.gitstate import reset_to, snapshot, unchanged
from sendesis.model import Profile, Role, load_profile
from sendesis.router import Refusal, Slot, StatusFn, route, sandbox_problem
from sendesis.seat import Outcome, SeatResult
from sendesis.workflow import Stage

SeatFn = Callable[[Role, Profile, str, Path, float], SeatResult]


class StageStopped(Exception):
    pass


@dataclass
class Attempt:
    label: str
    role: str
    profile: str
    family: str
    outcome: str
    reason: str
    stall: dict[str, Any] | None
    wall_s: float
    input_tokens: int
    output_tokens: int


@dataclass
class RunState:
    fixed: dict[str, str] = field(default_factory=dict)
    run_excluded: dict[str, str] = field(default_factory=dict)
    slot_excluded: dict[str, dict[str, str]] = field(default_factory=dict)
    attempts: list[Attempt] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def timeout_for(role: Role, profile: Profile) -> float:
    return min(t for t in (profile.timeout_s, role.per_call_timeout_s) if t)


def _call(slot: Slot, role: Role, profile: Profile, family: str, message: str, cwd: Path,
          state: RunState, seat_fn: SeatFn) -> SeatResult:
    before = snapshot(cwd)
    try:
        res = seat_fn(role, profile, message, cwd, timeout_for(role, profile))
    except Exception as exc:
        raise StageStopped(f"seat {slot.label} ({role.id}): untyped exception {type(exc).__name__}: {exc}") from exc
    state.attempts.append(Attempt(slot.label, role.id, profile.id, family, res.outcome.value, res.reason,
                                  res.stall, res.wall_s, res.input_tokens, res.output_tokens))
    if role.kind == "reviewer" and not unchanged(cwd, before):
        raise StageStopped(f"reviewer seat {slot.label} ({role.id}) changed the tree")
    return res


def run_slot(slot: Slot, stage: Stage, roles: dict[str, Role], state: RunState, *, root: Path, cwd: Path,
             messages: dict[str, str], status_fn: StatusFn, seat_fn: SeatFn,
             sandbox: Callable[[Role], str | None] = sandbox_problem) -> SeatResult | Refusal:
    role = roles[slot.role_id]
    while True:
        plan = route(stage, roles, root, status_fn, fixed=state.fixed, run_excluded=state.run_excluded,
                     slot_excluded=state.slot_excluded, sandbox=sandbox)
        if isinstance(plan, Refusal):
            return plan
        for w in plan.warnings:
            if w not in state.warnings:
                state.warnings.append(w)
        pid = plan.profiles[slot.label]
        profile = load_profile(root / "profiles" / f"{pid}.yaml", root)
        start = snapshot(cwd)
        res = _call(slot, role, profile, plan.families[slot.label], messages[role.id], cwd, state, seat_fn)
        if res.outcome is Outcome.INVALID:  # one retry on the same profile
            res = _call(slot, role, profile, plan.families[slot.label], messages[role.id], cwd, state, seat_fn)
        if res.outcome is Outcome.OK:
            state.fixed[slot.label] = pid
            return res
        if res.outcome is Outcome.RATE_LIMIT:
            state.run_excluded[pid] = "rate-limited earlier in this run"
        else:
            state.slot_excluded.setdefault(slot.label, {})[pid] = f"failed this seat ({res.outcome.value})"
        if role.kind != "reviewer":
            reset_to(cwd, start)
