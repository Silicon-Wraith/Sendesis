"""Local tier: a real local model through Agno's OpenAILike. Free; run with -m local."""

import urllib.request
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
    try:
        urllib.request.urlopen(profile.model.base_url.rstrip("/") + "/models", timeout=5).close()
    except OSError as exc:
        pytest.skip(f"local server at {profile.model.base_url} is unreachable: {exc}")
    result = qualify(REPO, "security-reviewer", "ollama-local", suite_dir=REPO / "suites" / "security-reviewer-smoke",
                     dry_run=True, runs_dir=tmp_path / "runs")
    r = result.receipt
    assert r["suite"]["n_cases"] == 10
    assert {s["metric"] for s in r["scores"]} >= {"recall", "schema_validity"}
    reason = r.get("status_reason", "")
    assert r["observed"][0]["model"] == profile.model.id, "no case succeeded or the wrong model answered: " + reason
    assert r["cost"]["output_tokens"] > 0, reason
    # per-case failures are recorded as "case <id>: <outcome>: ..." in status_reason
    assert "case " not in reason, reason
    print(result.path, r["status"], r.get("status_reason", ""))
