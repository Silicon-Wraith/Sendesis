# M3: Sendesis on Agno

| | |
|---|---|
| Status | Draft for review |
| Date | 2026-10-01 |
| Scope | Roadmap milestone M3 of the system vision: Sendesis rebuilt on Agno, from schema v2 to gate evidence for two review roles. |
| Authority | Implements `docs/specs/2026-09-30-system-vision-design.md` (sections 7 to 11 and roadmap M3). Where this spec is more specific, it governs M3. |
| Inputs | The system vision spec; Sendesis's decision log; Phases 1 and 2 of this repository; agno-cli-models 0.1; ReasonHold 0.1.1; Ariadne's governance skills (`feature-workflow`, `review-design-doc`, `validate-plan-against-design`, `validate-code-against-design`, `sync-docs`, `bypass-feature-workflow`) and AGENTS.md gates 1 to 3, read read-only on 2026-10-01; the design conversation of 2026-10-01. |

## 1. Scope

M3 turns Sendesis into a multi-model engineering team built on Agno. Roles, profiles and workflows are files. A router picks only qualified profiles. A compiler turns workflow YAML into Agno `Workflow` objects. Ten roles run the `feature` workflow and the small `review-*` workflows, using agno-cli-models for Claude and Codex and ReasonHold for project knowledge. Sendesis has a CLI and an MCP server, and M3 ends with gate evidence for two review roles.

### 1.1 Stages and exit criteria

One spec; each stage gets its own plan, pull request and exit criterion.

| Stage | Delivers | Exit criterion |
|---|---|---|
| M3.1 | Schema v2 (role, profile, workflow, receipt, finding); labels with several ranges; qualification through the Agno model classes; the subprocess runners retire | The Security Reviewer re-qualifies on the seat path; Phase 2 receipts read UNKNOWN |
| M3.2 | Router and failover | Cut one provider mid-stage: the stage resets and finishes on a qualified profile, or refuses naming what is missing |
| M3.3 | Compiler, evidence pack, adjudication, run record, `review-code`, `review-design`, `review-plan`; CLI `run`, `status`, `answer`, `resume`, `report` | `review-code` runs on the local tier and on two cloud families, with blind seats and recorded adjudication |
| M3.4 | Worker roles; the `feature` workflow with the per-task inner loop; Doc sync limits; skips; `--brief`, `--request` and `--design` starts | **Checkpoint A:** a real small feature in one of the operator's repositories runs from brief to an approved branch, with its decisions in that repository's ReasonHold log |
| M3.5 | MCP server | A run is started and its gates answered from a Claude Code session |
| M3.6 | Code Reviewer suite; gate runs | **Exit B:** `team_gate` reports for the Security Reviewer and the Code Reviewer, win or lose |

### 1.2 Test tiers

| Tier | Model | When it runs | What it proves |
|---|---|---|---|
| Unit | A scripted fake Agno model | Every run, default | Routing, failover, blinding, adjudication, loops, gates, budgets: all logic in code |
| Local | Ollama and vLLM through Agno's own classes; marker `local` | On purpose; free | Real structured output, tool use, retries and timeouts; whole workflows end to end |
| Integration | `ClaudeCodeModel`, `CodexModel`; marker `integration` | On purpose; spends subscription quota | The subscription CLIs: auth, isolation, sandbox and network enforcement, CLI quirks |

Golden runs replay recorded transcripts from the local and integration tiers end to end, in the unit tier.

### 1.3 Out of scope for M3

An interactive Clarify stage (deferred, perhaps indefinitely); executable suites for the Implementer and Test Engineer (a later milestone); graders for the Architect and Planner (they stay provisional); Codex approvals; AgentOS serving; multi-machine routing; cross-project upstream reports.

## 2. Roles

Ten roles. Every role without a qualification suite is **provisional**, reviewers included: it may run, with a prominent warning at run start, in the run record and at the top of the report.

