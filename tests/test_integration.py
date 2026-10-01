"""Real CLI calls. They spend subscription quota, so they only run on purpose:

    .venv/bin/pytest -m integration
"""

import json

import pytest

from conftest import REPO
from sendesis.model import load_profile
from sendesis.runners import Call, Status, claude_cli, cli_version, codex_cli

pytestmark = pytest.mark.integration

SCHEMA = json.loads((REPO / "schemas" / "finding.json").read_text())
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


@pytest.mark.parametrize("name, module", [("claude-opus", claude_cli), ("codex-gpt", codex_cli)])
def test_real_call_returns_pinned_model_and_version(name, module, workdir):
    profile = load_profile(REPO / "profiles" / f"{name}.yaml", REPO)
    assert cli_version(profile.cli_binary) == profile.cli_version, "installed CLI differs from the profile pin"
    call = Call(PROMPT, SCHEMA, workdir, profile.timeout_s)
    result = module.run(profile, ("read", "search"), call) if module is claude_cli else module.run(profile, call)
    assert result.status is Status.OK, result.reason
    assert result.model == profile.model
    assert result.output is not None and "findings" in result.output
    assert result.input_tokens > 0 and result.output_tokens > 0
