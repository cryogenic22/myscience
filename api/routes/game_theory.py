"""SPEC_025 — Game-Theoretic Simulation API.

Endpoints:
  POST  /game-theory/bayesian        uploader+
  POST  /game-theory/stackelberg     uploader+
  POST  /game-theory/pomdp           uploader+
  GET   /game-theory/runs            viewer+
  GET   /game-theory/runs/{run_id}   viewer+
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.deps import get_db, require_role
from db import Database
from services import game_theory as gt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/game-theory", tags=["game-theory"])


# ────────────────────────────────────────────────────────────────────
# Request schemas
# ────────────────────────────────────────────────────────────────────

class BayesianAdversaryBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=50)
    type_distribution: dict[str, float]
    type_response_strengths: dict[str, dict[str, float]]


class BayesianBody(BaseModel):
    brief_id: Optional[str] = None
    adversary: BayesianAdversaryBody
    options: list[dict] = Field(min_length=1, max_length=10)
    sample_count: int = Field(default=1000, ge=1, le=100_000)
    seed: Optional[int] = None


class StackelbergCellBody(BaseModel):
    timing: float
    response: str
    payoff: float


class StackelbergBody(BaseModel):
    brief_id: Optional[str] = None
    timing_grid: list[float] = Field(min_length=1, max_length=500)
    opponent_responses: list[str] = Field(min_length=1, max_length=50)
    our_payoff: list[StackelbergCellBody] = Field(min_length=1)
    opponent_payoff: list[StackelbergCellBody] = Field(min_length=1)


class POMDPSignalBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    arrival_days: int = Field(ge=0, le=3650)
    expected_info_value: float
    posterior_shifts: dict[str, float]


class POMDPBody(BaseModel):
    brief_id: Optional[str] = None
    options: dict[str, float] = Field(min_length=1, max_length=20)
    upcoming_signals: list[POMDPSignalBody] = Field(min_length=1, max_length=50)
    discount_rate_per_day: float = Field(default=0.005, ge=0.0, lt=1.0)


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _to_matrix(cells: list[StackelbergCellBody]) -> dict:
    """Convert [{timing, response, payoff}, ...] → {(timing, response): payoff}."""
    out = {}
    for c in cells:
        out[(c.timing, c.response)] = c.payoff
    return out


def _matrix_to_list(matrix: dict) -> list[dict]:
    """For persisting as JSON — tuple keys aren't serializable."""
    return [{"timing": k[0], "response": k[1], "payoff": v} for k, v in matrix.items()]


# ────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────

@router.post("/bayesian", status_code=200)
def bayesian(
    body: BayesianBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    cfg = gt.BayesianRunConfig(
        adversary=gt.BayesianAdversaryConfig(
            name=body.adversary.name,
            kind=body.adversary.kind,
            type_distribution=body.adversary.type_distribution,
            type_response_strengths=body.adversary.type_response_strengths,
        ),
        options=body.options,
        sample_count=body.sample_count,
        seed=body.seed,
    )
    t0 = time.perf_counter()
    try:
        outputs = gt.run_bayesian(cfg)
    except ValueError as e:
        raise HTTPException(400, str(e))
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    rec = gt.persist_run(
        db,
        brief_id=body.brief_id,
        kind="bayesian",
        inputs={
            "adversary": {
                "name": body.adversary.name, "kind": body.adversary.kind,
                "type_distribution": body.adversary.type_distribution,
                "type_response_strengths": body.adversary.type_response_strengths,
            },
            "options": body.options,
            "sample_count": body.sample_count,
            "seed": body.seed,
        },
        outputs=outputs,
        compute_ms=elapsed_ms,
        started_by_user_id=str(user["id"]),
    )
    return rec


@router.post("/stackelberg", status_code=200)
def stackelberg(
    body: StackelbergBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    our_matrix = _to_matrix(body.our_payoff)
    opp_matrix = _to_matrix(body.opponent_payoff)
    cfg = gt.StackelbergConfig(
        timing_grid=body.timing_grid,
        opponent_responses=body.opponent_responses,
        our_payoff_matrix=our_matrix,
        opponent_payoff_matrix=opp_matrix,
    )
    t0 = time.perf_counter()
    try:
        outputs = gt.run_stackelberg(cfg)
    except ValueError as e:
        raise HTTPException(400, str(e))
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    rec = gt.persist_run(
        db,
        brief_id=body.brief_id,
        kind="stackelberg",
        inputs={
            "timing_grid": body.timing_grid,
            "opponent_responses": body.opponent_responses,
            "our_payoff": _matrix_to_list(our_matrix),
            "opponent_payoff": _matrix_to_list(opp_matrix),
        },
        outputs=outputs,
        compute_ms=elapsed_ms,
        started_by_user_id=str(user["id"]),
    )
    return rec


@router.post("/pomdp", status_code=200)
def pomdp(
    body: POMDPBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    cfg = gt.POMDPConfig(
        options=body.options,
        upcoming_signals=[
            gt.POMDPSignalConfig(
                name=s.name,
                arrival_days=s.arrival_days,
                expected_info_value=s.expected_info_value,
                posterior_shifts=s.posterior_shifts,
            )
            for s in body.upcoming_signals
        ],
        discount_rate_per_day=body.discount_rate_per_day,
    )
    t0 = time.perf_counter()
    try:
        outputs = gt.run_pomdp(cfg)
    except ValueError as e:
        raise HTTPException(400, str(e))
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    rec = gt.persist_run(
        db,
        brief_id=body.brief_id,
        kind="pomdp",
        inputs={
            "options": body.options,
            "upcoming_signals": [s.model_dump() for s in body.upcoming_signals],
            "discount_rate_per_day": body.discount_rate_per_day,
        },
        outputs=outputs,
        compute_ms=elapsed_ms,
        started_by_user_id=str(user["id"]),
    )
    return rec


@router.get("/runs")
def list_runs(
    brief_id: Optional[str] = Query(default=None),
    kind: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    try:
        runs = gt.list_runs(db, brief_id=brief_id, kind=kind, limit=limit, offset=offset)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"runs": runs, "limit": limit, "offset": offset, "count": len(runs)}


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    rec = gt.get_run(db, run_id)
    if not rec:
        raise HTTPException(404, f"run not found: {run_id}")
    return rec
