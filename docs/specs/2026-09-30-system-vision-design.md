# System vision: Sendesis, ReasonHold and agno-cli-models on Agno

| | |
|---|---|
| Status | Draft for review |
| Date | 2026-09-30 |
| Scope | The whole system: what each project is for, where the boundaries sit, how they work together, and the order they are built in. Each project gets its own spec and plan after this one. |
| Replaces | `docs/PLAN.md` as the source of truth for scope, once approved. PLAN.md stays in git history. |
| Inputs | `README.md`, `docs/PLAN.md`, `docs/AGNO_HANDOFF.md`, the Agno spike (`agno` worktree `argo-spike`, `spike/FINDINGS.md`), `Ariadne/DOCS-RAG.md`, the Auctor folder (`docs/architecture/requirements.md`, `decisions.jsonl`), Phases 1 and 2 of this repo, and the design conversation of 2026-09-30. |

## 1. Why this document exists

Sendesis was first designed around NVIDIA NeMo Switchyard as its model-routing fabric. Several concepts were shaped by that fabric: a role was a Switchyard route, read-only enforcement lived in the proxy, and routing policy sat beside a transport. Phases 1 and 2 then built a thin engine that drives `claude -p` and `codex exec` as subprocesses.

The Agno spike (2026-09-30) changed the ground. Agno, a Python agent framework, can use Claude Code and Codex as models through their official clients, with full tool loops, session resume, structured output, streaming and human approval pauses. Agno also has agents, workflows, knowledge, tools and hooks. That makes a much larger Sendesis possible, and it makes Agno the natural place to feed ReasonHold's project knowledge to every model.

This document sets the north star before any further building.

## 2. Goals and audience

**Audience.** Open-source products for other developers first. The author's projects (Ariadne, Nebulon, Sendesis itself) are the first users, not the target. Configuration must not assume one machine, one directory layout or one set of local services.

**Goals.**

1. Sendesis v1 runs a **full engineering team**: roles that design, plan, implement, test, review and keep documentation true, as a multi-model team under rules written in code.
2. ReasonHold tells any agent **what it should believe** about a repository: which documents govern which code, what has been retracted, which source ranks higher, and what was decided and why.
3. Both work for people who use Agno and for people who do not.
4. Every claim that a model can fill a role is backed by evidence (receipts), and every multi-model loop has to earn its place against cheaper baselines (the gate).

**Non-goals for v1.** AgentOS serving. Multi-machine compute routing. Any LLM-led orchestration. ReasonHold generating text. Automatic promotion of model-proposed bindings.

## 3. Decisions taken in this design

| # | Decision | Choice |
|---|---|---|
| 1 | Audience | Open-source product first |
| 2 | Relationship to Agno | ReasonHold is standalone (core library, CLI, MCP server) with an Agno integration package. Sendesis is built on Agno. |
| 3 | NVIDIA Switchyard | Optional transport only. A profile may point at a Switchyard or PAIR endpoint. Nothing in the core depends on it. |
| 4 | Sendesis v1 headline | A full engineering team (design, plan, implement, verify) |
| 5 | Human gates | Configurable per workflow, with shipped defaults |
| 6 | Interface | CLI plus MCP server |
| 7 | Default workflow | Ariadne's governance workflow, rebuilt as a multi-model Sendesis team. ReasonHold supplies its data and tools, and ships a lighter single-agent skill pack. |
| 8 | ReasonHold storage | Re-tested in the ReasonHold spec. Auctor's "Weaviate only" decision stands unless an embedded store passes the seven required capabilities. |
| 9 | Model providers | The product supports any Agno model. "Cloud only through subscription CLIs, plus local" is the author's deployment rule, not a product rule. |
| 10 | Client surfaces | `claude -p`, the Claude Agent SDK, `codex exec` and `codex app-server` are allowed, always with the CLI's own login state. No stored OAuth tokens. |
| 11 | CLI-backed Agno models | Their own package, `agno-cli-models`, under Silicon-Wraith. Sendesis depends on it. It may be offered to Agno upstream later. |
| 12 | Build order | `agno-cli-models`, then ReasonHold, then Sendesis |
| 13 | How Sendesis sits on Agno | Declarative workflows compiled to Agno `Workflow` objects (approach A) |
| 14 | Qualification path | Qualification runs a role as a seat would run it, through the profile's Agno model class. The Phase 2 one-shot runners retire. |
| 15 | Manifest name | `reasonhold.yaml` for new projects; `sync-doc.yaml` read as a legacy name |
| 16 | Decision record ids | Derived deterministically from `topic` and `datetime` for existing records; written explicitly from now on |
| 17 | Receipts | Each project qualifies its own profiles. Sendesis does not ship receipts; it publishes gate reports as evidence. |
| 18 | Run persistence | SQLite by default, Postgres as a supported option |
| 19 | Where a run works | In the worktree and branch it is started from |
| 20 | Ungated cross-model loops | Allowed with a prominent warning |
| 21 | Plan gate | Off by default |
| 22 | Worker roles without a suite | Allowed as provisional, with a prominent warning |

