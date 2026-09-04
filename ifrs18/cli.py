"""Command line interface: ``python -m ifrs18 restate|verify-workbook|rules``."""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

from .mpm import load_definition, reconcile
from .restate import SUBTOTALS, restate
from .rules import CATEGORIES, ENTITY_TYPES, classify, load_rules
from .statement import read_csv


def _load_statement(args):
    if args.sec_adsh:
        from .sec import download_quarter, find_zip_for, load_statement
        if args.sec_zip:
            zips = [Path(z) for z in args.sec_zip]
        elif args.sec_quarter:
            cache = Path(os.environ.get("TMPDIR", "/tmp")) / "sec-fsds"
            zips = [download_quarter(q, cache, args.user_agent) for q in args.sec_quarter]
        else:
            sys.exit("--sec-adsh needs --sec-zip PATH or --sec-quarter 2025q1")
        return load_statement(find_zip_for(args.sec_adsh, zips), args.sec_adsh)
    if not args.input:
        sys.exit("give an input CSV or --sec-adsh")
    return read_csv(args.input)


def _overrides(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    with open(path, newline="", encoding="utf-8") as fh:
        out = {r["line_id"]: r["category"].strip() for r in csv.DictReader(fh)}
    bad = {c for c in out.values() if c not in CATEGORIES}
    if bad:
        sys.exit(f"unknown categories in {path}: {sorted(bad)}")
    return out


def cmd_restate(args) -> int:
    from .workbook import write_workbook

    stmt = _load_statement(args)
    rules = load_rules(args.rules) if args.rules else load_rules()
    classes = classify(stmt, args.entity_type, rules)
    mapping = {lid: c.category for lid, c in classes.items()}
    mapping.update(_overrides(args.mapping))
    r = restate(stmt, mapping)

    mpm_path = args.mpm
    if mpm_path is None and args.input:
        sibling = Path(args.input).with_suffix(".mpm.yaml")
        mpm_path = str(sibling) if sibling.exists() else None
    mpm = load_definition(mpm_path) if mpm_path else None

    write_workbook(r, classes, args.output, mpm=mpm, entity_type=args.entity_type)

    flagged = [c for c in classes.values() if c.flagged]
    print(f"{stmt.entity}: {len(classes)} lines classified, {len(flagged)} flagged for review ({stmt.source or args.input})")
    for c in flagged:
        print(f"  REVIEW {c.line_id} {c.label[:55]!r}: suggested {c.category}, alternatives {', '.join(c.alternatives)}")
    width = max(len(lbl) for _, lbl, _ in SUBTOTALS)
    print(f"  {'':{width}s} " + " ".join(f"{p:>20s}" for p in stmt.periods))
    for key, lbl, _ in SUBTOTALS:
        print(f"  {lbl:{width}s} " + " ".join(f"{r.subtotals[p][key]:>20,.2f}" for p in stmt.periods))
    if mpm:
        for p in stmt.periods:
            rec = reconcile(mpm, r, p)
            print(f"  {mpm.name} {p}: {rec.mpm:,.2f} (tax effect {rec.total_tax:,.2f}, NCI effect {rec.total_nci:,.2f})")
    status = "conserved" if r.is_conserved() else "NOT conserved"
    print(f"  Net income {status}: " + ", ".join(f"{p} diff {max(abs(v) for v in r.conservation[p].values())}" for p in stmt.periods))
    print(f"Wrote {args.output}")
    return 0 if r.is_conserved() else 1


def cmd_verify(args) -> int:
    from .workbook import verify_workbook

    res = verify_workbook(args.workbook, args.tolerance)
    print(f"Recalculated {args.workbook} in headless LibreOffice: {res.checked} cells checked, "
          f"max |LibreOffice - Python| = {res.max_abs_diff:.3g}, tolerance {args.tolerance:g}")
    for sheet, cell, want, got in res.failures[:20]:
        print(f"  MISMATCH {sheet}!{cell}: expected {want!r}, got {got!r}")
    print("OK" if res.ok else f"FAILED ({len(res.failures)} cells)")
    return 0 if res.ok else 1


def cmd_rules(args) -> int:
    for r in load_rules():
        cats = r.category
        cat = cats["general"] if len(set(cats.values())) == 1 else ", ".join(f"{k}: {v}" for k, v in cats.items())
        flag = " [flags for review]" if r.flag else ""
        print(f"{r.id:40s} {r.paragraph:18s} {cat}{flag}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ifrs18", description="IFRS 18 income statement restatement")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("restate", help="classify, restate and write the Excel workbook")
    p.add_argument("input", nargs="?", help="P&L CSV (label, optional line_id/tag/kind, period columns)")
    p.add_argument("--sec-adsh", help="accession number of a 20-F/40-F in the SEC Financial Statement Data Sets")
    p.add_argument("--sec-zip", action="append", help="local FSDS quarterly zip (repeatable)")
    p.add_argument("--sec-quarter", action="append", help="FSDS quarter to download, e.g. 2025q1 (repeatable)")
    p.add_argument("--user-agent", default="ifrs18-restatement-engine research contact@example.org")
    p.add_argument("--entity-type", choices=ENTITY_TYPES, default="general",
                   help="main business activity: general, investing (in assets) or financing (customers)")
    p.add_argument("--mpm", help="MPM definition YAML (default: <input>.mpm.yaml if present)")
    p.add_argument("--mapping", help="CSV of line_id,category overrides after review")
    p.add_argument("--rules", help="alternative rules YAML")
    p.add_argument("-o", "--output", required=True, help="output .xlsx")
    p.set_defaults(func=cmd_restate)

    v = sub.add_parser("verify-workbook", help="recalculate in headless LibreOffice and compare with Python")
    v.add_argument("workbook")
    v.add_argument("--tolerance", type=float, default=1e-9)
    v.set_defaults(func=cmd_verify)

    rl = sub.add_parser("rules", help="list the classification rules")
    rl.set_defaults(func=cmd_rules)

    args = ap.parse_args(argv)
    return args.func(args)
