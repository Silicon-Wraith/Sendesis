# M1: agno-cli-models 0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `agno-cli-models` 0.1, a standalone Python package with two Agno `Model` classes, `ClaudeCodeModel` and `CodexModel`, that run Agno agents on the official Claude Code and Codex clients with isolation, typed errors, persisted CLI sessions, human approvals on both CLIs, and full test coverage.

**Architecture:** One shared base class (`CliModel`) owns everything Agno-facing: the `aresponse`/`aresponse_stream` entry points, the wall-clock timeout, the sync wrappers, metric accounting and run info. A shared `ToolBridge` runs every CLI tool call through Agno's own `arun_function_calls`, so hooks, limits and approval pauses behave as with any Agno model. Each CLI has three small modules: an options or protocol builder (pure, unit-tested), a translator from CLI messages to metrics and errors (pure, unit-tested), and the model engine that wires them to the client. The Claude client is the Claude Agent SDK; the Codex client is `codex app-server` over JSON-RPC on stdio. Both clients are injectable, so engine tests run against fakes and spend no quota.

**Tech Stack:** Python 3.11, `agno` 3.0.x, `claude-agent-sdk` 0.2.x, Claude Code 2.1.286, codex-cli 0.155.1, pytest.

**Spec:** `docs/specs/2026-09-30-system-vision-design.md` in the Sendesis repo, section 5 and roadmap item M1. The spike being hardened is in the Agno worktree at `/mnt/ml_storage/dev/projects/agno/.claude/worktrees/argo-spike/spike/` (`claude_code_model.py`, `codex_model.py`, `FINDINGS.md`).

## Global Constraints

- New repository at `/mnt/ml_storage/dev/projects/agno-cli-models`, MIT license, package `agno_cli_models` under `src/`.
- Python `>=3.11`. Virtualenv in `.venv`. No global installs.
- Dependencies: `agno>=3.0.11,<3.1`, `claude-agent-sdk>=0.2.163,<0.3`. Dev: `pytest>=8`.
- Auth is the CLI's own login state only. Never read, store or pass `CLAUDE_CODE_OAUTH_TOKEN` or any token file. Never set `CODEX_HOME` by default.
- Never use `--bare`, `danger-full-access`, or `bypassPermissions` anywhere.
- Child processes never see `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `CODEX_API_KEY`, `CLAUDECODE`, or any `CLAUDE_*` variable except `CLAUDE_CONFIG_DIR` and `CLAUDE_CODE_ENTRYPOINT`.
- Every subprocess gets an empty stdin and a hard wall-clock timeout.
- Supported CLI versions: Claude Code `2.1.286`, codex-cli `0.155.1`. An unknown version warns; it never fails silently and never blocks.
- Token semantics, identical for both models: `input_tokens` is total input including cached tokens; `cache_read_tokens` is the cached part; `cache_write_tokens` is cache creation (Claude only); `reasoning_tokens` is reasoning or thinking output; `total_tokens = input_tokens + output_tokens`.
- Unit tests never call a real CLI. Real calls only in tests marked `@pytest.mark.integration`, which are deselected by default.
- In docs and user-facing text, do not use em dashes.
- Feature work happens in a worktree: all tasks after Task 1 run in `/mnt/ml_storage/dev/projects/agno-cli-models-m1` on branch `m1`.
- Nothing is pushed to GitHub by this plan. Creating the remote is the user's call.

## Review Focus

These are the inputs most likely to bite a user that the spec implies but no happy-path test exercises. Each has a pinned test in the task named.

1. **Agno session reused across processes with no history in context.** A user runs an agent with `add_history_to_context=False`. Expected: a fresh CLI conversation, never a resume of an unrelated session. (Task 2, `test_find_cli_session_ignores_other_cli_and_absent_data`; Task 7, `test_no_history_means_fresh_session`.)
2. **The parent process is itself a Claude Code session** (Sendesis is developed inside one). Expected: the child CLI does not inherit `CLAUDE_CODE_SESSION_ID`, `CLAUDE_EFFORT` and friends, and the parent's `os.environ` is never mutated. (Task 1, `test_blanking_overrides_never_mutate_environ`.)
3. **The CLI hangs** (unreachable provider). Expected: `CliTimeoutError` after `timeout_s`, the client task cancelled, no orphan process. (Task 3, `test_aresponse_times_out`; Task 8, `test_rpc_close_kills_hung_process`.)
4. **Sync `agent.run()` called from inside a running event loop** (Jupyter, an async web handler). Expected: it works instead of raising "asyncio.run() cannot be called from a running event loop". (Task 2, `test_run_sync_inside_running_loop`.)
5. **Two parallel calls to the same Agno tool with different arguments** on Claude. Expected: each handler gets its own `tool_use_id`, so a later pause or precomputed result attaches to the right call. (Task 6, `test_matcher_pairs_by_arguments_not_order`.)

---

## File Structure

```
agno-cli-models/
  pyproject.toml
  LICENSE
  README.md
  src/agno_cli_models/
    __init__.py          public exports, __version__
    _env.py              child environment policy (clean_env, blanking_overrides)
    _common.py           text_of, canon_args, prompts, find_cli_session, strict_schema,
                         strip_nulls, config_hash, run_sync
    errors.py            CliTimeoutError, CliProtocolError (+ re-export Agno's rate-limit error)
    versions.py          SUPPORTED, installed_version, check_supported, warning class
    _bridge.py           ToolBridge: Agno tool execution and pauses for both CLIs
    _base.py             CliModel: shared Agno Model plumbing
    claude/__init__.py
    claude/options.py    build_options, fingerprint, ISOLATION_SETTINGS
    claude/translate.py  usage_metrics, observed_model, check_result, rate_limit_error
    claude/matcher.py    CallIdMatcher (tool_use_id pairing)
    claude/model.py      ClaudeCodeModel
    codex/__init__.py
    codex/rpc.py         Rpc: JSON-RPC 2.0 over a subprocess
    codex/protocol.py    thread_start_params, turn_start_params, fingerprint, TurnTracker
    codex/model.py       CodexModel
  tests/
    conftest.py
    test_env.py  test_common.py  test_versions.py  test_bridge.py  test_base.py
    test_claude_options.py  test_claude_translate.py  test_claude_matcher.py  test_claude_model.py
    test_codex_rpc.py  test_codex_protocol.py  test_codex_model.py
    test_integration.py
```

---

### Task 1: Repository, packaging, environment policy

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `README.md`, `.gitignore`, `src/agno_cli_models/__init__.py`, `src/agno_cli_models/_env.py`, `tests/conftest.py`, `tests/test_env.py`

**Interfaces:**
- Produces: `agno_cli_models._env.clean_env(environ: Mapping[str, str] | None = None) -> dict[str, str]`, `blanking_overrides(environ: Mapping[str, str] | None = None) -> dict[str, str]`, `is_removed(key: str) -> bool`.

- [ ] **Step 1: Create the repository and the worktree**

```bash
mkdir -p /mnt/ml_storage/dev/projects/agno-cli-models && cd /mnt/ml_storage/dev/projects/agno-cli-models
git init -q -b main
cp /mnt/ml_storage/dev/projects/sendesis/LICENSE LICENSE   # MIT, Silicon Wraith
printf '# agno-cli-models\n\nAgno models backed by the official Claude Code and Codex clients.\n' > README.md
printf '.venv/\n__pycache__/\n*.egg-info/\n.pytest_cache/\n' > .gitignore
git add . && git commit -q -m "Initial commit"
git worktree add ../agno-cli-models-m1 -b m1
cd ../agno-cli-models-m1
```

- [ ] **Step 2: Write `pyproject.toml` and the package stub**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "agno-cli-models"
version = "0.1.0"
description = "Agno models backed by the official Claude Code and Codex clients."
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.11"
dependencies = [
    "agno>=3.0.11,<3.1",
    "claude-agent-sdk>=0.2.163,<0.3",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--strict-markers -m 'not integration'"
markers = ["integration: real Claude Code or Codex calls; spends subscription quota; run on purpose only"]
```

`src/agno_cli_models/__init__.py`:

```python
"""Agno models backed by the official Claude Code and Codex clients."""

__version__ = "0.1.0"
```

`tests/conftest.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
```

Create the venv and install:

```bash
/usr/bin/python3.11 -m venv .venv && .venv/bin/pip install -q -e '.[dev]'
```

- [ ] **Step 3: Write the failing tests for the environment policy**

`tests/test_env.py`:

```python
import os

from agno_cli_models._env import blanking_overrides, clean_env, is_removed

PARENT = {
    "HOME": "/home/u",
    "PATH": "/usr/bin",
    "ANTHROPIC_API_KEY": "sk-a",
    "OPENAI_API_KEY": "sk-o",
    "CODEX_API_KEY": "sk-c",
    "CLAUDECODE": "1",
    "CLAUDE_CODE_SESSION_ID": "parent",
    "CLAUDE_EFFORT": "max",
    "CLAUDE_CONFIG_DIR": "/home/u/.claude-alt",
    "CLAUDE_CODE_ENTRYPOINT": "cli",
}


def test_is_removed():
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY", "CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_EFFORT"):
        assert is_removed(key), key
    for key in ("HOME", "PATH", "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_ENTRYPOINT"):
        assert not is_removed(key), key


def test_clean_env_drops_keys_and_parent_session_vars():
    env = clean_env(PARENT)
    assert env == {"HOME": "/home/u", "PATH": "/usr/bin", "CLAUDE_CONFIG_DIR": "/home/u/.claude-alt", "CLAUDE_CODE_ENTRYPOINT": "cli"}


def test_blanking_overrides_blank_only_present_removed_keys():
    over = blanking_overrides(PARENT)
    assert over == {k: "" for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY", "CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_EFFORT")}


def test_blanking_overrides_never_mutate_environ(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-live")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent")
    blanking_overrides()
    clean_env()
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-live"
    assert os.environ["CLAUDE_CODE_SESSION_ID"] == "parent"
```

- [ ] **Step 4: Run the tests and watch them fail**

Run: `.venv/bin/pytest tests/test_env.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'agno_cli_models._env'`.

- [ ] **Step 5: Implement `_env.py`**

```python
"""What a child CLI process may see of the parent environment.

API keys are removed so a CLI can never silently switch from the subscription
login to API billing. Claude Code session variables are removed because a
parent Claude Code session sets several (session id, effort) that would
otherwise leak into the child.
"""

from __future__ import annotations

import os
from typing import Mapping

REMOVED_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY", "CLAUDECODE")
REMOVED_PREFIXES = ("CLAUDE_",)
KEPT_KEYS = ("CLAUDE_CONFIG_DIR", "CLAUDE_CODE_ENTRYPOINT")


def is_removed(key: str) -> bool:
    if key in KEPT_KEYS:
        return False
    return key in REMOVED_KEYS or key.startswith(REMOVED_PREFIXES)


def clean_env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """A full environment for a child we spawn ourselves (Codex)."""
    source = os.environ if environ is None else environ
    return {k: v for k, v in source.items() if not is_removed(k)}


def blanking_overrides(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Overrides for a child spawned by the Claude Agent SDK, which merges the
    parent environment under `options.env` and cannot delete keys. Blank
    values hide them without touching the parent's `os.environ`."""
    source = os.environ if environ is None else environ
    return {k: "" for k in source if is_removed(k)}
```

- [ ] **Step 6: Run the tests and watch them pass**

Run: `.venv/bin/pytest tests/test_env.py -v`
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add . && git commit -q -m "Packaging and child environment policy"
```

---

### Task 2: Shared helpers, errors and version checks

**Files:**
- Create: `src/agno_cli_models/_common.py`, `src/agno_cli_models/errors.py`, `src/agno_cli_models/versions.py`, `tests/test_common.py`, `tests/test_versions.py`

**Interfaces:**
- Consumes: `clean_env` from Task 1.
- Produces:
  - `_common.text_of(content: Any) -> str`
  - `_common.canon_args(args: Mapping[str, Any] | None) -> str`
  - `_common.split_system(messages: list[Message]) -> tuple[str, list[Message]]`
  - `_common.last_user_text(rest: list[Message]) -> str`
  - `_common.transcript_prompt(rest: list[Message]) -> str`
  - `_common.find_cli_session(messages: list[Message], cli: str) -> str | None`
  - `_common.session_marker(cli: str, session_id: str) -> dict[str, str]`
  - `_common.strict_schema(schema: dict) -> dict`, `_common.strip_nulls(value: Any) -> Any`
  - `_common.config_hash(config: Mapping[str, Any]) -> str`
  - `_common.run_sync(coro: Coroutine[Any, Any, T]) -> T`
  - `errors.CliTimeoutError(ModelProviderError)`, `errors.CliProtocolError(ModelProviderError)`, re-exports `ModelRateLimitError`, `ModelProviderError`, `ContextWindowExceededError` from `agno.exceptions`
  - `versions.SUPPORTED: dict[str, tuple[str, ...]]`, `versions.parse_version(text: str) -> str | None`, `versions.installed_version(binary: str) -> str | None`, `versions.check_supported(cli: str, version: str | None) -> bool`, `versions.UnsupportedCliVersionWarning(UserWarning)`

- [ ] **Step 1: Write the failing tests**

`tests/test_common.py`:

```python
import asyncio

from agno.models.message import Message

from agno_cli_models._common import (
    canon_args,
    config_hash,
    find_cli_session,
    last_user_text,
    run_sync,
    session_marker,
    split_system,
    strict_schema,
    strip_nulls,
    text_of,
    transcript_prompt,
)


def test_text_of():
    assert text_of(None) == ""
    assert text_of("hi") == "hi"
    assert text_of({"a": 1}) == '{"a": 1}'
    assert text_of(["a", "b"]) == "a\nb"


def test_canon_args_is_order_independent():
    assert canon_args({"b": 1, "a": 2}) == canon_args({"a": 2, "b": 1})
    assert canon_args(None) == "{}"


def test_split_system_and_last_user():
    msgs = [Message(role="system", content="S1"), Message(role="user", content="u1"),
            Message(role="system", content="S2"), Message(role="assistant", content="a1"),
            Message(role="user", content="u2")]
    system, rest = split_system(msgs)
    assert system == "S1\n\nS2"
    assert [m.role for m in rest] == ["user", "assistant", "user"]
    assert last_user_text(rest) == "u2"


def test_transcript_prompt_replays_history():
    rest = [Message(role="user", content="hello"), Message(role="assistant", content="hi there"),
            Message(role="user", content="and now?")]
    assert transcript_prompt(rest) == "Conversation so far:\nUSER: hello\nASSISTANT: hi there\n\nUSER: and now?"


def test_transcript_prompt_without_history_is_just_the_message():
    assert transcript_prompt([Message(role="user", content="only")]) == "only"


def test_find_cli_session_takes_latest_matching_marker():
    msgs = [Message(role="assistant", content="a", provider_data=session_marker("claude", "s1")),
            Message(role="assistant", content="b", provider_data=session_marker("codex", "t1")),
            Message(role="assistant", content="c", provider_data=session_marker("claude", "s2"))]
    assert find_cli_session(msgs, "claude") == "s2"
    assert find_cli_session(msgs, "codex") == "t1"


def test_find_cli_session_ignores_other_cli_and_absent_data():
    msgs = [Message(role="user", content="x"), Message(role="assistant", content="y"),
            Message(role="assistant", content="z", provider_data={"something": "else"})]
    assert find_cli_session(msgs, "claude") is None


def test_strict_schema_requires_every_property_and_nullable_optionals():
    schema = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "integer"}}, "required": ["a"]}
    strict = strict_schema(schema)
    assert strict["required"] == ["a", "b"]
    assert strict["additionalProperties"] is False
    assert strict["properties"]["b"]["type"] == ["integer", "null"]
    assert schema["required"] == ["a"]  # input not mutated


