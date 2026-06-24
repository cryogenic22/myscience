"""One-shot recovery of the open_targets target-disease dead-letter backlog.

Replays failed_records (source_type='open_targets', the NOT NULL
therapeutic_areas.'name' error, status='pending') through the post-fix path:
each stored disease_association becomes one NAMED therapeutic-area ontology term
(name=disease_name, ontology_id=EFO/MONDO id), upserted via
KnowledgeStore._store_ontology_term (reused — not reimplemented). On success the
source failed_record is marked status='recovered' (reversible).

ONE-SHOT by design: the forward fix (OpenTargetsConnector._make_disease_records
+ the mesh_id→ontology_id→name three-tier dedup) prevents NEW such failures, so
there is no ongoing drift to schedule. Idempotent + reversible: re-running
dedupes on ontology_id and skips already-recovered rows; inserted
therapeutic_areas rows are deletable and the status flip is revertible.

Requires migration 097 (therapeutic_areas.ontology_id) applied first.

Usage:
    python scripts/recover_open_targets_dlq.py            # DRY RUN (read-only)
    python scripts/recover_open_targets_dlq.py --apply    # write + mark recovered
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from config import config
from connectors.base import Provenance, RawRecord, RecordType, SourceType
from connectors.open_targets import OT_API_URL
from db import Database
from integration.embedder import EmbeddedRecord
from integration.entity_resolver import ResolvedRecord
from integration.knowledge_store import KnowledgeStore
from integration.normalizer import NormalizedRecord

_PENDING_FILTER = """
    source_type = 'open_targets'
      AND error_message LIKE '%therapeutic_areas%'
      AND status = 'pending'
"""


def _disease_record(disease_id: str, disease_name: str) -> EmbeddedRecord:
    """Build the post-fix per-disease ontology-term record (no re-fetch)."""
    data = {"name": disease_name, "ontology_id": disease_id,
            "term_type": "therapeutic_area"}
    raw = RawRecord(
        record_type=RecordType.ONTOLOGY_TERM,
        external_id=f"ot_disease_{disease_id}",
        source_name="Open Targets Platform",
        provenance=Provenance(
            source_type=SourceType.OPEN_TARGETS,
            api_endpoint=OT_API_URL,
            query_params={},
            retrieved_at=datetime.now(timezone.utc),
            raw_response_hash="dlq-recovery",
        ),
        data=data,
        identifiers={"ontology_id": disease_id},
    )
    norm = NormalizedRecord(raw=raw, canonical_data=dict(data),
                            identifiers={"ontology_id": disease_id})
    return EmbeddedRecord(
        resolved=ResolvedRecord(normalized=norm, resolved_links={}),
        embedding=None,
    )


def _collect_distinct_diseases(rows: list[dict]) -> dict[str, str]:
    """{disease_id: disease_name} across every failed payload (id+name only)."""
    distinct: dict[str, str] = {}
    for r in rows:
        payload = r["raw_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        for a in (payload.get("disease_associations") or []):
            did = (a.get("disease_id") or "").strip()
            dn = (a.get("disease_name") or "").strip()
            if did and dn:
                distinct.setdefault(did, dn)
    return distinct


def main() -> None:
    apply = "--apply" in sys.argv
    db = Database(config.db.dsn)
    db.connect()
    store = KnowledgeStore(db)

    rows = db.fetch_all(
        f"SELECT id, raw_payload FROM failed_records WHERE {_PENDING_FILTER}"
    )
    distinct = _collect_distinct_diseases(rows)
    print(f"open_targets name-NULL pending failed_records: {len(rows)}")
    print(f"distinct recoverable diseases (id+name): {len(distinct)}")

    if not apply:
        print("\nDRY RUN — no writes. Diseases that would be upserted:")
        for did, dn in sorted(distinct.items()):
            print(f"  {did:18}  {dn}")
        print(f"\n{len(rows)} failed_records would be marked 'recovered'.")
        db.close()
        return

    inserted = updated = 0
    with db.transaction():
        for did, dn in distinct.items():
            _id, was_insert = store._store_ontology_term(
                _disease_record(did, dn), "dlq-recovery-open-targets")
            inserted += int(was_insert)
            updated += int(not was_insert)
        db.execute(
            f"""UPDATE failed_records
                SET status = 'recovered', resolved_at = NOW(),
                    resolution_notes =
                        'replayed as per-disease therapeutic_areas (migration 097)'
                WHERE {_PENDING_FILTER}"""
        )

    print(f"\nAPPLIED: therapeutic_areas inserted={inserted} updated={updated}; "
          f"failed_records marked recovered={len(rows)}")
    db.close()


if __name__ == "__main__":
    main()
