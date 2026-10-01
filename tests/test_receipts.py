import json
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path

import pytest

from sendesis.model import load_profile, load_role
from sendesis.receipts import effective_status

REPO = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


def phase2_receipt() -> dict:
    path = sorted((REPO / "receipts" / "security-reviewer" / "claude-opus").glob("*.json"))[0]
    return json.loads(path.read_text())


def v2_receipt(role, profile, fp="a" * 64) -> dict:
    return {
        "kind": "single",
        "role": {"id": role.id, "version": role.version, "sha256": role.sha256, "prompt_sha256": role.prompt_sha256},
        "profile": {"ids": [profile.id], "sha256": profile.sha256},
        "observed": [{"profile_id": profile.id, "model": profile.model.id, "cli_version": profile.model.cli_version,
                      "config_fingerprint": fp, "workdir_context_sha256": "b" * 64}],
        "suite": {"path": "suites/security-reviewer", "sha256": "c" * 64, "n_cases": 100},
        "status": "QUALIFIED", "scores": [], "cost": {"input_tokens": 0, "output_tokens": 0, "wall_s": 0},
        "issued_at": "2026-10-01T00:00:00Z", "expires_at": "2026-10-31T00:00:00Z",
    }


def args(root, **over):
    role = load_role(root / "roles" / "security-reviewer.yaml", root)
    profile = load_profile(root / "profiles" / "claude-opus.yaml", root)
    base = dict(role=role, profile=profile, suite_sha256="c" * 64, cli_version=profile.model.cli_version,
                config_fingerprint="a" * 64, now=NOW)
    base.update(over)
    return role, profile, base


def test_phase2_receipt_reads_unknown(root: Path):
    _, _, kw = args(root)
    status, reasons = effective_status(phase2_receipt(), **kw)
    assert status == "UNKNOWN" and reasons == ["no config fingerprint (issued before M3.1)"]


def test_matching_v2_receipt_holds(root: Path):
    role, profile, kw = args(root)
    assert effective_status(v2_receipt(role, profile), **kw) == ("QUALIFIED", [])


def test_fingerprint_change_voids(root: Path):
    role, profile, kw = args(root, config_fingerprint="d" * 64)
    status, reasons = effective_status(v2_receipt(role, profile), **kw)
    assert status == "UNKNOWN" and any("config fingerprint" in r for r in reasons)


def test_cli_version_change_voids(root: Path):
    role, profile, kw = args(root, cli_version="0.0.1")
    status, reasons = effective_status(v2_receipt(role, profile), **kw)
    assert status == "UNKNOWN" and any("cli version" in r for r in reasons)


DRIFT = [
    (lambda k: k.update(role=replace(k["role"], version="0.0.9")), "role version"),
    (lambda k: k.update(role=replace(k["role"], sha256="0" * 64)), "role file"),
    (lambda k: k.update(role=replace(k["role"], prompt_sha256="0" * 64)), "role prompt"),
    (lambda k: k.update(profile=replace(k["profile"], sha256="0" * 64)), "profile file"),
    (lambda k: k.update(suite_sha256="0" * 64), "suite changed"),
    (lambda k: k.update(profile=replace(k["profile"], model=replace(k["profile"].model, id="other-model"))), "model observed"),
    (lambda k: k.update(now=datetime(2026, 11, 5, tzinfo=timezone.utc)), "expired"),
    (lambda k: k.update(role=replace(k["role"], qualification=None)), "no qualification suite"),
]


@pytest.mark.parametrize("change, reason", DRIFT)
def test_drift_voids_receipt(root: Path, change, reason):
    role, profile, kw = args(root)
    receipt = v2_receipt(role, profile)
    change(kw)
    status, reasons = effective_status(receipt, **kw)
    assert status == "UNKNOWN" and any(reason in r for r in reasons), reasons
