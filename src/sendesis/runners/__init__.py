"""Runners turn a profile into one call and return output plus usage.

Only the router picks a profile. `run` dispatches on `profile.model.cls`.
"""

from __future__ import annotations

from sendesis.model import Profile
from sendesis.runners import claude_cli, codex_cli, openai_http
from sendesis.runners.base import Call, RunResult, Status, cli_version

MODULES = {"claude_cli": claude_cli, "codex_cli": codex_cli, "openai_http": openai_http}

# Transitional (Task 2): the old runners retire in Tasks 7 to 10.
RUNNER_OF_CLASS = {"claude_code": "claude_cli", "codex": "codex_cli"}


def run(profile: Profile, capabilities: tuple[str, ...], call: Call) -> RunResult:
    if profile.model.cls == "claude_code":
        return claude_cli.run(profile, capabilities, call)
    if profile.model.cls == "codex":
        return codex_cli.run(profile, call)
    return openai_http.run(profile, call)


def config_sha256(profile: Profile) -> str:
    return MODULES[RUNNER_OF_CLASS.get(profile.model.cls, "openai_http")].config_sha256()


__all__ = ["Call", "RunResult", "Status", "cli_version", "config_sha256", "run", "claude_cli", "codex_cli", "openai_http"]
