# Stall handling for model seats

Status: proposed, for review. Not approved, not implemented.

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
- **Claude Code:** the default is `None` until its event cadence is measured. The Claude Agent SDK may stay silent through long thinking. A Claude default is set only from a measurement, never by analogy with Codex.
- `idle_timeout_s` goes into `config_fingerprint()`. It changes what counts as a failed call, so a receipt must certify it.
- **Rejected for now: Codex's own `stream_idle_timeout_ms`.** It lets Codex reconnect before the idle limit fires. But it is a per-provider setting, and overriding it for the built-in ChatGPT provider through `-c` is unverified. A reconnect also replays the request, which is not visible to the caller. The design does not depend on it. Revisit it after the substrate check below.

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
| Those can be overridden for the built-in ChatGPT provider through `-c` on `codex app-server` | Unverified | |
| The Claude Agent SDK sends messages often enough for an idle limit | Unverified | Measure before setting a Claude default |
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

## Decisions to record

- `stall-is-not-a-miss`: qualification scores only measured cases. Any unmeasured case keeps the receipt UNKNOWN.
- `idle-limit-upstream`: the idle limit lives in agno-cli-models and is measured on protocol messages. Sendesis only sets it per profile and types the error.
- `stall-retry-once`: a stall gets one retry in qualification, and is a failover trigger in runs without skipping the profile for the rest of the run.
