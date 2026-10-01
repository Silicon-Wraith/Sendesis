"""Runner for `claude -p`, using the CLI's own login state.

Uses `--output-format stream-json --verbose` rather than plain `json`: the
extra `init` event reports the CLI version and the tools the session really
had, and the final `result` event is the same object `json` would return.
"""

from __future__ import annotations

import json

from sendesis.model import Profile
from sendesis.runners.base import (
    Call,
    RunResult,
    Status,
    clean_env,
    config_hash,
    is_rate_limit,
    jsonl,
    run_process,
    schema_without_meta,
)

# Abstract role capabilities to Claude Code tool names. Review roles never get Bash.
TOOL_MAP = {"read": ("Read",), "search": ("Grep", "Glob")}

SETTINGS = {"disableClaudeAiConnectors": True, "autoMemoryEnabled": False}
FIXED_FLAGS = [
    "--output-format", "stream-json", "--verbose",
    "--strict-mcp-config", "--setting-sources", "",
    "--no-session-persistence", "--disable-slash-commands",
    "--disallowedTools", "Bash",
    "--settings", json.dumps(SETTINGS, sort_keys=True),
]


def config_sha256() -> str:
    return config_hash({"runner": "claude_cli", "flags": FIXED_FLAGS, "tool_map": TOOL_MAP, "env": "clean_env"})


def build_argv(profile: Profile, capabilities: tuple[str, ...], call: Call) -> list[str]:
    tools: list[str] = []
    for cap in capabilities:
        if cap not in TOOL_MAP:
            raise ValueError(f"capability '{cap}' is not available to claude_cli review runs")
        tools.extend(TOOL_MAP[cap])
    tool_list = ",".join(tools)
    argv = [profile.cli_binary or "claude", "-p", call.prompt, "--model", profile.model.id, "--effort", profile.model.effort]
    argv += ["--tools", tool_list]
    if tools:
        argv += ["--allowedTools", tool_list]
    argv += FIXED_FLAGS
    argv += ["--json-schema", json.dumps(schema_without_meta(call.schema))]
    return argv


def parse(stdout: str, stderr: str, returncode: int, *, timed_out: bool, wall_s: float) -> RunResult:
    events = jsonl(stdout)
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    version = init.get("claude_code_version")

    if result is None:
        status = Status.TIMEOUT if timed_out else Status.ERROR
        reason = "timed out with no result" if timed_out else f"no result event (exit {returncode}): {stderr.strip()[:500]}"
        if is_rate_limit(stderr):
            status = Status.RATE_LIMIT
        return RunResult(status, cli_version=version, wall_s=wall_s, reason=reason)

    usage = result.get("modelUsage") or {}
    input_tokens = sum(m.get("inputTokens", 0) + m.get("cacheReadInputTokens", 0) + m.get("cacheCreationInputTokens", 0) for m in usage.values())
    cached = sum(m.get("cacheReadInputTokens", 0) for m in usage.values())
    output_tokens = sum(m.get("outputTokens", 0) for m in usage.values())
    # The model that did the work: most output tokens. Helper models may appear with small counts.
    model = max(usage, key=lambda k: usage[k].get("outputTokens", 0)) if usage else None
    common = dict(
        text=str(result.get("result") or ""),
        model=model,
        cli_version=version,
        input_tokens=input_tokens,
        cached_input_tokens=cached,
        output_tokens=output_tokens,
        wall_s=wall_s,
        list_usd=result.get("total_cost_usd"),
    )

    if result.get("is_error"):
        text = f"{result.get('subtype')} {result.get('api_error_status')} {result.get('result')}"
        status = Status.RATE_LIMIT if result.get("api_error_status") == 429 or is_rate_limit(text) else Status.ERROR
        return RunResult(status, reason=text[:500], **common)

    output = result.get("structured_output")
    if output is None:
        try:
            output = json.loads(common["text"])
        except json.JSONDecodeError:
            output = None
    reason = "" if output is not None else "answer is not JSON"
    if result.get("permission_denials"):
        reason = f"permission denials: {result['permission_denials']}"
    return RunResult(Status.OK, output=output, reason=reason, **common)


def run(profile: Profile, capabilities: tuple[str, ...], call: Call) -> RunResult:
    proc = run_process(build_argv(profile, capabilities, call), call.workdir, call.timeout_s, clean_env())
    return parse(proc.stdout, proc.stderr, proc.returncode, timed_out=proc.timed_out, wall_s=proc.wall_s)
