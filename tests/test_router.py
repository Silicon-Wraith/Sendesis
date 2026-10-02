from datetime import datetime, timezone
from pathlib import Path
import shutil

from conftest import REPO, edit_yaml
from sendesis.model import load_role
from sendesis.receipts import profile_status
from sendesis.router import (
    ACCEPTABLE, PROVISIONAL, REJECTED, Candidate, Refusal, assign, candidates, route, slots,
)
from sendesis.workflow import load_workflow
from stage_helpers import add_role, write_workflow

NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)
ORDER = ["claude-opus", "codex-gpt", "ollama-local"]


def statuses(table):
    return lambda role, profile: table.get(profile.id, ("NONE", []))


def stage_of(root, seats):
    return load_workflow(write_workflow(root, "wf", seats), root).stages[0]


def test_candidate_verdicts_for_a_role_with_a_suite(root: Path):
    add_role(root, "r", order=ORDER + ["vllm-local", "ghost"], suite=True)
    role = load_role(root / "roles" / "r.yaml", root)
    table = {"claude-opus": ("QUALIFIED", []), "codex-gpt": ("UNKNOWN", ["suite has 30 cases, role requires at least 100"])}
    got = {c.profile_id: c for c in candidates(role, root, statuses(table))}
    assert got["claude-opus"].verdict == ACCEPTABLE and got["claude-opus"].family == "anthropic"
    assert got["codex-gpt"].verdict == REJECTED
    assert got["codex-gpt"].reason == "receipt UNKNOWN: suite has 30 cases, role requires at least 100"
    assert got["ollama-local"].reason == "no receipt"
    assert got["vllm-local"].reason == "disabled"
    assert got["ghost"].verdict == REJECTED and got["ghost"].reason.startswith("profile file missing or invalid")


def test_provisional_role_accepts_enabled_profiles(root: Path):
    add_role(root, "p", order=ORDER)
    role = load_role(root / "roles" / "p.yaml", root)
    got = candidates(role, root, statuses({}))
    assert [c.verdict for c in got] == [PROVISIONAL, PROVISIONAL, PROVISIONAL]


def test_provisional_role_rejects_placeholder_family(root: Path):
    edit_yaml(root / "profiles" / "vllm-local.yaml", lambda d: d.update(enabled=True))
    add_role(root, "p", order=["vllm-local"])
    [c] = candidates(load_role(root / "roles" / "p.yaml", root), root, statuses({}))
    assert c.verdict == REJECTED and "placeholder" in c.reason


def test_placeholder_family_is_rejected_for_a_role_with_a_suite(root: Path):
    edit_yaml(root / "profiles" / "vllm-local.yaml", lambda d: d.update(enabled=True))
    add_role(root, "r", order=["vllm-local"], suite=True)
    role = load_role(root / "roles" / "r.yaml", root)
    [c] = candidates(role, root, lambda role, profile: ("QUALIFIED", []))
    assert c.verdict == REJECTED and "placeholder" in c.reason


def test_excluded_profile_is_rejected_with_its_reason(root: Path):
    add_role(root, "p", order=ORDER)
    role = load_role(root / "roles" / "p.yaml", root)
    got = candidates(role, root, statuses({}), excluded={"codex-gpt": "rate-limited earlier in this run"})
    assert got[1].verdict == REJECTED and got[1].reason == "rate-limited earlier in this run"


def test_edit_or_shell_role_is_rejected_for_sandbox(root: Path):
    add_role(root, "w", order=ORDER, kind="worker", tools=("read", "edit"))
    got = candidates(load_role(root / "roles" / "w.yaml", root), root, statuses({}))
    assert all(c.verdict == REJECTED and c.reason.startswith("sandbox unavailable") for c in got)


def test_slots_are_labelled_in_seat_order(root: Path):
    add_role(root, "p", order=ORDER)
    add_role(root, "q", order=ORDER)
    stage = stage_of(root, [{"role": "p", "count": 2}, {"role": "q"}])
    assert [(s.label, s.role_id, s.seat_index) for s in slots(stage)] == [("A", "p", 0), ("B", "p", 0), ("C", "q", 1)]


