# Usage

## Input CSV

```csv
line_id,label,tag,kind,FY2026,FY2025
L001,Revenue,,item,1250000.00,1180000.00
L002,Cost of sales,,item,-742500.40,-701230.15
S_GP,Gross profit,,subtotal,507499.60,478769.85
...
S_PL,Profit for the year,,profit,158712.97,164623.40
S_NCI,Attributable to non-controlling interests,,attribution,12697.04,13169.87
```

- Amounts are signed so the lines add up to profit: income positive, expenses negative. Parentheses and thousands separators are accepted.
- `kind` is `item` (a component of profit), `subtotal` (a presented total, ignored when restating), `profit` or `attribution`. It defaults to `item`.
- `tag` is optional. When it holds an XBRL element (for example `ifrs-full:FinanceIncome`), rules match on it before falling back to the label.
- The first period column is the current year and the second is the comparative.

A full example is `examples/sample_pl.csv`.

## Commands

```bash
python3 -m ifrs18 restate my_pl.csv --entity-type general -o restated.xlsx \
    --mpm my_adjusted_ebitda.yaml          # optional; <input>.mpm.yaml is picked up automatically
python3 -m ifrs18 restate my_pl.csv --mapping reviewed.csv -o restated.xlsx   # line_id,category overrides after review
python3 -m ifrs18 restate --sec-adsh 0001160106-25-000005 --sec-quarter 2025q1 --entity-type financing -o lloyds.xlsx
python3 -m ifrs18 rules                     # list the rule table
python3 -m ifrs18 verify-workbook restated.xlsx --tolerance 1e-9
```

`restate` options:

| Option | Meaning |
|---|---|
| `input` | P&L CSV (omit when using `--sec-adsh`) |
| `--entity-type` | `general` (default), `investing` or `financing` |
| `--mpm` | MPM definition YAML; defaults to `<input>.mpm.yaml` if it exists |
| `--mapping` | CSV of `line_id,category` overrides, applied after the rules |
| `--rules` | alternative rules YAML |
| `--sec-adsh` | accession number of a 20-F/40-F in the SEC Financial Statement Data Sets |
| `--sec-zip` | local quarterly FSDS zip (repeatable) |
| `--sec-quarter` | quarter to download, e.g. `2025q1` (repeatable); cached under `$TMPDIR/sec-fsds` |
| `--user-agent` | User-Agent sent to the SEC when downloading |
| `-o`, `--output` | output `.xlsx` (required) |

`restate` exits with status 1 if net income is not conserved.

## Entity types

`--entity-type investing` (main business is investing in assets, such as insurers or investment entities) and `--entity-type financing` (main business is lending to customers, such as banks) switch interest, dividends and fair-value returns into operating, as IFRS 18 requires. Equity-accounted results stay in investing either way.

## MPM definitions

An MPM is an IFRS 18 subtotal plus a list of adjustments. Each adjustment is either an amount per period taken from the notes, or an add-back of a P&L line by `line_id`, with its own tax rate and NCI share:

```yaml
name: Adjusted EBITDA
subtotal: operating_profit
adjustments:
  - label: Depreciation and amortisation (from the PP&E and intangibles notes)
    amounts: {FY2026: 85400.00, FY2025: 81200.00}
    tax_rate: 0.25
    nci_share: 0.08
  - label: Impairment of goodwill
    line: L006
    tax_rate: 0
    nci_share: 0.08
```

Tax effect is `-amount * tax_rate` and NCI effect is `-(amount + tax) * nci_share`, each rounded half-up to the cent, the same as Excel's `ROUND`.

## Tests

```bash
python3 -m pytest -q
```

The tests cover Hypothesis properties on random statements (profit is conserved under any classification, subtotals equal the sum of their categories, MPMs tie to the cent), LibreOffice round trips for the sample and all 18 corpus filers, the hard classification cases, the SEC loader, corpus integrity and the held-out accuracy thresholds, and the CLI.
