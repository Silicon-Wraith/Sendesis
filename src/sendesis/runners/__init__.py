"""Runners turn a profile into one call and return output plus usage.

Only the router picks a profile. `run` dispatches on `profile.runner`.
"""

from __future__ import annotations

from sendesis.model import Profile
from sendesis.runners import claude_cli, codex_cli, openai_http
from sendesis.runners.base import Call, RunResult, Status, cli_version

MODULES = {"claude_cli": claude_cli, "codex_cli": codex_cli, "openai_http": openai_http}


def run(profile: Profile, capabilities: tuple[str, ...], call: Call) -> RunResult:
    if profile.runner == "claude_cli":
        return claude_cli.run(profile, capabilities, call)
    if profile.runner == "codex_cli":
        return codex_cli.run(profile, call)
    return openai_http.run(profile, call)


def config_sha256(profile: Profile) -> str:
    return MODULES[profile.runner].config_sha256()


__all__ = ["Call", "RunResult", "Status", "cli_version", "config_sha256", "run", "claude_cli", "codex_cli", "openai_http"]
