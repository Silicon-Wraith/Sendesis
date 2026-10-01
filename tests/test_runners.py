import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from conftest import REPO
from sendesis.model import load_profile
from sendesis.runners import Call, Status, claude_cli, codex_cli, openai_http
from sendesis.runners.base import clean_env, run_process

FIXTURES = Path(__file__).parent / "fixtures"
FINDING_SCHEMA = json.loads((REPO / "schemas" / "finding.json").read_text())


def profile(name):
    return load_profile(REPO / "profiles" / f"{name}.yaml", REPO)


def call(tmp_path, timeout_s=60):
    return Call(prompt="review this", schema=FINDING_SCHEMA, workdir=tmp_path, timeout_s=timeout_s)


# ---- shared subprocess rules -------------------------------------------------


def test_clean_env_drops_api_keys_and_parent_session_vars(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY", "CLAUDE_CODE_SESSION_ID", "CLAUDECODE", "CLAUDE_EFFORT"):
        monkeypatch.setenv(name, "x")
    monkeypatch.setenv("HOME", "/home/someone")
    env = clean_env()
    assert env["HOME"] == "/home/someone"
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY", "CLAUDE_CODE_SESSION_ID", "CLAUDECODE", "CLAUDE_EFFORT"):
        assert name not in env


def test_run_process_gives_child_empty_stdin(tmp_path):
    proc = run_process([sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"], tmp_path, 10, clean_env())
    assert proc.stdout.strip() == "''"
    assert not proc.timed_out


def test_run_process_enforces_wall_clock_timeout(tmp_path):
    proc = run_process([sys.executable, "-c", "import time; time.sleep(10)"], tmp_path, 1, clean_env())
    assert proc.timed_out
    assert proc.wall_s < 5


# ---- claude_cli ---------------------------------------------------------------


def test_claude_argv_pins_model_effort_and_isolation(tmp_path):
    argv = claude_cli.build_argv(profile("claude-opus"), ("read", "search"), call(tmp_path))
    joined = " ".join(argv)
    assert argv[:2] == ["claude", "-p"]
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5"
    assert argv[argv.index("--effort") + 1] == "high"
    assert argv[argv.index("--tools") + 1] == "Read,Grep,Glob"
    for flag in ("--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"):
        assert flag in argv
    assert "Bash" not in argv[argv.index("--tools") + 1]
    assert "--bare" not in argv  # --bare never reads OAuth login state
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert "$schema" not in schema and "$id" not in schema
    assert "disableClaudeAiConnectors" in joined


def test_claude_argv_with_no_tools_disables_all(tmp_path):
    argv = claude_cli.build_argv(profile("claude-opus"), (), call(tmp_path))
    assert argv[argv.index("--tools") + 1] == ""


def test_claude_argv_refuses_shell_for_review_roles(tmp_path):
    with pytest.raises(ValueError):
        claude_cli.build_argv(profile("claude-opus"), ("read", "shell"), call(tmp_path))


def test_claude_parse_real_stream():
    stdout = (FIXTURES / "claude_review.stream.jsonl").read_text()
    r = claude_cli.parse(stdout, "", 0, timed_out=False, wall_s=7.7)
    assert r.status is Status.OK
    assert r.model == "claude-opus-5-5"
    assert r.cli_version == "2.1.286"
    assert r.output["findings"][0]["category"] == "CWE-89"
    assert r.input_tokens == 2 + 5873 and r.cached_input_tokens == 0 and r.output_tokens == 748
    assert r.list_usd == pytest.approx(0.061952)


def test_claude_parse_timeout_without_output():
    r = claude_cli.parse("", "", -9, timed_out=True, wall_s=300)
    assert r.status is Status.TIMEOUT


def test_claude_parse_rate_limit():
    result = {"type": "result", "subtype": "success", "is_error": True, "api_error_status": 429,
              "result": "Claude AI usage limit reached", "usage": {}, "modelUsage": {}}
    r = claude_cli.parse(json.dumps(result) + "\n", "", 1, timed_out=False, wall_s=1)
    assert r.status is Status.RATE_LIMIT


def test_claude_parse_missing_result_is_error():
    r = claude_cli.parse('{"type":"system","subtype":"init","claude_code_version":"2.1.286"}\n', "boom", 1, timed_out=False, wall_s=1)
    assert r.status is Status.ERROR
    assert "boom" in r.reason


# ---- codex_cli ----------------------------------------------------------------


def test_codex_strict_schema_requires_every_property():
    strict = codex_cli.strict_schema(FINDING_SCHEMA)
    loc = strict["$defs"]["finding"]["properties"]["location"]
    assert set(loc["required"]) == {"file", "line_start", "line_end"}
    assert loc["additionalProperties"] is False
    assert "null" in loc["properties"]["line_start"]["type"]
    assert set(strict["required"]) == set(strict["properties"])
    assert "$schema" not in strict


def test_codex_strip_nulls():
    assert codex_cli.strip_nulls({"a": None, "b": [{"c": None, "d": 1}], "e": {"f": None}}) == {"b": [{"d": 1}], "e": {}}


def test_codex_argv_pins_model_effort_and_read_only_sandbox(tmp_path):
    argv = codex_cli.build_argv(profile("codex-gpt"), call(tmp_path), schema_path=tmp_path / "s.json")
    assert argv[:3] == ["codex", "exec", "--json"]
    assert argv[argv.index("-m") + 1] == "gpt-5.6-sol"
    assert 'model_reasoning_effort="high"' in argv
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert "features.apps=false" in argv and 'web_search="disabled"' in argv
    assert "--ignore-user-config" in argv
    assert "danger-full-access" not in " ".join(argv)
    assert argv[-1] == "review this"


def test_codex_parse_real_events_and_rollout():
    stdout = (FIXTURES / "codex_review.events.jsonl").read_text()
    rollout = (FIXTURES / "codex_rollout.jsonl").read_text()
    r = codex_cli.parse(stdout, "Reading additional input from stdin...\n", 0, timed_out=False, wall_s=12, rollout_text=rollout)
    assert r.status is Status.OK
    assert r.model == "gpt-5.6-sol"
    assert r.cli_version == "0.155.1"
    assert r.input_tokens == 9982 and r.output_tokens == 287
    assert r.output["findings"][0]["category"] == "CWE-89"
    assert "run_id" not in r.output  # nulls from the strict schema are stripped


def test_codex_parse_without_turn_completed_is_error():
    events = [{"type": "thread.started", "thread_id": "t"}, {"type": "turn.started"},
              {"type": "error", "message": "invalid_json_schema: Missing 'line_start'"},
              {"type": "turn.failed", "error": {"message": "invalid_json_schema"}}]
    r = codex_cli.parse("".join(json.dumps(e) + "\n" for e in events), "", 1, timed_out=False, wall_s=2, rollout_text=None)
    assert r.status is Status.ERROR
    assert "invalid_json_schema" in r.reason


def test_codex_parse_rate_limit():
    events = [{"type": "thread.started", "thread_id": "t"},
              {"type": "error", "message": "You've hit your usage limit. Try again later."}]
    r = codex_cli.parse("".join(json.dumps(e) + "\n" for e in events), "", 1, timed_out=False, wall_s=2, rollout_text=None)
    assert r.status is Status.RATE_LIMIT


def test_codex_finds_rollout_by_thread_id(tmp_path):
    day = tmp_path / "sessions" / "2026" / "09" / "30"
    day.mkdir(parents=True)
    (day / "rollout-2026-09-30T16-01-00-abc-123.jsonl").write_text("x\n")
    assert codex_cli.find_rollout(tmp_path, "abc-123").name.endswith("abc-123.jsonl")
    assert codex_cli.find_rollout(tmp_path, "nope") is None


# ---- openai_http ----------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    reply_status = 200
    seen = {}

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Handler.seen = {"path": self.path, "body": body}
        payload = {
            "model": body["model"],
            "choices": [{"message": {"content": json.dumps({"role_id": "security-reviewer", "findings": []})}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30, "prompt_tokens_details": {"cached_tokens": 100}},
        }
        data = json.dumps(payload).encode()
        self.send_response(_Handler.reply_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def local_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    _Handler.reply_status = 200


def _http_profile(endpoint):
    from dataclasses import replace
    p = profile("vllm-local")
    return replace(p, model=replace(p.model, base_url=endpoint, id="qwen-test"), enabled=True)


def test_openai_http_posts_chat_completion_with_json_schema(local_server, tmp_path):
    r = openai_http.run(_http_profile(local_server), call(tmp_path))
    assert r.status is Status.OK
    assert r.model == "qwen-test"
    assert r.output == {"role_id": "security-reviewer", "findings": []}
    assert (r.input_tokens, r.cached_input_tokens, r.output_tokens) == (120, 100, 30)
    body = _Handler.seen["body"]
    assert _Handler.seen["path"] == "/v1/chat/completions"
    assert body["response_format"]["type"] == "json_schema"
    assert "tools" not in body


def test_openai_http_429_is_rate_limit(local_server, tmp_path):
    _Handler.reply_status = 429
    r = openai_http.run(_http_profile(local_server), call(tmp_path))
    assert r.status is Status.RATE_LIMIT


def test_openai_http_unreachable_is_error(tmp_path):
    r = openai_http.run(_http_profile("http://127.0.0.1:9/v1"), call(tmp_path, timeout_s=5))
    assert r.status in (Status.ERROR, Status.TIMEOUT)


def test_runner_config_hashes_are_stable_and_distinct():
    hashes = {m.config_sha256() for m in (claude_cli, codex_cli, openai_http)}
    assert len(hashes) == 3
    assert claude_cli.config_sha256() == claude_cli.config_sha256()
