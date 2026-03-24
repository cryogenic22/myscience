"""Scenario primitives API routes.

Deterministic what-if operations on the knowledge graph: entity removal,
temporal filtering, segment isolation, and threshold alerts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Optional

from api.deps import get_db, get_metrics
from db import Database
from services.metrics import PharmaMetrics
from services.scenario_engine import ScenarioEngine

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


def _get_scenario_engine(
    db: Database = Depends(get_db),
    metrics: PharmaMetrics = Depends(get_metrics),
) -> ScenarioEngine:
    return ScenarioEngine(db=db, metrics=metrics)


# ── Request models ──

class LandscapeWithoutRequest(BaseModel):
    entity_id: str
    entity_type: str
    topic: Optional[str] = None


class PipelineWithoutRequest(BaseModel):
    entity_id: str
    therapeutic_area: Optional[str] = None


class PipelineInactiveRequest(BaseModel):
    therapeutic_area: str
    inactive_years: int = 2


class ThresholdAlertRequest(BaseModel):
    metric: str
    threshold: float
    entity_type: str = "drug"


class CompanyRemovalRequest(BaseModel):
    company_id: str
    topic: Optional[str] = None


class MechanismIsolationRequest(BaseModel):
    mechanism_id: str
    topic: Optional[str] = None


# ── Endpoints ──

@router.post("/landscape-without")
def landscape_without(
    body: LandscapeWithoutRequest,
    engine: ScenarioEngine = Depends(_get_scenario_engine),
):
    """Recalculate competitive landscape excluding an entity (mechanism, TA, etc.)."""
    result = engine.landscape_without_entity(
        entity_id=body.entity_id,
        entity_type=body.entity_type,
        topic=body.topic,
    )
    return _scenario_result_to_dict(result)


@router.post("/pipeline-without")
def pipeline_without(
    body: PipelineWithoutRequest,
    engine: ScenarioEngine = Depends(_get_scenario_engine),
):
    """Recalculate pipeline strength excluding a specific drug."""
    result = engine.pipeline_without_entity(
        entity_id=body.entity_id,
        therapeutic_area=body.therapeutic_area,
    )
    return _scenario_result_to_dict(result)


@router.post("/pipeline-inactive")
def pipeline_excluding_inactive(
    body: PipelineInactiveRequest,
    engine: ScenarioEngine = Depends(_get_scenario_engine),
):
    """Pipeline excluding drugs with no recent trial activity."""
    result = engine.pipeline_excluding_inactive(
        therapeutic_area=body.therapeutic_area,
        inactive_years=body.inactive_years,
    )
    return _scenario_result_to_dict(result)


@router.post("/company-removal")
def company_removal(
    body: CompanyRemovalRequest,
    engine: ScenarioEngine = Depends(_get_scenario_engine),
):
    """Landscape excluding all drugs from a specific company."""
    result = engine.landscape_without_company(
        company_id=body.company_id,
        topic=body.topic,
    )
    return _scenario_result_to_dict(result)


@router.post("/mechanism-isolation")
def mechanism_isolation(
    body: MechanismIsolationRequest,
    engine: ScenarioEngine = Depends(_get_scenario_engine),
):
    """Isolate landscape to a single mechanism for deep-dive analysis."""
    result = engine.landscape_single_mechanism(
        mechanism_id=body.mechanism_id,
        topic=body.topic,
    )
    return _scenario_result_to_dict(result)


@router.post("/threshold-alert")
def threshold_alert(
    body: ThresholdAlertRequest,
    engine: ScenarioEngine = Depends(_get_scenario_engine),
):
    """Flag entities exceeding a metric threshold."""
    alerts = engine.threshold_alert(
        metric=body.metric,
        threshold=body.threshold,
        entity_type=body.entity_type,
    )
    return {"alerts": alerts, "count": len(alerts)}


# ── Helpers ──

def _scenario_result_to_dict(result) -> dict:
    """Convert ScenarioResult dataclass to JSON-serializable dict."""
    return {
        "scenario_type": result.scenario_type,
        "description": result.description,
        "baseline": result.baseline,
        "modified": result.modified,
        "delta": result.delta,
        "entities_affected": result.entities_affected,
    }
