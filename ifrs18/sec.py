"""Load income statements from the SEC Financial Statement Data Sets.

The quarterly zips (https://www.sec.gov/dera/data/financial-statement-data-sets)
contain ``sub.txt`` (filings), ``pre.txt`` (presentation: which element sits on
which line of which statement), ``num.txt`` (the numeric facts) and ``tag.txt``
(element definitions including the debit/credit balance). For IFRS filers the
elements come from the ``ifrs-full`` taxonomy plus entity extensions.

Signs: XBRL facts are stored with the element's natural sign (an expense is a
positive debit). Lines are re-signed with the ``crdr`` balance so that credits
(income) are positive and debits (expenses) negative, which makes every
component line add up to profit or loss.
"""
from __future__ import annotations

import io
import os
import urllib.request
import zipfile
from decimal import Decimal
from pathlib import Path

import pandas as pd

from .statement import ATTRIBUTION, ITEM, PROFIT, SUBTOTAL, TOLERANCE, Line, Statement

FSDS_URL = "https://www.sec.gov/files/dera/data/financial-statement-data-sets/{quarter}.zip"

PROFIT_TAGS = ("ProfitLoss",)
ATTRIBUTION_PREFIXES = ("ProfitLossAttributableTo", "ComprehensiveIncomeAttributableTo")
KNOWN_SUBTOTALS = {
    "GrossProfit", "ProfitLossFromOperatingActivities", "ProfitLossBeforeTax",
    "ProfitLossFromContinuingOperations", "FinanceIncomeCost", "Revenue" + "AndOtherIncome",
}


def download_quarter(quarter: str, dest_dir: str | Path, user_agent: str) -> Path:
    """Download one quarterly zip (e.g. ``2025q1``). SEC asks for a descriptive User-Agent."""
    dest = Path(dest_dir) / f"{quarter}.zip"
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(FSDS_URL.format(quarter=quarter), headers={"User-Agent": user_agent})
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(req) as resp, tmp.open("wb") as fh:
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
    os.replace(tmp, dest)
    return dest


def _read(z: zipfile.ZipFile, name: str, adsh: set[str] | None = None, usecols=None) -> pd.DataFrame:
    kw = dict(sep="\t", dtype=str, keep_default_na=False, usecols=usecols, quoting=3, on_bad_lines="skip")
    if adsh is None:
        return pd.read_csv(io.TextIOWrapper(z.open(name), encoding="utf-8", errors="replace"), **kw)
    # Filter raw lines first: num.txt holds millions of rows, a filing a few hundred.
    keys = tuple(a + "\t" for a in adsh)
    with io.TextIOWrapper(z.open(name), encoding="utf-8", errors="replace") as fh:
        buf = [next(fh)] + [ln for ln in fh if ln.startswith(keys)]
    return pd.read_csv(io.StringIO("".join(buf)), **kw)


def find_zip_for(adsh: str, zips: list[Path]) -> Path:
    for zp in zips:
        with zipfile.ZipFile(zp) as z:
            sub = _read(z, "sub.txt", usecols=["adsh"])
            if adsh in set(sub.adsh):
                return zp
    raise KeyError(f"accession {adsh} not found in {', '.join(map(str, zips))}")


def load_statement(zip_path: str | Path, adsh: str) -> Statement:
    """Build a two-year Statement for one filing's income statement (stmt = IS)."""
    with zipfile.ZipFile(zip_path) as z:
        sub = _read(z, "sub.txt")
        sub = sub[sub.adsh == adsh]
        if sub.empty:
            raise KeyError(f"{adsh} not in {zip_path}")
        s = sub.iloc[0]
        pre = _read(z, "pre.txt", {adsh})
        num = _read(z, "num.txt", {adsh})
        tag = _read(z, "tag.txt", usecols=["tag", "version", "custom", "abstract", "crdr", "tlabel"])
    return build_statement(s, pre, num, tag)


