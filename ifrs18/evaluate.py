"""Score the rule engine against the hand-labelled corpus."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import yaml

from .restate import restate
from .rules import classify, load_rules
from .statement import read_csv


@dataclass
class LineResult:
    slug: str
    split: str
    line_id: str
    label: str
    truth: str
    predicted: str
    rule_id: str
    flagged: bool
    ambiguous: bool

    @property
    def correct(self) -> bool:
        return self.truth == self.predicted


def run(corpus_dir: str | Path) -> tuple[list[LineResult], dict[str, bool]]:
    corpus_dir = Path(corpus_dir)
    rules = load_rules()
    results, conserved = [], {}
    with (corpus_dir / "manifest.csv").open() as fh:
        manifest = list(csv.DictReader(fh))
    for m in manifest:
        stmt = read_csv(corpus_dir / "statements" / f"{m['slug']}.csv")
        labels = yaml.safe_load((corpus_dir / "labels" / f"{m['slug']}.yaml").read_text())["lines"]
        classes = classify(stmt, m["entity_type"], rules)
        if set(labels) != set(classes):
            raise ValueError(f"{m['slug']}: labelled lines {sorted(labels)} != statement lines {sorted(classes)}")
        r = restate(stmt, {k: c.category for k, c in classes.items()})
        conserved[m["slug"]] = r.is_conserved()
        for lid, c in classes.items():
            lab = labels[lid]
            results.append(LineResult(m["slug"], m["split"], lid, c.label, lab["category"], c.category,
                                      c.rule_id, c.flagged, bool(lab.get("ambiguous", False))))
    return results, conserved


def summarise(results: list[LineResult], split: str) -> dict:
    rs = [r for r in results if r.split == split]
    wrong = [r for r in rs if not r.correct]
    n = len(rs)
    return {
        "split": split,
        "statements": len({r.slug for r in rs}),
        "lines": n,
        "correct": n - len(wrong),
        "accuracy": (n - len(wrong)) / n if n else 0.0,
        "flagged": sum(r.flagged for r in rs),
        "flag_share": sum(r.flagged for r in rs) / n if n else 0.0,
        "errors": len(wrong),
        "errors_flagged": sum(r.flagged for r in wrong),
        "accuracy_unflagged": (sum(r.correct for r in rs if not r.flagged) / max(1, sum(not r.flagged for r in rs))),
        "non_operating_lines": sum(r.truth != "operating" for r in rs),
        "non_operating_correct": sum(r.correct for r in rs if r.truth != "operating"),
    }


def baseline_accuracy(results: list[LineResult], split: str) -> float:
    """Naive restatement: every line operating except tax and discontinued (what
    an 'everything above tax is operating' spreadsheet would do)."""
    rs = [r for r in results if r.split == split]
    def naive(r):
        return r.predicted if r.predicted in ("income_taxes", "discontinued") else "operating"
    return sum(naive(r) == r.truth for r in rs) / len(rs)