| Role | Kind | Tools | Suite in M3 |
|---|---|---|---|
| Architect | worker | read, search, edit (docs) | none: provisional |
| Design Reviewer | reviewer | read, search | none: provisional |
| Planner | worker | read, search, edit (docs) | none: provisional |
| Plan Validator | reviewer | read, search | none: provisional |
| Test Engineer | worker | read, search, edit, shell | none: provisional |
| Implementer | worker | read, search, edit, shell | none: provisional |
| Code Validator | reviewer | read, search | none: provisional. Contract review: code against the design and its assertions |
| Code Reviewer | reviewer | read, search | **built in M3.6.** Correctness and the project's standards |
| Security Reviewer | reviewer | read, search | existing pilot (30 cases) and smoke set |
| Doc Syncer | worker | read, search, edit (limited, section 7) | none: provisional |

"edit (docs)" means code restricts the seat's edits to its own artifact path (the design or plan file), with the same fail-and-reset rule as the Doc Syncer (section 7.2).

Role prompts carry the Ariadne rules that do not depend on Ariadne itself: the claim and hypothesis discipline; "do not suggest code changes" for the Plan Validator and "do not suggest design changes" for the Code Validator; "group findings by cause"; "read every hit before reporting it"; the direction of authority per stage (design review: the design alone; plan: design over plan; code: design over code; doc sync: docs over code unless the docs failed to track approved work). Repository policy such as "greenfield, no backward compatibility" comes from the target repository's documents, not from Sendesis's prompts.

## 3. Files and schema v2

All files are YAML or JSON, validated by `sendesis validate`. Shipped defaults live in the package; a project adds or overrides under `.sendesis/{roles,profiles,workflows,suites}/`, with receipts committed in `.sendesis/receipts/`. The Sendesis repository keeps its top-level layout.

**Role v2** (`roles/<id>.yaml` plus prompt).

- `kind`: `worker` or `reviewer`.
- `tools`: from `read`, `search`, `edit`, `shell`. `validate` refuses `edit` or `shell` on a reviewer. `network` is always false at role level; a stage may grant loopback (section 3, Workflow).
- `context`: what the seat's pre-run hook requests from the context provider (governing docs and retractions for the paths in scope; decisions on the stage's topic).
- `qualification` is optional; without it the role is provisional. Each metric has `basis`: `wilson_lower` or `point`.
- The Phase 1 `team` block is removed: loop settings belong to workflows, and team mode follows the `team_gate` receipt.
- Kept: `inputs`, `definition_of_done`, `output_schema`, `failover_order`, `budgets`.

**Profile v2** (`profiles/<id>.yaml`).

- `model: {class, id, effort, ...class options}` replaces `runner`, `model`, `reasoning_effort`, `cli`, `endpoint`, `sandbox` and `extra_args`. Classes: `claude_code`, `codex`, `openai_like` (Ollama, vLLM, Switchyard or PAIR endpoints) and `agno:<provider>`.
- `family` stays, for diversity rules. CLI classes pin `cli_version`.
- `enabled`, `timeout_s` and `max_turns` stay. The sandbox is never set per profile: it is derived from the role's tools and the stage's network setting (section 8).

**Receipt v2.** As in Phase 2, plus the model class's `config_fingerprint()`. Each score records its basis. `kind` is `single` (one profile in one role) or `team_gate` (a workflow's cross-model loop for a role). Phase 2 receipts have no fingerprint and read UNKNOWN, which is correct.

**Finding v2** (`schemas/finding.json`). Each finding has:

