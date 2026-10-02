import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import edit_yaml
from sendesis.qualify import build_message, review_message
from sendesis.seat import Outcome
from sendesis.stage import StageError, run_stage
from sendesis.suite import load_suite
from stage_helpers import add_role, git_init, ok, result, scripted, write_workflow

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
ORDER = ["claude-opus", "codex-gpt", "ollama-local"]
PROFILES = ("claude-opus", "codex-gpt", "ollama-local", "vllm-local")


def make(root: Path, seats, *, roles=("p",)):
    for r in roles:
        add_role(root, r, order=ORDER)
    wf = write_workflow(root, "wf", seats)
    git_init(root)
    return wf


def go(root, wf, fn, **kw):
    return run_stage(root, wf, "review", diff="+x = 1\n", context={"app.py": "x = 1\n"}, now=NOW,
                     seat_fn=fn, runs_dir=root / ".sendesis" / "runs", **kw)


def test_review_message_matches_build_message(root: Path):
    case = load_suite(root / "suites" / "security-reviewer-smoke").cases[0]
    role = type("R", (), {"id": "security-reviewer"})()
    assert review_message("security-reviewer", case.diff, case.context) == build_message(role, case)


def test_completed_stage_writes_record(root: Path):
    wf = make(root, [{"role": "p", "count": 2, "distinct_families": 2}])
    fn = scripted({"claude-opus": [result(Outcome.STALL), ok()], "codex-gpt": [ok()]})
    r = go(root, wf, fn)
    assert r.status == "completed" and r.refusal is None
    assert r.initial_assignment == {"A": "claude-opus", "B": "codex-gpt"}
    rec = json.loads(r.record_path.read_text())
    assert rec["status"] == "completed" and rec["run_id"] == "20261003T120000Z"
    assert rec["workflow"]["id"] == "wf" and rec["stage"] == "review"
    assert [(a["label"], a["profile"], a["outcome"]) for a in rec["attempts"]] == [
        ("A", "claude-opus", "stall"), ("A", "codex-gpt", "ok"), ("B", "claude-opus", "ok")]
    assert rec["seats"]["A"] == {"role": "p", "profile": "codex-gpt", "outcome": "ok", "output": "seat-A.json"}
    assert json.loads((r.record_path.parent / "seat-A.json").read_text())["findings"] == []
    assert any("provisional" in w for w in rec["warnings"])


def test_no_seat_input_names_a_profile(root: Path):
    wf = make(root, [{"role": "p", "count": 2, "distinct_families": 2}])
    fn = scripted({"claude-opus": [ok()], "codex-gpt": [ok()]})
    go(root, wf, fn)
    for _, _, message in fn.calls:
        assert not any(p in message for p in PROFILES)


def test_dirty_tree_refuses_before_any_call(root: Path):
    wf = make(root, [{"role": "p"}])
    (root / "roles" / "p.yaml").write_text((root / "roles" / "p.yaml").read_text() + "\n# edited\n")
    fn = scripted({})
    r = go(root, wf, fn)
    assert r.status == "refused" and r.refusal == "refused: dirty tree: commit or stash first" and fn.calls == []


def test_unqualified_stage_refuses_before_any_call(root: Path):
    add_role(root, "q", order=ORDER, suite=True)
    wf = write_workflow(root, "wf", [{"role": "q"}])
    git_init(root)
    fn = scripted({})
    r = go(root, wf, fn, status_fn=lambda role, profile: ("UNKNOWN", ["suite has 30 cases, role requires at least 100"]))
    assert r.status == "refused" and fn.calls == []
    assert r.refusal.startswith("refused: stage review: q needs 1 family, 0 acceptable for seat A")
    assert json.loads(r.record_path.read_text())["refusal"] == r.refusal


def test_missing_role_refuses_before_any_call(root: Path):
    wf = write_workflow(root, "wf", [{"role": "nobody"}])
    git_init(root)
    fn = scripted({})
    r = go(root, wf, fn)
    assert r.status == "refused" and r.refusal == "refused: stage review: role nobody not found" and fn.calls == []


def test_stopped_stage_is_recorded(root: Path):
    wf = make(root, [{"role": "p"}])

    def boom(cwd):
        raise RuntimeError("bug")

    r = go(root, wf, scripted({"claude-opus": [boom]}))
    assert r.status == "stopped" and "untyped exception RuntimeError: bug" in r.stop_reason
    assert json.loads(r.record_path.read_text())["stop_reason"] == r.stop_reason


def test_unknown_stage_id_is_an_error(root: Path):
    wf = make(root, [{"role": "p"}])
    with pytest.raises(StageError, match="has no stage nope"):
        run_stage(root, wf, "nope", diff="", now=NOW, seat_fn=scripted({}))