def test_strip_nulls():
    assert strip_nulls({"a": None, "b": [{"c": None, "d": 1}]}) == {"b": [{"d": 1}]}


def test_config_hash_is_stable_and_sensitive():
    assert config_hash({"a": 1, "b": [1, 2]}) == config_hash({"b": [1, 2], "a": 1})
    assert config_hash({"a": 1}) != config_hash({"a": 2})


async def _double(x):
    await asyncio.sleep(0)
    return x * 2


def test_run_sync_without_loop():
    assert run_sync(_double(2)) == 4


def test_run_sync_inside_running_loop():
    async def outer():
        return run_sync(_double(3))

    assert asyncio.run(outer()) == 6
```

`tests/test_versions.py`:

```python
import sys
import warnings

import pytest

from agno_cli_models.versions import UnsupportedCliVersionWarning, check_supported, installed_version, parse_version


def test_parse_version():
    assert parse_version("2.1.286 (Claude Code)") == "2.1.286"
    assert parse_version("codex-cli 0.155.1") == "0.155.1"
    assert parse_version("nothing here") is None


def test_supported_versions_pass_silently():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert check_supported("claude", "2.1.286") is True
        assert check_supported("codex", "0.155.1") is True


@pytest.mark.parametrize("cli, version", [("claude", "2.1.999"), ("codex", None)])
def test_unknown_version_warns_and_returns_false(cli, version):
    with pytest.warns(UnsupportedCliVersionWarning):
        assert check_supported(cli, version) is False


def test_installed_version_reads_the_binary(tmp_path):
    fake = tmp_path / "fakecli"
    fake.write_text(f"#!{sys.executable}\nprint('9.8.7 (Fake)')\n")
    fake.chmod(0o755)
    assert installed_version(str(fake)) == "9.8.7"
    assert installed_version(str(tmp_path / "missing")) is None
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/bin/pytest tests/test_common.py tests/test_versions.py -v`
Expected: collection errors, modules not found.

- [ ] **Step 3: Implement `_common.py`**

```python
"""Small helpers shared by both CLI models."""

from __future__ import annotations

import asyncio
import concurrent.futures
import copy
import hashlib
import json
from typing import Any, Coroutine, Mapping, TypeVar

from agno.models.message import Message

T = TypeVar("T")
SESSION_KEY = "agno_cli_models"


def text_of(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(c) for c in content)
    return json.dumps(content)


def canon_args(args: Mapping[str, Any] | None) -> str:
    return json.dumps(dict(args or {}), sort_keys=True, separators=(",", ":"))


def split_system(messages: list[Message]) -> tuple[str, list[Message]]:
    system = "\n\n".join(text_of(m.content) for m in messages if m.role == "system")
    return system, [m for m in messages if m.role != "system"]


def last_user_text(rest: list[Message]) -> str:
    last = next((m for m in reversed(rest) if m.role == "user"), None)
    return text_of(last.content) if last else ""


def transcript_prompt(rest: list[Message]) -> str:
    """Prompt for a fresh CLI session when Agno already has history: replay it."""
    last = next((m for m in reversed(rest) if m.role == "user"), None)
    history = [m for m in rest if m is not last and m.role in ("user", "assistant") and m.content]
    body = text_of(last.content) if last else ""
    if not history:
        return body
    lines = [f"{m.role.upper()}: {text_of(m.content)}" for m in history]
    return "Conversation so far:\n" + "\n".join(lines) + "\n\nUSER: " + body


def session_marker(cli: str, session_id: str) -> dict[str, str]:
    """provider_data stored on assistant messages so Agno persists the CLI session id."""
    return {f"{SESSION_KEY}_cli": cli, f"{SESSION_KEY}_session": session_id}


def find_cli_session(messages: list[Message], cli: str) -> str | None:
    for m in reversed(messages):
        data = m.provider_data or {}
        if data.get(f"{SESSION_KEY}_cli") == cli and data.get(f"{SESSION_KEY}_session"):
            return data[f"{SESSION_KEY}_session"]
    return None


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """OpenAI strict variant: every property required, no extra properties,
    formerly optional properties made nullable."""

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


def config_hash(config: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine from sync code, even when an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
```

- [ ] **Step 4: Implement `errors.py`**

```python
"""Typed failures. Rate limits use Agno's own error so Agno's FallbackConfig and
callers such as Sendesis can react to them without knowing this package."""

from agno.exceptions import ContextWindowExceededError, ModelProviderError, ModelRateLimitError

__all__ = ["CliProtocolError", "CliTimeoutError", "ContextWindowExceededError", "ModelProviderError", "ModelRateLimitError"]


class CliTimeoutError(ModelProviderError):
    """The CLI produced no complete answer within the wall-clock limit."""

    def __init__(self, message: str, model_name: str | None = None, model_id: str | None = None):
        super().__init__(message, status_code=504, model_name=model_name, model_id=model_id)


class CliProtocolError(ModelProviderError):
    """The CLI exited or spoke in a way the protocol does not allow."""

    def __init__(self, message: str, model_name: str | None = None, model_id: str | None = None):
        super().__init__(message, status_code=502, model_name=model_name, model_id=model_id)
```

- [ ] **Step 5: Implement `versions.py`**

```python
"""CLI versions this release was tested against."""

from __future__ import annotations

import re
import subprocess
import warnings

from agno_cli_models._env import clean_env

SUPPORTED: dict[str, tuple[str, ...]] = {"claude": ("2.1.286",), "codex": ("0.155.1",)}
_VERSION = re.compile(r"\b(\d+\.\d+\.\d+)\b")


class UnsupportedCliVersionWarning(UserWarning):
    pass


def parse_version(text: str) -> str | None:
    match = _VERSION.search(text or "")
    return match.group(1) if match else None


def installed_version(binary: str) -> str | None:
    try:
        done = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL, env=clean_env())
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_version(done.stdout) if done.returncode == 0 else None


def check_supported(cli: str, version: str | None) -> bool:
    if version in SUPPORTED.get(cli, ()):
        return True
    warnings.warn(
        f"{cli} CLI version {version!r} is not in the tested set {SUPPORTED.get(cli)}; behavior may differ",
        UnsupportedCliVersionWarning,
        stacklevel=2,
    )
    return False
```

- [ ] **Step 6: Run the tests and watch them pass**

Run: `.venv/bin/pytest tests/test_common.py tests/test_versions.py -v`
Expected: 17 passed.

- [ ] **Step 7: Commit**

```bash
git add . && git commit -q -m "Shared helpers, typed errors and CLI version checks"
```

---

### Task 3: CliModel base (Agno entry points, timeout, sync, metrics)

**Files:**
- Create: `src/agno_cli_models/_base.py`, `tests/test_base.py`

**Interfaces:**
- Consumes: `run_sync`, `session_marker` from Task 2; `CliTimeoutError` from Task 2.
- Produces:

```python
@dataclass
class CliModel(Model):
    cwd: str | None = None
    timeout_s: float = 600.0
    last_run_info: dict = field(default_factory=dict, repr=False)
    CLI: ClassVar[str] = ""          # "claude" or "codex"
    def config_fingerprint(self) -> str                       # subclasses implement
    async def _drive(self, messages, response_format, tools, tool_call_limit, run_response, stream: bool) -> AsyncIterator[ModelResponse]   # subclasses implement
    def resolved_cwd(self) -> str     # self.cwd, or a private empty directory
    def usage_event(self, metrics: MessageMetrics, content: str, info: dict) -> ModelResponse
```

Contract for subclasses: `_drive` yields content deltas (`ModelResponse(content=...)`), Agno tool events from the bridge, and exactly one final `usage_event(...)`. `info` must contain `observed_model`, `cli_version`, `cli_session_id`; the base adds `config_fingerprint` and `cli`, stores it in `last_run_info`, sets `run_response.model_provider_data["agno_cli_models"]`, and puts `session_marker(...)` on the final assistant message so Agno persists the session id. A paused run (empty final content) appends no assistant message: the subclass puts the marker on the assistant tool-call message through `ToolBridge.pause(..., provider_data=...)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_base.py`:

```python
import asyncio
from dataclasses import dataclass

import pytest
from agno.metrics import MessageMetrics
from agno.models.message import Message
from agno.models.response import ModelResponse
from pydantic import BaseModel

from agno_cli_models._base import CliModel
from agno_cli_models._common import find_cli_session
from agno_cli_models.errors import CliTimeoutError


class City(BaseModel):
    city: str


@dataclass
class Scripted(CliModel):
    id: str = "scripted"
    CLI = "claude"
    final: str = "done"
    delay: float = 0.0

    def config_fingerprint(self) -> str:
        return "f" * 64

    async def _drive(self, messages, response_format, tools, tool_call_limit, run_response, stream):
        await asyncio.sleep(self.delay)
        yield ModelResponse(content="do")
        yield ModelResponse(content="ne")
        m = MessageMetrics()
        m.input_tokens, m.output_tokens = 10, 2
        yield self.usage_event(m, self.final, {"observed_model": "m-1", "cli_version": "2.1.286", "cli_session_id": "sess-1"})


class FakeRun:
    session_id = "agno-1"
    model_provider_data = None
    metrics = None
    requirements = None


def test_aresponse_returns_final_content_and_marks_session():
    msgs = [Message(role="user", content="hi")]
    run = FakeRun()
    out = asyncio.run(Scripted().aresponse(msgs, run_response=run))
    assert out.content == "done"
    assert msgs[-1].role == "assistant" and msgs[-1].content == "done"
    assert find_cli_session(msgs, "claude") == "sess-1"
    info = run.model_provider_data["agno_cli_models"]
    assert info["observed_model"] == "m-1" and info["config_fingerprint"] == "f" * 64 and info["cli"] == "claude"


def test_structured_output_is_parsed():
    out = asyncio.run(Scripted(final='{"city": "Oslo"}').aresponse([Message(role="user", content="q")], response_format=City))
    assert out.parsed == City(city="Oslo")


def test_stream_yields_deltas_and_records_message():
    msgs = [Message(role="user", content="hi")]

    async def collect():
        return [e async for e in Scripted().aresponse_stream(msgs)]

    events = asyncio.run(collect())
    assert "".join(e.content or "" for e in events) == "done"
    assert msgs[-1].content == "done"
    assert find_cli_session(msgs, "claude") == "sess-1"


def test_aresponse_times_out():
    with pytest.raises(CliTimeoutError):
        asyncio.run(Scripted(delay=5, timeout_s=0.2).aresponse([Message(role="user", content="hi")]))


def test_sync_response_works_inside_running_loop():
    async def outer():
        return Scripted().response([Message(role="user", content="hi")])

    assert asyncio.run(outer()).content == "done"


def test_empty_final_content_appends_no_assistant_message():
    msgs = [Message(role="user", content="hi")]
    asyncio.run(Scripted(final="").aresponse(msgs))
    assert [m.role for m in msgs] == ["user"]


