"""
Data quality engine for Market-Zero.

Provides configurable quality rules per entity type with 5 rule categories:
  - completeness: % of expected fields that are non-NULL
  - freshness: age of record vs source verification
  - consistency: cross-field agreement checks
  - cross_source: multi-source corroboration scoring
  - embedding_coverage: whether embeddings exist

Each rule produces a 0.0-1.0 score. Composite score is weighted average.
Results persisted to data_quality_results; summary written to entity row.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class QualityResult:
    """Result of a single quality rule evaluation."""
    rule_id: str
    rule_name: str
    rule_type: str
    severity: str
    passed: bool
    score: float
    details: dict = field(default_factory=dict)


@dataclass
class TableQualityReport:
    """Aggregate quality report for an entire table."""
    entity_type: str
    total_records: int
    assessed_records: int
    avg_score: float
    passing_count: int
    failing_count: int
    by_rule: dict = field(default_factory=dict)
    by_severity: dict = field(default_factory=dict)


# ─────────────────────────────────────────────
# Rule type → column mappings for completeness checks
# ─────────────────────────────────────────────

ENTITY_TABLE_MAP = {
    "drug": "drugs",
    "company": "companies",
    "trial": "clinical_trials",
    "literature": "pubmed_articles",
    "event": "market_events",
}

ENTITY_ID_COL = {
    "drug": "id",
    "company": "id",
    "trial": "id",
    "literature": "pmid",
    "event": "id",
}


class DataQualityEngine:
    """
    Runs configurable quality rules against records and persists results.

    When a domain_pack is provided, entity table and ID column mappings
    are read from the pack instead of module-level constants.

    Usage:
        engine = DataQualityEngine(db, config)
        results = engine.assess_record("drug", drug_id)
        report = engine.assess_table("trial")
    """

    def __init__(self, db, config, domain_pack=None):
        self.db = db
        self.config = config
        self.domain_pack = domain_pack
        self._rules_cache: dict[str, list[dict]] | None = None

        # Build table/ID mappings from domain pack or fallback
        if domain_pack:
            self._entity_table_map = domain_pack.get_entity_table_map()
            self._entity_id_col = domain_pack.get_entity_id_col_map()
        else:
            self._entity_table_map = ENTITY_TABLE_MAP
            self._entity_id_col = ENTITY_ID_COL

    def _load_rules(self, entity_type: str) -> list[dict]:
        """Load enabled rules for an entity type from DB."""
        if self._rules_cache is None:
            self._rules_cache = {}
            rows = self.db.fetch_all(
                "SELECT * FROM data_quality_rules WHERE enabled = TRUE ORDER BY entity_type, rule_name"
            )
            for r in rows:
                et = r["entity_type"]
                if et not in self._rules_cache:
                    self._rules_cache[et] = []
                self._rules_cache[et].append(dict(r))
        return self._rules_cache.get(entity_type, [])

    def invalidate_cache(self):
        """Force reload of rules on next call."""
        self._rules_cache = None

    # ─── Public API ──────────────────────────────

    def assess_record(self, entity_type: str, entity_id: str) -> list[QualityResult]:
        """Run all enabled rules for a single record."""
        rules = self._load_rules(entity_type)
        if not rules:
            return []

        table = self._entity_table_map.get(entity_type)
        id_col = self._entity_id_col.get(entity_type, "id")
        if not table:
            return []

        record = self.db.fetch_one(
            f"SELECT * FROM {table} WHERE {id_col} = %s", [entity_id]
        )
        if not record:
            return []

        results = []
        for rule in rules:
            result = self._evaluate_rule(rule, record, entity_type, entity_id)
            results.append(result)

        # Persist results
        self._persist_results(entity_type, entity_id, results)

        # Update composite score on the record
        composite = self.compute_composite_score(results)
        self.db.execute(
            f"UPDATE {table} SET quality_score = %s WHERE {id_col} = %s",
            [composite, entity_id],
        )

        return results

    def assess_batch(self, entity_type: str, entity_ids: list[str]) -> dict[str, list[QualityResult]]:
        """Run quality assessment for multiple records."""
        out = {}
        for eid in entity_ids:
            out[eid] = self.assess_record(entity_type, eid)
        return out

    def assess_table(self, entity_type: str) -> TableQualityReport:
        """Full table scan with aggregate quality metrics."""
        table = self._entity_table_map.get(entity_type)
        id_col = self._entity_id_col.get(entity_type, "id")
        if not table:
            return TableQualityReport(entity_type, 0, 0, 0.0, 0, 0)

        total = self.db.fetch_one(f"SELECT count(*) as c FROM {table}")["c"]
        ids = self.db.fetch_all(f"SELECT {id_col} as eid FROM {table}")

        scores = []
        rule_stats: dict[str, dict] = {}
        severity_stats: dict[str, int] = {}

        for row in ids:
            results = self.assess_record(entity_type, str(row["eid"]))
            if results:
                composite = self.compute_composite_score(results)
                scores.append(composite)

                for r in results:
                    if r.rule_name not in rule_stats:
                        rule_stats[r.rule_name] = {"passed": 0, "failed": 0, "avg_score": 0.0, "scores": []}
                    rule_stats[r.rule_name]["scores"].append(r.score)
                    if r.passed:
                        rule_stats[r.rule_name]["passed"] += 1
                    else:
                        rule_stats[r.rule_name]["failed"] += 1
                        severity_stats[r.severity] = severity_stats.get(r.severity, 0) + 1

        # Finalize averages
        for rn, rs in rule_stats.items():
            rs["avg_score"] = sum(rs["scores"]) / len(rs["scores"]) if rs["scores"] else 0.0
            del rs["scores"]

        avg = sum(scores) / len(scores) if scores else 0.0
        passing = sum(1 for s in scores if s >= self.config.pipeline.quality_warn_threshold)
        failing = len(scores) - passing

        return TableQualityReport(
            entity_type=entity_type,
            total_records=total,
            assessed_records=len(scores),
            avg_score=round(avg, 3),
            passing_count=passing,
            failing_count=failing,
            by_rule=rule_stats,
            by_severity=severity_stats,
        )

    def get_failing_records(self, entity_type: str, severity: str = "warning") -> list[dict]:
        """Get records with quality failures at or above given severity."""
        severity_order = {"info": 0, "warning": 1, "error": 2, "critical": 3}
        min_level = severity_order.get(severity, 1)

        rows = self.db.fetch_all(
            """
            SELECT DISTINCT dqr.entity_id, dqr.score, dqr.details,
                   dqr2.rule_name, dqr2.severity
            FROM data_quality_results dqr
            JOIN LATERAL (
                SELECT r.rule_name, r.severity
                FROM data_quality_rules r WHERE r.id = dqr.rule_id
            ) dqr2 ON TRUE
            WHERE dqr.entity_type = %s AND dqr.passed = FALSE
            ORDER BY dqr.score ASC
            """,
            [entity_type],
        )

        return [
            dict(r) for r in rows
            if severity_order.get(r.get("severity", "info"), 0) >= min_level
        ]

    @staticmethod
    def compute_composite_score(results: list[QualityResult]) -> float:
        """Weighted average across all rule results. Severity weights the importance."""
        if not results:
            return 1.0

        severity_weight = {"info": 0.5, "warning": 1.0, "error": 2.0, "critical": 3.0}
        total_weight = 0.0
        weighted_sum = 0.0

        for r in results:
            w = severity_weight.get(r.severity, 1.0)
            weighted_sum += r.score * w
            total_weight += w

        return round(weighted_sum / total_weight, 3) if total_weight > 0 else 1.0

    # ─── Rule evaluation ─────────────────────────

    def _evaluate_rule(self, rule: dict, record: dict, entity_type: str, entity_id: str) -> QualityResult:
        """Dispatch to the correct rule evaluator."""
        rule_type = rule["rule_type"]
        rule_config = rule["rule_config"] if isinstance(rule["rule_config"], dict) else json.loads(rule["rule_config"])

        evaluators = {
            "completeness": self._eval_completeness,
            "freshness": self._eval_freshness,
            "consistency": self._eval_consistency,
            "cross_source": self._eval_cross_source,
            "embedding_coverage": self._eval_embedding_coverage,
            "naming_consistency": self._eval_naming_consistency,
        }

        evaluator = evaluators.get(rule_type)
        if not evaluator:
            logger.warning("Unknown rule type: %s", rule_type)
            return QualityResult(
                rule_id=str(rule["id"]), rule_name=rule["rule_name"],
                rule_type=rule_type, severity=rule["severity"],
                passed=True, score=1.0, details={"skip": "unknown rule type"},
            )

        return evaluator(rule, rule_config, record, entity_type, entity_id)

    def _eval_completeness(self, rule, cfg, record, entity_type, entity_id) -> QualityResult:
        """Check what percentage of expected fields are non-NULL."""
        fields = cfg.get("fields", [])
        if not fields:
            return self._pass_result(rule, 1.0, {"fields": []})

        present = 0
        missing = []
        for f in fields:
            val = record.get(f)
            if val is not None and val != "" and val != []:
                present += 1
            else:
                missing.append(f)

        score = present / len(fields) if fields else 1.0
        threshold = cfg.get("threshold", 0.7)
        passed = score >= threshold

        return QualityResult(
            rule_id=str(rule["id"]), rule_name=rule["rule_name"],
            rule_type="completeness", severity=rule["severity"],
            passed=passed, score=round(score, 3),
            details={"missing_fields": missing, "total_fields": len(fields), "present": present},
        )

    def _eval_freshness(self, rule, cfg, record, entity_type, entity_id) -> QualityResult:
        """Check how recently the record was verified against its source."""
        max_age_days = cfg.get("max_age_days", self.config.pipeline.freshness_max_days)
        verified_at = record.get("last_verified_at") or record.get("retrieved_at")

        if verified_at is None:
            return QualityResult(
                rule_id=str(rule["id"]), rule_name=rule["rule_name"],
                rule_type="freshness", severity=rule["severity"],
                passed=False, score=0.0,
                details={"reason": "no verification timestamp"},
            )

        if isinstance(verified_at, str):
            try:
                verified_at = datetime.fromisoformat(verified_at)
            except ValueError:
                return self._pass_result(rule, 0.5, {"reason": "unparseable timestamp"})

        age = datetime.utcnow() - verified_at
        age_days = age.total_seconds() / 86400

        if age_days <= max_age_days:
            score = max(0.0, 1.0 - (age_days / max_age_days) * 0.5)
            return self._pass_result(rule, round(score, 3), {"age_days": round(age_days, 1), "max_age_days": max_age_days})
        else:
            score = max(0.0, 1.0 - age_days / (max_age_days * 2))
            return QualityResult(
                rule_id=str(rule["id"]), rule_name=rule["rule_name"],
                rule_type="freshness", severity=rule["severity"],
                passed=False, score=round(score, 3),
                details={"age_days": round(age_days, 1), "max_age_days": max_age_days},
            )

    def _eval_consistency(self, rule, cfg, record, entity_type, entity_id) -> QualityResult:
        """Check cross-field consistency (e.g., trial status vs completion_date)."""
        check = cfg.get("check", "")

        if check == "trial_status_date":
            status = (record.get("status") or "").lower()
            completion = record.get("completion_date")
            if status == "completed" and not completion:
                return QualityResult(
                    rule_id=str(rule["id"]), rule_name=rule["rule_name"],
                    rule_type="consistency", severity=rule["severity"],
                    passed=False, score=0.5,
                    details={"issue": "status is completed but completion_date is NULL"},
                )

        elif check == "drug_company_link":
            company_id = record.get("company_id")
            if not company_id:
                return QualityResult(
                    rule_id=str(rule["id"]), rule_name=rule["rule_name"],
                    rule_type="consistency", severity=rule["severity"],
                    passed=False, score=0.3,
                    details={"issue": "drug has no company_id linkage"},
                )

        elif check == "trial_drug_link":
            drug_id = record.get("drug_id")
            if not drug_id:
                return QualityResult(
                    rule_id=str(rule["id"]), rule_name=rule["rule_name"],
                    rule_type="consistency", severity=rule["severity"],
                    passed=False, score=0.3,
                    details={"issue": "trial has no drug_id linkage"},
                )

        elif check == "drug_ta_link":
            # Check if drug has a therapeutic area via FK or entity_links
            ta_id = record.get("therapeutic_area_id")
            has_ta = ta_id is not None
            if not has_ta:
                # Check entity_links for IN_THERAPEUTIC_AREA
                link = self.db.fetch_one(
                    """
                    SELECT id FROM entity_links
                    WHERE source_entity_id = %s AND link_type = 'IN_THERAPEUTIC_AREA'
                    LIMIT 1
                    """,
                    [entity_id],
                )
                has_ta = link is not None
            if not has_ta:
                return QualityResult(
                    rule_id=str(rule["id"]), rule_name=rule["rule_name"],
                    rule_type="consistency", severity=rule["severity"],
                    passed=False, score=0.3,
                    details={"issue": "drug has no therapeutic area linkage (FK or entity_links)"},
                )

        return self._pass_result(rule, 1.0, {"check": check})

    def _eval_cross_source(self, rule, cfg, record, entity_type, entity_id) -> QualityResult:
        """Check if entity is corroborated by multiple data sources."""
        min_sources = cfg.get("min_sources", 2)

        # Count distinct sources linking to this entity
        links = self.db.fetch_one(
            """
            SELECT count(DISTINCT provenance_source) as c
            FROM entity_links
            WHERE target_entity_id = %s OR source_entity_id = %s
            """,
            [entity_id, entity_id],
        )
        source_count = links["c"] if links else 0

        # Also check if the entity itself has an authoritative source
        source_api = record.get("source_api") or record.get("source_authority")
        if source_api:
            source_count = max(source_count, 1)

        score = min(1.0, source_count / min_sources)
        passed = source_count >= min_sources

        return QualityResult(
            rule_id=str(rule["id"]), rule_name=rule["rule_name"],
            rule_type="cross_source", severity=rule["severity"],
            passed=passed, score=round(score, 3),
            details={"source_count": source_count, "min_sources": min_sources},
        )

    def _eval_embedding_coverage(self, rule, cfg, record, entity_type, entity_id) -> QualityResult:
        """Check if the record has an embedding vector."""
        embedding_col = cfg.get("embedding_column", "molecule_embedding")
        val = record.get(embedding_col)
        has_embedding = val is not None

        return QualityResult(
            rule_id=str(rule["id"]), rule_name=rule["rule_name"],
            rule_type="embedding_coverage", severity=rule["severity"],
            passed=has_embedding, score=1.0 if has_embedding else 0.0,
            details={"embedding_column": embedding_col, "has_embedding": has_embedding},
        )

    def _eval_naming_consistency(self, rule, cfg, record, entity_type, entity_id) -> QualityResult:
        """Check that a column value belongs to an allowed set of canonical names."""
        column = cfg.get("column", "source_authority")
        allowed = set(cfg.get("allowed", []))
        value = record.get(column)

        if value is None:
            # NULL is acceptable (record may not have a source authority yet)
            return self._pass_result(rule, 0.5, {"column": column, "value": None, "reason": "NULL value"})

        if value in allowed:
            return self._pass_result(rule, 1.0, {"column": column, "value": value})

        return QualityResult(
            rule_id=str(rule["id"]), rule_name=rule["rule_name"],
            rule_type="naming_consistency", severity=rule["severity"],
            passed=False, score=0.0,
            details={"column": column, "value": value, "allowed": list(allowed)},
        )

    # ─── Helpers ─────────────────────────────────

    def _pass_result(self, rule, score, details) -> QualityResult:
        return QualityResult(
            rule_id=str(rule["id"]), rule_name=rule["rule_name"],
            rule_type=rule["rule_type"], severity=rule["severity"],
            passed=True, score=score, details=details,
        )

    def _persist_results(self, entity_type: str, entity_id: str, results: list[QualityResult]):
        """Write quality results to DB, replacing previous results for this entity."""
        # Clear old results for this entity
        self.db.execute(
            "DELETE FROM data_quality_results WHERE entity_type = %s AND entity_id = %s",
            [entity_type, entity_id],
        )
        for r in results:
            self.db.execute(
                """
                INSERT INTO data_quality_results
                    (entity_type, entity_id, rule_id, passed, score, details, assessed_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, NOW())
                """,
                [entity_type, entity_id, r.rule_id, r.passed, r.score, json.dumps(r.details)],
            )
