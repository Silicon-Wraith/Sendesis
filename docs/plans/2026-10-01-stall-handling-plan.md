# Stall handling (parts 2 and 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sendesis types a CLI stall as `Outcome.STALL`, lets a profile set the idle limit, retries a stalled qualification case once, and keeps every case without a measured answer out of the scores.

**Architecture:**
- agno-cli-models v0.1.2 already raises `CliStallError`, a subclass of `CliTimeoutError`, when a CLI goes silent for `idle_timeout_s`; its default is 60 s.
- `seat.py` maps that error to a new outcome and records the stall details.
- `qualify.py` changes its loop: STALL joins INVALID as retried once.
  - A case whose final outcome is TIMEOUT, ERROR, STALL or RATE_LIMIT becomes *unmeasured*: it is left out of `compute_metrics` and listed on the receipt.
- The receipt gains `suite.n_measured` and a top-level `unmeasured` list. Any unmeasured case keeps the status UNKNOWN, as today.

**Tech Stack:** Python 3.11, Agno 3.0.11, agno-cli-models v0.1.2, jsonschema (Draft 2020-12), pytest.

**Spec:** `docs/specs/2026-10-01-codex-stall-handling-design.md`, sections 2 and 3. Part 1 of that spec is done upstream in agno-cli-models v0.1.2. Recorded decisions: `stall-is-not-a-miss` (dec-038618ace90a), `idle-limit-upstream` (dec-4ab5fff8293f), `stall-retry-once` (dec-5e74b139f525).

## Global Constraints

- Qualification MUST NOT score a case without a measured answer as a miss or as clean.
- A receipt with any unmeasured case MUST read UNKNOWN.
- A stalled call MUST be typed STALL in Sendesis, and MUST remain a failover trigger.
  - The router is not built yet (M3.2). This plan only types the outcome.
- `idle_timeout_s` MUST be part of what a receipt certifies.
  - agno-cli-models puts it in `config_fingerprint()`.
  - Setting it in a profile also changes the profile hash.
- The wall-clock limit MUST stay. The idle limit is added to it and never replaces it.
- Only INVALID and STALL get the one retry in qualification. TIMEOUT and ERROR get none, and RATE_LIMIT still stops the run.
- Unit tests use the scripted fake model (`tests/fakes.py`) or a scripted `seat_fn`. No real CLI call outside `@pytest.mark.integration`.
- Never edit a receipt by hand. In docs and user-facing text, do not use em dashes.
- Prefer warnings over hard failures in `sendesis validate` for settings that are merely ineffective.
- Run every command from the worktree root with `.venv/bin/...`.

## Review Focus

1. **A retry that also stalls:** the case must end up unmeasured, never scored as a miss. It is pinned in Task 3 by `test_stall_retried_once_then_unmeasured`.
2. **A clean case that stalls:** it must leave the false-positive denominator. Otherwise a stall reads as "no findings, perfect". Pinned in Task 3 by `test_unmeasured_clean_case_is_not_counted_clean`.
3. **Every case unmeasured:** there are no scores, the receipt still validates, and the status is UNKNOWN. Pinned in Task 3 by `test_all_cases_unmeasured_still_writes_a_valid_receipt`.
4. **Retries of different kinds:** a first INVALID answer followed by a STALL on the retry must end unmeasured. It must not get a second retry. Pinned in Task 3 by `test_invalid_then_stall_is_one_retry_and_unmeasured`.
5. **`CliStallError` wrapped by another exception:** it must still be typed STALL, not TIMEOUT or ERROR. Pinned in Task 2 by `test_stall_inside_another_error_is_still_a_stall`.

---

### Task 1: Profile `idle_timeout_s`

**Files:**
- Modify: `schemas/profile.json` (add the property)
- Modify: `src/sendesis/model.py:140-155` (`Profile`), `:191-204` (`load_profile`)
- Modify: `src/sendesis/seat.py:58-88` (`build_model`)
- Modify: `src/sendesis/validate.py:64-82` (`_check_profile`)
- Test: `tests/test_seat.py`, `tests/test_validate.py`