def test_resolved_cwd_defaults_to_private_empty_dir(tmp_path):
    assert Scripted(cwd=str(tmp_path)).resolved_cwd() == str(tmp_path)
    default = Scripted().resolved_cwd()
    assert "agno-cli-models" in default
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_base.py -v`
Expected: collection error, `agno_cli_models._base` not found.

- [ ] **Step 3: Implement `_base.py`**

```python
"""Agno Model plumbing shared by both CLI models.

The CLI owns the whole tool loop, so Agno's provider hooks (invoke,
_parse_provider_response, ...) are never called; aresponse and
aresponse_stream are overridden instead.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, ClassVar, Iterator

from agno.metrics import MessageMetrics, accumulate_model_metrics
from agno.models.base import Model
from agno.models.message import Message
from agno.models.response import ModelResponse, ModelResponseEvent
from agno.run.requirement import RunRequirement
from pydantic import BaseModel

from agno_cli_models._common import run_sync, session_marker
from agno_cli_models.errors import CliTimeoutError

USAGE = "_agno_cli_models_usage"
DEFAULT_CWD = Path.home() / ".cache" / "agno-cli-models" / "empty"


@dataclass
class CliModel(Model):
    supports_native_structured_outputs: bool = True
    cwd: str | None = None
    timeout_s: float = 600.0
    last_run_info: dict = field(default_factory=dict, repr=False)
    CLI: ClassVar[str] = ""

    # Unused provider hooks: the loop lives in the CLI.
    def invoke(self, *args, **kwargs):  # type: ignore[override]
        raise NotImplementedError

    async def ainvoke(self, *args, **kwargs):  # type: ignore[override]
        raise NotImplementedError

    def invoke_stream(self, *args, **kwargs):  # type: ignore[override]
        raise NotImplementedError

    def ainvoke_stream(self, *args, **kwargs):  # type: ignore[override]
        raise NotImplementedError

    def _parse_provider_response(self, response: Any, **kwargs) -> ModelResponse:
        raise NotImplementedError

    def _parse_provider_response_delta(self, response: Any) -> ModelResponse:
        raise NotImplementedError

    # Subclass contract.
    def config_fingerprint(self) -> str:
        raise NotImplementedError

    def _drive(self, messages, response_format, tools, tool_call_limit, run_response, stream: bool) -> AsyncIterator[ModelResponse]:
        raise NotImplementedError

    def resolved_cwd(self) -> str:
        if self.cwd:
            return self.cwd
        DEFAULT_CWD.mkdir(parents=True, exist_ok=True)
        return str(DEFAULT_CWD)

    def usage_event(self, metrics: MessageMetrics, content: str, info: dict) -> ModelResponse:
        return ModelResponse(event=USAGE, response_usage=metrics, content=content, provider_data=info)

    # Shared machinery.
    async def _timed(self, gen: AsyncIterator[ModelResponse]) -> AsyncIterator[ModelResponse]:
        try:
            async with asyncio.timeout(self.timeout_s):
                async for ev in gen:
                    yield ev
        except TimeoutError as exc:
            raise CliTimeoutError(f"{self.CLI} gave no complete answer within {self.timeout_s}s", self.name, self.id) from exc
        finally:
            await gen.aclose()

    def _finish(self, ev: ModelResponse, messages: list[Message], content: str, run_response: Any) -> None:
        info = dict(ev.provider_data or {})
        info.update(cli=self.CLI, config_fingerprint=self.config_fingerprint())
        self.last_run_info = info
        if run_response is not None:
            if ev.response_usage is not None and getattr(run_response, "metrics", None) is not None:
                accumulate_model_metrics(ModelResponse(response_usage=ev.response_usage), self, self.model_type, run_response.metrics)
            data = dict(run_response.model_provider_data or {})
            data["agno_cli_models"] = info
            run_response.model_provider_data = data
        # A paused run ends with no answer; its session marker already sits on the
        # assistant tool-call message, so no empty assistant message is added.
        if content:
            marker = session_marker(self.CLI, info["cli_session_id"]) if info.get("cli_session_id") else None
            messages.append(Message(role="assistant", content=content, provider_data=marker))

    @staticmethod
    def _track_pause(ev: ModelResponse, run_response: Any) -> None:
        if ev.event == ModelResponseEvent.tool_call_paused.value and run_response is not None and ev.tool_executions:
            if run_response.requirements is None:
                run_response.requirements = []
            run_response.requirements.append(RunRequirement(tool_execution=ev.tool_executions[-1]))

    async def aresponse(  # type: ignore[override]
        self, messages: list[Message], response_format: Any = None, tools: list | None = None,
        tool_choice: Any = None, tool_call_limit: int | None = None, run_response: Any = None, **kwargs: Any,
    ) -> ModelResponse:
        out = ModelResponse(content="")
        gen = self._drive(messages, response_format, tools, tool_call_limit, run_response, False)
        async for ev in self._timed(gen):
            if ev.event == USAGE:
                out.content = ev.content or ""
                out.response_usage = ev.response_usage
                self._finish(ev, messages, out.content, run_response)
                continue
            if ev.event in (ModelResponseEvent.tool_call_completed.value, ModelResponseEvent.tool_call_paused.value):
                out.tool_executions = (out.tool_executions or []) + list(ev.tool_executions or [])
                self._track_pause(ev, run_response)
            if ev.updated_session_state is not None:
                out.updated_session_state = ev.updated_session_state
        if isinstance(response_format, type) and issubclass(response_format, BaseModel) and out.content:
            try:
                out.parsed = response_format.model_validate_json(out.content)
            except Exception:
                pass
        return out

    async def aresponse_stream(  # type: ignore[override]
        self, messages: list[Message], response_format: Any = None, tools: list | None = None,
        tool_choice: Any = None, tool_call_limit: int | None = None, stream_model_response: bool = True,
        run_response: Any = None, **kwargs: Any,
    ) -> AsyncIterator[ModelResponse]:
        streamed = ""
        gen = self._drive(messages, response_format, tools, tool_call_limit, run_response, True)
        async for ev in self._timed(gen):
            if ev.event == USAGE:
                final = ev.content or ""
                if not streamed and final:
                    streamed = final
                    yield ModelResponse(content=final)
                self._finish(ev, messages, streamed or final, run_response)
                continue
            if ev.event == ModelResponseEvent.assistant_response.value and ev.content:
                streamed += ev.content
            self._track_pause(ev, run_response)
            yield ev

    def response(self, *args: Any, **kwargs: Any) -> ModelResponse:  # type: ignore[override]
        return run_sync(self.aresponse(*args, **kwargs))

    def response_stream(self, *args: Any, **kwargs: Any) -> Iterator[ModelResponse]:  # type: ignore[override]
        async def collect() -> list[ModelResponse]:
            return [ev async for ev in self.aresponse_stream(*args, **kwargs)]

        yield from run_sync(collect())
```

- [ ] **Step 4: Run and watch them pass**

Run: `.venv/bin/pytest tests/test_base.py -v`
Expected: 7 passed. If `test_stream_yields_deltas_and_records_message` fails because Agno's `ModelResponse` default `event` is not `assistant_response`, check `ModelResponse().event` and keep deltas counted by whatever that default value is; the test asserts only the visible text.

- [ ] **Step 5: Commit**

```bash
.venv/bin/pytest -q
git add . && git commit -q -m "CliModel base: Agno entry points, timeout, sync wrappers, run info"
```

---

### Task 4: ToolBridge (Agno tool execution and pauses)

**Files:**
- Create: `src/agno_cli_models/_bridge.py`, `tests/test_bridge.py`

**Interfaces:**
- Consumes: `canon_args`, `text_of` from Task 2; `CliModel` from Task 3 (tests use a minimal concrete subclass).
- Produces:

```python
class ToolBridge:
    def __init__(self, model: Model, tools: list | None, messages: list[Message], tool_call_limit: int | None) -> None
    functions: dict[str, Function]
    def needs_pause(self, name: str) -> bool
    def precomputed(self, call_id: str) -> tuple[str, bool] | None
    async def run(self, call_id: str, name: str, args: dict, provider_data: dict | None = None) -> tuple[list[ModelResponse], str, bool]
    async def pause(self, call_id: str, name: str, args: dict, provider_data: dict | None = None) -> list[ModelResponse]
```

`run` appends one assistant message carrying the tool call (with `provider_data`) and the tool result messages to `messages`, exactly as Agno's own loop does. `pause` appends the assistant tool-call message and returns Agno's `tool_call_paused` events without running the tool.

- [ ] **Step 1: Write the failing tests**

`tests/test_bridge.py`:

```python
import asyncio

from agno.models.message import Message
from agno.models.response import ModelResponseEvent
from agno.tools import tool
from agno.tools.function import Function

from dataclasses import dataclass

from agno_cli_models._base import CliModel
from agno_cli_models._bridge import ToolBridge


@dataclass
class Dummy(CliModel):
    id: str = "dummy"
    CLI = "claude"

CALLS = []


def add(a: int, b: int) -> int:
    """Add two numbers.

    Args:
        a: first
        b: second
    """
    CALLS.append((a, b))
    return a + b


@tool(requires_confirmation=True)
def wipe(path: str) -> str:
    """Delete a path.

    Args:
        path: what to delete
    """
    CALLS.append(("wipe", path))
    return "wiped"


def bridge(messages=None, limit=None):
    functions = [Function.from_callable(add), wipe]
    for f in functions:
        f.process_entrypoint()
    return ToolBridge(Dummy(), functions, messages if messages is not None else [], limit)


def test_run_executes_through_agno_and_records_messages():
    CALLS.clear()
    msgs = []
    events, text, ok = asyncio.run(bridge(msgs).run("call-1", "add", {"a": 2, "b": 3}, provider_data={"k": "v"}))
    assert (text, ok) == ("5", True)
    assert CALLS == [(2, 3)]
    assert msgs[0].role == "assistant" and msgs[0].tool_calls[0]["id"] == "call-1"
    assert msgs[0].provider_data == {"k": "v"}
    assert msgs[1].role == "tool" and msgs[1].tool_call_id == "call-1"
    assert any(e.event == ModelResponseEvent.tool_call_completed.value for e in events)


def test_unknown_tool_reports_failure_without_raising():
    events, text, ok = asyncio.run(bridge().run("c", "nope", {}))
    assert ok is False and "unknown tool" in text and events == []


def test_needs_pause():
    b = bridge()
    assert b.needs_pause("wipe") is True
    assert b.needs_pause("add") is False
    assert b.needs_pause("nope") is False


def test_pause_emits_paused_event_without_running_the_tool():
    CALLS.clear()
    msgs = []
    events = asyncio.run(bridge(msgs).pause("call-9", "wipe", {"path": "/tmp/x"}))
    assert CALLS == []
    assert any(e.event == ModelResponseEvent.tool_call_paused.value for e in events)
    assert msgs[0].tool_calls[0]["id"] == "call-9"


def test_precomputed_results_come_from_continue_run_messages():
    msgs = [Message(role="tool", tool_call_id="call-9", content="wiped", tool_call_error=False),
            Message(role="tool", tool_call_id="call-8", content="denied", tool_call_error=True)]
    b = bridge(msgs)
    assert b.precomputed("call-9") == ("wiped", True)
    assert b.precomputed("call-8") == ("denied", False)
    assert b.precomputed("call-7") is None


def test_tool_call_limit_counts_across_calls():
    b = bridge(limit=1)
    asyncio.run(b.run("c1", "add", {"a": 1, "b": 1}))
    _, text, ok = asyncio.run(b.run("c2", "add", {"a": 1, "b": 1}))
    assert ok is False or "limit" in text.lower()
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_bridge.py -v`
Expected: collection error, `agno_cli_models._bridge` not found.

- [ ] **Step 3: Implement `_bridge.py`**

```python
"""Run CLI tool calls through Agno's own executor.

Both CLIs call our tools by name with JSON arguments. Routing each call
through `Model.arun_function_calls` keeps Agno's hooks, tool-call limits,
events and human-approval pauses identical to any other Agno model.
"""

from __future__ import annotations

import json
from typing import Any

from agno.models.base import Model
from agno.models.message import Message
from agno.models.response import ModelResponse
from agno.tools.function import Function
from agno.utils.tools import get_function_call_for_tool_call

from agno_cli_models._common import text_of


class ToolBridge:
    def __init__(self, model: Model, tools: list | None, messages: list[Message], tool_call_limit: int | None) -> None:
        self.model = model
        self.functions: dict[str, Function] = {t.name: t for t in (tools or []) if isinstance(t, Function)}
        self.messages = messages
        self.tool_call_limit = tool_call_limit
        self.count = 0
        self._done = {m.tool_call_id: m for m in messages if m.role == "tool" and m.tool_call_id}

    def needs_pause(self, name: str) -> bool:
        fn = self.functions.get(name)
        return bool(fn and (fn.requires_confirmation or fn.requires_user_input or fn.external_execution))

    def precomputed(self, call_id: str) -> tuple[str, bool] | None:
        msg = self._done.get(call_id)
        if msg is None:
            return None
        return text_of(msg.content), not bool(msg.tool_call_error)

    def _call(self, call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}

    async def run(self, call_id: str, name: str, args: dict[str, Any], provider_data: dict | None = None) -> tuple[list[ModelResponse], str, bool]:
        call = self._call(call_id, name, args)
        fc = get_function_call_for_tool_call(call, self.functions)
        if fc is None:
            return [], f"unknown tool {name}", False
        results: list[Message] = []
        events: list[ModelResponse] = []
        async for ev in self.model.arun_function_calls(
            [fc], results, current_function_call_count=self.count, function_call_limit=self.tool_call_limit
        ):
            events.append(ev)
        self.count += len(results)
        self.messages.append(Message(role="assistant", tool_calls=[call], provider_data=provider_data))
        self.messages.extend(results)
        res = results[0] if results else None
        return events, text_of(res.content) if res else "", not bool(res and res.tool_call_error)

    async def pause(self, call_id: str, name: str, args: dict[str, Any], provider_data: dict | None = None) -> list[ModelResponse]:
        call = self._call(call_id, name, args)
        fc = get_function_call_for_tool_call(call, self.functions)
        if fc is None:
            return []
        self.messages.append(Message(role="assistant", tool_calls=[call], provider_data=provider_data))
        results: list[Message] = []
        return [ev async for ev in self.model.arun_function_calls([fc], results)]
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `.venv/bin/pytest tests/test_bridge.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add . && git commit -q -m "ToolBridge: CLI tool calls run through Agno's executor"
```

---

### Task 5: Claude options and fingerprint

**Files:**
- Create: `src/agno_cli_models/claude/__init__.py` (empty), `src/agno_cli_models/claude/options.py`, `tests/test_claude_options.py`

**Interfaces:**
- Consumes: `blanking_overrides` (Task 1), `config_hash` (Task 2).
- Produces:

```python
ISOLATION_SETTINGS: dict
SERVER: str = "agno"
def fingerprint(builtin_tools: Sequence[str], permission_mode: str | None) -> str
def build_options(*, model_id: str, effort: str, cli_path: str, cwd: str, system_prompt: str,
                  builtin_tools: Sequence[str], permission_mode: str | None, agno_tool_names: Sequence[str],
                  mcp_server: Any | None, output_schema: dict | None, resume: str | None, stream: bool,
                  hooks: dict | None, max_turns: int | None) -> claude_agent_sdk.ClaudeAgentOptions
```

- [ ] **Step 1: Write the failing tests**

`tests/test_claude_options.py`:

```python
import json

import pytest

from agno_cli_models.claude.options import ISOLATION_SETTINGS, build_options, fingerprint


def opts(**over):
    base = dict(model_id="claude-opus-5-5", effort="high", cli_path="/usr/bin/claude", cwd="/work", system_prompt="S",
                builtin_tools=(), permission_mode=None, agno_tool_names=(), mcp_server=None, output_schema=None,
                resume=None, stream=False, hooks=None, max_turns=20)
    base.update(over)
    return build_options(**base)


def test_isolation_is_always_on(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk")
    o = opts()
    assert o.setting_sources == []
    assert o.strict_mcp_config is True
    assert json.loads(o.settings) == ISOLATION_SETTINGS
    assert ISOLATION_SETTINGS == {"disableClaudeAiConnectors": True, "autoMemoryEnabled": False}
    assert "disable-slash-commands" in o.extra_args
    assert o.env["ANTHROPIC_API_KEY"] == ""
    assert o.tools == []
    assert o.cli_path == "/usr/bin/claude"


def test_model_effort_cwd_are_pinned():
    o = opts()
    assert (o.model, o.effort, str(o.cwd), o.max_turns) == ("claude-opus-5-5", "high", "/work", 20)


def test_agno_tools_are_allowed_through_the_agno_server():
    o = opts(builtin_tools=("Read",), agno_tool_names=("add",), mcp_server=object())
    assert o.tools == ["Read"]
    assert o.allowed_tools == ["Read", "mcp__agno__add"]
    assert "agno" in o.mcp_servers


def test_output_schema_and_resume():
    o = opts(output_schema={"type": "object"}, resume="sess-1", stream=True)
    assert o.output_format == {"type": "json_schema", "schema": {"type": "object"}}
    assert o.resume == "sess-1"
    assert o.include_partial_messages is True


@pytest.mark.parametrize("mode", ["bypassPermissions"])
def test_dangerous_permission_mode_is_refused(mode):
    with pytest.raises(ValueError):
        opts(permission_mode=mode)


def test_fingerprint_tracks_tools_and_mode():
    assert fingerprint(("Read",), None) == fingerprint(("Read",), None)
    assert fingerprint(("Read",), None) != fingerprint(("Read", "Edit"), None)
    assert fingerprint(("Edit",), None) != fingerprint(("Edit",), "acceptEdits")
    assert len(fingerprint((), None)) == 64
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_claude_options.py -v`
Expected: collection error, module not found.

- [ ] **Step 3: Implement `claude/options.py`**

```python
"""ClaudeAgentOptions with isolation always on.

