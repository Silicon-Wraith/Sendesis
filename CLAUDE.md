# Sendesis

Sendesis qualifies AI execution profiles for engineering roles, fails over only to qualified profiles when a provider is down, and runs cross-model review loops only where a gate has shown they beat cheaper baselines.

Read `docs/specs/2026-09-30-system-vision-design.md` before starting work. It is the source of truth for scope and the roadmap. `docs/PLAN.md` is history: several of its sections are retracted (run `.venv/bin/reasonhold govern docs/PLAN.md`), and its capability ledger, suite and gate design, kill criteria and Spike 0 results still hold.

## Hard constraints

- No new paid services. Cloud models are reached only through the official CLIs on flat-rate subscriptions: `claude -p` and `codex exec`. Local models through OpenAI-compatible HTTP (Ollama on 127.0.0.1:11434, vLLM on 127.0.0.1:8000).
- Never extract or reuse subscription OAuth tokens outside the official CLIs.
- Never use `--sandbox danger-full-access` for Codex or grant Bash to review roles in Claude Code.
- Adjudication is a rule in code, never an LLM judge.

## Layout

```
schemas/      role, profile, receipt, finding (JSON Schema 2020-12)
roles/        role contracts (*.yaml) and their prompts (*.prompt.md)
profiles/     execution profiles (*.yaml)
suites/       qualification suites, one folder per role
receipts/     qualification and gate receipts (JSON, committed to git)
reports/      review and gate reports
spike/        Spike 0 probes, not product code
src/sendesis/ engine, CLI, MCP server (to be written)
tests/        unit tests (mocked runners) and integration tests (real calls)
```

## Runner requirements (from Spike 0, 2026-09-29)

- Every subprocess gets `stdin=subprocess.DEVNULL`. Codex waits on open stdin.
- Every call has a hard wall-clock timeout enforced by the orchestrator. An unreachable provider makes `claude -p` hang silently. Timeout with no output is a failover trigger, same as an error exit or rate limit.
- Pin model and reasoning effort on every call. Both CLIs default to their top model.
- `claude -p --output-format json` returns one JSON object. Use `is_error`, `subtype`, `api_error_status`, `permission_denials`, `num_turns`, `usage`, `modelUsage` (actual model), and `total_cost_usd` (list price, not a charge). The runner uses `--output-format stream-json --verbose` instead: the same `result` object comes last, and the `init` event adds `claude_code_version` and the tool list. With `--json-schema`, the answer is in `result.structured_output`. `--json-schema` rejects the 2020-12 `$schema` URI, so strip `$schema` and `$id` first.
- `codex exec --json` returns JSONL events. Answer is the last `item.completed` with `type: agent_message`. Usage is on `turn.completed`. A stream without `turn.completed` is a failure. In `--json` mode there is no stderr model header (verified 2026-09-30, codex-cli 0.155.1). Confirm the model from the session rollout file `$CODEX_HOME/sessions/**/rollout-*-<thread_id>.jsonl` (`turn_context.model`, `session_meta.cli_version`), which is why the runner does not pass `--ephemeral`.
- Codex requires a git repo as working directory, or `--skip-git-repo-check`. Run suites from a fixed, git-initialized workdir. AGENTS.md and CLAUDE.md in that workdir load into every call, so hash them into the receipt.
- Codex's sandbox needs the `/usr/bin/bwrap` AppArmor profile on Ubuntu 24.04. `workspace-write` has no network by design.
- Codex `--output-schema` rejects `finding.json` as-is (`invalid_json_schema`: every property must be required). The runner sends a strict variant (all properties required, optional ones made nullable, `additionalProperties: false`) and strips nulls from the answer before validating it against `finding.json`.
- CLI overhead depends on configuration. Spike 0 defaults cost about 34k input tokens per Claude call and 14k per Codex call. With the runners' isolation flags it is about 5k to 6k per Claude call and about 10k per Codex call (measured 2026-09-30). Isolation flags are hashed into receipts as `runner_config_sha256`. Cost matching in the gate counts total tokens, not prompt tokens.
- Isolation that works with CLI login state: Claude `--tools Read,Grep,Glob --strict-mcp-config --setting-sources "" --disable-slash-commands --no-session-persistence --settings '{"disableClaudeAiConnectors":true,"autoMemoryEnabled":false}'`; Codex `-c features.apps=false -c web_search="disabled" --ignore-user-config --sandbox read-only`. Never `--bare`: it ignores OAuth login. Strip `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `CODEX_API_KEY` and every `CLAUDE_*` variable from the child environment (a parent Claude Code session sets several).

## Working rules

- Python 3.11+, a venv in `.venv`, dependencies in `pyproject.toml`. No global installs.
- Unit tests mock runners. Real CLI calls go only in tests marked `@pytest.mark.integration`, run on purpose, because they spend subscription quota.
- Stop at the end of each milestone or plan, show the exit criterion evidence, and wait for review.
- Receipts and reports are data, committed to git. Never edit a receipt by hand.
- Prefer small, boring code. The engine's value is in D2 (receipts) and D8 (the gate). Everything else should stay thin.
- In docs and user-facing text, do not use em dashes.
