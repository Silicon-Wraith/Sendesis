# Stall handling for model seats

Status: decisions recorded 2026-10-01 (approved). Part 1 is done in agno-cli-models v0.1.2, and Sendesis pins it. Parts 2 and 3 are not implemented yet.

Evidence: `reports/2026-10-01-m3.1-exit-run.md`, "Known issue: Codex stream stalls".

## Problem

The M3.1 exit run qualified codex-gpt on the 30-case Security Reviewer suite. Five of the 21 CVE cases timed out at 300 s. In all five, Codex opened its final answer (an output item of type `message`) and then sent nothing for 218 to 271 s. Sendesis's wall-clock limit then aborted the turn.

In the 25 cases that passed, the longest silence was 16 s and the answer streamed in 8 to 18 s. A rerun of the five cases with every event timestamped passed all five. The stall is intermittent and not caused by the case content, and most likely happens on the provider side.

Three things went wrong in how Sendesis handled it:

1. **One limit, two meanings.** Sendesis has one per-call limit, wall clock. It cannot tell "the model is working slowly" from "nothing has arrived for minutes". Each stall cost about 300 s before it was detected, when the evidence says about 60 s is enough.
2. **Our limit hides Codex's own recovery.** Codex has a stream idle timeout of its own (`stream_idle_timeout_ms`, default 300,000 ms) and reconnects on it. Our limit is also 300 s, so it always fires first.
3. **An infrastructure failure was scored as a model miss.** Each stalled case counted as a miss for every label in it, so codex-gpt's recall read 0.677, FAIL. The receipt was UNKNOWN because of the stalls, but the printed score claims a measurement that never happened.

## Design

### 1. Idle limit in agno-cli-models (upstream, in the agno-cli-models repository)

- `CliModel` gains `idle_timeout_s: float | None`.
  - When it is set, a call that receives no message from the CLI for that long raises `CliStallError`.
  - `CliStallError` is a new subclass of `CliTimeoutError`, so callers that only know about timeouts keep working.
  - The error carries the seconds idle, the last message's method, and whether an answer item was open.
- **Codex:** the idle clock resets on every message from `codex app-server`, including `item/started`, deltas and token updates. It does not reset only on the `ModelResponse` events that `_timed` sees, because those do not cover reasoning.
  - The default is 60 s. That is about four times the longest healthy silence measured, 16 s.
- **Claude Code:** the default was to stay `None` until Claude's event cadence was measured. It has now been measured (agno-cli-models `claude-idle-cadence`, dec-9d0c71cd7c9e), and v0.1.2 ships a 60 s default for Claude. The limit holds only with partial messages on, so `ClaudeCodeModel` switches them on whenever an idle limit is set. The clock is held while an Agno tool runs.
- `idle_timeout_s` goes into `config_fingerprint()`. It changes what counts as a failed call, so a receipt must certify it.
- **Rejected: Codex's own `stream_idle_timeout_ms`.** It cannot be changed: `codex app-server` refuses to start when any `model_providers.openai` key is set (agno-cli-models `codex-builtin-provider-stream-settings`, dec-3bbadf61b14f). Codex keeps its defaults, a 300 s idle timeout and 5 stream retries. A Codex reconnect shows up as an `error` notification with `willRetry: true`, and that notification also resets the idle clock.

### 2. A STALL outcome in Sendesis

- `seat.py` maps `CliStallError` to a new `Outcome.STALL`.
  - Every other timeout stays `Outcome.TIMEOUT`.
  - The run log records the details: seconds idle, last method, and whether an answer item was open.
- **The profile sets the limit.** It gains an optional `idle_timeout_s`, which is passed to the model class. Setting it changes the profile hash, so existing receipts read void, as they should.
- **Failover (spec section 5):** STALL is a failover trigger, like TIMEOUT. It does not skip the profile for the rest of the run the way a rate limit does, because the evidence shows the next call usually succeeds.

### 3. Qualification treats a stall as unmeasured, not as a miss

- **Retry:** a STALL gets one retry of the same case, like INVALID.
  - Both attempts are logged.
  - A retry that also stalls leaves the case **unmeasured**.
- **Scores:** scores are computed over measured cases only.
  - A case whose final outcome is TIMEOUT, ERROR, or STALL after its retry is unmeasured, and its outcome is recorded.
  - The receipt records `n_measured` and the unmeasured case ids with their outcomes.
- **Status:** any unmeasured case keeps the status UNKNOWN, as today. A receipt can never reach QUALIFIED or FAILED on a subset of the suite.
  - Because of this, `sendesis qualify` prints a FAIL only for a model that answered and missed. Failures of the provider, the network or the CLI are reported in the status reason instead.
