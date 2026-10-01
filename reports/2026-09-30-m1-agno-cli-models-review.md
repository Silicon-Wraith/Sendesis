# M1 agno-cli-models 0.1: execution ledger and final review

Branch m1 of /mnt/ml_storage/dev/projects/agno-cli-models (6007b8c..e7fcb61), tag v0.1.0. Plan: docs/plans/2026-09-30-m1-agno-cli-models.md. Deferred and parked items below are the 0.1.1 backlog.

## Execution ledger


Spec: /mnt/ml_storage/dev/projects/sendesis/docs/specs/2026-09-30-system-vision-design.md (section 5)
Code repo: /mnt/ml_storage/dev/projects/agno-cli-models ; worktree /mnt/ml_storage/dev/projects/agno-cli-models-m1 (branch m1)
Scripts run from the code worktree with the absolute plan path.

## Pre-flight scan

| Pair / task | Produces vs consumes | Finding |
|---|---|---|
| T1 -> T2 | clean_env used by versions.installed_version | consistent |
| T2 -> T3 | run_sync, session_marker, CliTimeoutError | consistent |
| T3 -> T4 | CliModel; T4 test defines Dummy(CliModel) | consistent (order fixed in plan) |
| T3 -> T7, T10 | usage_event(metrics, content, info{observed_model,cli_version,cli_session_id}); CLI ClassVar; empty content appends no message | consistent; both engines put marker via bridge.pause provider_data |
| T4 -> T7, T10 | ToolBridge(model, tools, messages, limit).run/pause/precomputed/needs_pause/functions | consistent |
| T5 -> T7 | build_options kwargs (model_id, effort, cli_path, cwd, system_prompt, builtin_tools, permission_mode, agno_tool_names, mcp_server, output_schema, resume, stream, hooks, max_turns); fingerprint(builtin_tools, permission_mode) | names match |
| T6 -> T7 | check_result(result, name, id), rate_limit_error(ev, name, id), usage_metrics, observed_model, CallIdMatcher.record/take | consistent |
| T8 -> T10 | Rpc.spawn(argv, env), DONE, request/send/reply/close | consistent; T10 tests use FakeRpc with same surface |
| T9 -> T10 | app_server_argv, thread_start/resume_params, turn_start_params, dynamic_tool, continuation_text, TurnTracker, PAUSE_TEXT, fingerprint(sandbox, builtin_tools) | consistent |
| T2 -> T9 | strict_schema used by turn_start_params | consistent |
| T1 self | tests vs _env code | consistent |
| T2 self | stated "17 passed" = 12 common + 5 versions | consistent |
| T3 self | 7 tests listed, expected 7 | consistent; stream test depends on ModelResponse default event (plan gives fallback) |
| T4 self | 6 tests, 6 expected | consistent |
| T5 self | 6 tests | consistent |
| T6 self | lists 12 tests (8 translate + 4 matcher), says 13 | count mismatch |
| T7 self | 11 tests | consistent |
| T8 self | 5 tests | consistent |
| T9 self | lists 16 tests, says 17 | count mismatch |
| T10 self | creates model.py + edits __init__ | consistent |
| T11 self | Agno pause API names hedged in plan text | implementer must verify names against pinned Agno |
| T12 self | README only | consistent |

Ruling: expected pass counts in T6 (13) and T9 (17) are off by one against the tests the plan lists; the listed tests are binding, counts are indicative; cost if wrong: none, a missing test would still be caught by review against the listed test names.
Ruling: T11 Agno pause/continue API names may be adapted to the pinned Agno 3.0.x after checking agno/run sources, as the plan allows; cost if wrong: integration tests fail visibly.

