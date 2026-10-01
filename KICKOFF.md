# Kickoff prompt for Claude Code

Start Claude Code in the Sendesis repo root, then paste the prompt below. Recommended: accept-edits mode, with Bash allowed for `python`, `.venv/bin/*`, `pytest`, `git`, and nothing else until Phase 2.

---

Read CLAUDE.md and docs/PLAN.md fully before doing anything.

We are building Phase 1 of Sendesis only. Do not start Phase 2.

Phase 1 goal: the four schemas in `schemas/`, the Security Reviewer role in `roles/`, and four profiles in `profiles/` are loaded and validated by a real `sendesis validate` command, and it fails loudly on bad files.

Steps:

1. Create `pyproject.toml` for a package `sendesis` under `src/sendesis/`, Python 3.11+, with `jsonschema`, `pyyaml`, and `typer` (or `argparse` if you prefer no dependency). Create `.venv` and install the package in editable mode.
2. Implement `src/sendesis/model.py` with typed loaders for roles and profiles that validate against the schemas and return dataclasses. Canonicalize and hash files (sha256 of the parsed YAML dumped as sorted JSON) for later receipt use.
3. Implement `sendesis validate`. It must check everything `scripts/validate_files.py` checks, plus: each profile's `family`; that the role's `failover_order` includes at least two distinct families among enabled profiles (warn, do not fail, while local profiles are disabled); and that a role prompt file exists and is hashed.
4. Write unit tests in `tests/` covering: valid files pass; a missing required field fails with a readable message; an unknown profile in `failover_order` fails; a codex profile without `sandbox` fails; the hash is stable across key order and whitespace changes.
5. Run the tests and `sendesis validate`. Show me the output.

Stop there. Summarize what you built, what you decided, and anything in the schemas you think is wrong. Do not change the schemas without asking me first.