- **Schema validity is unchanged:** an answer that arrived but was invalid is still a measurement.

## Substrate reality

| Assumption | Status | Evidence |
|---|---|---|
| A stalled Codex turn opens a `message` item and then sends no app-server message | Verified, 5 of 5 stalls | `~/.codex/logs_2.sqlite` and rollouts, exit run 2026-10-01 |
| Healthy Codex turns never go silent for more than about 16 s | Verified on 30 turns (25 exit-run passes and 5 probe passes) | Exit report; probe event logs |
| The stall does not depend on the case content | Supported, not proven | Same five cases passed on rerun, 0 of 5 stalled |
| Codex 0.155.1 has `stream_idle_timeout_ms` and `stream_max_retries` | Verified (strings in the shipped binary, under `ModelProviderInfo`) | `strings` on the Codex binary |
| Those can be overridden for the built-in ChatGPT provider through `-c` on `codex app-server` | Refuted: app-server refuses any `model_providers.openai` key | agno-cli-models `reports/2026-10-01-substrate-checks.md` |
| The Claude Agent SDK sends messages often enough for an idle limit | Verified with partial messages on: longest gap 5.55 s in 14 healthy runs. Without them a long answer is silent (37.5 s). | Same report. Multi-minute thinking, API retries and rate-limit waits were not observed. |
| agno-cli-models can see every app-server message (`Rpc.inbox`) | Verified | `codex/rpc.py`; the probe wrapped it |

## Design assertions

- An idle limit MUST be measured on CLI protocol messages, not only on the events Agno sees.
- A stalled call MUST be typed STALL in Sendesis, and MUST remain a failover trigger.
- Qualification MUST NOT score a case without a measured answer as a miss or as clean.
- A receipt with any unmeasured case MUST read UNKNOWN.
- `idle_timeout_s` MUST be part of what a receipt certifies (config fingerprint and profile hash).
- A Claude idle default MUST NOT be set without a measurement of Claude's event cadence.
- The wall-clock limit MUST stay. The idle limit is added to it and never replaces it.

## Out of scope

- The isolation leak found in the same run: the user's skills block, a multi-agent developer prompt, and the `Collab`, `SleepTool` and `CodexHooks` features reach every Codex call. It is a separate item for agno-cli-models.
- Retrying TIMEOUT or ERROR in qualification. Only STALL gets a retry, because only a stall has evidence that a retry recovers.
- Re-running the codex-gpt qualification. That waits until both parts land, so the next receipt certifies the new behavior.

## Order of work

1. agno-cli-models, in its own session: `idle_timeout_s`, `CliStallError` and the fingerprint change, released as a tag. Tests use a fake app-server that goes silent mid-answer.
2. Sendesis: pin the new tag. Add `Outcome.STALL`, `idle_timeout_s` in the profile schema and model, the qualify retry and unmeasured cases, and the receipt fields. Unit tests use the scripted fake model raising `CliStallError`.
3. Re-run `sendesis qualify security-reviewer codex-gpt`. Any stall now shows up as STALL with its retry, not as a 300 s timeout.

## Decisions recorded

Recorded in Sendesis's `decisions.jsonl`, provenance human:

- `stall-is-not-a-miss` (dec-038618ace90a)
- `idle-limit-upstream` (dec-4ab5fff8293f)
- `stall-retry-once` (dec-5e74b139f525)

## Upstream requests

These are recorded in Sendesis's `decisions.jsonl` with the tags `upstream-request`, `pending` and `target:agno-cli-models`. They stand in for the `upstream_report` record planned for ReasonHold 0.2. A later Sendesis decision that supersedes a request closes it.

All four are closed as of agno-cli-models v0.1.2:
- housekeeping by dec-cb012bcea61f;
- isolation leak by dec-9fea3a9de7a5;
- substrate checks by dec-9100675d7844;
- idle limit by dec-d93fbe6aed26.

- `request-agno-cli-models-idle-limit` (dec-acb04313987e): `idle_timeout_s`, `CliStallError`, the fingerprint change, tests, and a release tag.
- `request-agno-cli-models-substrate-checks` (dec-5799c9b63ac7): measure the Claude Agent SDK's message cadence, and verify Codex's `stream_idle_timeout_ms` override.
- `request-agno-cli-models-codex-isolation-leak` (dec-477114059d7c): the skills block, the multi-agent prompt and user features that reach Codex calls.
- `request-agno-cli-models-housekeeping` (dec-996cadd56574): export `CliModel`, and add claude 2.1.287 to the tested set.