**Interfaces:**
- Produces: `Profile.idle_timeout_s: float | None` (default `None`, meaning "the model class's own default").
- Produces: `build_model` passes `idle_timeout_s=profile.idle_timeout_s` to `ClaudeCodeModel` and `CodexModel` only when it is not `None`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_seat.py`, add:

```python
def test_profile_idle_limit_reaches_cli_models_and_their_fingerprint(root: Path, tmp_path: Path):
    role = load_role(root / "roles" / "security-reviewer.yaml", root)
    for name in ("claude-opus", "codex-gpt"):
        path = root / "profiles" / f"{name}.yaml"
        default = build_model(load_profile(path, root), role, cwd=tmp_path, timeout_s=300)
        edit_yaml(path, lambda d: d.update(idle_timeout_s=45))
        model = build_model(load_profile(path, root), role, cwd=tmp_path, timeout_s=300)
        assert model.idle_timeout_s == 45 and model.timeout_s == 300
        assert model.config_fingerprint() != default.config_fingerprint()


def test_no_profile_idle_limit_keeps_the_class_default(root: Path, tmp_path: Path):
    role = load_role(root / "roles" / "security-reviewer.yaml", root)
    model = build_model(load_profile(root / "profiles" / "codex-gpt.yaml", root), role, cwd=tmp_path, timeout_s=300)
    assert model.idle_timeout_s == 60.0
```

Add `from conftest import edit_yaml` to the imports of `tests/test_seat.py`.

In `tests/test_validate.py`, add:

```python
def test_idle_limit_on_a_non_cli_profile_warns(root: Path):
    edit_yaml(root / "profiles" / "ollama-local.yaml", lambda d: d.update(idle_timeout_s=30))
    report = validate_repo(root)
    assert report.errors == []
    assert any("ollama-local.yaml" in w and "idle_timeout_s" in w for w in report.warnings)


def test_idle_limit_not_below_the_wall_clock_warns(root: Path):
    edit_yaml(root / "profiles" / "codex-gpt.yaml", lambda d: d.update(idle_timeout_s=300))
    report = validate_repo(root)
    assert report.errors == []
    assert any("codex-gpt.yaml" in w and "idle_timeout_s" in w and "timeout_s" in w for w in report.warnings)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_seat.py tests/test_validate.py -q -k "idle"`

Expected: FAIL. The schema rejects `idle_timeout_s` ("Additional properties are not allowed"), or `Profile` has no `idle_timeout_s`.

- [ ] **Step 3: Implement**

`schemas/profile.json`, under `properties`, after `max_turns`:

```json
    "idle_timeout_s": {"type": "number", "exclusiveMinimum": 0, "description": "Longest silence from the CLI a call tolerates, in seconds. claude_code and codex only; absent means the model class default (60 s in agno-cli-models v0.1.2). Part of the class's config fingerprint."},
```

`src/sendesis/model.py`, in `Profile`, after `max_turns`:

```python
    idle_timeout_s: float | None = None
```

In `load_profile`, after `max_turns=data.get("max_turns"),`:

```python
        idle_timeout_s=data.get("idle_timeout_s"),
```

`src/sendesis/seat.py`, in `build_model`:
- In the `claude_code` branch, just before `return ClaudeCodeModel(**kwargs)`, add the block below.
- In the `codex` branch, just before `return CodexModel(**kwargs)`, add the same block.

```python
        if profile.idle_timeout_s is not None:
            kwargs["idle_timeout_s"] = profile.idle_timeout_s
```

`src/sendesis/validate.py`, at the end of `_check_profile`:

```python
    if p.idle_timeout_s is not None:
        if p.model.cls not in CLI_CLASSES:
            report.warnings.append(f"{where}: idle_timeout_s applies only to claude_code and codex; model class {p.model.cls} ignores it")
        elif p.idle_timeout_s >= p.timeout_s:
            report.warnings.append(f"{where}: idle_timeout_s {p.idle_timeout_s} is not below timeout_s {p.timeout_s}, so the wall clock always fires first")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q`

Expected: all pass (134 passed, 3 deselected).

- [ ] **Step 5: Commit**

```bash
git add schemas/profile.json src/sendesis/model.py src/sendesis/seat.py src/sendesis/validate.py tests/test_seat.py tests/test_validate.py
git commit -m "Profile idle_timeout_s, passed to the CLI model classes"
```

---

### Task 2: `Outcome.STALL` in the seat

**Files:**
- Modify: `src/sendesis/seat.py:22` (import), `:35-55` (`Outcome`, `SeatResult`), `:201-244` (error typing in `run_seat`)
- Test: `tests/test_seat.py`

**Interfaces:**
- Consumes: `agno_cli_models.CliStallError` (v0.1.2). It subclasses `CliTimeoutError`, and its attributes are `idle_s: float`, `last_method: str | None` and `answer_open: bool`.
- Produces: `Outcome.STALL` with value `"stall"`.
- Produces: `SeatResult.stall: dict[str, Any] | None`. It is `{"idle_s": float, "last_method": str | None, "answer_open": bool}` when the outcome is STALL, and `None` otherwise.

- [ ] **Step 1: Write the failing tests**

In `tests/test_seat.py`, change the import line to `from agno_cli_models import CliStallError, CliTimeoutError, ModelRateLimitError`, and add:

```python
def stall_error():
    return CliStallError("codex sent nothing for 60.0s (last: item/started)", idle_s=60.0,
                         last_method="item/started", answer_open=True)


