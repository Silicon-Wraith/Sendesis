import hashlib
from pathlib import Path

import pytest

from conftest import edit_yaml
from sendesis.model import ValidationFailed, canonical_sha256, load_profile, load_role


def test_role_loads_as_dataclass(root: Path):
    role = load_role(root / "roles" / "security-reviewer.yaml", root)
    assert role.id == "security-reviewer"
    assert role.version == "0.1.0"
    assert role.failover_order[0] == "claude-opus"
    assert len(role.sha256) == 64


def test_role_input_required_defaults_to_true(root: Path):
    role = load_role(root / "roles" / "security-reviewer.yaml", root)
    by_name = {i.name: i for i in role.inputs}
    assert by_name["diff"].required is True
    assert by_name["context_files"].required is False


def test_role_prompt_is_hashed_from_raw_bytes(root: Path):
    role = load_role(root / "roles" / "security-reviewer.yaml", root)
    raw = (root / "roles" / "security-reviewer.prompt.md").read_bytes()
    assert role.prompt_sha256 == hashlib.sha256(raw).hexdigest()


def test_profile_loads_as_dataclass(root: Path):
    profile = load_profile(root / "profiles" / "codex-gpt.yaml", root)
    assert profile.id == "codex-gpt"
    assert profile.runner == "codex_cli"
    assert profile.family == "openai"
    assert profile.sandbox == "read-only"
    assert profile.enabled is True


def test_missing_required_field_fails_with_readable_message(root: Path):
    path = root / "roles" / "security-reviewer.yaml"
    edit_yaml(path, lambda d: d.pop("purpose"))
    with pytest.raises(ValidationFailed) as exc:
        load_role(path, root)
    messages = exc.value.messages
    assert any("roles/security-reviewer.yaml" in m and "'purpose' is a required property" in m for m in messages)


def test_codex_profile_without_sandbox_fails(root: Path):
    path = root / "profiles" / "codex-gpt.yaml"
    edit_yaml(path, lambda d: d.pop("sandbox"))
    with pytest.raises(ValidationFailed) as exc:
        load_profile(path, root)
    assert any("'sandbox' is a required property" in m for m in exc.value.messages)


def test_codex_profile_cannot_use_danger_full_access(root: Path):
    path = root / "profiles" / "codex-gpt.yaml"
    edit_yaml(path, lambda d: d.update(sandbox="danger-full-access"))
    with pytest.raises(ValidationFailed) as exc:
        load_profile(path, root)
    assert any("sandbox" in m for m in exc.value.messages)


def test_yaml_syntax_error_fails_readably(root: Path):
    path = root / "profiles" / "claude-opus.yaml"
    path.write_text("id: [unclosed\n", encoding="utf-8")
    with pytest.raises(ValidationFailed) as exc:
        load_profile(path, root)
    assert any("profiles/claude-opus.yaml" in m and "YAML" in m for m in exc.value.messages)


def test_hash_stable_across_key_order_and_whitespace():
    a = "id: x\nenabled: true\nnested:\n  b: 2\n  a: 1\n"
    b = "\n\nnested: {a: 1,   b: 2}\n# a comment\nenabled:    true\nid: 'x'\n"
    assert canonical_sha256(a) == canonical_sha256(b)


def test_hash_changes_when_a_value_changes():
    assert canonical_sha256("id: x\ntimeout_s: 300\n") != canonical_sha256("id: x\ntimeout_s: 301\n")


def test_profile_hash_matches_canonical_hash_of_file(root: Path):
    path = root / "profiles" / "claude-opus.yaml"
    profile = load_profile(path, root)
    assert profile.sha256 == canonical_sha256(path.read_text(encoding="utf-8"))


def test_profile_endpoint_must_be_a_uri(root: Path):
    path = root / "profiles" / "vllm-local.yaml"
    edit_yaml(path, lambda d: d.update(endpoint="127.0.0.1 port 8000"))
    with pytest.raises(ValidationFailed) as exc:
        load_profile(path, root)
    assert any("endpoint" in m and "uri" in m for m in exc.value.messages)


def test_claude_profile_without_reasoning_effort_fails(root: Path):
    path = root / "profiles" / "claude-opus.yaml"
    edit_yaml(path, lambda d: d.pop("reasoning_effort"))
    with pytest.raises(ValidationFailed) as exc:
        load_profile(path, root)
    assert any("'reasoning_effort' is a required property" in m for m in exc.value.messages)


def test_role_without_prompt_file_fails_schema(root: Path):
    path = root / "roles" / "security-reviewer.yaml"
    edit_yaml(path, lambda d: d.pop("prompt_file"))
    with pytest.raises(ValidationFailed) as exc:
        load_role(path, root)
    assert any("'prompt_file' is a required property" in m for m in exc.value.messages)


def test_role_budget_timeout_is_loaded(root: Path):
    role = load_role(root / "roles" / "security-reviewer.yaml", root)
    assert role.per_call_timeout_s == 300
