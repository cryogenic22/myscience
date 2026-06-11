#!/usr/bin/env python
"""Retire already-asserted FAERS ``adverse_event`` facts that are NOT adverse
drug reactions (medication errors, lack-of-efficacy PTs).

Background (docs/raw_notes.md / eval PV-01)
-------------------------------------------
The AdverseEventEmitter used to lift every MedDRA preferred term as a safety
fact. On prod the dominant GLP-1 "adverse events" were medication errors
("Incorrect dose administered" 35x, "Drug ineffective" 49x, "Off label use",
"Accidental overdose", ...). Rendered in a dossier they imply the drug carries
serious *harms* when the report is really a use error — the regression flagged
in raw_notes.md.

``services/fact_emitters/adverse_events.py`` now drops these at emission via
``is_non_adr_term``. This script applies the *same* classifier to facts already
in the ledger and retires them.

Conservation
------------
* The facts ledger is append-only (no DELETE). Retraction is a REVERSIBLE
  soft-close: ``valid_to`` is set to the fact's ``asserted_at`` so it is no
  longer valid as-of now (``facts_ledger._valid_at`` excludes it) while the row
  and its evidence stay for audit/replay.
* Every retired id + reaction is written to a drop-manifest JSON so the change
  is fully reversible: ``UPDATE facts SET valid_to = NULL WHERE id = ANY(...)``.
* The classifier is imported, never re-implemented — one source of truth.
* Idempotent (a re-run finds the retired facts already closed → no-op) and
  dry-run by default.

Usage:
    python -m scripts.retract_non_adr_faers_facts            # dry-run
    python -m scripts.retract_non_adr_faers_facts --apply    # write
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from services.fact_emitters.adverse_events import is_non_adr_term

logger = logging.getLogger(__name__)


# ── pure helper (DB-free, unit-tested) ──────────────────────────────────────

def extract_reaction(object_value: dict) -> str:
    """The MedDRA reaction term from a stored ``adverse_event`` fact. Prefers the
    explicit ``reaction`` key; falls back to the head of the description
    ('Incorrect dose administered — 35 reports' -> 'Incorrect dose administered')."""
    if not isinstance(object_value, dict):
        return ""
    rxn = (object_value.get("reaction") or "").strip()
    if rxn:
        return rxn
    desc = (object_value.get("description") or "").strip()
    # split on the em dash the emitter uses, else the whole string
    return desc.split(" — ")[0].strip() if " — " in desc else desc


_SELECT_OPEN_AE = """
    SELECT id, subject_entity_id, object_value, asserted_at
      FROM facts
     WHERE predicate = 'adverse_event'
       AND superseded_by IS NULL
       AND valid_to IS NULL
"""

_CLOSE_SQL = "UPDATE facts SET valid_to = asserted_at WHERE id = %s"


def find_non_adr_facts(db) -> list[dict]:
    """Open (non-superseded, not-yet-closed) adverse_event facts whose reaction
    the emitter would now reject."""
    rows = db.fetch_all(_SELECT_OPEN_AE, [])
    out = []
    for r in rows:
        ov = r.get("object_value") or {}
        if isinstance(ov, str):
            try:
                ov = json.loads(ov)
            except (ValueError, TypeError):
                ov = {}
        reaction = extract_reaction(ov)
        if reaction and is_non_adr_term(reaction):
            out.append({"id": str(r["id"]),
                        "subject": str(r.get("subject_entity_id")),
                        "reaction": reaction})
    return out


def retract(db, *, apply: bool, manifest_path: Optional[str] = None) -> dict:
    targets = find_non_adr_facts(db)
    if apply and targets:
        for t in targets:
            db.execute(_CLOSE_SQL, [t["id"]])
        if manifest_path:
            stamp = datetime.now(timezone.utc).isoformat()
            with open(manifest_path, "w", encoding="utf-8") as fh:
                json.dump({"retired_at": stamp, "reason": "non_adr_faers_term",
                           "count": len(targets), "facts": targets}, fh, indent=2)
    return {"matched": len(targets), "applied": apply, "targets": targets}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write changes")
    ap.add_argument("--manifest", default="benchmark/reports/retract_non_adr_manifest.json")
    args = ap.parse_args()

    from db import Database
    dsn = os.environ.get("DATABASE_URL") or __import__("config").config.db.dsn
    db = Database(dsn)
    db.connect()
    try:
        res = retract(db, apply=args.apply,
                      manifest_path=args.manifest if args.apply else None)
    finally:
        db.close()

    mode = "APPLIED" if args.apply else "DRY-RUN"
    logger.info("[%s] non-ADR adverse_event facts matched=%d", mode, res["matched"])
    from collections import Counter
    by_rxn = Counter(t["reaction"] for t in res["targets"])
    for rxn, n in by_rxn.most_common(30):
        logger.info("  %4d  %s", n, rxn)
    if args.apply:
        logger.info("manifest -> %s (reverse with: UPDATE facts SET valid_to=NULL "
                    "WHERE id = ANY(<manifest ids>))", args.manifest)


if __name__ == "__main__":
    main()
