"""
Step 5: Cross-Link Detection.

After a record is stored, detect new relationships it creates with
existing entities. Writes to the entity_links table -- the flat graph
that replaces Neo4j for MVP.

Each record type has its own linking rules:
- Drug → company (OWNS), therapeutic_area (IN_THERAPEUTIC_AREA), mechanism (TARGETS_MECHANISM)
- Trial → drug (INVESTIGATES), company (SPONSORS)
- Literature → drug (EVIDENCE_FOR) via MeSH terms
- Event → drug (SHORTAGE_AFFECTS)
- Chunk → company/drug (MENTIONED_IN)
"""

from __future__ import annotations

import logging
from typing import Optional

from connectors.base import LinkType, RecordType
from integration.embedder import EmbeddedRecord

logger = logging.getLogger(__name__)


class CrossLinker:
    """
    Detects and records cross-source relationships after a record is stored.

    Links are idempotent: re-running the pipeline for the same record will
    not create duplicate links (enforced by the unique index on entity_links).

    When a domain_pack is provided, link rules are read from the pack's
    declarative config. Custom per-type methods are still used as fallbacks
    for complex linking logic (e.g., ontology-mediated literature links).
    """

    def __init__(self, db, domain_pack=None):
        self.db = db
        self.domain_pack = domain_pack

    def cross_link(self, record: EmbeddedRecord, stored_id: str) -> list[dict]:
        """
        Detect relationships created by a newly stored record.

        Args:
            record: The embedded record (with resolved links from Step 2).
            stored_id: The UUID of the row just written by KnowledgeStore.

        Returns:
            List of dicts describing the links created.
        """
        record_type = record.resolved.normalized.raw.record_type
        source_type = record.resolved.normalized.raw.provenance.source_type

        # Try domain pack link rules first
        if self.domain_pack:
            links = self._apply_link_rules(record, stored_id, record_type, source_type.value)
            # Still call custom handlers for complex logic (ontology-mediated, etc.)
            custom = self._custom_link(record, stored_id, record_type, source_type.value)
            links.extend(custom)
            return links

        # Fallback: original per-type router
        router = {
            RecordType.DRUG: self._link_drug,
            RecordType.COMPANY: self._link_company,
            RecordType.TRIAL: self._link_trial,
            RecordType.EVENT: self._link_event,
            RecordType.LITERATURE: self._link_literature,
            RecordType.DOCUMENT_CHUNK: self._link_chunk,
            RecordType.ONTOLOGY_TERM: self._link_ontology_term,
            RecordType.PATENT: self._link_patent,
            RecordType.REGULATORY_MILESTONE: self._link_regulatory_milestone,
            RecordType.TRIAL_OUTCOME: self._link_trial_outcome,
            RecordType.TRIAL_LOCATION: self._link_trial_location,
            RecordType.INVESTIGATOR: self._link_investigator,
        }

        handler = router.get(record_type)
        if handler is None:
            return []

        return handler(record, stored_id, source_type.value)

    def _apply_link_rules(self, record: EmbeddedRecord, stored_id: str,
                          record_type: RecordType, source: str) -> list[dict]:
        """Apply declarative link rules from the domain pack."""
        links = []
        resolved = record.resolved.resolved_links
        rules = self.domain_pack.get_link_rules_for_record_type(record_type.value)

        for rule in rules:
            entity_link = resolved.get(rule.identifier_key)
            if not entity_link:
                continue

            if rule.stored_id_is == "source":
                source_id = stored_id
                source_entity = rule.source_entity
                target_id = entity_link.entity_id
                target_entity = rule.target_entity
            else:
                source_id = entity_link.entity_id
                source_entity = rule.source_entity
                target_id = stored_id
                target_entity = rule.target_entity

            created = self._upsert_link(
                source_id=source_id,
                source_type=source_entity,
                target_id=target_id,
                target_type=target_entity,
                link_type=LinkType(rule.link_type),
                via=entity_link.matched_via,
                confidence=entity_link.confidence,
                source=source,
            )
            if created:
                links.append(created)

        return links

    def _custom_link(self, record: EmbeddedRecord, stored_id: str,
                     record_type: RecordType, source: str) -> list[dict]:
        """Handle complex linking logic not expressible as simple rules."""
        # Ontology-mediated literature links
        if record_type == RecordType.LITERATURE:
            return self._link_literature_ontology(record, stored_id, source)
        # Trial outcome/location FK links
        if record_type == RecordType.TRIAL_OUTCOME:
            return self._link_trial_outcome(record, stored_id, source)
        if record_type == RecordType.TRIAL_LOCATION:
            return self._link_trial_location(record, stored_id, source)
        # Investigator links (trial + article)
        if record_type == RecordType.INVESTIGATOR:
            return self._link_investigator(record, stored_id, source)
        return []

    def _link_literature_ontology(self, record: EmbeddedRecord, stored_id: str, source: str) -> list[dict]:
        """Ontology-mediated literature links (MeSH → drugs)."""
        links = []
        for onto_link in record.resolved.ontology_links:
            if onto_link.entity_type == "therapeutic_area":
                drug_rows = self.db.fetch_all(
                    "SELECT id FROM drugs WHERE therapeutic_area_id = %s",
                    [onto_link.entity_id],
                )
                for drug_row in drug_rows:
                    created = self._upsert_link(
                        source_id=stored_id, source_type="literature",
                        target_id=str(drug_row["id"]), target_type="drug",
                        link_type=LinkType.EVIDENCE_FOR, via="mesh_term",
                        confidence=onto_link.confidence, source=source,
                        metadata={"mesh_id": onto_link.matched_value},
                    )
                    if created:
                        links.append(created)
            elif onto_link.entity_type == "mechanism":
                drug_rows = self.db.fetch_all(
                    "SELECT id FROM drugs WHERE mechanism_id = %s",
                    [onto_link.entity_id],
                )
                for drug_row in drug_rows:
                    created = self._upsert_link(
                        source_id=stored_id, source_type="literature",
                        target_id=str(drug_row["id"]), target_type="drug",
                        link_type=LinkType.EVIDENCE_FOR, via="mesh_mechanism",
                        confidence=onto_link.confidence, source=source,
                        metadata={"mesh_id": onto_link.matched_value},
                    )
                    if created:
                        links.append(created)
        return links

    # ---- Per-type linking rules ----

    def _link_drug(self, record: EmbeddedRecord, stored_id: str, source: str) -> list[dict]:
        """
        Drug creates links:
        - OWNS: company → drug (if company_id resolved)
        - IN_THERAPEUTIC_AREA: drug → therapeutic_area (if TA resolved)
        - TARGETS_MECHANISM: drug → mechanism (if mechanism resolved)
        """
        links = []
        resolved = record.resolved.resolved_links

        # Company OWNS drug
        company_link = resolved.get("company_name")
        if company_link:
            created = self._upsert_link(
                source_id=company_link.entity_id,
                source_type="company",
                target_id=stored_id,
                target_type="drug",
                link_type=LinkType.OWNS,
                via=company_link.matched_via,
                confidence=company_link.confidence,
                source=source,
            )
            if created:
                links.append(created)

        # Drug IN_THERAPEUTIC_AREA
        ta_link = resolved.get("therapeutic_area")
        if ta_link:
            created = self._upsert_link(
                source_id=stored_id,
                source_type="drug",
                target_id=ta_link.entity_id,
                target_type="therapeutic_area",
                link_type=LinkType.IN_THERAPEUTIC_AREA,
                via=ta_link.matched_via,
                confidence=ta_link.confidence,
                source=source,
            )
            if created:
                links.append(created)

        # Drug TARGETS_MECHANISM
        mech_link = resolved.get("mechanism")
        if mech_link:
            created = self._upsert_link(
                source_id=stored_id,
                source_type="drug",
                target_id=mech_link.entity_id,
                target_type="mechanism",
                link_type=LinkType.TARGETS_MECHANISM,
                via=mech_link.matched_via,
                confidence=mech_link.confidence,
                source=source,
            )
            if created:
                links.append(created)

        return links

    def _link_company(self, record: EmbeddedRecord, stored_id: str, source: str) -> list[dict]:
        """
        Company records don't create outgoing links on their own.
        Links from company → drug are created when the drug is stored.
        """
        return []

    def _link_trial(self, record: EmbeddedRecord, stored_id: str, source: str) -> list[dict]:
        """
        Trial creates links:
        - INVESTIGATES: trial → drug (if drug resolved via generic_name)
        - SPONSORS: company → trial (if sponsor resolved)
        """
        links = []
        resolved = record.resolved.resolved_links

        # INVESTIGATES: trial → drug
        drug_link = resolved.get("generic_name")
        if drug_link:
            created = self._upsert_link(
                source_id=stored_id,
                source_type="trial",
                target_id=drug_link.entity_id,
                target_type="drug",
                link_type=LinkType.INVESTIGATES,
                via=drug_link.matched_via,
                confidence=drug_link.confidence,
                source=source,
            )
            if created:
                links.append(created)

        # SPONSORS: company → trial
        sponsor_link = resolved.get("sponsor_name")
        if sponsor_link:
            created = self._upsert_link(
                source_id=sponsor_link.entity_id,
                source_type="company",
                target_id=stored_id,
                target_type="trial",
                link_type=LinkType.SPONSORS,
                via=sponsor_link.matched_via,
                confidence=sponsor_link.confidence,
                source=source,
            )
            if created:
                links.append(created)

        return links

    def _link_event(self, record: EmbeddedRecord, stored_id: str, source: str) -> list[dict]:
        """
        Market event creates links:
        - SHORTAGE_AFFECTS: event → drug (if drug resolved)
        """
        links = []
        resolved = record.resolved.resolved_links

        drug_link = resolved.get("generic_name")
        if drug_link:
            created = self._upsert_link(
                source_id=stored_id,
                source_type="event",
                target_id=drug_link.entity_id,
                target_type="drug",
                link_type=LinkType.SHORTAGE_AFFECTS,
                via=drug_link.matched_via,
                confidence=drug_link.confidence,
                source=source,
            )
            if created:
                links.append(created)

        return links

    def _link_literature(self, record: EmbeddedRecord, stored_id: str, source: str) -> list[dict]:
        """
        PubMed article creates links:
        - EVIDENCE_FOR: article → drug (via resolved generic_name or via MeSH ontology)

        The ontology-mediated path: article has MeSH descriptor IDs →
        find drugs whose therapeutic_area or mechanism shares that MeSH ID.
        """
        links = []
        resolved = record.resolved.resolved_links

        # Direct drug link (if generic_name resolved)
        drug_link = resolved.get("generic_name")
        if drug_link:
            created = self._upsert_link(
                source_id=stored_id,
                source_type="literature",
                target_id=drug_link.entity_id,
                target_type="drug",
                link_type=LinkType.EVIDENCE_FOR,
                via=drug_link.matched_via,
                confidence=drug_link.confidence,
                source=source,
            )
            if created:
                links.append(created)

        # Ontology-mediated links (MeSH IDs → drugs via therapeutic area)
        for onto_link in record.resolved.ontology_links:
            if onto_link.entity_type == "therapeutic_area":
                # Find drugs in this therapeutic area
                drug_rows = self.db.fetch_all(
                    "SELECT id FROM drugs WHERE therapeutic_area_id = %s",
                    [onto_link.entity_id],
                )
                for drug_row in drug_rows:
                    created = self._upsert_link(
                        source_id=stored_id,
                        source_type="literature",
                        target_id=str(drug_row["id"]),
                        target_type="drug",
                        link_type=LinkType.EVIDENCE_FOR,
                        via="mesh_term",
                        confidence=onto_link.confidence,
                        source=source,
                        metadata={"mesh_id": onto_link.matched_value},
                    )
                    if created:
                        links.append(created)

            elif onto_link.entity_type == "mechanism":
                # Find drugs targeting this mechanism
                drug_rows = self.db.fetch_all(
                    "SELECT id FROM drugs WHERE mechanism_id = %s",
                    [onto_link.entity_id],
                )
                for drug_row in drug_rows:
                    created = self._upsert_link(
                        source_id=stored_id,
                        source_type="literature",
                        target_id=str(drug_row["id"]),
                        target_type="drug",
                        link_type=LinkType.EVIDENCE_FOR,
                        via="mesh_mechanism",
                        confidence=onto_link.confidence,
                        source=source,
                        metadata={"mesh_id": onto_link.matched_value},
                    )
                    if created:
                        links.append(created)

        return links

    def _link_chunk(self, record: EmbeddedRecord, stored_id: str, source: str) -> list[dict]:
        """
        Knowledge chunk (SEC filing, user doc) creates links:
        - MENTIONED_IN: chunk → company or drug (whichever entity it's linked to)
        """
        links = []
        resolved = record.resolved.resolved_links

        for link_key in ("company_name", "cik", "generic_name"):
            entity_link = resolved.get(link_key)
            if entity_link:
                created = self._upsert_link(
                    source_id=stored_id,
                    source_type="knowledge_chunk",
                    target_id=entity_link.entity_id,
                    target_type=entity_link.entity_type,
                    link_type=LinkType.MENTIONED_IN,
                    via=entity_link.matched_via,
                    confidence=entity_link.confidence,
                    source=source,
                )
                if created:
                    links.append(created)

        return links

    def _link_ontology_term(self, record: EmbeddedRecord, stored_id: str, source: str) -> list[dict]:
        """
        Ontology terms don't create entity_links -- they are referenced
        via FK columns (therapeutic_area_id, mechanism_id) on drugs.
        """
        return []

    def _link_patent(self, record: EmbeddedRecord, stored_id: str, source: str) -> list[dict]:
        """
        Patent creates links:
        - HAS_PATENT: drug → patent (if drug resolved via nda_number)
        """
        links = []
        resolved = record.resolved.resolved_links

        drug_link = resolved.get("nda_number")
        if drug_link:
            created = self._upsert_link(
                source_id=drug_link.entity_id,
                source_type="drug",
                target_id=stored_id,
                target_type="patent",
                link_type=LinkType.HAS_PATENT,
                via=drug_link.matched_via,
                confidence=drug_link.confidence,
                source=source,
            )
            if created:
                links.append(created)

        return links

    def _link_regulatory_milestone(self, record: EmbeddedRecord, stored_id: str, source: str) -> list[dict]:
        """
        Regulatory milestone creates links:
        - HAS_MILESTONE: drug → milestone (if drug resolved via nda_number)
        """
        links = []
        resolved = record.resolved.resolved_links

        drug_link = resolved.get("nda_number")
        if drug_link:
            created = self._upsert_link(
                source_id=drug_link.entity_id,
                source_type="drug",
                target_id=stored_id,
                target_type="regulatory_milestone",
                link_type=LinkType.HAS_MILESTONE,
                via=drug_link.matched_via,
                confidence=drug_link.confidence,
                source=source,
            )
            if created:
                links.append(created)

        return links

    def _link_trial_outcome(self, record: EmbeddedRecord, stored_id: str, source: str) -> list[dict]:
        """Trial outcome: HAS_OUTCOME trial → outcome."""
        links = []
        data = record.resolved.normalized.canonical_data
        trial_id = data.get("nct_id", "")
        if "|" in trial_id:
            trial_id = trial_id.split("|")[0]

        if trial_id:
            created = self._upsert_link(
                source_id=trial_id,
                source_type="trial",
                target_id=stored_id,
                target_type="trial_outcome",
                link_type=LinkType.HAS_OUTCOME,
                via="trial_fk",
                confidence=1.0,
                source=source,
            )
            if created:
                links.append(created)
        return links

    def _link_trial_location(self, record: EmbeddedRecord, stored_id: str, source: str) -> list[dict]:
        """Trial location: LOCATED_AT trial → location."""
        links = []
        data = record.resolved.normalized.canonical_data
        trial_id = data.get("nct_id", "")
        if "|" in trial_id:
            trial_id = trial_id.split("|")[0]

        if trial_id:
            created = self._upsert_link(
                source_id=trial_id,
                source_type="trial",
                target_id=stored_id,
                target_type="trial_location",
                link_type=LinkType.LOCATED_AT,
                via="trial_fk",
                confidence=1.0,
                source=source,
            )
            if created:
                links.append(created)
        return links

    def _link_investigator(self, record: EmbeddedRecord, stored_id: str, source: str) -> list[dict]:
        """
        Investigator creates links:
        - LED_BY: trial → investigator (if trial NCT ID available)
        - AUTHORED_BY: article → investigator (if article context available)
        """
        links = []
        data = record.resolved.normalized.canonical_data

        # Trial → investigator (LED_BY)
        trial_nct_id = data.get("trial_nct_id")
        if trial_nct_id:
            created = self._upsert_link(
                source_id=trial_nct_id,
                source_type="trial",
                target_id=stored_id,
                target_type="investigator",
                link_type=LinkType.LED_BY,
                via="trial_pi",
                confidence=1.0,
                source=source,
            )
            if created:
                links.append(created)

        # If this investigator came from a PubMed article
        pmid = data.get("source_pmid")
        if pmid:
            row = self.db.fetch_one(
                "SELECT id FROM pubmed_articles WHERE pmid = %s", [pmid]
            )
            if row:
                created = self._upsert_link(
                    source_id=str(row["id"]),
                    source_type="literature",
                    target_id=stored_id,
                    target_type="investigator",
                    link_type=LinkType.AUTHORED_BY,
                    via="pubmed_author",
                    confidence=1.0,
                    source=source,
                )
                if created:
                    links.append(created)

        return links

    # ---- Link persistence ----

    def _upsert_link(
        self,
        source_id: str,
        source_type: str,
        target_id: str,
        target_type: str,
        link_type: LinkType,
        via: str,
        confidence: float,
        source: str,
        metadata: Optional[dict] = None,
    ) -> Optional[dict]:
        """
        Insert a link into entity_links if it doesn't already exist.

        Returns:
            Dict describing the link if created, None if it already existed.
        """
        import json

        metadata_json = json.dumps(metadata) if metadata else None

        row = self.db.fetch_one(
            """
            INSERT INTO entity_links
                (source_entity_id, source_entity_type,
                 target_entity_id, target_entity_type,
                 link_type, link_via, confidence, metadata, provenance_source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (source_entity_id, target_entity_id, link_type) DO NOTHING
            RETURNING id
            """,
            [
                source_id,
                source_type,
                target_id,
                target_type,
                link_type.value,
                via,
                confidence,
                metadata_json,
                source,
            ],
        )

        if row:
            link_info = {
                "link_id": str(row["id"]),
                "source_id": source_id,
                "target_id": target_id,
                "link_type": link_type.value,
                "via": via,
            }
            logger.info(
                "Created link: %s %s → %s %s [%s] via %s",
                source_type, source_id[:8],
                target_type, target_id[:8],
                link_type.value, via,
            )
            return link_info

        return None