Measured on Claude Code 2.1.286: without these settings a session sees the
user's claude.ai connectors, settings, memory and project context.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

import claude_agent_sdk as sdk

from agno_cli_models._common import config_hash
from agno_cli_models._env import blanking_overrides

SERVER = "agno"
ISOLATION_SETTINGS = {"disableClaudeAiConnectors": True, "autoMemoryEnabled": False}
REFUSED_PERMISSION_MODES = ("bypassPermissions",)
ENV_POLICY = "blank-api-keys-and-claude-vars/v1"


def fingerprint(builtin_tools: Sequence[str], permission_mode: str | None) -> str:
    return config_hash({
        "cli": "claude",
        "settings": ISOLATION_SETTINGS,
        "setting_sources": [],
        "strict_mcp_config": True,
        "slash_commands": False,
        "builtin_tools": sorted(builtin_tools),
        "permission_mode": permission_mode,
        "env": ENV_POLICY,
    })


def build_options(*, model_id: str, effort: str, cli_path: str, cwd: str, system_prompt: str,
                  builtin_tools: Sequence[str], permission_mode: str | None, agno_tool_names: Sequence[str],
                  mcp_server: Any | None, output_schema: dict | None, resume: str | None, stream: bool,
                  hooks: dict | None, max_turns: int | None) -> sdk.ClaudeAgentOptions:
    if permission_mode in REFUSED_PERMISSION_MODES:
        raise ValueError(f"permission_mode {permission_mode!r} is not allowed")
    allowed = list(builtin_tools) + [f"mcp__{SERVER}__{n}" for n in agno_tool_names]
    kwargs: dict[str, Any] = dict(
        model=model_id,
        effort=effort,
        cli_path=cli_path,
        cwd=cwd,
        system_prompt=system_prompt or "",
        tools=list(builtin_tools),
        allowed_tools=allowed,
        setting_sources=[],
        strict_mcp_config=True,
        settings=json.dumps(ISOLATION_SETTINGS, sort_keys=True),
        extra_args={"disable-slash-commands": None},
        env=blanking_overrides(),
        include_partial_messages=stream,
        max_turns=max_turns,
    )
    if permission_mode:
        kwargs["permission_mode"] = permission_mode
    if hooks:
        kwargs["hooks"] = hooks
    if mcp_server is not None:
        kwargs["mcp_servers"] = {SERVER: mcp_server}
    if output_schema is not None:
        kwargs["output_format"] = {"type": "json_schema", "schema": output_schema}
    if resume:
        kwargs["resume"] = resume
    return sdk.ClaudeAgentOptions(**kwargs)
```

- [ ] **Step 4: Run and watch them pass**

Run: `.venv/bin/pytest tests/test_claude_options.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add . && git commit -q -m "Claude options with isolation always on, and config fingerprint"
```

---

### Task 6: Claude translation and call-id matching

**Files:**
- Create: `src/agno_cli_models/claude/translate.py`, `src/agno_cli_models/claude/matcher.py`, `tests/test_claude_translate.py`, `tests/test_claude_matcher.py`

**Interfaces:**
- Consumes: `canon_args` (Task 2); `ModelRateLimitError`, `ModelProviderError`, `ContextWindowExceededError` (Task 2).
- Produces:

```python
# translate.py
def usage_metrics(result: sdk.ResultMessage) -> MessageMetrics
def observed_model(result: sdk.ResultMessage) -> str | None
def check_result(result: sdk.ResultMessage, model_name: str, model_id: str) -> None   # raises on error results
def rate_limit_error(event: sdk.RateLimitEvent, model_name: str, model_id: str) -> ModelRateLimitError | None

# matcher.py
class CallIdMatcher:
    def record(self, name: str, args: Mapping | None, tool_use_id: str | None) -> str
    def take(self, name: str, args: Mapping | None) -> str
```

- [ ] **Step 1: Write the failing tests**

`tests/test_claude_translate.py`:

```python
import claude_agent_sdk as sdk
import pytest

from agno_cli_models.claude.translate import check_result, observed_model, rate_limit_error, usage_metrics
from agno_cli_models.errors import ContextWindowExceededError, ModelProviderError, ModelRateLimitError

