import json
from pathlib import Path

import pytest
from agno_cli_models import CliTimeoutError, ModelRateLimitError

from fakes import ScriptedModel
from sendesis.model import load_profile, load_role, schema_validator
from sendesis.seat import (
    Outcome, SandboxUnavailable, build_model, fingerprint, make_agent, run_seat,
)

GOOD = {"role_id": "security-reviewer", "findings": [], "checks": [{"id": "injection", "outcome": "no_findings"}]}


def run(root: Path, *replies):
    schema = json.loads((root / "schemas" / "finding.json").read_text())
    agent = make_agent(ScriptedModel(replies=list(replies)), instructions="Review.", schema=schema)
    return run_seat(agent, "the diff", schema_validator(root, "finding.json"))


def test_ok_output_validates_and_reports_usage(root: Path):
    r = run(root, json.dumps(GOOD))
    assert r.outcome is Outcome.OK and r.output == GOOD
    assert r.observed_model == "scripted-1" and r.cli_version == "9.9.9" and r.config_fingerprint == "f" * 64
    assert r.input_tokens == 100 and r.output_tokens == 20


def test_fenced_json_and_nulls_are_accepted(root: Path):
    with_null = {**GOOD, "summary": None}
    r = run(root, "```json\n" + json.dumps(with_null) + "\n```")
    assert r.outcome is Outcome.OK and "summary" not in r.output


def test_invalid_output_is_typed(root: Path):
    r = run(root, json.dumps({"role_id": "x"}))
    assert r.outcome is Outcome.INVALID and "required property" in r.reason


def test_not_json_is_invalid(root: Path):
    assert run(root, "I found nothing.").outcome is Outcome.INVALID


def test_rate_limit_is_typed(root: Path):
    r = run(root, ModelRateLimitError("usage limit reached"))
    assert r.outcome is Outcome.RATE_LIMIT and "usage limit" in r.reason


def test_timeout_is_typed(root: Path):
    assert run(root, CliTimeoutError("no answer in 300s")).outcome is Outcome.TIMEOUT


def test_other_error_is_typed(root: Path):
    r = run(root, RuntimeError("process exited 1"))
    assert r.outcome is Outcome.ERROR and "process exited 1" in r.reason


def test_claude_reviewer_gets_read_grep_glob_only(root: Path, tmp_path: Path):
    role = load_role(root / "roles" / "security-reviewer.yaml", root)
    model = build_model(load_profile(root / "profiles" / "claude-opus.yaml", root), role, cwd=tmp_path, timeout_s=30)
    assert tuple(model.builtin_tools) == ("Read", "Grep", "Glob")
    assert model.id == "claude-opus-5-5" and model.effort == "high"


def test_codex_reviewer_is_read_only(root: Path, tmp_path: Path):
    role = load_role(root / "roles" / "security-reviewer.yaml", root)
    model = build_model(load_profile(root / "profiles" / "codex-gpt.yaml", root), role, cwd=tmp_path, timeout_s=30)
    assert model.sandbox == "read-only" and model.builtin_tools is True


def test_edit_or_shell_role_is_refused(root: Path, tmp_path: Path):
    from conftest import edit_yaml

    path = root / "roles" / "security-reviewer.yaml"
    edit_yaml(path, lambda d: d.update(kind="worker") or d["tools"].update(allowed=["read", "edit"]))
    role = load_role(path, root)
    with pytest.raises(SandboxUnavailable):
        build_model(load_profile(root / "profiles" / "claude-opus.yaml", root), role, cwd=tmp_path, timeout_s=30)


def test_fingerprint_changes_with_tools(root: Path, tmp_path: Path):
    from conftest import edit_yaml

    profile = load_profile(root / "profiles" / "claude-opus.yaml", root)
    role = load_role(root / "roles" / "security-reviewer.yaml", root)
    a = fingerprint(build_model(profile, role, cwd=tmp_path, timeout_s=30), profile)
    path = root / "roles" / "security-reviewer.yaml"
    edit_yaml(path, lambda d: d["tools"].update(allowed=["read"]))
    b = fingerprint(build_model(profile, load_role(path, root), cwd=tmp_path, timeout_s=30), profile)
    assert len(a) == 64 and a != b


def test_openai_like_fingerprint_is_stable(root: Path, tmp_path: Path):
    from conftest import edit_yaml

    path = root / "profiles" / "ollama-local.yaml"
    edit_yaml(path, lambda d: d["model"].update(id="qwen-test"))
    profile = load_profile(path, root)
    role = load_role(root / "roles" / "security-reviewer.yaml", root)
    a = fingerprint(build_model(profile, role, cwd=tmp_path, timeout_s=30), profile)
    assert a == fingerprint(build_model(profile, role, cwd=tmp_path, timeout_s=30), profile)
