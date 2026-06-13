"""B1 (Helix §7.5) — per-source coverage+freshness for the answer path.

The closed-world honesty guard can only state limits ACCURATELY if it knows, per
source, how much data we hold, how fresh it is, and what that source may even
assert. This pins the DATA provider: it composes the #224 source-contract pack
(trust tier + may_emit) with the freshness SLA map + connector_health's flow
scorer, and surfaces empty/stale sources as explicit gaps (the G2 lever).

Lane-1, DB-free (mock db).
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from services.source_coverage import (
    load_source_contracts,
    summarize_source,
    source_coverage_summary,
    coverage_brief,
)

NOW = datetime(2026, 6, 13, tzinfo=timezone.utc)


def _dt(days_ago: float) -> datetime:
    from datetime import timedelta
    return NOW - timedelta(days=days_ago)


# ── contract loader ─────────────────────────────────────────────────────────

class TestLoadContracts:
    def test_loads_active_contracts_and_tier_ranks(self):
        contracts, tier_rank = load_source_contracts()
        assert "openfda_faers" in contracts
        assert contracts["openfda_faers"]["trust_tier"] == "registry_primary"
        # regulatory is the most authoritative tier
        assert tier_rank["regulatory_primary"] == 1
        assert tier_rank["trade_press"] == 4


# ── pure per-source cell ────────────────────────────────────────────────────

class TestSummarizeSource:
    def _faers_contract(self):
        return {"trust_tier": "registry_primary",
                "may_emit": [{"predicate": "adverse_event", "fact_class": "signal"}]}

    def test_fresh_source_is_green_and_carries_contract(self):
        cell = summarize_source(source="openfda_faers", table="adverse_events",
                                rows=2562, age_days=10.0, sla_days=14,
                                contract=self._faers_contract())
        assert cell["flow"] == "GREEN" and cell["fresh"] is True
        assert cell["trust_tier"] == "registry_primary"
        assert cell["may_emit"] == ["adverse_event"]
        assert cell["empty"] is False

    def test_empty_source_is_red_and_flagged(self):
        cell = summarize_source(source="nadac", table="drug_pricing",
                                rows=0, age_days=None, sla_days=14, contract=None)
        assert cell["flow"] == "RED" and cell["empty"] is True
        assert cell["trust_tier"] is None and cell["may_emit"] == []

    def test_stale_source_is_amber(self):
        cell = summarize_source(source="openfda_labels", table="drug_labels",
                                rows=191, age_days=20.0, sla_days=14, contract=None)
        assert cell["flow"] == "AMBER"   # stale but < 2x SLA


# ── DB-backed summary ───────────────────────────────────────────────────────

class TestSourceCoverageSummary:
    def _db(self, by_table):
        """by_table: {table_name: (rows, newest_datetime_or_None)}"""
        db = MagicMock()

        def fetch_one(sql, params=None):
            for table, (rows, newest) in by_table.items():
                if f"FROM {table}" in sql:
                    return {"n": rows, "newest": newest}
            return {"n": 0, "newest": None}

        db.fetch_one = MagicMock(side_effect=fetch_one)
        return db

    def test_one_row_per_sla_source_contract_enriched(self):
        from scheduler.config import FRESHNESS_SLA_DAYS
        db = self._db({"adverse_events": (2562, _dt(10)), "drug_pricing": (0, None)})
        summary = source_coverage_summary(db, now=NOW)
        assert len(summary) == len(FRESHNESS_SLA_DAYS)
        faers = next(c for c in summary if c["source"] == "openfda_faers")
        assert faers["trust_tier"] == "registry_primary"
        assert "adverse_event" in faers["may_emit"]
        assert faers["flow"] == "GREEN"

    def test_empty_source_surfaces_as_red(self):
        db = self._db({"drug_pricing": (0, None)})
        summary = source_coverage_summary(db, now=NOW)
        nadac = next(c for c in summary if c["table"] == "drug_pricing")
        assert nadac["empty"] is True and nadac["flow"] == "RED"

    def test_sorted_by_trust_tier_rank(self):
        db = self._db({})  # all sources empty
        summary = source_coverage_summary(db, now=NOW)
        ranks = [c["trust_tier"] for c in summary if c["trust_tier"]]
        # regulatory_primary (rank 1) must appear before trade_press (rank 4)
        if "regulatory_primary" in ranks and "trade_press" in ranks:
            assert ranks.index("regulatory_primary") < ranks.index("trade_press")

    def test_count_failure_is_isolated_not_fatal(self):
        db = MagicMock()
        db.fetch_one = MagicMock(side_effect=RuntimeError("no such table"))
        summary = source_coverage_summary(db, now=NOW)  # must not raise
        assert all(c["rows"] == 0 and c["flow"] == "RED" for c in summary)


# ── answer-path brief (the seam Platform's guard states verbatim) ───────────

class TestCoverageBrief:
    def test_brief_states_counts_and_flags_empties_as_gaps(self):
        summary = [
            summarize_source(source="clinicaltrials.gov", table="clinical_trials",
                             rows=5636, age_days=1.0, sla_days=2, contract=None),
            summarize_source(source="nadac", table="drug_pricing",
                             rows=0, age_days=None, sla_days=14, contract=None),
        ]
        brief = coverage_brief(summary)
        assert "5,636" in brief
        assert "nadac" in brief and "NO DATA" in brief   # honest limit stated

    def test_empty_summary_is_explicit(self):
        assert coverage_brief([]) == "Source coverage unavailable."
