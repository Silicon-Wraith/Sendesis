"""`sendesis qualify <role> <profile>`: run a role's suite on one profile and
write a receipt.

Status rules:
- UNKNOWN when the installed CLI version differs from the profile's pin
  (checked first, so no quota is spent), when a call fails or is rate
  limited, when the observed model is not the profile's model, when a metric
  cannot be computed, or when the suite has fewer cases than `min_cases`;
- otherwise QUALIFIED if every metric passes at the conservative end of its
  interval, else FAILED.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from sendesis import runners
from agno_cli_models.versions import parse_version
from sendesis.model import Profile, Role, ValidationFailed, load_profile, load_role, schema_validator
from sendesis.receipts import iso, write_receipt
from sendesis.runners import Call, RunResult, Status
from sendesis.runners.codex_cli import codex_home
from sendesis.scoring import CaseOutcome, compute_metrics, passes
from sendesis.suite import Case, load_suite

CONTEXT_FILES = ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", "AGENTS.override.md")


class QualifyError(Exception):
    pass


@dataclass
class QualifyResult:
    path: Path
    receipt: dict[str, Any]


def default_workdir(role_id: str) -> Path:
    # Outside the repo on purpose: Claude Code reads CLAUDE.md from every parent directory.
    return Path.home() / ".cache" / "sendesis" / "workdirs" / role_id


def workdir_context_sha256(workdir: Path) -> str:
    """Hash of every instruction file either CLI could load from the workdir,
    its parents, or the users' global config."""
    candidates = []
    for d in [workdir, *workdir.parents]:
        candidates += [d / name for name in CONTEXT_FILES]
    candidates += [Path.home() / ".claude" / "CLAUDE.md", codex_home() / "AGENTS.md"]
    h = hashlib.sha256()
    for path in candidates:
        if path.is_file():
            h.update(str(path).encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def prepare_workdir(workdir: Path, case: Case) -> Path:
    """A fixed, git-initialized directory. `case/` holds only the current case,
    under a neutral name so nothing in the path hints at the label."""
    workdir.mkdir(parents=True, exist_ok=True)
    if not (workdir / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=workdir, check=True, stdin=subprocess.DEVNULL)
    case_dir = workdir / "case"
    shutil.rmtree(case_dir, ignore_errors=True)
    case_dir.mkdir()
    (case_dir / "diff.patch").write_text(case.diff, encoding="utf-8")
    for rel, text in case.context.items():
        target = case_dir / "context" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return workdir


def build_prompt(role: Role, prompt_text: str, case: Case) -> str:
    parts = [prompt_text.rstrip(), "", f"Set role_id to {role.id}.", "", "## diff", "```diff", case.diff.rstrip(), "```"]
    if case.context:
        parts += ["", "## context files"]
        for rel, text in case.context.items():
            parts += ["", f"### {rel}", "```", text.rstrip(), "```"]
    return "\n".join(parts) + "\n"


def _call_once(run_fn, profile, role, call, validator) -> tuple[RunResult, bool]:
    result = run_fn(profile, role.tools_allowed, call)
    valid = result.status is Status.OK and result.output is not None and not list(validator.iter_errors(result.output))
    return result, valid


def qualify(
    root: Path,
    role_id: str,
    profile_id: str,
    *,
    suite_dir: Path | None = None,
    run_fn: Callable[[Profile, tuple[str, ...], Call], RunResult] = runners.run,
    version_fn: Callable[[str], str | None] = runners.cli_version,
    now: datetime | None = None,
    workdir: Path | None = None,
    runs_dir: Path | None = None,
) -> QualifyResult:
    try:
        role = load_role(root / "roles" / f"{role_id}.yaml", root)
        profile = load_profile(root / "profiles" / f"{profile_id}.yaml", root)
        if role.qualification is None:
            raise QualifyError(f"role {role.id} is provisional: it has no qualification block")
        suite = load_suite(suite_dir or root / role.qualification.suite)
    except (ValidationFailed, FileNotFoundError) as exc:
        raise QualifyError(str(exc)) from exc
    if not profile.enabled:
        raise QualifyError(f"profile {profile.id} is disabled")
    if profile.id not in role.failover_order:
        raise QualifyError(f"profile {profile.id} is not in {role.id}'s failover_order")

    started = now or datetime.now(timezone.utc)
    workdir = workdir or default_workdir(role.id)
    timeout_s = min(t for t in (profile.timeout_s, role.per_call_timeout_s) if t)
    validator = schema_validator(root, Path(role.output_schema).name)
    prompt_text = (root / role.prompt_file).read_text(encoding="utf-8")
    run_log = (runs_dir or root / "runs") / role.id / profile.id / started.strftime("%Y%m%dT%H%M%SZ")

    reasons: list[str] = []
    installed = version_fn(profile.cli_binary) if profile.cli_binary else None
    pin = profile.model.cli_version
    if profile.cli_binary and parse_version(installed or "") != parse_version(pin or ""):
        reasons.append(f"installed cli version {installed!r} does not match profile pin {pin!r}; no calls made")

    outcomes: list[CaseOutcome] = []
    results: list[RunResult] = []
    if not reasons:
        for case in suite.cases:
            call = Call(build_prompt(role, prompt_text, case), json.loads((root / role.output_schema).read_text()), prepare_workdir(workdir, case), timeout_s)
            result, valid = _call_once(run_fn, profile, role, call, validator)
            results.append(result)
            if result.status is Status.OK and not valid:  # one retry on invalid output
                result, valid = _call_once(run_fn, profile, role, call, validator)
                results.append(result)
            _log(run_log, case.id, result, valid)
            findings = (result.output or {}).get("findings", []) if valid else []
            outcomes.append(CaseOutcome(case.id, case.clean, case.labels, findings, valid, result.status is Status.OK))
            if result.status is not Status.OK:
                reasons.append(f"case {case.id}: {result.status.value}: {result.reason[:200]}")
                if result.status is Status.RATE_LIMIT:
                    reasons.append("stopped after rate limit")
                    break

    models = sorted({r.model for r in results if r.status is Status.OK and r.model})
    wrong = [m for m in models if m != profile.model.id]
    if wrong:
        reasons.append(f"observed model {', '.join(wrong)}, profile wants {profile.model.id}")

    scores = []
    if outcomes:
        metrics = compute_metrics(outcomes)
        for m in role.qualification.metrics:
            score = metrics.get(m.name)
            if score is None:
                reasons.append(f"metric {m.name} could not be computed")
                continue
            scores.append({
                "metric": m.name, "value": round(score.value, 6), "ci_low": round(score.ci_low, 6), "ci_high": round(score.ci_high, 6),
                "ci_method": score.ci_method, "threshold": m.threshold, "pass": passes(score, m.direction, m.threshold),
            })
    if outcomes and len(suite.cases) < role.qualification.min_cases:
        reasons.append(f"suite has {len(suite.cases)} cases, role requires at least {role.qualification.min_cases}")

    if reasons:
        status = "UNKNOWN"
    elif all(s["pass"] for s in scores):
        status = "QUALIFIED"
    else:
        status = "FAILED"
        reasons.append("failed: " + ", ".join(s["metric"] for s in scores if not s["pass"]))

    observed = {"profile_id": profile.id, "model": models[0] if len(models) == 1 else (",".join(models) or "not-observed"),
                "runner_config_sha256": runners.config_sha256(profile), "workdir_context_sha256": workdir_context_sha256(workdir)}
    if installed:
        observed["cli_version"] = installed
    list_usd = [r.list_usd for r in results if r.list_usd is not None]
    cost = {
        "input_tokens": sum(r.input_tokens for r in results),
        "cached_input_tokens": sum(r.cached_input_tokens for r in results),
        "output_tokens": sum(r.output_tokens for r in results),
        "wall_s": round(sum(r.wall_s for r in results), 3),
    }
    if list_usd:
        cost["list_usd"] = round(sum(list_usd), 6)

    receipt = {
        "kind": "single",
        "role": {"id": role.id, "version": role.version, "sha256": role.sha256, "prompt_sha256": role.prompt_sha256},
        "profile": {"ids": [profile.id], "sha256": profile.sha256},
        "observed": [observed],
        "suite": {"path": _suite_rel(root, suite.path), "sha256": suite.sha256, "n_cases": len(suite.cases)},
        "status": status,
        "scores": scores,
        "cost": cost,
        "issued_at": iso(started),
        "expires_at": iso(started + timedelta(days=role.qualification.expiry_days)),
    }
    if reasons:
        receipt["status_reason"] = "; ".join(reasons)
    return QualifyResult(write_receipt(root, receipt), receipt)


def _suite_rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _log(run_log: Path, case_id: str, result: RunResult, valid: bool) -> None:
    """Per-case detail for debugging. `runs/` is gitignored; receipts are the record."""
    run_log.mkdir(parents=True, exist_ok=True)
    data = asdict(result) | {"status": result.status.value, "valid": valid}
    (run_log / f"{case_id}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
