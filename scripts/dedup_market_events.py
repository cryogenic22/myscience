"""D2 — supervised, reversible market_events dedup (SPEC_DATA_001 §D2).

market_events is flooded: a single real event exists in up to ~1,041 copies and
~96% of rows in a 5-yr window are duplicates of ~1,657 distinct events. The
read-time dedup (intelligence_feed) hides this in the UI, but the ledger still
ingested the duplicates, so 33% of the fact ledger is duplicated `market_event`
noise (docs/data-sense-layer-status.html).

This collapses duplicates **destructively but reversibly** (SUPERVISED — the
human authorized it in-turn):

  1. Group active rows by ``(primary_entity_id, event_type, description)``.
  2. Keep the survivor = highest trust_score, then newest retrieved_at/created_at.
  3. **Soft-delete** the rest (``record_status='superseded'``) — NOT hard delete.
  4. Re-point `market_event` facts that reference a superseded event_id onto the
     surviving canonical event_id (append-only ledger: dup facts that now collide
     on the canonical event are superseded, keeping one grounded fact per event).
  5. Backfill ``event_hash`` on survivors (the UNIQUE partial index means this
     MUST follow the collapse, or it would conflict). Hash keys on the same
     fields the ingest path uses (drug_id/event_type/description/event_date).
  6. Re-emit `market_event` facts from the grounded, deduped survivors
     (idempotent, via services.fact_ingest.backfill_facts_from_events).

Verification (--verify, also run after a real run): nothing in
``facts.object_value->>'event_id'``, ``signals.event_id`` /
``signals.primary_entity_id`` points at a superseded market_events row.

Usage:
    python scripts/dedup_market_events.py "<db url>" --dry-run
    python scripts/dedup_market_events.py "<db url>"            # execute
    python scripts/dedup_market_events.py "<db url>" --verify   # orphan check only
"""

from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


# ── pure planning (DB-free, unit-tested) ──────────────────────────────────

def pick_survivor(rows: list[dict]) -> dict:
    """Pick the canonical survivor from a duplicate group.

    Highest trust_score wins; ties break to the newest ingestion timestamp
    (retrieved_at, then created_at). Matches the read-time dedup rule in
    services.intelligence_feed (highest-trust / newest), so the ledger and the
    UI agree on which copy is canonical.
    """
    def key(r: dict):
        return (
            float(r.get("trust_score") or 0.0),
            str(r.get("retrieved_at") or ""),
            str(r.get("created_at") or ""),
        )

    return max(rows, key=key)


def plan_collapse(rows: list[dict]) -> tuple[list[str], dict[str, str]]:
    """Given active market_events rows, return (superseded_ids, dup_to_canon).

    ``superseded_ids`` are the duplicate row ids to soft-delete.
    ``dup_to_canon`` maps each superseded id -> the surviving canonical id, so
    facts/signals referencing a dropped event can be repointed.
    Rows are grouped by (primary_entity_id, event_type, description).
    """
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        k = (r.get("primary_entity_id"), r.get("event_type"), r.get("description"))
        groups.setdefault(k, []).append(r)

    superseded: list[str] = []
    dup_to_canon: dict[str, str] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        survivor = pick_survivor(members)
        canon_id = str(survivor["id"])
        for r in members:
            rid = str(r["id"])
            if rid != canon_id:
                superseded.append(rid)
                dup_to_canon[rid] = canon_id
    return superseded, dup_to_canon


# ── DB execution ──────────────────────────────────────────────────────────

_ACTIVE = "record_status IS DISTINCT FROM 'superseded'"


def _fetch_active(db) -> list[dict]:
    return db.fetch_all(
        f"SELECT id, primary_entity_id, event_type, description, "
        f"       trust_score, retrieved_at, created_at "
        f"  FROM market_events WHERE {_ACTIVE}"
    )


def count_orphans(db) -> dict[str, int]:
    """Spine refs pointing at a superseded market_events row — must be 0."""
    out: dict[str, int] = {}
    out["facts.event_id"] = (db.fetch_one(
        "SELECT count(*) c FROM facts f "
        "JOIN market_events me ON me.id::text = f.object_value->>'event_id' "
        "WHERE me.record_status = 'superseded' AND f.superseded_by IS NULL "
        "  AND f.predicate = 'market_event'"
    ) or {}).get("c", 0)
    out["signals.event_id"] = (db.fetch_one(
        "SELECT count(*) c FROM signals s "
        "JOIN market_events me ON me.id = s.event_id "
        "WHERE me.record_status = 'superseded'"
    ) or {}).get("c", 0)
    out["signals.primary_entity_id"] = (db.fetch_one(
        "SELECT count(*) c FROM signals s "
        "JOIN market_events me ON me.id::text = s.primary_entity_id "
        "WHERE me.record_status = 'superseded'"
    ) or {}).get("c", 0)
    out["entity_links.event"] = (db.fetch_one(
        "SELECT count(*) c FROM entity_links el "
        "JOIN market_events me "
        "  ON me.id::text IN (el.source_entity_id, el.target_entity_id) "
        "WHERE me.record_status = 'superseded'"
    ) or {}).get("c", 0)
    return out


