import json
from pathlib import Path

import pytest
from agno_cli_models import CliStallError, CliTimeoutError, ModelRateLimitError

from conftest import edit_yaml
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
    assert r.outcome is Outcome.INVALID and "'findings' is a required property" in r.reason


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


def test_prose_with_two_objects_is_invalid(root: Path):
    r = run(root, 'Here: {"a":"x"} and also {"b":1}')
    assert r.outcome is Outcome.INVALID and r.output is None


def test_ok_text_is_raw_reply(root: Path):
    r = run(root, json.dumps(GOOD))
    assert json.loads(r.text) == GOOD


def _agent_for(model, root: Path):
    schema = json.loads((root / "schemas" / "finding.json").read_text())
    return make_agent(model, instructions="x", schema=schema)


def test_cli_model_gets_bare_schema(root: Path):
    a = _agent_for(ScriptedModel(), root)
    assert "$schema" not in a.output_schema and "properties" in a.output_schema


def test_openai_like_gets_wrapped_schema(root: Path, tmp_path: Path):
    profile = load_profile(root / "profiles" / "ollama-local.yaml", root)
    role = load_role(root / "roles" / "security-reviewer.yaml", root)
    a = _agent_for(build_model(profile, role, cwd=tmp_path, timeout_s=30), root)
    assert a.output_schema["type"] == "json_schema"
    assert "properties" in a.output_schema["json_schema"]["schema"]
    assert a.model.max_retries == 0


def test_openai_timeout_is_classified():
    import httpx
    from agno.exceptions import ModelProviderError
    from openai import APITimeoutError

    from sendesis.seat import _is_timeout

    err = ModelProviderError("boom")
    err.__cause__ = APITimeoutError(request=httpx.Request("POST", "http://x"))
    assert _is_timeout(err) and not _is_timeout(RuntimeError("x"))


def test_max_turns_is_the_smaller_of_role_and_profile(root: Path, tmp_path: Path):
    from conftest import edit_yaml

    rpath = root / "roles" / "security-reviewer.yaml"
    ppath = root / "profiles" / "claude-opus.yaml"
    for role_turns, profile_turns, want in [(5, 20, 5), (30, 20, 20), (None, 20, 20), (7, None, 7)]:
        edit_yaml(rpath, lambda d: d["budgets"].update(max_turns=role_turns) if role_turns else d["budgets"].pop("max_turns", None))
        edit_yaml(ppath, lambda d: d.update(max_turns=profile_turns) if profile_turns else d.pop("max_turns", None))
        model = build_model(load_profile(ppath, root), load_role(rpath, root), cwd=tmp_path, timeout_s=30)
        assert model.max_turns == want


def test_profile_idle_limit_reaches_cli_models_and_their_fingerprint(root: Path, tmp_path: Path):
    role = load_role(root / "roles" / "security-reviewer.yaml", root)
    for name in ("claude-opus", "codex-gpt"):
        path = root / "profiles" / f"{name}.yaml"
        default = build_model(load_profile(path, root), role, cwd=tmp_path, timeout_s=300)
        edit_yaml(path, lambda d: d.update(idle_timeout_s=45))
        model = build_model(load_profile(path, root), role, cwd=tmp_path, timeout_s=300)
        assert model.idle_timeout_s == 45 and model.timeout_s == 300
        assert model.config_fingerprint() != default.config_fingerprint()


def test_no_profile_idle_limit_keeps_the_class_default(root: Path, tmp_path: Path):
    role = load_role(root / "roles" / "security-reviewer.yaml", root)
    model = build_model(load_profile(root / "profiles" / "codex-gpt.yaml", root), role, cwd=tmp_path, timeout_s=300)
    assert model.idle_timeout_s == 60.0


def stall_error():
    return CliStallError("codex sent nothing for 60.0s (last: item/started)", idle_s=60.0,
                         last_method="item/started", answer_open=True)


def test_stall_is_typed_with_its_details(root: Path):
    r = run(root, stall_error())
    assert r.outcome is Outcome.STALL
    assert r.stall == {"idle_s": 60.0, "last_method": "item/started", "answer_open": True}
    assert "CliStallError" in r.reason


def test_plain_timeout_is_still_a_timeout(root: Path):
    r = run(root, CliTimeoutError("no answer in 300s"))
    assert r.outcome is Outcome.TIMEOUT and r.stall is None


def test_stall_inside_another_error_is_still_a_stall(root: Path):
    try:
        try:
            raise stall_error()
        except CliStallError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        wrapped = outer
    r = run(root, wrapped)
    assert r.outcome is Outcome.STALL and r.stall["last_method"] == "item/started"


def test_stall_reached_only_through_context_is_still_a_stall(root: Path):
    try:
        try:
            raise stall_error()
        except CliStallError:
            raise RuntimeError()  # no "from": the stall is only on __context__
    except RuntimeError as outer:
        implicit = outer
    assert implicit.__cause__ is None and isinstance(implicit.__context__, CliStallError)
    stall = implicit.__context__

    # Agno raises the scripted error while another exception is being handled, and Python would then
    # overwrite __context__. Pin it so the error reaches run_seat exactly as built above.
    class Pinned(RuntimeError):
        __context__ = property(lambda self: stall, lambda self, value: None)

    r = run(root, Pinned())
    assert r.outcome is Outcome.STALL and r.stall["last_method"] == "item/started"
