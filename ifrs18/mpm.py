"""Management-defined performance measure (MPM) reconciliations (IFRS 18.117-125).

An MPM is defined as an IFRS 18 subtotal plus a list of adjustments. Each
adjustment shows its income tax effect and its effect on non-controlling
interests separately (IFRS 18.123). All amounts are rounded to the cent with
ROUND_HALF_UP, matching Excel's ROUND for the workbook formulas.

Definition file (YAML)::

    name: Adjusted EBITDA
    subtotal: operating_profit
    adjustments:
      - label: Depreciation and amortisation
        amounts: {FY2026: 1234.5, FY2025: 1100}   # added to the subtotal
        tax_rate: 0.25                             # tax effect = -amount * rate
        nci_share: 0.10                            # NCI effect = -(amount + tax) * share
      - label: Impairment of goodwill
        line: L007                                 # add back a P&L line: amount = -line value
        tax_rate: 0
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml

from .restate import SUBTOTAL_LABELS, Restatement

CENT = Decimal("0.01")


def cents(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Adjustment:
    label: str
    line: str | None = None
    amounts: dict[str, Decimal] = field(default_factory=dict)
    tax_rate: Decimal = Decimal(0)
    nci_share: Decimal = Decimal(0)


@dataclass
class MPMDefinition:
    name: str
    subtotal: str
    adjustments: list[Adjustment]
    description: str = ""


@dataclass
class ReconRow:
    label: str
    amount: Decimal
    tax_effect: Decimal
    nci_effect: Decimal


@dataclass
class Reconciliation:
    definition: MPMDefinition
    period: str
    subtotal_label: str
    subtotal: Decimal
    rows: list[ReconRow]
    mpm: Decimal
    total_tax: Decimal
    total_nci: Decimal


def _d(x) -> Decimal:
    return Decimal(str(x))


def load_definition(path: str | Path) -> MPMDefinition:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return parse_definition(raw)


def parse_definition(raw: dict) -> MPMDefinition:
    if raw["subtotal"] not in SUBTOTAL_LABELS:
        raise ValueError(f"subtotal must be one of {list(SUBTOTAL_LABELS)}")
    adjs = []
    for a in raw.get("adjustments", []):
        if ("line" in a) == ("amounts" in a):
            raise ValueError(f"adjustment {a.get('label')!r}: give exactly one of 'line' or 'amounts'")
        adjs.append(Adjustment(
            label=a["label"], line=a.get("line"),
            amounts={k: _d(v) for k, v in (a.get("amounts") or {}).items()},
            tax_rate=_d(a.get("tax_rate", 0)), nci_share=_d(a.get("nci_share", 0)),
        ))
    return MPMDefinition(raw["name"], raw["subtotal"], adjs, raw.get("description", ""))


def adjustment_amount(adj: Adjustment, r: Restatement, period: str) -> Decimal:
    if adj.line is not None:
        return cents(-r.statement.line(adj.line).amounts.get(period, Decimal(0)))
    return cents(adj.amounts.get(period, Decimal(0)))


def reconcile(defn: MPMDefinition, r: Restatement, period: str) -> Reconciliation:
    subtotal = cents(r.subtotals[period][defn.subtotal])
    rows = []
    for adj in defn.adjustments:
        amt = adjustment_amount(adj, r, period)
        tax = cents(-amt * adj.tax_rate)
        nci = cents(-(amt + tax) * adj.nci_share)
        rows.append(ReconRow(adj.label, amt, tax, nci))
    mpm = subtotal + sum((x.amount for x in rows), Decimal(0))
    return Reconciliation(defn, period, SUBTOTAL_LABELS[defn.subtotal], subtotal, rows, mpm,
                          sum((x.tax_effect for x in rows), Decimal(0)), sum((x.nci_effect for x in rows), Decimal(0)))
