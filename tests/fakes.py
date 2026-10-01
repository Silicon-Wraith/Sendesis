"""Test doubles. No network, no CLI, no quota."""

from __future__ import annotations

from dataclasses import dataclass, field

from agno.metrics import MessageMetrics
from agno_cli_models._base import CliModel


@dataclass
class ScriptedModel(CliModel):
    """An Agno model that replays scripted replies.

    Built on agno-cli-models' CliModel (the same pattern as that package's own
    tests), so Agno drives it exactly as it drives ClaudeCodeModel and
    CodexModel: same structured-output path, same run info, same metrics.
    """

    id: str = "scripted"
    CLI = "claude"
    replies: list = field(default_factory=list)
    observed_model: str = "scripted-1"
    cli_version: str = "9.9.9"
    calls: list = field(default_factory=list)

    def config_fingerprint(self) -> str:
        return "f" * 64

    async def _drive(self, messages, response_format, tools, tool_call_limit, run_response, stream):
        self.calls.append([m.content for m in messages])
        item = self.replies.pop(0)
        if isinstance(item, BaseException):
            raise item
        metrics = MessageMetrics()
        metrics.input_tokens, metrics.output_tokens = 100, 20
        yield self.usage_event(metrics, item, {"observed_model": self.observed_model, "cli_version": self.cli_version})
