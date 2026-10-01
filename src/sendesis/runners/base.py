"""What every runner shares: the call, the result, and the subprocess rules.

Rules from Spike 0 and the Agno spike, enforced here so no runner can forget:
- the child gets an empty stdin (Codex waits on an open one);
- a hard wall-clock timeout, after which the process is killed;
- API keys are removed so a CLI cannot silently switch from the
  subscription to API billing, and the parent Claude Code session's
  variables are removed so a nested `claude -p` starts clean.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

REMOVED_ENV = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY")
REMOVED_ENV_PREFIXES = ("CLAUDE_CODE_", "CLAUDE_")
KEPT_ENV = ("CLAUDE_CONFIG_DIR",)
RATE_LIMIT_PATTERN = re.compile(r"rate.?limit|usage limit|too many requests|\b429\b|quota", re.IGNORECASE)


class Status(str, Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"


@dataclass(frozen=True)
class Call:
    prompt: str
    schema: dict[str, Any]
    workdir: Path
    timeout_s: int


@dataclass
class RunResult:
    status: Status
    output: dict[str, Any] | None = None
    text: str = ""
    model: str | None = None
    cli_version: str | None = None
    input_tokens: int = 0  # total input, cached tokens included
    cached_input_tokens: int = 0
    output_tokens: int = 0
    wall_s: float = 0.0
    list_usd: float | None = None
    reason: str = ""


@dataclass(frozen=True)
class Proc:
    returncode: int
    stdout: str
    stderr: str
    wall_s: float
    timed_out: bool


def clean_env() -> dict[str, str]:
    env = {}
    for key, value in os.environ.items():
        if key in REMOVED_ENV:
            continue
        if key.startswith(REMOVED_ENV_PREFIXES) and key not in KEPT_ENV:
            continue
        if key == "CLAUDECODE":
            continue
        env[key] = value
    return env


def run_process(argv: list[str], cwd: Path, timeout_s: int, env: dict[str, str]) -> Proc:
    start = time.monotonic()
    try:
        done = subprocess.run(
            argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout_s
        )
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return Proc(-9, out, err, time.monotonic() - start, True)
    return Proc(done.returncode, done.stdout, done.stderr, time.monotonic() - start, False)


def cli_version(binary: str, timeout_s: int = 30) -> str | None:
    """Exact `<binary> --version` output, the string profiles pin. No quota is spent."""
    try:
        proc = run_process([binary, "--version"], Path.cwd(), timeout_s, clean_env())
    except FileNotFoundError:
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def config_hash(config: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def schema_without_meta(schema: dict[str, Any]) -> dict[str, Any]:
    """Both CLIs reject the 2020-12 `$schema` URI; the keywords themselves are fine."""
    return {k: v for k, v in schema.items() if k not in ("$schema", "$id")}


def is_rate_limit(text: str) -> bool:
    return bool(RATE_LIMIT_PATTERN.search(text or ""))


def jsonl(text: str) -> list[dict[str, Any]]:
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events
