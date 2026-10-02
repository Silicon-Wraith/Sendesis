"""One seat: a role run on a profile as an Agno Agent.

Qualification (M3.1) and real runs (M3.3 onward) both build seats here, so a
receipt certifies the path production uses (vision decision 14).
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from agno.agent import Agent
from agno.run.base import RunStatus
from agno_cli_models import CliModel
from agno_cli_models import ClaudeCodeModel, CliTimeoutError, CodexModel, ModelRateLimitError
from jsonschema import Draft202012Validator

from sendesis.model import REVIEWER_FORBIDDEN_TOOLS, Profile, Role, schema_validator

CLAUDE_TOOLS = {"read": ("Read",), "search": ("Grep", "Glob")}
_WRAPPED = ("response", "aresponse", "response_stream", "aresponse_stream")


class SandboxUnavailable(Exception):
    """The seat needs access M3.1 cannot enforce; it is refused, never run wider."""


class Outcome(str, Enum):
    OK = "ok"
    INVALID = "invalid"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class SeatResult:
    outcome: Outcome
    output: dict[str, Any] | None = None
    text: str = ""
    observed_model: str | None = None
    cli_version: str | None = None
    config_fingerprint: str | None = None
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    wall_s: float = 0.0
    reason: str = ""


def build_model(profile: Profile, role: Role, *, cwd: Path, timeout_s: float):
    bad = [t for t in role.tools_allowed if t in REVIEWER_FORBIDDEN_TOOLS]
    if bad:
        raise SandboxUnavailable(f"{role.id} needs {', '.join(bad)}; sandboxed edit and shell seats arrive in M3.3")
    m = profile.model
    if m.cls == "claude_code":
        kwargs: dict[str, Any] = {
            "id": m.id, "cwd": str(cwd), "timeout_s": timeout_s,
            "builtin_tools": tuple(t for name in role.tools_allowed for t in CLAUDE_TOOLS[name]),
        }
        if m.effort:
            kwargs["effort"] = m.effort
        max_turns = min((t for t in (role.max_turns, profile.max_turns) if t), default=None)
        if max_turns:
            kwargs["max_turns"] = max_turns
        if profile.idle_timeout_s is not None:
            kwargs["idle_timeout_s"] = profile.idle_timeout_s
        return ClaudeCodeModel(**kwargs)
    if m.cls == "codex":
        kwargs = {"id": m.id, "cwd": str(cwd), "timeout_s": timeout_s, "sandbox": "read-only", "builtin_tools": bool(role.tools_allowed)}
        if m.effort:
            kwargs["effort"] = m.effort
        if profile.idle_timeout_s is not None:
            kwargs["idle_timeout_s"] = profile.idle_timeout_s
        return CodexModel(**kwargs)
    if m.cls == "openai_like":
        from agno.models.openai.like import OpenAILike

        key = os.environ.get(m.api_key_env, "") if m.api_key_env else "not-needed"
        extra: dict[str, Any] = {"reasoning_effort": m.effort} if m.effort else {}
        return OpenAILike(id=m.id, base_url=m.base_url, api_key=key, timeout=timeout_s, max_retries=0, **extra)
    _, module, class_name = m.cls.split(":")
    cls = getattr(importlib.import_module(f"agno.models.{module}"), class_name)
    extra = {"timeout": timeout_s} if "timeout" in getattr(cls, "model_fields", getattr(cls, "__dataclass_fields__", {})) else {}
    return cls(id=m.id, **extra)


def fingerprint(model, profile: Profile | None = None) -> str:
    own = getattr(model, "config_fingerprint", None)
    if callable(own):
        return own()
    if profile is None:
        payload = {"class": type(model).__name__, "id": getattr(model, "id", None)}
    else:
        payload = {"class": profile.model.cls, "id": profile.model.id, "effort": profile.model.effort, "base_url": profile.model.base_url}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _profile_of(agent: Agent) -> Profile | None:
    return getattr(agent.model, "_sendesis_profile", None)


def _capture_errors(model) -> dict[str, Exception | None]:
    holder: dict[str, Exception | None] = {"error": None}

    def remember(exc: Exception) -> None:
        holder["error"] = exc

    for name in _WRAPPED:
        original = getattr(model, name)
        if name == "aresponse":
            async def wrapped(*a, _orig=original, **k):
                try:
                    return await _orig(*a, **k)
                except Exception as exc:
                    remember(exc)
                    raise
        elif name == "aresponse_stream":
            async def wrapped(*a, _orig=original, **k):
                try:
                    async for ev in _orig(*a, **k):
                        yield ev
                except Exception as exc:
                    remember(exc)
                    raise
        elif name == "response_stream":
            def wrapped(*a, _orig=original, **k):
                try:
                    yield from _orig(*a, **k)
                except Exception as exc:
                    remember(exc)
                    raise
        else:
            def wrapped(*a, _orig=original, **k):
                try:
                    return _orig(*a, **k)
                except Exception as exc:
                    remember(exc)
                    raise
        object.__setattr__(model, name, wrapped)
    object.__setattr__(model, "_sendesis_errors", holder)
    return holder


def _schema_for_model(schema: dict[str, Any]) -> dict[str, Any]:
    """Both CLIs reject the 2020-12 `$schema` URI; the keywords themselves are fine."""
    return {k: v for k, v in schema.items() if k not in ("$schema", "$id")}


def make_agent(model, *, instructions: str, schema: dict[str, Any]) -> Agent:
    _capture_errors(model)
    bare = _schema_for_model(schema)
    if isinstance(model, CliModel):
        output_schema = bare
    else:
        # Native structured outputs on OpenAI-style APIs need the response_format envelope.
        output_schema = {"type": "json_schema", "json_schema": {"name": "output", "schema": bare, "strict": False}}
    return Agent(model=model, instructions=instructions, output_schema=output_schema, telemetry=False, markdown=False)


def build_seat(role: Role, profile: Profile, *, root: Path, cwd: Path, timeout_s: float) -> Agent:
    model = build_model(profile, role, cwd=cwd, timeout_s=timeout_s)
    instructions = (root / role.prompt_file).read_text(encoding="utf-8")
    schema = json.loads((root / role.output_schema).read_text(encoding="utf-8"))
    agent = make_agent(model, instructions=instructions, schema=schema)
    object.__setattr__(agent.model, "_sendesis_profile", profile)
    return agent


def _strip_nulls(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_strip_nulls(v) for v in value]
    return value


def _parse_object(text: str) -> dict[str, Any] | None:
    """Strict: the whole reply, minus one surrounding code fence, must be one JSON object."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _raw_text(out: Any) -> str:
    for message in reversed(getattr(out, "messages", None) or []):
        if getattr(message, "role", None) == "assistant" and isinstance(message.content, str):
            return message.content
    return out.content if isinstance(out.content, str) else ""


