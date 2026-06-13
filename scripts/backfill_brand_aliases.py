"""A1 — brand→generic alias backfill + brand_name de-smear (eval handoff Part A1).

The eval's E03 "Ozempic" / E07 "Januvia" fail because the brand doesn't resolve to
the rich generic canonical: `entity_aliases` has no brand row, and `brand_name` is
*over-applied* (e.g. "Ozempic" is set on ~30 semaglutide fragment rows, not just the
rich `semaglutide` canonical). Two consequences this fixes:

  1. Resolution — `dossier_kb._alias_lookup` finds nothing for the brand. We add one
     alias per brand → the richest ACTIVE canonical, so resolve_asset('drug:Ozempic')
     lands on the rich generic.
  2. The invariant `test_drugs_with_brand_name_have_alias_entry` wants a self-alias
     per brand-bearing row, but the unique index entity_aliases(entity_type,
     alias_text, source_type) forbids many same-brand aliases. So we DE-SMEAR: keep
     brand_name on the one canonical, clear it from the rest. Then there's one
     brand-bearing row, it has its alias, and the invariant is green.

Conservation: the de-smear is a reversible FIELD edit (never a row delete/merge —
that's the consolidation lane). Every cleared value is written to a manifest;
`--reverse` restores them and removes the inserted aliases. Idempotent + dry-run
by default.

⚠️ Overlaps the consolidation lane (A3): this only CLEARS over-applied brand_name +
adds aliases; it does NOT merge rows. Coordinate via COORDINATION §7.3 before
consolidating the same brands.

Usage:
    python -m scripts.backfill_brand_aliases            # dry-run (default)
    python -m scripts.backfill_brand_aliases --apply
    python -m scripts.backfill_brand_aliases --reverse  # undo from manifest
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Optional

from config import config
from db import Database

logger = logging.getLogger(__name__)

ALIAS_SOURCE = "brand_backfill"
_MANIFEST = os.path.join("benchmark", "reports", "brand_desmear_manifest.json")
_INACTIVE = ("merged", "superseded", "excluded")

# Qualifying brand-bearing drug rows + richness (facts + trials), mirroring the
# resolver's richness signal. Excludes brand==generic (the invariant ignores those).
_BRAND_ROWS_SQL = """
    SELECT d.id::text AS id, TRIM(d.brand_name) AS brand_name,
           d.generic_name, d.record_status,
           (SELECT count(*) FROM facts f WHERE f.subject_entity_id = d.id::text)
         + (SELECT count(*) FROM clinical_trials t WHERE t.drug_id = d.id) AS richness
      FROM drugs d
     WHERE d.brand_name IS NOT NULL
       AND TRIM(d.brand_name) != ''
       AND LOWER(TRIM(d.brand_name)) != LOWER(d.generic_name)
"""


def choose_canonical(rows: list[dict]) -> Optional[str]:
    """Pick the brand's canonical row id: the richest ACTIVE row if any exists,
    else the richest row overall (so a brand on only inactive rows isn't lost).
    Pure / DB-free."""
    if not rows:
        return None
    def key(r):
        active = (r.get("record_status") or "active") not in _INACTIVE
        return (active, r.get("richness") or 0)
    return max(rows, key=key)["id"]


_INSERT_ALIAS_SQL = """
    INSERT INTO entity_aliases (entity_type, entity_id, alias_text, source_type, confidence, verified)
    VALUES ('drug', %s, %s, %s, 1.0, TRUE)
    ON CONFLICT (entity_type, alias_text, source_type) DO NOTHING
"""


def _insert_alias(db, brand: str, canonical_id: str) -> None:
    db.execute(_INSERT_ALIAS_SQL, [canonical_id, brand, ALIAS_SOURCE])


def _clear_brand(db, drug_id: str, old_brand: str, manifest: list[dict]) -> None:
    """Clear an over-applied brand_name (reversibly: record the old value first)."""
    manifest.append({"id": drug_id, "brand_name": old_brand})
    db.execute("UPDATE drugs SET brand_name = NULL WHERE id::text = %s", [drug_id])


def run(*, apply: bool = False, reverse: bool = False) -> dict:
    db = Database(config.db.dsn)
    db.connect()
    try:
        if reverse:
            return _reverse(db, apply=apply)
        return _backfill(db, apply=apply)
    finally:
        db.close()


def _backfill(db, *, apply: bool) -> dict:
    rows = db.fetch_all(_BRAND_ROWS_SQL) or []
    by_brand: dict[str, list[dict]] = {}
    for r in rows:
        by_brand.setdefault(r["brand_name"].lower(), []).append(r)

    stats = {"brands": 0, "aliases_inserted": 0, "rows_desmeared": 0, "skipped": 0}
    manifest: list[dict] = []
    for brand_key, brand_rows in by_brand.items():
        brand = brand_rows[0]["brand_name"]  # original case
        canonical = choose_canonical(brand_rows)
        if not canonical:
            stats["skipped"] += 1
            continue
        stats["brands"] += 1
        if apply:
            _insert_alias(db, brand, canonical)
        stats["aliases_inserted"] += 1
        for r in brand_rows:
            if r["id"] != canonical:
                if apply:
                    _clear_brand(db, r["id"], r["brand_name"], manifest)
                else:
                    manifest.append({"id": r["id"], "brand_name": r["brand_name"]})
                stats["rows_desmeared"] += 1

    if apply and manifest:
        os.makedirs(os.path.dirname(_MANIFEST), exist_ok=True)
        with open(_MANIFEST, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
        logger.info("wrote de-smear manifest: %s (%d rows)", _MANIFEST, len(manifest))
    stats["manifest_rows"] = len(manifest)
    return stats


def _reverse(db, *, apply: bool) -> dict:
    if not os.path.exists(_MANIFEST):
        logger.warning("no manifest at %s — nothing to reverse", _MANIFEST)
        return {"restored": 0}
    with open(_MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    restored = 0
    for entry in manifest:
        if apply:
            db.execute("UPDATE drugs SET brand_name = %s WHERE id::text = %s AND brand_name IS NULL",
                       [entry["brand_name"], entry["id"]])
        restored += 1
    if apply:
        db.execute("DELETE FROM entity_aliases WHERE source_type = %s", [ALIAS_SOURCE])
    return {"restored": restored}


def main():
    ap = argparse.ArgumentParser(description="Backfill brand→generic aliases + de-smear brand_name")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument("--reverse", action="store_true", help="undo from the manifest")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    stats = run(apply=args.apply, reverse=args.reverse)
    print("\n=== brand alias backfill ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if not args.apply:
        print("  (dry-run — no changes written)")


if __name__ == "__main__":
    main()
