"""Rule engine that suggests an IFRS 18 category for each income statement line."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .statement import Statement

CATEGORIES = ("operating", "investing", "financing", "income_taxes", "discontinued")
CATEGORY_LABELS = {
    "operating": "Operating",
    "investing": "Investing",
    "financing": "Financing",
    "income_taxes": "Income taxes",
    "discontinued": "Discontinued operations",
}
ENTITY_TYPES = ("general", "investing", "financing")
DEFAULT_RULES = Path(__file__).with_name("rules.yaml")


@dataclass
class Rule:
    id: str
    description: str
    paragraph: str
    category: dict[str, str]
    tags: frozenset[str] = frozenset()
    tag_regex: re.Pattern | None = None
    label_regex: re.Pattern | None = None
    flag: dict[str, dict] = field(default_factory=dict)

    def matches(self, tag: str, label: str) -> bool:
        local = tag.split(":")[-1]
        if local and local in self.tags:
            return True
        if local and self.tag_regex is not None and self.tag_regex.search(local):
            return True
        return self.label_regex is not None and bool(self.label_regex.search(label.strip()))


@dataclass
class Classification:
    line_id: str
    label: str
    category: str
    rule_id: str
    paragraph: str
    flagged: bool = False
    alternatives: tuple[str, ...] = ()
    reason: str = ""


def _per_entity(value, what: str) -> dict:
    if isinstance(value, dict) and set(value) <= set(ENTITY_TYPES):
        return {et: value.get(et) for et in ENTITY_TYPES}
    return {et: value for et in ENTITY_TYPES}


def load_rules(path: str | Path = DEFAULT_RULES) -> list[Rule]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rules = []
    for r in raw:
        m = r.get("match", {})
        category = _per_entity(r["category"], "category")
        for et, cat in category.items():
            if cat not in CATEGORIES:
                raise ValueError(f"rule {r['id']}: unknown category {cat!r} for {et}")
        flag = r.get("flag")
        flags = {}
        if flag:
            if "reason" in flag:
                flags = {et: flag for et in ENTITY_TYPES}
            else:
                flags = {et: flag[et] for et in flag}
        rules.append(Rule(
            id=r["id"], description=r["description"], paragraph=r["paragraph"], category=category,
            tags=frozenset(m.get("tags", [])),
            tag_regex=re.compile(m["tag_regex"], re.I) if m.get("tag_regex") else None,
            label_regex=re.compile(m["label_regex"], re.I) if m.get("label_regex") else None,
            flag=flags,
        ))
    if not rules or rules[-1].label_regex is None or rules[-1].label_regex.pattern != ".*":
        raise ValueError("the last rule must be a catch-all (label_regex: '.*')")
    return rules


def classify_line(rules: list[Rule], line_id: str, tag: str, label: str, entity_type: str) -> Classification:
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"entity type must be one of {ENTITY_TYPES}")
    for rule in rules:
        if not rule.matches(tag, label):
            continue
        c = Classification(line_id, label, rule.category[entity_type], rule.id, rule.paragraph)
        f = rule.flag.get(entity_type)
        if f and (not f.get("when_label_regex") or re.search(f["when_label_regex"], label.strip(), re.I)):
            c.flagged = True
            c.reason = f["reason"]
            c.alternatives = tuple(a for a in f.get("alternatives", []) if a != c.category)
        return c
    raise AssertionError("unreachable: catch-all rule")


def classify(stmt: Statement, entity_type: str = "general", rules: list[Rule] | None = None) -> dict[str, Classification]:
    """Suggest a category for every component line of the statement."""
    rules = rules if rules is not None else load_rules()
    return {ln.line_id: classify_line(rules, ln.line_id, ln.tag, ln.label, entity_type) for ln in stmt.items()}