def build_statement(s: pd.Series, pre: pd.DataFrame, num: pd.DataFrame, tag: pd.DataFrame) -> Statement:
    adsh = s["adsh"]
    pre = pre[(pre.stmt == "IS") & (pre.inpth == "0")].copy()
    if pre.empty:
        raise ValueError(f"{adsh}: no income statement (stmt=IS) in pre.txt")
    # Pick the report holding profit or loss; break ties by size.
    rep = pre.groupby("report").agg(n=("tag", "size"), has_pl=("tag", lambda t: t.isin(PROFIT_TAGS).any()))
    report = rep.sort_values(["has_pl", "n"], ascending=False).index[0]
    pre = pre[pre.report == report].copy()
    pre["line"] = pre.line.astype(int)
    pre = pre.sort_values("line").drop_duplicates("tag", keep="first")

    num = num[(num.qtrs == "4") & (num.coreg == "")]
    if "segments" in num.columns:
        num = num[num.segments == ""]
    currency = num.uom.value_counts().index[0] if not num.empty else ""
    num = num[num.uom == currency]
    current = s["period"]
    ddates = sorted({d for d in num.ddate if d <= current}, reverse=True)
    periods = ddates[:2]
    if len(periods) < 2:
        raise ValueError(f"{adsh}: fewer than two annual periods")
    vals = {(r.tag, r.ddate): Decimal(r.value) for r in num.itertuples() if r.value != "" and r.ddate in periods}

    crdr = {(r.tag, r.version): r.crdr for r in tag.itertuples()}
    tlabel = {(r.tag, r.version): r.tlabel for r in tag.itertuples()}

    lines: list[Line] = []
    seen_profit = False
    for r in pre.itertuples():
        if not any((r.tag, p) in vals for p in periods):
            continue  # headings, EPS (per-share unit) and empty rows
        sign = -1 if crdr.get((r.tag, r.version)) == "D" else 1
        amounts = {f"FY{p[:4]}": sign * vals.get((r.tag, p), Decimal(0)) for p in periods}
        if r.tag in PROFIT_TAGS:
            kind, seen_profit = PROFIT, True
        elif r.tag.startswith(ATTRIBUTION_PREFIXES):
            kind = ATTRIBUTION
        elif seen_profit:
            continue  # anything after profit or loss is not part of it
        else:
            kind = ITEM
        label = r.plabel or tlabel.get((r.tag, r.version), r.tag)
        prefix = "ifrs-full:" if r.version.startswith("ifrs") else ("" if r.version == adsh else f"{r.version}:")
        tag_name = r.tag if r.version != adsh else f"ext:{r.tag}"
        lines.append(Line(f"L{len(lines) + 1:03d}", label, amounts, tag=f"{prefix}{tag_name}", kind=kind))

    periods_fy = [f"FY{p[:4]}" for p in periods]
    _mark_subtotals(lines, periods_fy)
    stmt = Statement(entity=s["name"].title(), periods=periods_fy, lines=lines, currency=currency,
                     source=f"SEC FSDS {adsh} ({s['form']})", meta={"adsh": adsh, "cik": s["cik"], "form": s["form"]})
    if stmt.profit_line() is None:
        _infer_profit_line(stmt)
    return stmt


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= TOLERANCE * max(1, abs(b) // 10**9 + 1)


def _mark_subtotals(lines: list[Line], periods: list[str]) -> None:
    """Flag presented totals so components are not counted twice.

    A line is a subtotal when it is a known total element, or when in every
    period it equals the running sum of all components above it, or the sum of
    a contiguous run (two or more) of the components directly above it.
    """
    items: list[Line] = []
    for ln in lines:
        if ln.kind != ITEM:
            continue
        name = ln.tag.split(":")[-1]
        is_total = name in KNOWN_SUBTOTALS and len(items) >= 1
        if not is_total and len(items) >= 2:
            for k in range(len(items), 1, -1):
                window = items[-k:]
                if all(_close(sum((w.amounts[p] for w in window), Decimal(0)), ln.amounts[p]) for p in periods) \
                        and any(ln.amounts[p] != 0 for p in periods):
                    is_total = True
                    break
        if is_total:
            ln.kind = SUBTOTAL
        else:
            items.append(ln)


def _infer_profit_line(stmt: Statement) -> None:
    """Some filers present only profit attributable to owners; treat the last
    attribution line whose value equals the component total as profit."""
    for ln in stmt.lines:
        if ln.kind in (ATTRIBUTION, SUBTOTAL) and all(_close(stmt.item_total(p), ln.amounts[p]) for p in stmt.periods):
            ln.kind = PROFIT
            return
