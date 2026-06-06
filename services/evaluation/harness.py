"""EV-1 — the eval harness: run the SYSTEM's answer for each Forge gold item,
score it (services.evaluation.scorers), aggregate, and persist an eval run.

The flow, per gold item (a forge_eval_items row joined to its forge_rounds row
for the round payload):

  1. read the GOLD answer (the SME's constrained label).
  2. compute the SYSTEM answer for the SAME prompt:
       what_matters    → DecompositionPlanner dimensions for that compare's
                         playbook, ordered by weight (what the system says
                         matters).
       routing         → the playbook dimension's actual routes.
       signal_or_noise → the round's candidate signals re-ranked by the
                         materiality model (compute_materiality).
       critique        → whether grounded evidence for the graded cell still
                         exists (facts_as_of).
  3. score gold vs system (pure scorers) → verdict + precision/recall.
  4. aggregate accuracy / precision / recall / coverage per round-type and per
     playbook, and persist eval_runs + eval_results (migration 087).

Reuse, not duplication: the planner, the playbook registry, the materiality
scorer, and the Forge gold contract are CALLED, never reimplemented. No
fabricated numbers — every metric is computed from scored items.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from services.evaluation.scorers import (
    CORRECT,
    ItemScore,
    PARTIAL,
    SKIPPED,
    score_critique,
    score_routing,
    score_signal_or_noise,
    score_what_matters,
)

logger = logging.getLogger(__name__)

_ROUND_TYPES = ("what_matters", "routing", "signal_or_noise", "critique")


def _j(v: Any, default: Any) -> Any:
    """Coerce a JSONB column that may arrive as str under some drivers."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (TypeError, ValueError):
            return default
    return v if v is not None else default


@dataclass
class EvalRunSummary:
    """The aggregate result of one harness run — the scorecard's source."""

    run_key: str
    timestamp: str
    gold_count: int
    scored_count: int
    metrics: dict = field(default_factory=dict)   # overall + by_round_type + by_playbook
    results: list[dict] = field(default_factory=list)
    run_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "run_key": self.run_key,
            "timestamp": self.timestamp,
            "gold_count": self.gold_count,
            "scored_count": self.scored_count,
            "metrics": self.metrics,
        }