def test_stall_is_typed_with_its_details(root: Path):
    r = run(root, stall_error())
    assert r.outcome is Outcome.STALL
    assert r.stall == {"idle_s": 60.0, "last_method": "item/started", "answer_open": True}
    assert "CliStallError" in r.reason


def test_plain_timeout_is_still_a_timeout(root: Path):
    r = run(root, CliTimeoutError("no answer in 300s"))
    assert r.outcome is Outcome.TIMEOUT and r.stall is None


def test_stall_inside_another_error_is_still_a_stall(root: Path):
    try:
        try:
            raise stall_error()
        except CliStallError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        wrapped = outer
    r = run(root, wrapped)
    assert r.outcome is Outcome.STALL and r.stall["last_method"] == "item/started"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_seat.py -q -k "stall or plain_timeout"`

Expected: FAIL with `AttributeError: STALL`.

- [ ] **Step 3: Implement**

In `src/sendesis/seat.py`, change line 22 to:

```python
from agno_cli_models import ClaudeCodeModel, CliStallError, CliTimeoutError, CodexModel, ModelRateLimitError
```

In `Outcome`, after `TIMEOUT = "timeout"`:

```python
    STALL = "stall"
```

In `SeatResult`, after `reason: str = ""`:

```python
    stall: dict[str, Any] | None = None
```

Above `_is_timeout`, add:

```python
def _find_stall(err: BaseException | None) -> CliStallError | None:
    seen = []
    while err is not None and err not in seen:
        if isinstance(err, CliStallError):
            return err
        seen.append(err)
        err = err.__cause__ or err.__context__
    return None
```

In `run_seat`, replace this block:

```python
        if isinstance(err, ModelRateLimitError):
            result.outcome = Outcome.RATE_LIMIT
        elif _is_timeout(err):
```

with:

```python
        stall = _find_stall(err)
        if isinstance(err, ModelRateLimitError):
            result.outcome = Outcome.RATE_LIMIT
        elif stall is not None:
            result.outcome = Outcome.STALL
            result.stall = {"idle_s": stall.idle_s, "last_method": stall.last_method, "answer_open": stall.answer_open}
        elif _is_timeout(err):
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q`

Expected: all pass (137 passed, 3 deselected).

- [ ] **Step 5: Commit**

```bash
git add src/sendesis/seat.py tests/test_seat.py
git commit -m "Type CLI stalls as Outcome.STALL with idle time, last message and open-answer flag"
```

---

### Task 3: Qualification: retry a stall once, keep unmeasured cases out of the scores

**Files:**
- Modify: `src/sendesis/qualify.py:1-11` (docstring), `:141-161` (case loop), `:185-186` and `:210-223` (receipt)
- Modify: `schemas/receipt.json` (`suite.n_measured`, top-level `unmeasured`)
- Modify: `src/sendesis/cli.py:39-46` (print measured count)
- Test: `tests/test_qualify.py`

**Interfaces:**
- Consumes: `Outcome.STALL`, `SeatResult.stall` (Task 2).
- Produces, on the receipt:
  - `receipt["suite"]["n_measured"]: int`.
  - `receipt["unmeasured"]: list[{"case_id": str, "outcome": "timeout" | "error" | "stall" | "rate_limit"}]`, present only when non-empty.
- Rule: `CaseOutcome`s are appended only for measured cases, whose final outcome is OK or INVALID.
- Rule: retry once when the first outcome is INVALID or STALL, never twice.

- [ ] **Step 1: Write the failing tests**

In `tests/test_qualify.py`, add:

```python
def stalled():
    return SeatResult(Outcome.STALL, reason="CliStallError: codex sent nothing for 60.0s",
                      stall={"idle_s": 60.0, "last_method": "item/started", "answer_open": True})