## 4. System overview

```
                    ┌──────────────────────────────┐
                    │           Sendesis           │  roles, qualification, router,
                    │  (built on Agno, CLI + MCP)  │  workflows, adjudication, run record
                    └──────┬───────────────┬───────┘
                           │ uses          │ uses
              ┌────────────▼───┐   ┌───────▼──────────────────┐
              │ agno-cli-models│   │ reasonhold-agno          │  knowledge, tools,
              │ ClaudeCodeModel│   │ (Agno integration pkg)   │  pre-run hook, skills
              │ CodexModel     │   └───────┬──────────────────┘
              └───────┬────────┘           │ wraps
                      │              ┌─────▼──────────────────┐
                      │              │ reasonhold (core + MCP)│  docs, decisions,
                      │              │ no Agno dependency     │  retractions, governance map
                      │              └────────────────────────┘
                      ▼
       claude / codex binaries (own login)    local and API models via Agno's own classes
```

Dependencies point one way. ReasonHold knows nothing about models, roles or Sendesis. `agno-cli-models` knows nothing about roles or ReasonHold. Sendesis uses ReasonHold as its default context provider but runs without it.

**Flows between the parts.**

- Sendesis gives every seat ReasonHold's context for the paths in scope: governing documents, active retractions and relevant decisions.
- Sendesis writes back. Approved designs, resolved conflicts and preserved dissent become ReasonHold decision records, with `supersedes` where they retract documentation and provenance pointing at the Sendesis run.
- Any endpoint-based profile may sit behind Switchyard or PAIR. The core has no knowledge of either.

### 4.1 Why there is no LLM team leader

Agno's `Team` lets a leader model delegate to members and write the final answer. Sendesis does not use that for orchestration, because:

1. Adjudication must be a rule in code. A leader that merges findings is an LLM judge and can drop minority findings, which Sendesis promises to keep.
2. Reviewers must look first without seeing each other. A leader sees everything and chooses what to pass on.
3. Only the router picks models (PLAN.md D11). A leader delegating work is a second, unqualified router.
4. Leader calls add cost and make control flow vary between runs, which breaks budgets and the gate's equal-cost comparison.
5. Flow written in code can be unit-tested with fake agents. Flow in a prompt cannot.

The workflow's control flow is code. Models do the work inside seats. A single seat may use an Agno `Team` internally if a role needs it.

## 5. agno-cli-models

**Purpose.** Make the official Claude Code and Codex clients usable as ordinary Agno models.

**API.** Two Agno `Model` subclasses that override `aresponse` and `aresponse_stream`:

- `ClaudeCodeModel(id, effort, cwd, builtin_tools=[...], permission_mode=...)`, driven by the Claude Agent SDK.
- `CodexModel(id, effort, cwd, sandbox="read-only" | "workspace-write", ...)`, driven by `codex app-server`.

Agno tools become CLI tools: through an in-process MCP server for Claude, and through `dynamicTools` for Codex. Each CLI tool call runs through Agno's `arun_function_calls`, so Agno's hooks, limits and approval detection apply.

**Isolation on by default** (measured in Phase 2):

