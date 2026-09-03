"""Income statement data model and CSV input/output.

Amounts are stored as Decimal and signed so that every ``item`` line adds to
profit or loss: income is positive, expenses are negative.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

ITEM = "item"            # component of profit or loss
SUBTOTAL = "subtotal"    # a presented total in the original statement
PROFIT = "profit"        # profit or loss for the year
ATTRIBUTION = "attribution"  # split of profit between owners and NCI
KINDS = (ITEM, SUBTOTAL, PROFIT, ATTRIBUTION)

TOLERANCE = Decimal("0.5")


@dataclass
class Line:
    line_id: str
    label: str
    amounts: dict[str, Decimal]
    tag: str = ""
    kind: str = ITEM


@dataclass
class Statement:
    entity: str
    periods: list[str]
    lines: list[Line]
    currency: str = ""
    source: str = ""
    meta: dict = field(default_factory=dict)

    def items(self) -> list[Line]:
        return [ln for ln in self.lines if ln.kind == ITEM]

    def profit_line(self) -> Line | None:
        for ln in self.lines:
            if ln.kind == PROFIT:
                return ln
        return None

    def line(self, line_id: str) -> Line:
        for ln in self.lines:
            if ln.line_id == line_id:
                return ln
        raise KeyError(line_id)

    def item_total(self, period: str) -> Decimal:
        return sum((ln.amounts.get(period, Decimal(0)) for ln in self.items()), Decimal(0))

    def check_items_sum_to_profit(self) -> dict[str, Decimal]:
        """Return the difference (items minus reported profit) per period."""
        p = self.profit_line()
        if p is None:
            return {}
        return {per: self.item_total(per) - p.amounts.get(per, Decimal(0)) for per in self.periods}


def _dec(text: str) -> Decimal:
    text = (text or "").strip().replace(",", "")
    if text in ("", "-"):
        return Decimal(0)
    if text.startswith("(") and text.endswith(")"):
        return -Decimal(text[1:-1])
    return Decimal(text)


def read_csv(path: str | Path, entity: str | None = None) -> Statement:
    """Read a P&L export.

    Required columns: ``label`` plus one column per period whose header starts
    with ``FY`` or is a four-digit year. Optional: ``line_id``, ``tag`` (XBRL
    element), ``kind`` (item/subtotal/profit/attribution; default item).
    The first period column is the current year, the second the comparative.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"{path}: no rows")
    cols = list(rows[0].keys())
    periods = [c for c in cols if c.strip().upper().startswith("FY") or (c.strip().isdigit() and len(c.strip()) == 4)]
    if not periods:
        raise ValueError(f"{path}: no period columns (expected headers like FY2026 or 2026)")
    lines = []
    for i, r in enumerate(rows, 1):
        kind = (r.get("kind") or ITEM).strip() or ITEM
        if kind not in KINDS:
            raise ValueError(f"{path}: line {i} has unknown kind {kind!r}")
        lines.append(Line(
            line_id=(r.get("line_id") or f"L{i:03d}").strip(),
            label=r["label"].strip(),
            tag=(r.get("tag") or "").strip(),
            kind=kind,
            amounts={p: _dec(r[p]) for p in periods},
        ))
    return Statement(entity=entity or path.stem, periods=periods, lines=lines, source=str(path))


def write_csv(stmt: Statement, path: str | Path) -> None:
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["line_id", "label", "tag", "kind", *stmt.periods])
        for ln in stmt.lines:
            w.writerow([ln.line_id, ln.label, ln.tag, ln.kind, *[_fmt(ln.amounts.get(p, Decimal(0))) for p in stmt.periods]])


def _fmt(d: Decimal) -> str:
    d = d.normalize()
    return format(d, "f")