def test_stall_retried_once_and_recovered_is_measured(qroot, tmp_path):
    plan = all_ok()
    plan["v1"] = [stalled(), ok([HIT])]
    seat_fn = scripted(plan)
    r = qualify(qroot, "security-reviewer", "claude-opus", seat_fn=seat_fn, version_fn=lambda b: PIN, now=NOW,
                workdir=tmp_path / "wd", runs_dir=tmp_path / "runs").receipt
    assert seat_fn.calls.count("v1") == 2
    assert r["status"] == "QUALIFIED" and r["suite"]["n_measured"] == 4 and "unmeasured" not in r
    logs = sorted(p.name for p in (tmp_path / "runs").rglob("v1*.json"))
    assert logs == ["v1.1.json", "v1.json"]
    assert json.loads(next((tmp_path / "runs").rglob("v1.1.json")).read_text())["stall"]["last_method"] == "item/started"


def test_stall_retried_once_then_unmeasured(qroot, tmp_path):
    plan = all_ok()
    plan["v1"] = [stalled(), stalled()]
    seat_fn = scripted(plan)
    r = qualify(qroot, "security-reviewer", "claude-opus", seat_fn=seat_fn, version_fn=lambda b: PIN, now=NOW,
                workdir=tmp_path / "wd", runs_dir=tmp_path / "runs").receipt
    assert seat_fn.calls.count("v1") == 2
    recall = next(s for s in r["scores"] if s["metric"] == "recall")
    assert recall["value"] == 1.0  # v2's one label, hit; v1 is not a miss
    assert r["suite"]["n_cases"] == 4 and r["suite"]["n_measured"] == 3
    assert r["unmeasured"] == [{"case_id": "v1", "outcome": "stall"}]
    assert r["status"] == "UNKNOWN" and "case v1: stall" in r["status_reason"]


def test_invalid_then_stall_is_one_retry_and_unmeasured(qroot, tmp_path):
    plan = all_ok()
    plan["v1"] = [SeatResult(Outcome.INVALID, reason="bad"), stalled()]
    seat_fn = scripted(plan)
    r = qualify(qroot, "security-reviewer", "claude-opus", seat_fn=seat_fn, version_fn=lambda b: PIN, now=NOW,
                workdir=tmp_path / "wd", runs_dir=tmp_path / "runs").receipt
    assert seat_fn.calls.count("v1") == 2
    assert r["unmeasured"] == [{"case_id": "v1", "outcome": "stall"}]


@pytest.mark.parametrize("outcome", [Outcome.TIMEOUT, Outcome.ERROR])
def test_timeout_and_error_are_not_retried_and_are_unmeasured(qroot, tmp_path, outcome):
    plan = all_ok()
    plan["v1"] = [SeatResult(outcome, reason="boom")]
    seat_fn = scripted(plan)
    r = qualify(qroot, "security-reviewer", "claude-opus", seat_fn=seat_fn, version_fn=lambda b: PIN, now=NOW,
                workdir=tmp_path / "wd", runs_dir=tmp_path / "runs").receipt
    assert seat_fn.calls.count("v1") == 1
    assert next(s for s in r["scores"] if s["metric"] == "recall")["value"] == 1.0
    assert r["unmeasured"] == [{"case_id": "v1", "outcome": outcome.value}]


def test_unmeasured_clean_case_is_not_counted_clean(qroot, tmp_path):
    plan = all_ok()
    plan["c1"] = [stalled(), stalled()]
    plan["c2"] = [ok([HIT])]  # one false positive on the only measured clean case
    r = run(qroot, plan, tmp_path).receipt
    fp = next(s for s in r["scores"] if s["metric"] == "false_positives_per_clean_case")
    assert fp["value"] == 1.0  # 1 finding / 1 measured clean case, not / 2


def test_all_cases_unmeasured_still_writes_a_valid_receipt(qroot, tmp_path):
    from sendesis.receipts import validate_receipt

    plan = {k: [stalled(), stalled()] for k in ("v1", "v2", "c1", "c2")}
    result = run(qroot, plan, tmp_path)
    r = result.receipt
    assert r["scores"] == [] and r["suite"]["n_measured"] == 0 and len(r["unmeasured"]) == 4
    assert r["status"] == "UNKNOWN"
    assert validate_receipt(qroot, json.loads(result.path.read_text())) == []


def test_rate_limited_case_is_listed_unmeasured(qroot, tmp_path):
    plan = {"c1": [SeatResult(Outcome.RATE_LIMIT, reason="ModelRateLimitError: usage limit")], "c2": [ok()], "v1": [ok()], "v2": [ok()]}
    r = run(qroot, plan, tmp_path).receipt
    assert r["suite"]["n_measured"] == 0 and r["unmeasured"] == [{"case_id": "c1", "outcome": "rate_limit"}]