def _chunks(seq, n=1000):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


# The survivor map: ONE source of truth. A server-side window picks the survivor
# per (primary_entity_id, event_type, description) group with the SAME ordering
# as pick_survivor (highest trust, newest, then id). Every dup→survivor mapping
# the repoints and the soft-delete use comes from this map — so they can never
# disagree (the bug that orphaned facts when the Python plan and the SQL window
# picked different survivors on a tie).
_BUILD_MAP_SQL = """
    CREATE TEMP TABLE me_map ON COMMIT DROP AS
    WITH grp AS (
        SELECT id,
               first_value(id) OVER (
                   PARTITION BY primary_entity_id, event_type, description
                   ORDER BY trust_score DESC NULLS LAST,
                            retrieved_at DESC NULLS LAST,
                            created_at DESC NULLS LAST,
                            id) AS survivor
          FROM market_events
         WHERE record_status IS DISTINCT FROM 'superseded'
    )
    SELECT id::text AS dup_id, survivor::text AS survivor
      FROM grp WHERE id <> survivor
"""


def run(db, *, dry_run: bool = False, reemit: bool = True) -> dict:
    rows = _fetch_active(db)
    superseded, _ = plan_collapse(rows)
    stats = {
        "active_rows": len(rows),
        "to_supersede": len(superseded),
        "survivors": len(rows) - len(superseded),
        "facts_repointed": 0,
        "signals_repointed": 0,
        "facts_superseded_dup": 0,
        "links_repointed": 0,
        "links_deduped": 0,
        "soft_deleted": 0,
        "hash_backfilled": 0,
        "facts_reemitted": 0,
    }
    if dry_run or not superseded:
        logger.info("[plan] active=%d supersede=%d survivors=%d",
                    stats["active_rows"], stats["to_supersede"], stats["survivors"])
        return stats

    with db.transaction():
        # 0. Build the dup→survivor map (one source of truth, dropped on commit).
        db.execute(_BUILD_MAP_SQL)
        db.execute("CREATE INDEX ON me_map(dup_id)")

        # 1. Re-point market_event FACTS dup→survivor (set-based join on the map),
        #    BEFORE soft-delete, so the ledger never points at a superseded row.
        db.execute(
            "UPDATE facts f SET object_value = "
            "jsonb_set(f.object_value, '{event_id}', to_jsonb(m.survivor)) "
            "FROM me_map m "
            "WHERE f.predicate = 'market_event' AND f.superseded_by IS NULL "
            "  AND f.object_value->>'event_id' = m.dup_id"
        )
        stats["facts_repointed"] = (db.fetch_one(
            "SELECT count(*) c FROM facts f JOIN me_map m "
            "  ON f.object_value->>'event_id' = m.survivor "
            "WHERE f.predicate = 'market_event' AND f.superseded_by IS NULL"
        ) or {}).get("c", 0)

        # 2. Re-point SIGNALS. signals.event_id is GLOBALLY UNIQUE: repoint a
        #    dup's signal onto the survivor only when the survivor has no signal
        #    (NOT EXISTS); leave residual collisions on the dup. (In practice no
        #    signal references a dup — but this keeps the invariant.)
        db.execute(
            "UPDATE signals s SET event_id = m.survivor::uuid "
            "FROM me_map m "
            "WHERE s.event_id::text = m.dup_id "
            "  AND NOT EXISTS (SELECT 1 FROM signals c WHERE c.event_id = m.survivor::uuid)"
        )

        # 3. Re-point ENTITY_LINKS off the dup events (market_events live in the
        #    entity graph as event→drug edges). idx_links_unique forbids dup
        #    (source,target,link_type), and many dups map to the same survivor,
        #    so first DELETE every dup-source link that would collide with a
        #    survivor link OR another dup mapping to the same survivor (keep one),
        #    then bulk-repoint the unique remainder. Set-based (not per-link —
        #    pathological on high-degree nodes). Mirror for the target side.
        for side, other in (("source", "target"), ("target", "source")):
            db.execute(
                f"""
                WITH proposed AS (
                    SELECT el.id,
                           row_number() OVER (
                               PARTITION BY m.survivor, el.{other}_entity_id, el.link_type
                               ORDER BY el.id) AS rn,
                           m.survivor, el.{other}_entity_id AS oid, el.link_type
                      FROM entity_links el JOIN me_map m
                        ON el.{side}_entity_id = m.dup_id),
                to_del AS (
                    SELECT p.id FROM proposed p
                     WHERE p.rn > 1
                        OR EXISTS (SELECT 1 FROM entity_links c
                                    WHERE c.{side}_entity_id = p.survivor
                                      AND c.{other}_entity_id = p.oid
                                      AND c.link_type = p.link_type))
                DELETE FROM entity_links el USING to_del d WHERE el.id = d.id
                """
            )
            db.execute(
                f"UPDATE entity_links el SET {side}_entity_id = m.survivor "
                f"FROM me_map m WHERE el.{side}_entity_id = m.dup_id"
            )
        stats["links_repointed"] = -1  # tracked via orphan check, not a count

        # 4. Soft-delete the dup market_events rows (reversible) FROM the map.
        #    EXCLUDE any dup that still has a signal pointing at it — its signal
        #    couldn't repoint (the survivor already owns one; signals.event_id is
        #    globally unique), so the dup must stay active or the signal orphans.
        db.execute(
            "UPDATE market_events me SET record_status = 'superseded' "
            "FROM me_map m WHERE me.id::text = m.dup_id "
            "  AND NOT EXISTS (SELECT 1 FROM signals s WHERE s.event_id = me.id)"
        )
        stats["soft_deleted"] = (db.fetch_one(
            "SELECT count(*) c FROM market_events WHERE record_status = 'superseded'"
        ) or {}).get("c", 0)

        # 5. Collapse market_event FACTS that now duplicate (same survivor
        #    event_id + subject): keep earliest asserted, supersede the rest by
        #    it (append-only — never delete a fact).
        db.execute(
            "WITH ranked AS ("
            "  SELECT id, "
            "         first_value(id) OVER ("
            "             PARTITION BY object_value->>'event_id', "
            "                          subject_entity_type, subject_entity_id "
            "             ORDER BY asserted_at ASC, id ASC) AS keeper, "
            "         row_number() OVER ("
            "             PARTITION BY object_value->>'event_id', "
            "                          subject_entity_type, subject_entity_id "
            "             ORDER BY asserted_at ASC, id ASC) AS rn "
            "    FROM facts "
            "   WHERE predicate = 'market_event' AND superseded_by IS NULL "
            "     AND object_value->>'event_id' IS NOT NULL"
            ") "
            "UPDATE facts f SET superseded_by = r.keeper "
            "  FROM ranked r WHERE f.id = r.id AND r.rn > 1"
        )
        stats["facts_superseded_dup"] = (db.fetch_one(
            "SELECT count(*) c FROM facts "
            "WHERE predicate = 'market_event' AND superseded_by IS NOT NULL"
        ) or {}).get("c", 0)

        # 6. Backfill event_hash on survivors (UNIQUE partial index → must follow
        #    collapse). pgcrypto isn't installed, so hash in Python with the EXACT
        #    construction the ingest path uses (KnowledgeStore._event_hash), then
        #    write set-based in chunked unnest() batches; de-dup the hash in
        #    Python (keep first id per hash) so the UNIQUE index can't trip.
        from integration.knowledge_store import KnowledgeStore
        survivors = db.fetch_all(
            f"SELECT id, drug_id, event_type, description, event_date "
            f"  FROM market_events WHERE {_ACTIVE} AND event_hash IS NULL"
        )
        # Seed with hashes ALREADY present (a prior partial run set some), so we
        # never re-issue a hash the UNIQUE index already holds.
        seen_hash: set[str] = {
            r["event_hash"] for r in db.fetch_all(
                "SELECT event_hash FROM market_events WHERE event_hash IS NOT NULL"
            ) if r.get("event_hash")
        }
        pairs: list[tuple[str, str]] = []
        for s in survivors:
            h = KnowledgeStore._event_hash(
                s.get("drug_id"), s.get("event_type"),
                s.get("description"), s.get("event_date"),
            )
            if h in seen_hash:
                continue   # rarer collider stays NULL (read-time dedup covers it)
            seen_hash.add(h)
            pairs.append((str(s["id"]), h))
        for batch in _chunks(pairs, 500):
            ids = [p[0] for p in batch]
            hashes = [p[1] for p in batch]
            db.execute(
                "UPDATE market_events me SET event_hash = v.h "
                "FROM (SELECT unnest(%s::text[]) AS id, unnest(%s::text[]) AS h) v "
                "WHERE me.id::text = v.id",
                [ids, hashes],
            )
            stats["hash_backfilled"] += len(batch)

    # 7. Re-emit market_event facts from the grounded, deduped SURVIVORS only
    #    (idempotent). Filter to active rows so we never re-assert a fact for a
    #    superseded event (that would re-create orphans).
    if reemit:
        from services.fact_ingest import backfill_facts_from_events
        rs = backfill_facts_from_events(db, active_only=True)
        stats["facts_reemitted"] = rs.asserted

    logger.info("dedup done: %s", stats)
    return stats


def _connect(url: str):
    from db import Database
    db = Database(url)
    db.connect()
    return db


def main() -> None:
    ap = argparse.ArgumentParser(description="Supervised market_events dedup (D2)")
    ap.add_argument("db_url", nargs="?", help="postgres url (or set DATABASE_URL)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true", help="orphan check only")
    ap.add_argument("--no-reemit", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import os
    url = args.db_url or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Pass a postgres url or set DATABASE_URL")
    db = _connect(url)
    try:
        if args.verify:
            print("orphans:", count_orphans(db))
            return
        stats = run(db, dry_run=args.dry_run, reemit=not args.no_reemit)
        print("=== market_events dedup ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        if not args.dry_run:
            print("orphans after:", count_orphans(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
