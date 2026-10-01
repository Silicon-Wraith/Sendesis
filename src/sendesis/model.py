"""Typed loaders for role contracts and execution profiles.

Each loader parses a YAML file, validates it against its JSON Schema in
`schemas/`, and returns a frozen dataclass carrying the canonical hash that
receipts will record.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


class ValidationFailed(Exception):
    """A file could not be loaded. `messages` holds one readable line per problem."""

    def __init__(self, messages: list[str]):
        super().__init__("\n".join(messages))
        self.messages = messages


def canonical_sha256(yaml_text: str) -> str:
    """sha256 of the parsed YAML dumped as sorted, compact JSON.

    Stable across key order, whitespace, comments and quoting style. Changing
    this function voids every receipt, so do not.
    """
    data = yaml.safe_load(yaml_text)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    """sha256 of a file's raw bytes. Used for prompts, which are not YAML."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schema_validator(root: Path, name: str) -> Draft202012Validator:
    """Load `schemas/<name>`, check it is valid 2020-12, and return a validator."""
    schema = json.loads((root / "schemas" / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def rel_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _load_checked(path: Path, root: Path, schema_name: str) -> tuple[dict[str, Any], str]:
    where = rel_path(path, root)
    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValidationFailed([f"{where}: YAML parse error: {exc}"]) from exc
    if not isinstance(data, dict):
        raise ValidationFailed([f"{where}: expected a YAML mapping at the top level"])
    errors = sorted(schema_validator(root, schema_name).iter_errors(data), key=lambda e: list(e.path))
    if errors:
        raise ValidationFailed(
            [f"{where}: {'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}" for e in errors]
        )
    return data, canonical_sha256(text)


@dataclass(frozen=True)
class RoleInput:
    name: str
    description: str
    required: bool = True


@dataclass(frozen=True)
class Metric:
    name: str
    direction: str  # "higher_is_better" | "lower_is_better"
    threshold: float
    basis: str = "interval"  # "interval" (conservative end) | "point"


@dataclass(frozen=True)
class Qualification:
    suite: str
    min_cases: int
    expiry_days: int
    metrics: tuple[Metric, ...]


REVIEWER_FORBIDDEN_TOOLS = ("edit", "shell")


@dataclass(frozen=True)
class Role:
    path: Path
    sha256: str
    id: str
    version: str
    kind: str  # "worker" | "reviewer"
    purpose: str
    inputs: tuple[RoleInput, ...]
    definition_of_done: tuple[str, ...]
    output_schema: str
    tools_allowed: tuple[str, ...]
    context: tuple[str, ...]
    failover_order: tuple[str, ...]
    qualification: Qualification | None
    per_call_timeout_s: int | None = None
    max_turns: int | None = None
    prompt_file: str | None = None
    prompt_sha256: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def provisional(self) -> bool:
        return self.qualification is None


CLI_CLASSES = {"claude_code": ("claude", "anthropic"), "codex": ("codex", "openai")}


@dataclass(frozen=True)
class ModelSpec:
    cls: str
    id: str
    effort: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    cli_version: str | None = None


@dataclass(frozen=True)
class Profile:
    path: Path
    sha256: str
    id: str
    enabled: bool
    family: str
    model: ModelSpec
    timeout_s: int
    max_turns: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def cli_binary(self) -> str | None:
        return CLI_CLASSES.get(self.model.cls, (None, None))[0]


def load_role(path: Path, root: Path) -> Role:
    data, sha = _load_checked(path, root, "role.json")
    prompt_file = data.get("prompt_file")
    prompt_path = root / prompt_file if prompt_file else None
    q = data.get("qualification")
    budgets = data.get("budgets", {})
    return Role(
        path=path,
        sha256=sha,
        id=data["id"],
        version=data["version"],
        kind=data["kind"],
        purpose=data["purpose"],
        inputs=tuple(RoleInput(i["name"], i["description"], i.get("required", True)) for i in data["inputs"]),
        definition_of_done=tuple(data["definition_of_done"]),
        output_schema=data["output_schema"],
        tools_allowed=tuple(data["tools"]["allowed"]),
        context=tuple(data.get("context", [])),
        failover_order=tuple(data["failover_order"]),
        qualification=None if q is None else Qualification(
            suite=q["suite"], min_cases=q["min_cases"], expiry_days=q["expiry_days"],
            metrics=tuple(Metric(m["name"], m["direction"], m["threshold"], m.get("basis", "interval")) for m in q["metrics"]),
        ),
        per_call_timeout_s=budgets.get("per_call_timeout_s"),
        max_turns=budgets.get("max_turns"),
        prompt_file=prompt_file,
        prompt_sha256=file_sha256(prompt_path) if prompt_path and prompt_path.is_file() else None,
        raw=data,
    )


def load_profile(path: Path, root: Path) -> Profile:
    data, sha = _load_checked(path, root, "profile.json")
    m = data["model"]
    return Profile(
        path=path,
        sha256=sha,
        id=data["id"],
        enabled=data["enabled"],
        family=data["family"],
        model=ModelSpec(
            cls=m["class"], id=m["id"], effort=m.get("effort"), base_url=m.get("base_url"),
            api_key_env=m.get("api_key_env"), cli_version=m.get("cli_version"),
        ),
        timeout_s=data["timeout_s"],
        max_turns=data.get("max_turns"),
        raw=data,
    )
