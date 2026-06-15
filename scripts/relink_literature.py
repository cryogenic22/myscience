#!/usr/bin/env python
"""D4 — back-data relink of pubmed_articles to drugs via name mentions.

66% of pubmed_articles had a NULL drug_id, so they never surfaced for a drug.
The existing fix_data_quality matcher used generic_name only, substring (not
word-boundary) matching, included merged dup rows, and broke ties by random
dict order. This builds a richer, deterministic name index — generic_name +
brand_name + confirmed aliases, canonical (non-merged) rows only — and matches
on word boundaries, breaking ties by richness (facts+trials).

Additive + idempotent: only fills NULL drug_id; re-runs touch nothing new.
After it lands, re-run LiteratureEmitter for fresh key_publication /
disease_evidence facts.

Usage:
    DATABASE_URL=... python -m scripts.relink_literature [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import Database  # noqa: E402

# Drug-name tokens shorter than this, or that are generic English / drug-class
# words, are too noisy to match safely.
_MIN_NAME_LEN = 5
_STOPNAMES = {
    "beta blockers", "blockers", "agonist", "agonists", "inhibitor", "inhibitors",
    "statin", "statins", "insulin", "placebo", "vaccine", "saline", "control",
    "water", "sodium", "glucose", "oxygen", "vitamin",
    # Polluted drug rows surfaced by the C1 prod probe (14-Jun-2026): these exist
    # as rows in `drugs` but are NOT drugs — matching them silently corrupts the
    # link (e.g. a behavioral trial whose title says "lifestyle intervention" would
    # resolve to a drug literally named "intervention"). Dropping them from the
    # match index is a precision improvement for both literature and trial
    # relinking; soft-deleting the rows themselves is a separate cleanup follow-up.
    "intervention", "medication", "titration", "treatment", "therapy",
    "no intervention", "active control", "rate control", "formulation 1",
    "usual care", "standard care", "standard of care", "best supportive care",
}


@dataclass
class DrugName:
    drug_id: str
    name: str
    richness: int


def build_name_index(rows: list[dict]) -> dict[str, DrugName]:
    """rows: {drug_id, name, richness}. Returns lower(name) -> richest DrugName.

    Drops too-short and stop-list names. On a name collision (two drugs share a
    name), keeps the richer one — matching the resolver's canonical ranking.
    """
    index: dict[str, DrugName] = {}
    for r in rows:
        name = (r["name"] or "").lower().strip()
        if len(name) < _MIN_NAME_LEN or name in _STOPNAMES:
            continue
        richness = int(r.get("richness") or 0)
        existing = index.get(name)
        if existing is None or richness > existing.richness:
            index[name] = DrugName(str(r["drug_id"]), name, richness)
    return index


def compile_matcher(name_index: dict[str, DrugName]) -> "re.Pattern | None":
    """One alternation regex over all names, longest-first so the most specific
    name wins. ~3,800 per-name searches → one scan per article (the naive loop
    was ~11M regex calls and far too slow for the full table)."""
    names = sorted(name_index.keys(), key=len, reverse=True)
    if not names:
        return None
    alt = "|".join(re.escape(n) for n in names)
    return re.compile(r"\b(" + alt + r")\b")


def match_drug_in_text(
    text: str,
    name_index: dict[str, DrugName],
    matcher: "re.Pattern | None" = None,
) -> DrugName | None:
    """Return the best DrugName mentioned (word-boundary) in text, or None.

    'Best' = the longest matching name (more specific) then richest. ``matcher``
    is an optional precompiled alternation (compile_matcher) for speed; if omitted
    it is built on the fly (fine for tests / single calls).
    """
    if not text:
        return None
    text = text.lower()
    matcher = matcher or compile_matcher(name_index)
    if matcher is None:
        return None
    found = {m.group(1) for m in matcher.finditer(text)}
    if not found:
        return None
    best = max(
        (name_index[n] for n in found),
        key=lambda d: (len(d.name), d.richness),
    )
    return best


def _load_name_index(db: Database) -> dict[str, DrugName]:
    rows = db.fetch_all(
        """
        WITH richness AS (
            SELECT d.id,
                   (SELECT count(*) FROM facts f WHERE f.subject_entity_id = d.id::text)
                 + (SELECT count(*) FROM clinical_trials ct WHERE ct.drug_id = d.id) AS r
            FROM drugs d
            WHERE d.record_status IS NULL
               OR d.record_status NOT IN ('merged', 'superseded', 'excluded')
        )
        SELECT d.id AS drug_id, d.generic_name AS name, richness.r AS richness
          FROM drugs d JOIN richness ON richness.id = d.id
         WHERE d.generic_name IS NOT NULL
        UNION ALL
        SELECT d.id AS drug_id, d.brand_name AS name, richness.r AS richness
          FROM drugs d JOIN richness ON richness.id = d.id
         WHERE d.brand_name IS NOT NULL
        UNION ALL
        SELECT a.entity_id::uuid AS drug_id, a.alias_text AS name,
               COALESCE(richness.r, 0) AS richness
          FROM entity_aliases a
          LEFT JOIN richness ON richness.id = a.entity_id::uuid
         WHERE a.entity_type = 'drug'
        """
    )
    return build_name_index(rows)


def relink(db: Database, limit: int | None = None, dry_run: bool = False) -> dict:
    name_index = _load_name_index(db)
    matcher = compile_matcher(name_index)
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    articles = db.fetch_all(
        f"""
        SELECT id, title, abstract FROM pubmed_articles
        WHERE drug_id IS NULL {limit_sql}
        """
    )
    matched = 0
    for art in articles:
        text = ((art["title"] or "") + " " + (art["abstract"] or ""))
        dn = match_drug_in_text(text, name_index, matcher)
        if not dn:
            continue
        matched += 1
        if not dry_run:
            db.execute(
                "UPDATE pubmed_articles SET drug_id = %s WHERE id = %s AND drug_id IS NULL",
                [dn.drug_id, art["id"]],
            )
    return {"candidates": len(articles), "matched": matched, "dry_run": dry_run}


def run(dry_run: bool = False) -> dict:
    """Scheduler entrypoint (called from scripts/auto_curate.py post-tasks) so
    literature relinking is self-healing every curate cycle — new NULL-drug_id
    articles don't accumulate back over the orphan ceiling."""
    from config import config

    db = Database(config.db.dsn)
    db.connect()
    try:
        return relink(db, dry_run=dry_run)
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("db_url", nargs="?", default=os.environ.get("DATABASE_URL"))
    args = ap.parse_args()
    if not args.db_url:
        sys.exit("Pass a DB url or set DATABASE_URL.")
    db = Database(args.db_url)
    db.connect()
    try:
        print(relink(db, limit=args.limit, dry_run=args.dry_run))
    finally:
        db.close()


if __name__ == "__main__":
    main()
