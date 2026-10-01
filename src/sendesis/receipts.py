"""Qualification receipts: plain JSON in git, written once, never edited.

A receipt records what was true when it was issued. `effective_status`
decides whether it still holds: any drift in role, prompt, profile, suite,
config fingerprint, CLI version or model, or an expired date, makes it UNKNOWN.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sendesis.model import Profile, Role, load_profile, load_role, rel_path, schema_validator
from agno_cli_models.versions import installed_version, parse_version
from sendesis.suite import suite_sha256

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime(TIME_FORMAT)


def parse_iso(s: str) -> datetime:
    return datetime.strptime(s, TIME_FORMAT).replace(tzinfo=timezone.utc)


def validate_receipt(root: Path, receipt: dict[str, Any]) -> list[str]:
    validator = schema_validator(root, "receipt.json")
    return [f"{'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}" for e in validator.iter_errors(receipt)]


def write_receipt(root: Path, receipt: dict[str, Any]) -> Path:
    errors = validate_receipt(root, receipt)
    if errors:
        raise ValueError("receipt does not validate: " + "; ".join(errors))
    issued = parse_iso(receipt["issued_at"]).strftime("%Y%m%dT%H%M%SZ")
    folder = root / "receipts" / receipt["role"]["id"] / "+".join(receipt["profile"]["ids"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{issued}.json"
    with path.open("x", encoding="utf-8") as fh:  # "x": never overwrite a receipt
        fh.write(json.dumps(receipt, indent=2) + "\n")
    return path


def effective_status(
    receipt: dict[str, Any],
    *,
    role: Role,
    profile: Profile,
    suite_sha256: str | None,
    cli_version: str | None,
    config_fingerprint: str,
    now: datetime,
) -> tuple[str, list[str]]:
    """Status a router may rely on for a single-profile receipt, and why it changed."""
    obs = next((o for o in receipt["observed"] if o["profile_id"] == profile.id), {})
    if "config_fingerprint" not in obs:
        return "UNKNOWN", ["no config fingerprint (issued before M3.1)"]
    reasons = []
    r_role, r_prof = receipt["role"], receipt["profile"]
    if role.provisional:
        reasons.append("role has no qualification suite now")
    if r_role["version"] != role.version:
        reasons.append(f"role version {r_role['version']} -> {role.version}")
    if r_role["sha256"] != role.sha256:
        reasons.append("role file changed")
    if r_role["prompt_sha256"] != role.prompt_sha256:
        reasons.append("role prompt changed")
    if r_prof["sha256"] != profile.sha256:
        reasons.append("profile file changed")
    if suite_sha256 is not None and receipt["suite"]["sha256"] != suite_sha256:
        reasons.append("suite changed")
    if obs["config_fingerprint"] != config_fingerprint:
        reasons.append("model class configuration changed (config fingerprint)")
    if profile.cli_binary and parse_version(obs.get("cli_version") or "") != parse_version(cli_version or ""):
        reasons.append(f"cli version {obs.get('cli_version')!r} -> {cli_version!r}")
    if obs.get("model") != profile.model.id:
        reasons.append(f"model observed {obs.get('model')!r}, profile now wants {profile.model.id!r}")
    if now >= parse_iso(receipt["expires_at"]):
        reasons.append(f"expired at {receipt['expires_at']}")
    return ("UNKNOWN", reasons) if reasons else (receipt["status"], [])


def current_fingerprint(profile: Profile, role: Role) -> str:
    """Build the model (no call is made) and fingerprint it."""
    from sendesis.qualify import default_workdir
    from sendesis.seat import build_model, fingerprint

    model = build_model(profile, role, cwd=default_workdir(role.id), timeout_s=profile.timeout_s)
    return fingerprint(model, profile)


def latest_receipts(root: Path) -> list[Path]:
    """The newest receipt per role and profile."""
    latest = []
    for folder in sorted(p for p in (root / "receipts").glob("*/*") if p.is_dir()):
        files = sorted(folder.glob("*.json"))
        if files:
            latest.append(files[-1])
    return latest


def check_all(root: Path, now: datetime) -> list[tuple[Path, str, str, list[str]]]:
    """(path, recorded status, effective status, reasons) for each latest single receipt."""
    rows = []
    versions: dict[str, str | None] = {}
    for path in latest_receipts(root):
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if receipt["kind"] != "single":
            continue
        try:
            role = load_role(root / "roles" / f"{receipt['role']['id']}.yaml", root)
            profile = load_profile(root / "profiles" / f"{receipt['profile']['ids'][0]}.yaml", root)
        except Exception as exc:  # a missing or broken file voids the receipt
            rows.append((path, receipt["status"], "UNKNOWN", [f"cannot load role or profile: {exc}"]))
            continue
        cases = root / receipt["suite"]["path"] / "cases"
        current_suite = suite_sha256(cases) if cases.is_dir() else None
        if profile.cli_binary and profile.cli_binary not in versions:
            versions[profile.cli_binary] = installed_version(profile.cli_binary)
        try:
            fingerprint = current_fingerprint(profile, role)
        except Exception as exc:  # SandboxUnavailable, a missing binary: void this row, keep listing
            rows.append((Path(rel_path(path, root)), receipt["status"], "UNKNOWN", [f"seat cannot be built: {exc}"]))
            continue
        status, reasons = effective_status(
            receipt,
            role=role,
            profile=profile,
            suite_sha256=current_suite,
            cli_version=versions.get(profile.cli_binary) if profile.cli_binary else None,
            config_fingerprint=fingerprint,
            now=now,
        )
        if current_suite is None:
            reasons = reasons + [f"suite {receipt['suite']['path']} not found"]
            status = "UNKNOWN"
        if receipt.get("status_reason"):
            reasons = reasons + [f"recorded: {receipt['status_reason']}"]
        rows.append((Path(rel_path(path, root)), receipt["status"], status, reasons))
    return rows
