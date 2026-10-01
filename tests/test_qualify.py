import json
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import edit_yaml
from sendesis.cli import main
from sendesis.model import load_profile, load_role
from sendesis.qualify import QualifyError, qualify
from sendesis.receipts import effective_status, validate_receipt
from sendesis.runners import RunResult, Status
from test_suite_scoring import write_case

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
CLAUDE_VERSION = "2.1.281 (Claude Code)"  # the pin the test copy of claude-opus gets


@pytest.fixture
def qroot(root: Path, tmp_path: Path) -> Path:
    """Repo copy plus a 4-case suite (2 vulnerable, 2 clean) wired into the role."""
    (root / "roles" / "security-reviewer.prompt.md").write_text("Review the diff.\n")
    suite = root / "suites" / "smoke"
    for case_id in ("v1", "v2", "c1", "c2"):
        # The marker lets the fake runner tell cases apart; case ids never reach the prompt.
        write_case(suite, case_id, clean=case_id.startswith("c"), context={"app.py": f"x = 2  # marker {case_id}\n"})

    def wire(d):
        d["qualification"]["suite"] = "suites/smoke"
        d["qualification"]["min_cases"] = 4
        # Four cases cannot clear the real thresholds at the conservative end of a Wilson interval.
        for m in d["qualification"]["metrics"]:
            if m["direction"] == "higher_is_better":
                m["threshold"] = 0.3

    edit_yaml(root / "roles" / "security-reviewer.yaml", wire)
    # Pin the copy's CLI version so the tests do not follow the repo's real pin.
    edit_yaml(root / "profiles" / "claude-opus.yaml", lambda d: d["model"].update(cli_version=CLAUDE_VERSION))
    return root


def good_finding():
    return {"id": "f1", "claim": "SQL injection here", "category": "CWE-89", "severity": "blocking", "claim_status": "proven",
            "location": {"file": "app.py", "line_start": 11, "line_end": 11},
            "evidence": [{"kind": "code_quote", "file": "app.py", "text": "x = 2"}]}


class FakeRunner:
    """Answers like a perfect reviewer unless told otherwise."""

    def __init__(self, model="claude-opus-5-5", outputs=None, statuses=None):
        self.model = model
        self.outputs = outputs or {}
        self.statuses = statuses or {}
        self.calls = []

    def __call__(self, profile, capabilities, call):
        case_id = self._case_of(call)
        self.calls.append(case_id)
        status = self.statuses.get(case_id, Status.OK)
        if status is not Status.OK:
            return RunResult(status, reason="simulated", wall_s=1.0)
        if case_id in self.outputs:
            output = self.outputs[case_id]
        else:
            output = {"role_id": "security-reviewer", "findings": [] if case_id.startswith("c") else [good_finding()], "checks": []}
        return RunResult(Status.OK, output=output, text=json.dumps(output), model=self.model, cli_version="2.1.281",
                         input_tokens=1000, cached_input_tokens=400, output_tokens=100, wall_s=2.0, list_usd=0.01)

    @staticmethod
    def _case_of(call):
        return re.search(r"# marker (\w+)", call.prompt).group(1)


def run_qualify(qroot, runner, version=CLAUDE_VERSION, profile="claude-opus", now=NOW):
    return qualify(qroot, "security-reviewer", profile, run_fn=runner, version_fn=lambda binary: version,
                   now=now, workdir=qroot / "wd", runs_dir=qroot / "runs")