def test_receipt_with_unmeasured_cases_validates(qroot, tmp_path):
    from sendesis.receipts import validate_receipt

    plan = all_ok()
    plan["v1"] = [stalled(), stalled()]
    result = run(qroot, plan, tmp_path)
    assert validate_receipt(qroot, json.loads(result.path.read_text())) == []


def test_cli_qualify_prints_measured_count(qroot, tmp_path, capsys, monkeypatch):
    import sendesis.qualify as q

    plan = {k: [ok(model="qwen-test")] for k in ("v2", "c1", "c2")}
    plan["v1"] = [stalled(), stalled()]
    monkeypatch.setattr(q, "default_workdir", lambda role_id: tmp_path / "wd")
    monkeypatch.setattr(q, "default_seat_fn", lambda root: scripted(plan))
    def local(d):
        d.update(enabled=True, family="qwen")
        d["model"].update(id="qwen-test")
    edit_yaml(qroot / "profiles" / "ollama-local.yaml", local)
    assert main(["qualify", "security-reviewer", "ollama-local", "--local", "--root", str(qroot)]) == 0
    out = capsys.readouterr().out
    assert "measured 3 of 4 cases" in out and "unmeasured: v1 (stall)" in out
```

The CLI test uses `ollama-local` with `--local`, as `test_cli_qualify_reports_local_flag` does, so no CLI version check runs.

Two existing tests stay unchanged and must still pass:
- `test_failed_call_is_unknown_and_names_case`, because the reasons still name the case.
- `test_rate_limit_stops_with_unknown`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_qualify.py -q`

Expected: the new tests FAIL. They fail on missing `n_measured` / `unmeasured`, on a stall not being retried, or on recall counting the unmeasured case as a miss.

- [ ] **Step 3: Implement**

`schemas/receipt.json`:
- In `suite.properties`, after `n_cases`, add:

```json
        "n_measured": {"type": "integer", "minimum": 0, "description": "Cases with a measured answer (final outcome ok or invalid). Scores are computed over these only. Absent on receipts issued before stall handling."}
```

- At the top level of `properties`, after `status_reason`, add:

```json
    "unmeasured": {
      "type": "array",
      "description": "Cases without a measured answer, with their final outcome. Never scored as a miss or as clean; any entry keeps the status UNKNOWN.",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["case_id", "outcome"],
        "properties": {
          "case_id": {"type": "string"},
          "outcome": {"enum": ["timeout", "error", "stall", "rate_limit"]}
        }
      }
    },
```

`src/sendesis/qualify.py`, the docstring's status rules become:

```python
"""`sendesis qualify <role> <profile>`: run a role's suite on one profile and
write a receipt.

A case is measured when its final outcome is OK or INVALID. INVALID and STALL
get one retry. A case that ends TIMEOUT, ERROR, STALL or RATE_LIMIT is
unmeasured: it is listed on the receipt and left out of every score, never
counted as a miss or as clean (decision stall-is-not-a-miss).

Status rules:
- UNKNOWN when the installed CLI version differs from the profile's pin
  (checked first, so no quota is spent), when any case is unmeasured, when
  the observed model is not the profile's model, when a metric cannot be
  computed, or when the suite has fewer cases than `min_cases`;
- otherwise QUALIFIED if every metric passes at the conservative end of its
  interval, else FAILED.
"""
```

Replace the case loop (the block from `outcomes: list[CaseOutcome] = []` through the `break`) with:

```python
    RETRIED = (Outcome.INVALID, Outcome.STALL)
    MEASURED = (Outcome.OK, Outcome.INVALID)
    outcomes: list[CaseOutcome] = []
    unmeasured: list[dict[str, str]] = []
    results: list[SeatResult] = []
    if not reasons:
        for case in suite.cases:
            message = build_message(role, case)
            cwd = prepare_workdir(workdir, case)
            result = seat_fn(role, profile, message, cwd, timeout_s)
            results.append(result)
            if result.outcome in RETRIED:  # one retry on invalid output or a stall
                _log(run_log, f"{case.id}.1", result)
                result = seat_fn(role, profile, message, cwd, timeout_s)
                results.append(result)
            _log(run_log, case.id, result)
            if result.outcome in MEASURED:
                valid = result.outcome is Outcome.OK
                findings = (result.output or {}).get("findings", []) if valid else []
                outcomes.append(CaseOutcome(case.id, case.clean, case.labels, findings, valid, True))
                continue
            unmeasured.append({"case_id": case.id, "outcome": result.outcome.value})
            reasons.append(f"case {case.id}: {result.outcome.value}: {result.reason[:200]}")
            if result.outcome is Outcome.RATE_LIMIT:
                reasons.append("stopped after rate limit")
                break
```

