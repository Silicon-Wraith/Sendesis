import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import edit_yaml
from sendesis.cli import main
from sendesis.qualify import QualifyError, qualify
from sendesis.seat import Outcome, SeatResult
from test_suite_scoring import write_case

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
PIN = "2.1.286"


@pytest.fixture
def qroot(root: Path) -> Path:
    """Repo copy plus a 4-case suite (2 vulnerable, 2 clean) wired into the role."""
    suite = root / "suites" / "smoke"
    for case_id in ("v1", "v2", "c1", "c2"):
        write_case(suite, case_id, clean=case_id.startswith("c"), context={"app.py": f"x = 2  # marker {case_id}\n"})

    def wire(d):
        d["qualification"]["suite"] = "suites/smoke"
        d["qualification"]["min_cases"] = 4
        for m in d["qualification"]["metrics"]:
            if m["direction"] == "higher_is_better" and m["name"] != "schema_validity":
                m["threshold"] = 0.3

    edit_yaml(root / "roles" / "security-reviewer.yaml", wire)
    edit_yaml(root / "profiles" / "claude-opus.yaml", lambda d: d["model"].update(cli_version=PIN))
    return root


def output(findings):
    return {"role_id": "security-reviewer", "findings": findings, "checks": [{"id": "injection", "outcome": "findings" if findings else "no_findings"}]}


HIT = {"id": "F-1", "claim": "SQL built from input.", "category": "CWE-89", "severity": "blocking", "claim_status": "proven",
       "location": {"file": "app.py", "line_start": 10, "line_end": 12}, "evidence": [{"kind": "code_quote", "file": "app.py", "text": "x"}]}


def ok(findings=(), model="claude-opus-5-5"):
    return SeatResult(Outcome.OK, output=output(list(findings)), observed_model=model, cli_version=PIN,
                      config_fingerprint="a" * 64, input_tokens=100, output_tokens=20, wall_s=1.0)


def scripted(plan):
    """plan maps a case marker to a list of SeatResults, returned in order."""
    calls = []

    def seat_fn(role, profile, message, workdir, timeout_s):
        marker = re.search(r"marker (\w+)", message).group(1)
        calls.append(marker)
        return plan[marker].pop(0)

    seat_fn.calls = calls
    return seat_fn


def run(qroot, plan, tmp_path, **kw):
    return qualify(qroot, "security-reviewer", "claude-opus", seat_fn=scripted(plan), version_fn=lambda b: PIN,
                   now=NOW, workdir=tmp_path / "wd", runs_dir=tmp_path / "runs", **kw)


def test_qualified_receipt_on_the_seat_path(qroot, tmp_path):
    plan = {"v1": [ok([HIT])], "v2": [ok([HIT])], "c1": [ok()], "c2": [ok()]}
    r = run(qroot, plan, tmp_path).receipt
    assert r["status"] == "QUALIFIED", r.get("status_reason")
    obs = r["observed"][0]
    assert obs["config_fingerprint"] == "a" * 64 and obs["model"] == "claude-opus-5-5" and obs["cli_version"] == PIN
    assert {s["metric"]: s["basis"] for s in r["scores"]}["schema_validity"] == "point"


def test_invalid_output_retried_once_then_counted_invalid(qroot, tmp_path):
    bad = SeatResult(Outcome.INVALID, reason="(root): 'checks' is a required property", observed_model="claude-opus-5-5")
    fn_plan = {"v1": [bad, SeatResult(Outcome.INVALID, reason="again")], "v2": [ok([HIT])], "c1": [ok()], "c2": [ok()]}
    seat_fn = scripted(fn_plan)
    r = qualify(qroot, "security-reviewer", "claude-opus", seat_fn=seat_fn, version_fn=lambda b: PIN, now=NOW,
                workdir=tmp_path / "wd", runs_dir=tmp_path / "runs").receipt
    assert seat_fn.calls.count("v1") == 2
    validity = next(s for s in r["scores"] if s["metric"] == "schema_validity")
    assert validity["value"] == pytest.approx(3 / 4)


def test_rate_limit_stops_with_unknown(qroot, tmp_path):
    plan = {"c1": [SeatResult(Outcome.RATE_LIMIT, reason="ModelRateLimitError: usage limit")], "c2": [ok()], "v1": [ok()], "v2": [ok()]}
    seat_fn = scripted(plan)
    r = qualify(qroot, "security-reviewer", "claude-opus", seat_fn=seat_fn, version_fn=lambda b: PIN, now=NOW,
                workdir=tmp_path / "wd", runs_dir=tmp_path / "runs").receipt
    assert r["status"] == "UNKNOWN" and "rate limit" in r["status_reason"] and seat_fn.calls == ["c1"]


