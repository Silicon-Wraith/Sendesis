from pathlib import Path

from conftest import REPO, edit_yaml
from sendesis.cli import main
from sendesis.validate import validate_repo

ROLE = Path("roles") / "security-reviewer.yaml"


def test_repo_files_pass():
    report = validate_repo(REPO)
    assert report.errors == []


def test_valid_copy_passes(root: Path):
    assert validate_repo(root).errors == []


def test_unknown_profile_in_failover_order_fails(root: Path):
    edit_yaml(root / ROLE, lambda d: d["failover_order"].append("no-such-profile"))
    errors = validate_repo(root).errors
    assert any("unknown profile 'no-such-profile'" in e for e in errors)


def test_missing_prompt_file_fails(root: Path):
    (root / "roles" / "security-reviewer.prompt.md").unlink()
    errors = validate_repo(root).errors
    assert any("prompt_file" in e and "missing" in e for e in errors)


def test_role_without_prompt_file_fails(root: Path):
    edit_yaml(root / ROLE, lambda d: d.pop("prompt_file"))
    errors = validate_repo(root).errors
    assert any("prompt_file" in e for e in errors)


def test_missing_output_schema_file_fails(root: Path):
    edit_yaml(root / ROLE, lambda d: d.update(output_schema="schemas/nope.json"))
    errors = validate_repo(root).errors
    assert any("output_schema" in e and "missing" in e for e in errors)


def test_invalid_schema_fails(root: Path):
    (root / "schemas" / "finding.json").write_text('{"type": 12}', encoding="utf-8")
    errors = validate_repo(root).errors
    assert any("schemas/finding.json" in e for e in errors)


def test_id_must_match_file_name(root: Path):
    edit_yaml(root / "profiles" / "claude-opus.yaml", lambda d: d.update(id="claude-other"))
    errors = validate_repo(root).errors
    assert any("claude-opus.yaml" in e and "file name" in e for e in errors)


def test_disabled_profile_with_placeholder_family_warns(root: Path):
    report = validate_repo(root)
    assert report.errors == []
    assert any("vllm-local.yaml" in w and "family" in w for w in report.warnings)


def test_single_family_failover_warns_while_disabled_profiles_remain(root: Path):
    for name in ("codex-gpt", "ollama-local"):
        edit_yaml(root / "profiles" / f"{name}.yaml", lambda d: d.update(enabled=False))
    report = validate_repo(root)
    assert report.errors == []
    assert any("failover_order" in w and "famil" in w for w in report.warnings)


def test_single_family_failover_fails_when_nothing_disabled_could_fix_it(root: Path):
    def only_claude(d):
        d["failover_order"] = ["claude-opus"]

    edit_yaml(root / ROLE, only_claude)
    errors = validate_repo(root).errors
    assert any("failover_order" in e and "famil" in e for e in errors)


def test_cli_exit_codes_and_output(root: Path, capsys):
    assert main(["validate", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out
    assert "prompt sha256" in out

    edit_yaml(root / ROLE, lambda d: d.pop("purpose"))
    assert main(["validate", "--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "'purpose' is a required property" in out


def test_cli_class_family_mismatch_fails(root: Path):
    edit_yaml(root / "profiles" / "codex-gpt.yaml", lambda d: d.update(family="anthropic"))
    errors = validate_repo(root).errors
    assert any("codex-gpt.yaml" in e and "family" in e and "openai" in e for e in errors)


def test_enabled_profile_with_placeholder_fails(root: Path):
    def enable(d):
        d["enabled"] = True
        d["model"]["id"] = "qwen3-coder"
    edit_yaml(root / "profiles" / "vllm-local.yaml", enable)
    errors = validate_repo(root).errors
    assert any("vllm-local.yaml" in e and "family" in e for e in errors)


def test_cli_class_needs_a_version_pin(root: Path):
    edit_yaml(root / "profiles" / "claude-opus.yaml", lambda d: d["model"].pop("cli_version"))
    errors = validate_repo(root).errors
    assert any("claude-opus.yaml" in e and "cli_version" in e for e in errors)


def test_openai_like_needs_base_url(root: Path):
    edit_yaml(root / "profiles" / "vllm-local.yaml", lambda d: d["model"].pop("base_url"))
    errors = validate_repo(root).errors
    assert any("vllm-local.yaml" in e and "base_url" in e for e in errors)


def test_broken_profile_is_not_also_reported_as_unknown(root: Path):
    edit_yaml(root / "profiles" / "codex-gpt.yaml", lambda d: d.pop("model"))
    errors = validate_repo(root).errors
    assert any("codex-gpt.yaml" in e and "model" in e for e in errors)
    assert not any("unknown profile 'codex-gpt'" in e for e in errors)


def test_reviewer_with_shell_fails(root: Path):
    edit_yaml(root / ROLE, lambda d: d["tools"].update(allowed=["read", "search", "shell"]))
    errors = validate_repo(root).errors
    assert any("security-reviewer.yaml" in e and "shell" in e and "reviewer" in e for e in errors)


def test_provisional_role_warns(root: Path):
    edit_yaml(root / ROLE, lambda d: d.pop("qualification"))
    report = validate_repo(root)
    assert report.errors == []
    assert any("security-reviewer.yaml" in w and "provisional" in w for w in report.warnings)


def test_missing_suite_folder_fails(root: Path):
    edit_yaml(root / ROLE, lambda d: d["qualification"].update(suite="suites/nope"))
    errors = validate_repo(root).errors
    assert any("suites/nope" in e for e in errors)


def test_idle_limit_on_a_non_cli_profile_warns(root: Path):
    edit_yaml(root / "profiles" / "ollama-local.yaml", lambda d: d.update(idle_timeout_s=30))
    report = validate_repo(root)
    assert report.errors == []
    assert any("ollama-local.yaml" in w and "idle_timeout_s" in w for w in report.warnings)


def test_idle_limit_not_below_the_wall_clock_warns(root: Path):
    edit_yaml(root / "profiles" / "codex-gpt.yaml", lambda d: d.update(idle_timeout_s=300))
    report = validate_repo(root)
    assert report.errors == []
    assert any("codex-gpt.yaml" in w and "idle_timeout_s" in w and "timeout_s" in w for w in report.warnings)
