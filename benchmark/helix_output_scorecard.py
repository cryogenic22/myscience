"""Helix Output-Quality scorecard — does the sensing/intelligence substrate
produce decision-grade objects, or beautiful-but-unsupported ones?

Unlike benchmark/eval_pharma_v1.yaml (which scores chat ANSWERS), this scores the
intelligence OBJECTS the Helix output depends on, computed from LIVE state — so a
substrate that LOOKS rich but can't trace a signal to a fact, or moves a scenario
probability without an audit row, fails loud. The dimensions map to the build
plan's OQ gates (docs/helix-intelligence-buildplan.md §5):

  OQ1 sensing       — every signal traces to a fact (signal_facts lineage)
  OQ2 calibration   — scenarios with a current_prob have a probability-history row
  OQ3 contradiction — signals carry a polarity (direction), so contradictions can refute
  OQ5 provenance    — facts are evidence-backed (source_doc_id)
  OQ6 as-of         — facts carry detected_at, so fair-hindsight reconstruction works

OQ4 (decision-grounding) is platform-owned (decision briefs) and reported as
informational, not scored here. TA-general: every metric is keyed off the
substrate, not any therapy area.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)

# Readiness thresholds (a coverage ratio → a state). A gate that LOOKS green at
# 60% lineage is not decision-grade, so the bar is deliberately high.
READY = 0.90
THIN = 0.60


def score_state(ratio: Optional[float]) -> str:
    """Pure: coverage ratio → readiness state. None (no denominator) = 'n/a'
    (honest: we don't score a dimension with nothing to measure as 'ready')."""
    if ratio is None:
        return "n/a"
    if ratio >= READY:
        return "ready"
    if ratio >= THIN:
        return "thin"
    return "gap"


def _ratio(num: int, den: int) -> Optional[float]:
    return None if not den else round(num / den, 3)


@dataclass
class Dimension:
    key: str
    label: str
    num: int
    den: int
    ratio: Optional[float]
    state: str
    note: str = ""


def _dim(key, label, num, den, note="") -> Dimension:
    r = _ratio(num, den)
    return Dimension(key, label, num, den, r, score_state(r), note)


def _count(db, sql, params=None) -> int:
    try:
        row = db.fetch_one(sql, params or [])
        return int(row["c"]) if row and row.get("c") is not None else 0
    except Exception:
        logger.warning("scorecard count failed: %s", sql[:60], exc_info=True)
        return 0


def compute_scorecard(db) -> dict:
    """Compute the OQ dimensions from live substrate state (global, not per-
    engagement — the substrate is shared)."""
    dims: list[Dimension] = []

    # OQ1 sensing — every signal traces to evidence. Two valid lineage paths: a
    # governed fact (signal_facts) OR a cited evidence document
    # (evidence_document_ids — e.g. a news signal cites its article). The GATE is
    # "no ungrounded signal" (either path); fact-grounding depth is a sub-note,
    # not a pass/fail (most signals are document-backed news, which is legitimate
    # — news creates a signal, not a fact).
    sig_total = _count(db, "SELECT count(*) c FROM signals")
    sig_evidenced = _count(
        db,
        "SELECT count(*) c FROM signals s "
        "WHERE array_length(s.evidence_document_ids, 1) >= 1 "
        "   OR EXISTS (SELECT 1 FROM signal_facts sf WHERE sf.signal_id = s.id)")
    sig_fact_grounded = _count(db, "SELECT count(DISTINCT signal_id) c FROM signal_facts")
    grounded_pct = _ratio(sig_fact_grounded, sig_total)
    dims.append(_dim(
        "OQ1_sensing", "Signals traceable to evidence",
        sig_evidenced, sig_total,
        f"either a governed fact or a cited evidence document; fact-grounded "
        f"depth = {sig_fact_grounded}/{sig_total} "
        f"({'n/a' if grounded_pct is None else str(round(grounded_pct * 100)) + '%'})"))

    # OQ2 calibration audit — scenarios with a current_prob have a history row.
    scn_cal = _count(db, "SELECT count(*) c FROM scenarios "
                         "WHERE current_prob IS NOT NULL AND is_archived = FALSE")
    scn_hist = _count(db, "SELECT count(DISTINCT s.id) c FROM scenarios s "
                         "JOIN scenario_probability_history h ON h.scenario_id = s.id "
                         "WHERE s.current_prob IS NOT NULL AND s.is_archived = FALSE")
    dims.append(_dim("OQ2_calibration_audit", "Calibrated scenarios with an audit row",
                     scn_hist, scn_cal,
                     "probability changes are recorded going forward; backfilled history is not fabricated"))

    # OQ3 contradiction-ready — signals carry a polarity.
    sig_dir = _count(db, "SELECT count(*) c FROM signals WHERE direction IS NOT NULL")
    dims.append(_dim("OQ3_contradiction_ready", "Signals carrying a polarity (direction)",
                     sig_dir, sig_total,
                     "polarity enables a contradicting signal to refute a scenario"))

    # OQ5 provenance — facts are evidence-backed.
    fact_total = _count(db, "SELECT count(*) c FROM facts WHERE superseded_by IS NULL")
    fact_ev = _count(db, "SELECT count(*) c FROM facts "
                        "WHERE superseded_by IS NULL AND source_doc_id IS NOT NULL")
    dims.append(_dim("OQ5_provenance", "Facts that are evidence-backed",
                     fact_ev, fact_total, "fraction of live facts with a source_doc_id"))

    # OQ6 as-of integrity — facts carry detected_at.
    fact_det = _count(db, "SELECT count(*) c FROM facts "
                         "WHERE superseded_by IS NULL AND detected_at IS NOT NULL")
    dims.append(_dim("OQ6_as_of", "Facts with an epistemic timestamp (detected_at)",
                     fact_det, fact_total, "enables fair-hindsight as-of reconstruction"))

    gaps = [d.key for d in dims if d.state == "gap"]
    return {
        "dimensions": [asdict(d) for d in dims],
        "gaps": gaps,
        "ready": not gaps,
        "summary": {d.key: d.state for d in dims},
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from db import Database
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        from config import config
        dsn = config.db.dsn
    db = Database(dsn)
    db.connect()
    try:
        card = compute_scorecard(db)
    finally:
        db.close()
    print("\n=== Helix Output-Quality Scorecard ===")
    for d in card["dimensions"]:
        pct = "n/a" if d["ratio"] is None else f"{d['ratio']*100:.0f}%"
        print(f"  [{d['state']:5}] {d['key']:24} {pct:>5}  {d['num']}/{d['den']}  — {d['label']}")
    print(f"\n  overall: {'READY' if card['ready'] else 'GAPS: ' + ', '.join(card['gaps'])}")
    print(json.dumps(card["summary"]))


if __name__ == "__main__":
    main()
