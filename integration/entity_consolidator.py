"""
Entity Consolidation — deduplicate drugs and companies.

Finds duplicate entities (same normalized name, multiple records) and merges
them into a single canonical record. The canonical is chosen by scoring on
source authority and data completeness. All FK references are repointed,
enrichment fields are coalesced, and duplicates are marked 'superseded'.

Usage:
    consolidator = EntityConsolidator(db, domain_pack=pack, dry_run=False)
    results = consolidator.run()
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Source authority scores for picking canonical records
DRUG_SOURCE_SCORES = {
    "fda_orange_book": 100,
    "clinical_trials_gov": 50,
    "pubmed": 30,
    "fda_shortages": 20,
    "openfda_faers": 15,
    "openfda_labels": 15,
    "pmc": 10,
}

COMPANY_SOURCE_SCORES = {
    "sec_edgar": 100,
    "fda_orange_book": 70,
    "clinical_trials_gov": 30,
    "pubmed": 10,
}

# Drug enrichment fields — each non-NULL adds to the score
DRUG_ENRICHMENT_FIELDS = [
    "brand_name", "nda_number", "company_id", "therapeutic_area_id",
    "mechanism_id", "approval_date", "molecule_embedding", "source_url",
    "active_ingredient", "dosage_form", "route", "marketing_status",
]

# Company enrichment fields
COMPANY_ENRICHMENT_FIELDS = [
    "cik", "ticker", "region", "country", "sic_code",
    "strategy_embedding", "source_url", "description",
]

# Tables with drug_id FK that need repointing
DRUG_FK_TABLES = [
    "clinical_trials",
    "market_events",
    "pubmed_articles",
    "patents",
    "regulatory_milestones",
    "adverse_events",
    "drug_labels",
    "pmc_articles",
]

# Tables with company_id FK
COMPANY_FK_TABLES = [
    "drugs",  # drugs.company_id
]


class EntityConsolidator:
    """Finds and merges duplicate drug and company entities."""

    def __init__(self, db, domain_pack=None, dry_run: bool = False):
        self.db = db
        self.domain_pack = domain_pack
        self.dry_run = dry_run

        # Load company normalizer
        self._normalize_company = None
        if domain_pack and domain_pack.mention_normalizers:
            company_normalizer = domain_pack.mention_normalizers.get("company")
            if company_normalizer:
                self._normalize_company = company_normalizer.normalize_fn
        if not self._normalize_company:
            try:
                from domain.pharma.mention_normalizer import normalize_company_mention
                self._normalize_company = normalize_company_mention
            except ImportError:
                self._normalize_company = lambda x: x.strip().lower()

    def run(self) -> dict:
        """Run full consolidation: drugs then companies."""
        results = {}
        results["drugs"] = self.consolidate_drugs()
        results["companies"] = self.consolidate_companies()
        return results

    # ============================================================
    # Drug consolidation
    # ============================================================

    def consolidate_drugs(self) -> dict:
        """Find and merge duplicate drug records."""
        stats = {"groups_found": 0, "records_merged": 0, "skipped": 0}

        # Find duplicate groups by normalized generic_name
        groups = self.db.fetch_all(
            """
            SELECT LOWER(generic_name) AS norm_name, array_agg(id) AS ids, count(*) AS cnt
            FROM drugs
            WHERE record_status != 'superseded' AND generic_name IS NOT NULL
            GROUP BY LOWER(generic_name)
            HAVING count(*) > 1
            ORDER BY count(*) DESC
            """
        )

        stats["groups_found"] = len(groups)
        logger.info("Drug dedup: found %d duplicate groups", len(groups))

        for group in groups:
            norm_name = group["norm_name"]
            drug_ids = group["ids"]

            # Fetch full records for scoring
            drugs = self.db.fetch_all(
                "SELECT * FROM drugs WHERE id = ANY(%s)",
                [drug_ids],
            )
            if len(drugs) < 2:
                stats["skipped"] += 1
                continue

            # Score and pick canonical
            scored = [(self._score_drug(d), d) for d in drugs]
            scored.sort(key=lambda x: (-x[0], x[1].get("created_at")))
            canonical = scored[0][1]
            duplicates = [s[1] for s in scored[1:]]

            if self.dry_run:
                logger.info(
                    "[DRY RUN] Drug '%s': canonical=%s (score=%d), would merge %d duplicates",
                    norm_name, canonical["id"], scored[0][0], len(duplicates),
                )
                stats["records_merged"] += len(duplicates)
                continue

            for dup in duplicates:
                self._merge_drug(canonical, dup)
                stats["records_merged"] += 1

            logger.info(
                "Drug '%s': merged %d duplicates into canonical %s",
                norm_name, len(duplicates), canonical["id"],
            )

        return stats

    def _score_drug(self, drug: dict) -> int:
        """Score a drug record for canonical selection."""
        source = (drug.get("source_authority") or drug.get("source_api") or "").lower()
        score = DRUG_SOURCE_SCORES.get(source, 0)
        for field in DRUG_ENRICHMENT_FIELDS:
            if drug.get(field) is not None:
                score += 5
        return score

    def _merge_drug(self, canonical: dict, duplicate: dict) -> None:
        """Merge a duplicate drug into the canonical record."""
        can_id = str(canonical["id"])
        dup_id = str(duplicate["id"])

        with self.db.transaction():
            # 1. COALESCE enrichment fields (fill NULLs in canonical only)
            updates = []
            params = []
            for field in DRUG_ENRICHMENT_FIELDS:
                if canonical.get(field) is None and duplicate.get(field) is not None:
                    updates.append(f"{field} = %s")
                    params.append(duplicate[field])

            if updates:
                params.append(can_id)
                self.db.execute(
                    f"UPDATE drugs SET {', '.join(updates)} WHERE id = %s",
                    params,
                )

            # 2. Repoint FK references in related tables
            for table in DRUG_FK_TABLES:
                self.db.execute(
                    f"UPDATE {table} SET drug_id = %s WHERE drug_id = %s",
                    [can_id, dup_id],
                )

            # 3. Repoint entity_links (both source and target)
            self._repoint_entity_links(can_id, dup_id, "drug")

            # 4. Repoint entity_aliases
            self.db.execute(
                """
                UPDATE entity_aliases SET entity_id = %s
                WHERE entity_type = 'drug' AND entity_id = %s
                    AND NOT EXISTS (
                        SELECT 1 FROM entity_aliases ea2
                        WHERE ea2.entity_type = 'drug'
                          AND ea2.entity_id = %s
                          AND ea2.alias_text = entity_aliases.alias_text
                          AND ea2.source_type = entity_aliases.source_type
                    )
                """,
                [can_id, dup_id, can_id],
            )
            # Delete remaining aliases that would conflict
            self.db.execute(
                "DELETE FROM entity_aliases WHERE entity_type = 'drug' AND entity_id = %s",
                [dup_id],
            )

            # 5. Repoint data_quality_results
            self.db.execute(
                "UPDATE data_quality_results SET entity_id = %s WHERE entity_id = %s AND entity_type = 'drug'",
                [can_id, dup_id],
            )

            # 6. Repoint unresolved_entities suggested_match_id
            self.db.execute(
                "UPDATE unresolved_entities SET suggested_match_id = %s WHERE suggested_match_id = %s AND record_type = 'drug'",
                [can_id, dup_id],
            )

            # 7. Create alias from duplicate's name → canonical
            dup_name = duplicate.get("generic_name", "")
            if dup_name:
                self.db.execute(
                    """
                    INSERT INTO entity_aliases (entity_type, entity_id, alias_text, source_type, confidence, verified)
                    VALUES ('drug', %s, %s, 'consolidation_merge', 1.0, TRUE)
                    ON CONFLICT (entity_type, alias_text, source_type) DO NOTHING
                    """,
                    [can_id, dup_name],
                )

            # 8. Mark duplicate as superseded
            self.db.execute(
                "UPDATE drugs SET record_status = 'superseded' WHERE id = %s",
                [dup_id],
            )

            # 9. Audit log
            self.db.execute(
                """
                INSERT INTO resolution_audit
                    (raw_value, entity_type, resolved_entity_id, resolution_method,
                     confidence, reasoning, source_type, accepted)
                VALUES (%s, 'drug', %s, 'consolidation_merge', 1.0, %s, 'consolidation', true)
                """,
                [
                    dup_name, can_id,
                    f"Merged duplicate drug {dup_id} into canonical {can_id}",
                ],
            )

    # ============================================================
    # Company consolidation
    # ============================================================

    def consolidate_companies(self) -> dict:
        """Find and merge duplicate company records."""
        stats = {"groups_found": 0, "records_merged": 0, "skipped": 0}

        # Fetch all active companies and group by normalized name
        companies = self.db.fetch_all(
            "SELECT * FROM companies WHERE record_status != 'superseded' AND name IS NOT NULL"
        )

        # Group by normalized name
        groups: dict[str, list[dict]] = {}
        for company in companies:
            norm = self._normalize_company(company["name"])
            if not norm:
                continue
            groups.setdefault(norm, []).append(company)

        # Filter to groups with duplicates
        dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
        stats["groups_found"] = len(dup_groups)
        logger.info("Company dedup: found %d duplicate groups", len(dup_groups))

        for norm_name, group_companies in dup_groups.items():
            # Score and pick canonical
            scored = [(self._score_company(c), c) for c in group_companies]
            scored.sort(key=lambda x: (-x[0], x[1].get("created_at")))
            canonical = scored[0][1]
            duplicates = [s[1] for s in scored[1:]]

            if self.dry_run:
                logger.info(
                    "[DRY RUN] Company '%s': canonical=%s (score=%d), would merge %d duplicates",
                    norm_name, canonical["id"], scored[0][0], len(duplicates),
                )
                stats["records_merged"] += len(duplicates)
                continue

            for dup in duplicates:
                self._merge_company(canonical, dup)
                stats["records_merged"] += 1

            logger.info(
                "Company '%s': merged %d duplicates into canonical %s",
                norm_name, len(duplicates), canonical["id"],
            )

        return stats

    def _score_company(self, company: dict) -> int:
        """Score a company record for canonical selection."""
        source = (company.get("source_authority") or company.get("source_api") or "").lower()
        score = COMPANY_SOURCE_SCORES.get(source, 0)
        for field in COMPANY_ENRICHMENT_FIELDS:
            if company.get(field) is not None:
                score += 5
        return score

    def _merge_company(self, canonical: dict, duplicate: dict) -> None:
        """Merge a duplicate company into the canonical record."""
        can_id = str(canonical["id"])
        dup_id = str(duplicate["id"])

        with self.db.transaction():
            # 1. COALESCE enrichment fields
            updates = []
            params = []
            for field in COMPANY_ENRICHMENT_FIELDS:
                if canonical.get(field) is None and duplicate.get(field) is not None:
                    updates.append(f"{field} = %s")
                    params.append(duplicate[field])

            if updates:
                params.append(can_id)
                self.db.execute(
                    f"UPDATE companies SET {', '.join(updates)} WHERE id = %s",
                    params,
                )

            # 2. Repoint drugs.company_id
            for table in COMPANY_FK_TABLES:
                self.db.execute(
                    f"UPDATE {table} SET company_id = %s WHERE company_id = %s",
                    [can_id, dup_id],
                )

            # 3. Repoint entity_links
            self._repoint_entity_links(can_id, dup_id, "company")

            # 4. Repoint entity_aliases
            self.db.execute(
                """
                UPDATE entity_aliases SET entity_id = %s
                WHERE entity_type = 'company' AND entity_id = %s
                    AND NOT EXISTS (
                        SELECT 1 FROM entity_aliases ea2
                        WHERE ea2.entity_type = 'company'
                          AND ea2.entity_id = %s
                          AND ea2.alias_text = entity_aliases.alias_text
                          AND ea2.source_type = entity_aliases.source_type
                    )
                """,
                [can_id, dup_id, can_id],
            )
            self.db.execute(
                "DELETE FROM entity_aliases WHERE entity_type = 'company' AND entity_id = %s",
                [dup_id],
            )

            # 5. Repoint data_quality_results
            self.db.execute(
                "UPDATE data_quality_results SET entity_id = %s WHERE entity_id = %s AND entity_type = 'company'",
                [can_id, dup_id],
            )

            # 6. Repoint unresolved_entities
            self.db.execute(
                "UPDATE unresolved_entities SET suggested_match_id = %s WHERE suggested_match_id = %s AND record_type = 'company'",
                [can_id, dup_id],
            )

            # 7. Create alias
            dup_name = duplicate.get("name", "")
            if dup_name:
                self.db.execute(
                    """
                    INSERT INTO entity_aliases (entity_type, entity_id, alias_text, source_type, confidence, verified)
                    VALUES ('company', %s, %s, 'consolidation_merge', 1.0, TRUE)
                    ON CONFLICT (entity_type, alias_text, source_type) DO NOTHING
                    """,
                    [can_id, dup_name],
                )

            # 8. Mark superseded
            self.db.execute(
                "UPDATE companies SET record_status = 'superseded' WHERE id = %s",
                [dup_id],
            )

            # 9. Audit log
            self.db.execute(
                """
                INSERT INTO resolution_audit
                    (raw_value, entity_type, resolved_entity_id, resolution_method,
                     confidence, reasoning, source_type, accepted)
                VALUES (%s, 'company', %s, 'consolidation_merge', 1.0, %s, 'consolidation', true)
                """,
                [
                    dup_name, can_id,
                    f"Merged duplicate company {dup_id} into canonical {can_id}",
                ],
            )

    # ============================================================
    # Entity links repointing (shared by drug and company merges)
    # ============================================================

    def _repoint_entity_links(self, canonical_id: str, duplicate_id: str, entity_type: str) -> None:
        """
        Repoint entity_links from duplicate to canonical, handling unique
        constraint conflicts on (source_entity_id, target_entity_id, link_type).
        """
        # Repoint source_entity_id
        source_links = self.db.fetch_all(
            "SELECT id, target_entity_id, link_type FROM entity_links WHERE source_entity_id = %s AND source_entity_type = %s",
            [duplicate_id, entity_type],
        )
        for link in source_links:
            # Check if canonical already has this link
            existing = self.db.fetch_one(
                "SELECT id FROM entity_links WHERE source_entity_id = %s AND target_entity_id = %s AND link_type = %s",
                [canonical_id, link["target_entity_id"], link["link_type"]],
            )
            if existing:
                # Canonical already covers this — delete the duplicate's link
                self.db.execute("DELETE FROM entity_links WHERE id = %s", [link["id"]])
            else:
                # Safe to repoint
                self.db.execute(
                    "UPDATE entity_links SET source_entity_id = %s WHERE id = %s",
                    [canonical_id, link["id"]],
                )

        # Repoint target_entity_id
        target_links = self.db.fetch_all(
            "SELECT id, source_entity_id, link_type FROM entity_links WHERE target_entity_id = %s AND target_entity_type = %s",
            [duplicate_id, entity_type],
        )
        for link in target_links:
            existing = self.db.fetch_one(
                "SELECT id FROM entity_links WHERE source_entity_id = %s AND target_entity_id = %s AND link_type = %s",
                [link["source_entity_id"], canonical_id, link["link_type"]],
            )
            if existing:
                self.db.execute("DELETE FROM entity_links WHERE id = %s", [link["id"]])
            else:
                self.db.execute(
                    "UPDATE entity_links SET target_entity_id = %s WHERE id = %s",
                    [canonical_id, link["id"]],
                )
