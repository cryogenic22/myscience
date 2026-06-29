"""One-shot recovery of the ChEMBL bioactivity dead-letter backlog.

Replays failed_records (source_type='chembl', record_type='bioactivity', the
``column "molecule_chembl_id" of relation "bioactivities" does not exist`` error,
status='pending') through the POST-#304 store path.

WHY THESE FAILED: migration 089 (bioactivities.molecule_chembl_id) was recorded
applied in prod but its file had gone missing from disk, and an INSERT that
referenced the column ran against a March schema where it did not yet exist — so
every one of the ~1,125 activities crashed at STORE and was dead-lettered with
the whole row lost. #304 restored migration 089 and re-added molecule_chembl_id
to the INSERT/UPDATE in ``KnowledgeStore._store_bioactivity``. The forward path no
longer drops it, so this recovery is ONE-SHOT.

HOW: each failed_record is reconstructed into the RawRecord the connector
originally emitted (its ``raw_payload`` is exactly ``RawRecord.data``; the
``identifiers`` dict, incl. generic_name, was not dead-lettered so we rebuild it
from the payload + the stored external_id), then STORED via the real #304
``_store_bioactivity`` (no re-fetch), which persists molecule_chembl_id — the
field whose absent column caused the crash — plus the molecular target. On
success the source failed_record is flipped to status='recovered' (reversible).

DRUG LINKING: the drug link is a function of generic_name only, so we resolve
each DISTINCT drug ONCE (the backlog spans ~10 molecules) and cache name->drug_id
— rather than calling the resolver per row (which is both slow and, by design,
WRITES: an alias-strategy match upserts an idempotent entity_aliases row, exactly
as the live pipeline does). auto_create is force-disabled, so the recovery never
mints a new drug/target entity; an unresolved name maps to drug_id NULL with
molecule_chembl_id as the molecule link — the exact case #304's column was added
for. The resolver is the authority over the duplicate generic_name rows.

IDEMPOTENT + REVERSIBLE: _store_bioactivity dedups on chembl_activity_id, so a
re-run UPDATEs (COALESCE-backfilling molecule_chembl_id) rather than duplicating;
already-recovered failed_records are filtered out; inserted rows are deletable and
the status flip is revertible.

BATCHED + ATOMIC PER BATCH: rows are replayed in batches, each its OWN
transaction (atomic in single-connection mode — Database.transaction yields self
and toggles autocommit when pool_size=0; a pooled DB would split the work, so we
fail closed). A long single transaction over all rows is fragile against the
managed DB dropping a long-lived connection, so on a connection drop we reconnect
and retry the batch — safe because the replay is idempotent.

Usage:
    python scripts/recover_bioactivity_dlq.py            # DRY RUN (read-only)
    python scripts/recover_bioactivity_dlq.py --apply    # write + mark recovered
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg2

from config import config
from connectors.base import Provenance, RawRecord, RecordType, SourceType
from connectors.chembl import CHEMBL_API_BASE
from db import Database
from domain.pharma.pack import get_pharma_pack
from integration.embedder import EmbeddedRecord
from integration.entity_resolver import EntityResolver, ResolvedRecord
from integration.knowledge_store import KnowledgeStore
from integration.normalizer import Normalizer

# Precise filter: the molecule_chembl_id schema-drift crash on bioactivities,
# still pending. (Other chembl DLQ causes — target_type NULL, target_name missing,
# the source_type '.value' bug — are distinct loops and must NOT be swept in here.)
_PENDING_FILTER = """
    source_type = 'chembl'
      AND error_message LIKE '%molecule_chembl_id%'
      AND error_message LIKE '%bioactivities%'
      AND status = 'pending'