USAGE = {
    "claude-opus-5-5": {"inputTokens": 2, "outputTokens": 748, "cacheReadInputTokens": 100, "cacheCreationInputTokens": 5873, "thinkingTokens": 40},
    "claude-haiku-4-5": {"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0},
}


def result(**over):
    base = dict(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="s1",
                total_cost_usd=0.06, model_usage=USAGE, result="ok")
    base.update(over)
    return sdk.ResultMessage(**base)


def test_usage_metrics_normalized():
    m = usage_metrics(result())
    assert m.input_tokens == 2 + 100 + 5873 + 10
    assert m.cache_read_tokens == 100
    assert m.cache_write_tokens == 5873
    assert m.output_tokens == 753
    assert m.reasoning_tokens == 40
    assert m.total_tokens == m.input_tokens + m.output_tokens
    assert m.cost == pytest.approx(0.06)


def test_observed_model_is_the_one_that_did_the_work():
    assert observed_model(result()) == "claude-opus-5-5"
    assert observed_model(result(model_usage=None)) is None


def test_check_result_passes_success():
    check_result(result(), "ClaudeCode", "claude-opus-5-5")


@pytest.mark.parametrize("over, error", [
    (dict(is_error=True, api_error_status=429, result="limit"), ModelRateLimitError),
    (dict(is_error=True, result="Claude AI usage limit reached"), ModelRateLimitError),
    (dict(is_error=True, result="prompt is too long: context window exceeded"), ContextWindowExceededError),
    (dict(is_error=True, subtype="error_during_execution", result="boom"), ModelProviderError),
])
def test_check_result_raises_typed_errors(over, error):
    with pytest.raises(error):
        check_result(result(**over), "ClaudeCode", "claude-opus-5-5")


def test_rate_limit_event_only_when_rejected():
    def ev(status):
        return sdk.RateLimitEvent(rate_limit_info=sdk.RateLimitInfo(status=status, rate_limit_type="five_hour", utilization=1.0), uuid="u", session_id="s")

    assert isinstance(rate_limit_error(ev("rejected"), "ClaudeCode", "x"), ModelRateLimitError)
    assert rate_limit_error(ev("allowed_warning"), "ClaudeCode", "x") is None
    assert rate_limit_error(ev("allowed"), "ClaudeCode", "x") is None
```

`tests/test_claude_matcher.py`:

```python
from agno_cli_models.claude.matcher import CallIdMatcher


def test_matcher_pairs_by_arguments_not_order():
    m = CallIdMatcher()
    m.record("add", {"a": 1}, "id-A")
    m.record("add", {"a": 2}, "id-B")
    assert m.take("add", {"a": 2}) == "id-B"
    assert m.take("add", {"a": 1}) == "id-A"


def test_same_arguments_fall_back_to_order():
    m = CallIdMatcher()
    m.record("add", {"a": 1}, "id-1")
    m.record("add", {"a": 1}, "id-2")
    assert [m.take("add", {"a": 1}), m.take("add", {"a": 1})] == ["id-1", "id-2"]


def test_unrecorded_call_gets_a_fresh_id():
    m = CallIdMatcher()
    assert m.take("add", {}) != m.take("add", {})


def test_missing_tool_use_id_is_generated():
    m = CallIdMatcher()
    rid = m.record("add", {}, None)
    assert rid and m.take("add", {}) == rid
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_claude_translate.py tests/test_claude_matcher.py -v`
Expected: collection errors.

- [ ] **Step 3: Implement `claude/translate.py`**

```python
"""Claude Agent SDK messages to Agno metrics and typed errors."""

from __future__ import annotations

import re

import claude_agent_sdk as sdk
from agno.metrics import MessageMetrics

from agno_cli_models.errors import ContextWindowExceededError, ModelProviderError, ModelRateLimitError

_RATE = re.compile(r"rate.?limit|usage limit|too many requests|\b429\b", re.IGNORECASE)
_CONTEXT = re.compile(r"context (window|length)|prompt is too long", re.IGNORECASE)


def usage_metrics(result: sdk.ResultMessage) -> MessageMetrics:
    usage = result.model_usage or {}
    m = MessageMetrics()
    m.cache_read_tokens = sum(u.get("cacheReadInputTokens", 0) for u in usage.values())
    m.cache_write_tokens = sum(u.get("cacheCreationInputTokens", 0) for u in usage.values())
    m.input_tokens = sum(u.get("inputTokens", 0) for u in usage.values()) + m.cache_read_tokens + m.cache_write_tokens
    m.output_tokens = sum(u.get("outputTokens", 0) for u in usage.values())
    m.reasoning_tokens = sum(u.get("thinkingTokens", 0) for u in usage.values())
    m.total_tokens = m.input_tokens + m.output_tokens
    m.cost = result.total_cost_usd
    return m


def observed_model(result: sdk.ResultMessage) -> str | None:
    usage = result.model_usage or {}
    if not usage:
        return None
    return max(usage, key=lambda k: usage[k].get("outputTokens", 0))


def check_result(result: sdk.ResultMessage, model_name: str, model_id: str) -> None:
    if not result.is_error:
        return
    text = f"{result.subtype} {result.api_error_status} {result.result} {result.errors}"
    if result.api_error_status == 429 or _RATE.search(text):
        raise ModelRateLimitError(text[:500], model_name=model_name, model_id=model_id)
    if _CONTEXT.search(text):
        raise ContextWindowExceededError(text[:500], model_name=model_name, model_id=model_id)
    raise ModelProviderError(text[:500], model_name=model_name, model_id=model_id)


def rate_limit_error(event: sdk.RateLimitEvent, model_name: str, model_id: str) -> ModelRateLimitError | None:
    info = event.rate_limit_info
    if info.status != "rejected":
        return None
    return ModelRateLimitError(f"rate limit {info.rate_limit_type} rejected (resets {info.resets_at})",
                               model_name=model_name, model_id=model_id)
```

If `ContextWindowExceededError` has a different constructor than `(message, model_name=, model_id=)`, check `inspect.signature(agno.exceptions.ContextWindowExceededError.__init__)` and match it; the test only asserts the type.

- [ ] **Step 4: Implement `claude/matcher.py`**

```python
"""Pair the SDK hook's tool_use_id with the tool handler call.

The in-process MCP handler does not receive the tool_use_id, but the
PreToolUse hook does, with the same arguments. Pairing by (name, arguments)
keeps parallel calls to one tool apart; order is the fallback only for
identical arguments.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Mapping
from uuid import uuid4

from agno_cli_models._common import canon_args


class CallIdMatcher:
    def __init__(self) -> None:
        self._ids: dict[tuple[str, str], deque[str]] = defaultdict(deque)

    def record(self, name: str, args: Mapping | None, tool_use_id: str | None) -> str:
        call_id = tool_use_id or str(uuid4())
        self._ids[(name, canon_args(args))].append(call_id)
        return call_id

    def take(self, name: str, args: Mapping | None) -> str:
        queue = self._ids.get((name, canon_args(args)))
        return queue.popleft() if queue else str(uuid4())
```

- [ ] **Step 5: Run and watch them pass**

Run: `.venv/bin/pytest tests/test_claude_translate.py tests/test_claude_matcher.py -v`
Expected: 13 passed.

- [ ] **Step 6: Commit**

```bash
git add . && git commit -q -m "Claude translation (metrics, observed model, typed errors) and call-id matcher"
```

---

### Task 7: ClaudeCodeModel engine

**Files:**
- Create: `src/agno_cli_models/claude/model.py`, `tests/test_claude_model.py`

**Interfaces:**
- Consumes: `CliModel` (Task 3), `ToolBridge` (Task 4), `build_options`, `fingerprint`, `SERVER` (Task 5), `usage_metrics`, `observed_model`, `check_result`, `rate_limit_error`, `CallIdMatcher` (Task 6), `split_system`, `transcript_prompt`, `last_user_text`, `find_cli_session`, `session_marker` (Task 2), `installed_version`, `check_supported` (Task 2).
- Produces:

```python
@dataclass
class ClaudeCodeModel(CliModel):
    id: str = "claude-opus-5-5"
    effort: str = "high"
    builtin_tools: tuple[str, ...] = ()       # native Claude Code tools, e.g. ("Read", "Grep", "Glob", "Edit", "Bash")
    permission_mode: str | None = None        # e.g. "acceptEdits" for working roles; never "bypassPermissions"
    max_turns: int | None = 50
    cli_path: str | None = None               # default: shutil.which("claude")
    query_fn: Callable | None = None          # default: claude_agent_sdk.query; injectable for tests
    CLI = "claude"
```

Behavior:
- Session: `resume = find_cli_session(messages, "claude")`. With a resume id the prompt is the last user message, or `"Continue."` when the last message is a tool result. Without one, the prompt is `transcript_prompt(rest)`.
- The CLI version is read once per instance with `installed_version(cli_path)` and checked with `check_supported`.
- Rate-limit events with status `rejected` raise `ModelRateLimitError` immediately.
- A `ResultMessage` with `deferred_tool_use` produces bridge pause events (with the session marker on the assistant tool-call message) instead of a final answer.

- [ ] **Step 1: Write the failing tests**

`tests/test_claude_model.py`:

```python
import asyncio
import json

import claude_agent_sdk as sdk
import pytest
from agno.models.message import Message
from agno.models.response import ModelResponseEvent
from agno.tools import tool

from agno_cli_models._common import find_cli_session, session_marker
from agno_cli_models.claude.model import ClaudeCodeModel
from agno_cli_models.errors import ModelRateLimitError

INIT = sdk.SystemMessage(subtype="init", data={"session_id": "sess-1", "claude_code_version": "2.1.286", "tools": [], "apiKeySource": "none"})


def result(**over):
    base = dict(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="sess-1",
                total_cost_usd=0.01, result="hello", model_usage={"claude-opus-5-5": {"inputTokens": 5, "outputTokens": 3}})
    base.update(over)
    return sdk.ResultMessage(**base)


class FakeQuery:
    def __init__(self, *items):
        self.items = items
        self.calls = []

    def __call__(self, *, prompt, options):
        self.calls.append((prompt, options))
        items = self.items

        async def gen():
            for item in items:
                yield item

        return gen()


def model(fake, **over):
    return ClaudeCodeModel(query_fn=fake, cli_path="claude-test", **over)


@pytest.fixture(autouse=True)
def pinned_version(monkeypatch):
    monkeypatch.setattr("agno_cli_models.claude.model.installed_version", lambda path: "2.1.286")


def test_plain_answer_and_run_info():
    fake = FakeQuery(INIT, result())
    m = model(fake)
    msgs = [Message(role="system", content="SYS"), Message(role="user", content="hi")]
    out = asyncio.run(m.aresponse(msgs))
    assert out.content == "hello"
    prompt, options = fake.calls[0]
    assert prompt == "hi" and options.system_prompt == "SYS" and options.resume is None
    assert m.last_run_info["observed_model"] == "claude-opus-5-5"
    assert m.last_run_info["cli_version"] == "2.1.286"
    assert find_cli_session(msgs, "claude") == "sess-1"


def test_no_history_means_fresh_session():
    fake = FakeQuery(INIT, result())
    asyncio.run(model(fake).aresponse([Message(role="user", content="first")]))
    assert fake.calls[0][1].resume is None


def test_resume_uses_persisted_session_and_sends_only_new_message():
    fake = FakeQuery(INIT, result())
    msgs = [Message(role="user", content="q1"),
            Message(role="assistant", content="a1", provider_data=session_marker("claude", "sess-0")),
            Message(role="user", content="q2")]
    asyncio.run(model(fake).aresponse(msgs))
    prompt, options = fake.calls[0]
    assert options.resume == "sess-0" and prompt == "q2"


def test_history_without_session_is_replayed():
    fake = FakeQuery(INIT, result())
    msgs = [Message(role="user", content="q1"), Message(role="assistant", content="a1"), Message(role="user", content="q2")]
    asyncio.run(model(fake).aresponse(msgs))
    assert fake.calls[0][0].startswith("Conversation so far:")


def test_structured_output_wins_over_text():
    fake = FakeQuery(INIT, result(structured_output={"city": "Oslo"}, result="ignored"))
    out = asyncio.run(model(fake).aresponse([Message(role="user", content="q")], response_format={"type": "object"}))
    assert json.loads(out.content) == {"city": "Oslo"}


def test_rejected_rate_limit_event_raises():
    ev = sdk.RateLimitEvent(rate_limit_info=sdk.RateLimitInfo(status="rejected", rate_limit_type="five_hour"), uuid="u", session_id="s")
    with pytest.raises(ModelRateLimitError):
        asyncio.run(model(FakeQuery(INIT, ev, result())).aresponse([Message(role="user", content="q")]))


def test_error_result_raises():
    with pytest.raises(ModelRateLimitError):
        asyncio.run(model(FakeQuery(INIT, result(is_error=True, api_error_status=429))).aresponse([Message(role="user", content="q")]))


def test_stream_deltas():
    delta = sdk.StreamEvent(uuid="u", session_id="s", event={"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hel"}})
    delta2 = sdk.StreamEvent(uuid="u", session_id="s", event={"type": "content_block_delta", "delta": {"type": "text_delta", "text": "lo"}})
    fake = FakeQuery(INIT, delta, delta2, result())

    async def collect():
        return [e async for e in model(fake).aresponse_stream([Message(role="user", content="q")])]

    events = asyncio.run(collect())
    assert "".join(e.content or "" for e in events) == "hello"
    assert fake.calls[0][1].include_partial_messages is True


@tool(requires_confirmation=True)
def wipe(path: str) -> str:
    """Delete a path.

    Args:
        path: what to delete
    """
    return "wiped"


class Deferred:
    def __init__(self):
        self.id, self.name, self.input = "tu-1", "mcp__agno__wipe", {"path": "/x"}


def test_deferred_tool_use_pauses_the_run():
    fake = FakeQuery(INIT, result(deferred_tool_use=Deferred(), result=None))
    wipe.process_entrypoint()

    class Run:
        session_id, model_provider_data, metrics, requirements = "a", None, None, None

    run = Run()
    msgs = [Message(role="user", content="delete /x")]
    out = asyncio.run(model(fake).aresponse(msgs, tools=[wipe], run_response=run))
    assert run.requirements and run.requirements[0].tool_execution.tool_name == "wipe"
    assert find_cli_session(msgs, "claude") == "sess-1"
    assert out.tool_executions


def test_unsupported_version_warns(monkeypatch):
    monkeypatch.setattr("agno_cli_models.claude.model.installed_version", lambda path: "9.9.9")
    from agno_cli_models.versions import UnsupportedCliVersionWarning

    with pytest.warns(UnsupportedCliVersionWarning):
        asyncio.run(model(FakeQuery(INIT, result())).aresponse([Message(role="user", content="q")]))


def test_fingerprint_matches_options_module():
    from agno_cli_models.claude.options import fingerprint

    m = ClaudeCodeModel(builtin_tools=("Read",))
    assert m.config_fingerprint() == fingerprint(("Read",), None)
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_claude_model.py -v`
Expected: collection error, `agno_cli_models.claude.model` not found.

- [ ] **Step 3: Implement `claude/model.py`**

```python
"""ClaudeCodeModel: an Agno Model whose tool loop runs inside Claude Code,
driven by the official Claude Agent SDK and the CLI's own login."""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

import claude_agent_sdk as sdk
from agno.models.response import ModelResponse
from pydantic import BaseModel

from agno_cli_models._base import CliModel
from agno_cli_models._bridge import ToolBridge
from agno_cli_models._common import find_cli_session, last_user_text, session_marker, split_system, transcript_prompt
from agno_cli_models.claude.matcher import CallIdMatcher
from agno_cli_models.claude.options import SERVER, build_options, fingerprint
from agno_cli_models.claude.translate import check_result, observed_model, rate_limit_error, usage_metrics
from agno_cli_models.versions import check_supported, installed_version

_DONE = object()


@dataclass
class ClaudeCodeModel(CliModel):
    id: str = "claude-opus-5-5"
    name: str = "ClaudeCode"
    provider: str = "ClaudeCode"
    effort: str = "high"
    builtin_tools: tuple[str, ...] = ()
    permission_mode: str | None = None
    max_turns: int | None = 50
    cli_path: str | None = None
    query_fn: Callable | None = field(default=None, repr=False)
    _version: str | None = field(default=None, repr=False)
    CLI = "claude"

    def config_fingerprint(self) -> str:
        return fingerprint(self.builtin_tools, self.permission_mode)

    def _cli(self) -> str:
        path = self.cli_path or shutil.which("claude")
        if not path:
            raise FileNotFoundError("claude CLI not found on PATH; install Claude Code or set cli_path")
        return path

    def _cli_version(self, path: str) -> str | None:
        if self._version is None:
            self._version = installed_version(path)
            check_supported("claude", self._version)
        return self._version

    async def _drive(self, messages, response_format, tools, tool_call_limit, run_response, stream: bool) -> AsyncIterator[ModelResponse]:
        cli = self._cli()
        version = self._cli_version(cli)
        bridge = ToolBridge(self, tools, messages, tool_call_limit)
        matcher = CallIdMatcher()
        queue: asyncio.Queue = asyncio.Queue()
        system, rest = split_system(messages)
        resume = find_cli_session(messages, "claude")
        state: dict[str, Any] = {"session": resume}

        async def pre_tool_use(inp: dict, tool_use_id: str | None, ctx: Any) -> dict:
            name = inp.get("tool_name", "")
            prefix = f"mcp__{SERVER}__"
            if not name.startswith(prefix):
                return {}
            short = name[len(prefix):]
            call_id = matcher.record(short, inp.get("tool_input"), tool_use_id)
            if bridge.needs_pause(short) and bridge.precomputed(call_id) is None:
                return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "defer"}}
            return {}

        def handler_for(fn_name: str):
            async def handler(args: dict) -> dict:
                call_id = matcher.take(fn_name, args)
                done = bridge.precomputed(call_id)
                if done is not None:
                    text, ok = done
                else:
                    marker = session_marker("claude", state["session"]) if state["session"] else None
                    events, text, ok = await bridge.run(call_id, fn_name, args, provider_data=marker)
                    for ev in events:
                        await queue.put(ev)
                return {"content": [{"type": "text", "text": text}], "is_error": not ok}

            return handler

        sdk_tools = [
            sdk.tool(fn.name, fn.description or fn.name, fn.parameters or {"type": "object", "properties": {}})(handler_for(fn.name))
            for fn in bridge.functions.values()
        ]
        schema = None
        if isinstance(response_format, type) and issubclass(response_format, BaseModel):
            schema = response_format.model_json_schema()
        elif isinstance(response_format, dict):
            schema = response_format
        options = build_options(
            model_id=self.id, effort=self.effort, cli_path=cli, cwd=self.resolved_cwd(), system_prompt=system,
            builtin_tools=self.builtin_tools, permission_mode=self.permission_mode,
            agno_tool_names=list(bridge.functions), mcp_server=sdk.create_sdk_mcp_server(SERVER, tools=sdk_tools) if sdk_tools else None,
            output_schema=schema, resume=resume, stream=stream,
            hooks={"PreToolUse": [sdk.HookMatcher(matcher=None, hooks=[pre_tool_use])]}, max_turns=self.max_turns,
        )
        if resume:
            prompt = "Continue." if rest and rest[-1].role == "tool" else last_user_text(rest)
        else:
            prompt = transcript_prompt(rest)
        resuming_after_pause = bool(resume) and bool(rest) and rest[-1].role == "tool"
        query = self.query_fn or sdk.query

        async def pump() -> None:
            gen = query(prompt=prompt, options=options)
            try:
                async for msg in gen:
                    await queue.put(msg)
            except Exception as exc:
                await queue.put(exc)
            finally:
                await gen.aclose()
                await queue.put(_DONE)

        task = asyncio.create_task(pump())
        try:
            while True:
                item = await queue.get()
                if item is _DONE:
                    return
                if isinstance(item, Exception):
                    raise item
                if isinstance(item, ModelResponse):
                    yield item
                elif isinstance(item, sdk.StreamEvent):
                    ev = item.event
                    if ev.get("type") == "content_block_delta" and ev.get("delta", {}).get("type") == "text_delta":
                        yield ModelResponse(content=ev["delta"]["text"])
                elif isinstance(item, sdk.RateLimitEvent):
                    err = rate_limit_error(item, self.name, self.id)
                    if err is not None:
                        raise err
                elif isinstance(item, sdk.SystemMessage) and item.subtype == "init":
                    state["session"] = item.data.get("session_id") or state["session"]
                elif isinstance(item, sdk.ResultMessage):
                    state["session"] = item.session_id or state["session"]
                    check_result(item, self.name, self.id)
                    info = {"observed_model": observed_model(item), "cli_version": version, "cli_session_id": state["session"]}
                    deferred = item.deferred_tool_use
                    if deferred is not None:
                        short = deferred.name.split("__")[-1]
                        for ev in await bridge.pause(deferred.id, short, deferred.input or {}, provider_data=session_marker("claude", state["session"])):
                            yield ev
                        text = ""
                    elif item.structured_output is not None:
                        text = json.dumps(item.structured_output)
                    else:
                        text = item.result or ""
                    yield self.usage_event(usage_metrics(item), text, info)
                    if resuming_after_pause or deferred is not None:
                        return
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
```

- [ ] **Step 4: Run and watch them pass**

Run: `.venv/bin/pytest tests/test_claude_model.py -v`
Expected: 11 passed. Then the whole suite: `.venv/bin/pytest -q`, all green.

- [ ] **Step 5: Commit**

```bash
git add . && git commit -q -m "ClaudeCodeModel: SDK engine with persisted sessions, pauses, typed errors"
```

---

### Task 8: Codex JSON-RPC client

**Files:**
- Create: `src/agno_cli_models/codex/__init__.py` (empty), `src/agno_cli_models/codex/rpc.py`, `tests/test_codex_rpc.py`

**Interfaces:**
- Consumes: `clean_env` (Task 1), `CliProtocolError` (Task 2).
- Produces:

```python
DONE: object                                   # sentinel put in inbox when the server's stdout closes
class Rpc:
    @classmethod
    async def spawn(cls, argv: list[str], env: dict[str, str]) -> "Rpc"
    def __init__(self, proc: asyncio.subprocess.Process) -> None
    inbox: asyncio.Queue                       # notifications and server-initiated requests, then DONE
    async def send(self, obj: dict) -> None
    async def request(self, method: str, params: dict) -> dict      # raises CliProtocolError on JSON-RPC error
    async def reply(self, request_id: Any, result: dict) -> None
    async def close(self, grace_s: float = 3.0) -> None             # terminate, then kill after grace
```

- [ ] **Step 1: Write the failing tests**

`tests/test_codex_rpc.py` drives a tiny Python "server" as a real subprocess, so the stdio handling is real:

```python
import asyncio
import sys
import textwrap

