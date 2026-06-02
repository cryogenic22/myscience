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

    def __init__(self, db, domain_pack=None, dry_run: bool = False,
                 rank_by_richness: bool = False, drug_name_normalizer=None):
        self.db = db
        self.domain_pack = domain_pack
        self.dry_run = dry_run
        # rank_by_richness: pick the canonical row that owns the most data
        # (facts + clinical_trials + entity_links) rather than by source
        # authority. Keeps the survivor consistent with the dossier resolver,
        # which richness-ranks duplicates (ci-data-quality-integration-audit).
        self.rank_by_richness = rank_by_richness
        # drug_name_normalizer: optional callable to group duplicates by a
        # normalized name (e.g. strip salt forms / brand parentheticals) instead
        # of exact LOWER(generic_name). Combo-safe normalizers keep multi-drug
        # products in their own group.
        self.drug_name_normalizer = drug_name_normalizer
        # Restrict FK repointing to tables that actually exist with a drug_id
        # column — a missing table would abort the whole per-group transaction.
        self._drug_fk_tables = self._existing_drug_fk_tables()

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

    def _existing_drug_fk_tables(self) -> list[str]:
        """Subset of DRUG_FK_TABLES that exist with a drug_id column."""
        try:
            rows = self.db.fetch_all(
                "SELECT table_name FROM information_schema.columns "
                "WHERE column_name = 'drug_id' AND table_schema = 'public' "
                "  AND table_name = ANY(%s)",
                [list(DRUG_FK_TABLES)],
            )
            present = {r["table_name"] for r in rows}
            return [t for t in DRUG_FK_TABLES if t in present]
        except Exception:
            logger.warning("could not introspect drug FK tables; using full list",
                           exc_info=True)
            return list(DRUG_FK_TABLES)

    def _drug_richness(self, drug_id: str) -> int:
        """How much data a drug row owns: facts + clinical_trials +
        entity_links. Used to pick the canonical survivor."""
        try:
            row = self.db.fetch_one(
                "SELECT "
                " (SELECT count(*) FROM facts f "
                "    WHERE f.subject_entity_type='drug' "
                "      AND f.subject_entity_id = %s AND f.superseded_by IS NULL) "
                " + (SELECT count(*) FROM clinical_trials ct WHERE ct.drug_id = %s) "
                " + (SELECT count(*) FROM entity_links el "
                "      WHERE el.source_entity_id = %s OR el.target_entity_id = %s) "
                " AS richness",
                [str(drug_id), str(drug_id), str(drug_id), str(drug_id)],
            )
            return int(row["richness"]) if row and row.get("richness") is not None else 0
        except Exception:
            logger.debug("richness lookup failed for %s", drug_id, exc_info=True)
            return 0

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
        stats = {"groups_found": 0, "records_merged": 0, "skipped": 0,
                 "plan": []}

        groups = self._drug_duplicate_groups()
        stats["groups_found"] = len(groups)
        logger.info("Drug dedup: found %d duplicate groups", len(groups))

        for norm_name, drug_ids in groups:
            # Fetch full records for scoring (cast: ids may be uuid or str)
            drugs = self.db.fetch_all(
                "SELECT * FROM drugs WHERE id::text = ANY(%s)",
                [[str(x) for x in drug_ids]],
            )
            if len(drugs) < 2:
                stats["skipped"] += 1
                continue

            # Pick canonical: by data richness (consistent with the dossier
            # resolver) or by source authority + completeness.
            if self.rank_by_richness:
                scored = [(self._drug_richness(d["id"]), d) for d in drugs]
            else:
                scored = [(self._score_drug(d), d) for d in drugs]
            scored.sort(key=lambda x: (-x[0], str(x[1].get("created_at") or "")))
            canonical = scored[0][1]
            duplicates = [s[1] for s in scored[1:]]

            stats["plan"].append({
                "name": norm_name,
                "canonical": str(canonical["id"]),
                "canonical_name": canonical.get("generic_name"),
                "score": scored[0][0],
                "merge": [
                    {"id": str(d["id"]), "name": d.get("generic_name")}
                    for d in duplicates
                ],
            })

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

    def _drug_duplicate_groups(self) -> list[tuple[str, list]]:
        """Return [(norm_name, [drug_ids])] for groups with >1 active row.

        Uses ``drug_name_normalizer`` when provided (e.g. strip salt forms /
        brand parentheticals — combo-safe), else exact LOWER(generic_name).
        Excludes already-merged/superseded rows."""
        active = (
            "(record_status IS DISTINCT FROM 'superseded' "
            " AND record_status IS DISTINCT FROM 'merged')"
        )
        if self.drug_name_normalizer is None:
            rows = self.db.fetch_all(
                f"""
                SELECT LOWER(generic_name) AS norm_name, array_agg(id) AS ids
                  FROM drugs
                 WHERE {active} AND generic_name IS NOT NULL
                 GROUP BY LOWER(generic_name)
                HAVING count(*) > 1
                ORDER BY count(*) DESC
                """
            )
            return [(r["norm_name"], r["ids"]) for r in rows]

        rows = self.db.fetch_all(
            f"SELECT id, generic_name FROM drugs "
            f"WHERE {active} AND generic_name IS NOT NULL AND generic_name != ''"
        )
        buckets: dict[str, list] = {}
        for r in rows:
            norm = self.drug_name_normalizer(r["generic_name"])
            if not norm or len(norm) < 2:
                continue
            buckets.setdefault(norm, []).append(r["id"])
        return [(n, ids) for n, ids in buckets.items() if len(ids) > 1]

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

            # 2. Repoint FK references in related tables (existing ones only).
            # Conflict-safe: some tables have a unique constraint that includes
            # drug_id (e.g. regulatory_milestones on
            # drug_id+submission_type+submission_number). A blunt UPDATE would
            # collide when the canonical already has the equivalent row. Use a
            # savepoint and, on conflict, drop the duplicate's copies (the
            # canonical already carries them — these are the SAME real drug).
            for table in self._drug_fk_tables:
                self._repoint_drug_fk(table, can_id, dup_id)

            # 2b. Repoint text-keyed spine references (NOT real FKs, so the
            # generic loop above misses them). Without this, facts/signals
            # asserted against a merged duplicate would be orphaned — the
            # dossier resolves to the canonical id and would lose that evidence.
            # facts has no unique constraint on the subject, so a plain UPDATE
            # is safe (and facts is append-only — never delete here).
            self.db.execute(
                "UPDATE facts SET subject_entity_id = %s "
                "WHERE subject_entity_type = 'drug' AND subject_entity_id = %s",
                [can_id, dup_id],
            )
            self._repoint_signals(can_id, dup_id)

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

    def _repoint_drug_fk(self, table: str, can_id: str, dup_id: str) -> None:
        """Repoint one FK table's drug_id dup→canonical, conflict-safe.

        Uses a SQL savepoint so a unique-constraint collision doesn't abort the
        whole per-group transaction. On conflict the duplicate's rows for that
        table are dropped (the canonical — chosen as the richest, same real
        drug — already holds the equivalents). `table` comes from the vetted
        DRUG_FK_TABLES constant, so the f-string is safe."""
        sp = f"sp_{table}"
        self.db.execute(f"SAVEPOINT {sp}")
        try:
            self.db.execute(
                f"UPDATE {table} SET drug_id = %s WHERE drug_id = %s",
                [can_id, dup_id],
            )
            self.db.execute(f"RELEASE SAVEPOINT {sp}")
        except Exception:
            self.db.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            self.db.execute(f"DELETE FROM {table} WHERE drug_id = %s", [dup_id])
            self.db.execute(f"RELEASE SAVEPOINT {sp}")
            logger.info("repoint %s: dropped duplicate rows for %s (conflict)",
                        table, dup_id)

    def _repoint_signals(self, can_id: str, dup_id: str) -> None:
        """Repoint signals.primary_entity_id dup→canonical, conflict-safe.
        Signals are never deleted here; on conflict the dup's signals are left
        (rare; avoids destroying signal history)."""
        self.db.execute("SAVEPOINT sp_signals")
        try:
            self.db.execute(
                "UPDATE signals SET primary_entity_id = %s "
                "WHERE primary_entity_type = 'drug' AND primary_entity_id = %s",
                [can_id, dup_id],
            )
            self.db.execute("RELEASE SAVEPOINT sp_signals")
        except Exception:
            self.db.execute("ROLLBACK TO SAVEPOINT sp_signals")
            self.db.execute("RELEASE SAVEPOINT sp_signals")
            logger.info("repoint signals: left dup signals for %s (conflict)", dup_id)

    def _repoint_entity_links(self, canonical_id: str, duplicate_id: str, entity_type: str) -> None:
        """
        Repoint entity_links from duplicate to canonical, handling unique
        constraint conflicts on (source_entity_id, target_entity_id, link_type).

        Set-based (4 statements) rather than per-link: high-degree nodes (e.g.
        'placebo' touches every trial) have tens of thousands of links, and a
        Python loop with a round-trip per link is pathologically slow on a
        remote DB. First delete the duplicate's links the canonical already
        has, then bulk-repoint the rest. A savepoint guards the rare residual
        conflict (two duplicate links to the same target).
        """
        for side, other in (("source", "target"), ("target", "source")):
            sp = f"sp_links_{side}"
            self.db.execute(f"SAVEPOINT {sp}")
            try:
                # Drop duplicate's links that canonical already carries.
                self.db.execute(
                    f"""
                    DELETE FROM entity_links el
                     WHERE el.{side}_entity_id = %s
                       AND el.{side}_entity_type = %s
                       AND EXISTS (
                           SELECT 1 FROM entity_links c
                            WHERE c.{side}_entity_id = %s
                              AND c.{other}_entity_id = el.{other}_entity_id
                              AND c.link_type = el.link_type)
                    """,
                    [duplicate_id, entity_type, canonical_id],
                )
                # Bulk-repoint the remainder.
                self.db.execute(
                    f"UPDATE entity_links SET {side}_entity_id = %s "
                    f"WHERE {side}_entity_id = %s AND {side}_entity_type = %s",
                    [canonical_id, duplicate_id, entity_type],
                )
                self.db.execute(f"RELEASE SAVEPOINT {sp}")
            except Exception:
                # Residual conflict (intra-duplicate dupes): drop the rest.
                self.db.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                self.db.execute(
                    f"DELETE FROM entity_links "
                    f"WHERE {side}_entity_id = %s AND {side}_entity_type = %s",
                    [duplicate_id, entity_type],
                )
                self.db.execute(f"RELEASE SAVEPOINT {sp}")
                logger.info("repoint entity_links(%s): dropped residual for %s",
                            side, duplicate_id)
