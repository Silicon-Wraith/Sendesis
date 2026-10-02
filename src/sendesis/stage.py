"""`sendesis stage`: run one stage's seats through the router and failover (M3.2).

No evidence pack, adjudication or gate: those arrive with the M3.3 compiler, which
builds on run_stage. The record goes to .sendesis/runs/<run-id>/ (ignored by git).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sendesis.failover import Attempt, RunState, SeatFn, StageStopped, run_slot
from sendesis.gitstate import GitError, is_clean
from sendesis.model import Role, ValidationFailed, load_role
from sendesis.qualify import review_message
from sendesis.receipts import iso, profile_status
from sendesis.router import Refusal, StatusFn, route, sandbox_problem, slots
from sendesis.seat import run_role
from sendesis.workflow import load_workflow


class StageError(Exception):
    pass


@dataclass
class StageResult:
    run_id: str
    status: str
    refusal: str | None
    stop_reason: str | None
    initial_assignment: dict[str, str]
    attempts: list[Attempt]
    seats: dict[str, dict[str, Any]]
    warnings: list[str]
    record_path: Path


def default_seat_fn(root: Path) -> SeatFn:
    def seat_fn(role, profile, message, cwd, timeout_s):
        return run_role(role, profile, message, root=root, cwd=cwd, timeout_s=timeout_s)
    return seat_fn


def _cached_status(root: Path, now: datetime) -> StatusFn:
    versions: dict[str, str | None] = {}
    cache: dict[tuple[str, str], tuple[str, list[str]]] = {}

    def status_fn(role, profile):
        key = (role.id, profile.id)
        if key not in cache:
            cache[key] = profile_status(root, role, profile, now, versions=versions)
        return cache[key]
    return status_fn


def run_stage(root: Path, workflow_path: Path, stage_id: str, *, diff: str, context: dict[str, str] | None = None,
              cwd: Path | None = None, now: datetime | None = None, seat_fn: SeatFn | None = None,
              status_fn: StatusFn | None = None, runs_dir: Path | None = None,
              sandbox: Callable[[Role], str | None] = sandbox_problem) -> StageResult:
    now = now or datetime.now(timezone.utc)
    cwd = cwd or root
    context = context or {}
    try:
        wf = load_workflow(workflow_path, root)
    except (ValidationFailed, FileNotFoundError) as exc:
        raise StageError(str(exc)) from exc
    stage = next((s for s in wf.stages if s.id == stage_id), None)
    if stage is None:
        raise StageError(f"workflow {wf.id} has no stage {stage_id}")
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    run_dir = (runs_dir or root / ".sendesis" / "runs") / run_id
    state = RunState()
    initial: dict[str, str] = {}
    finished: dict[str, tuple[str, str, Any]] = {}

    def finish(status: str, *, refusal: str | None = None, stop_reason: str | None = None) -> StageResult:
        run_dir.mkdir(parents=True, exist_ok=True)
        seats = {}
        for label, (role_id, pid, output) in finished.items():
            (run_dir / f"seat-{label}.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
            seats[label] = {"role": role_id, "profile": pid, "outcome": "ok", "output": f"seat-{label}.json"}
        record = {
            "run_id": run_id,
            "workflow": {"id": wf.id, "sha256": wf.sha256},
            "stage": stage.id,
            "started_at": iso(now),
            "finished_at": iso(datetime.now(timezone.utc)),
            "input_sha256": hashlib.sha256(json.dumps({"diff": diff, "context": context}, sort_keys=True).encode()).hexdigest(),
            "status": status,
            "warnings": state.warnings,
            "initial_assignment": initial,
            "attempts": [asdict(a) for a in state.attempts],
            "seats": seats,
        }
        if refusal is not None:
            record["refusal"] = refusal
        if stop_reason is not None:
            record["stop_reason"] = stop_reason
        path = run_dir / "stage.json"
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return StageResult(run_id, status, refusal, stop_reason, initial, state.attempts, seats, state.warnings, path)

    roles: dict[str, Role] = {}
    for seat in stage.seats:
        try:
            roles[seat.role] = load_role(root / "roles" / f"{seat.role}.yaml", root)
        except (ValidationFailed, FileNotFoundError):
            return finish("refused", refusal=f"refused: stage {stage.id}: role {seat.role} not found")
    try:
        clean = is_clean(cwd)
    except GitError as exc:
        return finish("refused", refusal=f"refused: {exc}")
    if not clean:
        return finish("refused", refusal="refused: dirty tree: commit or stash first")

    status_fn = status_fn or _cached_status(root, now)
    seat_fn = seat_fn or default_seat_fn(root)
    plan = route(stage, roles, root, status_fn, fixed={}, run_excluded={}, slot_excluded={}, sandbox=sandbox)
    if isinstance(plan, Refusal):
        return finish("refused", refusal=plan.text)
    initial.update(plan.profiles)
    state.warnings.extend(plan.warnings)
    messages = {rid: review_message(rid, diff, context) for rid in roles}
    try:
        for slot in slots(stage):
            res = run_slot(slot, stage, roles, state, root=root, cwd=cwd, messages=messages,
                           status_fn=status_fn, seat_fn=seat_fn, sandbox=sandbox)
            if isinstance(res, Refusal):
                return finish("refused", refusal=res.text)
            finished[slot.label] = (slot.role_id, state.fixed[slot.label], res.output)
    except StageStopped as exc:
        return finish("stopped", stop_reason=str(exc))
    return finish("completed")