def _is_timeout(err: BaseException | None) -> bool:
    try:
        from openai import APITimeoutError
    except ImportError:  # pragma: no cover
        APITimeoutError = ()  # type: ignore[assignment]
    seen = []
    while err is not None and err not in seen:
        if isinstance(err, (CliTimeoutError, TimeoutError, APITimeoutError)):
            return True
        seen.append(err)
        err = err.__cause__ or err.__context__
    return False


def run_seat(agent: Agent, message: str, validator: Draft202012Validator) -> SeatResult:
    holder = getattr(agent.model, "_sendesis_errors", {"error": None})
    holder["error"] = None
    start = time.monotonic()
    out = agent.run(message)
    wall = time.monotonic() - start
    info = (out.model_provider_data or {}).get("agno_cli_models")
    text = _raw_text(out)
    metrics = out.metrics
    result = SeatResult(
        outcome=Outcome.OK,
        text=text,
        observed_model=info.get("observed_model") if info is not None else getattr(out, "model", None),
        cli_version=(info or {}).get("cli_version"),
        config_fingerprint=(info or {}).get("config_fingerprint") or fingerprint(agent.model, _profile_of(agent)),
        input_tokens=getattr(metrics, "input_tokens", 0) or 0,
        cached_input_tokens=getattr(metrics, "cache_read_tokens", 0) or 0,
        output_tokens=getattr(metrics, "output_tokens", 0) or 0,
        wall_s=round(wall, 3),
    )
    if out.status == RunStatus.error:
        err = holder.get("error")
        if isinstance(err, ModelRateLimitError):
            result.outcome = Outcome.RATE_LIMIT
        elif _is_timeout(err):
            result.outcome = Outcome.TIMEOUT
        else:
            result.outcome = Outcome.ERROR
        result.reason = f"{type(err).__name__}: {err}" if err else str(out.content)[:500]
        return result
    if out.status not in (RunStatus.completed, RunStatus.running):
        result.outcome, result.reason = Outcome.ERROR, f"run ended with status {getattr(out.status, 'value', out.status)}"
        return result
    data = _parse_object(text)
    if data is None:
        result.outcome, result.reason = Outcome.INVALID, "output is not a JSON object"
        return result
    data = _strip_nulls(data)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        e = errors[0]
        result.outcome = Outcome.INVALID
        result.reason = f"{'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}"
        return result
    result.output = data
    return result


def run_role(role: Role, profile: Profile, message: str, *, root: Path, cwd: Path, timeout_s: float) -> SeatResult:
    agent = build_seat(role, profile, root=root, cwd=cwd, timeout_s=timeout_s)
    return run_seat(agent, message, schema_validator(root, Path(role.output_schema).name))
