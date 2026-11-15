from pathlib import Path

import pytest

from conftest import edit_yaml
from sendesis.failover import RunState, StageStopped, run_slot
from sendesis.model import load_role
from sendesis.router import Refusal, slots
from sendesis.seat import Outcome
from sendesis.workflow import load_workflow
from stage_helpers import add_role, git_init, ok, result, scripted, write_workflow

ORDER = ["claude-opus", "codex-gpt", "ollama-local"]
NO_STATUS = lambda role, profile: ("NONE", [])


def setup(root: Path, *, count=1, need=1, kind="reviewer", tools=("read", "search")):
    add_role(root, "p", order=ORDER, kind=kind, tools=tools)
    stage = load_workflow(write_workflow(root, "wf", [{"role": "p", "count": count, "distinct_families": need}]), root).stages[0]
    git_init(root)
    return stage, {"p": load_role(root / "roles" / "p.yaml", root)}


def run_all(root, stage, roles, seat_fn, state=None, **kw):
    state = state or RunState()
    out = {}
    for slot in slots(stage):
        r = run_slot(slot, stage, roles, state, root=root, cwd=root, messages={"p": "review this"},
                     status_fn=NO_STATUS, seat_fn=seat_fn, **kw)
        if isinstance(r, Refusal):
            return state, r
        out[slot.label] = r
    return state, out


def trail(state):
    return [(a.label, a.profile, a.outcome) for a in state.attempts]


def test_invalid_is_retried_once_then_fails_over(root: Path):
    stage, roles = setup(root)
    fn = scripted({"claude-opus": [result(Outcome.INVALID), result(Outcome.INVALID)], "codex-gpt": [ok()]})
    state, out = run_all(root, stage, roles, fn)
    assert trail(state) == [("A", "claude-opus", "invalid"), ("A", "claude-opus", "invalid"), ("A", "codex-gpt", "ok")]
    assert state.fixed == {"A": "codex-gpt"}


def test_rate_limit_excludes_profile_from_later_seats(root: Path):
    stage, roles = setup(root, count=2)
    fn = scripted({"claude-opus": [result(Outcome.RATE_LIMIT)], "codex-gpt": [ok(), ok()]})
    state, out = run_all(root, stage, roles, fn)
    assert trail(state) == [("A", "claude-opus", "rate_limit"), ("A", "codex-gpt", "ok"), ("B", "codex-gpt", "ok")]
    assert state.run_excluded == {"claude-opus": "rate-limited earlier in this run"}


def test_stall_excludes_profile_for_that_seat_only(root: Path):
    stage, roles = setup(root, count=2)
    fn = scripted({"claude-opus": [result(Outcome.STALL), ok()], "codex-gpt": [ok()]})
    state, out = run_all(root, stage, roles, fn)
    assert trail(state) == [("A", "claude-opus", "stall"), ("A", "codex-gpt", "ok"), ("B", "claude-opus", "ok")]


def test_family_rule_is_rechecked_after_failover(root: Path):
    stage, roles = setup(root, count=2, need=2)
    fn = scripted({"claude-opus": [ok()], "codex-gpt": [result(Outcome.TIMEOUT)], "ollama-local": [ok()]})
    state, out = run_all(root, stage, roles, fn)
    assert state.fixed == {"A": "claude-opus", "B": "ollama-local"}


def test_finished_seat_keeps_profile_after_later_rate_limit(root: Path):
    stage, roles = setup(root, count=2, need=2)
    fn = scripted({"claude-opus": [ok()], "codex-gpt": [result(Outcome.RATE_LIMIT)], "ollama-local": [ok()]})
    state, out = run_all(root, stage, roles, fn)
    assert state.fixed == {"A": "claude-opus", "B": "ollama-local"}
    assert out["A"].outcome is Outcome.OK


def test_running_out_of_profiles_refuses(root: Path):
    stage, roles = setup(root)
    fn = scripted({p: [result(Outcome.ERROR)] for p in ORDER})
    state, refusal = run_all(root, stage, roles, fn)
    assert isinstance(refusal, Refusal)
    assert refusal.text.splitlines()[0] == "refused: stage review: p needs 1 family, 0 acceptable for seat A"
    assert "  rejected: ollama-local: failed this seat (error)" in refusal.text.splitlines()