def test_cli_version_mismatch_spends_nothing(qroot, tmp_path):
    seat_fn = scripted({})
    r = qualify(qroot, "security-reviewer", "claude-opus", seat_fn=seat_fn, version_fn=lambda b: "9.9.9", now=NOW,
                workdir=tmp_path / "wd", runs_dir=tmp_path / "runs").receipt
    assert r["status"] == "UNKNOWN" and "does not match" in r["status_reason"] and seat_fn.calls == []


def test_wrong_observed_model_is_unknown(qroot, tmp_path):
    plan = {k: [ok(model="claude-haiku")] for k in ("v1", "v2", "c1", "c2")}
    r = run(qroot, plan, tmp_path).receipt
    assert r["status"] == "UNKNOWN" and "claude-haiku" in r["status_reason"]


def test_provisional_role_is_refused(qroot, tmp_path):
    edit_yaml(qroot / "roles" / "security-reviewer.yaml", lambda d: d.pop("qualification"))
    with pytest.raises(QualifyError, match="provisional"):
        run(qroot, {}, tmp_path)


def test_dry_run_needs_a_local_model(qroot, tmp_path):
    with pytest.raises(QualifyError, match="local"):
        run(qroot, {}, tmp_path, dry_run=True)


def test_dry_run_writes_no_receipt(qroot, tmp_path):
    def local(d):
        d.update(enabled=True, family="qwen")
        d["model"].update(id="qwen-test")
    edit_yaml(qroot / "profiles" / "ollama-local.yaml", local)
    edit_yaml(qroot / "roles" / "security-reviewer.yaml", lambda d: d["failover_order"].append("ollama-local") if "ollama-local" not in d["failover_order"] else None)
    plan = {k: [ok(model="qwen-test")] for k in ("v1", "v2", "c1", "c2")}
    result = qualify(qroot, "security-reviewer", "ollama-local", seat_fn=scripted(plan), version_fn=lambda b: None, now=NOW,
                     workdir=tmp_path / "wd", runs_dir=tmp_path / "runs", dry_run=True)
    assert result.path.name == "summary.json" and result.path.is_file()
    assert not (qroot / "receipts" / "security-reviewer" / "ollama-local").exists()


def test_cli_qualify_reports_local_flag(qroot, tmp_path, capsys, monkeypatch):
    import sendesis.qualify as q

    monkeypatch.setattr(q, "default_seat_fn", lambda root: scripted({k: [ok(model="qwen-test")] for k in ("v1", "v2", "c1", "c2")}))
    def local(d):
        d.update(enabled=True, family="qwen")
        d["model"].update(id="qwen-test")
    edit_yaml(qroot / "profiles" / "ollama-local.yaml", local)
    assert main(["qualify", "security-reviewer", "ollama-local", "--local", "--root", str(qroot)]) == 0
    assert "DRY RUN" in capsys.readouterr().out


def test_fresh_receipt_survives_check_all(qroot, tmp_path, monkeypatch):
    import dataclasses

    import sendesis.receipts as receipts_mod
    from sendesis.model import load_profile, load_role

    # A real seat reports the fingerprint of the configuration it ran, so the fake reports the current one.
    fp = receipts_mod.current_fingerprint(load_profile(qroot / "profiles" / "claude-opus.yaml", qroot), load_role(qroot / "roles" / "security-reviewer.yaml", qroot))
    plan = {"v1": [ok([HIT])], "v2": [ok([HIT])], "c1": [ok()], "c2": [ok()]}
    plan = {k: [dataclasses.replace(r, config_fingerprint=fp) for r in v] for k, v in plan.items()}
    assert run(qroot, plan, tmp_path).receipt["status"] == "QUALIFIED"

    monkeypatch.setattr(receipts_mod, "installed_version", lambda binary: PIN)
    rows = receipts_mod.check_all(qroot, NOW + timedelta(days=1))
    assert [(r[2], r[3]) for r in rows] == [("QUALIFIED", [])]


@pytest.mark.parametrize("profile,pin,installed,proceeds", [
    ("codex-gpt", "0.155.1", "codex-cli 0.155.1", True),
    ("codex-gpt", "0.155.1", "codex-cli 0.155.2", False),
])
def test_version_pin_compares_parsed_versions(qroot, tmp_path, profile, pin, installed, proceeds):
    edit_yaml(qroot / "profiles" / f"{profile}.yaml", lambda d: d["model"].update(cli_version=pin))
    edit_yaml(qroot / "roles" / "security-reviewer.yaml", lambda d: d["failover_order"].append(profile) if profile not in d["failover_order"] else None)
    seat_fn = scripted({k: [ok(model="gpt-5.5")] for k in ("v1", "v2", "c1", "c2")})
    r = qualify(qroot, "security-reviewer", profile, seat_fn=seat_fn, version_fn=lambda b: installed, now=NOW,
                workdir=tmp_path / "wd", runs_dir=tmp_path / "runs").receipt
    assert bool(seat_fn.calls) is proceeds
    assert ("does not match profile pin" in (r.get("status_reason") or "")) is (not proceeds)
