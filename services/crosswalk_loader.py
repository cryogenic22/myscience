#!/usr/bin/env python
"""Loop L1b — load governed ATC crosswalk records + backfill drugs.atc_codes.

Reads the SME-curated ATC seed mappings from the crosswalk pack, resolves each to
the richest active drug row, asks services.ontology_crosswalk.classify() for the
GOVERNED relation/scope/confidence/flags/action (ATC L5 -> molecule is always
`related`, substance-level — never identity), and persists:
  * a crosswalk_records row (idempotent on the natural key), and
  * the ATC code appended to drugs.atc_codes (idempotent; never overwrites).

Conservation: a drug that cannot be resolved is COUNTED and skipped, never dropped;
records enrich, never overwrite. Dry-run by default.

The seed set is SME smoke-test data (docs/pharmcore_atc.md §6). The bulk WHO ATC /
RxNorm release load plugs into the same path and is Loop L1b-ii.

Usage (run as a module from the worktree root so cwd wins over the editable-install
config.py shadow):
    DATABASE_URL=... python -m services.crosswalk_loader            # dry run
    DATABASE_URL=... python -m services.crosswalk_loader --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

from db import Database
from services.ontology_crosswalk import (
    CrosswalkCandidate,
    classify,
    load_crosswalk_pack,
)

SOURCE_VERSION = "sme_seed_pharmcore_atc_2026-06-09"


def seed_atc_mappings(pack: dict) -> list[dict]:
    """Pure: extract [{drug_name, atc_l5, atc_l4, atc_l4_label}] from the pack."""
    out = []
    for name, ex in (pack.get("seed_examples") or {}).items():
        if ex.get("atc_l5"):
            out.append({"drug_name": name, "atc_l5": ex["atc_l5"],
                        "atc_l4": ex.get("atc_l4"), "atc_l4_label": ex.get("atc_l4_label")})
    return out


def build_atc_candidate(atc_l5: str, source_curated: bool = True) -> CrosswalkCandidate:
    """Pure: an ATC L5 code asserting a molecule classification (related, not identity).

    source_curated grants the curated-crosswalk boost — true for SME seeds, but the
    bulk WHO-release path (L1b-ii) must pass False (a raw release code is not curated).
    """
    return CrosswalkCandidate(
        from_system="atc", level=5, to_target="molecule",
        method="external_source_crosswalk", external_id=atc_l5, source_curated=source_curated)


# An action that ACCEPTS the mapping — only these may enrich the drug spine.
_SPINE_ACTIONS = {"approved_auto", "approved_with_audit"}


def _review_status_for(action: str) -> str:
    """Derive the persisted review_status from the engine's action (faithful, not
    hardcoded) so a steward queue and the review index reflect reality."""
    return {
        "approved_auto": "approved",
        "approved_with_audit": "machine_only",   # accepted, available for audit
        "review_required": "pending_review",
        "rejected_or_quarantined": "rejected",
    }.get(action, "machine_only")


def _should_backfill_spine(rec) -> bool:
    """A code may only touch drugs.atc_codes when the engine ACCEPTED the mapping
    (not rejected/quarantined, not merely pending review)."""
    return rec.relation != "rejected" and rec.action in _SPINE_ACTIONS


def _resolve_richest_drug(db: Database, name: str) -> dict | None:
    """Richest active drug row for a generic name (agrees with the resolver)."""
    return db.fetch_one(
        """
        SELECT id, generic_name
        FROM drugs
        WHERE LOWER(generic_name) = LOWER(%s)
          AND (record_status IS NULL OR record_status NOT IN ('merged','superseded','excluded'))
        ORDER BY (SELECT count(*) FROM facts f WHERE f.subject_entity_id = drugs.id::text)
               + (SELECT count(*) FROM clinical_trials ct WHERE ct.drug_id = drugs.id) DESC
        LIMIT 1
        """,
        [name],
    )


def load_atc_seeds(db: Database, pack: dict, apply: bool = False) -> Counter:
    stats: Counter = Counter()
    for seed in seed_atc_mappings(pack):
        stats["seeds"] += 1
        drug = _resolve_richest_drug(db, seed["drug_name"])
        if not drug:
            stats["unresolved_drug"] += 1
            print(f"  [skip] no active drug for '{seed['drug_name']}'")
            continue

        rec = classify(build_atc_candidate(seed["atc_l5"]), pack)
        review_status = _review_status_for(rec.action)
        backfill = _should_backfill_spine(rec)
        label = f"{seed['atc_l5']} ({seed.get('atc_l4_label')})"
        print(f"  {seed['drug_name']:<14} -> {drug['id']}  {seed['atc_l5']}  "
              f"relation={rec.relation} conf={rec.confidence} action={rec.action} "
              f"review={review_status} spine={'yes' if backfill else 'NO'}")
        if not apply:
            stats["would_write"] += 1
            stats["would_backfill"] += 1 if backfill else 0
            continue

        # crosswalk_records — record EVERY governed verdict (incl. rejected, so the
        # decision is auditable, never silently dropped). Idempotent on the natural
        # key, but a re-classified mapping UPDATES the governed fields (drift is
        # recorded, not masked by DO NOTHING).
        db.execute(
            """
            INSERT INTO crosswalk_records
                (internal_entity_id, internal_entity_type, external_system, external_id,
                 external_label, mapping_relation, mapping_scope, mapping_confidence,
                 mapping_method, ambiguity_flags, source_version, review_status, action)
            VALUES (%s, 'molecule', 'atc', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (internal_entity_id, external_system, external_id) DO UPDATE SET
                mapping_relation = EXCLUDED.mapping_relation,
                mapping_scope = EXCLUDED.mapping_scope,
                mapping_confidence = EXCLUDED.mapping_confidence,
                ambiguity_flags = EXCLUDED.ambiguity_flags,
                review_status = EXCLUDED.review_status,
                action = EXCLUDED.action,
                source_version = EXCLUDED.source_version,
                updated_at = NOW()
            """,
            [str(drug["id"]), seed["atc_l5"], label, rec.relation, rec.scope,
             rec.confidence, "external_source_crosswalk", rec.flags or [],
             SOURCE_VERSION, review_status, rec.action],
        )
        stats["records_written"] += 1
        stats[f"verdict_{rec.action}"] += 1

        # drugs.atc_codes — ONLY enrich the spine when the engine ACCEPTED the
        # mapping. A rejected/quarantined/pending mapping is recorded above but must
        # never touch the drug spine. Append-only, dup-guarded, never overwrites.
        if backfill:
            db.execute(
                """
                UPDATE drugs SET atc_codes = array_append(COALESCE(atc_codes, '{}'), %s),
                                 updated_at = NOW()
                WHERE id = %s AND NOT (%s = ANY(COALESCE(atc_codes, '{}')))
                """,
                [seed["atc_l5"], str(drug["id"]), seed["atc_l5"]],
            )
            stats["spine_backfilled"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("url", nargs="?", help="postgres url (else DATABASE_URL)")
    args = ap.parse_args()
    url = args.url or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Set DATABASE_URL or pass a postgres url.")

    db = Database(url)
    db.connect()
    pack = load_crosswalk_pack()
    print(f"=== ATC seed crosswalk load ({'APPLY' if args.apply else 'DRY RUN'}) ===")
    stats = load_atc_seeds(db, pack, apply=args.apply)
    print(f"\nTotals: {dict(stats)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
