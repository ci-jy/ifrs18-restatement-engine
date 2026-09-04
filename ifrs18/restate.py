"""Restate a classified income statement into the IFRS 18 structure.

Subtotals (IFRS 18.69):
    operating profit                               = operating
    profit before financing and income taxes       = + investing
    profit before tax                              = + financing
    profit from continuing operations              = + income taxes
    profit or loss                                 = + discontinued operations
Restating only regroups lines, so profit or loss must equal the original
reported figure exactly; ``conservation`` records the proof.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .rules import CATEGORIES
from .statement import Statement

SUBTOTALS = (
    ("operating_profit", "Operating profit", ("operating",)),
    ("pbfit", "Profit before financing and income taxes", ("operating", "investing")),
    ("profit_before_tax", "Profit before tax", ("operating", "investing", "financing")),
    ("profit_continuing", "Profit from continuing operations", ("operating", "investing", "financing", "income_taxes")),
    ("profit", "Profit or loss for the year", CATEGORIES),
)
SUBTOTAL_LABELS = {k: lbl for k, lbl, _ in SUBTOTALS}


@dataclass
class Restatement:
    statement: Statement
    mapping: dict[str, str]                      # line_id -> category
    category_totals: dict[str, dict[str, Decimal]] = field(default_factory=dict)  # period -> category -> total
    subtotals: dict[str, dict[str, Decimal]] = field(default_factory=dict)        # period -> subtotal -> value
    conservation: dict[str, dict[str, Decimal]] = field(default_factory=dict)     # period -> check -> difference

    def is_conserved(self) -> bool:
        return all(v == 0 for per in self.conservation.values() for v in per.values())


def restate(stmt: Statement, mapping: dict[str, str]) -> Restatement:
    items = stmt.items()
    missing = [ln.line_id for ln in items if ln.line_id not in mapping]
    if missing:
        raise ValueError(f"lines without a category: {missing}")
    bad = {c for c in mapping.values() if c not in CATEGORIES}
    if bad:
        raise ValueError(f"unknown categories: {sorted(bad)}")
    r = Restatement(stmt, dict(mapping))
    profit_line = stmt.profit_line()
    for per in stmt.periods:
        totals = {c: Decimal(0) for c in CATEGORIES}
        for ln in items:
            totals[mapping[ln.line_id]] += ln.amounts.get(per, Decimal(0))
        r.category_totals[per] = totals
        r.subtotals[per] = {key: sum((totals[c] for c in cats), Decimal(0)) for key, _, cats in SUBTOTALS}
        original_items = stmt.item_total(per)
        checks = {
            # every line lands in exactly one category: category totals add back to the line total
            "categories_sum_to_items": sum(totals.values(), Decimal(0)) - original_items,
            # the restated bottom line equals the sum of all original lines
            "profit_equals_items": r.subtotals[per]["profit"] - original_items,
        }
        if profit_line is not None:
            checks["profit_equals_reported"] = r.subtotals[per]["profit"] - profit_line.amounts.get(per, Decimal(0))
        r.conservation[per] = checks
    return r