class EvalHarness:
    """Scores the system against the Forge gold set. Stateless; pass the db
    handle to run()."""

    def __init__(self, registry: Any = None) -> None:
        # Optional injected playbook registry (tests). Otherwise a db-backed one
        # is built per run so SME edits are reflected (mirrors the planner).
        self._registry = registry

    # ── public API ────────────────────────────────────────────────────────

    def run(
        self,
        db: Any,
        *,
        playbook_id: Optional[str] = None,
        persist: bool = True,
        created_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> EvalRunSummary:
        """Score every gold item (optionally filtered by playbook), aggregate,
        and (by default) persist the run. Returns an EvalRunSummary."""
        gold = self._load_gold(db, playbook_id=playbook_id)
        scored: list[dict] = []
        for item in gold:
            try:
                row = self._score_item(db, item)
            except Exception:
                logger.exception("eval: scoring failed for item %s", item.get("id"))
                continue
            if row is not None:
                scored.append(row)

        metrics = self._aggregate(scored)
        run_key = f"eval-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        summary = EvalRunSummary(
            run_key=run_key,
            timestamp=datetime.now(timezone.utc).isoformat(),
            gold_count=len(gold),
            scored_count=len(scored),
            metrics=metrics,
            results=scored,
        )
        if persist:
            summary.run_id = self._persist(db, summary, created_by=created_by, notes=notes)
        return summary

    def latest_summary(self, db: Any) -> Optional[dict]:
        """The most recent persisted eval run's stored summary (for the
        scorecard / GET /eval/summary). Returns None when no run exists."""
        row = db.fetch_one(
            "SELECT id, run_key, gold_count, scored_count, metrics, notes, created_at "
            "FROM eval_runs ORDER BY created_at DESC LIMIT 1"
        )
        if not row:
            return None
        return {
            "run_id": str(row["id"]),
            "run_key": row.get("run_key"),
            "gold_count": int(row.get("gold_count") or 0),
            "scored_count": int(row.get("scored_count") or 0),
            "metrics": _j(row.get("metrics"), {}),
            "notes": row.get("notes"),
            "timestamp": row["created_at"].isoformat() if row.get("created_at") else None,
        }

    def flagged_backlog(self, db: Any) -> dict:
        """The flagged-proposals backlog: gold items the Forge recorded as
        dissenting / not-yet-corroborated (consensus_state='flagged'). Surfaced
        on the scorecard alongside the scored gold set."""
        try:
            row = db.fetch_one(
                "SELECT COUNT(*) AS n FROM forge_eval_items "
                "WHERE consensus_state = 'flagged'"
            ) or {}
            by_pb = db.fetch_all(
                "SELECT playbook_id, COUNT(*) AS n FROM forge_eval_items "
                "WHERE consensus_state = 'flagged' GROUP BY playbook_id "
                "ORDER BY n DESC"
            ) or []
        except Exception:
            logger.debug("flagged_backlog read failed", exc_info=True)
            return {"flagged": 0, "by_playbook": []}
        return {
            "flagged": int(row.get("n") or 0),
            "by_playbook": [{"playbook_id": r.get("playbook_id"),
                             "count": int(r.get("n") or 0)} for r in by_pb],
        }

    # ── gold loading ────────────────────────────────────────────────────────

    def _load_gold(self, db: Any, *, playbook_id: Optional[str]) -> list[dict]:
        """Gold eval items joined to their round (for the round payload — the
        candidate signals / cell / dimension the system must answer against)."""
        where, params = ["1=1"], []
        if playbook_id:
            where.append("e.playbook_id = %s")
            params.append(playbook_id)
        rows = db.fetch_all(
            "SELECT e.id, e.round_id, e.session_id, e.playbook_id, e.intent, "
            "       e.prompt, e.answer, e.consensus_state, "
            "       r.round_type, r.payload "
            "FROM forge_eval_items e "
            "JOIN forge_rounds r ON r.id = e.round_id "
            "WHERE " + " AND ".join(where) +
            " ORDER BY e.created_at DESC",
            params,
        ) or []
        out = []
        for r in rows:
            out.append({
                "id": str(r.get("id")),
                "round_id": str(r.get("round_id")) if r.get("round_id") else None,
                "playbook_id": r.get("playbook_id"),
                "intent": r.get("intent"),
                "prompt": r.get("prompt"),
                "answer": _j(r.get("answer"), {}),
                "round_type": (r.get("round_type") or "what_matters").strip(),
                "payload": _j(r.get("payload"), {}),
            })
        return out

    # ── per-item scoring (compute system answer + score) ─────────────────────

    def _score_item(self, db: Any, item: dict) -> Optional[dict]:
        rt = item["round_type"]
        if rt == "what_matters":
            score = self._score_what_matters(db, item)
        elif rt == "routing":
            score = self._score_routing(db, item)
        elif rt == "signal_or_noise":
            score = self._score_signal_or_noise(db, item)
        elif rt == "critique":
            score = self._score_critique(db, item)
        else:
            return None
        return {
            "eval_item_id": item["id"],
            "round_type": rt,
            "playbook_id": item["playbook_id"],
            "verdict": score.verdict,
            "precision": score.precision,
            "recall": score.recall,
            "covered": score.covered,
            "detail": score.detail,
        }

    def _registry_for(self, db: Any) -> Any:
        if self._registry is not None:
            return self._registry
        from services.domain_intelligence.playbook import PlaybookRegistry, get_playbook_registry
        return PlaybookRegistry(db=db) if db is not None else get_playbook_registry()

    def _planner_dimensions(self, db: Any, item: dict) -> tuple[list[str], Optional[str]]:
        """The system's "what matters": the matching playbook's dimensions
        ordered by weight (highest first). Returns (dimension_keys, top_key)."""
        reg = self._registry_for(db)
        pb = reg.get(item["playbook_id"])
        if pb is None:
            # fall back: select by intent + the round's entity signature (two drugs)
            ents = (item.get("payload") or {}).get("entities") or []
            etypes = [(e.get("entity_type") or "drug") for e in ents] or ["drug", "drug"]
            pb = reg.select(item.get("intent") or "compare", etypes)
        if pb is None:
            return [], None
        dims = sorted(pb.dimensions, key=lambda d: float(d.weight or 0), reverse=True)
        keys = [d.key for d in dims]
        return keys, (keys[0] if keys else None)

    def _score_what_matters(self, db: Any, item: dict) -> ItemScore:
        ans = item["answer"] or {}
        gold = list(ans.get("ranking") or ans.get("selected") or [])
        sys_dims, sys_top = self._planner_dimensions(db, item)
        return score_what_matters(gold, sys_dims, system_top=sys_top)

    def _score_routing(self, db: Any, item: dict) -> ItemScore:
        ans = item["answer"] or {}
        gold_routes = list(ans.get("selected") or [])
        # the dimension the routing round edited: the round payload carries it;
        # the stored answer's consensus_key ("dim|r1,r2,...") is a fallback.
        dim_key = ((item.get("payload") or {}).get("dimension") or {}).get("key")
        if not dim_key:
            ck = str(ans.get("consensus_key") or "")
            dim_key = ck.split("|", 1)[0] if "|" in ck else ck
        sys_routes = self._playbook_routes(db, item["playbook_id"], dim_key)
        return score_routing(gold_routes, sys_routes)

    def _playbook_routes(self, db: Any, playbook_id: str, dim_key: str) -> list[str]:
        """The playbook dimension's routes as 'kind:value' strings (the system's
        'where does the answer live')."""
        reg = self._registry_for(db)
        pb = reg.get(playbook_id)
        if pb is None or not dim_key:
            return []
        for d in pb.dimensions:
            if d.key == dim_key:
                return [f"{r.kind}:{r.value}" for r in d.routes]
        return []

    def _score_signal_or_noise(self, db: Any, item: dict) -> ItemScore:
        ans = item["answer"] or {}
        gold_signal = str(ans.get("signal_id") or "")
        candidates = (item.get("payload") or {}).get("signals") or []
        ranked = self._rank_signals_by_materiality(db, candidates)
        return score_signal_or_noise(gold_signal, ranked)

    def _rank_signals_by_materiality(self, db: Any, candidates: list[dict]) -> list[str]:
        """Re-rank the round's candidate signals by the materiality model. The
        candidates carry kbq_tags + impact_tier (from the round payload); we
        derive scorer inputs and order by computed score, highest first."""
        if not candidates:
            return []
        from services.materiality import (
            compute_materiality,
            get_active_config,
            kbq_tags_to_claim_type,
        )
        cfg = get_active_config(db)
        scored: list[tuple[float, str]] = []
        for s in candidates:
            sid = str(s.get("signal_id") or "")
            if not sid:
                continue
            claim_type = kbq_tags_to_claim_type(s.get("kbq_tags"))
            # criticality proxy: impact_tier 'high' → focal, else 'other'.
            crit = "focal" if (str(s.get("impact_tier") or "").lower() == "high") else "other"
            result = compute_materiality(
                source_tier=None, entity_criticality=crit,
                claim_type=claim_type, age_days=0.0, config=cfg,
            )
            scored.append((result.score, sid))
        # stable highest-first ordering
        scored.sort(key=lambda t: t[0], reverse=True)
        return [sid for _, sid in scored]

    def _score_critique(self, db: Any, item: dict) -> ItemScore:
        ans = item["answer"] or {}
        gold_grade = str(ans.get("grade") or "")
        cell = (item.get("payload") or {}).get("cell") or {}
        grounded = self._cell_grounded(db, cell)
        return score_critique(gold_grade, grounded)

    def _cell_grounded(self, db: Any, cell: dict) -> bool:
        """Does grounded evidence for the graded cell still exist? The cell came
        from a real ledger fact; the system still 'asserts' it iff a fact with
        that predicate exists for the entity (facts_as_of)."""
        eid = cell.get("entity_id")
        predicate = cell.get("predicate")
        if not eid or not predicate:
            # last resort: the fact row itself still exists
            fid = cell.get("fact_id")
            if not fid:
                return False
            try:
                row = db.fetch_one(
                    "SELECT 1 FROM facts WHERE id::text = %s "
                    "AND (record_status IS NULL OR record_status <> 'superseded') LIMIT 1",
                    [str(fid)],
                )
                return bool(row)
            except Exception:
                return False
        try:
            from services.facts_ledger import facts_as_of
            rows = facts_as_of(db, "drug", str(eid), predicate=str(predicate))
            return bool(rows)
        except Exception:
            logger.debug("cell_grounded: facts_as_of failed", exc_info=True)
            return False

    # ── aggregation ───────────────────────────────────────────────────────

    def _aggregate(self, scored: list[dict]) -> dict:
        """Accuracy / precision / recall / coverage, overall + per round-type +
        per playbook. Each metric traces to the scored items (no fabrication).

        - accuracy = mean accuracy_credit over NON-skipped items (correct=1,
          partial=0.5, miss=0).
        - precision / recall = mean over items that carry them (routing /
          what_matters set answers).
        - coverage = fraction of items for which the system produced ANY answer.
        """
        overall = self._metrics_for(scored)
        by_rt = {
            rt: self._metrics_for([s for s in scored if s["round_type"] == rt])
            for rt in _ROUND_TYPES
            if any(s["round_type"] == rt for s in scored)
        }
        playbooks = sorted({s["playbook_id"] for s in scored})
        by_pb = {
            pb: self._metrics_for([s for s in scored if s["playbook_id"] == pb])
            for pb in playbooks
        }
        return {"overall": overall, "by_round_type": by_rt, "by_playbook": by_pb}

    @staticmethod
    def _metrics_for(items: list[dict]) -> dict:
        n = len(items)
        if n == 0:
            return {"n": 0, "accuracy": 0.0, "precision": None, "recall": None,
                    "coverage": 0.0, "correct": 0, "partial": 0, "miss": 0,
                    "skipped": 0}
        non_skipped = [s for s in items if s["verdict"] != SKIPPED]
        correct = sum(1 for s in items if s["verdict"] == CORRECT)
        partial = sum(1 for s in items if s["verdict"] == PARTIAL)
        skipped = sum(1 for s in items if s["verdict"] == SKIPPED)
        miss = len(non_skipped) - correct - partial

        def _credit(v: str) -> float:
            return 1.0 if v == CORRECT else (0.5 if v == PARTIAL else 0.0)

        accuracy = (sum(_credit(s["verdict"]) for s in non_skipped) / len(non_skipped)
                    if non_skipped else 0.0)
        precs = [s["precision"] for s in items if s.get("precision") is not None]
        recs = [s["recall"] for s in items if s.get("recall") is not None]
        coverage = sum(1 for s in items if s.get("covered")) / n
        return {
            "n": n,
            "accuracy": round(accuracy, 4),
            "precision": round(sum(precs) / len(precs), 4) if precs else None,
            "recall": round(sum(recs) / len(recs), 4) if recs else None,
            "coverage": round(coverage, 4),
            "correct": correct,
            "partial": partial,
            "miss": miss,
            "skipped": skipped,
        }

    # ── persistence ─────────────────────────────────────────────────────────

    def _persist(self, db: Any, summary: EvalRunSummary, *,
                 created_by: Optional[str], notes: Optional[str]) -> Optional[str]:
        run = db.fetch_one(
            "INSERT INTO eval_runs (run_key, gold_count, scored_count, metrics, "
            "                       notes, created_by) "
            "VALUES (%s, %s, %s, %s::jsonb, %s, %s) "
            "ON CONFLICT (run_key) DO NOTHING "
            "RETURNING id",
            [summary.run_key, summary.gold_count, summary.scored_count,
             json.dumps(summary.metrics), notes, created_by],
        )
        if not run:
            # run_key collision (same-second re-run) — read the existing id.
            run = db.fetch_one("SELECT id FROM eval_runs WHERE run_key = %s",
                               [summary.run_key])
        run_id = str(run["id"]) if run else None
        if run_id:
            for s in summary.results:
                db.execute(
                    "INSERT INTO eval_results (run_id, eval_item_id, round_type, "
                    "    playbook_id, verdict, precision, recall, detail) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
                    [run_id, s["eval_item_id"], s["round_type"], s["playbook_id"],
                     s["verdict"], s.get("precision"), s.get("recall"),
                     json.dumps(s.get("detail") or {})],
                )
        return run_id
