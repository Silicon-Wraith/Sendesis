# Handoff: Agno research and the CLI-backed model spike

Written 2026-09-30 at the end of a Claude Code session in the Agno repo. It records what was learned there that matters for Sendesis. It is context, not a plan: `docs/PLAN.md` stays the source of truth.

## Where things are

| What | Path |
|---|---|
| Agno architecture and extension points | `/mnt/ml_storage/dev/projects/agno/ARCHITECTURE.md` (uncommitted file on Agno `main`) |
| Spike code and findings | `/mnt/ml_storage/dev/projects/agno/.claude/worktrees/argo-spike/spike/`, committed on local branch `worktree-argo-spike` (commit `784456f3e`). Start with `FINDINGS.md`. |
| Spike credentials | `~/.argo-spike/claude_oauth_token` (from `claude setup-token`) and `~/.argo-spike/codex-home/` (a separate `CODEX_HOME`, logged in with `codex login`) |

## What the spike proved

An Agno `Model` subclass can hand the whole tool loop to Claude Code or Codex. The CLI calls back into Agno's own tool functions, so an ordinary Agno `Agent` works unchanged with a subscription-backed model.

These were tested on 2026-09-30 with Claude Code 2.1.286 (haiku) and codex-cli 0.155.1 (gpt-5.6-luna):

- Custom tools run through Agno.
- Multi-turn sessions resume across processes.
- Structured output returns a Pydantic object.
- Streaming delivers text and tool events.
- Agno built-in tools work.
- On Claude only, the approval flow works: a tool pauses for approval, then is confirmed or rejected, and `continue_run` completes the run. The Codex approval flow is not designed yet.

## Conflicts with Sendesis hard constraints

1. **Surfaces.** Sendesis names `claude -p` and `codex exec`. The spike used different surfaces:
   - The Claude Agent SDK, a Python library that drives the official `claude` binary over its stream-json protocol.
   - `codex app-server`, an official Codex subcommand speaking JSON-RPC.

   Both are official, and both give things the one-shot commands do not: in-process tools, approval callbacks, token streaming and session resume. But they are not the two commands the constraint names. Using them would require a deliberate decision to widen the constraint.
2. **Tokens.** The Claude side authenticated with `CLAUDE_CODE_OAUTH_TOKEN`, a long-lived token from `claude setup-token` saved in a file and passed to the CLI through its environment. Only the official CLI ever consumed it. Even so, check it against "Never extract or reuse subscription OAuth tokens outside the official CLIs". If that rule is meant to forbid storing the token in a file at all, the Sendesis runners should rely on the CLI's own `/login` state instead.

## Findings that update Spike 0

**Overhead is mostly configuration.**
- Spike 0 measured about 34k input tokens per Claude call and 14k per Codex call.
- With isolation settings, the spike measured about 0.6k to 2.9k per Claude call and 3.7k to 4.1k per Codex call (70 to 90 percent cached).
- The gate counts total tokens, so the runner configuration changes cost comparisons. It belongs in the receipt.

**Isolation settings that worked.** These were SDK and app-server options. Each maps to a CLI flag or `-c` override; verify the exact flag names for `claude -p` and `codex exec` before relying on them.
- **Claude.** Without these, a session saw about 70 personal claude.ai connector tools (Gmail, Drive and others) and the working directory's project and git context.
  - no built-in tools (`tools=[]`)
  - no settings sources (`setting_sources=[]`)
  - strict MCP config
  - an empty working directory
  - `ANTHROPIC_API_KEY` removed from the environment, because if present it silently switches billing to the API
- **Codex.** Without these, a session started the user's `~/.codex` MCP servers and the ChatGPT apps MCP server.
  - a dedicated `CODEX_HOME`
  - `-c features.apps=false`
  - `-c web_search="disabled"`
  - with app-server, `environments: []`, which removes shell and file access
  - `OPENAI_API_KEY` and `CODEX_API_KEY` removed from the environment
- This matches the Spike 0 note that workdir files load into every call: anything the CLI can see from its home or workdir leaks into the prompt.

**Rate-limit signals exist for failover.**
- The Claude SDK emits a `RateLimitEvent` with `rate_limit_type` (`five_hour`, `seven_day`, `seven_day_opus`) and `utilization`.
- Codex app-server emits `account/rateLimits/updated`.
- Neither is available from plain `claude -p --output-format json` or `codex exec --json`, as far as tested.

**Codex facts.**
- `codex login --device-auth` fails until device-code sign-in is enabled in ChatGPT security settings. Plain `codex login` (browser, localhost callback) works.
- `codex mcp-server` no longer exists in 0.155.1.
- App-server `dynamicTools` requires the experimental API opt-in, so the Codex version should be pinned.
- Codex `outputSchema` needed a strict schema (every property required, `additionalProperties: false`). This confirms the Spike 0 guess.

## Subscription terms

This answers the "subscription terms for headless use" item under Remaining in PLAN.md. The quotes were gathered by a research agent on 2026-09-30 and were not re-checked by hand, so re-read the sources before relying on them.

**Anthropic.**
- https://code.claude.com/docs/en/legal-and-compliance: "Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, or Max plan credentials on behalf of their users."
- The same page: "Advertised usage limits for Pro and Max plans assume ordinary, individual usage of Claude Code and the Agent SDK." It also says the policy does not prevent an end user from signing in to the unmodified Claude Code binary with their own subscription.
- Reading: personal use of your own login is tolerated. Offering subscription login to others is not.

**OpenAI** (learn.chatgpt.com auth and non-interactive docs):
- The docs point automation and CI to API keys.
- Running as your ChatGPT account in automation is described as allowed when you "specifically need to run as your Codex account", and the docs warn against doing so in public repos.

## Open items from the spike

- The Agno-session-to-CLI-session map is in memory only.
- The Codex approval flow is not designed. Tool calls are blocking server requests, so a durable pause needs a live process or a decline-and-resume scheme.
- Not tested: tool-call limits inside the CLI loop, Teams and Workflows, memory and knowledge tools, image input.

The full list is in `FINDINGS.md`.

## Cleanup when done

- Revoke the `setup-token` token from your Claude account settings.
- Delete `~/.argo-spike/`.
- Remove the worktree with `git worktree remove .claude/worktrees/argo-spike` from the Agno repo.
