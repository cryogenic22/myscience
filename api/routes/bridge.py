"""Loop #17 — Helix Bridge endpoints.

`POST /bridge/moments` synthesises Moment objects from top-tier
signals, calling `services/llm.py::LLMSynthesizer` to produce the
serif headline + summary. Falls back to a deterministic synthesis
(signal headline echo) if the LLM is disabled or fails.

Spec: `specs/raw_helix.md` §3.4 + `specs/SPEC_LOOP_17_helix_bridge.md`.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_db, get_llm
from db import Database
from services.llm import LLMSynthesizer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bridge", tags=["bridge"])


# ── Moment categories preserved from the prototype taxonomy ──
_CATEGORY_LABELS = {
    "financial":  "Financial",
    "governance": "Governance",
    "strategic":  "Strategic",
    "clinical":   "Clinical",
    "product":    "Product",
    "regulatory": "Regulatory",
    "ma":         "M&A",
    "access":     "Pricing & Access",
    "ai":         "AI & Digital",
    "esg":        "ESG & Supply",
}

_DEFAULT_PLAYS_TEMPLATE = [
    {"kind": "aggressive", "label": "Lean in — accelerate the response",     "prob_success": 0.55, "ev_var_factor": 0.4},
    {"kind": "balanced",   "label": "Stage the response — wait for confirm", "prob_success": 0.74, "ev_var_factor": 0.2},
    {"kind": "cautious",   "label": "Hold and observe",                       "prob_success": 0.85, "ev_var_factor": 0.1},
]


class MomentsRequest(BaseModel):
    n: int = Field(default=3, ge=1, le=5)
    since_days: int = Field(default=7, ge=1, le=90)


def _moment_id(*, category: str, signal_ids: list[str]) -> str:
    """Stable id from (category + signal_ids) so re-requests are idempotent."""
    h = hashlib.sha1(("|".join([category, *signal_ids])).encode("utf-8")).hexdigest()
    return f"m-{h[:10]}"


def _ev_from_signals(signals: list[dict]) -> int:
    """Crude EV proxy = sum(impact_score) × $50M. Real EV lands via BE-52."""
    total = sum(float(s.get("impact_score") or 0) for s in signals)
    return int(round(total * 50))


def _expiry_hours(signals: list[dict]) -> int:
    """Most-urgent signal drives the clock. Default 72h."""
    top = max((float(s.get("impact_score") or 0) for s in signals), default=0.0)
    if top >= 9.0:
        return 48
    if top >= 7.0:
        return 168  # 1 week
    return 336  # 2 weeks


def _delta_belief(signals: list[dict]) -> dict:
    """Toy belief shift: avg impact_score → 0–1 posterior magnitude."""
    if not signals:
        return {"from": 0.5, "to": 0.5, "label": "P(material event in horizon)"}
    avg = sum(float(s.get("impact_score") or 0) for s in signals) / len(signals)
    posterior = min(0.95, 0.3 + (avg / 10.0) * 0.6)
    return {
        "from": round(max(0.0, posterior - 0.25), 2),
        "to":   round(posterior, 2),
        "label": "P(material event in horizon)",
    }


def _llm_synthesize_moment(
    *, category: str, signals: list[dict], llm: LLMSynthesizer
) -> tuple[str, str]:
    """Return (title, summary) — LLM if available, deterministic otherwise."""
    if not llm.enabled or not signals:
        # Deterministic fallback: serif-friendly headline from top signal.
        top = signals[0] if signals else {}
        title = (
            f"{_CATEGORY_LABELS.get(category, category.title())} moment: "
            f"{(top.get('headline') or 'Signals cluster forming')}"
        )
        summary = top.get("summary") or (
            f"{len(signals)} signal(s) jointly raise the materiality "
            f"on this {category} thread."
        )
        return title, summary

    # LLM path — keep prompt short, structured. Asks for two short fields.
    signal_text = "\n".join(
        f"- ({s.get('primary_entity_name') or 'system'}) "
        f"{(s.get('headline') or '')[:200]}: {(s.get('summary') or '')[:240]}"
        for s in signals[:5]
    )
    prompt = (
        "You are a pharma competitive-intelligence analyst. From the "
        "following signals, write a single strategic 'Moment' that an "
        "executive would read in 30 seconds. "
        "Output exactly two lines:\n"
        "TITLE: <one declarative serif-style sentence, 8-14 words>\n"
        "SUMMARY: <one sentence, 16-28 words, naming the strategic "
        "implication>\n\n"
        f"Category: {_CATEGORY_LABELS.get(category, category)}\n"
        f"Signals:\n{signal_text}\n"
    )
    try:
        raw = llm.synthesize(prompt) if hasattr(llm, "synthesize") else ""
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("empty LLM response")
        title_line = next((l for l in raw.splitlines() if l.lower().startswith("title:")), "")
        summary_line = next((l for l in raw.splitlines() if l.lower().startswith("summary:")), "")
        title = title_line.split(":", 1)[1].strip() if ":" in title_line else ""
        summary = summary_line.split(":", 1)[1].strip() if ":" in summary_line else ""
        if not title or not summary:
            raise ValueError("could not parse TITLE / SUMMARY")
        return title, summary
    except Exception:
        logger.exception("bridge moment LLM synth failed; falling back")
        return _llm_synthesize_moment(
            category=category, signals=signals, llm=_DisabledLLM()
        )


class _DisabledLLM:
    enabled = False
    def synthesize(self, *args, **kwargs):
        raise RuntimeError("disabled")


def _make_moment(*, category: str, signals: list[dict], llm: LLMSynthesizer, priority: int) -> dict:
    title, summary = _llm_synthesize_moment(category=category, signals=signals, llm=llm)
    signal_ids = [str(s.get("id")) for s in signals if s.get("id")]
    ev = _ev_from_signals(signals)

    plays = []
    for i, tmpl in enumerate(_DEFAULT_PLAYS_TEMPLATE):
        play_ev = int(round(ev * (1.1 if tmpl["kind"] == "aggressive" else 0.7 if tmpl["kind"] == "balanced" else 0.4)))
        plays.append({
            "id": f"p-{priority}-{i}",
            "label": tmpl["label"],
            "ev": play_ev,
            "ev_var": int(round(play_ev * tmpl["ev_var_factor"])),
            "prob_success": tmpl["prob_success"],
            "kind": tmpl["kind"],
        })

    return {
        "id":               _moment_id(category=category, signal_ids=signal_ids),
        "priority":         priority,
        "ev_at_stake_musd": ev,
        "expires_hours":    _expiry_hours(signals),
        "title":            title,
        "summary":          summary,
        "delta_belief":     _delta_belief(signals),
        "signal_chain":     signal_ids,
        "category":         category,
        "plays":            plays,
    }


@router.post("/moments")
def synthesise_moments(
    body: MomentsRequest,
    db: Database = Depends(get_db),
    llm: LLMSynthesizer = Depends(get_llm),
) -> dict:
    """Synthesise up to `n` Moments from top tier-1 signals."""
    try:
        rows = db.fetch_all(
            """
            SELECT id, headline, summary, kbq_tags, impact_tier, impact_score,
                   primary_entity_name, created_at
              FROM signals
             WHERE impact_tier IN ('high', 'medium')
               AND created_at > NOW() - INTERVAL %s
             ORDER BY impact_score DESC NULLS LAST, created_at DESC
             LIMIT 30
            """,
            [f"{body.since_days} days"],
        ) or []
    except Exception:
        logger.exception("bridge.moments signal pull failed")
        rows = []

    if not rows:
        return {"moments": []}

    # Group by first kbq_tag (impact category).
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        cat = (r.get("kbq_tags") or ["strategic"])[0]
        if cat not in _CATEGORY_LABELS:
            cat = "strategic"
        grouped.setdefault(cat, []).append(r)

    # Sort categories by aggregate impact, take top N.
    ranked = sorted(
        grouped.items(),
        key=lambda kv: -sum(float(s.get("impact_score") or 0) for s in kv[1]),
    )[: body.n]

    moments = [
        _make_moment(category=cat, signals=sigs[:3], llm=llm, priority=i + 1)
        for i, (cat, sigs) in enumerate(ranked)
    ]
    return {"moments": moments}
