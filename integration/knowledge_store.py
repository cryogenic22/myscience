"""
Step 4: Store resolved, embedded records in the knowledge layer.

Routes each record to the correct table based on RecordType.
Handles upserts (insert or update) with full provenance preservation.
Includes content hashing for change detection and lifecycle tracking.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from connectors.base import RecordType
from integration.embedder import EmbeddedRecord

logger = logging.getLogger(__name__)


class RecordSkipped(Exception):
    """A record that cannot be stored but is NOT a failure — a deliberate,
    recorded skip (conservation: fail closed, count the drop, don't crash into
    the dead-letter queue). The pipeline catches this and increments
    ``records_skipped`` instead of routing to ``_dlq_insert``."""


# Precision-safe floor for grounding a news event by mining its headline (the
# same posture as the signal promoter): only full canonical names (0.9) and
# hand-vetted aliases (0.85) ground an entity; a weak word-like auto-alias (0.72)
# leaves the event honestly NULL-primary rather than mis-attributing at ingest.
_HEADLINE_LINK_MIN_CONFIDENCE = 0.85


class _NullLinker:
    """Sentinel used when the gazetteer can't be built — never links, so a
    failed build degrades to the prior NULL-primary behaviour without retrying
    on every record."""
    def link(self, text):  # noqa: D401 - tiny shim
        return None


_NULL_LINKER = _NullLinker()


class KnowledgeStore:
    """
    Writes records to the appropriate Postgres tables.
    Every write includes provenance columns. No row is stored without them.
    Computes content hashes for change detection and updates lifecycle timestamps.
    """

    def __init__(self, db):
        self.db = db
        # Lazily-built headline gazetteer (shared across one ETL run; the store
        # is instantiated once per pipeline run). Built on first news event.
        self._event_linker = None

    def _get_event_linker(self):
        """Lazy, cached full-universe entity gazetteer (built once per store).
        A build failure degrades to a never-linking sentinel — ingest must not
        break because the gazetteer is unavailable."""
        if self._event_linker is None:
            try:
                from services.entity_linker import EntityLinker
                self._event_linker = EntityLinker(self.db).load(with_priority_aliases=True)
            except Exception:
                logger.exception("event linker unavailable; news events stay primary-null")
                self._event_linker = _NULL_LINKER
        return self._event_linker

    def _link_headline(self, description: Optional[str]):
        """Return a high-confidence entity mentioned in a headline, or None.
        Used only for events the resolver could not structure-link."""
        text = (description or "").strip()
        if not text:
            return None
        hit = self._get_event_linker().link(text)
        if hit is not None and hit.confidence >= _HEADLINE_LINK_MIN_CONFIDENCE:
            return hit
        return None

    def relink_null_primary_events(
        self, *, limit: int = 5000, min_confidence: float = _HEADLINE_LINK_MIN_CONFIDENCE
    ) -> dict:
        """Backfill: ground existing NULL-primary events by mining their
        headline against the full gazetteer. Idempotent (only touches rows that
        newly resolve at/above the precision-safe floor); reversible (revert =
        set primary_* back to NULL). The forward `_store_event` path keeps new
        events grounded, so this is a one-shot recovery, not an ongoing need."""
        try:
            rows = self.db.fetch_all(
                """SELECT id, description FROM market_events
                    WHERE primary_entity_id IS NULL AND description IS NOT NULL
                    LIMIT %s""",
                [limit],
            )
        except Exception:
            logger.exception("event relink: null-primary query failed")
            rows = []

        # Link directly here (not via _link_headline, which is pinned to the
        # forward floor) so `min_confidence` is honoured in both directions.
        linker = self._get_event_linker()
        scanned = relinked = 0
        for r in rows:
            scanned += 1
            text = (r.get("description") or "").strip()
            hit = linker.link(text) if text else None
            if hit is None or hit.confidence < min_confidence:
                continue
            try:
                self.db.execute(
                    """UPDATE market_events
                          SET primary_entity_id   = %s,
                              primary_entity_type = %s,
                              primary_entity_name = %s
                        WHERE id = %s""",
                    [hit.entity_id, hit.entity_type, hit.canonical_name, r["id"]],
                )
                relinked += 1
            except Exception:
                logger.exception("event relink: update failed for %s", r.get("id"))

        logger.info("event relink: scanned=%d relinked=%d", scanned, relinked)
        return {"scanned": scanned, "relinked": relinked}

    @staticmethod
    def compute_content_hash(data: dict) -> str:
        """Deterministic SHA-256 of canonical payload (excludes embeddings/timestamps)."""
        skip_keys = {
            "molecule_embedding", "strategy_embedding", "abstract_embedding",
            "protocol_embedding", "scope_note_embedding", "embedding",
            "retrieved_at", "created_at", "updated_at", "last_verified_at",
            "content_hash", "quality_score", "record_status",
        }
        filtered = {k: v for k, v in data.items() if k not in skip_keys and v is not None}
        canonical = json.dumps(filtered, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def store(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """
        Route the record to the correct table and upsert.

        Returns:
            (stored_id, was_insert): The UUID of the stored row and whether
            it was a new insert (True) or an update (False).
            May return (stored_id, None) when content is unchanged (skip).
        """
        record_type = record.resolved.normalized.raw.record_type

        router = {
            RecordType.ONTOLOGY_TERM: self._store_ontology_term,
            RecordType.DRUG: self._store_drug,
            RecordType.COMPANY: self._store_company,
            RecordType.TRIAL: self._store_trial,
            RecordType.EVENT: self._store_event,
            RecordType.LITERATURE: self._store_literature,
            RecordType.ADVERSE_EVENT: self._store_adverse_event,
            RecordType.DRUG_LABEL: self._store_drug_label,
            RecordType.PMC_ARTICLE: self._store_pmc_article,
            RecordType.DOCUMENT_CHUNK: self._store_chunk,
            RecordType.PATENT: self._store_patent,
            RecordType.REGULATORY_MILESTONE: self._store_regulatory_milestone,
            RecordType.TRIAL_OUTCOME: self._store_trial_outcome,
            RecordType.TRIAL_LOCATION: self._store_trial_location,
            RecordType.INVESTIGATOR: self._store_investigator,
            RecordType.BIOMARKER: self._store_biomarker,
            RecordType.MOLECULAR_TARGET: self._store_molecular_target,
            RecordType.BIOACTIVITY: self._store_bioactivity,
        }

        handler = router.get(record_type)
        if handler is None:
            raise ValueError(f"No store handler for record type: {record_type}")

        return handler(record, etl_run_id)

    # ---- Handlers per record type ----

    def _store_ontology_term(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a MeSH therapeutic area or mechanism of action."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        term_type = data.get("term_type", "therapeutic_area")

        # Conservation: therapeutic_areas.name / mechanisms_of_action.name are
        # NOT NULL. A name-less ontology term must FAIL CLOSED as a recorded skip,
        # not crash into the dead-letter queue on a NOT NULL violation. This was
        # the #1 dead-letter-queue cause: the open_targets connector emits
        # target-disease association records that carry no single term name, so
        # every one of them silently crash-lost here. Modelling those associations
        # as named per-disease terms is a separate follow-up.
        name = (data.get("name") or "").strip()
        if not name:
            src = getattr(prov.source_type, "value", prov.source_type)
            raise RecordSkipped(
                f"ontology term has no name "
                f"(source={src}, external_id={record.resolved.normalized.raw.external_id})"
            )

        table = (
            "therapeutic_areas"
            if term_type == "therapeutic_area"
            else "mechanisms_of_action"
        )

        row = self.db.fetch_one(
            f"SELECT id FROM {table} WHERE mesh_id = %s",
            [data.get("mesh_id")],
        )

        if row:
            self.db.execute(
                f"""
                UPDATE {table}
                SET name = %s, tree_numbers = %s, parent_mesh_id = %s,
                    scope_note = %s, scope_note_embedding = %s,
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    name,
                    data.get("tree_numbers"),
                    data.get("parent_mesh_id"),
                    data.get("scope_note"),
                    record.embedding,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                f"""
                INSERT INTO {table}
                    (name, mesh_id, tree_numbers, parent_mesh_id, scope_note,
                     scope_note_embedding, source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                [
                    name,
                    data.get("mesh_id"),
                    data.get("tree_numbers"),
                    data.get("parent_mesh_id"),
                    data.get("scope_note"),
                    record.embedding,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_drug(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a drug from Orange Book."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        # Resolve FK references
        company_id = links.get("company_name", None)
        company_id = company_id.entity_id if company_id else None

        ta_id = links.get("therapeutic_area", None)
        ta_id = ta_id.entity_id if ta_id else None

        mech_id = links.get("mechanism", None)
        mech_id = mech_id.entity_id if mech_id else None

        # NDA-first lookup; fall back to case-insensitive generic_name
        # (auto-created drugs from ClinicalTrials.gov have no NDA).
        nda = data.get("nda_number")
        gname = data.get("generic_name")
        row = None
        if nda:
            row = self.db.fetch_one(
                "SELECT id FROM drugs WHERE nda_number = %s", [nda]
            )
        if not row and gname:
            row = self.db.fetch_one(
                """SELECT id FROM drugs
                   WHERE LOWER(generic_name) = LOWER(%s)
                     AND (record_status IS NULL OR record_status NOT IN ('excluded', 'merged'))
                   ORDER BY quality_score DESC NULLS LAST
                   LIMIT 1""",
                [gname],
            )

        content_hash = self.compute_content_hash(data)

        if row:
            self.db.execute(
                """
                UPDATE drugs
                SET brand_name = COALESCE(%s, brand_name),
                    generic_name = COALESCE(%s, generic_name),
                    company_id = COALESCE(%s, company_id),
                    therapeutic_area_id = COALESCE(%s, therapeutic_area_id),
                    mechanism_id = COALESCE(%s, mechanism_id),
                    approval_date = COALESCE(%s, approval_date),
                    patent_expiry_date = COALESCE(%s, patent_expiry_date),
                    patent_number = COALESCE(%s, patent_number),
                    dosage_form = COALESCE(%s, dosage_form),
                    route = COALESCE(%s, route),
                    marketing_status = COALESCE(%s, marketing_status),
                    rxcui = COALESCE(%s, rxcui),
                    pubchem_cid = COALESCE(%s, pubchem_cid),
                    canonical_smiles = COALESCE(%s, canonical_smiles),
                    inchi = COALESCE(%s, inchi),
                    inchi_key = COALESCE(%s, inchi_key),
                    molecular_formula = COALESCE(%s, molecular_formula),
                    molecular_weight = COALESCE(%s, molecular_weight),
                    xlogp = COALESCE(%s, xlogp),
                    tpsa = COALESCE(%s, tpsa),
                    hbd = COALESCE(%s, hbd),
                    hba = COALESCE(%s, hba),
                    molecule_embedding = CASE WHEN %s IS NOT NULL THEN %s::vector ELSE molecule_embedding END,
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    content_hash = %s, last_verified_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    data.get("brand_name"),
                    data.get("generic_name"),
                    company_id,
                    ta_id,
                    mech_id,
                    data.get("approval_date"),
                    data.get("patent_expiry_date"),
                    data.get("patent_number"),
                    data.get("dosage_form"),
                    data.get("route"),
                    data.get("marketing_status"),
                    data.get("rxcui"),
                    data.get("pubchem_cid"),
                    data.get("canonical_smiles"),
                    data.get("inchi"),
                    data.get("inchi_key"),
                    data.get("molecular_formula"),
                    data.get("molecular_weight"),
                    data.get("xlogp"),
                    data.get("tpsa"),
                    data.get("hbd"),
                    data.get("hba"),
                    record.embedding,
                    record.embedding,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    content_hash,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO drugs
                    (brand_name, generic_name, nda_number, company_id,
                     therapeutic_area_id, mechanism_id, approval_date,
                     patent_expiry_date, patent_number,
                     dosage_form, route, marketing_status, rxcui,
                     molecule_embedding, content_hash, last_verified_at,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                RETURNING id
                """,
                [
                    data.get("brand_name"),
                    data.get("generic_name"),
                    data.get("nda_number"),
                    company_id,
                    ta_id,
                    mech_id,
                    data.get("approval_date"),
                    data.get("patent_expiry_date"),
                    data.get("patent_number"),
                    data.get("dosage_form"),
                    data.get("route"),
                    data.get("marketing_status"),
                    data.get("rxcui"),
                    record.embedding,
                    content_hash,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_company(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a company (typically from EDGAR or entity resolution)."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance

        name = data.get("company_name", data.get("name"))
        cik = data.get("cik")

        # CIK-first lookup (authoritative); fall back to exact name match.
        # Never use OR — it caused Novo Nordisk to match NOVAVAX.
        row = None
        if cik:
            row = self.db.fetch_one(
                "SELECT id FROM companies WHERE cik = %s", [cik]
            )
        if not row and name:
            row = self.db.fetch_one(
                "SELECT id FROM companies WHERE name = %s", [name]
            )

        content_hash = self.compute_content_hash(data)

        if row:
            self.db.execute(
                """
                UPDATE companies
                SET name = CASE WHEN %s IS NOT NULL THEN COALESCE(%s, name) ELSE name END,
                    ticker = COALESCE(%s, ticker),
                    cik = COALESCE(%s, cik),
                    region = COALESCE(%s, region),
                    sic_code = COALESCE(%s, sic_code),
                    country = COALESCE(%s, country),
                    fiscal_year_end = COALESCE(%s, fiscal_year_end),
                    strategy_embedding = CASE WHEN %s IS NOT NULL THEN %s::vector ELSE strategy_embedding END,
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    content_hash = %s, last_verified_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    cik,    # if CIK provided, update name from authoritative source
                    name,
                    data.get("ticker"),
                    cik,
                    data.get("region"),
                    data.get("sic_code"),
                    data.get("country"),
                    data.get("fiscal_year_end"),
                    record.embedding,
                    record.embedding,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    content_hash,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO companies
                    (name, ticker, cik, region,
                     sic_code, country, fiscal_year_end,
                     strategy_embedding, content_hash, last_verified_at,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                RETURNING id
                """,
                [
                    name,
                    data.get("ticker"),
                    data.get("cik"),
                    data.get("region"),
                    data.get("sic_code"),
                    data.get("country"),
                    data.get("fiscal_year_end"),
                    record.embedding,
                    content_hash,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_trial(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a clinical trial from ClinicalTrials.gov."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_id = links.get("generic_name", None)
        drug_id = drug_id.entity_id if drug_id else None

        nct_id = data.get("nct_id", record.resolved.normalized.raw.external_id)

        # TEXT[] columns — ensure Python lists
        conditions = self._to_pg_array(data.get("conditions"))
        interventions = self._to_pg_array(data.get("interventions"))
        collaborators = self._to_pg_array(data.get("collaborator_names"))

        # Date columns — parse flexible date strings to DATE or None
        start_date = self._parse_date(data.get("start_date"))
        completion_date = self._parse_date(data.get("completion_date"))
        primary_comp_date = self._parse_date(data.get("primary_completion_date"))

        content_hash = self.compute_content_hash(data)

        row = self.db.fetch_one(
            "SELECT id FROM clinical_trials WHERE id = %s",
            [nct_id],
        )

        if row:
            self.db.execute(
                """
                UPDATE clinical_trials
                SET status = %s, phase = %s, sponsor_name = %s,
                    conditions = %s, interventions = %s,
                    start_date = %s, completion_date = %s,
                    enrollment_target = %s, actual_enrollment = %s,
                    failure_reason = %s, detailed_description = %s,
                    study_type = COALESCE(%s, study_type),
                    official_title = COALESCE(%s, official_title),
                    eligibility_criteria = COALESCE(%s, eligibility_criteria),
                    primary_completion_date = COALESCE(%s, primary_completion_date),
                    collaborator_names = COALESCE(%s, collaborator_names),
                    protocol_embedding = %s, drug_id = COALESCE(%s, drug_id),
                    content_hash = %s, last_verified_at = NOW(),
                    source_url = %s, retrieved_at = %s, updated_at = NOW()
                WHERE id = %s
                """,
                [
                    data.get("status") or data.get("overall_status"),
                    data.get("phase"),
                    data.get("sponsor_name") or data.get("lead_sponsor_name"),
                    conditions,
                    interventions,
                    start_date,
                    completion_date,
                    data.get("enrollment_target"),
                    data.get("actual_enrollment"),
                    data.get("failure_reason") or data.get("why_stopped"),
                    data.get("detailed_description"),
                    data.get("study_type"),
                    data.get("official_title"),
                    data.get("eligibility_criteria"),
                    primary_comp_date,
                    collaborators,
                    record.embedding,
                    drug_id,
                    content_hash,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    nct_id,
                ],
            )
            return nct_id, False
        else:
            self.db.execute(
                """
                INSERT INTO clinical_trials
                    (id, drug_id, sponsor_name, status, phase,
                     conditions, interventions, start_date, completion_date,
                     enrollment_target, actual_enrollment, failure_reason,
                     detailed_description,
                     study_type, official_title, eligibility_criteria,
                     primary_completion_date, collaborator_names,
                     protocol_embedding, content_hash, last_verified_at,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                """,
                [
                    nct_id,
                    drug_id,
                    data.get("sponsor_name") or data.get("lead_sponsor_name"),
                    data.get("status") or data.get("overall_status"),
                    data.get("phase"),
                    conditions,
                    interventions,
                    start_date,
                    completion_date,
                    data.get("enrollment_target"),
                    data.get("actual_enrollment"),
                    data.get("failure_reason") or data.get("why_stopped"),
                    data.get("detailed_description"),
                    data.get("study_type"),
                    data.get("official_title"),
                    data.get("eligibility_criteria"),
                    primary_comp_date,
                    collaborators,
                    record.embedding,
                    content_hash,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return nct_id, True

    @staticmethod
    def _event_hash(drug_id, event_type, description, event_date) -> str:
        """Stable dedup identity for a market event (PB-SL09). The same recall
        re-fetched on every connector run must hash identically so the
        idx_events_hash unique index collapses it instead of inserting a
        thousandth copy."""
        import hashlib
        key = "|".join([
            str(drug_id or ""),
            str(event_type or ""),
            (str(description or "")).strip().lower(),
            str(event_date or ""),
        ])
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _store_event(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a market event (shortage, guidance, etc.). Idempotent on
        event_hash — re-ingesting the same event is a no-op (PB-SL09)."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_link = links.get("generic_name", None)
        drug_id = drug_link.entity_id if drug_link else None

        # D2: stamp the spine entity at ingest. Established convention (verified
        # on prod: 26,442/26,442 grounded rows) is primary_entity_id ==
        # drug_id::text for drug-grounded events, with primary_entity_type/name
        # mirrored. A resolved drug wins; otherwise a resolved company grounds
        # the event (e.g. M&A/exec news with no drug subject). Previously this
        # writer set drug_id but never the primary_entity_* spine columns, so
        # ~29% of events landed NULL-primary and were uncited by the dossier.
        company_link = links.get("company_name") or links.get("sponsor_name")
        if drug_id:
            primary_entity_id = drug_id
            primary_entity_type = "drug"
            primary_entity_name = data.get("generic_name")
        elif company_link:
            primary_entity_id = company_link.entity_id
            primary_entity_type = "company"
            primary_entity_name = data.get("company_name")
        else:
            # No structured resolver link (the common case for free-text news
            # headlines): mine the headline for a known entity so the event is
            # fact-eligible instead of landing orphaned. Precision-safe floor.
            primary_entity_id = primary_entity_type = primary_entity_name = None
            hit = self._link_headline(data.get("description"))
            if hit is not None:
                primary_entity_id = hit.entity_id
                primary_entity_type = hit.entity_type
                primary_entity_name = hit.canonical_name

        # event_date is NOT NULL — use retrieved_at as fallback
        event_date = data.get("event_date") or prov.retrieved_at.strftime("%Y-%m-%d")
        content_hash = self.compute_content_hash(data)
        event_hash = self._event_hash(
            drug_id, data.get("event_type"), data.get("description"), event_date,
        )

        new_row = self.db.fetch_one(
            """
            INSERT INTO market_events
                (drug_id, event_type, event_date, description, impact_score,
                 content_hash, event_hash, last_verified_at,
                 source_api, source_url, etl_run_id, retrieved_at,
                 primary_entity_id, primary_entity_type, primary_entity_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s,
                    %s, %s, %s)
            ON CONFLICT (event_hash) WHERE event_hash IS NOT NULL
                DO NOTHING
            RETURNING id
            """,
            [
                drug_id,
                data.get("event_type"),
                event_date,
                data.get("description"),
                data.get("impact_score"),
                content_hash,
                event_hash,
                prov.source_type.value,
                prov.api_endpoint,
                etl_run_id,
                prov.retrieved_at,
                primary_entity_id,
                primary_entity_type,
                primary_entity_name,
            ],
        )
        if new_row:
            return str(new_row["id"]), True
        # Conflict → the event already exists; return its id, not newly inserted.
        existing = self.db.fetch_one(
            "SELECT id FROM market_events WHERE event_hash = %s LIMIT 1",
            [event_hash],
        )
        return (str(existing["id"]) if existing else ""), False

    @staticmethod
    def _to_pg_array(val):
        """Ensure a value is a list (for TEXT[] columns) or None."""
        if val is None:
            return None
        if isinstance(val, list):
            return val
        if isinstance(val, str) and val:
            # Split comma-separated string back into list
            return [v.strip() for v in val.split(", ") if v.strip()]
        return None

    @staticmethod
    def _parse_date(val):
        """Parse flexible date strings into YYYY-MM-DD or None."""
        if val is None:
            return None
        if isinstance(val, str):
            val = val.strip()
            if not val:
                return None
            # Already ISO format
            if len(val) == 10 and val[4] == "-":
                return val
            # YYYYMMDD
            if len(val) == 8 and val.isdigit():
                return f"{val[:4]}-{val[4:6]}-{val[6:8]}"
            # "YYYY-MM" partial date — set to first of month
            if len(val) == 7 and val[4] == "-":
                return f"{val}-01"
            # "Month YYYY" format from CT.gov
            from datetime import datetime as _dt
            for fmt in ("%B %Y", "%b %Y", "%B %d, %Y", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return _dt.strptime(val, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
        return None

    def _store_literature(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a PubMed article."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_link = links.get("generic_name", None)
        drug_id = drug_link.entity_id if drug_link else None

        pmid = data.get("pmid", record.resolved.normalized.raw.external_id)

        # Ensure array fields are actual lists for TEXT[] columns
        authors = self._to_pg_array(data.get("authors"))
        mesh_terms = self._to_pg_array(data.get("mesh_terms"))
        mesh_ids = self._to_pg_array(data.get("mesh_descriptor_ids"))
        grant_agencies = self._to_pg_array(data.get("grant_agencies"))
        keywords = self._to_pg_array(data.get("keywords"))

        content_hash = self.compute_content_hash(data)

        row = self.db.fetch_one(
            "SELECT id FROM pubmed_articles WHERE pmid = %s",
            [pmid],
        )

        if row:
            self.db.execute(
                """
                UPDATE pubmed_articles
                SET title = %s, abstract = %s, authors = %s,
                    journal = %s, publication_date = %s,
                    mesh_terms = %s, mesh_descriptor_ids = %s,
                    doi = COALESCE(%s, doi),
                    publication_type = COALESCE(%s, publication_type),
                    grant_agencies = COALESCE(%s, grant_agencies),
                    keywords = COALESCE(%s, keywords),
                    drug_id = COALESCE(%s, drug_id),
                    abstract_embedding = CASE WHEN %s IS NOT NULL THEN %s::vector ELSE abstract_embedding END,
                    content_hash = %s, last_verified_at = NOW(),
                    source_url = %s, retrieved_at = %s
                WHERE id = %s
                """,
                [
                    data.get("title"),
                    data.get("abstract"),
                    authors,
                    data.get("journal"),
                    data.get("publication_date"),
                    mesh_terms,
                    mesh_ids,
                    data.get("doi"),
                    data.get("publication_type"),
                    grant_agencies,
                    keywords,
                    drug_id,
                    record.embedding,
                    record.embedding,
                    content_hash,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO pubmed_articles
                    (pmid, title, abstract, authors, journal,
                     publication_date, mesh_terms, mesh_descriptor_ids,
                     doi, publication_type, grant_agencies, keywords,
                     drug_id, abstract_embedding, content_hash, last_verified_at,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                RETURNING id
                """,
                [
                    pmid,
                    data.get("title"),
                    data.get("abstract"),
                    authors,
                    data.get("journal"),
                    data.get("publication_date"),
                    mesh_terms,
                    mesh_ids,
                    data.get("doi"),
                    data.get("publication_type"),
                    grant_agencies,
                    keywords,
                    drug_id,
                    record.embedding,
                    content_hash,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_adverse_event(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store an FDA FAERS adverse event report."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_link = links.get("generic_name", None)
        drug_id = drug_link.entity_id if drug_link else None

        report_id = data.get("report_id", record.resolved.normalized.raw.external_id)
        content_hash = self.compute_content_hash(data)

        row = self.db.fetch_one(
            "SELECT id FROM adverse_events WHERE report_id = %s",
            [report_id],
        )

        if row:
            self.db.execute(
                """
                UPDATE adverse_events
                SET drug_id = COALESCE(%s, drug_id),
                    drug_name = COALESCE(%s, drug_name),
                    reaction = %s, reaction_meddra_pt = %s,
                    outcome = %s, severity = %s,
                    report_date = %s, patient_age = %s,
                    patient_sex = %s, reporter_type = %s,
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    content_hash = %s, last_verified_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    drug_id,
                    data.get("drug_name"),
                    data.get("reaction"),
                    data.get("reaction_meddra_pt"),
                    data.get("outcome"),
                    data.get("severity"),
                    data.get("report_date"),
                    data.get("patient_age"),
                    data.get("patient_sex"),
                    data.get("reporter_type"),
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    content_hash,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO adverse_events
                    (report_id, drug_id, drug_name, reaction,
                     reaction_meddra_pt, outcome, severity,
                     report_date, patient_age, patient_sex,
                     reporter_type, content_hash, last_verified_at,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                RETURNING id
                """,
                [
                    report_id,
                    drug_id,
                    data.get("drug_name"),
                    data.get("reaction"),
                    data.get("reaction_meddra_pt"),
                    data.get("outcome"),
                    data.get("severity"),
                    data.get("report_date"),
                    data.get("patient_age"),
                    data.get("patient_sex"),
                    data.get("reporter_type"),
                    content_hash,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_drug_label(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store an FDA drug label from openFDA."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_link = links.get("generic_name", None)
        drug_id = drug_link.entity_id if drug_link else None

        set_id = data.get("set_id", record.resolved.normalized.raw.external_id)
        content_hash = self.compute_content_hash(data)

        row = self.db.fetch_one(
            "SELECT id FROM drug_labels WHERE set_id = %s",
            [set_id],
        )

        if row:
            self.db.execute(
                """
                UPDATE drug_labels
                SET drug_id = COALESCE(%s, drug_id),
                    drug_name = COALESCE(%s, drug_name),
                    spl_version = COALESCE(%s, spl_version),
                    indications = %s, contraindications = %s,
                    warnings_and_precautions = %s, boxed_warning = %s,
                    dosage_and_administration = %s,
                    adverse_reactions_text = %s,
                    drug_interactions_text = %s,
                    clinical_pharmacology = %s,
                    effective_date = COALESCE(%s, effective_date),
                    manufacturer = COALESCE(%s, manufacturer),
                    label_embedding = CASE WHEN %s IS NOT NULL THEN %s::vector ELSE label_embedding END,
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    content_hash = %s, last_verified_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    drug_id,
                    data.get("drug_name"),
                    data.get("spl_version"),
                    data.get("indications"),
                    data.get("contraindications"),
                    data.get("warnings_and_precautions"),
                    data.get("boxed_warning"),
                    data.get("dosage_and_administration"),
                    data.get("adverse_reactions_text"),
                    data.get("drug_interactions_text"),
                    data.get("clinical_pharmacology"),
                    data.get("effective_date"),
                    data.get("manufacturer"),
                    record.embedding,
                    record.embedding,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    content_hash,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO drug_labels
                    (set_id, drug_id, drug_name, spl_version,
                     indications, contraindications,
                     warnings_and_precautions, boxed_warning,
                     dosage_and_administration,
                     adverse_reactions_text, drug_interactions_text,
                     clinical_pharmacology,
                     effective_date, manufacturer,
                     label_embedding, content_hash, last_verified_at,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                RETURNING id
                """,
                [
                    set_id,
                    drug_id,
                    data.get("drug_name"),
                    data.get("spl_version"),
                    data.get("indications"),
                    data.get("contraindications"),
                    data.get("warnings_and_precautions"),
                    data.get("boxed_warning"),
                    data.get("dosage_and_administration"),
                    data.get("adverse_reactions_text"),
                    data.get("drug_interactions_text"),
                    data.get("clinical_pharmacology"),
                    data.get("effective_date"),
                    data.get("manufacturer"),
                    record.embedding,
                    content_hash,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_pmc_article(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a PubMed Central full-text article."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_link = links.get("generic_name", None)
        drug_id = drug_link.entity_id if drug_link else None

        pmc_id = data.get("pmc_id", record.resolved.normalized.raw.external_id)
        pmid = data.get("pmid")

        # Try to resolve pubmed_article_id from linked PMID
        pubmed_article_id = None
        if pmid:
            pm_row = self.db.fetch_one(
                "SELECT id FROM pubmed_articles WHERE pmid = %s",
                [pmid],
            )
            if pm_row:
                pubmed_article_id = pm_row["id"]

        content_hash = self.compute_content_hash(data)

        row = self.db.fetch_one(
            "SELECT id FROM pmc_articles WHERE pmc_id = %s",
            [pmc_id],
        )

        if row:
            self.db.execute(
                """
                UPDATE pmc_articles
                SET pmid = COALESCE(%s, pmid),
                    pubmed_article_id = COALESCE(%s, pubmed_article_id),
                    drug_id = COALESCE(%s, drug_id),
                    title = COALESCE(%s, title),
                    full_text = %s,
                    article_type = COALESCE(%s, article_type),
                    is_protocol = %s, is_systematic_review = %s,
                    license = COALESCE(%s, license),
                    full_text_embedding = CASE WHEN %s IS NOT NULL THEN %s::vector ELSE full_text_embedding END,
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    content_hash = %s, last_verified_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    pmid,
                    pubmed_article_id,
                    drug_id,
                    data.get("title"),
                    data.get("full_text"),
                    data.get("article_type"),
                    data.get("is_protocol", False),
                    data.get("is_systematic_review", False),
                    data.get("license"),
                    record.embedding,
                    record.embedding,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    content_hash,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO pmc_articles
                    (pmc_id, pmid, pubmed_article_id, drug_id,
                     title, full_text, article_type,
                     is_protocol, is_systematic_review, license,
                     full_text_embedding, content_hash, last_verified_at,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                RETURNING id
                """,
                [
                    pmc_id,
                    pmid,
                    pubmed_article_id,
                    drug_id,
                    data.get("title"),
                    data.get("full_text"),
                    data.get("article_type"),
                    data.get("is_protocol", False),
                    data.get("is_systematic_review", False),
                    data.get("license"),
                    record.embedding,
                    content_hash,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_chunk(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a knowledge chunk (SEC filing section, user document, etc.)."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        # Determine entity link
        entity_type = "company"
        entity_id = None
        for link_key in ("company_name", "cik", "generic_name"):
            if link_key in links:
                entity_type = links[link_key].entity_type
                entity_id = links[link_key].entity_id
                break

        new_row = self.db.fetch_one(
            """
            INSERT INTO knowledge_chunks
                (entity_type, entity_id, source_type, source_reference,
                 source_url, chunk_text, embedding, etl_run_id, retrieved_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            [
                entity_type,
                entity_id,
                data.get("filing_type", data.get("source_type", prov.source_type.value)),
                data.get("section_name", data.get("source_reference", "")),
                prov.api_endpoint,
                data.get("chunk_text", record.resolved.normalized.text_content),
                record.embedding,
                etl_run_id,
                prov.retrieved_at,
            ],
        )
        return str(new_row["id"]), True

    def _store_patent(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a patent record from Orange Book."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_link = links.get("nda_number")
        drug_id = drug_link.entity_id if drug_link else None

        row = self.db.fetch_one(
            "SELECT id FROM patents WHERE drug_id = %s AND patent_number = %s",
            [drug_id, data.get("patent_number")],
        )

        if row:
            self.db.execute(
                """
                UPDATE patents
                SET patent_expiry_date = COALESCE(%s, patent_expiry_date),
                    patent_type = COALESCE(%s, patent_type),
                    applicant_holder = COALESCE(%s, applicant_holder),
                    source_api = %s, source_url = %s, retrieved_at = %s
                WHERE id = %s
                """,
                [
                    data.get("patent_expiry_date"),
                    data.get("patent_type"),
                    data.get("applicant_holder"),
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO patents
                    (drug_id, patent_number, patent_expiry_date, patent_type,
                     applicant_holder, source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                [
                    drug_id,
                    data.get("patent_number"),
                    data.get("patent_expiry_date"),
                    data.get("patent_type"),
                    data.get("applicant_holder"),
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_regulatory_milestone(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store an FDA regulatory milestone (submission/approval event)."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_link = links.get("nda_number")
        drug_id = drug_link.entity_id if drug_link else None

        row = self.db.fetch_one(
            """SELECT id FROM regulatory_milestones
               WHERE drug_id = %s AND submission_type = %s AND submission_number = %s""",
            [drug_id, data.get("submission_type"), data.get("submission_number")],
        )

        if row:
            self.db.execute(
                """
                UPDATE regulatory_milestones
                SET submission_status = COALESCE(%s, submission_status),
                    submission_status_date = COALESCE(%s, submission_status_date),
                    review_priority = COALESCE(%s, review_priority),
                    document_url = COALESCE(%s, document_url),
                    source_api = %s, source_url = %s, retrieved_at = %s
                WHERE id = %s
                """,
                [
                    data.get("submission_status"),
                    data.get("submission_status_date"),
                    data.get("review_priority"),
                    data.get("document_url"),
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO regulatory_milestones
                    (drug_id, submission_type, submission_number,
                     submission_status, submission_status_date,
                     review_priority, document_url,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                [
                    drug_id,
                    data.get("submission_type"),
                    data.get("submission_number"),
                    data.get("submission_status"),
                    data.get("submission_status_date"),
                    data.get("review_priority"),
                    data.get("document_url"),
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_trial_outcome(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a clinical trial outcome measure."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance

        trial_id = data.get("nct_id", record.resolved.normalized.raw.external_id)
        # Extract just the NCT ID if it contains extra info
        if "|" in trial_id:
            trial_id = trial_id.split("|")[0]

        new_row = self.db.fetch_one(
            """
            INSERT INTO trial_outcomes
                (trial_id, outcome_type, measure, time_frame, description,
                 source_api, source_url, retrieved_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            [
                trial_id,
                data.get("outcome_type"),
                data.get("measure"),
                data.get("time_frame"),
                data.get("description"),
                prov.source_type.value,
                prov.api_endpoint,
                prov.retrieved_at,
            ],
        )
        return str(new_row["id"]), True

    def _store_trial_location(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a clinical trial site location."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance

        trial_id = data.get("nct_id", record.resolved.normalized.raw.external_id)
        if "|" in trial_id:
            trial_id = trial_id.split("|")[0]

        new_row = self.db.fetch_one(
            """
            INSERT INTO trial_locations
                (trial_id, facility_name, city, state, country, status,
                 source_api, source_url, retrieved_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            [
                trial_id,
                data.get("facility_name"),
                data.get("city"),
                data.get("state"),
                data.get("country"),
                data.get("status"),
                prov.source_type.value,
                prov.api_endpoint,
                prov.retrieved_at,
            ],
        )
        return str(new_row["id"]), True

    def _store_investigator(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a key investigator (from trials or publications)."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance

        # Try to find existing investigator by ORCID or name+affiliation
        orcid = data.get("orcid")
        name = data.get("name")

        row = None
        if orcid:
            row = self.db.fetch_one(
                "SELECT id FROM investigators WHERE orcid = %s",
                [orcid],
            )
        if not row and name:
            row = self.db.fetch_one(
                "SELECT id FROM investigators WHERE name = %s AND affiliation = %s",
                [name, data.get("affiliation")],
            )

        if row:
            self.db.execute(
                """
                UPDATE investigators
                SET affiliation = COALESCE(%s, affiliation),
                    affiliation_country = COALESCE(%s, affiliation_country),
                    orcid = COALESCE(%s, orcid),
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    data.get("affiliation"),
                    data.get("affiliation_country"),
                    orcid,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO investigators
                    (name, affiliation, affiliation_country, orcid,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                [
                    name,
                    data.get("affiliation"),
                    data.get("affiliation_country"),
                    orcid,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_biomarker(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a biomarker entity."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance

        name = data.get("name")
        content_hash = self.compute_content_hash(data)

        row = None
        if name:
            row = self.db.fetch_one(
                "SELECT id FROM biomarkers WHERE LOWER(name) = LOWER(%s)",
                [name],
            )

        if row:
            self.db.execute(
                """
                UPDATE biomarkers
                SET category = COALESCE(%s, category),
                    abbreviation = COALESCE(%s, abbreviation),
                    unit = COALESCE(%s, unit),
                    clinical_significance = COALESCE(%s, clinical_significance),
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    content_hash = %s, last_verified_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    data.get("category"),
                    data.get("abbreviation"),
                    data.get("unit"),
                    data.get("clinical_significance"),
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    content_hash,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            import uuid

            new_id = str(uuid.uuid4())
            self.db.execute(
                """
                INSERT INTO biomarkers
                    (id, name, category, abbreviation, unit,
                     clinical_significance, content_hash, last_verified_at,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                """,
                [
                    new_id,
                    name,
                    data.get("category"),
                    data.get("abbreviation"),
                    data.get("unit"),
                    data.get("clinical_significance"),
                    content_hash,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return new_id, True

    def _store_molecular_target(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a molecular target (gene/protein) from ChEMBL or similar sources."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance

        chembl_id = data.get("chembl_id")
        ensembl_id = data.get("ensembl_id")
        gene_symbol = data.get("gene_symbol")

        row = None
        if chembl_id:
            row = self.db.fetch_one(
                "SELECT id FROM molecular_targets WHERE chembl_id = %s",
                [chembl_id],
            )
        if not row and ensembl_id:
            row = self.db.fetch_one(
                "SELECT id FROM molecular_targets WHERE ensembl_id = %s",
                [ensembl_id],
            )
        if not row and gene_symbol:
            row = self.db.fetch_one(
                "SELECT id FROM molecular_targets WHERE gene_symbol = %s",
                [gene_symbol],
            )

        content_hash = self.compute_content_hash(data)

        if row:
            self.db.execute(
                """
                UPDATE molecular_targets
                SET gene_symbol = COALESCE(%s, gene_symbol),
                    name = COALESCE(%s, name),
                    organism = COALESCE(%s, organism),
                    target_type = COALESCE(%s, target_type),
                    chembl_id = COALESCE(%s, chembl_id),
                    ensembl_id = COALESCE(%s, ensembl_id),
                    uniprot_id = COALESCE(%s, uniprot_id),
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    gene_symbol,
                    data.get("target_name") or data.get("name"),
                    data.get("organism"),
                    data.get("target_type"),
                    chembl_id,
                    ensembl_id,
                    data.get("uniprot_id"),
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            import uuid

            new_id = str(uuid.uuid4())
            self.db.execute(
                """
                INSERT INTO molecular_targets
                    (id, gene_symbol, name, organism, target_type,
                     chembl_id, ensembl_id, uniprot_id,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    new_id,
                    gene_symbol,
                    data.get("target_name") or data.get("name") or gene_symbol or "Unknown",
                    data.get("organism"),
                    # target_type is NOT NULL (default 'SINGLE PROTEIN').
                    data.get("target_type") or "SINGLE PROTEIN",
                    chembl_id,
                    ensembl_id,
                    data.get("uniprot_id"),
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return new_id, True

    def _upsert_target_by_chembl(self, data: dict, prov) -> Optional[str]:
        """Upsert a molecular_targets row keyed on the *target's* ChEMBL id.

        D3: a bioactivity/mechanism record carries the target via
        ``target_chembl_id`` / ``target_name`` (distinct from the molecule's
        ``chembl_id``). Resolving/creating the target here populates
        molecular_targets (was 0 rows) and yields the FK for bioactivities.
        Returns the target id, or None if no target info is present."""
        target_chembl = data.get("target_chembl_id")
        target_name = data.get("target_name")
        if not target_chembl and not target_name:
            return None
        row = None
        if target_chembl:
            row = self.db.fetch_one(
                "SELECT id FROM molecular_targets WHERE chembl_id = %s", [target_chembl]
            )
        if not row and target_name:
            row = self.db.fetch_one(
                "SELECT id FROM molecular_targets WHERE name = %s", [target_name]
            )
        if row:
            return str(row["id"])
        import uuid

        new_id = str(uuid.uuid4())
        self.db.execute(
            """
            INSERT INTO molecular_targets
                (id, name, chembl_id, organism, target_type,
                 source_api, source_url, retrieved_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                new_id,
                target_name or target_chembl or "Unknown target",
                target_chembl,
                data.get("target_organism") or data.get("organism"),
                # target_type is NOT NULL (default 'SINGLE PROTEIN'); the ChEMBL
                # activity endpoint omits it, so fall back rather than pass NULL.
                data.get("target_type") or "SINGLE PROTEIN",
                prov.source_type.value,
                prov.api_endpoint,
                prov.retrieved_at,
            ],
        )
        return new_id

    def _store_bioactivity(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a bioactivity measurement from ChEMBL or similar sources."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance

        chembl_activity_id = data.get(
            "chembl_activity_id", record.resolved.normalized.raw.external_id
        )

        # D3: link drug + target so bioactivities joins the spine (was 100% NULL
        # drug_id, 0 molecular_targets). drug_id from the resolved generic_name
        # link (added to the connector's identifiers); target_id upserted from
        # the activity's own target fields.
        links = record.resolved.resolved_links or {}
        drug_link = links.get("generic_name")
        drug_id = drug_link.entity_id if drug_link else None
        target_id = self._upsert_target_by_chembl(data, prov)

        row = self.db.fetch_one(
            "SELECT id FROM bioactivities WHERE chembl_activity_id = %s",
            [chembl_activity_id],
        )

        if row:
            self.db.execute(
                """
                UPDATE bioactivities
                -- Overwrite drug_id/target_id when a fresh resolution exists
                -- (not COALESCE): the resolver is the authority and now excludes
                -- merged dup rows, so a re-run must re-point a stale merged
                -- drug_id to the canonical one. Falls back to the existing value
                -- only when this run produced no link.
                SET drug_id = COALESCE(%s, drug_id),
                    target_id = COALESCE(%s, target_id),
                    molecule_chembl_id = COALESCE(%s, molecule_chembl_id),
                    activity_type = COALESCE(%s, activity_type),
                    activity_value = COALESCE(%s, activity_value),
                    activity_units = COALESCE(%s, activity_units),
                    assay_type = COALESCE(%s, assay_type),
                    pchembl_value = COALESCE(%s, pchembl_value),
                    assay_description = COALESCE(%s, assay_description),
                    source_api = %s, retrieved_at = %s
                WHERE id = %s
                """,
                [
                    drug_id,
                    target_id,
                    data.get("chembl_id"),
                    data.get("activity_type") or data.get("standard_type"),
                    data.get("activity_value") or data.get("standard_value"),
                    data.get("activity_units") or data.get("standard_units"),
                    data.get("assay_type"),
                    data.get("pchembl_value"),
                    data.get("assay_description"),
                    prov.source_type.value,
                    prov.retrieved_at,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            import uuid

            new_id = str(uuid.uuid4())
            self.db.execute(
                """
                INSERT INTO bioactivities
                    (id, drug_id, target_id, molecule_chembl_id, chembl_activity_id,
                     activity_type, activity_value, activity_units, assay_type,
                     pchembl_value, assay_description, source_api, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    new_id,
                    drug_id,
                    target_id,
                    data.get("chembl_id"),
                    chembl_activity_id,
                    data.get("activity_type") or data.get("standard_type"),
                    data.get("activity_value") or data.get("standard_value"),
                    data.get("activity_units") or data.get("standard_units"),
                    data.get("assay_type"),
                    data.get("pchembl_value"),
                    data.get("assay_description"),
                    prov.source_type.value,
                    prov.retrieved_at,
                ],
            )
            return new_id, True
