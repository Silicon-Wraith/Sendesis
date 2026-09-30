# Sendesis: The Simplest Build Plan

Snapshot of the living plan (Claude Docs, "Sendesis: The Simplest Build Plan"), 2026-09-29. If this file and the doc disagree, the doc wins; ask John.

## Bottom line

Build one small Python package and CLI (`sendesis`) that drives the tools John already pays for: Claude Code, Codex CLI, and local Ollama/vLLM endpoints. Everything else is YAML and JSON files in this repo. No new purchases, no new runtime, no gateway service.

- What it delivers: role contracts, qualified profiles with expiry, qualified-only failover when a provider goes down, cross-model review loops with preserved dissent, rule-based adjudication, per-phase budgets, and a gate that proves a cross-model loop beats cheaper baselines before it is used.
- Size: roughly 1,500 to 2,500 lines of Python plus the schemas and one role suite. An estimate.
- Order: Spike 0, schemas, qualify, failover, review loop, gate. Failover ships early because it pays off on the next outage.
- Not bought: vendor-neutral enforcement inside the CLIs, true blinding, or dollar-accurate cost comparisons on flat-rate plans.

## Constraint that shapes the design

Flat-rate subscriptions reach models only through the vendors' own clients. So Sendesis drives the official CLIs as subprocesses.

| Asset | How Sendesis reaches it | Role |
| --- | --- | --- |
| Anthropic subscription | `claude -p`, JSON output | Primary for hard roles; tool limits via `--allowedTools` |
| OpenAI subscription | `codex exec` signed in with ChatGPT, JSONL events | Second cloud family; sandbox modes for limits |
| Ollama | OpenAI-compatible HTTP on 127.0.0.1:11434 | Cheap baselines, last-resort failover where qualified |
| vLLM | OpenAI-compatible HTTP on 127.0.0.1:8000 | Same, with batching for large baseline runs on the RTX 6000 Ada |

Do not extract subscription OAuth tokens into third-party tools.

## Architecture

Three layers of files feed one engine: repo files (roles, profiles, receipts, reports), the `sendesis` CLI plus router (qualify, run, review, gate), and three runners (`claude_cli`, `codex_cli`, `openai_http`). Only the router picks a profile. Runners turn a profile into CLI flags or an HTTP call and return output with token usage. Receipts are plain JSON in git, so their history is the audit trail.

## In-CLI use

| Layer | What it is | Used from |
| --- | --- | --- |
| Engine | Python package: runners, receipts, loop, adjudication, gate | Everything below |
| CLI | `sendesis validate`, `qualify`, `gate`, `run` | Terminal; qualify and gate are long batch jobs |
| MCP server | Thin wrapper exposing `critique`, `review`, `run_role` | Inside Claude Code and Codex |
| Plugin | Claude Code plugin bundling the MCP config and slash commands | Optional |

A script run from Codex inherits its sandbox, loses the network, and hangs calling Claude. MCP servers are expected to run outside the command sandbox; `spike/mcp_net_probe.py` confirms it. Inside a CLI, the host session is the author and Sendesis supplies the critic from the other family. `critique` runs one round per call so the host drives the loop and John can step in between rounds.

## Capability map (ledger D1 to D12)

| # | Capability | Delivery | Effort |
| --- | --- | --- | --- |
| D1 | Role contracts | `roles/<role>.yaml` validated by `schemas/role.json` | Low |
| D2 | Qualified profiles with expiry | `profiles/*.yaml`; `sendesis qualify` writes receipts with QUALIFIED, FAILED or UNKNOWN, intervals, expiry. Void on role version, profile hash, suite hash, CLI version or model change | Medium, core |
| D3 | Capability limits | Native flags only: Claude `--allowedTools`, Codex `--sandbox read-only`, HTTP runners get no tools | Low |
| D4 | Blinded first pass | Separate processes, no shared context, reviewer labels A, B instead of model names | Low |
| D5 | Findings with evidence states | Output validates against `schemas/finding.json`; one retry, then UNKNOWN | Low |
| D6 | Dissent as output | Minority findings kept in `dissent`, never dropped | Low |
| D7 | Adjudication | Rule: dedupe by file, overlapping lines, category; confirmed if two reviewers agree or evidence reproduces; else disputed and kept | Low |
| D8 | Loop must beat baselines at equal cost | `sendesis gate` with four arms; team mode only on a win | Medium, differentiator |
| D9 | Budgets and escalation reserve | Timeouts, max turns, token ceilings, reserve calls for disputed findings | Low |
| D10 | Provider independence | Three runners, one interface | Low |
| D11 | One decision-maker per routing dimension | Only the router picks profiles | None |
| D12 | Pluggable context | Use AGENTS.md and CLAUDE.md as they are | None |