## Progress
Task 1: verified ⚠️ items myself: initial commit 6007b8c has LICENSE/README/.gitignore; worktree m1 exists; venv py3.11; 4 passed.
Task 1: minor (deferred): REMOVED_KEYS omits ANTHROPIC_AUTH_TOKEN (and ANTHROPIC_BASE_URL/OPENAI_BASE_URL) which could bypass subscription login or reroute; final review should decide (security-relevant)
Task 1: minor (deferred): no test pins CLAUDE_CODE_OAUTH_TOKEN removal (covered by prefix rule)
Task 1: minor (deferred): is_removed lacks docstring; typing.Mapping vs collections.abc
Task 1: complete (commits 6007b8c..751aca3, review clean)
Task 2: minor (deferred): strict_schema drops a property literally named "default"/"$id"/"$schema" (strips keys inside properties maps); real bug, plan-mandated code; final review should decide
Task 2: minor (deferred): strict_schema optional enum gets None appended but type stays non-null; may duplicate "null" in type lists
Task 2: minor (deferred): text_of raises on non-JSON-serializable content (use default=str); transcript_prompt drops tool messages undocumented; run_sync no contextvars note; no tests for installed_version nonzero/timeout or errors.py
Task 2: complete (commits 751aca3..36de08d, review clean)
Task 3: Ruling: structured-output parse failure (plan-mandated `except Exception: pass`) -> narrow to pydantic ValidationError/ValueError, log a warning via agno.utils.log.log_warning, record "parse_error" in last_run_info; do not raise (Agno's own models leave parsed=None); cost if wrong: callers wanting a hard failure must check parsed/last_run_info
Task 3: minor (deferred): early stream abandon relies on async-gen GC to close the CLI; timeout window includes consumer time and relabels any inner TimeoutError; sync response_stream buffers; resolved_cwd default dir not enforced empty/0700; last_run_info shared mutable state; no validation of required info keys
Task 3: fix round 1/5 (3 addressed, 0 open; stream empty-final append, parse-error logging, contract tests; commits 89e79ea..5e6c425)
Task 3: minor (deferred): aresponse_stream does no structured-output parsing (parse_error only on non-stream path); duplicate agno.metrics import in tests
Task 3: complete (commits 36de08d..5e6c425, review clean)
Task 4: minor (deferred): ToolBridge.pause executes a non-pausing tool (no needs_pause guard); engines must only call pause after needs_pause; carry to T7/T10
Task 4: minor (deferred): precomputed keyed by tool_call_id across whole history; engines must use globally unique call ids (Claude tool_use_id, Codex callId); carry to T7/T10
Task 4: minor (deferred): stop_after_tool_call not surfaced; result_store not passed; test gaps (needs_pause for requires_user_input/external_execution, raising tool, single message after pause, pause unknown name)
Task 4: complete (commits 5e6c425..0bf80cd, review clean)
Task 5: ⚠️ resolved: --disable-slash-commands verified in 2026-09-30 Phase 2 probe (skills 0); blank ANTHROPIC_API_KEY treated as unset is asserted by T11 test_claude_isolation (apiKeySource == none)
Task 5: minor (deferred): env test only checks ANTHROPIC_API_KEY; blanking snapshot at build time; REFUSED_PERMISSION_MODES exact-match (no allow-list); hooks and acceptEdits branch untested; ENV_POLICY manual version string
Task 5: complete (commits 0bf80cd..d97f7dd, review clean)
Task 6: parked; reviewer minor "thinkingTokens not a real modelUsage key"; Ruling: the real CLI emits it (2026-09-30 Phase 2 probe: modelUsage claude-haiku-4-5 thinkingTokens 36; SDK TypedDict is incomplete); code stands; cost if wrong: reasoning_tokens reads 0
Task 6: minor (deferred): \b429\b / rate.?limit regex runs over result text too; a context-overflow message mentioning "429" would be classed as rate limit (prefer api_error_status for 429); usage_metrics with None/{} untested; observed_model tie picks first key; matcher has no stale-entry cleanup (one per run); rate_limit_error test doesn't check message
Task 6: complete (commits d97f7dd..2acc5c1, review clean)
Task 7: ⚠️ resume-after-defer behavior (same tool_use_id on re-fire, "Continue." prompt, first result is the answer) → verified by T11 approval integration tests on the real CLI; reviewer's out-of-tree probe confirmed run-exactly-once with fakes
Task 7: minor (deferred, SHOULD FIX in final wave): no unit test drives the PreToolUse hook + MCP handlers (defer, precomputed, bridge.run from handler, "Continue." prompt, stop after first result)
Task 7: minor (deferred, SHOULD FIX): query() call outside try and aclose before _DONE in pump finally → a pump setup failure surfaces as CliTimeoutError after timeout_s instead of the real error
Task 7: minor (deferred, SHOULD FIX): hook strips exact "mcp__agno__" prefix but pause path uses split("__")[-1] → tool names containing "__" misparse and the run ends empty
Task 7: minor (deferred): version unreadable → re-checks and re-warns every call, sync subprocess blocks loop (use sentinel / to_thread); session marker read from consumer-set state (record in pump); swallowed second cancellation
Task 7: complete (commits 2acc5c1..23a3f6f, review clean)
Task 8: review needs fixes (non-dict JSON line kills reader; >16MiB line kills reader; request after reader done raises raw OSError and leaks pending future; named risks untested); fix round 1 dispatched to original implementer (haiku)
Task 8: minor (deferred): close() not idempotent, does not close stdin/transport, signals only direct child; stderr DEVNULL loses diagnostics; asserts for runtime invariants
Task 8: fix round 1/5 (3 addressed, 1 open; oversized-line error still generic to waiters; plus non-dict JSON forwarded to inbox instead of skipped; commits 28dc939..b5ef8d1)
Task 8: minor (deferred): popped future may log "exception never retrieved" when send fails after reader finally; close() swallows caller cancellation
Task 8: fix round 2/5 (2 addressed + 1 minor, 0 open; specific oversized error to waiters, non-dict skipped, rpc closed error; commits b5ef8d1..c34cdc1)
Task 8: complete (commits 23a3f6f..c34cdc1, review clean)
Task 9: Ruling: plan-mandated use of tokenUsage.last for per-turn usage may undercount multi-call turns; schema is ambiguous; keep `last` for now, measure in Task 11 (log every thread/tokenUsage/updated during the Codex custom-tool integration test and compare last vs total delta), fix in the final wave if it undercounts; cost if wrong: Codex token counts in receipts and gate cost matching low for tool-using turns
Task 9: minor (deferred, SHOULD FIX): turn/completed with status inProgress sets done; only completed/interrupted should
Task 9: minor (deferred): serverOverloaded/sessionBudgetExceeded/unauthorized map to generic error (consider retry/failover types); tracker ignores thread/started model; no turnId/threadId filtering of stale notifications; coverage gaps (dynamic_tool, resume sandbox refusal, builtin_tools turn params, empty metrics)
Task 9: complete (commits c34cdc1..bad56ea, review clean)
Task 10: note: implementer wrote tests and code together, RED captured afterwards by removing model.py (tests are verbatim plan text)
Task 10: review needs fixes: (1) pause race (turn completes before interrupt -> paused run with content, or interrupt error fails run); (2) plan-mandated blanket {"decision":"decline"} wrong shape for most ServerRequest methods
Task 10: Ruling: replace blanket decline with schema-correct per-method replies (commandExecution/fileChange approvals {"decision":"decline"}; applyPatchApproval/execCommandApproval {"decision":"denied"}; mcpServer/elicitation {"action":"decline"}; everything else a JSON-RPC error -32601); schema is authoritative over plan code; cost if wrong: a server request still stalls until timeout
Task 10: Ruling (isolation gap found in review): codex app-server has no --ignore-user-config, and ~/.codex/config.toml defines MCP servers, so user MCP servers would load into every run (violates spec section 5 isolation). Fix in Task 9's app_server_argv: add a config override that disables user MCP servers, verified against a real app-server via initialize + mcpServerStatus/list (no model call, no quota); include the override in fingerprint(); cost if wrong: user MCP tools leak into Codex runs
Task 10: fix round 1/5 (3 addressed, 0 open; pause race, per-method server replies, user MCP servers disabled via per-server enabled=false (mcp_servers={} verified NOT to work); commits 36bed51..f352090)
Task 10: minor (deferred): project-level .codex config and plugin MCP servers not covered by the disable override; malformed user config silently loses isolation; only docs-rag probed (quoted dotted names unprobed); interrupt that never completes waits for server exit (bounded by timeout_s)
Task 10: complete (commits bad56ea..f352090, review clean)
Task 11: MEASURED: Codex thread/tokenUsage/updated `last` is per model call (turn with one tool call: last 5822 then 5853; total 5822 then 11675). TurnTracker using final `last` undercounts tool turns by ~half.
Task 9/10: Ruling (load-bearing, FINAL WAVE MUST FIX): TurnTracker turn usage = sum of `last` over this turn's thread/tokenUsage/updated notifications (equivalently final total minus pre-turn total); add a unit test with two updates; cost if wrong: Codex token counts wrong in receipts and gate cost matching
Task 11: verified: Codex approval confirm/reject pass on real app-server, so dynamic tools survive thread/resume (resolves Task 10 ⚠️); MCP isolation: docs-rag listed disabled, nothing started
Task 11: note: added sqlalchemy[asyncio] to dev extra (agno.db.sqlite needs it); continue_run uses run_response= not run_id=
Task 11: review needs fixes: reject test vacuous (no pause assertion); Codex usage bug (final `last`); Ruling: fix the token bug in this fix round (authorized package change) rather than the final wave, since the implementer holds the measurement; cost if wrong: none beyond scope creep of one task
Task 11: minor (deferred): token sequence printed only with -s and keyed on param id; custom-tool CALLS >= 1 lenient
Task 11: Ruling: reject test asserts wipe never ran and the rejected requirements are resolved, not "continued run not paused"; Claude may retry the rejected tool and pause again, matching spike FINDINGS.md ("model sometimes retries, which pauses again, correctly"); cost if wrong: a loop of re-pauses would not be caught by this test
Task 11: fix round 1/5 (2 addressed, 0 open; reject test non-vacuous, Codex usage summed per turn: real tool turn now 11643 input vs 5847 before; commits 6ed616f..e874657)
Task 11: minor (deferred): explicit null tokenUsage would raise AttributeError (pre-existing); debug print in integration test
Task 11: complete (commits f352090..e874657, review clean)
Task 12: review needs fixes (README stdin claim false for both transports) + 3 cheap minors folded in; fix round 1 dispatched
Task 12: Ruling: v0.1.0 tag (local, unpushed) will be re-pointed by the controller-dispatched fixer at the final head after the final whole-branch review, instead of tagging a pre-review commit; cost if wrong: none, tag never published
Task 12: minor (deferred): README pip install line before PyPI publish (user decision)
Task 12: fix round 1/5 (4 addressed, 0 open; commits d70bba2..4fa4919)
Task 12: complete (commits e874657..4fa4919, review clean)
Final review: Opus run stopped at user's request; re-dispatched on fable (user considers Fable the most capable model)
Final review (fable 5.1): With fixes. 0 Critical, 6 Important (env keys; Claude transport errors untyped + empty result silent + T7 one-liners; Codex malformed config loses isolation while fingerprint claims it; stale session resume has no fallback; streaming untested + sync buffering undocumented; strict_schema drops field named default). Agrees with all rulings.
Final review: Ruling: fix wave covers all 6 Important plus cheap minors 7 (README builtin_tools pre-approved), 8 (cache version miss), 9 (clientInfo version), 11 (KeyError -> CliProtocolError), 13 (README stream content note), 14 (null tokenUsage), 15 (Claude hook/handler unit test); defer minors 10 (stderr tail) and 12 (dynamicTools on resume, document); cost if wrong: two small diagnostics gaps remain in 0.1
Final fix wave: 9 commits 4fa4919..e7fcb61; unit 141 passed; stream integration 2 passed; Claude stale-session retry triggers on any pre-init failure while resuming except rate limit/context overflow (SDK cannot distinguish)
Final fix wave re-review (fable 5.1): all findings addressed, no new Critical/Important breakage (unit 141 passed -W error)
Final: parked; tests/test_codex_protocol.py::test_app_server_argv_isolates reads the developer's real ~/.codex/config.toml (fails on a machine with a malformed one); Ruling: real but test-only; fix with a CODEX_HOME tmp fixture in 0.1.1; cost if wrong: a spurious unit failure on such a machine
Final: parked; stale-session fallback replays transcript without tool calls/results, so a non-confirmation tool from an earlier turn could run again after a fallback, and README "confirmed tools run exactly once" does not hold across a fallback; Ruling: inherent to the requested fallback; document in README in 0.1.1; cost if wrong: a rare duplicate tool run after a stale session
Final: parked; Codex missing-rollout reply shape not verified with a real call; if the server exits instead of replying, the old typed error is raised (no regression); Ruling: verify when a stale thread occurs naturally
Final: note for Sendesis; a malformed local Codex config raises CliProtocolError (502), so Agno FallbackConfig.on_error treats it like a provider outage
Final: Ruling: controller re-pointed local unpushed tag v0.1.0 from d70bba2 to e7fcb61 (post-fix head); cost if wrong: none, tag never published
M1: complete (branch m1, 6007b8c..e7fcb61, tag v0.1.0)

## Final whole-branch review (Fable 5.1)

# Final whole-branch review: agno-cli-models 0.1 (branch m1, 6007b8c..4fa4919)

Reviewed: all 15 source files and 13 test files in /mnt/ml_storage/dev/projects/agno-cli-models-m1, README, pyproject, the 18-commit diff, spec section 5, plan constraints and review focus, the ledger, task-11-report.md. Unit suite run once: `.venv/bin/pytest -q -W error` gives 118 passed, 13 deselected. Integration tests not run (13 passed per task-11-report.md). Facts checked against the pinned claude-agent-sdk 0.2.163 and agno 3.0.11 sources. No em dashes in README, src or tests.

### Strengths

- Architecture matches the plan exactly: one `CliModel` base owns the Agno surface (timeout, sync wrappers, metrics, run info, pause tracking), `ToolBridge` routes every CLI tool call through `Model.arun_function_calls`, and each CLI has a pure builder, a pure translator and a thin engine with an injectable client. Engines are small (169 and 159 lines).
- Hard constraints hold everywhere: no `--bare`, no `bypassPermissions` (refused with ValueError, options.py:40), no `danger-full-access` (ALLOWED_SANDBOXES, protocol.py:26), no token reading or `CODEX_HOME` setting, `approvalPolicy: never`, `allowProviderModelFallback: False`, model and effort pinned on every call for both CLIs.
- Review Focus items 1-5 each have the pinned test the plan asked for, and they test the stated behavior (fresh session without markers, environ never mutated, timeout raises `CliTimeoutError`, `run_sync` inside a running loop, matcher pairs by arguments).
- Session persistence through `provider_data` is simple and robust: marker on the final assistant message, or on the assistant tool-call message for paused runs, so `continue_run` across processes works on both CLIs (integration `test_session_resumes_across_agent_instances` and both approval tests pass).
- Codex engine handles the hard cases found in review: pause race (turn completes before interrupt), one interrupt per run, later non-pausing tools declined with `PAUSE_TEXT`, schema-correct per-method replies to server requests, `-32601` for unknown requests, and user MCP servers disabled per server after `mcp_servers={}` was shown not to work.
- Token semantics are consistent across CLIs and were measured, not assumed: Codex `last` is per model call and is now summed per turn (11643 input on a real tool turn versus 5847 before the fix), with a unit test that failed before the fix.
- `Rpc` is well hardened for a 114-line client: oversized lines, non-JSON and non-dict lines, send after exit, pending futures failed with the specific reason, terminate then kill on close (`test_rpc_close_kills_hung_process` uses a SIGTERM-ignoring child).
- Errors are Agno's own classes with 5xx status codes, so `FallbackConfig.on_rate_limit`, `on_context_overflow` and `on_error` work without glue; verified against `agno/models/fallback.py`.
- README mechanics I checked against the code are correct: stdin handling, env blanking versus removal, version-warning cadence, `parse_error`, the approval flow, known limits. The gaps are the three noted below (Important 1, Important 5, Minor 7).

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. `src/agno_cli_models/_env.py:14` REMOVED_KEYS omits `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL` and `OPENAI_BASE_URL`. With `ANTHROPIC_AUTH_TOKEN` in the parent environment Claude Code authenticates with that bearer token instead of the login; with either `*_BASE_URL` the CLI is rerouted to an arbitrary endpoint. README:99 states "A CLI can never fall back to API billing by accident", which is false under these variables. The spec names four variables, but the README claim and the package's purpose make this a defect, not spec silence. Fix: add the three keys to `REMOVED_KEYS`, bump `ENV_POLICY`, and extend `tests/test_env.py::test_is_removed`.

2. `src/agno_cli_models/claude/model.py:115-133` Claude transport failures are not typed, and a stream that ends without a `ResultMessage` is a silent empty answer. The pump forwards any `Exception` and the consumer re-raises it raw, so `claude_agent_sdk` `ProcessError` (subprocess_cli.py:1157, nonzero CLI exit), `CLIConnectionError` and `MessageParseError` escape as SDK types although README:192-194 says `ModelProviderError` covers "other CLI errors" and `CliProtocolError` covers "the CLI exited". And if the generator finishes (`_DONE`) before a `ResultMessage` was seen, `_drive` returns with no usage event and `aresponse` returns `content=""` with no error; the Codex engine raises `CliProtocolError` in the same situation (codex/model.py:113-114). Fix: in the pump wrap non-Agno exceptions in `CliProtocolError(str(exc), self.name, self.id)` (chained), and in the `_DONE` branch raise `CliProtocolError("claude ended without a result")` when no `ResultMessage` was processed. Add a fake-query unit test for each. While in this block, apply the two one-liners from the T7 ledger: `deferred.name.removeprefix(prefix)` instead of `split("__")[-1]` (line 152), and put `_DONE` in its own inner `finally` so an `aclose()` failure cannot hang the consumer (lines 122-124).

3. `src/agno_cli_models/codex/protocol.py:32-44` versus `:51-54` The fingerprint asserts `"user_mcp_servers": "disabled"` unconditionally, but `_user_mcp_overrides` returns `[]` on `OSError` or `TOMLDecodeError`, so a malformed `~/.codex/config.toml` silently loads every user MCP server while the receipt says they were disabled. For a package whose value is receipts, the fingerprint must not claim isolation that was skipped. Fix: let a decode error raise (`ValueError` with the path), or at minimum record `user_mcp_overrides: "failed"` in the fingerprint input and `last_run_info`. Related and smaller: spec section 5 says Codex "user config ignored", but only MCP servers are neutralised; `notify`, `model_provider`/`model_providers`, `shell_environment_policy`, `[plugins]` (the local config has `plugins."github@openai-curated"`) and `~/.codex/AGENTS.md` still apply. README:213 should name these rather than say "covers MCP servers from your user config only", and the deviation from the spec should be stated as a known limit of `app-server` lacking `--ignore-user-config`.

4. `src/agno_cli_models/codex/model.py:94-97` and `src/agno_cli_models/claude/model.py:108-109` A persisted CLI session that no longer exists (user cleaned `$CODEX_HOME/sessions` or `~/.claude/projects`, or a different machine) has no fallback: `thread/resume` errors become `CliProtocolError`, Claude `--resume` fails (how it surfaces was not verified here; likely a transport error or an error `ResultMessage`), and because the marker lives in Agno's persisted history every later run of that Agno session fails the same way. Expected by a reasonable user: fall back to a fresh session with `transcript_prompt(rest)` and overwrite the marker on success. No test covers it. Fix: catch the resume failure, log a warning, and retry as the no-session path; add a fake-driven unit test on each engine.

5. `src/agno_cli_models/_base.py:156-160`, `tests/test_integration.py` Streaming has no end-to-end coverage, and sync streaming is not streaming. No integration test uses `stream=True` on either CLI; the plan has none either. `Agent.run(stream=True)` reaches `model.response_stream(**kwargs)` through `agno/models/fallback.py:221`, and our sync `response_stream` buffers the whole run before yielding, so a user who streams synchronously sees everything at once after the call completes; only `arun(stream=True)` streams. README has no streaming section. Fix: add one `arun(stream=True)` integration test per CLI (two calls of quota) and a README paragraph stating that sync streaming is buffered.

6. `src/agno_cli_models/_common.py:75` `strict_schema` strips `$schema`, `$id` and `default` from every dict, including the `properties` map, so a Pydantic model with a field named `default` (or `$id`) loses that field in the Codex output schema; Codex then omits it and validation fails with a `parse_error`. Fix: strip those keys only from schema nodes, not when the dict is the value of a `properties` key (walk `properties` entries directly). One test with a field named `default`.

#### Minor (Nice to Have)

7. `src/agno_cli_models/claude/options.py:42` Every `builtin_tools` entry goes into `allowed_tools`, meaning it is pre-approved and never prompts; `builtin_tools=("Bash",)` is unconditional Bash. This is the right design for a headless host, but README:72 says only "to allow". Say plainly: listed built-in tools run without a permission check.

8. `src/agno_cli_models/claude/model.py:50-54`, `codex/model.py:58-62`, `versions.py:26` When `--version` cannot be read, the miss is not cached: every call re-runs a blocking `subprocess.run` (up to 30 s) on the event loop and warns again. Cache a sentinel for the miss.

9. `src/agno_cli_models/codex/model.py:90` `clientInfo.version` is the literal `"0.1.0"`; use `agno_cli_models.__version__` (import inside the function to avoid the cycle) so it cannot drift.

10. `src/agno_cli_models/codex/rpc.py:19` `stderr=DEVNULL` discards the only diagnostic when `codex app-server` fails to start (bad flag, not logged in before `initialize`); the user sees "codex app-server exited". Capture a bounded stderr tail and include it in that `CliProtocolError`.

11. `src/agno_cli_models/codex/model.py:103` `res["thread"]["id"]` raises a bare `KeyError` on an unexpected response shape; wrap as `CliProtocolError`.

12. `src/agno_cli_models/codex/protocol.py:77-80` `thread/resume` does not pass `dynamicTools`, so a resumed thread only sees the Agno tools registered when the thread was started; a tool added to the agent later is invisible in that session. The spike showed tools survive resume, so this is a documentation item unless the resume schema accepts `dynamicTools`, in which case pass them.

13. `src/agno_cli_models/claude/model.py:136-139` versus `codex/protocol.py:124-125` Claude streams every text delta including pre-tool commentary, Codex only `final_answer` deltas. Consequence for Claude: the stored assistant message in stream mode is the concatenation of all deltas, not `ResultMessage.result`, so stream and non-stream runs persist different content. Acceptable for Agno, worth a README line.

14. `src/agno_cli_models/codex/protocol.py:132` `params.get("tokenUsage", {})` returns `None` when the key is present with a null value and then `.get` raises `AttributeError`; use `(params.get("tokenUsage") or {})`.

15. `tests/test_claude_model.py` No unit test drives the `PreToolUse` hook and the MCP handlers with a fake query (defer decision, precomputed result on resume, "Continue." prompt, stop after first result). The real-CLI integration tests cover it, but a regression there costs quota to detect. Worth adding together with fix 2, which touches the same code.

### Deferred-minor triage

T1 REMOVED_KEYS omits ANTHROPIC_AUTH_TOKEN/ANTHROPIC_BASE_URL/OPENAI_BASE_URL: MUST FIX BEFORE RELEASE, one line, security-relevant, and README:99 claims the opposite (Important 1).
T1 no test pins CLAUDE_CODE_OAUTH_TOKEN removal: OK TO DEFER, the prefix rule covers it; add one assert when touching test_env.py.
T1 is_removed docstring, typing.Mapping vs collections.abc: OK TO DEFER, cosmetic.
T2 strict_schema drops a property named default/$id/$schema: MUST FIX BEFORE RELEASE, silent structured-output corruption for a plausible field name, five-line fix (Important 6).
T2 optional enum gets None appended while type stays non-null, possible duplicate null: OK TO DEFER, OpenAI strict accepts it and no failure was observed.
T2 text_of raises on non-JSON-serializable content: OK TO DEFER, tool results are str or JSON in practice; use default=str later.
T2 transcript_prompt drops tool messages undocumented: OK TO DEFER, replay is the no-session fallback; document in 0.1.x.
T2 run_sync has no contextvars note: OK TO DEFER, documentation only.
T2 no tests for installed_version nonzero/timeout or errors.py: OK TO DEFER, trivial code paths.
T3 early stream abandon relies on async-gen GC: OK TO DEFER, asyncio's asyncgen hooks schedule aclose and the SDK close is bounded (about 20 s).
T3 timeout window includes consumer time: OK TO DEFER, conservative direction; document with the streaming note.
T3 relabels any inner TimeoutError: OK TO DEFER, only the asyncio.timeout can raise it in practice.
T3 sync response_stream buffers: OK TO DEFER as behavior, but README must say so (folded into Important 5).
T3 resolved_cwd default dir not enforced empty or 0700: OK TO DEFER, directory is created under the user's cache.
T3 last_run_info is shared mutable state: OK TO DEFER, the per-run copy is in run_output.model_provider_data.
T3 no validation of required info keys: OK TO DEFER, internal contract between base and two engines.
T3 aresponse_stream does no structured-output parsing: OK TO DEFER, Agno parses content at run end and README states non-stream only.
T3 duplicate agno.metrics import in tests: OK TO DEFER, cosmetic.
T4 ToolBridge.pause has no needs_pause guard: OK TO DEFER, both engines guard before calling pause.
T4 precomputed keyed by tool_call_id across the whole history: OK TO DEFER, both CLIs issue unique ids.
T4 stop_after_tool_call not surfaced: OK TO DEFER, the CLI owns the loop; list under Known limits later.
T4 result_store not passed: OK TO DEFER, no caller needs it yet.
T4 bridge test gaps (needs_pause variants, raising tool, pause unknown name): OK TO DEFER, small functions, low risk.
T5 env test checks only ANTHROPIC_API_KEY: OK TO DEFER, test_env.py covers the full policy.
T5 blanking snapshot taken at build time: OK TO DEFER, same process environment.
T5 REFUSED_PERMISSION_MODES exact match: OK TO DEFER, the SDK validates the PermissionMode literal.
T5 hooks and acceptEdits branch untested: OK TO DEFER, trivial kwargs passthrough.
T5 ENV_POLICY manual version string: OK TO DEFER, bump it with Important 1.
T6 rate-limit regex runs over result text: OK TO DEFER, only on is_error results and api_error_status is checked first.
T6 usage_metrics with None or {} untested: OK TO DEFER, guarded by `or {}`.
T6 observed_model tie picks first key: OK TO DEFER, ties are implausible.
T6 matcher has no stale-entry cleanup: OK TO DEFER, one matcher per run.
T6 rate_limit_error test does not check the message: OK TO DEFER, cosmetic.
T7 SHOULD FIX no unit test for PreToolUse hook and MCP handlers: OK TO DEFER, the real-CLI approval and custom-tool integration tests exercise it (Minor 15 recommends adding it with Important 2).
T7 SHOULD FIX query() outside try and aclose before _DONE: MUST FIX BEFORE RELEASE as part of Important 2, three lines in the same block (sdk.query itself is lazy, so the risk today is only a custom query_fn or an aclose failure).
T7 SHOULD FIX hook strips exact prefix but pause path uses split("__")[-1]: MUST FIX BEFORE RELEASE as part of Important 2, one line (`removeprefix`), same block.
T7 unreadable version re-checks and blocks the loop every call: OK TO DEFER, `claude --version` is fast; cache the miss in 0.1.x (Minor 8).
T7 session marker read from consumer-set state: OK TO DEFER, the init message arrives before any tool call.
T7 swallowed second cancellation: OK TO DEFER, cleanup path only.
T8 close() not idempotent, does not close stdin, signals only the direct child: OK TO DEFER, app-server is the direct child and terminate-then-kill is tested.
T8 stderr DEVNULL loses diagnostics: OK TO DEFER, nice to have (Minor 10).
T8 asserts for runtime invariants: OK TO DEFER, pipes are always set by spawn.
T8 popped future may log "exception never retrieved": OK TO DEFER, log noise only.
T8 close() swallows caller cancellation: OK TO DEFER, cleanup path only.
T9 SHOULD FIX turn/completed with status inProgress sets done: OK TO DEFER, `turn/completed` is terminal by name and the alternative trades an early return for a hang until timeout on an unknown status; current behavior is the safer one.
T9 serverOverloaded/sessionBudgetExceeded/unauthorized map to generic error: OK TO DEFER, ModelProviderError 502 still triggers on_error fallback; refine in 0.1.x.
T9 tracker ignores thread/started model: OK TO DEFER, thread/start result carries the model.
T9 no turnId/threadId filtering of stale notifications: OK TO DEFER, one turn per process.
T9 coverage gaps (dynamic_tool, resume sandbox refusal, builtin_tools turn params, empty metrics): OK TO DEFER, small pure functions.
T10 project-level .codex config and plugin MCP servers not covered: OK TO DEFER, README documents it; the local config has a plugins entry so verify in 0.1.x.
T10 malformed user config silently loses isolation: MUST FIX BEFORE RELEASE, the fingerprint then asserts isolation that did not happen (Important 3).
T10 only docs-rag probed, quoted dotted names unprobed: OK TO DEFER, json.dumps quoting is the TOML form; probe when such a name appears.
T10 interrupt that never completes waits bounded by timeout_s: OK TO DEFER, bounded.
T11 token sequence printed only with -s and keyed on param id: OK TO DEFER, diagnostic output.
T11 custom-tool CALLS >= 1 lenient: OK TO DEFER, models may legitimately call twice.
T11 explicit null tokenUsage would raise AttributeError: OK TO DEFER, one-line guard (Minor 14).
T11 debug print in integration test: OK TO DEFER, integration only.
T12 README pip install line before PyPI publish: OK TO DEFER, user decision; add a "from source" line if publishing waits.

### Rulings

Pre-flight expected pass counts in T6 and T9 off by one, listed tests binding: agree, the listed tests exist and pass.
Pre-flight T11 Agno pause API names adapted to pinned Agno: agree, continue_run(run_response=...) and friends exist in 3.0.11 and the integration run proves it.
T3 structured-output parse failure narrowed, logged, recorded, not raised: agree, matches Agno's own parsed=None convention and the failure is visible in last_run_info.
T6 thinkingTokens kept despite the SDK TypedDict: agree, the Phase 2 probe shows the CLI emits it and the worst case is reasoning_tokens 0.
T9 keep tokenUsage.last, measure in T11, fix in the final wave: agree, exactly the right order and the measurement found the undercount.
T10 per-method schema-correct server replies instead of the blanket decline: agree, schema beats plan code and the parametrized test pins each shape.
T10 disable user MCP servers per server, in argv and fingerprint: agree on the mechanism, with the reservation that it covers MCP only while the spec says "user config ignored" and the fingerprint does not reflect a failed override (Important 3).
T9/10 turn usage is the sum of `last` over the turn's updates: agree, 5822 + 5853 = 11675 equals the total delta.
T11 fix the token bug inside the T11 fix round rather than the final wave: agree, the implementer held the measurement and the change was one function plus a test.
T11 reject test asserts the tool never ran and the rejected requirements resolved, not "not paused": agree, a retry that pauses again is correct behavior and README documents it.
T12 v0.1.0 tag re-pointed after the final review: agree; the tag currently points at d70bba2, one commit behind HEAD, and must move to the post-fix head.

### Declined to judge

- PyPI name and publication, and the `pip install` line: user decision per the ledger and open item 9.
- Codex session files under `$CODEX_HOME/sessions`: open item 11, README documents it.
- Project-level `.codex` config and plugin MCP servers: README documents it; the spec's isolation list names user config.
- CLAUDE.md and AGENTS.md in a user-supplied `cwd` not hashed into the fingerprint: Sendesis receipt concern, outside this package.
- `tool_choice` ignored: the CLI owns the loop; not in the spec's API.
- `stop_after_tool_call` and `result_store` not honored: Agno executor details the spec does not mention.
- Agno version pinning beyond `<3.1`: open item 10.
- Honoring a user-set `CODEX_HOME`: deliberate per the plan's auth rule.
- One model instance shared by concurrent runs racing on `last_run_info`: Agno models are not documented as run-safe either.
- Default `max_turns=50`, default model ids, and `effort="high"`: product choices the spec leaves open.
- Claude re-firing a rejected tool and pausing again: CLI behavior, documented.
- Sync `response_stream` buffering as a design: judged only its documentation (Important 5).
- The SDK's own `--version` check and `CLAUDE_AGENT_SDK_VERSION` injection: SDK behavior.

### Assessment

**Ready to release 0.1?** With fixes

**Reasoning:** The package does what the spec and plan ask, the hard constraints hold, the integration run is clean and the per-task fix rounds landed; nothing here is Critical. Before tagging, fix the two items the ledger asked this review to rule on (T1 env keys, which README:99 contradicts; T2 `strict_schema`), the fingerprint-after-parse-failure gap (Important 3), wrap Claude SDK transport errors into the typed hierarchy with the two T7 one-liners (Important 2), and add the streaming note to README; then re-point v0.1.0 to that head. The resume fallback (Important 4) and the streaming integration tests (Important 5) can follow in 0.1.1 if the user prefers to ship now, but they are the next two things a real user will hit.
