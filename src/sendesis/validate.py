"""Repo-wide checks behind `sendesis validate`.

Schema validation catches single-file mistakes. The checks here catch
mistakes between files: unknown profile ids, missing prompt files, and
failover orders that cannot cross model families.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from jsonschema.exceptions import SchemaError

from sendesis.model import CLI_CLASSES, Profile, Role, ValidationFailed, rel_path, load_profile, load_role, schema_validator

SCHEMAS = ("role.json", "profile.json", "receipt.json", "finding.json")
PLACEHOLDER = "set-me"
# The official CLIs only reach one vendor each, so their family is fixed.


@dataclass
class Report:
    ok: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _check_schemas(root: Path, report: Report) -> set[str]:
    good = set()
    for name in SCHEMAS:
        where = f"schemas/{name}"
        try:
            schema_validator(root, name)
        except FileNotFoundError:
            report.errors.append(f"{where}: missing")
        except ValueError as exc:  # json.JSONDecodeError is a ValueError
            report.errors.append(f"{where}: not valid JSON: {exc}")
        except SchemaError as exc:
            report.errors.append(f"{where}: not a valid JSON Schema 2020-12: {exc.message}")
        else:
            good.add(name)
            report.ok.append(where)
    return good


def _load_all(root: Path, folder: str, loader, report: Report) -> dict:
    loaded = {}
    for path in sorted((root / folder).glob("*.yaml")):
        where = rel_path(path, root)
        try:
            item = loader(path, root)
        except ValidationFailed as exc:
            report.errors.extend(exc.messages)
            continue
        if item.id != path.stem:
            report.errors.append(f"{where}: id '{item.id}' does not match file name '{path.stem}'")
            continue
        loaded[item.id] = item
        report.ok.append(f"{where} (sha256 {item.sha256[:12]})")
    return loaded


def _check_profile(p: Profile, root: Path, report: Report) -> None:
    where = rel_path(p.path, root)
    for label, value in (("family", p.family), ("model.id", p.model.id)):
        if value == PLACEHOLDER:
            msg = f"{where}: {label} is the placeholder '{PLACEHOLDER}'"
            if p.enabled:
                report.errors.append(f"{msg} but the profile is enabled")
            else:
                report.warnings.append(f"{msg}; set it before enabling")
    if p.model.cls in CLI_CLASSES:
        binary, family = CLI_CLASSES[p.model.cls]
        if p.family != family:
            report.errors.append(f"{where}: model class {p.model.cls} reaches family '{family}', but family is '{p.family}'")
        if not p.model.cli_version:
            report.errors.append(f"{where}: model class {p.model.cls} needs model.cli_version (the {binary} version it was set up with)")
    if p.model.cls == "openai_like" and not p.model.base_url:
        report.errors.append(f"{where}: model class openai_like needs model.base_url")


def _check_role(role: Role, profiles: dict[str, Profile], profile_files: set[str], root: Path, report: Report) -> None:
    where = rel_path(role.path, root)

    if not (root / role.output_schema).is_file():
        report.errors.append(f"{where}: output_schema points to missing file '{role.output_schema}'")

    if not role.prompt_file:
        report.errors.append(f"{where}: prompt_file is not set; every role needs a prompt")
    elif role.prompt_sha256 is None:
        report.errors.append(f"{where}: prompt_file points to missing file '{role.prompt_file}'")
    else:
        report.ok.append(f"{role.prompt_file} (prompt sha256 {role.prompt_sha256[:12]})")

    known = [profiles[pid] for pid in role.failover_order if pid in profiles]
    for pid in role.failover_order:
        # A profile file that failed to load is already reported against its own file.
        if pid not in profile_files:
            report.errors.append(f"{where}: failover_order names unknown profile '{pid}'")

    usable = [p for p in known if p.enabled and p.family != PLACEHOLDER]
    families = sorted({p.family for p in usable})
    if len(families) < 2:
        msg = f"{where}: failover_order has {len(families)} model families among enabled profiles ({', '.join(families) or 'none'}); need at least 2"
        disabled = [p.id for p in known if not p.enabled]
        if disabled:
            report.warnings.append(f"{msg}. Enabling {', '.join(disabled)} may fix this")
        else:
            report.errors.append(msg)


def validate_repo(root: Path) -> Report:
    report = Report()
    good_schemas = _check_schemas(root, report)
    profiles = _load_all(root, "profiles", load_profile, report) if "profile.json" in good_schemas else {}
    roles = _load_all(root, "roles", load_role, report) if "role.json" in good_schemas else {}

    for p in profiles.values():
        _check_profile(p, root, report)
    profile_files = {path.stem for path in (root / "profiles").glob("*.yaml")}
    for role in roles.values():
        _check_role(role, profiles, profile_files, root, report)
    return report
