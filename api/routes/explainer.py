"""BE-19 — POST /why-this endpoint."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_llm
from services import explainer as svc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["explainer"])


class WhyThisBody(BaseModel):
    surface: str = Field(..., description="pulse|brief_proposal|agent_suggestion|wargame_rec|trigger_fire")
    item_id: str = Field(..., min_length=1, max_length=200)
    context: dict = Field(default_factory=dict)


@router.post("/why-this")
def why_this(body: WhyThisBody, llm = Depends(get_llm)):
    """Return a one-paragraph plain-language explanation + deep_links."""
    try:
        request = svc.ExplanationRequest(
            surface=body.surface,
            item_id=body.item_id,
            context=body.context or {},
        )
    except Exception as exc:  # pragma: no cover — Pydantic catches before this
        raise HTTPException(400, str(exc))

    try:
        result = svc.explain(request, llm=llm)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return result.to_dict()
