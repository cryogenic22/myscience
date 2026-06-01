"""DBAdapter for the SEC 8-K pipeline (Epic 1 α3).

Implements the DBAdapter Protocol from services/sec_8k_pipeline.py
against the existing db.Database wrapper.

Persistence behavior:

  insert_event(row)
    INSERT INTO market_events ... ON CONFLICT (event_hash) DO NOTHING
    RETURNING id. The RETURNING clause yields a row on fresh insert
    and nothing on duplicate, which is how we tell the two cases apart.
    Returns True on insert, False on duplicate.

  insert_deal(row)
    INSERT INTO deals ... RETURNING id. Caller passes the resolved
    party ids; the adapter writes them straight through.

  append_roles_history(person_name, entry, *, company_id)
    Two-step: lookup investigators by canonical_name. If absent,
    INSERT a fresh row with [entry] as the initial roles_history. If
    present, UPDATE adding the entry via jsonb concatenation.

  resolve_drug_id(drug_name)
    Three-step lookup: drugs.generic_name → drugs.brand_name →
    entity_aliases. Case-insensitive exact match (ILIKE = via TRIM
    + LOWER). Returns the first hit's id or None.

The adapter never raises on duplicates / unknowns — it returns
False / None per the Protocol contract. SQL errors propagate; the
orchestrator catches them in its per-Item handlers.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from services.person_roles import normalise_name

logger = logging.getLogger(__name__)


class _PostgresDBAdapter:
    """Concrete adapter — wraps a db.Database instance.

    Constructed via the build_adapter() factory so callers can swap in
    decorators (cost meter, retry wrapper) without changing call sites.
    """

    def __init__(self, db: Any):
        self._db = db

    # ────────────────────────────────────────────────────────────────
    # insert_event
    # ────────────────────────────────────────────────────────────────

    # PB-H18: align to the live market_events schema. The legacy columns
    # disclosed_date / source_feed / payload / source_document_id were dropped
    # (real cols: source_api, no payload), so this INSERT used to throw on prod
    # — which is why there were ZERO 8-K events. NOT NULL source_url/retrieved_at
    # are now supplied. ON CONFLICT must name the partial unique index predicate
    # (idx_events_hash is WHERE event_hash IS NOT NULL).
    _EVENT_INSERT_SQL = """
        INSERT INTO market_events (
            event_type,
            description,
            primary_entity_type,
            primary_entity_id,
            primary_entity_name,
            drug_id,
            event_date,
            source_tier,
            trust_score,
            status,
            event_hash,
            source_api,
            source_url,
            retrieved_at,
            corroborating_sources
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, COALESCE(%s, ''), NOW(), %s::jsonb
        )
        ON CONFLICT (event_hash) WHERE event_hash IS NOT NULL DO NOTHING
        RETURNING id
    """

    def insert_event(self, row: dict[str, Any]) -> bool:
        """INSERT into market_events with idempotency on event_hash.

        Returns True if a row was inserted, False if event_hash matched
        an existing row (the row is unchanged in that case).
        """
        # drug_id mirrors the primary entity when it's a drug (lets the facts
        # ledger resolve the subject). impact_hint has no column on the live
        # schema and is dropped (it was only ever stashed in the now-absent
        # payload column).
        is_drug = row.get("primary_entity_type") == "drug"
        params = [
            row["event_type"],
            row["description"],
            row["primary_entity_type"],
            row["primary_entity_id"],
            row.get("primary_entity_name"),
            row["primary_entity_id"] if is_drug else None,   # drug_id
            row["event_date"],
            row.get("source_tier", "tier_1"),
            row.get("trust_score", 0.5),
            row.get("status", "new"),
            row["event_hash"],
            row.get("source_feed") or row.get("source_api"),  # → source_api
            row.get("source_url"),                            # COALESCE '' if None
            json.dumps(row.get("corroborating_sources", [])),
        ]

        result = self._db.fetch_one(self._EVENT_INSERT_SQL, params)
        return result is not None

    # ────────────────────────────────────────────────────────────────
    # insert_deal
    # ────────────────────────────────────────────────────────────────

    _DEAL_INSERT_SQL = """
        INSERT INTO deals (
            deal_types,
            acquirer_id,
            target_id,
            licensor_id,
            licensee_id,
            subject_drug_ids,
            subject_indications,
            geography,
            currency,
            upfront_value_usd,
            upfront_disclosed,
            milestones_total_usd,
            milestones_breakdown,
            royalty_terms,
            total_potential_usd,
            equity_component,
            announced_date,
            closing_date,
            status,
            source_document_id,
            press_release_url,
            filing_url,
            notes
        ) VALUES (
            %s,
            %s, %s, %s, %s,
            %s,
            %s::jsonb,
            %s, %s,
            %s, %s,
            %s,
            %s::jsonb,
            %s::jsonb,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s
        )
        RETURNING id
    """

    def insert_deal(self, row: dict[str, Any]) -> str:
        params = [
            list(row.get("deal_types") or []),
            row.get("acquirer_id"),
            row.get("target_id"),
            row.get("licensor_id"),
            row.get("licensee_id"),
            list(row.get("subject_drug_ids") or []),
            json.dumps(row.get("subject_indications") or []),
            row.get("geography"),
            row.get("currency", "USD"),
            row.get("upfront_value_usd"),
            row.get("upfront_disclosed", True),
            row.get("milestones_total_usd"),
            json.dumps(row.get("milestones_breakdown")) if row.get("milestones_breakdown") else None,
            json.dumps(row.get("royalty_terms")) if row.get("royalty_terms") else None,
            row.get("total_potential_usd"),
            row.get("equity_component", False),
            row.get("announced_date"),
            row.get("closing_date"),
            row.get("status", "announced"),
            row.get("source_document_id"),
            row.get("press_release_url"),
            row.get("filing_url"),
            row.get("notes"),
        ]
        result = self._db.fetch_one(self._DEAL_INSERT_SQL, params)
        if not result:
            return ""
        return str(result["id"])

    # ────────────────────────────────────────────────────────────────
    # append_roles_history
    # ────────────────────────────────────────────────────────────────

    _SELECT_INVESTIGATOR_SQL = """
        SELECT id FROM investigators
        WHERE canonical_name = %s
        LIMIT 1
    """

    _INSERT_INVESTIGATOR_SQL = """
        INSERT INTO investigators (
            name, canonical_name, roles_history,
            source_api, source_url, retrieved_at
        ) VALUES (
            %s, %s, %s::jsonb, 'sec_8k_item_5_02', '', NOW()
        )
    """

    _APPEND_ROLES_HISTORY_SQL = """
        UPDATE investigators
           SET roles_history = roles_history || %s::jsonb,
               updated_at = NOW()
         WHERE id = %s
    """

    def append_roles_history(
        self,
        person_name: str,
        entry: dict[str, Any],
        *,
        company_id: str,
    ) -> bool:
        """Append `entry` to investigators.roles_history. Creates the
        investigator row if no canonical-name match exists.
        """
        canonical = normalise_name(person_name)
        if not canonical:
            return False

        existing = self._db.fetch_one(
            self._SELECT_INVESTIGATOR_SQL, [canonical],
        )

        if existing is None:
            # Fresh investigator
            self._db.execute(
                self._INSERT_INVESTIGATOR_SQL,
                [person_name.strip(), canonical, json.dumps([entry])],
            )
            return True

        # Append to existing
        self._db.execute(
            self._APPEND_ROLES_HISTORY_SQL,
            [json.dumps([entry]), existing["id"]],
        )
        return True

    # ────────────────────────────────────────────────────────────────
    # resolve_drug_id
    # ────────────────────────────────────────────────────────────────

    _DRUG_BY_GENERIC_SQL = """
        SELECT id FROM drugs
        WHERE LOWER(TRIM(generic_name)) = LOWER(TRIM(%s))
        LIMIT 1
    """
    _DRUG_BY_BRAND_SQL = """
        SELECT id FROM drugs
        WHERE LOWER(TRIM(brand_name)) = LOWER(TRIM(%s))
        LIMIT 1
    """
    _DRUG_BY_ALIAS_SQL = """
        SELECT entity_id AS id FROM entity_aliases
        WHERE entity_type = 'drug'
          AND LOWER(TRIM(alias)) = LOWER(TRIM(%s))
        LIMIT 1
    """

    def resolve_drug_id(self, drug_name: Optional[str]) -> Optional[str]:
        if not drug_name or not drug_name.strip():
            return None

        for sql in (
            self._DRUG_BY_GENERIC_SQL,
            self._DRUG_BY_BRAND_SQL,
            self._DRUG_BY_ALIAS_SQL,
        ):
            row = self._db.fetch_one(sql, [drug_name])
            if row and row.get("id"):
                return str(row["id"])

        return None


def build_adapter(db: Any) -> _PostgresDBAdapter:
    """Construct a DBAdapter wrapping the given Database instance.

    The factory exists so callers can swap in decorators (cost meter,
    retry wrapper) without changing call sites.
    """
    return _PostgresDBAdapter(db)
