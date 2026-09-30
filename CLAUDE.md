# Sendesis

Sendesis qualifies AI execution profiles for engineering roles, fails over only to qualified profiles when a provider is down, and runs cross-model review loops only where a gate has shown they beat cheaper baselines.

Read `docs/PLAN.md` before starting any phase. It is the source of truth for scope and exit criteria.

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
- `claude -p --output-format json` returns one JSON object. Use `is_error`, `subtype`, `api_error_status`, `permission_denials`, `num_turns`, `usage`, `modelUsage` (actual model), and `total_cost_usd` (list price, not a charge).
- `codex exec --json` returns JSONL events. Answer is the last `item.completed` with `type: agent_message`. Usage is on `turn.completed`. A stream without `turn.completed` is a failure. The model name appears only in the plain-text stderr header (`model: ...`); parse it to confirm the model.
- Codex requires a git repo as working directory, or `--skip-git-repo-check`. Run suites from a fixed, git-initialized workdir. AGENTS.md and CLAUDE.md in that workdir load into every call, so hash them into the receipt.
- Codex's sandbox needs the `/usr/bin/bwrap` AppArmor profile on Ubuntu 24.04. `workspace-write` has no network by design.
- Codex `--output-schema` likely needs a strict schema (every property required, `additionalProperties: false`). Generate a strict variant of `finding.json` for Codex if it rejects the normal one. Verify before building around it.
- CLI overhead is large: about 34k input tokens per Claude call and 14k per Codex call, mostly cached. Cost matching in the gate counts total tokens, not prompt tokens.

## Working rules

- Python 3.11+, a venv in `.venv`, dependencies in `pyproject.toml`. No global installs.
- Unit tests mock runners. Real CLI calls go only in tests marked `@pytest.mark.integration`, run on purpose, because they spend subscription quota.
- Stop at the end of each phase in `docs/PLAN.md`, show the exit criterion evidence, and wait for review.
- Receipts and reports are data, committed to git. Never edit a receipt by hand.
- Prefer small, boring code. The engine's value is in D2 (receipts) and D8 (the gate). Everything else should stay thin.
- In docs and user-facing text, do not use em dashes.
