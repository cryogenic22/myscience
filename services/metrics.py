"""
PharmaMetrics: Pre-computed pharmaceutical KPIs from materialized views.

Provides trustworthy, pre-calculated metrics that agents and users can query
without needing to compute from raw data (which risks hallucinated math).

Usage:
    metrics = PharmaMetrics(db, config)
    pipeline = metrics.drug_pipeline_strength(therapeutic_area="Diabetes Mellitus")
    rates = metrics.trial_success_rate(drug_id="some-uuid")
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from services.telemetry import log_mv_fallback

logger = logging.getLogger(__name__)

# Materialized views this service reads from
VIEWS = [
    "mv_drug_pipeline_strength",
    "mv_trial_success_rate",
    "mv_evidence_density",
    "mv_competitive_landscape",
    "mv_company_portfolio",
]

# D6 — metric provenance. Materialized-view / realtime aggregates are real but
# were unciteable: a "23 drugs in P2-3" narrative had no source or as-of, the
# largest ungrounded-prose risk. We stamp every metric row with a `_provenance`
# block — derivation (which view/base tables + the aggregation), computed_at
# (when this call read it), and a record_basis (the N records the figure rolls
# up) — so the synthesis layer (owned elsewhere) can cite it without recomputing.
# Each metric method declares how it was derived here.
_METHOD_PROVENANCE: dict[str, dict] = {
    "drug_pipeline_strength": {
        "source": "mv_drug_pipeline_strength",
        "derivation": "phase-weighted active-trial count per drug from clinical_trials",
        "basis_field": "total_trials",
    },
    "trial_success_rate": {
        "source": "mv_trial_success_rate",
        "derivation": "completed / (completed + terminated + withdrawn) per drug from clinical_trials",
        "basis_field": "total",
    },
    "evidence_density": {
        "source": "mv_evidence_density",
        "derivation": "recency-weighted PubMed article count per drug from pubmed_articles",
        "basis_field": "total_articles",
    },
    "competitive_landscape": {
        "source": "mv_competitive_landscape",
        "derivation": "drugs/trials grouped by mechanism × therapeutic_area",
        "basis_field": "drug_count",
    },
    "company_portfolio": {
        "source": "mv_company_portfolio",
        "derivation": "drug/trial/article rollup per company via entity_links (SPONSORS, OWNS)",
        "basis_field": "drug_count",
    },
}


def stamp_metric_provenance(
    rows: list[dict], method: str, *, realtime: bool = False
) -> list[dict]:
    """Attach a citeable `_provenance` block to each metric row (D6).

    Additive: mutates rows in place and returns them. Each row's `_provenance`
    carries the derivation, the source view (or 'base tables (realtime)' when
    the MV fallback fired), a computed_at timestamp, and a record_basis count
    drawn from the row's basis_field — enough for the synthesis layer to render
    "derived from N records, as of <date>" without recomputing.
    """
    meta = _METHOD_PROVENANCE.get(method, {})
    source = "base tables (realtime)" if realtime else meta.get("source", method)
    computed_at = datetime.now(timezone.utc).isoformat()
    basis_field = meta.get("basis_field")
    for row in rows:
        if not isinstance(row, dict):
            continue
        basis = row.get(basis_field) if basis_field else None
        row["_provenance"] = {
            "method": method,
            "source": source,
            "derivation": meta.get("derivation", ""),
            "computed_at": computed_at,
            "record_basis": int(basis) if isinstance(basis, (int, float)) else None,
            "realtime_fallback": realtime,
        }
    return rows


class PharmaMetrics:
    """Pharma-domain KPIs backed by PostgreSQL materialized views."""

    def __init__(self, db, config):
        self.db = db
        self.config = config

    def drug_pipeline_strength(
        self,
        drug_id: Optional[str] = None,
        therapeutic_area: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Active trials by phase per drug, with phase-weighted pipeline score.

        Phase weights: P1=1, P1/P2=1.5, P2=2, P2/P3=3, P3=4, P4=1, Early=0.5
        Higher score = deeper, later-stage pipeline = more valuable.

        When filtering by therapeutic_area, also checks entity_links
        for multi-indication drugs (e.g. SGLT2i in both diabetes and HF).
        """
        conditions = []
        params = []

        if drug_id:
            conditions.append("drug_id = %s")
            params.append(drug_id)
        if therapeutic_area:
            # Match via materialized view TA column OR via entity_links
            conditions.append("""(
                therapeutic_area ILIKE %s
                OR drug_id::text IN (
                    SELECT el.source_entity_id
                    FROM entity_links el
                    JOIN therapeutic_areas ta ON el.target_entity_id::uuid = ta.id
                    WHERE el.link_type = 'IN_THERAPEUTIC_AREA'
                      AND ta.name ILIKE %s
                )
            )""")
            params.extend([f"%{therapeutic_area}%", f"%{therapeutic_area}%"])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        rows = self.db.fetch_all(
            f"""
            SELECT drug_id, drug_name, brand_name, therapeutic_area, mechanism,
                   p1_count, p2_count, p3_count, p4_count,
                   total_trials, active_trials,
                   pipeline_score, active_pipeline_score, last_trial_start
            FROM mv_drug_pipeline_strength
            {where}
            ORDER BY pipeline_score DESC
            LIMIT %s
            """,
            params,
        )

        # Post-process: add computed insight fields
        if rows:
            scores = sorted([r.get("pipeline_score", 0) or 0 for r in rows])
            n = len(scores)
            for row in rows:
                score = row.get("pipeline_score", 0) or 0
                rank = sum(1 for s in scores if s <= score)
                row["percentile_rank"] = round((rank / n) * 100, 1) if n else 0

                early = (row.get("p1_count", 0) or 0) + (row.get("p2_count", 0) or 0)
                late = (row.get("p3_count", 0) or 0) + (row.get("p4_count", 0) or 0)
                row["phase_progression_rate"] = round(late / early, 2) if early > 0 else None

        # Fallback: if MV returns sparse results for a TA query, try realtime
        if len(rows) <= 2 and therapeutic_area:
            logger.info("Pipeline MV returned %d rows for '%s', trying realtime", len(rows), therapeutic_area)
            log_mv_fallback(
                self.db,
                method_name="drug_pipeline_strength",
                mv_name="mv_drug_pipeline_strength",
                reason="insufficient_data",
                row_count=len(rows),
            )
            rt_rows = realtime_pipeline_strength(self.db, therapeutic_area, limit=limit)
            if len(rt_rows) > len(rows):
                return stamp_metric_provenance(rt_rows, "drug_pipeline_strength", realtime=True)

        return stamp_metric_provenance(rows, "drug_pipeline_strength")

    def trial_success_rate(
        self,
        drug_id: Optional[str] = None,
        therapeutic_area: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Completed vs terminated/withdrawn trials per drug.

        success_rate = completed / (completed + terminated + withdrawn).
        Includes TA-level average for benchmarking.
        """
        conditions = []
        params = []

        if drug_id:
            conditions.append("drug_id = %s")
            params.append(drug_id)
        if therapeutic_area:
            conditions.append("""(
                therapeutic_area ILIKE %s
                OR drug_id::text IN (
                    SELECT el.source_entity_id
                    FROM entity_links el
                    JOIN therapeutic_areas ta ON el.target_entity_id::uuid = ta.id
                    WHERE el.link_type = 'IN_THERAPEUTIC_AREA'
                      AND ta.name ILIKE %s
                )
            )""")
            params.extend([f"%{therapeutic_area}%", f"%{therapeutic_area}%"])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        rows = self.db.fetch_all(
            f"""
            SELECT drug_id, drug_name, therapeutic_area,
                   total, completed, terminated, withdrawn, suspended, active,
                   success_rate, ta_avg_success_rate
            FROM mv_trial_success_rate
            {where}
            ORDER BY total DESC
            LIMIT %s
            """,
            params,
        )
        return stamp_metric_provenance(rows, "trial_success_rate")

    def evidence_density(
        self,
        drug_id: Optional[str] = None,
        min_articles: int = 1,
        limit: int = 50,
    ) -> list[dict]:
        """PubMed articles per drug, recency-weighted.

        Weights: last 2yr=1.0, 2-5yr=0.5, 5+yr=0.25.
        Higher weighted_score = stronger, more recent evidence base.
        """
        conditions = [f"total_articles >= %s"]
        params = [min_articles]

        if drug_id:
            conditions.append("drug_id = %s")
            params.append(drug_id)

        where = f"WHERE {' AND '.join(conditions)}"
        params.append(limit)

        rows = self.db.fetch_all(
            f"""
            SELECT drug_id, drug_name, total_articles, recent_count,
                   weighted_score, oldest_date, newest_date
            FROM mv_evidence_density
            {where}
            ORDER BY weighted_score DESC
            LIMIT %s
            """,
            params,
        )
        return stamp_metric_provenance(rows, "evidence_density")

    def competitive_landscape(
        self,
        therapeutic_area_id: Optional[str] = None,
        mechanism_id: Optional[str] = None,
        topic: Optional[str] = None,
        original_topic: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Drugs per mechanism per therapeutic area with pipeline depth.

        Groups competition at the mechanism level (e.g., "GLP-1 receptor agonists
        in Diabetes") which is where pharma competition actually happens.

        Args:
            topic: Free-text topic filter — matched against mechanism_name
                   and therapeutic_area columns via ILIKE.
        """
        conditions = []
        params = []

        if therapeutic_area_id:
            conditions.append("therapeutic_area_id = %s")
            params.append(therapeutic_area_id)
        if mechanism_id:
            conditions.append("mechanism_id = %s")
            params.append(mechanism_id)
        if topic:
            conditions.append(
                "(mechanism_name ILIKE %s OR therapeutic_area ILIKE %s)"
            )
            params.extend([f"%{topic}%", f"%{topic}%"])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        try:
            rows = self.db.fetch_all(
                f"""
                SELECT mechanism_id, mechanism_name, therapeutic_area_id, therapeutic_area,
                       drug_count, trial_count, active_trial_count,
                       top_drug, total_pipeline_score
                FROM mv_competitive_landscape
                {where}
                ORDER BY trial_count DESC
                LIMIT %s
                """,
                params,
            )

            # Post-process: add market share percentage
            total_drugs = sum(r.get("drug_count", 0) or 0 for r in rows)
            if total_drugs > 0:
                for row in rows:
                    dc = row.get("drug_count", 0) or 0
                    row["market_share_pct"] = round((dc / total_drugs) * 100, 1)

            # Fallback: if MV returns sparse results, try real-time query
            if len(rows) <= 2 and topic:
                logger.info("MV returned %d rows for '%s', trying realtime fallback", len(rows), topic)
                log_mv_fallback(
                    self.db,
                    method_name="competitive_landscape",
                    mv_name="mv_competitive_landscape",
                    reason="insufficient_data",
                    row_count=len(rows),
                )
                # Try expanded topic first
                rt_rows = realtime_competitive_landscape(self.db, topic, limit=limit)
                # If original_topic differs from expanded topic, also try the short form
                if len(rt_rows) <= len(rows) and original_topic and original_topic.lower() != topic.lower():
                    logger.info("Expanded topic '%s' returned %d rows, trying original '%s'", topic, len(rt_rows), original_topic)
                    rt_original = realtime_competitive_landscape(self.db, original_topic, limit=limit)
                    if len(rt_original) > len(rt_rows):
                        rt_rows = rt_original
                if len(rt_rows) > len(rows):
                    return stamp_metric_provenance(rt_rows, "competitive_landscape", realtime=True)

            return stamp_metric_provenance(rows, "competitive_landscape")
        except Exception as exc:
            logger.warning("competitive_landscape unavailable: %s", exc)
            log_mv_fallback(
                self.db,
                method_name="competitive_landscape",
                mv_name="mv_competitive_landscape",
                reason="mv_error",
                row_count=0,
            )
            # Fallback to realtime on MV failure
            if topic:
                logger.info("MV failed, trying realtime fallback for '%s'", topic)
                rt_rows = realtime_competitive_landscape(self.db, topic, limit=limit)
                if not rt_rows and original_topic and original_topic.lower() != topic.lower():
                    rt_rows = realtime_competitive_landscape(self.db, original_topic, limit=limit)
                return stamp_metric_provenance(rt_rows, "competitive_landscape", realtime=True)
            return []

    def company_portfolio(
        self,
        company_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Company-level rollup: drugs, trials, TAs, articles, pipeline score.

        Uses entity_links (SPONSORS, OWNS) to associate trials/drugs with companies,
        since the drugs.company_id FK is sparsely populated.
        """
        conditions = []
        params = []

        if company_id:
            conditions.append("company_id = %s")
            params.append(company_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        try:
            rows = self.db.fetch_all(
                f"""
                SELECT company_id, company_name, ticker, country,
                       drug_count, trial_count, active_trial_count,
                       article_count, ta_count, pipeline_score_total
                FROM mv_company_portfolio
                {where}
                ORDER BY pipeline_score_total DESC
                LIMIT %s
                """,
                params,
            )
            return stamp_metric_provenance(rows, "company_portfolio")
        except Exception as exc:
            logger.warning("company_portfolio unavailable: %s", exc)
            log_mv_fallback(
                self.db,
                method_name="company_portfolio",
                mv_name="mv_company_portfolio",
                reason="mv_error",
                row_count=0,
            )
            return []

    # Academic / clinical orgs that are NOT pharma market players — excluded
    # from "who leads" rankings. Word-bounded (\y) to mirror
    # services.ctx_pipeline._JUNK_ORG_RE and avoid partial-word false positives.
    _JUNK_ORG_SQL = (
        r'\y(institut\w*|universit\w*|college|school|foundation|hospital|'
        r'registry|ministry|department|center|centre|clinic|trust|consortium|'
        r'society|association|polyclinic)\y'
        r'|medical\s+cent(er|re)|health\s+system'
    )

    def top_companies_by_topic(self, topic: Optional[str], limit: int = 8) -> list[dict]:
        """Companies ranked by # of drugs in a therapeutic area or mechanism class.

        Answers "which companies dominate/lead <area>". Uses the AUTHORITATIVE
        ``drugs.company_id`` attribution (derived from dominant trial sponsor by
        the data lane) — NOT raw entity_links sponsorship, which conflates trial
        sponsors with developers and ranked vaccine makers as GLP-1 leaders.
        Excludes academic/clinical orgs. Real-time (no MV), bounded by the topic
        filter + LIMIT.
        """
        if not topic:
            return []
        try:
            rows = self.db.fetch_all(
                """
                SELECT c.name AS company_name,
                       COUNT(DISTINCT d.id)  AS drug_count,
                       COUNT(DISTINCT ct.id) AS trial_count
                FROM drugs d
                JOIN companies c ON c.id = d.company_id
                LEFT JOIN therapeutic_areas ta ON ta.id = d.therapeutic_area_id
                LEFT JOIN mechanisms_of_action m ON m.id = d.mechanism_id
                LEFT JOIN clinical_trials ct ON ct.drug_id = d.id
                WHERE (ta.name ILIKE %s OR m.name ILIKE %s)
                  AND d.record_status = 'active'
                  AND c.record_status IS DISTINCT FROM 'superseded'
                  AND c.name !~* %s
                GROUP BY c.name
                ORDER BY drug_count DESC, trial_count DESC
                LIMIT %s
                """,
                [f"%{topic}%", f"%{topic}%", self._JUNK_ORG_SQL, limit],
            )
            return stamp_metric_provenance(rows, "top_companies_by_topic", realtime=True)
        except Exception as exc:
            logger.warning("top_companies_by_topic unavailable: %s", exc)
            return []

    def refresh(self) -> dict:
        """Refresh all materialized views. Call after pipeline runs or backfills."""
        results = {}
        for view in VIEWS:
            try:
                self.db.execute(f"REFRESH MATERIALIZED VIEW {view}")
                results[view] = "refreshed"
                logger.info("Refreshed materialized view: %s", view)
            except Exception as e:
                results[view] = f"error: {e}"
                logger.warning("Failed to refresh %s: %s", view, e)
        return results


# ── Real-time fallback functions (module-level, used when MVs are stale) ──


def realtime_competitive_landscape(db, topic: str, limit: int = 30) -> list[dict]:
    """Compute competitive landscape from base tables (not materialized views).

    Groups drugs by mechanism + therapeutic area, counting drugs and trials.
    Used as fallback when mv_competitive_landscape returns sparse results.
    """
    try:
        rows = db.fetch_all(
            """
            SELECT
                m.name AS mechanism_name,
                ta.name AS therapeutic_area,
                COUNT(DISTINCT d.id) AS drug_count,
                COUNT(DISTINCT ct.id) AS trial_count,
                COUNT(DISTINCT ct.id) FILTER (WHERE ct.status IN ('RECRUITING', 'ACTIVE_NOT_RECRUITING')) AS active_trial_count,
                COALESCE(SUM(
                    CASE ct.phase
                        WHEN 'Phase 1' THEN 1 WHEN 'Phase 1/Phase 2' THEN 1.5
                        WHEN 'Phase 2' THEN 2 WHEN 'Phase 2/Phase 3' THEN 3
                        WHEN 'Phase 3' THEN 4 WHEN 'Phase 4' THEN 1
                        ELSE 0.5
                    END
                ), 0) AS total_pipeline_score
            FROM drugs d
            JOIN mechanisms_of_action m ON d.mechanism_id = m.id
            JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
            LEFT JOIN entity_links el ON el.target_entity_id = d.id::text
                AND el.target_entity_type = 'drug' AND el.link_type = 'INVESTIGATES'
            LEFT JOIN clinical_trials ct ON ct.id = el.source_entity_id
            WHERE d.record_status IS DISTINCT FROM 'excluded'
              AND d.record_status IS DISTINCT FROM 'merged'
              AND (LOWER(m.name) ILIKE %s OR LOWER(ta.name) ILIKE %s)
            GROUP BY m.name, ta.name
            ORDER BY total_pipeline_score DESC
            LIMIT %s
            """,
            [f"%{topic.lower()}%", f"%{topic.lower()}%", limit],
        )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("realtime_competitive_landscape failed: %s", e)
        return []


def realtime_pipeline_strength(db, therapeutic_area: str, limit: int = 20) -> list[dict]:
    """Compute drug pipeline strength from base tables (not materialized views).

    Used as fallback when mv_drug_pipeline_strength returns sparse results.
    """
    try:
        rows = db.fetch_all(
            """
            SELECT
                d.generic_name AS drug_name,
                d.id::text AS drug_id,
                COUNT(DISTINCT ct.id) AS total_trials,
                COUNT(DISTINCT ct.id) FILTER (WHERE ct.status IN ('RECRUITING', 'ACTIVE_NOT_RECRUITING')) AS active_trials,
                COUNT(ct.id) FILTER (WHERE ct.phase = 'Phase 1') AS p1_count,
                COUNT(ct.id) FILTER (WHERE ct.phase LIKE 'Phase 2%') AS p2_count,
                COUNT(ct.id) FILTER (WHERE ct.phase LIKE 'Phase 3%') AS p3_count,
                COUNT(ct.id) FILTER (WHERE ct.phase = 'Phase 4') AS p4_count,
                COALESCE(SUM(
                    CASE ct.phase
                        WHEN 'Phase 1' THEN 1 WHEN 'Phase 1/Phase 2' THEN 1.5
                        WHEN 'Phase 2' THEN 2 WHEN 'Phase 2/Phase 3' THEN 3
                        WHEN 'Phase 3' THEN 4 WHEN 'Phase 4' THEN 1
                        ELSE 0.5
                    END
                ), 0) AS pipeline_score
            FROM drugs d
            JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
            LEFT JOIN entity_links el ON el.target_entity_id = d.id::text
                AND el.target_entity_type = 'drug' AND el.link_type = 'INVESTIGATES'
            LEFT JOIN clinical_trials ct ON ct.id = el.source_entity_id
            WHERE d.record_status IS DISTINCT FROM 'excluded'
              AND d.record_status IS DISTINCT FROM 'merged'
              AND LOWER(ta.name) ILIKE %s
            GROUP BY d.generic_name, d.id
            HAVING COUNT(DISTINCT ct.id) > 0
            ORDER BY pipeline_score DESC
            LIMIT %s
            """,
            [f"%{therapeutic_area.lower()}%", limit],
        )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("realtime_pipeline_strength failed: %s", e)
        return []


