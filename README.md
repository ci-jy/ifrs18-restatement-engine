# IFRS 18 Restatement Engine

This tool takes an IFRS income statement and restates it into the five categories IFRS 18 introduces (operating, investing, financing, income taxes and discontinued operations), for both the current and the comparative year, and writes an Excel workbook that still works as a spreadsheet. On 13 real 20-F income statements that I kept out of development, it put 133 of 137 lines in the right category (97.1%), against 72.3% for the naive restatement where everything above tax counts as operating. All four misses were on lines it had already flagged for review.

IFRS 18 replaces IAS 1, and last year's numbers have to be restated alongside the new ones. Most of the line-by-line sorting is easy. The hard part is a handful of lines (interest income, FX differences, equity-accounted results, derivatives) and companies like banks and insurers, where interest and dividends flip into operating. A restatement only regroups lines, so if net income moves, something has gone wrong. That is easy to miss in a hand-built spreadsheet.

![Held-out accuracy per filer: rule engine vs naive restatement](docs/accuracy.png)

## Running it

You need Python and LibreOffice (`sudo apt-get install libreoffice-calc`), which is used to recalculate the workbook.

```bash
pip install -r requirements.txt
python3 -m ifrs18 restate examples/sample_pl.csv --entity-type general -o restated.xlsx
python3 -m ifrs18 verify-workbook restated.xlsx --tolerance 1e-9
```

The first command prints the suggested categories, the lines flagged for review, the new subtotals for both years and an adjusted-EBITDA reconciliation, then writes `restated.xlsx`. The second opens that file in headless LibreOffice, recalculates every formula and compares the results with Python's. `python3 -m pytest -q` runs the tests.

To use your own P&L, export it to CSV with income positive and expenses negative. The CSV columns, the other options (banks, insurers, loading a filing straight from the SEC, overriding categories after review) and the MPM file format are in [docs/usage.md](docs/usage.md).

## How it decides

Classification is an ordered table of 18 rules in `ifrs18/rules.yaml`. Each one matches an XBRL element or a label pattern, names a category per entity type and cites the IFRS 18 paragraph it follows. The first match wins. I used rules rather than a model because a reviewer has to see why a line landed where it did, and 18 statements is nowhere near enough to train on.

Some lines can't be settled from the face of the statement. IFRS 18 puts FX differences and derivative gains in the category of whatever caused them, and the statement rarely says what that was. Those lines get a fallback category and a review flag with the alternatives. Suzano's derivatives (mostly debt swaps) and its exchange variations (mostly on USD debt) were two of the four held-out errors, both flagged.

Loading SEC data took more work than I expected. The `num.txt` file in each quarterly zip has millions of rows, so the loader filters raw lines by accession number before pandas sees them. XBRL stores expenses as positive debits, so every fact is re-signed from the element's debit/credit balance. Filers also print their own totals between the lines, and those have to be spotted or they get counted twice.

The workbook is formulas, not pasted values. Category totals are `SUMIF`s over a Mapping sheet, so changing one line's category in Excel updates every subtotal, the checks and the MPM reconciliation. Python does the sums in `Decimal`, and every amount in the workbook is wrapped in `ROUND(…,2)`. Without that, a spreadsheet summing floats and Python drift apart at the last cent. All 18 filers' workbooks match Python within 1e-9 after LibreOffice recalculates them. What each sheet holds and a worked adjusted-EBITDA example are in [docs/workbook.md](docs/workbook.md).

How the corpus was labelled and the full results are in [docs/evaluation.md](docs/evaluation.md).

## What it can't do yet

- It only reads the face of the income statement. Netted lines such as "other financial results" get one category for the whole amount. Splitting them needs the finance-cost note, which is the next input I'd add.
- The SEC loader rejects filers whose components don't add up to reported profit, for example ones that show revenue and operating profit with no expense lines. It also reads only standalone income statements, not combined P&L and OCI statements.
- Banks and other financing entities still get a "profit before financing and income taxes" subtotal, even though IFRS 18 relaxes it for some of them.
- I wrote the labels myself from public filings, without seeing the companies' own transition decisions, and 18 of the 137 held-out lines are marked ambiguous. The paragraph references should also be checked against the standard itself.

Project period: 2026-09-03 to 2026-09-23.
