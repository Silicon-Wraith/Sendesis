"""Validate roles/*.yaml and profiles/*.yaml against schemas/.

Usage: python scripts/validate_files.py
Exit code 0 when every file validates, 1 otherwise.
This is a stand-in until `sendesis validate` exists.
"""

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent


def load_schema(name: str) -> Draft202012Validator:
    schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def check(folder: str, validator: Draft202012Validator) -> tuple[int, dict]:
    failures = 0
    loaded = {}
    for path in sorted((ROOT / folder).glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
        if errors:
            failures += 1
            for err in errors:
                where = "/".join(str(p) for p in err.path) or "(root)"
                print(f"FAIL {path.relative_to(ROOT)}: {where}: {err.message}")
        else:
            print(f"ok   {path.relative_to(ROOT)}")
        loaded[data.get("id")] = (path, data)
    return failures, loaded


def main() -> int:
    for name in ("role.json", "profile.json", "receipt.json", "finding.json"):
        load_schema(name)
    print("ok   schemas are valid JSON Schema 2020-12")

    role_fail, roles = check("roles", load_schema("role.json"))
    prof_fail, profiles = check("profiles", load_schema("profile.json"))
    failures = role_fail + prof_fail

    for role_id, (path, role) in roles.items():
        for pid in role.get("failover_order", []):
            if pid not in profiles:
                failures += 1
                print(f"FAIL {path.relative_to(ROOT)}: failover_order names unknown profile '{pid}'")
        for key in ("output_schema", "prompt_file"):
            ref = role.get(key)
            if ref and not (ROOT / ref).exists():
                failures += 1
                print(f"FAIL {path.relative_to(ROOT)}: {key} points to missing file '{ref}'")

    print("PASS" if failures == 0 else f"{failures} failure(s)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
