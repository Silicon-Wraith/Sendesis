"""Runner for local OpenAI-compatible servers (Ollama, vLLM). No tools, ever."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request

from sendesis.model import Profile
from sendesis.runners.base import Call, RunResult, Status, config_hash, schema_without_meta


def config_sha256() -> str:
    return config_hash({"runner": "openai_http", "api": "chat/completions", "response_format": "json_schema", "tools": None})


def run(profile: Profile, call: Call) -> RunResult:
    body = {
        "model": profile.model.id,
        "messages": [{"role": "user", "content": call.prompt}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "findings", "schema": schema_without_meta(call.schema)},
        },
    }
    if profile.model.effort:
        body["reasoning_effort"] = profile.model.effort
    request = urllib.request.Request(
        profile.model.base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=call.timeout_s) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        status = Status.RATE_LIMIT if exc.code == 429 else Status.ERROR
        return RunResult(status, wall_s=time.monotonic() - start, reason=f"HTTP {exc.code}: {exc.reason}")
    except (TimeoutError, socket.timeout):
        return RunResult(Status.TIMEOUT, wall_s=time.monotonic() - start, reason="timed out")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        return RunResult(Status.ERROR, wall_s=time.monotonic() - start, reason=str(exc)[:500])

    wall_s = time.monotonic() - start
    usage = payload.get("usage") or {}
    text = (payload.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    try:
        output = json.loads(text)
    except json.JSONDecodeError:
        output = None
    return RunResult(
        Status.OK,
        output=output,
        text=text,
        model=payload.get("model"),
        input_tokens=usage.get("prompt_tokens", 0),
        cached_input_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
        wall_s=wall_s,
        reason="" if output is not None else "answer is not JSON",
    )
