"""B1 (Helix §7.5 data-team eval loop) — per-source coverage + freshness for the
ANSWER PATH.

The closed-world honesty guard (Platform, A1) can only state a limit ACCURATELY
if it knows, per source: how much data we hold, how fresh it is, and what that
source is even allowed to assert. Today that's spread across three governed
pieces — the #224 source-contract pack (trust tier + ``may_emit``), the
``FRESHNESS_SLA_DAYS`` table/SLA map, and ``connector_health``'s pure flow scorer
— none of which reaches the synthesis prompt. This composes them into one
answer-path summary + a compact brief, so the guard says "NADAC: NO DATA" instead
of vaguely hedging (the G2 honesty lever).

This is the DATA half of B1: a read-only reporting lens (no migration, never the
source of truth for ingestion). Platform wires ``coverage_brief`` into the guard
prompt — that is the seam (announced in COORDINATION §6).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import yaml

from scheduler.config import FRESHNESS_SLA_DAYS
# Reuse Platform's PURE scorers (scripts/connector_health.py is Platform-owned —
# imported, never refactored here).
from scripts.connector_health import score_flow, _age_days

logger = logging.getLogger(__name__)

_PACK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "domain", "pharma", "packs", "pharma_source_contracts.yaml",
)


def load_source_contracts() -> tuple[dict, dict]:
    """Returns ({source_key: active_contract}, {trust_tier: rank}). Source keys
    are ``SourceType.value`` (so they join the freshness SLA map). Degrades to
    ({}, {}) on any read/parse error — coverage then runs freshness-only and the
    answer path still gets accurate counts, never an exception."""
    try:
        with open(_PACK, encoding="utf-8") as fh:
            pack = yaml.safe_load(fh) or {}
    except Exception:
        logger.warning("source-contract pack unreadable; coverage runs freshness-only",
                       exc_info=True)
        return {}, {}
    contracts = {k: v for k, v in (pack.get("source_contracts") or {}).items()
                 if isinstance(v, dict) and v.get("status") == "active"}
    tier_rank = {t: (info or {}).get("rank", 9)
                 for t, info in (pack.get("trust_tiers") or {}).items()}
    return contracts, tier_rank


def summarize_source(*, source: str, table: str, rows: int,
                     age_days: Optional[float], sla_days: int,
                     contract: Optional[dict]) -> dict:
    """Pure per-source coverage cell (DB-free, testable). ``flow`` reuses
    connector_health's GREEN/AMBER/RED scorer; contract fields are None/[] when
    the source is ungoverned (still reported — an ungoverned source is itself a
    fact the guard should see)."""
    flow = score_flow(rows, age_days, sla_days)
    c = contract or {}
    return {
        "source": source,
        "table": table,
        "rows": rows,
        "age_days": age_days,
        "sla_days": sla_days,
        "flow": flow,                       # GREEN | AMBER | RED
        "trust_tier": c.get("trust_tier"),  # None if ungoverned
        "may_emit": [e["predicate"] for e in c.get("may_emit", [])
                     if isinstance(e, dict) and e.get("predicate")],
        "fresh": flow == "GREEN",
        "empty": rows == 0,
    }


_COUNT_SQL = "SELECT count(*) AS n, max({col}) AS newest FROM {table}"


def source_coverage_summary(db, *, now: Optional[datetime] = None) -> list[dict]:
    """Per-source coverage+freshness across every source with a freshness SLA,
    enriched with its source contract, sorted by trust-tier rank then source.

    Each per-source count is isolated: a missing/locked table is logged and
    treated as 0 rows (RED), never blanking the whole summary — conservation
    (no silent total failure)."""
    now = now or datetime.now(timezone.utc)
    contracts, tier_rank = load_source_contracts()
    out: list[dict] = []
    for source_type, (table, recency_col, sla_days) in FRESHNESS_SLA_DAYS.items():
        rows, newest = 0, None
        try:
            r = db.fetch_one(_COUNT_SQL.format(col=recency_col, table=table))
            if r:
                rows, newest = int(r.get("n") or 0), r.get("newest")
        except Exception:
            logger.warning("coverage: count failed for %s (%s)",
                           source_type, table, exc_info=True)
        out.append(summarize_source(
            source=source_type.value, table=table, rows=rows,
            age_days=_age_days(newest, now), sla_days=sla_days,
            contract=contracts.get(source_type.value),
        ))
    out.sort(key=lambda c: (tier_rank.get(c["trust_tier"], 9), c["source"]))
    return out


def coverage_brief(summary: list[dict]) -> str:
    """Compact, answer-path string the closed-world guard can state verbatim, so
    limits are ACCURATE not vague. Empty sources surfaced first as explicit gaps
    ("NADAC: NO DATA") — the data half of the G2 honesty lever."""
    if not summary:
        return "Source coverage unavailable."

    def _one(c: dict) -> str:
        if c["empty"]:
            return f"{c['source']}: NO DATA (0 rows) [RED]"
        age = f"{c['age_days']:.0f}d" if c["age_days"] is not None else "no recency"
        return f"{c['source']}: {c['rows']:,} rows, {age} [{c['flow']}]"

    # gaps (empty, then non-green) first so the guard leads with limits
    ordered = sorted(summary, key=lambda c: (not c["empty"], c["flow"] == "GREEN"))
    return "Source coverage (probe): " + "; ".join(_one(c) for c in ordered) + "."
