#!/usr/bin/env python
"""Correct drugs whose coarse MeSH mechanism is clinically wrong.

The CLIN-02 eval failure (docs/raw_notes.md): tirzepatide and semaglutide point
at the SAME mechanism row, "Glucagon-Like Peptide-1 Receptor Agonists" (MeSH
D000097789). Tirzepatide is the first GIP/GLP-1 "twincretin"; calling it a pure
GLP-1 agonist is a domain-correctness error. The coarse MeSH class collapsed the
whole incretin co-agonist family (tirzepatide, retatrutide, survodutide, ...)
into pure GLP-1 — and ``scripts/backfill_mechanisms.py`` encoded that collapse.

This script:
  1. ensures the curated co-agonist mechanism rows exist (idempotent, by name),
  2. repoints each mis-tagged active drug to its correct mechanism,
  3. closes the stale ``mechanism_of_action`` fact and re-emits the corrected one
     via the existing MechanismEmitter.

Scope = ``backfill_mechanisms.CO_AGONIST_CORRECTIONS`` (one source of truth with
the backfill map, so a NULL-backfill and a correction never disagree).

Conservation
------------
* Repoint records the prior ``mechanism_id`` in a drop-manifest → reversible
  (``UPDATE drugs SET mechanism_id = <prior> WHERE id = ...``); not a silent
  overwrite.
* Only repoints ACTIVE drugs whose ``generic_name`` is a normalized-EXACT match
  to a corrected generic AND whose current mechanism differs — never fuzzy, so
  "semaglutide or tirzepatide" junk rows and semaglutide itself are untouched.
* Stale facts are soft-closed (``valid_to``), append-only honored; the corrected
  fact is emitted idempotently. Re-run = no-op. Dry-run by default.

Usage:
    python -m scripts.correct_drug_mechanisms             # dry-run
    python -m scripts.correct_drug_mechanisms --apply     # write
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from scripts.backfill_mechanisms import (
    CO_AGONIST_CORRECTIONS,
    CURATED_CO_AGONIST_MECHANISMS,
)

logger = logging.getLogger(__name__)

_INSERT_MECH = """
    INSERT INTO mechanisms_of_action (name, mechanism_class, scope_note,
                                      source_api, source_url, retrieved_at)
    VALUES (%s, %s, %s, 'curated_sme', 'curated:sme/incretin_co_agonists', NOW())
    RETURNING id
"""
_CLOSE_OLD_FACT = """
    UPDATE facts SET valid_to = COALESCE(valid_to, asserted_at)
     WHERE predicate = 'mechanism_of_action'
       AND subject_entity_type = 'drug'
       AND subject_entity_id = %s
       AND superseded_by IS NULL
       AND valid_to IS NULL
       AND COALESCE(object_value->>'source_row_id', '') <> %s
"""


def ensure_curated_mechanisms(db, *, apply: bool) -> dict:
    """Return {mechanism_name: id}, creating curated rows that don't yet exist."""
    existing = {r["name"]: str(r["id"])
                for r in db.fetch_all("SELECT id, name FROM mechanisms_of_action", [])}
    for spec in CURATED_CO_AGONIST_MECHANISMS:
        if spec["name"] in existing:
            continue
        if not apply:
            logger.info("[DRY-RUN] would create mechanism %r", spec["name"])
            continue
        row = db.fetch_one(_INSERT_MECH,
                           [spec["name"], spec["mechanism_class"], spec["scope_note"]])
        existing[spec["name"]] = str(row["id"])
        logger.info("created mechanism %r -> %s", spec["name"], existing[spec["name"]])
    return existing


def find_mistagged(db, mech_ids: dict) -> list[dict]:
    """Active drug rows whose generic_name is a corrected co-agonist and whose
    current mechanism_id is not already the correct one."""
    out = []
    for generic, correct_name in CO_AGONIST_CORRECTIONS.items():
        correct_id = mech_ids.get(correct_name)
        rows = db.fetch_all(
            """SELECT id, generic_name, mechanism_id FROM drugs
                WHERE lower(generic_name) = %s
                  AND COALESCE(record_status, 'active') NOT IN ('merged', 'superseded')""",
            [generic],
        )
        for r in rows:
            cur_mech = str(r["mechanism_id"]) if r["mechanism_id"] else None
            if cur_mech == correct_id:
                continue  # already correct
            out.append({"drug_id": str(r["id"]), "generic": r["generic_name"],
                        "from_mech": cur_mech, "to_mech": correct_id,
                        "to_name": correct_name})
    return out


def correct(db, *, apply: bool, manifest_path: Optional[str] = None) -> dict:
    mech_ids = ensure_curated_mechanisms(db, apply=apply)
    if not apply:
        # In dry-run the curated rows may not exist yet → resolve to a sentinel so
        # find_mistagged still reports what WOULD change.
        for spec in CURATED_CO_AGONIST_MECHANISMS:
            mech_ids.setdefault(spec["name"], "<new>")
    targets = find_mistagged(db, mech_ids)

    if apply and targets:
        from services.fact_emitters.base import run_emitter
        from services.fact_emitters.mechanisms import MechanismEmitter
        emitter = MechanismEmitter()
        for t in targets:
            db.execute("UPDATE drugs SET mechanism_id = %s WHERE id = %s",
                       [t["to_mech"], t["drug_id"]])
            db.execute(_CLOSE_OLD_FACT, [t["drug_id"], str(t["to_mech"])])
            run_emitter(db, emitter, drug_id=t["drug_id"])
        if manifest_path:
            with open(manifest_path, "w", encoding="utf-8") as fh:
                json.dump({"corrected_at": datetime.now(timezone.utc).isoformat(),
                           "reason": "co_agonist_mechanism_correction",
                           "count": len(targets), "drugs": targets}, fh, indent=2)
    return {"matched": len(targets), "applied": apply, "targets": targets}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write changes")
    ap.add_argument("--manifest", default="benchmark/reports/mechanism_correction_manifest.json")
    args = ap.parse_args()

    from db import Database
    dsn = os.environ.get("DATABASE_URL") or __import__("config").config.db.dsn
    db = Database(dsn)
    db.connect()
    try:
        res = correct(db, apply=args.apply,
                      manifest_path=args.manifest if args.apply else None)
    finally:
        db.close()

    mode = "APPLIED" if args.apply else "DRY-RUN"
    logger.info("[%s] mis-tagged co-agonist drugs matched=%d", mode, res["matched"])
    for t in res["targets"]:
        logger.info("  %s (%s)  %s -> %s", t["generic"], t["drug_id"][:8],
                    (t["from_mech"] or "NULL")[:8], t["to_name"])


if __name__ == "__main__":
    main()
