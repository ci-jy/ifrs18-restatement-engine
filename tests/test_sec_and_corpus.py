from decimal import Decimal
from pathlib import Path

import pandas as pd
import yaml

from ifrs18.evaluate import baseline_accuracy, run, summarise
from ifrs18.sec import build_statement
from ifrs18.statement import ATTRIBUTION, ITEM, PROFIT, SUBTOTAL, read_csv

ROOT = Path(__file__).resolve().parents[1]


def _fsds():
    sub = pd.Series({"adsh": "A1", "name": "TEST PLC", "form": "20-F", "period": "20241231", "cik": "1"})
    rows = [("Revenue", "Revenue", "C", 1000, 900), ("CostOfSales", "Cost of sales", "D", 600, 500),
            ("GrossProfit", "Gross profit", "C", 400, 400), ("FinanceIncome", "Finance income", "C", 10, 5),
            ("FinanceCosts", "Finance costs", "D", 30, 20), ("FinanceIncomeCost", "Net finance", "C", -20, -15),
            ("IncomeTaxExpenseContinuingOperations", "Tax", "D", 95, 100), ("ProfitLoss", "Profit", "C", 285, 285),
            ("ProfitLossAttributableToOwnersOfParent", "Owners", "C", 280, 280)]
    pre = pd.DataFrame([{"adsh": "A1", "report": "4", "line": str(i + 1), "stmt": "IS", "inpth": "0", "tag": t,
                         "version": "ifrs/2024", "plabel": lbl} for i, (t, lbl, *_ ) in enumerate(rows)])
    num = []
    for t, _, _, a, b in rows:
        for d, v in (("20241231", a), ("20231231", b)):
            num.append({"adsh": "A1", "tag": t, "version": "ifrs/2024", "ddate": d, "qtrs": "4", "uom": "EUR",
                        "segments": "", "coreg": "", "value": str(v)})
    tag = pd.DataFrame([{"tag": t, "version": "ifrs/2024", "custom": "0", "abstract": "0", "crdr": c, "tlabel": lbl}
                        for t, lbl, c, *_ in rows])
    return sub, pre, pd.DataFrame(num), tag


def test_fsds_loader_signs_orders_and_detects_subtotals():
    stmt = build_statement(*_fsds())
    assert stmt.periods == ["FY2024", "FY2023"] and stmt.currency == "EUR"
    kinds = {l.tag.split(":")[1]: l.kind for l in stmt.lines}
    assert kinds["GrossProfit"] == SUBTOTAL and kinds["FinanceIncomeCost"] == SUBTOTAL
    assert kinds["ProfitLoss"] == PROFIT and kinds["ProfitLossAttributableToOwnersOfParent"] == ATTRIBUTION
    cost = next(l for l in stmt.lines if l.tag.endswith("CostOfSales"))
    assert cost.amounts["FY2024"] == Decimal(-600)  # debit re-signed as expense
    assert [l.line_id for l in stmt.lines] == sorted(l.line_id for l in stmt.lines)
    assert all(v == 0 for v in stmt.check_items_sum_to_profit().values())


def test_every_corpus_statement_conserves_and_is_fully_labelled():
    manifest = pd.read_csv(ROOT / "corpus" / "manifest.csv")
    assert 15 <= len(manifest) <= 20 and (manifest.split == "dev").sum() == 5
    for slug in manifest.slug:
        stmt = read_csv(ROOT / "corpus" / "statements" / f"{slug}.csv")
        assert all(v == 0 for v in stmt.check_items_sum_to_profit().values()), slug
        labels = yaml.safe_load((ROOT / "corpus" / "labels" / f"{slug}.yaml").read_text())["lines"]
        assert set(labels) == {l.line_id for l in stmt.lines if l.kind == ITEM}, slug
        assert all(v.get("rationale") for v in labels.values()), slug


def test_heldout_accuracy_flags_and_conservation():
    results, conserved = run(ROOT / "corpus")
    assert all(conserved.values())
    s = summarise(results, "heldout")
    assert s["lines"] >= 100
    assert s["accuracy"] >= 0.90
    assert s["accuracy"] > baseline_accuracy(results, "heldout") + 0.15
    assert s["flag_share"] <= 0.25
    assert s["errors_flagged"] == s["errors"]  # every held-out error was sent to review
