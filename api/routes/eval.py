"""Track I — the EVAL HARNESS API.

Surfaces the harness that scores the SYSTEM's own answer for each Forge gold
item (forge_eval_items) and reports accuracy / precision / recall / coverage,
per round-type and per playbook.

Mounted on its OWN prefix (`/eval`) — NOT under /entities, whose greedy
`/{entity_type}[/{entity_id}]` routes would otherwise shadow these.

Endpoints:
  GET  /eval/summary                 viewer+    latest run's metrics + flagged backlog
  POST /eval/run                     uploader+  run the harness now (persist a run)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_db, require_role
from db import Database
from services.evaluation import EvalHarness

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eval", tags=["eval"])

_harness = EvalHarness()


class RunBody(BaseModel):
    playbook_id: Optional[str] = None
    notes: Optional[str] = None


@router.get("/summary")
def eval_summary(
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    """The latest persisted eval run's metrics, the gold-set size, and the
    flagged-proposals backlog — the scorecard's data source. Returns a
    has_run=false envelope (not a 404) when no run has been recorded yet."""
    latest = _harness.latest_summary(db)
    backlog = _harness.flagged_backlog(db)
    if latest is None:
        return {"has_run": False, "latest": None, "flagged_backlog": backlog}
    return {"has_run": True, "latest": latest, "flagged_backlog": backlog}


@router.post("/run", status_code=201)
def eval_run(
    body: RunBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    """Run the harness now: score the gold set (optionally one playbook),
    aggregate, and persist an eval run. Returns the run summary."""
    try:
        summary = _harness.run(
            db,
            playbook_id=body.playbook_id,
            persist=True,
            created_by=(str(user.get("id")) if user else None),
            notes=body.notes,
        )
    except Exception as e:
        logger.exception("eval run failed")
        raise HTTPException(500, f"eval run failed: {e}")
    return summary.to_dict()
