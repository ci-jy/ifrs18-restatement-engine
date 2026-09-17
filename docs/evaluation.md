# Evaluation

`python3 scripts/evaluate.py` regenerates [results.md](results.md) and `accuracy.png`.

## Corpus

`corpus/manifest.csv` lists 18 IFRS filers whose 20-F income statements come from the SEC Financial Statement Data Sets for 2025 Q1 and Q2. Five are for development (Ferrari, Lloyds, Nokia, National Grid, GSK) and 13 are held out, including two banks (Lloyds, Barclays) classified as financing entities. `scripts/build_corpus.py` rebuilds `corpus/statements/` from the public zips.

Every line in `corpus/labels/*.yaml` has a category and a written rationale. Lines whose category depends on the notes are marked `ambiguous`. The labels were committed before the rule table was written, and the rules were adjusted only against dev-set results. The one adjustment was to check discontinued operations before income taxes.

## Results

| Split | Statements | Lines | Rule accuracy | Naive baseline | Flagged for review | Errors caught by a flag |
|---|---|---|---|---|---|---|
| dev | 5 | 58 | 100.0% (58/58) | 77.6% | 8.6% (5) | 0/0 |
| heldout | 13 | 137 | 97.1% (133/137) | 72.3% | 13.1% (18) | 4/4 |

Net income was conserved for all 18 statements.

## Held-out errors

All four were flagged, and all are ambiguous on the face of the statement.

| Filer | Line | Labelled | Predicted |
|---|---|---|---|
| Novo Nordisk | Financial income (mostly hedge gains on forecast sales) | operating | investing |
| argenx | Exchange (losses)/gains (mostly on EUR cash) | investing | operating |
| Suzano | Derivative financial instruments (mostly debt swaps) | financing | operating |
| Suzano | Monetary and exchange variations (mostly on USD debt) | financing | operating |
