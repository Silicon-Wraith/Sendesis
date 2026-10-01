"""Runner for `codex exec --json`, using the CLI's own login state.

`--json` mode prints no model header, so the model is read from the session
rollout file Codex writes under `$CODEX_HOME/sessions`, found by thread id.
That is also why `--ephemeral` is not passed.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

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
)

FIXED_FLAGS = [
    "-c", "features.apps=false",
    "-c", 'web_search="disabled"',
    "--ignore-user-config",
]


def config_sha256() -> str:
    return config_hash({"runner": "codex_cli", "flags": FIXED_FLAGS, "schema": "strict", "env": "clean_env"})


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """The variant Codex's `--output-schema` accepts: every property required,
    no additional properties, and formerly optional properties made nullable."""

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(x) for x in node]
        if not isinstance(node, dict):
            return node
        node = {k: walk(v) for k, v in node.items() if k not in ("$schema", "$id", "default")}
        if node.get("type") == "object" and "properties" in node:
            required = set(node.get("required", []))
            for name, prop in node["properties"].items():
                if name in required:
                    continue
                if "enum" in prop:
                    prop["enum"] = prop["enum"] + [None]
                elif "type" in prop:
                    types = prop["type"] if isinstance(prop["type"], list) else [prop["type"]]
                    prop["type"] = types + ["null"]
                else:
                    node["properties"][name] = {"anyOf": [prop, {"type": "null"}]}
            node["required"] = list(node["properties"])
            node["additionalProperties"] = False
        return node

    return walk(copy.deepcopy(schema))


def strip_nulls(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: strip_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [strip_nulls(v) for v in value]
    return value


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def find_rollout(home: Path, thread_id: str) -> Path | None:
    return next(iter(sorted((home / "sessions").glob(f"**/rollout-*{thread_id}.jsonl"))), None)


def build_argv(profile: Profile, call: Call, *, schema_path: Path) -> list[str]:
    return [
        profile.cli_binary or "codex", "exec", "--json",
        "-m", profile.model.id,
        "-c", f'model_reasoning_effort="{profile.model.effort}"',
        "--sandbox", "read-only",  # transitional: the sandbox now comes from the role
        *FIXED_FLAGS,
        "-C", str(call.workdir),
        "--output-schema", str(schema_path),
        call.prompt,
    ]


def parse(stdout: str, stderr: str, returncode: int, *, timed_out: bool, wall_s: float, rollout_text: str | None) -> RunResult:
    events = jsonl(stdout)
    model = version = None
    for e in jsonl(rollout_text or ""):
        payload = e.get("payload", {})
        if e.get("type") == "session_meta":
            version = payload.get("cli_version") or version
        elif e.get("type") == "turn_context":
            model = payload.get("model") or model

    errors = [e.get("message") or json.dumps(e.get("error")) for e in events if e.get("type") in ("error", "turn.failed")]
    turn = next((e for e in reversed(events) if e.get("type") == "turn.completed"), None)
    if turn is None:
        reason = "; ".join(str(x) for x in errors) or stderr.strip()[:500] or f"no turn.completed (exit {returncode})"
        if timed_out:
            return RunResult(Status.TIMEOUT, model=model, cli_version=version, wall_s=wall_s, reason="timed out: " + reason[:400])
        status = Status.RATE_LIMIT if is_rate_limit(reason) else Status.ERROR
        return RunResult(status, model=model, cli_version=version, wall_s=wall_s, reason=reason[:500])

    usage = turn.get("usage", {})
    messages = [e["item"] for e in events if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message"]
    text = messages[-1].get("text", "") if messages else ""
    try:
        output = strip_nulls(json.loads(text))
    except json.JSONDecodeError:
        output = None
    return RunResult(
        Status.OK,
        output=output,
        text=text,
        model=model,
        cli_version=version,
        input_tokens=usage.get("input_tokens", 0),
        cached_input_tokens=usage.get("cached_input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        wall_s=wall_s,
        reason="" if output is not None else "answer is not JSON",
    )


def run(profile: Profile, call: Call) -> RunResult:
    with tempfile.TemporaryDirectory() as tmp:
        schema_path = Path(tmp) / "schema.strict.json"
        schema_path.write_text(json.dumps(strict_schema(call.schema)), encoding="utf-8")
        proc = run_process(build_argv(profile, call, schema_path=schema_path), call.workdir, call.timeout_s, clean_env())
    thread = next((e.get("thread_id") for e in jsonl(proc.stdout) if e.get("type") == "thread.started"), None)
    rollout = find_rollout(codex_home(), thread) if thread else None
    rollout_text = rollout.read_text(encoding="utf-8") if rollout else None
    return parse(proc.stdout, proc.stderr, proc.returncode, timed_out=proc.timed_out, wall_s=proc.wall_s, rollout_text=rollout_text)
