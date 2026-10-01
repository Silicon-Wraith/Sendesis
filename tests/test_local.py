"""Local tier: a real local model through Agno's OpenAILike. Free; run with -m local."""

from pathlib import Path

import pytest

from sendesis.model import load_profile
from sendesis.qualify import qualify

pytestmark = pytest.mark.local
REPO = Path(__file__).resolve().parent.parent


def test_smoke_suite_dry_run_on_the_local_model(tmp_path):
    profile = load_profile(REPO / "profiles" / "ollama-local.yaml", REPO)
    if not profile.enabled:
        pytest.skip("ollama-local is disabled; set its model and family, then enable it")
    result = qualify(REPO, "security-reviewer", "ollama-local", suite_dir=REPO / "suites" / "security-reviewer-smoke",
                     dry_run=True, runs_dir=tmp_path / "runs")
    r = result.receipt
    assert r["suite"]["n_cases"] == 10
    assert {s["metric"] for s in r["scores"]} >= {"recall", "schema_validity"}
    print(result.path, r["status"], r.get("status_reason", ""))
