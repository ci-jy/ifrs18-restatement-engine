import re

import pytest

from ifrs18.rules import CATEGORIES, classify, classify_line, load_rules
from ifrs18.statement import read_csv

RULES = load_rules()


def cat(label, tag="", entity="general"):
    return classify_line(RULES, "X", tag, label, entity)


def test_every_rule_cites_an_ifrs18_paragraph():
    for r in RULES:
        assert re.match(r"IFRS 18\.(\d+|B\d+)", r.paragraph), r.id
        assert set(r.category.values()) <= set(CATEGORIES)


@pytest.mark.parametrize("entity", ["general", "investing", "financing"])
def test_equity_accounted_results_are_investing_for_every_entity(entity):
    assert cat("Share of profit of associate (equity-accounted)", entity=entity).category == "investing"
    assert cat("Result from investments", "ifrs-full:ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod",
               entity).category == "investing"


def test_interest_income_switches_with_main_business_activity():
    assert cat("Interest income on cash and cash equivalents").category == "investing"
    assert cat("Interest income on cash and cash equivalents", entity="investing").category == "operating"
    assert cat("Interest income", "ifrs-full:RevenueFromInterest", "financing").category == "operating"
    assert cat("Dividend income from equity investments", entity="investing").category == "operating"
    assert cat("Fair value gain/(loss) on investment property").category == "investing"


def test_interest_expense_and_financing_entities():
    assert cat("Interest expense on borrowings").category == "financing"
    bank = cat("Interest expense", "ifrs-full:InterestExpense", "financing")
    assert bank.category == "operating" and bank.flagged and "financing" in bank.alternatives


def test_fx_follows_the_item_that_gave_rise_to_it():
    assert cat("Foreign exchange gain/(loss) on USD borrowings").category == "financing"
    assert cat("Exchange differences on cash balances").category == "investing"
    fx = cat("Foreign exchange gains/(losses) on trade receivables")
    assert fx.flagged and fx.category == "operating" and set(fx.alternatives) == {"investing", "financing"}
    assert cat("Net foreign exchange gains/losses", "ifrs-full:GainsLossesOnExchangeDifferencesOnTranslationRecognisedInProfitOrLoss").flagged


def test_ambiguous_lines_are_flagged_with_reason_not_guessed_silently():
    for label in ["Fair value loss on derivatives", "Net monetary gain arising from hyperinflationary economies",
                  "Other financial results", "Financial income"]:
        c = cat(label)
        assert c.flagged and c.reason and c.alternatives, label


def test_pension_interest_and_unwinding_are_financing():
    assert cat("Net interest on defined benefit pension liability").category == "financing"
    assert cat("Unwinding of discount on decommissioning provisions").category == "financing"


def test_taxes_and_discontinued():
    assert cat("Income tax expense").category == "income_taxes"
    assert cat("Profit after taxation from discontinued operations").category == "discontinued"
    assert cat("Share of post-tax results of associates").category == "investing"


def test_classify_sample_records_rule_and_paragraph(sample_csv):
    classes = classify(read_csv(sample_csv))
    assert len(classes) == 21
    assert all(c.rule_id and c.paragraph for c in classes.values())
    assert classes["L009"].category == "investing"
    assert classes["L014"].category == "financing"
    assert classes["L001"].rule_id == "operating-residual"
