# The workbook

| Sheet | Content |
|---|---|
| Original | The statement as reported. |
| Mapping | One row per line: category (a drop-down, the reviewer's input), the rule that fired, the IFRS 18 paragraph, a REVIEW flag (highlighted), the alternatives and the reason. |
| Restated | Lines grouped by category, category totals via `SUMIF` on the Mapping sheet, the five subtotals, and the difference from reported profit, which must be zero. |
| MPM | The MPM reconciliation: IFRS subtotal, each adjustment with its tax and NCI effect, and the MPM total. Every amount is `ROUND(…,2)`. |
| Checks | Category totals minus original lines, restated profit minus reported profit, and lines without a valid category. All must be 0. |

The Python results for every subtotal, check and reconciliation cell are stored in a hidden `_expected` sheet. `verify-workbook` converts the file with `soffice --headless` using a throwaway profile under `$TMPDIR` (so your own LibreOffice settings are untouched), reloads the recalculated values and compares them cell by cell.

## Worked example: adjusted EBITDA

`examples/sample_pl.mpm.yaml` defines adjusted EBITDA as operating profit plus depreciation and amortisation (from the notes), goodwill impairment (line L006) and restructuring costs (line L007).

| FY2026 | Amount | Tax effect | NCI effect |
|---|---:|---:|---:|
| Operating profit (IFRS 18 subtotal) | 227,118.85 | | |
| Depreciation and amortisation | 85,400.00 | (21,350.00) | (5,124.00) |
| Impairment of goodwill | 18,000.00 | 0.00 | (1,440.00) |
| Restructuring costs | 12,500.00 | (3,125.00) | (750.00) |
| Adjusted EBITDA | 343,018.85 | (24,475.00) | (7,314.00) |

The synthetic sample's previously reported "operating profit" was 243,919.10. It included the associate and the FX on receivables, and excluded finance items. Under IFRS 18 the associate moves to investing, so operating profit becomes 227,118.85. FX on USD borrowings, lease interest, pension interest and unwinding move to financing; interest income, dividends and investment-property fair-value changes move to investing. Profit for the year stays at 158,712.97.