Change the `suite` entry of the receipt dict to:

```python
        "suite": {"path": rel_path(suite.path, root), "sha256": suite.sha256, "n_cases": len(suite.cases), "n_measured": len(outcomes)},
```

After `if reasons: receipt["status_reason"] = ...`, add:

```python
    if unmeasured:
        receipt["unmeasured"] = unmeasured
```

The `if outcomes and len(suite.cases) < q.min_cases` check stays as it is.

`src/sendesis/cli.py`, after the `print(f"{r['status']}  ...")` line, add:

```python
    n_measured = r["suite"].get("n_measured", r["suite"]["n_cases"])
    if n_measured < r["suite"]["n_cases"]:
        print(f"  measured {n_measured} of {r['suite']['n_cases']} cases; scores cover measured cases only")
    if r.get("unmeasured"):
        print("  unmeasured: " + ", ".join(f"{u['case_id']} ({u['outcome']})" for u in r["unmeasured"]))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest -q`

Expected: all pass: 137 plus 10 new (9 test functions, one parametrized twice), so 147 passed, 3 deselected.

- [ ] **Step 5: Commit**

```bash
git add schemas/receipt.json src/sendesis/qualify.py src/sendesis/cli.py tests/test_qualify.py
git commit -m "Qualify: retry a stall once; unmeasured cases stay out of scores and are listed on the receipt"
```

---

### Task 4: Docs, and the exit run (operator-gated)

**Files:**
- Modify: `docs/specs/2026-10-01-codex-stall-handling-design.md` (status line)
- Modify: `CLAUDE.md` ("Model client requirements", the wall-clock bullet)
- Modify: `reasonhold.yaml` (place this plan as archival under `global`)

- [ ] **Step 1: Update the docs**

In `docs/specs/2026-10-01-codex-stall-handling-design.md`, replace the status line with:

```
Status: decisions recorded 2026-10-01 (approved). Implemented: part 1 in agno-cli-models v0.1.2, and parts 2 and 3 in Sendesis (plan `docs/plans/2026-10-01-stall-handling-plan.md`).
```

In `CLAUDE.md`, replace this bullet:

```
- Every call has a hard wall-clock timeout enforced by the orchestrator. An unreachable provider makes `claude -p` hang silently. Timeout with no output is a failover trigger, same as an error exit or rate limit.
```

with:

```
- Every call has a hard wall-clock timeout enforced by the orchestrator, and an idle limit: agno-cli-models raises `CliStallError` when the CLI sends nothing for `idle_timeout_s` (default 60 s; a profile may set it). An unreachable provider makes `claude -p` hang silently. A timeout or a stall is a failover trigger, same as an error exit or rate limit. Qualification retries a stall once and never scores an unmeasured case.
```

In `reasonhold.yaml`, under `global.archival`, add `docs/plans/2026-10-01-stall-handling-plan.md`.

Run: `.venv/bin/reasonhold check`

Expected: `ok`. Then run `grep -c $'\u2014' CLAUDE.md docs/specs/2026-10-01-codex-stall-handling-design.md`.

Expected: `0` for both files.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md docs/specs/2026-10-01-codex-stall-handling-design.md reasonhold.yaml
git commit -m "Docs: stall handling implemented; idle limit in the model client requirements"
```

- [ ] **Step 3: STOP. Exit run, only after the operator says go (spends quota)**

Report to the operator that the exit run spends quota: 2 integration calls, and 30 or more calls per profile. Only after the operator says go, run:

```bash
.venv/bin/pytest -m integration -q
.venv/bin/sendesis qualify security-reviewer claude-opus
.venv/bin/sendesis qualify security-reviewer codex-gpt
```

What each result shows:
- Both receipts validate and carry `suite.n_measured`, and `sendesis receipts` reads them as matching the current fingerprints.
- If a stall happens, the run log has `<case>.1.json` with `outcome: stall` and a `stall` block. The case is then either measured on the retry or listed under `unmeasured`.
- A codex-gpt recall figure covers measured cases only.
- With no unmeasured case, the status reason is only "suite has 30 cases, role requires at least 100".
