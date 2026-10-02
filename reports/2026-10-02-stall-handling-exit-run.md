# Stall handling exit run, 2026-10-02

Exit evidence for stall handling parts 2 and 3: `docs/specs/2026-10-01-codex-stall-handling-design.md`, executed from `docs/plans/2026-10-01-stall-handling-plan.md`.

Components:
- agno-cli-models v0.1.2: 60 s idle limit and `CliStallError`.
- claude CLI 2.1.287.
- codex-cli 0.155.1.

## Runs

| Tier | Result |
|---|---|
| Unit | 153 passed, 3 deselected |
| Integration | 2 passed, 19 s: one real call each on claude-opus and codex-gpt through `run_role` |
| `qualify security-reviewer claude-opus` | UNKNOWN: "suite has 30 cases, role requires at least 100". Receipt `receipts/security-reviewer/claude-opus/20261002T021847Z.json` |
| `qualify security-reviewer codex-gpt` | UNKNOWN: "suite has 30 cases, role requires at least 100". Receipt `receipts/security-reviewer/codex-gpt/20261002T021852Z.json` |

Both receipts validate against `schemas/receipt.json`. `sendesis receipts` reads both as current, so recorded and effective status agree.

The two profiles ran in parallel. Each called `qualify()` with its own workdir, `~/.cache/sendesis/workdirs/security-reviewer-<profile>`. The CLI's default workdir is shared by all profiles, and `prepare_workdir` rewrites `case/` for every case, so two runs in one directory would overwrite each other's case files. The workdir path is not part of the receipt, and `workdir_context_sha256` hashes only the instruction files found there, of which there are none. So the receipts are the same as CLI runs would produce.

An earlier sequential attempt (`runs/security-reviewer/claude-opus/20261002T021521Z`, 9 cases) stopped with its session and wrote no receipt.

## Scores

| Metric | claude-opus | codex-gpt |
|---|---|---|
| measured | 30 of 30 | 30 of 30 |
| recall (interval, threshold 0.6) | 1.000 [0.890, 1.000] pass | 0.903 [0.751, 0.967] pass |
| false_positives_per_clean_case (interval, 0.5) | 0.000 pass | 0.000 pass |
| schema_validity (point, 0.98) | 1.000 pass | 1.000 pass |
| tokens in (cached) / out | 406,588 (202,391) / 48,684 | 420,237 (245,632) / 47,264 |
| wall | 485 s | 1,002 s |

There were no stalls, timeouts or retries in either run. No `.1.json` retry log was written, and neither receipt has an `unmeasured` list.

## Compared with the M3.1 exit run (2026-10-01)

| | M3.1 codex-gpt | This run |
|---|---|---|
| Cases ending in a 300 s timeout | 5 | 0 |
| Recall | 0.677, FAIL (5 stalled cases counted as misses) | 0.903, pass (every case measured) |
| Wall time | 2,254 s | 1,002 s |

No stall happened in this run, so the new path (STALL after 60 s, one retry, unmeasured if it stalls again) was not exercised by a real stall. It is covered in two other ways:
- **Unit tests:** `tests/test_seat.py` and `tests/test_qualify.py`.
- **The final branch review:** it drove the real `CodexModel` against a scripted app-server that went silent. The idle limit firing first gave `Outcome.STALL` with `last_method: item/started` and `answer_open: true`. The wall clock firing first gave `Outcome.TIMEOUT`.

The codex-gpt recall of 0.903 counts real misses: 28 of 31 labels were found, in cases that all answered.