- `id`, `claim`, `location` (`file`, `line_start`, `line_end`).
- `severity`: `blocking`, `refine` or `note`. This drives gating. The Security Reviewer keeps an optional `impact` from `critical` to `info`.
- `category`: from an enumerated list per role. Design review: internal contradiction, cross-document conflict, upstream misalignment, scope leakage, underspecified, unimplementable, ownership, untestable, substrate not real, placeholder, decision conflict. Plan validation: missing assertion, phase boundary, coverage gap (forward and inverse), duplicate requirement. Contract: assertion failed, import violation, write-target violation, test missing, test not run, test weak. Correctness: per the Code Reviewer suite's categories. Security: a CWE id. Doc sync: doc drift, code drift. Every list includes `ambiguous`, which always routes to the operator.
- `resolution` for contract findings: `change_code`, `change_design` or `clarify` (Ariadne's three-way verdict).
- `evidence`: one or more typed items, `code_quote` (file, lines, text), `doc_quote` (path, section, text), `test_result` (test id from the evidence pack) or `query` (a ReasonHold exact query and its expected result); and `claim_status`: `proven` or `hypothesis`.
- Set by code, never by the reviewer: `evidence_valid`, `state` (`confirmed`, `disputed`), `raised_by` (blinded label), `supporters`, `first_round`.

A reviewer's output also carries `checks`: one record per check its role defines, with outcome `findings`, `no_findings` or `could_not_run` and a note. Silence is never read as a check that ran.

**Workflow** (`workflows/<id>.yaml`, new).

- `stages`, in order. Each has `seats` (role, count, `distinct_families`, `blind`), an optional `inner_loop`, `loops` (round cap, stop rule), `gates` (on or off, and the answers offered), `evidence` (what the pack contains), `network` (`false` or `loopback`), `writes` (what goes to the context provider on approval) and `budgets`.

**Worker artifacts stay Markdown**, because the operator reviews them; code checks their required sections.

- Designs (`docs/specs/<date>-<slug>-design.md`): Problem; Design; Substrate reality (one row per assumed dependency, with status and evidence); Design assertions (concrete MUST, MUST NOT and MUST ONLY statements); Out of scope; Decisions to record.
- Plans (`docs/plans/<date>-<slug>-plan[-N].md`): tasks, each with `kind` (`change` or `verification`) and a Design Assertions block drawn from the design. A `verification` task enumerates the assertions it checks and changes nothing.

## 4. Qualification on the seat path

**One seat builder.** `build_seat(role, profile, context)` returns an Agno `Agent`: the profile's model class instance, the role prompt as instructions, the role's tools mapped to the class's native controls under the derived sandbox, the role's output schema, and optionally a context provider with its pre-run hook. Qualification and real runs both use it, so a receipt certifies the path production uses (vision decision 14). Qualification passes no context provider: each suite case carries its own files, which keeps receipts reproducible and independent of any repository's index.

**Runners retire.** `src/sendesis/runners/` is deleted in M3.1, once the Security Reviewer re-qualifies on the seat path. Parsing and isolation live in agno-cli-models; OpenAI-compatible endpoints go through Agno's own class.

**Receipts** are void when any of these changes: role version, profile hash, suite hash, CLI version, observed model, or the class's `config_fingerprint()`. Statuses stay QUALIFIED, FAILED and UNKNOWN, with an expiry.

**Metrics.** Recall and false positives per clean case are judged at the Wilson lower bound. Schema validity is judged on its point value, at least 0.98, counted after the one allowed retry; it is a hygiene check, not a skill estimate.

**Labels v2.** A label carries `ranges: [{file, start, end}, ...]`. A finding hits a label if it overlaps any range within the 3-line slack; several findings for one label count as one hit. Existing labels keep their single range; `cve-0003` gains its sink ranges at lines 52 and 64.

**The Code Reviewer suite** (M3.6). A 30-case pilot, then about 100 cases. About 70 percent are real diffs from permissively licensed projects (MIT, BSD, ISC, Apache) with one planted correctness bug each: a wrong condition, an off-by-one, a swallowed error, a leaked resource, a wrong API use, a broken invariant. About 30 percent are clean diffs. A `SOURCING.md` records provenance and licences; no model is used for labeling. Scorer and thresholds as for the Security Reviewer, tunable in the role file.

**Cheap first.** Every suite runs once on the local tier before any cloud qualification, to catch scorer and schema problems for free.

## 5. Router and failover

The router is the only component that chooses models.

**Candidates.** A profile is acceptable for a seat when it is enabled and either its receipt for the role is QUALIFIED, unexpired and still matches role version, profile hash, suite hash, CLI version and fingerprint, or the role is provisional (enabled is enough; a warning is recorded).

**Diversity.** `distinct_families: N` applies across a stage's seats of the same role. The per-task checker in the inner loop must be of a family other than the Implementer's assigned profile; this is a rule in code. The router fills seats in `failover_order`, backtracking when an earlier choice would make the rule impossible. When no assignment satisfies the rule, the stage refuses before any model call, naming the role, the families needed and the families qualified. Assignments are recorded; reviewers are labeled A, B and so on during the run and mapped to profiles only in the final report.

**Failover triggers.** Typed errors from agno-cli-models and Agno: rate limit, timeout (including no output), provider or process error, and output still invalid after the one retry. A budget overrun is not a failover trigger (section 8).

**Failover.** Record the attempt and its reason. Undo the seat's work: a worker seat resets the worktree to the seat's starting commit (the stage's start, or the current task's commit in the inner loop); reviewer seats write nothing. Pick the next acceptable profile that still satisfies diversity, re-checking the whole stage. Rerun the seat from its original inputs. A profile that hit a rate limit is skipped for the rest of the run. When nothing acceptable remains, the stage stops with a refusal naming what is missing.

Because a stage starts only on a clean tree and every task ends in a commit, a reset (`git reset --hard` to the recorded commit plus removal of untracked files the seat created) discards only the team's own uncommitted work in that seat.

## 6. Compiler, evidence pack and adjudication

**Compiler.** Workflow YAML becomes an Agno `Workflow`: one seat is a `Step`, several seats a `Parallel` group; blind seats are wrapped in an executor that passes only the stage's inputs and evidence pack, never a peer's output; `loops` become `Loop` with the stop condition computed in code (no new confirmed finding in a round, or the round cap); `inner_loop` becomes a per-task `Loop` inside the Implement stage; gates become Agno's human-review pause steps offering the declared answers; evidence, adjudication and context-provider writes are plain Python executors. Users may add their own Python executors. The M3.3 plan verifies Agno 3.0.x's pause-step API before building on it.

**Evidence pack.** Built by code before every review step and written to the run directory, so every reviewer receives identical files:

- the diff for the stage (or the task, in the inner loop) and the full contents of the files in scope;
- results of the tests the plan names, run by Sendesis in the worktree under the workers' sandbox and network setting;
- from the context provider: governing documents, retractions and decisions for the paths in scope, exact symbol inventories for those paths, and index freshness.

Anything that could not be produced is listed as missing. Reviewers may also call the context provider's exact-query tools during review. Claims that something is absent must come from complete inventories, never ranked search; the role prompts say so and adjudication treats a ranked-search absence claim as a hypothesis.

**Adjudication**, a rule in code, after each round:

1. **Validate.** Each reviewer output must validate against `finding.json`; one retry, then the seat has failed (and fails over, section 5).
2. **Verify evidence.** `code_quote` and `doc_quote` text must exist at the cited location (whitespace-normalized); a `test_result` must name a test that fails in the pack; a `query` must match what the context provider returns. A finding that fails is kept with `evidence_valid: false` and never blocks.
3. **Group.** Same file, line ranges overlapping within 3 lines, same category. A group's severity is the highest of its members.
4. **State.** A group is **confirmed** when two or more reviewers raised it with valid evidence, or one did and code reproduced it (a failing test in the pack, or an exact query). Otherwise it is **disputed**.
5. **Route.** Confirmed `blocking` and `refine` findings go back to the worker. `note` findings go to the report only. Disputed `blocking` findings and every `ambiguous` finding go to the top of the operator's next gate, where the operator sends back or overrules; the answer is recorded. Every finding not confirmed by the end of the run is kept in `dissent`; nothing is dropped.
6. **Checks.** Check records are merged; a check any reviewer reported as `could_not_run` is shown as such.

**Later rounds.** Reviewers receive a fresh pack for the revised artifact plus the earlier confirmed findings, identified by finding id and not by reviewer, and mark each resolved or not. "No new confirmed finding" is therefore measurable.

## 7. Workflows

### 7.1 Starting a run

`sendesis run feature --request "..."` or `--brief file.md` starts at Design. `--design docs/specs/x.md` starts at Plan; the skipped Design stage is recorded as a decision.

### 7.2 The `feature` workflow

| Stage | What happens |
|---|---|
| 0. Orient (code) | Context-provider freshness: a stale index is a warning; a configured but missing index stops the run and names `reasonhold index`. Paths in scope are mapped to areas, with a warning for unmapped paths (never a silent fallback to everything). Governing documents, retractions and decisions are gathered. The result goes into the run record. |
| 1. Design | The Architect writes the design with the required sections. Two blind Design Reviewers of distinct families review it; the round loop runs. **Design gate, on by default:** approve, edit, send back, reject or skip. On approval, the design's "Decisions to record" become context-provider decisions with `supersedes` where they retract documentation, and provenance `sendesis_run` with the run id and role. |
| 2. Plan | The Planner writes the plan (several numbered plans per design are allowed). Blind Plan Validators of distinct families review it; the round loop runs. Gate off by default. The plan is frozen once the stage passes. |
| 3. Implement | Per task, in order: the Test Engineer writes the tests from the task's assertions, preferring tests that fail if a forbidden behaviour returns, and commits; the Implementer makes them pass and commits; then the inner loop runs the tests the plan names and one Code Validator of another family checks the task's diff against the task's assertions. Confirmed failures return to the Implementer, up to 3 fix rounds per task, then the task escalates. A `verification` task changes nothing; the Code Validator only checks its assertions. |
| 4. Verify | Over the whole branch: two blind Code Validators of distinct families (contract), one Code Reviewer (correctness) and the Security Reviewer. Confirmed findings return to the Implementer, one commit per fix, until no new confirmed finding or the round cap. |
| 5. Doc sync | The Doc Syncer fixes factual drift only (names, paths, counts that no longer match approved code). Code restricts its edits to documents outside the specs, plans and architecture paths; an edit anywhere else fails the seat and resets it. A drifted design claim becomes a finding for the operator. It may propose context-provider bindings and never promotes them. |
| 6. Final (gate, always) | The branch diff summary, every finding with its state, dissent, the Doc Syncer's diff shown separately, skips and warnings. On approval, resolved conflicts and dissent are recorded in the context provider. The branch is left for the operator; Sendesis never pushes or merges. |

**Escalation.** Any worker may return `escalate` with a reason: the design is wrong for the code, a dependency is unavailable, a task would cross a boundary. The stage stops and the reason goes to the next gate, or to Final. The per-task fix cap escalates the same way.

### 7.3 Skips

Only from the CLI, never through MCP: `sendesis run ... --skip <stage> --reason "..."`, or `skip` as a gate answer from `sendesis answer`. A reason is required; Sendesis states what the skip loses ("Verify skipped: no blind review of the code against the design"). The skip goes into the run record and the report header, and becomes a context-provider decision with provenance `human` and the run id. Orient and Final can never be skipped.

### 7.4 Small workflows

`review-design <path>`, `review-plan <path>` and `review-code <range>`: one blind reviewer stage, adjudication and a report, no workers. `sync-docs`: the Doc Syncer with the same limits, followed by a gate.

## 8. Runtime

**Where a run works.** In the worktree and branch it starts from. Each stage starts only on a clean tree; otherwise Sendesis asks the operator to commit or stash and never commits the operator's changes. `.sendesis/run.lock` allows one run per worktree. Every stage and task ends in a commit (`design: ...`, `test: task 3 ...`, `implement: task 3 ...`, `fix: F-12 ...`, `docs: ...`), made with the operator's git identity and the trailers `Sendesis-Run: <id>` and `Sendesis-Role: <role>`. During a stage, a change by the operator (HEAD moved, or files changed that the team did not touch) stops the run. At a gate the worktree is the operator's, and an `edit` answer resumes from the operator's commit. Sendesis never merges or pushes. The project must be a git repository.

**Sandboxes**, derived from the role and the stage, never set by hand:

| Seat | Claude (`ClaudeCodeModel`) | Codex (`CodexModel`) |
|---|---|---|
| Reviewer | `Read`, `Grep`, `Glob` only | `read-only` sandbox |
| Worker with `edit` and `shell` | Claude Code sandbox on, network denied | `workspace-write`, no network |
| Stage with `network: loopback` | Sandbox allows 127.0.0.1 only | Only if the class can express loopback-only |

Seats run autonomously: no per-call approvals; the stage commits, the reset on failover and the gates are the human checkpoints. A profile whose class cannot enforce what a stage needs is excluded from that stage with a recorded reason, never run with wider access. Network rules do not affect reading: seats read any file their role's tools allow. The M3.3 plan verifies each class's configuration.

**Context provider (ReasonHold).** Through `reasonhold[agno]`:

- A pre-run hook injects the preamble plus governing documents and retractions for the paths in scope, so a seat starts knowing what is retracted even if it later reads a raw file.
- Seats get read tools (search, `governing_docs`, `retractions_for`, decisions, symbols, freshness, and `read_document` once ReasonHold provides it), and only the roles that need them get `propose_binding` and `report_conflict`.
- Seats never get `store_decision`. Decisions are written by Sendesis's own executors, only when the operator approves at a gate.
- Role prompts require checking `retractions_for(path)` before relying on a design document read directly.
- Without a context provider, runs still work, with a warning that no governing context was supplied.

ReasonHold calls run in Sendesis's process, outside the CLI sandboxes; "no network" restricts only the commands a model runs itself.

**Persistence.** Agno's workflow session store, SQLite at `.sendesis/runs.db` by default, Postgres through `store: postgres://...`; both tested. A run paused at a gate survives restarts and resumes with `sendesis resume`. Artifacts, evidence packs, raw seat outputs, adjudications and the report go under `.sendesis/runs/<run-id>/`, ignored by git. The report and the decisions it produces are committed.

**Budgets.** Per seat, a timeout and a turn limit from the role and profile. Token ceilings per stage and per run, counting total tokens. Exceeding one stops the stage and surfaces it at the next gate, or fails the run if no gate follows.

**Errors** are typed: rate limit, timeout, provider error, invalid output, budget exceeded, lock held, dirty tree, operator edit detected, sandbox unavailable, escalation. Every one is recorded. The router fails over where it can; otherwise the run stops with a refusal naming what is missing.

## 9. Interfaces

**CLI** (`sendesis`).

| Command | Purpose |
|---|---|
| `validate` | Validate every role, profile, workflow, suite and receipt |
| `qualify <role> <profile> [--local]` | Write a receipt; `--local` is the free dry run on the local tier |
| `receipts` | Statuses, expiries and why a receipt is void |
| `run <workflow> --request/--brief/--design ... [--skip <stage> --reason ...]` | Start a run |
| `status [run-id]`, `report <run-id>` | Inspect a run |
| `answer <run-id> approve\|reject\|edit\|send-back\|skip [--note ...] [--reason ...]` | Answer a gate |
| `resume <run-id>` | Continue a paused or interrupted run |
| `gate <role> [--pilot] [--rounds 1,4]` | Produce gate evidence |

**MCP server** (stdio): `list_workflows`, `start_run` (returns a run id at once; the run continues in a detached process), `run_status`, `pending_gates`, `answer_gate` (approve, reject, edit, send back; never skip), `get_report`, and `critique` (one review round of an artifact from the host session by a reviewer of the other family). Claude Code is a supported host. Codex as a host waits for the sandbox probe (`spike/mcp_net_probe.py`).

## 10. The gate

For the Security Reviewer and the Code Reviewer, four arms run on the same suite at matched total tokens (`PLAN.md` D8):

| Arm | What runs |
|---|---|
| Cross-model loop | Blind first pass, then author and critic alternate across families for R rounds, with rule adjudication |
| Same-model loop | The strongest profile critiques and revises its own work for the same R rounds |
| Single pass | The strongest profile once, with self-review |
| N-sample vote | The strongest profile sampled N times, majority by location |

Wilson intervals per arm and a paired bootstrap on the differences. Team mode for a role is allowed only when the cross-model loop beats all three baselines with non-overlapping intervals. A `team_gate` receipt and a report under `reports/` are written either way.

**Order.** The full gate on the local tier first (free; proves the machinery). Then the 30-case pilots at R = 1 and 4. Then the full suite at R = 1, 2, 4 and 8, only for a role whose pilot is not a clear loss.

**Quota.** Rough estimate: at R = 4 a case costs about 30 model calls across the four arms; 30 cases times 2 roles is about 2,000 calls at R = 4 and about 1,000 at R = 1, so the pilot is roughly 3,000 subscription CLI calls, and the full sweep several times that. Gate runs are resumable, may spread over days, and **pause on a rate limit instead of failing over**, because substituting a profile mid-gate would change what an arm measures.

## 11. Migration of this repository

Mostly in M3.1:

- Schemas move to v2 and a workflow schema is added. `roles/security-reviewer.yaml` and the four profiles are migrated. Phase 2 receipts stay as written and read UNKNOWN.
- `src/sendesis/runners/` is deleted; `qualify` is rebuilt on the seat builder; `suite`, `scoring`, `receipts` and `validate` evolve.
- Suite labels move to v2; `cve-0003` gains its sink ranges.
- The README sections "Model Routing" and "Local and Distributed Inference" are rewritten, with a decision that resolves their retractions.
- `CLAUDE.md`'s hard constraints are reworded as the vision's section 12 says: the subscription-CLI rule applies to this repository's own runs; the Claude Agent SDK and `codex app-server` are allowed; "never extract or reuse subscription OAuth tokens" stays.

## 12. Dependencies

- `agno` 3.0.x, pinned and tested against.
- `agno-cli-models`, pinned to a git tag.
- `reasonhold[agno]` v0.1.1 as an optional extra (`sendesis[reasonhold]`); Sendesis runs without it, with a warning.

Upstream needs, each verified first by the plan of the stage that needs it; if missing, they are taken to the owning repository (read across, write home):

1. agno-cli-models: for edit and shell seats, Claude Code's sandbox with network denied and with loopback-only; loopback inside Codex's sandbox.
2. ReasonHold 0.1.2: `read_document(path)`, which returns a document with retractions marked inline. M3 works without it, through the pre-run hook and the role prompt rule.

## 13. Decisions to record on approval

In Sendesis's decision log, provenance human, actor John Sheppard:

1. M3 is one spec built in six stages, with checkpoint A (a real feature run) and exit B (gate reports for two review roles).
2. Three test tiers: unit with a scripted fake model, local models, subscription integration.
3. Every role without a suite is provisional, reviewers included; M3 builds the Code Reviewer suite; executable worker suites come after M3.
4. Schema validity is judged on its point value; labels may carry several ranges.
5. Edit and shell seats run autonomously with no network, both families sandboxed alike, with a per-stage loopback allowance.
6. Runs start from `--brief` or `--request`, or from an approved `--design`; the interactive Clarify stage is deferred.
7. Skips come only from the CLI, with a reason, recorded as decisions; Orient and Final are never skippable.
8. Only confirmed findings loop; disputed blocking findings go to the operator's next gate; findings with invalid evidence never block.
9. Ten roles: Code Validator (contract) and Code Reviewer (correctness) are separate.
10. Stage order is Verify, then Doc sync limited to factual drift, then Final, with the Doc Syncer's diff shown separately.
11. Implement runs a per-task inner loop: the named tests plus one other-family Code Validator.
12. Reviewers receive evidence packs built by code and exact-query tools; "could not run" is never a pass; absence claims need complete inventories.
13. Seats never call `store_decision`; decisions are written only at operator-approved gates.
14. Gate runs pause on rate limits instead of failing over.

## 14. Open items

1. Codex as an MCP host: the sandbox probe (`spike/mcp_net_probe.py`) is unrun.
2. Whether Codex's `workspace-write` sandbox blocks loopback, and whether loopback-only can be expressed.
3. Agno 3.0.x's pause-step API for gates (verified in M3.3).
4. The interactive Clarify stage, if ever.
5. Executable suites for the Implementer and Test Engineer.
6. Rule-only graders for the Architect and Planner.
7. Codex approvals in agno-cli-models.
