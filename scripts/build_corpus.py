"""Rebuild corpus/statements/*.csv from the SEC Financial Statement Data Sets.

Usage: python scripts/build_corpus.py [--cache DIR] [--user-agent "name email"]
Downloads the quarterly zips listed in corpus/manifest.csv (about 80-130 MB
each) into the cache directory and extracts each filing's income statement.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ifrs18.sec import download_quarter, load_statement  # noqa: E402
from ifrs18.statement import write_csv  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.path.join(os.environ.get("TMPDIR", "/tmp"), "sec-fsds"))
    ap.add_argument("--user-agent", default="ifrs18-restatement-engine research contact@example.org")
    args = ap.parse_args()
    out = ROOT / "corpus" / "statements"
    out.mkdir(parents=True, exist_ok=True)
    with (ROOT / "corpus" / "manifest.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        zp = download_quarter(r["quarter"], args.cache, args.user_agent)
        stmt = load_statement(zp, r["adsh"])
        diff = stmt.check_items_sum_to_profit()
        write_csv(stmt, out / f"{r['slug']}.csv")
        print(f"{r['slug']:15s} {stmt.entity[:32]:32s} {stmt.currency} {len(stmt.items()):3d} items  "
              f"items-profit diff {', '.join(str(v) for v in diff.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