import pytest

from agno_cli_models.codex.rpc import DONE, Rpc
from agno_cli_models.errors import CliProtocolError

SERVER = textwrap.dedent("""
    import json, sys
    for line in sys.stdin:
        msg = json.loads(line)
        if msg.get("method") == "ping":
            print(json.dumps({"jsonrpc": "2.0", "method": "note", "params": {"n": 1}}), flush=True)
            print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {"pong": True}}), flush=True)
        elif msg.get("method") == "fail":
            print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -1, "message": "nope"}}), flush=True)
        elif msg.get("method") == "ask":
            print(json.dumps({"jsonrpc": "2.0", "id": 99, "method": "item/tool/call", "params": {}}), flush=True)
        elif "result" in msg and msg.get("id") == 99:
            print(json.dumps({"jsonrpc": "2.0", "method": "got-reply", "params": msg["result"]}), flush=True)
        elif msg.get("method") == "quit":
            sys.exit(0)
""")


async def server():
    return await Rpc.spawn([sys.executable, "-c", SERVER], env={"PATH": "/usr/bin"})


def test_request_response_and_notifications():
    async def go():
        rpc = await server()
        try:
            assert await rpc.request("ping", {}) == {"pong": True}
            assert (await rpc.inbox.get())["method"] == "note"
        finally:
            await rpc.close()

    asyncio.run(go())


def test_error_response_raises():
    async def go():
        rpc = await server()
        try:
            with pytest.raises(CliProtocolError):
                await rpc.request("fail", {})
        finally:
            await rpc.close()

    asyncio.run(go())


def test_server_request_and_reply():
    async def go():
        rpc = await server()
        try:
            await rpc.send({"jsonrpc": "2.0", "method": "ask"})
            req = await rpc.inbox.get()
            assert req["method"] == "item/tool/call" and req["id"] == 99
            await rpc.reply(99, {"ok": 1})
            assert (await rpc.inbox.get()) == {"jsonrpc": "2.0", "method": "got-reply", "params": {"ok": 1}}
        finally:
            await rpc.close()

    asyncio.run(go())


def test_exit_puts_done_in_inbox():
    async def go():
        rpc = await server()
        await rpc.send({"jsonrpc": "2.0", "method": "quit"})
        assert await asyncio.wait_for(rpc.inbox.get(), 5) is DONE
        await rpc.close()

    asyncio.run(go())