## Build phases

0. Spike 0: headless CLI check. Mostly done; see below.
1. Schemas and one role. Loaders and `sendesis validate`. Exit: every file validates, bad files fail loudly.
2. Runners and qualify. Three runners and `sendesis qualify <role> <profile>`, recording CLI version, observed model, tokens, wall time, exit status. Exit: receipts on disk with score, interval, expiry, status; a changed CLI version reports UNKNOWN.
3. Qualified failover. `sendesis run <role> <input>` tries `failover_order`, falling over on error, rate limit, or timeout, only to profiles with a valid receipt. Exit: cut network to one provider mid-run; the task finishes on a qualified profile or refuses clearly. Also build the MCP server here.
4. Review loop. Blinded first pass, then author and critic alternate across families until a round adds no new confirmed finding or the round cap is hit. Rule adjudication at the end. Findings, dissent and per-round history to JSON plus a Markdown summary. Exit: on five known cases, disputed findings stay disputed and minority findings survive.
5. The gate. `sendesis gate <role>` runs four arms on the same suite at matched cost and writes a team_gate receipt. Exit: a gate report for Security Reviewer, win or lose.

Stop at each phase boundary for review.

## Suite and gate

About 100 labeled cases, roughly 30 percent clean; 30-case pilot first. Sources: CVEfixes, OWASP Benchmark, freshly planted bugs, clean diffs. Metrics: recall, false positives per clean case, schema validity. Wilson intervals per arm, paired bootstrap on differences. See `suites/security-reviewer/README.md`.

| Arm | What runs | Cost matching |
| --- | --- | --- |
| Cross-model loop | Blinded first pass, author and critic alternate across families, R rounds, rule adjudication | Sets the budget |
| Same-model loop | Strongest profile critiques and revises its own work for R rounds | Same rounds, tokens capped to match |
| Single pass | Strongest profile once with self-review | Given the loop's token budget |
| N-sample vote | Strongest profile sampled N times, majority by location | N chosen to spend the loop's budget |

Sweep R at 1, 2, 4, 8. Pilot at 1 and 4 rounds first. Team mode for a role is allowed only when the cross-model loop beats all three baselines with non-overlapping intervals.

## Kill criteria

- Round count: kill team mode for a role only if the cross-model loop never beats the same-model loop at any round count within budget. Iteration helping is settled by John's manual Claude and ChatGPT round-trips; the open question is whether a second family beats the same number of rounds with one family.
- Security Reviewer loss: diagnose ceiling, adjudication, round cap, and task shape first. A real loss kills team mode for that role only. Then test a revision role such as Design Reviewer by blind pairwise preference on about 20 artifacts.
- Spike 0 failure: switch cloud runners to API keys or run local-only.

Expect the automated loop to land slightly below John's manual results, since a rule replaces his judgment of what to keep each round.

## Spike 0 results (2026-09-29, Claude Code 2.1.281, codex-cli 0.155.1)

| Check | Result |
| --- | --- |
| Claude Code headless, JSON, usage, model name | Pass; about 34k input tokens overhead per call, mostly cached |
| Codex headless, JSONL, usage | Pass after `--skip-git-repo-check` or running in a git repo; about 14k tokens overhead |
| Codex model name | Only in the stderr header |
| Claude calls Codex | Pass; 16.5 s, about 69k Claude tokens |
| Codex sandbox runs commands | Pass after AppArmor profile for `/usr/bin/bwrap` |
| Codex calls Claude under `workspace-write` | Blocked by design, no DNS; Claude hung 60 s |

Remaining: MCP probe from Codex (`spike/README.md`), subscription terms for headless use, per-plan rate limits, and choosing a local model with structured output on Ollama and vLLM.
