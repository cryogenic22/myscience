"""Schema-completeness regression net (data squad).

Two layers:

1. **Pure / config invariants** (always run, no DB): every fact-emitter predicate
   that should surface must be mapped in BOTH _PREDICATE_DOMAIN (to a specific
   ZS domain, not the wargame_specific fallback) AND _PREDICATE_KBQ. This is the
   "a fact can exist and still be invisible" guard (target_activity was the
   exemplar — in DOMAIN but missing from KBQ).

2. **Live-DB invariants** (run only when DATABASE_URL is set): every scheduled
   connector's target table is populated and within its freshness SLA;
   FK-orphan shares stay under documented thresholds; the fact ledger carries
   evidence above a floor. This is the regression net for the D1–D4 fixes —
   if a connector silently dies again, or a linkage regresses, these fail.

Live tests are skipped (not failed) without DATABASE_URL so the unit suite stays
DB-free. Run the live net with:
    DATABASE_URL=<railway url> python -m pytest tests/test_schema_completeness.py -v
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from scheduler.config import FRESHNESS_SLA_DAYS
from services.dossier_kb import _PREDICATE_DOMAIN, route_predicate_to_domain
from services.kbq_views import _PREDICATE_KBQ

# Emitter predicates that MUST be visible in a dossier + a KBQ. (Excludes the
# generic "market_event" catch-all and regulatory_* event predicates, which are
# intentionally routed to a strategic domain and kept out of the KBQ surface to
# avoid flooding it with recall/shortage noise — see _PREDICATE_KBQ docstring.)
SURFACEABLE_EMITTER_PREDICATES = {
    "clinical_trial",
    "adverse_event",
    "label_indication",
    "safety_signal",
    "mechanism_of_action",
    "target_activity",
    "key_publication",
    "disease_evidence",
    "trial_result",
    "competitor",
    "product_sales",
}

# Documented FK-orphan ceilings (NULL-fk share). Set just above the verified
# post-fix levels so a real regression trips them but normal drift doesn't.
ORPHAN_CEILINGS = {
    "pubmed_articles.drug_id": 0.30,        # post-D4 ~15%
    "market_events.primary_entity_id": 0.45,  # post-D2 ~29%
    "bioactivities.drug_id": 0.95,          # legacy unlinked rows remain; new rows link
    "clinical_trials.drug_id": 0.15,
    "adverse_events.drug_id": 0.10,
    "facts.source_doc_id": 0.10,            # D5 done — backfilled to ~0% NULL
}


# ───────────────────────── pure / config invariants ─────────────────────────

@pytest.mark.parametrize("predicate", sorted(SURFACEABLE_EMITTER_PREDICATES))
def test_predicate_routes_to_specific_domain(predicate):
    """Every surfaceable emitter predicate maps to a real ZS domain (not the
    wargame_specific fallback that means 'unmapped')."""
    domain = route_predicate_to_domain(predicate)
    assert domain != "wargame_specific", f"{predicate} falls through to the fallback domain"
    assert predicate in _PREDICATE_DOMAIN or domain, predicate


@pytest.mark.parametrize("predicate", sorted(SURFACEABLE_EMITTER_PREDICATES))
def test_predicate_mapped_in_kbq(predicate):
    """A fact can exist and still be invisible: every surfaceable predicate must
    also be in _PREDICATE_KBQ (the dossier-vs-KBQ double-mapping rule)."""
    assert predicate in _PREDICATE_KBQ, (
        f"{predicate} is routed to a dossier domain but missing from _PREDICATE_KBQ "
        f"— it would never appear in the KBQ surface"
    )


def test_every_scheduled_source_has_an_sla():
    """Every source with a freshness SLA names a target table + recency column."""
    for source, (table, col, days) in FRESHNESS_SLA_DAYS.items():
        assert table and col and days > 0, source


# ─────────────────────────── live-DB invariants ───────────────────────────

DB_URL = os.environ.get("DATABASE_URL")
live = pytest.mark.skipif(not DB_URL, reason="DATABASE_URL not set — live schema gate skipped")


@pytest.fixture(scope="module")
def conn():
    import psycopg2

    c = psycopg2.connect(DB_URL)
    yield c
    c.close()


def _scalar(conn, sql, params=None):
    cur = conn.cursor()
    try:
        cur.execute(sql, params or [])
        return cur.fetchone()
    finally:
        conn.rollback()


@live
@pytest.mark.parametrize("source", sorted(FRESHNESS_SLA_DAYS, key=lambda s: s.value))
def test_scheduled_source_populated_and_fresh(conn, source):
    """No scheduled connector has 0 rows, and its newest row is within SLA.

    PMC/patents/pricing may legitimately stay out — documented exceptions below.
    """
    table, recency_col, sla_days = FRESHNESS_SLA_DAYS[source]
    row = _scalar(conn, f"SELECT count(*) n, max({recency_col}) newest FROM {table}")
    n, newest = row
    # Documented exceptions: sources with no source data yet (tracked in
    # SPEC_DATA_001 D8 / no-source notes). Asserting >0 here would be a false red.
    no_source_yet = {"nadac", "open_targets", "pubchem"}
    if source.value in no_source_yet:
        pytest.skip(f"{source.value}: no source wired yet (D8 / deferred)")
    assert n > 0, f"{source.value} target table {table} is EMPTY"
    assert newest is not None, f"{source.value}: no recency timestamp"
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - newest).days
    assert age <= sla_days, f"{source.value}: {table} newest is {age}d old (SLA {sla_days}d)"


@live
@pytest.mark.parametrize("label", sorted(ORPHAN_CEILINGS))
def test_fk_orphan_share_under_ceiling(conn, label):
    """FK-orphan shares stay under documented thresholds (regression net for
    D2/D3/D4 linkage)."""
    table, col = label.split(".")
    where = "WHERE superseded_by IS NULL" if table == "facts" else ""
    n, total = _scalar(
        conn,
        f"SELECT count(*) FILTER (WHERE {col} IS NULL), count(*) FROM {table} {where}",
    )
    if total == 0:
        pytest.skip(f"{label}: table empty")
    share = n / total
    ceiling = ORPHAN_CEILINGS[label]
    assert share <= ceiling, f"{label} orphan share {share:.1%} exceeds ceiling {ceiling:.0%}"


@live
def test_fact_ledger_has_evidence_floor(conn):
    """A meaningful share of ledger facts carry an evidence link (source_doc_id),
    so the dossier can drill through. Floor raised to 0.90 after the D5 backfill
    (scripts/backfill_evidence.py) — live NULL share is ~0%."""
    n_null, total = _scalar(
        conn,
        "SELECT count(*) FILTER (WHERE source_doc_id IS NULL), count(*) "
        "FROM facts WHERE superseded_by IS NULL",
    )
    if total == 0:
        pytest.skip("ledger empty")
    with_evidence = 1 - (n_null / total)
    assert with_evidence >= 0.90, f"only {with_evidence:.0%} of facts have evidence links"


@live
def test_emitted_predicates_are_all_routable(conn):
    """Every predicate actually present in the live ledger routes to a domain
    (total function guard — none silently dropped)."""
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT predicate FROM facts WHERE superseded_by IS NULL")
    preds = [r[0] for r in cur.fetchall()]
    conn.rollback()
    for p in preds:
        assert route_predicate_to_domain(p), f"predicate {p} did not route"
