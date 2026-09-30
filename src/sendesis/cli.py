"""The `sendesis` command line."""

from __future__ import annotations

import argparse
from pathlib import Path

from sendesis.validate import validate_repo


def cmd_validate(args: argparse.Namespace) -> int:
    report = validate_repo(Path(args.root))
    for line in report.ok:
        print(f"ok   {line}")
    for line in report.warnings:
        print(f"WARN {line}")
    for line in report.errors:
        print(f"FAIL {line}")
    if report.errors:
        print(f"{len(report.errors)} failure(s), {len(report.warnings)} warning(s)")
        return 1
    print(f"PASS with {len(report.warnings)} warning(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sendesis")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="Validate schemas, roles and profiles. Exit 1 on any failure.")
    p.add_argument("--root", default=".", help="Repo root holding schemas/, roles/ and profiles/ (default: current directory)")
    p.set_defaults(func=cmd_validate)

    args = parser.parse_args(argv)
    return args.func(args)
