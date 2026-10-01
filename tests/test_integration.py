"""Integration tier: one real call per CLI through the seat path. Spends quota; run with -m integration."""

import shutil
from pathlib import Path

import pytest

from sendesis.model import load_profile, load_role
from sendesis.qualify import build_message, prepare_workdir
from sendesis.seat import Outcome, run_role
from sendesis.suite import load_suite

pytestmark = pytest.mark.integration
REPO = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("profile_id, binary", [("claude-opus", "claude"), ("codex-gpt", "codex")])
def test_one_smoke_case_on_the_seat_path(profile_id, binary, tmp_path):
    if shutil.which(binary) is None:
        pytest.skip(f"{binary} is not installed")
    role = load_role(REPO / "roles" / "security-reviewer.yaml", REPO)
    profile = load_profile(REPO / "profiles" / f"{profile_id}.yaml", REPO)
    case = load_suite(REPO / "suites" / "security-reviewer-smoke").cases[0]
    result = run_role(role, profile, build_message(role, case), root=REPO, cwd=prepare_workdir(tmp_path / "wd", case), timeout_s=profile.timeout_s)
    assert result.outcome is Outcome.OK, result.reason
    assert result.observed_model == profile.model.id
    assert result.cli_version == profile.model.cli_version
    assert result.input_tokens > 0 and result.output_tokens > 0
    assert len(result.config_fingerprint) == 64