def test_untyped_exception_stops_and_is_not_failed_over(root: Path):
    stage, roles = setup(root)

    def boom(cwd):
        raise RuntimeError("bug in sendesis")

    fn = scripted({"claude-opus": [boom], "codex-gpt": [ok()]})
    with pytest.raises(StageStopped, match="untyped exception RuntimeError: bug in sendesis"):
        run_all(root, stage, roles, fn)
    assert [c[1] for c in fn.calls] == ["claude-opus"]


def test_reviewer_that_changes_the_tree_stops_the_stage(root: Path):
    stage, roles = setup(root)

    def writes(cwd):
        (Path(cwd) / "oops.txt").write_text("a reviewer wrote this")
        return ok()

    fn = scripted({"claude-opus": [writes], "codex-gpt": [ok()]})
    with pytest.raises(StageStopped, match="changed the tree"):
        run_all(root, stage, roles, fn)
    assert [c[1] for c in fn.calls] == ["claude-opus"]


def test_worker_seat_is_reset_before_the_rerun(root: Path):
    (root / "code.py").write_text("x = 1\n")
    stage, roles = setup(root, kind="worker", tools=("read", "edit"))
    seen = {}

    def breaks(cwd):
        (Path(cwd) / "code.py").write_text("x = 2\n")
        (Path(cwd) / "made.py").write_text("y = 1\n")
        return result(Outcome.ERROR)

    def checks(cwd):
        seen["code"] = (Path(cwd) / "code.py").read_text()
        seen["made"] = (Path(cwd) / "made.py").exists()
        return ok()

    fn = scripted({"claude-opus": [breaks], "codex-gpt": [checks]})
    state, out = run_all(root, stage, roles, fn, sandbox=lambda role: None)
    assert seen == {"code": "x = 1\n", "made": False}
    assert state.fixed == {"A": "codex-gpt"}


def test_every_attempt_gets_the_same_message(root: Path):
    stage, roles = setup(root)
    fn = scripted({"claude-opus": [result(Outcome.STALL)], "codex-gpt": [ok()]})
    run_all(root, stage, roles, fn)
    assert [c[2] for c in fn.calls] == ["review this", "review this"]


def test_refusal_after_a_finished_seat_names_the_stuck_seat(root: Path):
    stage, roles = setup(root, count=2)
    fn = scripted({"claude-opus": [ok(), result(Outcome.ERROR)], "codex-gpt": [result(Outcome.ERROR)],
                   "ollama-local": [result(Outcome.ERROR)]})
    state, refusal = run_all(root, stage, roles, fn)
    assert isinstance(refusal, Refusal)
    assert refusal.text.splitlines() == [
        "refused: stage review: p needs 1 family, 0 acceptable for seat B",
        "  kept: A claude-opus (anthropic)",
        "  rejected: claude-opus: failed this seat (error)",
        "  rejected: codex-gpt: failed this seat (error)",
        "  rejected: ollama-local: failed this seat (error)",
    ]


def test_invalid_then_ok_on_retry_keeps_the_profile(root: Path):
    stage, roles = setup(root)
    fn = scripted({"claude-opus": [result(Outcome.INVALID), ok()]})
    state, out = run_all(root, stage, roles, fn)
    assert trail(state) == [("A", "claude-opus", "invalid"), ("A", "claude-opus", "ok")]
    assert state.fixed == {"A": "claude-opus"}


def test_invalid_then_rate_limit_excludes_for_the_run(root: Path):
    stage, roles = setup(root)
    fn = scripted({"claude-opus": [result(Outcome.INVALID), result(Outcome.RATE_LIMIT)], "codex-gpt": [ok()]})
    state, out = run_all(root, stage, roles, fn)
    assert trail(state) == [("A", "claude-opus", "invalid"), ("A", "claude-opus", "rate_limit"), ("A", "codex-gpt", "ok")]
    assert state.run_excluded == {"claude-opus": "rate-limited earlier in this run"}