def test_first_fit_and_one_profile_fills_several_seats_when_n_is_1(root: Path):
    add_role(root, "p", order=ORDER)
    stage = stage_of(root, [{"role": "p", "count": 2, "distinct_families": 1}])
    a = route(stage, {"p": load_role(root / "roles" / "p.yaml", root)}, root, statuses({}),
              fixed={}, run_excluded={}, slot_excluded={})
    assert a.profiles == {"A": "claude-opus", "B": "claude-opus"}
    assert a.warnings == ("p is provisional: no suite, profile claude-opus not qualified",)


def test_two_families_take_the_next_family(root: Path):
    add_role(root, "p", order=ORDER)
    stage = stage_of(root, [{"role": "p", "count": 2, "distinct_families": 2}])
    a = route(stage, {"p": load_role(root / "roles" / "p.yaml", root)}, root, statuses({}),
              fixed={}, run_excluded={}, slot_excluded={})
    assert a.profiles == {"A": "claude-opus", "B": "codex-gpt"} and a.families == {"A": "anthropic", "B": "openai"}


def test_backtracking_changes_an_earlier_seat(root: Path):
    add_role(root, "p", order=ORDER)
    stage = stage_of(root, [{"role": "p", "count": 2, "distinct_families": 2}])
    sl = slots(stage)
    cands = {
        "A": [Candidate("claude-opus", PROVISIONAL, "anthropic"), Candidate("codex-gpt", PROVISIONAL, "openai")],
        "B": [Candidate("claude-opus", PROVISIONAL, "anthropic")],
    }
    a = assign(stage, sl, cands, fixed={})
    assert a.profiles == {"A": "codex-gpt", "B": "claude-opus"}


def test_one_profile_serves_two_roles(root: Path):
    add_role(root, "p", order=ORDER)
    add_role(root, "q", order=ORDER)
    stage = stage_of(root, [{"role": "p"}, {"role": "q"}])
    roles = {r: load_role(root / "roles" / f"{r}.yaml", root) for r in ("p", "q")}
    a = route(stage, roles, root, statuses({}), fixed={}, run_excluded={}, slot_excluded={})
    assert a.profiles == {"A": "claude-opus", "B": "claude-opus"}


def test_refusal_text_names_role_families_and_rejections(root: Path):
    edit_yaml(root / "profiles" / "ollama-local.yaml", lambda d: d.update(enabled=False))
    add_role(root, "p", order=ORDER)
    stage = stage_of(root, [{"role": "p", "count": 2, "distinct_families": 2}])
    r = route(stage, {"p": load_role(root / "roles" / "p.yaml", root)}, root, statuses({}),
              fixed={"A": "codex-gpt"}, run_excluded={}, slot_excluded={"B": {"claude-opus": "failed this seat (stall)"}})
    assert isinstance(r, Refusal)
    assert r.text.splitlines() == [
        "refused: stage review: p needs 2 families, 1 acceptable (openai: codex-gpt)",
        "  kept: A codex-gpt (openai)",
        "  rejected: claude-opus: failed this seat (stall)",
        "  rejected: ollama-local: disabled",
    ]


def test_real_security_reviewer_stage_refuses_today(root: Path):
    shutil.copytree(REPO / "receipts", root / "receipts")
    stage = stage_of(root, [{"role": "security-reviewer"}])
    role = load_role(root / "roles" / "security-reviewer.yaml", root)
    versions = {"claude": "2.1.287", "codex": "0.155.1"}
    status_fn = lambda rl, pr: profile_status(root, rl, pr, NOW, version_fn=versions.get)
    r = route(stage, {"security-reviewer": role}, root, status_fn, fixed={}, run_excluded={}, slot_excluded={})
    assert isinstance(r, Refusal)
    assert r.text.startswith("refused: stage review: security-reviewer needs 1 family, 0 acceptable for seat A")
    assert "  rejected: claude-opus: receipt UNKNOWN: suite has 30 cases, role requires at least 100" in r.text.splitlines()
    assert "  rejected: codex-gpt: receipt UNKNOWN: suite has 30 cases, role requires at least 100" in r.text.splitlines()