"""

_ACTIVITY_PREFIX = "chembl_activity_"
_BATCH_SIZE = 200


@dataclass
class _DrugLink:
    """Minimal stand-in for a resolved entity link — _store_bioactivity reads only
    ``.entity_id`` off the generic_name link."""
    entity_id: str


def _as_dict(value) -> dict:
    if isinstance(value, str):
        return json.loads(value)
    return value or {}


def _parse_retrieved(prov: dict) -> datetime:
    raw = prov.get("retrieved_at")
    if raw:
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _reconstruct(fr: dict) -> RawRecord:
    """Rebuild the RawRecord the ChEMBL connector emitted for this activity.

    Mirrors connectors.chembl._fetch_activities: external_id 'chembl_activity_<id>',
    data=raw_payload, identifiers carrying chembl_id / activity_id / generic_name."""
    data = _as_dict(fr["raw_payload"])
    prov = _as_dict(fr["provenance"])
    external_id = fr["external_id"] or ""
    activity_id = external_id
    if external_id.startswith(_ACTIVITY_PREFIX):
        activity_id = external_id[len(_ACTIVITY_PREFIX):]

    return RawRecord(
        record_type=RecordType.BIOACTIVITY,
        external_id=external_id,
        source_name="ChEMBL",
        provenance=Provenance(
            source_type=SourceType.CHEMBL,
            api_endpoint=prov.get("api_endpoint") or f"{CHEMBL_API_BASE}/activity.json",
            query_params={"molecule_chembl_id": data.get("chembl_id")},
            retrieved_at=_parse_retrieved(prov),
            raw_response_hash="dlq-recovery",
        ),
        data=data,
        identifiers={
            "chembl_id": data.get("chembl_id"),
            "activity_id": activity_id,
            "generic_name": data.get("drug_name"),
        },
    )


def _resolve_drug_ids(normalizer, resolver, rows) -> dict:
    """Resolve each DISTINCT drug_name once -> canonical drug_id (the resolver is
    the authority over duplicate generic_name rows). Returns {drug_name: drug_id|None}.

    SIDE EFFECT (bounded to the ~10 distinct drugs, identical to the live pipeline):
    an alias-strategy match upserts an idempotent entity_aliases row (+ an audit
    row). auto_create is disabled upstream, so NO new drug/target entity is minted —
    an unresolved name simply maps to None."""
    cache: dict = {}
    for fr in rows:
        name = _as_dict(fr["raw_payload"]).get("drug_name")
        if name in cache:
            continue
        link = (resolver.resolve(normalizer.normalize(_reconstruct(fr))).resolved_links
                or {}).get("generic_name")
        cache[name] = getattr(link, "entity_id", None)
    return cache


def _replay_batch(db, normalizer, store, rows, drug_ids) -> tuple[int, int]:
    """Store one batch of activities + flip their failed_records to 'recovered', in
    a SINGLE transaction (atomic per batch). Uses the cached drug_id — no per-row
    resolver call. Returns (inserted, updated)."""
    inserted = updated = 0
    with db.transaction():
        for fr in rows:
            raw = _reconstruct(fr)
            normalized = normalizer.normalize(raw)
            drug_id = drug_ids.get(raw.data.get("drug_name"))
            links = {"generic_name": _DrugLink(drug_id)} if drug_id else {}
            _id, was_insert = store._store_bioactivity(
                EmbeddedRecord(
                    resolved=ResolvedRecord(normalized=normalized, resolved_links=links),
                    embedding=None,
                ),
                "dlq-recovery",
            )
            if was_insert:
                inserted += 1
            else:
                updated += 1
            db.execute(
                "UPDATE failed_records SET status = 'recovered' WHERE id = %s",
                [fr["id"]],
            )
    return inserted, updated


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _apply(db, normalizer, resolver, store, rows, batch_size=_BATCH_SIZE) -> tuple[int, int, int]:
    """Resolve drug ids once (cached), then replay rows in idempotent batches with a
    single reconnect-retry per batch (the managed DB drops long-lived connections)."""
    # Atomic-per-batch holds only in single-connection mode (see module docstring).
    assert db._pool is None, (
        "recover_bioactivity_dlq requires single-connection mode (pool_size=0) for "
        "an atomic per-batch replay; refusing to run against a pooled Database."
    )
    drug_ids = _resolve_drug_ids(normalizer, resolver, rows)
    resolved_n = sum(1 for v in drug_ids.values() if v)
    print(f"resolved {resolved_n}/{len(drug_ids)} distinct drugs to a canonical drug_id "
          f"(unresolved -> drug_id NULL, molecule_chembl_id still set)", flush=True)

    inserted = updated = recovered = 0
    for n, batch in enumerate(_chunks(rows, batch_size), 1):
        for attempt in (1, 2):
            try:
                i, u = _replay_batch(db, normalizer, store, batch, drug_ids)
                inserted += i
                updated += u
                recovered += len(batch)
                break
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                if attempt == 2:
                    raise
                print(f"  batch {n}: connection dropped ({type(e).__name__}); "
                      f"reconnecting + retrying (idempotent)", flush=True)
                db._conn = None        # force a fresh connection (connect() else no-ops)
                db.connect()
        print(f"  ... {recovered}/{len(rows)} replayed (batch {n})", flush=True)
    return inserted, updated, recovered


def _build_components(db: Database):
    """Normalizer + resolver + store wired for a deterministic, non-entity-creating
    replay. openai_client=None disables the embedding/LLM resolution strategies (no
    network); auto_create is force-disabled so the recovery never mints a new
    drug/target entity from an unresolved name."""
    pack = get_pharma_pack()
    normalizer = Normalizer(domain_pack=pack)
    resolver = EntityResolver(db, config, openai_client=None, domain_pack=pack)
    resolver.auto_create_enabled = False
    store = KnowledgeStore(db)
    return normalizer, resolver, store


def main() -> None:
    apply = "--apply" in sys.argv
    db = Database(config.db.dsn)
    db.connect()
    normalizer, resolver, store = _build_components(db)

    rows = db.fetch_all(
        f"SELECT id, external_id, raw_payload, provenance "
        f"FROM failed_records WHERE {_PENDING_FILTER}"
    )
    print(f"chembl bioactivity molecule_chembl_id pending failed_records: {len(rows)}")
    if not rows:
        print("nothing to recover.")
        db.close()
        return

    # READ-ONLY preview: distinct molecules + INSERT/UPDATE split (no resolver call,
    # so no writes — drug resolution + its bounded alias upserts happen at --apply).
    molecules: dict[str, str] = {}
    ext_ids: list[str] = []
    for fr in rows:
        data = _as_dict(fr["raw_payload"])
        molecules.setdefault(data.get("chembl_id"), data.get("drug_name"))
        ext_ids.append(fr["external_id"])
    existing = {
        r["chembl_activity_id"]
        for r in db.fetch_all(
            "SELECT chembl_activity_id FROM bioactivities WHERE chembl_activity_id = ANY(%s)",
            [ext_ids],
        )
    }
    would_update = sum(1 for e in ext_ids if e in existing)
    print(f"distinct molecules: {len(molecules)}  ->  "
          + ", ".join(f"{n}" for n in sorted(filter(None, molecules.values()))))
    print(f"store split: {len(ext_ids) - would_update} INSERT (new bioactivity rows), "
          f"{would_update} UPDATE (backfill molecule_chembl_id on existing)")

    if not apply:
        print(f"\nDRY RUN — no writes. {len(rows)} failed_records would be replayed + "
              f"marked 'recovered' (drugs resolved to canonical drug_id at --apply).")
        db.close()
        return

    inserted, updated, recovered = _apply(db, normalizer, resolver, store, rows)
    print(f"\nAPPLIED: {inserted} inserted, {updated} updated bioactivity rows; "
          f"{recovered} failed_records marked 'recovered'.")
    db.close()


if __name__ == "__main__":
    main()
