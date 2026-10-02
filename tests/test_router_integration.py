"""M3.2 exit: cut one provider mid-stage (docs/specs/2026-10-02-sendesis-m3.2-router-design.md, section 4).

Claude is cut by pointing ClaudeCodeModel at a shim that answers --version and then
stays silent, so agno-cli-models raises a real CliStallError. Spends quota: one Codex
call per stage test. Uses the local Qwen model through Ollama (free).
"""

import functools
import shutil
from pathlib import Path

import pytest
import yaml
from agno_cli_models import ClaudeCodeModel

import sendesis.seat as seat
from sendesis.model import load_profile, load_role
from sendesis.qualify import review_message
from sendesis.seat import Outcome, run_role
from sendesis.stage import run_stage
from sendesis.suite import load_suite
from stage_helpers import git_init

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parent.parent
QWEN = "hf.co/OBLITERATUS/Qwen3.8-27B-OBLITERATED:Q4_K_M"
SHIM = '#!/bin/sh\nif [ "$1" = "--version" ]; then echo "2.1.287 (Claude Code)"; exit 0; fi\nexec sleep 600\n'


def _edit(path: Path, change) -> None:
    data = yaml.safe_load(path.read_text())
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _repo(tmp_path: Path, *, ollama_enabled: bool) -> Path:
    root = tmp_path / "repo"
    for folder in ("schemas", "roles", "profiles"):
        shutil.copytree(REPO / folder, root / folder)
    role = yaml.safe_load((root / "roles" / "security-reviewer.yaml").read_text())
    role.update(id="security-reviewer-provisional", failover_order=["claude-opus", "codex-gpt", "ollama-local"])
    role.pop("qualification")
    (root / "roles" / "security-reviewer-provisional.yaml").write_text(yaml.safe_dump(role, sort_keys=False))
    _edit(root / "profiles" / "claude-opus.yaml", lambda d: d.update(idle_timeout_s=15))

    def local(d):
        d.update(enabled=ollama_enabled, family="qwen")
        d["model"].update(id=QWEN)

    _edit(root / "profiles" / "ollama-local.yaml", local)
    (root / "workflows").mkdir()
    (root / "workflows" / "review-failover.yaml").write_text(yaml.safe_dump({
        "id": "review-failover", "version": "0.1.0", "description": "M3.2 exit: one blind review stage.",
        "stages": [{"id": "review", "seats": [
            {"role": "security-reviewer-provisional", "count": 2, "distinct_families": 2, "blind": True}]}],
    }, sort_keys=False))
    git_init(root)
    return root


@pytest.fixture
def cut_claude(tmp_path: Path, monkeypatch):
    shim = tmp_path / "claude-shim"
    shim.write_text(SHIM)
    shim.chmod(0o755)
    monkeypatch.setattr(seat, "ClaudeCodeModel", functools.partial(ClaudeCodeModel, cli_path=str(shim)))
    return shim


def _case():
    return next(c for c in load_suite(REPO / "suites" / "security-reviewer-smoke").cases if not c.clean)


def test_silent_claude_cli_is_a_stall(tmp_path: Path, cut_claude):
    """Substrate check (no quota): the shim makes the SDK wait, so the idle limit fires."""
    root = _repo(tmp_path, ollama_enabled=False)
    role = load_role(root / "roles" / "security-reviewer-provisional.yaml", root)
    profile = load_profile(root / "profiles" / "claude-opus.yaml", root)
    case = _case()
    r = run_role(role, profile, review_message(role.id, case.diff, case.context), root=root, cwd=root, timeout_s=120)
    assert r.outcome is Outcome.STALL, r.reason
    assert r.stall["idle_s"] == 15


def test_cut_provider_fails_over_and_completes(tmp_path: Path, cut_claude):
    root = _repo(tmp_path, ollama_enabled=True)
    case = _case()
    r = run_stage(root, root / "workflows" / "review-failover.yaml", "review", diff=case.diff, context=case.context)
    print(r.record_path.read_text())
    assert r.status == "completed", r.refusal or r.stop_reason
    assert r.initial_assignment == {"A": "claude-opus", "B": "codex-gpt"}
    assert [(a.label, a.profile, a.outcome) for a in r.attempts] == [
        ("A", "claude-opus", "stall"), ("A", "codex-gpt", "ok"), ("B", "claude-opus", "stall"), ("B", "ollama-local", "ok")]
    assert any("provisional" in w for w in r.warnings)


def test_cut_provider_without_a_second_family_refuses(tmp_path: Path, cut_claude):
    root = _repo(tmp_path, ollama_enabled=False)
    case = _case()
    r = run_stage(root, root / "workflows" / "review-failover.yaml", "review", diff=case.diff, context=case.context)
    print(r.record_path.read_text())
    assert r.status == "refused"
    lines = r.refusal.splitlines()
    assert lines[0] == "refused: stage review: security-reviewer-provisional needs 2 families, 1 acceptable (openai: codex-gpt)"
    assert "  rejected: claude-opus: failed this seat (stall)" in lines
    assert "  rejected: ollama-local: disabled" in lines
    assert [(a.label, a.profile, a.outcome) for a in r.attempts] == [
        ("A", "claude-opus", "stall"), ("A", "codex-gpt", "ok"), ("B", "claude-opus", "stall")]
