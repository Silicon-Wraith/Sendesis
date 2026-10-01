"""Real CLI calls. They spend subscription quota, so they only run on purpose:

    .venv/bin/pytest -m integration
"""

import pytest

from conftest import REPO
from sendesis.model import load_profile, load_role
from sendesis.seat import Outcome, run_role

pytestmark = pytest.mark.integration

PROMPT = (
    "Review this diff for security problems. Return JSON for the findings schema with role_id "
    "security-reviewer.\n\n```diff\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n"
    "-cur.execute('SELECT * FROM t WHERE id = ?', (i,))\n+cur.execute(f'SELECT * FROM t WHERE id = {i}')\n```\n"
)


@pytest.fixture
def workdir(tmp_path):
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, stdin=subprocess.DEVNULL)
    return tmp_path


@pytest.mark.parametrize("name", ["claude-opus", "codex-gpt"])
def test_real_call_returns_pinned_model_and_version(name, workdir):
    profile = load_profile(REPO / "profiles" / f"{name}.yaml", REPO)
    role = load_role(REPO / "roles" / "security-reviewer.yaml", REPO)
    result = run_role(role, profile, PROMPT, root=REPO, cwd=workdir, timeout_s=profile.timeout_s)
    assert result.outcome is Outcome.OK, result.reason
    assert result.observed_model == profile.model.id
    assert result.cli_version == profile.model.cli_version, "installed CLI differs from the profile pin"
    assert result.output is not None and "findings" in result.output
    assert result.input_tokens > 0 and result.output_tokens > 0
