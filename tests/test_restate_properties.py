"""Property-based proof that restatement conserves profit under any classification."""
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from ifrs18.mpm import cents, parse_definition, reconcile
from ifrs18.restate import SUBTOTALS, restate
from ifrs18.rules import CATEGORIES
from ifrs18.statement import ITEM, PROFIT, SUBTOTAL, Line, Statement

PERIODS = ["FY2026", "FY2025"]
amount = st.decimals(min_value=Decimal("-1e13"), max_value=Decimal("1e13"), places=2, allow_nan=False, allow_infinity=False)


@st.composite
def statements(draw):
    n = draw(st.integers(1, 40))
    lines = [Line(f"L{i:03d}", f"line {i}", {p: draw(amount) for p in PERIODS}) for i in range(n)]
    # interleave presented subtotals that must be ignored
    for k in draw(st.lists(st.integers(0, n), max_size=4)):
        lines.insert(min(k, len(lines)), Line(f"S{k}", "subtotal", {p: draw(amount) for p in PERIODS}, kind=SUBTOTAL))
    items = [ln for ln in lines if ln.kind == ITEM]
    lines.append(Line("P", "Profit", {p: sum((ln.amounts[p] for ln in items), Decimal(0)) for p in PERIODS}, kind=PROFIT))
    return Statement("test", PERIODS, lines)


@st.composite
def classified(draw):
    stmt = draw(statements())
    # adversarial: any category for any line, including everything in one bucket
    mode = draw(st.sampled_from(["random", "all-same", "alternating"]))
    ids = [ln.line_id for ln in stmt.items()]
    if mode == "random":
        mapping = {i: draw(st.sampled_from(CATEGORIES)) for i in ids}
    elif mode == "all-same":
        c = draw(st.sampled_from(CATEGORIES))
        mapping = {i: c for i in ids}
    else:
        mapping = {i: CATEGORIES[k % len(CATEGORIES)] for k, i in enumerate(ids)}
    return stmt, mapping


@settings(max_examples=400, deadline=None)
@given(classified())
def test_any_classification_conserves_net_income_exactly(case):
    stmt, mapping = case
    r = restate(stmt, mapping)
    assert r.is_conserved()
    for p in PERIODS:
        assert r.subtotals[p]["profit"] == stmt.profit_line().amounts[p]
        assert sum(r.category_totals[p].values(), Decimal(0)) == stmt.item_total(p)


@settings(max_examples=400, deadline=None)
@given(classified())
def test_every_subtotal_adds_up(case):
    stmt, mapping = case
    r = restate(stmt, mapping)
    for p in PERIODS:
        t, s = r.category_totals[p], r.subtotals[p]
        for key, _, cats in SUBTOTALS:
            assert s[key] == sum((ln.amounts[p] for ln in stmt.items() if mapping[ln.line_id] in cats), Decimal(0))
        assert s["pbfit"] == s["operating_profit"] + t["investing"]
        assert s["profit_before_tax"] == s["pbfit"] + t["financing"]
        assert s["profit_continuing"] == s["profit_before_tax"] + t["income_taxes"]
        assert s["profit"] == s["profit_continuing"] + t["discontinued"]


@settings(max_examples=200, deadline=None)
@given(classified(), st.data())
def test_reclassifying_one_line_moves_it_between_categories_only(case, data):
    stmt, mapping = case
    lid = data.draw(st.sampled_from(sorted(mapping)))
    new = data.draw(st.sampled_from(CATEGORIES))
    a = restate(stmt, mapping)
    b = restate(stmt, {**mapping, lid: new})
    for p in PERIODS:
        assert a.subtotals[p]["profit"] == b.subtotals[p]["profit"]


@settings(max_examples=300, deadline=None)
@given(classified(), st.lists(st.tuples(amount, st.decimals(0, 1, places=4), st.decimals(0, 1, places=4)), max_size=6),
       st.sampled_from([k for k, _, _ in SUBTOTALS]))
def test_mpm_reconciliation_ties_to_the_cent(case, adjs, subtotal):
    stmt, mapping = case
    r = restate(stmt, mapping)
    defn = parse_definition({"name": "MPM", "subtotal": subtotal, "adjustments": [
        {"label": f"a{i}", "amounts": {p: str(a) for p in PERIODS}, "tax_rate": str(t), "nci_share": str(n)}
        for i, (a, t, n) in enumerate(adjs)]})
    for p in PERIODS:
        rec = reconcile(defn, r, p)
        assert rec.subtotal == cents(r.subtotals[p][subtotal])
        assert rec.mpm == rec.subtotal + sum((x.amount for x in rec.rows), Decimal(0))
        for x in rec.rows:
            assert x.amount == x.amount.quantize(Decimal("0.01"))
            assert x.tax_effect == x.tax_effect.quantize(Decimal("0.01"))
            assert x.nci_effect == x.nci_effect.quantize(Decimal("0.01"))
        assert rec.total_tax == sum((x.tax_effect for x in rec.rows), Decimal(0))


def test_missing_or_unknown_category_is_rejected():
    stmt = Statement("t", PERIODS, [Line("A", "a", {p: Decimal(1) for p in PERIODS})])
    import pytest
    with pytest.raises(ValueError):
        restate(stmt, {})
    with pytest.raises(ValueError):
        restate(stmt, {"A": "other"})
