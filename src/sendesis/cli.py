"""The `sendesis` command line."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
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


def cmd_qualify(args: argparse.Namespace) -> int:
    from sendesis.qualify import QualifyError, qualify

    root = Path(args.root)
    try:
        result = qualify(root, args.role, args.profile, suite_dir=Path(args.suite) if args.suite else None, dry_run=args.local)
    except QualifyError as exc:
        print(f"FAIL {exc}")
        return 2
    r = result.receipt
    if args.local:
        print("DRY RUN (no receipt written)")
    print(f"{r['status']}  {args.role} on {args.profile}  ({r['suite']['n_cases']} cases, suite {r['suite']['path']})")
    for s in r["scores"]:
        mark = "pass" if s["pass"] else "FAIL"
        print(f"  {s['metric']:32} {s['value']:.3f}  [{s['ci_low']:.3f}, {s['ci_high']:.3f}] {s['ci_method']:9} threshold {s['threshold']} ({s['basis']})  {mark}")
    c = r["cost"]
    print(f"  tokens in {c['input_tokens']} (cached {c.get('cached_input_tokens', 0)}), out {c['output_tokens']}, wall {c['wall_s']:.0f}s")
    if r.get("status_reason"):
        print(f"  reason: {r['status_reason']}")
    print(f"  {'summary' if args.local else 'receipt'}: {result.path}")
    return 0


def cmd_receipts(args: argparse.Namespace) -> int:
    from sendesis.receipts import check_all

    rows = check_all(Path(args.root), datetime.now(timezone.utc))
    if not rows:
        print("no receipts")
    for path, recorded, effective, reasons in rows:
        print(f"{effective:9} (recorded {recorded:9}) {path}")
        for reason in reasons:
            print(f"          {reason}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sendesis")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="Validate schemas, roles and profiles. Exit 1 on any failure.")
    p.add_argument("--root", default=".", help="Repo root holding schemas/, roles/ and profiles/ (default: current directory)")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("qualify", help="Run a role's suite on one profile through its Agno model class and write a receipt. Spends subscription quota for CLI classes.")
    p.add_argument("role")
    p.add_argument("profile")
    p.add_argument("--suite", help="Suite folder to use instead of the role's qualification.suite")
    p.add_argument("--local", action="store_true", help="Dry run on a local model (class openai_like): free, writes runs/.../summary.json, never a receipt")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_qualify)

    p = sub.add_parser("receipts", help="Show each latest receipt and whether it still holds.")
    p.add_argument("--root", default=".")
    p.set_defaults(func=cmd_receipts)

    args = parser.parse_args(argv)
    return args.func(args)