def test_rpc_close_kills_hung_process():
    async def go():
        rpc = await Rpc.spawn([sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"], env={"PATH": "/usr/bin"})
        await rpc.close(grace_s=0.5)
        assert rpc.proc.returncode is not None

    asyncio.run(go())
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_codex_rpc.py -v`
Expected: collection error.

- [ ] **Step 3: Implement `codex/rpc.py`**

```python
"""Minimal JSON-RPC 2.0 client over a `codex app-server` stdio subprocess."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from agno_cli_models.errors import CliProtocolError

DONE = object()


class Rpc:
    @classmethod
    async def spawn(cls, argv: list[str], env: dict[str, str]) -> "Rpc":
        proc = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, env=env, limit=16 * 1024 * 1024,
        )
        return cls(proc)

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self.proc = proc
        self.next_id = 0
        self.pending: dict[int, asyncio.Future] = {}
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        assert self.proc.stdout is not None
        try:
            while True:
                line = await self.proc.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "id" in msg and "method" not in msg and msg["id"] in self.pending:
                    self.pending.pop(msg["id"]).set_result(msg)
                else:
                    await self.inbox.put(msg)
        finally:
            for fut in self.pending.values():
                if not fut.done():
                    fut.set_exception(CliProtocolError("codex app-server exited"))
            await self.inbox.put(DONE)

    async def send(self, obj: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write((json.dumps(obj) + "\n").encode())
        await self.proc.stdin.drain()

    async def request(self, method: str, params: dict) -> dict:
        self.next_id += 1
        fut = asyncio.get_running_loop().create_future()
        self.pending[self.next_id] = fut
        await self.send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params})
        msg = await fut
        if "error" in msg:
            raise CliProtocolError(f"codex {method} failed: {msg['error']}")
        return msg.get("result", {})

    async def reply(self, request_id: Any, result: dict) -> None:
        await self.send({"jsonrpc": "2.0", "id": request_id, "result": result})

    async def close(self, grace_s: float = 3.0) -> None:
        self.reader.cancel()
        if self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), grace_s)
            except asyncio.TimeoutError:
                self.proc.kill()
                await self.proc.wait()
```

- [ ] **Step 4: Run and watch them pass**

Run: `.venv/bin/pytest tests/test_codex_rpc.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add . && git commit -q -m "Codex JSON-RPC client over app-server stdio"
```

---

### Task 9: Codex protocol builders and turn tracker

**Files:**
- Create: `src/agno_cli_models/codex/protocol.py`, `tests/test_codex_protocol.py`

**Interfaces:**
- Consumes: `config_hash`, `strict_schema` (Task 2), errors (Task 2).
- Produces:

```python
FIXED_CONFIG: list[str]                      # app-server argv overrides
PAUSE_TEXT: str
def app_server_argv(binary: str) -> list[str]
def fingerprint(sandbox: str, builtin_tools: bool) -> str
def thread_start_params(*, model_id: str, system: str, cwd: str, sandbox: str, builtin_tools: bool, dynamic_tools: list[dict]) -> dict
def thread_resume_params(*, thread_id: str, model_id: str, system: str, cwd: str, sandbox: str) -> dict
def turn_start_params(*, thread_id: str, text: str, effort: str, builtin_tools: bool, output_schema: dict | None) -> dict
def dynamic_tool(fn: Function) -> dict
def continuation_text(results: list[Message]) -> str
@dataclass
class TurnTracker:
    model_name: str; model_id: str
    model: str | None = None; final_text: str = ""; usage: dict = {}; done: bool = False; interrupted: bool = False
    def on_notification(self, method: str, params: dict) -> list[ModelResponse]   # raises typed errors
    def metrics(self) -> MessageMetrics
```

- [ ] **Step 1: Write the failing tests**

`tests/test_codex_protocol.py`:

```python
import pytest
from agno.models.message import Message

from agno_cli_models.codex.protocol import (
    TurnTracker,
    app_server_argv,
    continuation_text,
    fingerprint,
    thread_resume_params,
    thread_start_params,
    turn_start_params,
)
from agno_cli_models.errors import ContextWindowExceededError, ModelProviderError, ModelRateLimitError


def test_app_server_argv_isolates():
    argv = app_server_argv("codex")
    assert argv[:2] == ["codex", "app-server"]
    assert "features.apps=false" in argv and 'web_search="disabled"' in argv


def test_thread_start_params_pin_everything():
    p = thread_start_params(model_id="gpt-5.6-sol", system="S", cwd="/w", sandbox="read-only", builtin_tools=False, dynamic_tools=[{"name": "t"}])
    assert p["model"] == "gpt-5.6-sol" and p["baseInstructions"] == "S" and p["cwd"] == "/w"
    assert p["sandbox"] == "read-only" and p["approvalPolicy"] == "never"
    assert p["allowProviderModelFallback"] is False
    assert p["environments"] == [] and p["dynamicTools"] == [{"name": "t"}]


def test_builtin_tools_keep_the_environment():
    p = thread_start_params(model_id="m", system="", cwd="/w", sandbox="workspace-write", builtin_tools=True, dynamic_tools=[])
    assert "environments" not in p and p["sandbox"] == "workspace-write"


def test_danger_sandbox_refused():
    with pytest.raises(ValueError):
        thread_start_params(model_id="m", system="", cwd="/w", sandbox="danger-full-access", builtin_tools=True, dynamic_tools=[])


def test_resume_and_turn_params():
    r = thread_resume_params(thread_id="t1", model_id="m", system="S", cwd="/w", sandbox="read-only")
    assert r["threadId"] == "t1" and r["model"] == "m"
    t = turn_start_params(thread_id="t1", text="hi", effort="high", builtin_tools=False, output_schema={"type": "object", "properties": {"a": {"type": "string"}}})
    assert t["input"] == [{"type": "text", "text": "hi"}] and t["effort"] == "high" and t["environments"] == []
    assert t["outputSchema"]["required"] == ["a"]


def test_fingerprint():
    assert fingerprint("read-only", False) != fingerprint("workspace-write", False)
    assert fingerprint("read-only", False) != fingerprint("read-only", True)


def test_continuation_text_reports_decisions():
    text = continuation_text([Message(role="tool", tool_call_id="c1", tool_name="wipe", content="wiped"),
                              Message(role="tool", tool_call_id="c2", tool_name="drop", content="denied by user", tool_call_error=True)])
    assert "c1" in text and "wiped" in text and "c2" in text and "denied" in text


def tracker():
    return TurnTracker(model_name="Codex", model_id="gpt-5.6-sol")


def test_tracker_collects_final_answer_usage_and_model():
    t = tracker()
    t.on_notification("thread/started", {"thread": {"id": "t1"}, "model": "gpt-5.6-sol"})
    assert t.on_notification("item/started", {"item": {"id": "i1", "type": "agentMessage", "phase": "final_answer"}}) == []
    deltas = t.on_notification("item/agentMessage/delta", {"itemId": "i1", "delta": "hel"})
    assert deltas[0].content == "hel"
    t.on_notification("item/completed", {"item": {"id": "i1", "type": "agentMessage", "phase": "final_answer", "text": "hello"}})
    t.on_notification("thread/tokenUsage/updated", {"tokenUsage": {"last": {"inputTokens": 100, "cachedInputTokens": 40, "outputTokens": 7, "reasoningOutputTokens": 3}}})
    t.on_notification("turn/completed", {"turn": {"status": "completed"}})
    assert t.done and t.final_text == "hello"
    m = t.metrics()
    assert (m.input_tokens, m.cache_read_tokens, m.output_tokens, m.reasoning_tokens, m.total_tokens) == (100, 40, 7, 3, 107)


def test_reroute_changes_observed_model():
    t = tracker()
    t.model = "gpt-5.6-sol"
    t.on_notification("model/rerouted", {"fromModel": "gpt-5.6-sol", "toModel": "gpt-5.6-mini", "reason": "x", "threadId": "t", "turnId": "u"})
    assert t.model == "gpt-5.6-mini"


@pytest.mark.parametrize("info, error", [
    ("usageLimitExceeded", ModelRateLimitError),
    ("rateLimitExceeded", ModelRateLimitError),
    ("contextWindowExceeded", ContextWindowExceededError),
    ("internalServerError", ModelProviderError),
])
def test_failed_turn_raises_typed_errors(info, error):
    with pytest.raises(error):
        tracker().on_notification("turn/completed", {"turn": {"status": "failed", "error": {"message": "x", "codexErrorInfo": info}}})


def test_interrupted_turn_is_not_an_error():
    t = tracker()
    t.on_notification("turn/completed", {"turn": {"status": "interrupted"}})
    assert t.done and t.interrupted


def test_error_notification_only_raises_when_final():
    t = tracker()
    assert t.on_notification("error", {"error": {"message": "retrying"}, "willRetry": True, "threadId": "t", "turnId": "u"}) == []
    with pytest.raises(ModelProviderError):
        t.on_notification("error", {"error": {"message": "dead"}, "willRetry": False, "threadId": "t", "turnId": "u"})


def test_rate_limit_snapshot_reached_raises():
    with pytest.raises(ModelRateLimitError):
        tracker().on_notification("account/rateLimits/updated", {"rateLimits": {"rateLimitReachedType": "rate_limit_reached"}})
    assert tracker().on_notification("account/rateLimits/updated", {"rateLimits": {"rateLimitReachedType": None}}) == []
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_codex_protocol.py -v`
Expected: collection error.

- [ ] **Step 3: Implement `codex/protocol.py`**

```python
"""codex app-server request builders and a per-turn notification tracker.

Shapes verified against `codex app-server generate-json-schema` for
codex-cli 0.155.1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agno.metrics import MessageMetrics
from agno.models.message import Message
from agno.models.response import ModelResponse
from agno.tools.function import Function

from agno_cli_models._common import config_hash, strict_schema, text_of
from agno_cli_models.errors import ContextWindowExceededError, ModelProviderError, ModelRateLimitError

FIXED_CONFIG = ["-c", 'web_search="disabled"', "-c", "features.apps=false"]
ALLOWED_SANDBOXES = ("read-only", "workspace-write")
PAUSE_TEXT = ("This tool call needs a human decision and has not run. Stop now and end your turn; "
              "you will be told the outcome and can continue.")
_RATE_INFOS = ("usageLimitExceeded", "rateLimitExceeded")


def app_server_argv(binary: str) -> list[str]:
    return [binary, "app-server", *FIXED_CONFIG]


def fingerprint(sandbox: str, builtin_tools: bool) -> str:
    return config_hash({"cli": "codex", "config": FIXED_CONFIG, "approval_policy": "never",
                        "allow_model_fallback": False, "sandbox": sandbox, "builtin_tools": builtin_tools,
                        "env": "clean_env/v1", "schema": "strict"})


def _check_sandbox(sandbox: str) -> None:
    if sandbox not in ALLOWED_SANDBOXES:
        raise ValueError(f"sandbox {sandbox!r} is not allowed; use one of {ALLOWED_SANDBOXES}")


def dynamic_tool(fn: Function) -> dict:
    return {"type": "function", "name": fn.name, "description": fn.description or fn.name,
            "inputSchema": fn.parameters or {"type": "object", "properties": {}}}


def thread_start_params(*, model_id: str, system: str, cwd: str, sandbox: str, builtin_tools: bool, dynamic_tools: list[dict]) -> dict:
    _check_sandbox(sandbox)
    params: dict[str, Any] = {"model": model_id, "baseInstructions": system or "You are a helpful assistant.",
                              "approvalPolicy": "never", "sandbox": sandbox, "cwd": cwd,
                              "allowProviderModelFallback": False, "dynamicTools": dynamic_tools}
    if not builtin_tools:
        params["environments"] = []
    return params


def thread_resume_params(*, thread_id: str, model_id: str, system: str, cwd: str, sandbox: str) -> dict:
    _check_sandbox(sandbox)
    return {"threadId": thread_id, "model": model_id, "baseInstructions": system or "You are a helpful assistant.",
            "approvalPolicy": "never", "sandbox": sandbox, "cwd": cwd}


def turn_start_params(*, thread_id: str, text: str, effort: str, builtin_tools: bool, output_schema: dict | None) -> dict:
    params: dict[str, Any] = {"threadId": thread_id, "input": [{"type": "text", "text": text}], "effort": effort}
    if not builtin_tools:
        params["environments"] = []
    if output_schema is not None:
        params["outputSchema"] = strict_schema(output_schema)
    return params


def continuation_text(results: list[Message]) -> str:
    lines = ["Human review of your paused tool calls is complete:"]
    for m in results:
        outcome = "was rejected or failed" if m.tool_call_error else "ran"
        lines.append(f"- {m.tool_name or 'tool'} (call {m.tool_call_id}) {outcome}; result: {text_of(m.content)}")
    lines.append("Continue from where you stopped. Do not call these tools again for the same purpose.")
    return "\n".join(lines)


@dataclass
class TurnTracker:
    model_name: str
    model_id: str
    model: str | None = None
    final_text: str = ""
    usage: dict = field(default_factory=dict)
    done: bool = False
    interrupted: bool = False
    _final_items: set = field(default_factory=set)

    def _raise(self, message: str, info: Any) -> None:
        if info in _RATE_INFOS:
            raise ModelRateLimitError(message, model_name=self.model_name, model_id=self.model_id)
        if info == "contextWindowExceeded":
            raise ContextWindowExceededError(message, model_name=self.model_name, model_id=self.model_id)
        raise ModelProviderError(message, model_name=self.model_name, model_id=self.model_id)

    def on_notification(self, method: str, params: dict) -> list[ModelResponse]:
        if method == "item/started":
            item = params.get("item", {})
            if item.get("type") == "agentMessage" and item.get("phase") == "final_answer":
                self._final_items.add(item.get("id"))
        elif method == "item/agentMessage/delta" and params.get("itemId") in self._final_items:
            return [ModelResponse(content=params.get("delta", ""))]
        elif method == "item/completed":
            item = params.get("item", {})
            if item.get("type") == "agentMessage" and item.get("phase") == "final_answer":
                self.final_text = item.get("text", "")
        elif method == "thread/tokenUsage/updated":
            self.usage = params.get("tokenUsage", {}).get("last") or {}
        elif method == "model/rerouted":
            self.model = params.get("toModel") or self.model
        elif method == "account/rateLimits/updated":
            reached = (params.get("rateLimits") or {}).get("rateLimitReachedType")
            if reached:
                raise ModelRateLimitError(f"codex rate limit reached: {reached}", model_name=self.model_name, model_id=self.model_id)
        elif method == "error":
            if not params.get("willRetry"):
                err = params.get("error") or {}
                self._raise(f"codex error: {err.get('message')}", err.get("codexErrorInfo"))
        elif method == "turn/completed":
            turn = params.get("turn", {})
            status = turn.get("status")
            if status == "failed":
                err = turn.get("error") or {}
                self._raise(f"codex turn failed: {err.get('message')}", err.get("codexErrorInfo"))
            self.interrupted = status == "interrupted"
            self.done = True
        return []

    def metrics(self) -> MessageMetrics:
        u = self.usage
        m = MessageMetrics()
        m.input_tokens = int(u.get("inputTokens", 0))
        m.cache_read_tokens = int(u.get("cachedInputTokens", 0))
        m.output_tokens = int(u.get("outputTokens", 0))
        m.reasoning_tokens = int(u.get("reasoningOutputTokens", 0))
        m.total_tokens = m.input_tokens + m.output_tokens
        return m
```

- [ ] **Step 4: Run and watch them pass**

Run: `.venv/bin/pytest tests/test_codex_protocol.py -v`
Expected: 17 passed.

- [ ] **Step 5: Commit**

```bash
git add . && git commit -q -m "Codex protocol builders and turn tracker with typed errors"
```

---

### Task 10: CodexModel engine (sessions, history replay, approvals)

**Files:**
- Create: `src/agno_cli_models/codex/model.py`, `tests/test_codex_model.py`
- Modify: `src/agno_cli_models/__init__.py` (public exports)

**Interfaces:**
- Consumes: `CliModel` (Task 3), `ToolBridge` (Task 4), `Rpc`, `DONE` (Task 8), everything in `codex/protocol.py` (Task 9), `clean_env` (Task 1), helpers and versions (Task 2).
- Produces:

```python
@dataclass
class CodexModel(CliModel):
    id: str = "gpt-5.6-sol"
    effort: str = "high"
    sandbox: str = "read-only"          # or "workspace-write"
    builtin_tools: bool = False         # True keeps Codex's own shell and file tools (sandboxed)
    codex_bin: str = "codex"
    spawn_fn: Callable[[list[str], dict], Awaitable[Any]] | None = None   # default Rpc.spawn; injectable
    CLI = "codex"
```

Approval design (decline and resume, spec section 5 item 3):
1. On `item/tool/call` for a tool that needs a pause and has no precomputed result, reply `{"contentItems": [{"type": "inputText", "text": PAUSE_TEXT}], "success": false}`, emit the bridge's pause events (session marker on the assistant tool-call message), then send `turn/interrupt` with the current `threadId` and `turnId`.
2. Wait for `turn/completed` with status `interrupted`; the run returns paused.
3. On `continue_run`, Agno has already executed or rejected the tool and appended its result. The model resumes the thread and starts a turn with `continuation_text(...)` built from the tool results that follow the last assistant tool-call message. If the CLI calls the same tool again, the bridge answers from the precomputed result, so the tool runs exactly once.

- [ ] **Step 1: Write the failing tests**

`tests/test_codex_model.py`:

```python
import asyncio

import pytest
from agno.models.message import Message
from agno.tools import tool
from agno.tools.function import Function

from agno_cli_models._common import find_cli_session, session_marker
from agno_cli_models.codex.model import CodexModel
from agno_cli_models.codex.rpc import DONE
from agno_cli_models.errors import CliProtocolError, ModelRateLimitError


class FakeRpc:
    """Scripted app-server. `script` maps a request method to (result, notifications to enqueue after it)."""

    def __init__(self, script, after_reply=None):
        self.script = script
        self.after_reply = after_reply or {}
        self.inbox = asyncio.Queue()
        self.requests = []
        self.replies = []
        self.sent = []
        self.closed = False

    async def request(self, method, params):
        self.requests.append((method, params))
        result, notes = self.script.get(method, ({}, []))
        for n in notes:
            await self.inbox.put(n)
        return result

    async def send(self, obj):
        self.sent.append(obj)

    async def reply(self, request_id, result):
        self.replies.append((request_id, result))
        for n in self.after_reply.get(request_id, []):
            await self.inbox.put(n)

    async def close(self, grace_s=3.0):
        self.closed = True


def note(method, params):
    return {"jsonrpc": "2.0", "method": method, "params": params}


FINAL = [
    note("item/started", {"item": {"id": "i1", "type": "agentMessage", "phase": "final_answer"}}),
    note("item/agentMessage/delta", {"itemId": "i1", "delta": "hello"}),
    note("item/completed", {"item": {"id": "i1", "type": "agentMessage", "phase": "final_answer", "text": "hello"}}),
    note("thread/tokenUsage/updated", {"tokenUsage": {"last": {"inputTokens": 50, "cachedInputTokens": 10, "outputTokens": 5}}}),
    note("turn/completed", {"turn": {"id": "u1", "status": "completed"}}),
]
THREAD = {"thread": {"id": "t1"}, "model": "gpt-5.6-sol"}


def script(turn_notes=FINAL):
    return {"initialize": ({}, []), "thread/start": (THREAD, []), "thread/resume": (THREAD, []),
            "turn/start": ({"turn": {"id": "u1"}}, list(turn_notes))}


def model(rpc, **over):
    async def spawn(argv, env):
        model.argv, model.env = argv, env
        return rpc

    return CodexModel(spawn_fn=spawn, **over)


@pytest.fixture(autouse=True)
def pinned_version(monkeypatch):
    monkeypatch.setattr("agno_cli_models.codex.model.installed_version", lambda b: "0.155.1")


def test_plain_answer_isolation_and_session_marker(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    rpc = FakeRpc(script())
    m = model(rpc)
    msgs = [Message(role="system", content="SYS"), Message(role="user", content="hi")]
    out = asyncio.run(m.aresponse(msgs))
    assert out.content == "hello"
    methods = [r[0] for r in rpc.requests]
    assert methods == ["initialize", "thread/start", "turn/start"]
    start = rpc.requests[1][1]
    assert start["baseInstructions"] == "SYS" and start["allowProviderModelFallback"] is False and start["environments"] == []
    assert rpc.requests[2][1]["input"][0]["text"] == "hi"
    assert "OPENAI_API_KEY" not in model.env
    assert "features.apps=false" in model.argv
    assert find_cli_session(msgs, "codex") == "t1"
    assert m.last_run_info["observed_model"] == "gpt-5.6-sol" and m.last_run_info["cli_version"] == "0.155.1"
    assert rpc.closed


def test_resume_uses_persisted_thread():
    rpc = FakeRpc(script())
    msgs = [Message(role="user", content="q1"), Message(role="assistant", content="a1", provider_data=session_marker("codex", "t0")),
            Message(role="user", content="q2")]
    asyncio.run(model(rpc).aresponse(msgs))
    assert rpc.requests[1][0] == "thread/resume" and rpc.requests[1][1]["threadId"] == "t0"
    assert rpc.requests[2][1]["input"][0]["text"] == "q2"


def test_history_without_thread_is_replayed():
    rpc = FakeRpc(script())
    msgs = [Message(role="user", content="q1"), Message(role="assistant", content="a1"), Message(role="user", content="q2")]
    asyncio.run(model(rpc).aresponse(msgs))
    assert rpc.requests[2][1]["input"][0]["text"].startswith("Conversation so far:")


def add(a: int, b: int) -> int:
    """Add.

    Args:
        a: first
        b: second
    """
    return a + b


def test_dynamic_tool_call_runs_through_agno():
    call = {"jsonrpc": "2.0", "id": 7, "method": "item/tool/call", "params": {"callId": "c1", "tool": "add", "arguments": {"a": 2, "b": 5}}}
    rpc = FakeRpc(script([call]), after_reply={7: FINAL})
    fn = Function.from_callable(add)
    fn.process_entrypoint()
    msgs = [Message(role="user", content="add")]
    asyncio.run(model(rpc).aresponse(msgs, tools=[fn]))
    assert rpc.replies[0] == (7, {"contentItems": [{"type": "inputText", "text": "7"}], "success": True})
    assert rpc.requests[1][1]["dynamicTools"][0]["name"] == "add"
    assert any(m.role == "tool" and m.tool_call_id == "c1" for m in msgs)


@tool(requires_confirmation=True)
def wipe(path: str) -> str:
    """Delete.

    Args:
        path: what to delete
    """
    return "wiped"


def test_approval_tool_declines_interrupts_and_pauses():
    call = {"jsonrpc": "2.0", "id": 8, "method": "item/tool/call", "params": {"callId": "c9", "tool": "wipe", "arguments": {"path": "/x"}}}
    interrupted = [note("turn/completed", {"turn": {"id": "u1", "status": "interrupted"}})]
    rpc = FakeRpc({**script([call]), "turn/interrupt": ({}, interrupted)})
    wipe.process_entrypoint()

    class Run:
        session_id, model_provider_data, metrics, requirements = "a", None, None, None

    run = Run()
    msgs = [Message(role="user", content="delete /x")]
    asyncio.run(model(rpc).aresponse(msgs, tools=[wipe], run_response=run))
    assert rpc.replies[0][1]["success"] is False
    assert ("turn/interrupt", {"threadId": "t1", "turnId": "u1"}) in rpc.requests
    assert run.requirements and run.requirements[0].tool_execution.tool_name == "wipe"
    assert find_cli_session(msgs, "codex") == "t1"


def test_continue_after_approval_sends_outcome_and_reuses_result():
    rpc = FakeRpc(script())
    msgs = [Message(role="user", content="delete /x"),
            Message(role="assistant", tool_calls=[{"id": "c9", "type": "function", "function": {"name": "wipe", "arguments": "{}"}}],
                    provider_data=session_marker("codex", "t1")),
            Message(role="tool", tool_call_id="c9", tool_name="wipe", content="wiped")]
    wipe.process_entrypoint()
    asyncio.run(model(rpc).aresponse(msgs, tools=[wipe]))
    assert rpc.requests[1][0] == "thread/resume"
    text = rpc.requests[2][1]["input"][0]["text"]
    assert "c9" in text and "wiped" in text


def test_rate_limit_notification_raises_and_closes():
    rl = [note("account/rateLimits/updated", {"rateLimits": {"rateLimitReachedType": "rate_limit_reached"}})]
    rpc = FakeRpc(script(rl))
    with pytest.raises(ModelRateLimitError):
        asyncio.run(model(rpc).aresponse([Message(role="user", content="q")]))
    assert rpc.closed


def test_server_exit_mid_turn_is_protocol_error():
    rpc = FakeRpc(script([DONE]))
    with pytest.raises(CliProtocolError):
        asyncio.run(model(rpc).aresponse([Message(role="user", content="q")]))


def test_other_server_requests_are_declined():
    approval = {"jsonrpc": "2.0", "id": 3, "method": "item/commandExecution/requestApproval", "params": {}}
    rpc = FakeRpc(script([approval] + FINAL))
    asyncio.run(model(rpc).aresponse([Message(role="user", content="q")]))
    assert rpc.replies[0] == (3, {"decision": "decline"})


def test_fingerprint_follows_sandbox():
    assert CodexModel(sandbox="read-only").config_fingerprint() != CodexModel(sandbox="workspace-write").config_fingerprint()
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_codex_model.py -v`
Expected: collection error.

- [ ] **Step 3: Implement `codex/model.py`**

```python
"""CodexModel: an Agno Model whose tool loop runs inside `codex app-server`,
using the CLI's own ChatGPT login."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

from agno.models.response import ModelResponse
from pydantic import BaseModel

from agno_cli_models._base import CliModel
from agno_cli_models._bridge import ToolBridge
from agno_cli_models._common import find_cli_session, last_user_text, session_marker, split_system, strip_nulls, transcript_prompt
from agno_cli_models._env import clean_env
from agno_cli_models.codex.protocol import (
    PAUSE_TEXT,
    TurnTracker,
    app_server_argv,
    continuation_text,
    dynamic_tool,
    fingerprint,
    thread_resume_params,
    thread_start_params,
    turn_start_params,
)
from agno_cli_models.codex.rpc import DONE, Rpc
from agno_cli_models.errors import CliProtocolError
from agno_cli_models.versions import check_supported, installed_version


@dataclass
class CodexModel(CliModel):
    id: str = "gpt-5.6-sol"
    name: str = "Codex"
    provider: str = "Codex"
    effort: str = "high"
    sandbox: str = "read-only"
    builtin_tools: bool = False
    codex_bin: str = "codex"
    spawn_fn: Callable[[list[str], dict], Awaitable[Any]] | None = field(default=None, repr=False)
    _version: str | None = field(default=None, repr=False)
    CLI = "codex"

    def config_fingerprint(self) -> str:
        return fingerprint(self.sandbox, self.builtin_tools)

    def _cli_version(self) -> str | None:
        if self._version is None:
            self._version = installed_version(self.codex_bin)
            check_supported("codex", self._version)
        return self._version

    @staticmethod
    def _pending_results(rest: list) -> list:
        """Tool results Agno appended after the last assistant tool call (continue_run)."""
        out = []
        for m in reversed(rest):
            if m.role == "tool":
                out.append(m)
            else:
                break
        return list(reversed(out))

    async def _drive(self, messages, response_format, tools, tool_call_limit, run_response, stream: bool) -> AsyncIterator[ModelResponse]:
        version = self._cli_version()
        bridge = ToolBridge(self, tools, messages, tool_call_limit)
        system, rest = split_system(messages)
        thread_id = find_cli_session(messages, "codex")
        schema = None
        if isinstance(response_format, type) and issubclass(response_format, BaseModel):
            schema = response_format.model_json_schema()
        elif isinstance(response_format, dict):
            schema = response_format

        spawn = self.spawn_fn or Rpc.spawn
        rpc = await spawn(app_server_argv(self.codex_bin), clean_env())
        tracker = TurnTracker(model_name=self.name, model_id=self.id)
        try:
            await rpc.request("initialize", {"clientInfo": {"name": "agno_cli_models", "version": "0.1.0"},
                                             "capabilities": {"experimentalApi": True}})
            await rpc.send({"jsonrpc": "2.0", "method": "initialized"})
            cwd = self.resolved_cwd()
            if thread_id:
                res = await rpc.request("thread/resume", thread_resume_params(thread_id=thread_id, model_id=self.id, system=system, cwd=cwd, sandbox=self.sandbox))
                pending = self._pending_results(rest)
                text = continuation_text(pending) if pending else last_user_text(rest)
            else:
                res = await rpc.request("thread/start", thread_start_params(
                    model_id=self.id, system=system, cwd=cwd, sandbox=self.sandbox, builtin_tools=self.builtin_tools,
                    dynamic_tools=[dynamic_tool(f) for f in bridge.functions.values()]))
                text = transcript_prompt(rest)
            thread_id = res["thread"]["id"]
            tracker.model = res.get("model") or self.id
            marker = session_marker("codex", thread_id)
            turn = await rpc.request("turn/start", turn_start_params(thread_id=thread_id, text=text, effort=self.effort,
                                                                    builtin_tools=self.builtin_tools, output_schema=schema))
            turn_id = turn.get("turn", {}).get("id")

            while not tracker.done:
                msg = await rpc.inbox.get()
                if msg is DONE:
                    raise CliProtocolError("codex app-server exited mid-turn", self.name, self.id)
                method, params = msg.get("method"), msg.get("params", {})
                if method == "item/tool/call" and "id" in msg:
                    name, call_id, args = params.get("tool"), params.get("callId"), params.get("arguments") or {}
                    done = bridge.precomputed(call_id)
                    if done is not None:
                        text_out, ok = done
                    elif bridge.needs_pause(name):
                        await rpc.reply(msg["id"], {"contentItems": [{"type": "inputText", "text": PAUSE_TEXT}], "success": False})
                        for ev in await bridge.pause(call_id, name, args, provider_data=marker):
                            yield ev
                        await rpc.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
                        continue
                    else:
                        events, text_out, ok = await bridge.run(call_id, name, args, provider_data=marker)
                        for ev in events:
                            yield ev
                    await rpc.reply(msg["id"], {"contentItems": [{"type": "inputText", "text": text_out}], "success": ok})
                elif "id" in msg and method:
                    await rpc.reply(msg["id"], {"decision": "decline"})
                else:
                    for ev in tracker.on_notification(method, params):
                        yield ev

            final = tracker.final_text
            if schema is not None and final:
                try:
                    final = json.dumps(strip_nulls(json.loads(final)))
                except json.JSONDecodeError:
                    pass
            info = {"observed_model": tracker.model, "cli_version": version, "cli_session_id": thread_id}
            yield self.usage_event(tracker.metrics(), "" if tracker.interrupted else final, info)
        finally:
            await rpc.close()
```

- [ ] **Step 4: Public exports**

`src/agno_cli_models/__init__.py`:

```python
"""Agno models backed by the official Claude Code and Codex clients."""

from agno_cli_models.claude.model import ClaudeCodeModel
from agno_cli_models.codex.model import CodexModel
from agno_cli_models.errors import CliProtocolError, CliTimeoutError, ModelProviderError, ModelRateLimitError
from agno_cli_models.versions import SUPPORTED, UnsupportedCliVersionWarning

__version__ = "0.1.0"
__all__ = ["ClaudeCodeModel", "CodexModel", "CliProtocolError", "CliTimeoutError", "ModelProviderError",
           "ModelRateLimitError", "SUPPORTED", "UnsupportedCliVersionWarning", "__version__"]
```

- [ ] **Step 5: Run and watch them pass**

Run: `.venv/bin/pytest -q`
Expected: every unit test passes (about 95), 0 failures, integration tests deselected.

- [ ] **Step 6: Commit**

```bash
git add . && git commit -q -m "CodexModel: app-server engine with persisted threads, history replay and decline-and-resume approvals"
```

---

### Task 11: Integration tests against the real CLIs

These spend subscription quota. Run them once, on purpose, at the end of M1. Budget: about 20 small calls (haiku-class for Claude where the scenario allows; Codex at `effort="low"`).

**Files:**
- Create: `tests/test_integration.py`

**Interfaces:**
- Consumes: the public API from Task 10.

- [ ] **Step 1: Write the integration tests**

`tests/test_integration.py`:

```python
"""Real Claude Code and Codex calls. Run on purpose only:

    .venv/bin/pytest -m integration -v
"""

import subprocess
import sys
import textwrap

import pytest
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.tools import tool
from pydantic import BaseModel

from agno_cli_models import ClaudeCodeModel, CodexModel

pytestmark = pytest.mark.integration
CALLS = {"secret": 0, "wipe": 0}


def claude(**kw):
    return ClaudeCodeModel(id="claude-haiku-4-5-20251001", effort="low", **kw)


def codex(**kw):
    return CodexModel(id="gpt-5.6-sol", effort="low", **kw)


MODELS = [pytest.param(claude, id="claude"), pytest.param(codex, id="codex")]


def get_secret(key: str) -> str:
    """Look up a secret by key.

    Args:
        key: secret name
    """
    CALLS["secret"] += 1
    return {"alpha": "4242"}.get(key, "not found")


@tool(requires_confirmation=True)
def wipe(path: str) -> str:
    """Delete a file.

    Args:
        path: file to delete
    """
    CALLS["wipe"] += 1
    return f"deleted {path}"


class City(BaseModel):
    city: str
    country: str


@pytest.mark.parametrize("make", MODELS)
def test_custom_tool_runs_through_agno(make):
    CALLS["secret"] = 0
    agent = Agent(model=make(), tools=[get_secret])
    out = agent.run("What is the secret for key 'alpha'? Answer with only the value.")
    assert "4242" in str(out.content) and CALLS["secret"] >= 1
    info = agent.model.last_run_info
    assert info["observed_model"] and info["cli_version"] and len(info["config_fingerprint"]) == 64


@pytest.mark.parametrize("make", MODELS)
def test_structured_output(make):
    out = Agent(model=make(), output_schema=City).run("Capital of Norway?")
    assert isinstance(out.content, City) and out.content.city.lower() == "oslo"


@pytest.mark.parametrize("make", MODELS)
def test_session_resumes_across_agent_instances(make, tmp_path):
    db = SqliteDb(db_file=str(tmp_path / "s.db"))
    first = Agent(model=make(), db=db, session_id="s1", add_history_to_context=True)
    first.run("Remember the code word: PELICAN. Reply OK.")
    second = Agent(model=make(), db=db, session_id="s1", add_history_to_context=True)
    out = second.run("What was the code word? One word.")
    assert "pelican" in str(out.content).lower()


@pytest.mark.parametrize("make", MODELS)
def test_approval_confirm_runs_tool_exactly_once(make):
    CALLS["wipe"] = 0
    agent = Agent(model=make(), tools=[wipe])
    run = agent.run("Delete /tmp/demo.txt using the wipe tool.")
    assert run.is_paused
    for req in run.active_requirements:
        req.confirm()
    done = agent.continue_run(run_id=run.run_id, requirements=run.requirements)
    assert CALLS["wipe"] == 1 and not done.is_paused


@pytest.mark.parametrize("make", MODELS)
def test_approval_reject_never_runs_tool(make):
    CALLS["wipe"] = 0
    agent = Agent(model=make(), tools=[wipe])
    run = agent.run("Delete /tmp/demo.txt using the wipe tool.")
    for req in run.active_requirements:
        req.reject()
    agent.continue_run(run_id=run.run_id, requirements=run.requirements)
    assert CALLS["wipe"] == 0


def test_claude_isolation_sees_only_agno_tools(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-be-hidden")
    import claude_agent_sdk as sdk

    seen = {}
    real = sdk.query

    def spy(*, prompt, options):
        async def gen():
            async for msg in real(prompt=prompt, options=options):
                if isinstance(msg, sdk.SystemMessage) and msg.subtype == "init":
                    seen.update(msg.data)
                yield msg

        return gen()

    Agent(model=claude(query_fn=spy), tools=[get_secret]).run("Say OK.")
    assert seen["apiKeySource"] == "none"
    assert all(t.startswith("mcp__agno__") for t in seen["tools"])
    assert [s["name"] for s in seen.get("mcp_servers", [])] == ["agno"]
    assert not seen.get("skills")


def test_sync_run_leaves_no_event_loop_warnings():
    code = textwrap.dedent("""
        from agno.agent import Agent
        from agno_cli_models import ClaudeCodeModel
        Agent(model=ClaudeCodeModel(id="claude-haiku-4-5-20251001", effort="low")).run("Say OK.")
    """)
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr
    assert "Event loop is closed" not in done.stderr
```

If an Agno attribute differs (`is_paused`, `active_requirements`, `confirm()`, `reject()`, `continue_run(run_id=..., requirements=...)`), check `agno/run/agent.py` and `agno/run/requirement.py` in the pinned Agno version and use the names found there; the spike's `run_claude_scenarios.py` scenarios 6 and 7 used the working calls.

- [ ] **Step 2: Confirm they are deselected by default**

Run: `.venv/bin/pytest -q`
Expected: unit tests pass, `12 deselected`.

- [ ] **Step 3: Run them for real, once**

Run: `.venv/bin/pytest -m integration -v`
Expected: 12 passed. If a scenario fails, fix the cause in the owning task's module with a new failing unit test first; do not weaken the integration assertion.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py && git commit -q -m "Integration tests against real Claude Code and Codex"
```

---

### Task 12: README and release 0.1.0

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write the README**

Cover, in this order, with code examples taken from the integration tests:

1. What it is: Agno models backed by the official Claude Code and Codex clients, using each CLI's own login.
2. Install: `pip install agno-cli-models`; requires Claude Code and/or codex-cli installed and logged in (`claude` then `/login`; `codex login`).
3. Quick start: `Agent(model=ClaudeCodeModel(...))`, `Agent(model=CodexModel(...))`.
4. Parameters for each model (the field lists from Tasks 7 and 10), including `builtin_tools`, `permission_mode`, `sandbox`, `cwd`, `timeout_s`.
5. Isolation: what is turned off and why; never `--bare`, `bypassPermissions` or `danger-full-access`.
6. Sessions: persisted through Agno history (`provider_data` on assistant messages); resume needs `add_history_to_context=True`.
7. Approvals: Claude uses SDK deferral; Codex declines, interrupts and resumes.
8. Run info: `model.last_run_info` and `run_output.model_provider_data["agno_cli_models"]` (`observed_model`, `cli_version`, `cli_session_id`, `config_fingerprint`, `cli`).
9. Token semantics table (copied from Global Constraints).
10. Errors: `ModelRateLimitError`, `ContextWindowExceededError`, `ModelProviderError`, `CliTimeoutError`, `CliProtocolError`, and that Agno's `FallbackConfig(on_rate_limit=[...])` works with them.
11. Supported CLI versions and the warning class.
12. Known limits: `codex app-server` is experimental; every Codex call leaves a session file under `$CODEX_HOME/sessions` containing the prompt; Claude's SDK bundles its own CLI but this package uses the `claude` on `PATH` unless `cli_path` is set.

No em dashes anywhere in the README.

- [ ] **Step 2: Verify the whole branch**

```bash
.venv/bin/pytest -q
grep -rn $'\u2014' README.md src tests || echo "no em dashes"
.venv/bin/python -c "import agno_cli_models as m; print(m.__version__, m.SUPPORTED)"
```

Expected: all unit tests pass; "no em dashes"; `0.1.0 {'claude': ('2.1.286',), 'codex': ('0.155.1',)}`.

- [ ] **Step 3: Commit and tag**

```bash
git add README.md && git commit -q -m "README for 0.1.0"
git tag v0.1.0
```

Stop here. Merging `m1` into `main`, creating the GitHub repository and publishing to PyPI are the user's decisions.

---

## M1 exit criterion

All of the following, shown as command output:

1. `.venv/bin/pytest -q` in the M1 worktree: every unit test passes.
2. `.venv/bin/pytest -m integration -v`: 12 passed, covering a custom tool, structured output, session resume across agent instances, approval confirm and reject on both CLIs, Claude isolation, and a clean sync run.
3. `git tag` shows `v0.1.0` on branch `m1`.
