import json
import shutil
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


def test_invalid_role_refuses_with_its_error(root: Path):
    (root / "roles" / "bad.yaml").write_text("id: bad\n")
    wf = write_workflow(root, "wf", [{"role": "bad"}])
    git_init(root)
    fn = scripted({})
    r = go(root, wf, fn)
    assert r.status == "refused" and fn.calls == []
    assert r.refusal.startswith("refused: stage review: role bad cannot be loaded: ")
    assert "not found" not in r.refusal


def test_status_fn_failure_stops_the_stage_with_a_record(root: Path):
    add_role(root, "q", order=ORDER, suite=True)
    wf = write_workflow(root, "wf", [{"role": "q"}])
    git_init(root)

    def bad(role, profile):
        raise RuntimeError("bad receipt")

    fn = scripted({})
    r = go(root, wf, fn, status_fn=bad)
    assert r.status == "stopped" and "bad receipt" in r.stop_reason and fn.calls == []
    assert json.loads(r.record_path.read_text())["status"] == "stopped"


def test_git_failure_mid_run_stops_the_stage_and_keeps_the_attempt(root: Path):
    wf = make(root, [{"role": "p"}])

    def wreck(cwd):
        shutil.rmtree(cwd / ".git")
        return ok()

    r = go(root, wf, scripted({"claude-opus": [wreck]}))
    assert r.status == "stopped" and r.stop_reason
    rec = json.loads(r.record_path.read_text())
    assert rec["status"] == "stopped" and [a["profile"] for a in rec["attempts"]] == ["claude-opus"]


def test_mid_run_refusal_keeps_the_finished_seat(root: Path):
    wf = make(root, [{"role": "p", "count": 2, "distinct_families": 1}])
    fn = scripted({"claude-opus": [ok(), result(Outcome.ERROR)], "codex-gpt": [result(Outcome.ERROR)],
                   "ollama-local": [result(Outcome.ERROR)]})
    r = go(root, wf, fn)
    assert r.status == "refused"
    assert r.refusal.startswith("refused: stage review: p needs 1 family, 0 acceptable for seat B")
    assert (r.record_path.parent / "seat-A.json").exists()
    assert list(r.seats) == ["A"]


def test_unknown_stage_id_is_an_error(root: Path):
    wf = make(root, [{"role": "p"}])
    with pytest.raises(StageError, match="has no stage nope"):
        run_stage(root, wf, "nope", diff="", now=NOW, seat_fn=scripted({}))


@pytest.fixture
def inputs(tmp_path_factory) -> Path:
    """Diff and context live outside `root`, so they do not dirty its git tree."""
    return tmp_path_factory.mktemp("inputs")


def cli_setup(root: Path, inputs: Path, monkeypatch, plan):
    import sendesis.stage as st

    wf = make(root, [{"role": "p", "count": 2, "distinct_families": 2}])
    monkeypatch.setattr(st, "default_seat_fn", lambda r: scripted(plan))
    diff = inputs / "change.diff"
    diff.write_text("+x = 1\n")
    return wf, diff


def test_cli_stage_completed_prints_mapping_last(root: Path, inputs: Path, monkeypatch, capsys):
    from sendesis.cli import main

    wf, diff = cli_setup(root, inputs, monkeypatch, {"claude-opus": [result(Outcome.STALL), ok()], "codex-gpt": [ok()]})
    assert main(["stage", str(wf), "review", "--diff", str(diff), "--root", str(root)]) == 0
    out = capsys.readouterr().out
    head, _, tail = out.partition("mapping:")
    assert out.startswith("COMPLETED  stage review of wf")
    seat_lines = [ln for ln in head.splitlines() if ln.startswith("  seat ")]
    assert any("seat A: stall" in ln for ln in seat_lines) and not any(p in ln for ln in seat_lines for p in PROFILES)
    assert "A claude-opus stall" in tail and "A codex-gpt ok" in tail and "record:" in tail


def test_cli_stage_refused_exits_1(root: Path, inputs: Path, monkeypatch, capsys):
    from sendesis.cli import main

    edit_yaml(root / "profiles" / "codex-gpt.yaml", lambda d: d.update(enabled=False))
    edit_yaml(root / "profiles" / "ollama-local.yaml", lambda d: d.update(enabled=False))
    wf, diff = cli_setup(root, inputs, monkeypatch, {})
    assert main(["stage", str(wf), "review", "--diff", str(diff), "--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert out.startswith("REFUSED") and "needs 2 families, 1 acceptable" in out


def test_cli_stage_missing_diff_exits_2(root: Path, inputs: Path, monkeypatch, capsys):
    from sendesis.cli import main

    wf, _ = cli_setup(root, inputs, monkeypatch, {})
    assert main(["stage", str(wf), "review", "--diff", str(inputs / "none.diff"), "--root", str(root)]) == 2
    assert capsys.readouterr().out.startswith("FAIL ")


def test_cli_stage_unknown_stage_exits_2(root: Path, inputs: Path, monkeypatch, capsys):
    from sendesis.cli import main

    wf, diff = cli_setup(root, inputs, monkeypatch, {})
    assert main(["stage", str(wf), "nope", "--diff", str(diff), "--root", str(root)]) == 2
    assert "has no stage nope" in capsys.readouterr().out


def test_cli_stage_reads_nested_context(root: Path, inputs: Path, monkeypatch, capsys):
    from sendesis.cli import main

    plan = {"claude-opus": [ok()], "codex-gpt": [ok()]}
    wf, diff = cli_setup(root, inputs, monkeypatch, plan)
    ctx = inputs / "ctx"
    (ctx / "pkg" / "sub").mkdir(parents=True)
    (ctx / "pkg" / "sub" / "mod.py").write_text("y = 2\n")
    import sendesis.stage as st
    fn = scripted(plan)
    monkeypatch.setattr(st, "default_seat_fn", lambda r: fn)
    assert main(["stage", str(wf), "review", "--diff", str(diff), "--context", str(ctx), "--root", str(root)]) == 0
    message = fn.calls[0][2]
    assert "### pkg/sub/mod.py" in message and "y = 2" in message
    assert not any(p in message for p in PROFILES)