def test_perfect_reviewer_qualifies_and_receipt_validates(qroot):
    runner = FakeRunner()
    result = run_qualify(qroot, runner)
    r = result.receipt
    assert r["status"] == "QUALIFIED", r.get("status_reason")
    assert validate_receipt(qroot, r) == []
    assert sorted(runner.calls) == ["c1", "c2", "v1", "v2"]
    assert result.path.parent == qroot / "receipts" / "security-reviewer" / "claude-opus"
    assert json.loads(result.path.read_text()) == r
    assert r["expires_at"] == "2026-10-31T12:00:00Z"
    assert r["cost"] == {"input_tokens": 4000, "cached_input_tokens": 1600, "output_tokens": 400, "wall_s": 8.0, "list_usd": 0.04}
    names = {s["metric"] for s in r["scores"]}
    assert names == {"recall", "false_positives_per_clean_case", "schema_validity"}
    obs = r["observed"][0]
    assert obs["model"] == "claude-opus-5-5" and obs["cli_version"] == CLAUDE_VERSION
    assert len(obs["runner_config_sha256"]) == 64 and len(obs["workdir_context_sha256"]) == 64


def test_prompt_carries_diff_and_context(qroot):
    seen = []

    def runner(profile, caps, call):
        seen.append(call.prompt)
        return FakeRunner()(profile, caps, call)

    run_qualify(qroot, runner)
    assert "Review the diff." in seen[0]
    assert "+x = 2" in seen[0]
    assert "### app.py" in seen[0]
    assert not any(case_id in p.replace("marker " + case_id, "") for p in seen for case_id in ("v1", "v2", "c1", "c2"))


def test_changed_cli_version_gives_unknown_without_spending_calls(qroot):
    runner = FakeRunner()
    r = run_qualify(qroot, runner, version="2.1.286 (Claude Code)").receipt
    assert r["status"] == "UNKNOWN"
    assert "2.1.286" in r["status_reason"] and "2.1.281" in r["status_reason"]
    assert runner.calls == []
    assert validate_receipt(qroot, r) == []


@pytest.mark.parametrize("profile,installed,proceeds", [
    ("codex-gpt", "codex-cli 0.155.1", True),
    ("codex-gpt", "codex-cli 0.155.2", False),
    ("claude-opus", "2.1.281 (Claude Code)", True),
])
def test_version_pin_compares_parsed_versions(qroot, profile, installed, proceeds):
    runner = FakeRunner()
    r = run_qualify(qroot, runner, version=installed, profile=profile).receipt
    assert bool(runner.calls) is proceeds
    assert ("does not match profile pin" in (r.get("status_reason") or "")) is (not proceeds)


def test_too_few_cases_gives_unknown(qroot):
    edit_yaml(qroot / "roles" / "security-reviewer.yaml", lambda d: d["qualification"].update(min_cases=100))
    r = run_qualify(qroot, FakeRunner()).receipt
    assert r["status"] == "UNKNOWN"
    assert "4 cases" in r["status_reason"] and "100" in r["status_reason"]
    assert r["scores"]  # scores are still recorded


def test_poor_reviewer_fails(qroot):
    outputs = {"v1": {"role_id": "security-reviewer", "findings": [], "checks": []}, "v2": {"role_id": "security-reviewer", "findings": [], "checks": []}}
    r = run_qualify(qroot, FakeRunner(outputs=outputs)).receipt
    assert r["status"] == "FAILED"
    recall = next(s for s in r["scores"] if s["metric"] == "recall")
    assert recall["value"] == 0.0 and recall["pass"] is False


def test_wrong_observed_model_gives_unknown(qroot):
    r = run_qualify(qroot, FakeRunner(model="claude-sonnet-5-5")).receipt
    assert r["status"] == "UNKNOWN"
    assert "claude-sonnet-5-5" in r["status_reason"]


def test_invalid_output_is_retried_once(qroot):
    attempts = {"v1": 0}
    base = FakeRunner()

    def runner(profile, caps, call):
        case = FakeRunner._case_of(call)
        if case == "v1":
            attempts["v1"] += 1
            if attempts["v1"] == 1:
                return RunResult(Status.OK, output={"nonsense": True}, model="claude-opus-5-5", wall_s=1.0)
        return base(profile, caps, call)

    r = run_qualify(qroot, runner).receipt
    assert attempts["v1"] == 2
    assert r["status"] == "QUALIFIED"