- Claude: no settings sources, strict MCP config, claude.ai connectors off, auto-memory off, slash commands off.
- Codex: `features.apps=false`, web search disabled, user config ignored.
- Both: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `CODEX_API_KEY` and every `CLAUDE_*` variable removed from the child environment.

`config_fingerprint()` returns a hash of these settings for receipts.

**Auth.** The CLI's own login state only. This deliberately departs from the spike, which used `CLAUDE_CODE_OAUTH_TOKEN` and a separate `CODEX_HOME`.

**Reporting.** Per run, into Agno's metrics: input, cached, output and reasoning tokens; observed model; CLI version; list cost where the CLI gives one. Rate limits raise a typed `ModelRateLimitError` (Claude SDK `RateLimitEvent`, Codex `account/rateLimits/updated`). Timeouts raise their own type.

**Hardening before 1.0** (from the spike's open items):

1. Persist the CLI session id in Agno session data.
2. Replay history for Codex when no CLI session exists yet.
3. Design and test Codex approvals: decline the tool call, resume after the human decides.
4. Verify Claude call-ID matching under parallel calls to the same tool.
5. Fix the sync path inside a running event loop and the interpreter-exit warnings.

**Versions.** Supported CLI versions are declared; an unknown version warns. `codex app-server` is experimental and pinned.

**Tests.** Unit tests replay recorded SDK and app-server transcripts. Real calls only in tests marked integration.

## 6. ReasonHold

**Purpose.** Answer "what should I believe?" about a repository along three axes: scope (which documents govern this code), time (what has been retracted) and rank (which source wins). Keep the decision log. Never generate text: every answer traces to a committed document, decision record or manifest entry, which keeps it trustworthy, deterministic and free of any chat-model dependency. Judgment happens in the calling agent, which writes through ReasonHold's tools.

**Source of truth: plain files committed in the user's repository.** The index is derived and rebuildable.

- **Manifest** (`reasonhold.yaml`; `sync-doc.yaml` read as legacy): corpus globs, areas, checks (`reads` to `validates_against` is the document-code mapping), the authority ladder (moved from code into the manifest, Auctor R-10), and a `candidates` section for model-proposed bindings awaiting human promotion.
- **Decision log** (`decisions.jsonl`, append-only): the current fields plus a stable `id` (derived for existing records from `topic` and `datetime`), `supersedes_records` (a decision retiring earlier decisions without editing the file, R-06), and `provenance` (human, agent, or Sendesis run id and role).

**Derived index.** Structure-aware chunkers from docs-rag. An embedding provider protocol `{embed, dims, model_id}` with Ollama and OpenAI-compatible implementations, and a model-identity guard (R-16). One collection per project, named from the manifest. Weaviate until the embedded-store test passes. The index behaviors Ariadne learned the hard way stay pinned by tests: `FIELD` tokenization of paths, insert before deleting stale chunks, verified inserts, the binary-file guard, loud schema drift.

**Operations** (one library API exposed three ways):

- Belief: `search_docs` (authority-ranked, retractions inline), `search_decisions`, `governing_docs(path)` (R-02), `retractions_for(path)`, `conflicts(path)` (two unretracted governing documents at the same rank; exact rule settled in the ReasonHold spec, R-11).
- Exact: symbol and inventory queries, `freshness`. Absence claims use exact queries, never vector search.
- Writes: `store_decision` with a fixed order (validate, embed, append, index) and an idempotency key so retries cannot duplicate records; `propose_binding`, which writes to `candidates` only. A human promotes candidates through the CLI.
- Governance: `coverage` (code that no document governs, R-03) and `preamble` (session-start summary).

**Delivery.**

1. Python library.
2. CLI: `reasonhold index | search | decide | govern | coverage | freshness | preamble | candidates`.
3. MCP server for any MCP client.
4. A skill pack and hook recipes for Claude Code and Codex: the single-agent form of the discipline.
5. `reasonhold-agno` (optional extra): an Agno knowledge/retriever, a toolkit, and a pre-run hook that injects the preamble plus governing documents and retractions for the files a run will touch.

**First users.** Ariadne, then Nebulon, through the legacy manifest reader with their decision logs imported as they are. Their vendored `docs-rag/` copies retire once the deletion criteria in Auctor's ledger are met.

## 7. Sendesis concepts and files

All files are YAML or JSON and validated by `sendesis validate`.

**Role** (`roles/<id>.yaml` plus prompt). A durable contract for one kind of expertise.

- `kind`: `worker` (produces an artifact) or `reviewer` (produces findings against `finding.json`).
- `tools`: `read`, `search`, `edit`, `shell`, `web`, mapped by each model class to native controls. Reviewer roles can never have `edit` or `shell`; `validate` enforces it.
- `context`: what the role needs from the context provider, such as `governing_docs` for paths in scope, `decisions` on a topic, `retractions`.
- Unchanged from Phase 1: `inputs`, `output_schema`, `definition_of_done`, `qualification`, `budgets`.
- Status `provisional` applies to a worker role without a qualification suite. It may run, with a prominent warning.

**Profile** (`profiles/<id>.yaml`). How a model is reached.

- `model: {class, id, effort, ...}` replaces the `runner` enum. Classes include `claude_code`, `codex`, `openai_like` (local or Switchyard endpoints) and any Agno provider.
- `family` stays, for diversity rules. CLI classes keep a CLI version pin.

**Receipt** (JSON, written once, never edited). As in Phase 2, plus the model class's `config_fingerprint()`. `single` certifies one profile in one role. `team_gate` certifies that a workflow's cross-model loop beat cheaper baselines for a role.

**Workflow** (`workflows/<id>.yaml`).

- `stages`, in order, each with `seats`. A seat names a role, a count, a diversity rule (for example `distinct_families: 2`) and `blind: true | false`.
- `loops`: round cap and stop rule.
- `gates`: which stages pause for a human and which answers are offered (approve, reject, edit, send back).
- `adjudication`: the named rule.
- `writes`: what is recorded to the context provider on approval.
- `budgets`: per run and per stage.

**Run record** (`runs/<run-id>/`). Per-stage artifacts, findings with states, dissent, gate answers and who gave them, seat-to-profile assignments (unblinded only in the final report), costs, warnings, and a Markdown report. It is the source of the decisions the run writes to ReasonHold.

**Placement in a user's project.** Shipped defaults (roles, workflows, suites) live in the package. A project overrides or adds under `.sendesis/{roles,profiles,workflows,suites}/`. Receipts go to `.sendesis/receipts/`, committed. Run records go to `.sendesis/runs/`, ignored by git by default; reports and the decisions they produce are committed. Each project qualifies its own profiles. The Sendesis repository keeps its current top-level layout because it is both the product and its own first user.

## 8. Sendesis runtime

The pipeline is validate, route, compile, execute on Agno, record.

**Router**, the only component that chooses models. For each seat:

- Candidates are the role's `failover_order`, filtered to enabled profiles whose receipt holds (Phase 2 `effective_status`). Provisional worker roles accept enabled profiles without a receipt and record a warning.
- The stage's diversity rule applies across its seats. The first acceptable profile in order wins, and the assignment is recorded.
- On rate limit, timeout or error, the seat is reset to the stage's starting commit and rerun on the next qualified profile that still satisfies diversity. If none remains, the stage stops with a refusal naming what is missing.

**Compiler** (workflow YAML to Agno `Workflow`):

- One seat is a `Step`; several seats are a `Parallel` group.
- Blind seats are wrapped in an executor that passes only the stage's original inputs, never peer outputs. Reviewers are labeled A, B, and so on, never by model.
- Loops become `Loop` with a stop condition computed in code: no new confirmed finding in a round, or the round cap.
- Adjudication is an executor step implementing PLAN.md D7: deduplicate by file, overlapping lines and category; confirmed when two reviewers agree or the evidence reproduces; otherwise disputed and kept; minority findings go to `dissent` and are never dropped.
- Gates are `HumanReview` steps offering the declared answers.
- Writes are an executor step that calls the context provider.
- Any step may be a plain Python executor, for users who need more than the YAML offers.

**Seat agent.** An Agno `Agent` with the profile's model instance, the role prompt as instructions, role tools mapped by the model class, the context-provider toolkit, a pre-run hook injecting context for the paths in scope, and the role's output schema.

**Where a run works.** In the git worktree and branch it is started from. A feature already lives in its own worktree, so the team works on that feature's branch.

- A stage starts only on a clean tree. Otherwise Sendesis stops and asks the user to commit or stash. It never commits the user's changes.
- Each stage ends with a commit on the branch ("design: ...", "plan: ...", "implement: ..."), so branch history shows what the team did.
- Failover rollback resets to the stage's starting commit. Because the stage started clean, this can only discard the team's edits from that stage.
- A lock file allows one active run per worktree. Separate features in separate worktrees run in parallel.
- While a stage executes, the worktree belongs to the run; edits by the user are detected and the run refuses to continue. At a gate the worktree is the user's, and an "edit" answer resumes from the user's commit.
- Sendesis never merges or pushes.
- The project must be a git repository.

**Persistence and resume.** Agno's workflow session store, SQLite under `.sendesis/` by default, Postgres through one setting (`store: postgres://...`). Both are tested. A run paused at a gate survives restarts and resumes from the CLI or MCP.

**Budgets.** Per-seat timeout and turn limit; token ceilings per stage and per run. Exceeding one stops the stage and surfaces it at the next gate, or fails the run if no gate follows.

**The gate (PLAN.md D8).** A cross-model review loop without a `team_gate` receipt for its role still runs, with a warning at start, in the run record, and at the top of the report: "ungated loop: no evidence yet that this beats cheaper baselines for role X". `sendesis gate` produces the evidence as in PLAN.md.

## 9. The default workflow: `feature`

Ariadne's governance workflow (`feature-workflow`, `review-design-doc`, `validate-plan-against-design`, `validate-code-against-design`, `sync-docs`, AGENTS.md Gate 2) as a multi-model team. The mapping below follows `Ariadne/DOCS-RAG.md`; the Sendesis spec checks it against the skill text line by line.

| Stage | Seats | Notes |
|---|---|---|
| 0. Orient | none (code) | ReasonHold: governing docs for touched areas, relevant decisions, active retractions, index freshness. A stale index is a warning. |
| 1. Design | Architect (worker); 2 Design Reviewers (blind, distinct families) | Adjudicate, revise until no new confirmed finding or the cap. **Gate on by default.** On approval, the design's decisions go to ReasonHold with `supersedes` and run provenance (Gate 2, made mechanical). |
| 2. Plan | Planner (worker); Plan Validators (blind, distinct families) | Same review loop. Gate off by default. |
| 3. Implement | Implementer (worker, `edit` + `shell`); Test Engineer (worker) | One commit per plan task. |
| 4. Verify | Code Validators and Security Reviewer (blind, distinct families) | Adjudicate; confirmed findings return to the Implementer up to the round cap. |
| 5. Doc sync | Doc Syncer (worker) | Manifest checks through ReasonHold exact queries; patches documentation drift; proposes binding candidates, never promotes them. |
| 6. Final | none (gate) | **Gate on by default.** Branch diff, all findings with states, dissent. On approval, resolved conflicts and dissent are recorded in ReasonHold. |

Any skipped or overridden stage is recorded as a decision, which preserves Ariadne's `bypass-feature-workflow` rule.

Smaller shipped workflows reuse the same roles on existing artifacts: `review-design`, `review-plan`, `review-code`, `sync-docs`.

**Roles (nine):** Architect, Design Reviewer, Planner, Plan Validator, Implementer, Test Engineer, Code Validator, Security Reviewer, Doc Syncer.

**Qualification of worker roles.** Implementer and Test Engineer get executable suites in v1 (seeded tasks with hidden tests). Architect and Planner run as provisional until a rule-only grader exists.

## 10. Interfaces

**CLI** (`sendesis`): `validate`, `qualify <role> <profile>`, `gate <workflow>`, `receipts`, `run <workflow> [--request "..."]`, `status [run-id]`, `answer <run-id> approve|reject|edit|send-back`, `resume <run-id>`, `report <run-id>`.

**MCP server:** `list_workflows`, `start_run`, `run_status`, `pending_gates`, `answer_gate`, `get_report`, and `critique` (one round of review of an artifact from the host session by a reviewer of the other model family, from PLAN.md). `start_run` returns a run id at once and the run continues in a detached process; the host polls and answers gates.

Codex as an MCP host depends on an unrun probe (`spike/mcp_net_probe.py`): whether an MCP server launched by Codex escapes Codex's sandbox. It must pass before Codex is a supported host.

## 11. Errors and testing

**Errors.** Every failure is typed (rate limit, timeout, error, budget exceeded, invalid output, lock held, dirty tree) and recorded in the run record. The router fails over where it can; otherwise the run stops with a refusal that names what is missing. The only deliberate degradations are provisional roles and ungated loops, and both carry warnings.

**Testing.** Unit tests use a fake Agno model, so compile, route, adjudication and gate logic run without spending quota. Golden runs replay recorded transcripts end to end. Real calls only in tests marked integration. Each package owns its tests.

## 12. Migration of existing work

**Sendesis repository.**

- `docs/PLAN.md` is replaced by this document and a new roadmap; it stays in history.
- `README.md` "Model Routing" and "Local and Distributed Inference" are rewritten: Switchyard and PAIR become optional transport.
- `CLAUDE.md` hard constraints are reworded: the subscription-CLI rule applies to this repository's own runs; the Agent SDK and `codex app-server` are allowed; "never extract or reuse subscription OAuth tokens" stays.
- Phase 1 and 2 code: schemas, `validate`, `suite`, `scoring` and `receipts` are kept and evolved. The runners' parsing and isolation knowledge moves into `agno-cli-models`. Existing receipts stay as written; after the profile schema changes they read UNKNOWN, which is correct.

**Spike.** Moves from the Agno worktree to a new `agno-cli-models` repository under Silicon-Wraith.

**Auctor.** Its requirements (R-01 to R-23), decisions and triage move into the ReasonHold repository, with the remaining "Auctor" names (collection, server instructions, package paths) renamed.

**Ariadne and Nebulon.** Migrate to ReasonHold after its first release.

## 13. Roadmap

Each milestone gets its own spec, plan and exit criterion.

1. **M1: `agno-cli-models` 0.1.** Hardening list, isolation fingerprint, typed errors, transcript fixtures, integration tests.
2. **M2: ReasonHold 0.1.** Core extraction; manifest with authority ladder; record ids; `governing_docs`; coverage; `store_decision` fix; MCP server; skill pack; `reasonhold-agno`; embedded-store test. Exit: Ariadne runs on it.
3. **M3: Sendesis on Agno.**
   1. Role and profile schema v2; qualification on the seat path.
   2. Router and failover.
   3. Compiler and the `review-*` workflows.
   4. Worker roles and the `feature` workflow.
   5. MCP server.
   6. Gate runs for the review roles.

## 14. Open items

These are carried into the project specs, not decided here.

1. **Qualifying the Architect and Planner.** No rule-only grader exists yet.
2. **ReasonHold conflict rule** (R-11): what exactly counts as a conflict.
3. **Embedded-store test** for ReasonHold against the seven required capabilities.
4. **Codex approvals** in `agno-cli-models`.
5. **Schema-validity threshold.** The Security Reviewer requires 0.98 at the Wilson lower bound. With p = 1 the lower bound is n / (n + 1.96²), so 100 of 100 gives 0.963 and the bar needs about 189 outputs. Lower the threshold, judge this metric on its point value, or raise `min_cases`.
6. **Labels with sink locations.** Pilot labels sit on the lines a CVE fix changed. A correct finding at the sink can fall outside the 3-line slack (cve-0003: label line 14, sinks at 52 and 64). Allow several acceptable ranges per label.
7. **Reasoning tokens in cost matching.** The CLIs count them differently; the gate matches on total tokens.
8. **Codex MCP sandbox probe** (`spike/mcp_net_probe.py`).
9. **PyPI names** for `sendesis`, `reasonhold` and `agno-cli-models`.
10. **Agno version pinning.** Agno changes quickly; pin and test against declared versions.
11. **Codex session files.** Model confirmation reads the rollout under `$CODEX_HOME/sessions`, so every Codex call leaves a file containing its prompt. Decide whether `agno-cli-models` cleans these up or documents them.