def test_rate_limit_stops_run_and_gives_unknown(qroot):
    runner = FakeRunner(statuses={"c2": Status.RATE_LIMIT})
    r = run_qualify(qroot, runner).receipt
    assert r["status"] == "UNKNOWN"
    assert "rate_limit" in r["status_reason"]
    assert "v1" not in runner.calls  # cases after the rate limit were not attempted


def test_disabled_profile_is_refused(qroot):
    with pytest.raises(QualifyError):
        run_qualify(qroot, FakeRunner(), profile="vllm-local")


def test_receipts_are_never_overwritten(qroot):
    a = run_qualify(qroot, FakeRunner()).path
    b = run_qualify(qroot, FakeRunner(), now=NOW + timedelta(seconds=1)).path
    assert a != b and a.exists() and b.exists()


# ---- effective status (what the Phase 3 router will ask) ------------------------------


def _inputs(qroot):
    role = load_role(qroot / "roles" / "security-reviewer.yaml", qroot)
    profile = load_profile(qroot / "profiles" / "claude-opus.yaml", qroot)
    from sendesis.runners import config_sha256
    from sendesis.suite import load_suite
    return dict(role=role, profile=profile, suite_sha256=load_suite(qroot / "suites" / "smoke").sha256,
                cli_version=CLAUDE_VERSION, runner_config_sha256=config_sha256(profile), now=NOW + timedelta(days=1))


def test_effective_status_holds_when_nothing_changed(qroot):
    r = run_qualify(qroot, FakeRunner()).receipt
    assert effective_status(r, **_inputs(qroot)) == ("QUALIFIED", [])


@pytest.mark.parametrize("change, reason", [
    (lambda i: i.update(cli_version="2.1.286 (Claude Code)"), "cli version"),
    (lambda i: i.update(now=NOW + timedelta(days=31)), "expired"),
    (lambda i: i.update(suite_sha256="0" * 64), "suite"),
    (lambda i: i.update(runner_config_sha256="0" * 64), "runner config"),
    (lambda i: i.update(profile=replace(i["profile"], sha256="0" * 64)), "profile"),
    (lambda i: i.update(profile=replace(i["profile"], model=replace(i["profile"].model, id="claude-sonnet-5-5"))), "model"),
    (lambda i: i.update(role=replace(i["role"], version="0.3.0")), "role version"),
    (lambda i: i.update(role=replace(i["role"], sha256="0" * 64)), "role file"),
    (lambda i: i.update(role=replace(i["role"], prompt_sha256="0" * 64)), "prompt"),
])
def test_effective_status_turns_unknown_on_drift(qroot, change, reason):
    r = run_qualify(qroot, FakeRunner()).receipt
    inputs = _inputs(qroot)
    change(inputs)
    status, reasons = effective_status(r, **inputs)
    assert status == "UNKNOWN"
    assert any(reason in x for x in reasons), reasons


# ---- CLI -------------------------------------------------------------------------------


def test_cli_receipts_reports_unknown_after_version_change(qroot, capsys, monkeypatch):
    run_qualify(qroot, FakeRunner())
    import sendesis.receipts as receipts_mod
    monkeypatch.setattr(receipts_mod, "cli_version", lambda binary: "2.1.286 (Claude Code)")
    assert main(["receipts", "--root", str(qroot)]) == 0
    out = capsys.readouterr().out
    assert "claude-opus" in out and "QUALIFIED" in out and "UNKNOWN" in out and "cli version" in out


def test_cli_receipts_shows_recorded_reason(qroot, capsys, monkeypatch):
    run_qualify(qroot, FakeRunner(), version="9.9.9")  # UNKNOWN at issue time
    import sendesis.receipts as receipts_mod
    monkeypatch.setattr(receipts_mod, "cli_version", lambda binary: "9.9.9")
    main(["receipts", "--root", str(qroot)])
    assert "does not match profile pin" in capsys.readouterr().out
