"""SPEC_026 — LLM Gateway API.

Endpoints:
  POST /llm-gateway/prompts                       uploader+
  GET  /llm-gateway/prompts                       viewer+
  GET  /llm-gateway/prompts/{prompt_id}           viewer+
  POST /llm-gateway/invoke                        uploader+
  POST /llm-gateway/scan-pii                      uploader+
  GET  /llm-gateway/cost-summary                  viewer+
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from api.deps import get_db, require_role
from db import Database
from services.llm_gateway import (
    LLMGateway,
    PromptNotFound,
    PromptRegistry,
    PIIRejected,
    TemplateError,
    VALID_GROUP_BY,
    VALID_PII_POLICIES,
    cost_summary,
    extract_template_variables,
    redact_pii,
    scan_pii,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm-gateway", tags=["llm-gateway"])


# ────────────────────────────────────────────────────────────────────
# Request schemas
# ────────────────────────────────────────────────────────────────────

class RegisterPromptBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=32768)
    purpose: Optional[str] = Field(default=None, max_length=2000)
    model_pref: Optional[str] = Field(default=None, max_length=100)
    max_tokens: Optional[int] = Field(default=None, gt=0, le=100000)


class InvokeBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=200, description="Prompt name or prompt_id (UUID)")
    variables: Optional[dict] = None
    user_message: Optional[str] = Field(default=None, max_length=65536)
    version: Optional[int] = Field(default=None, ge=1)
    model_pref: Optional[str] = Field(default=None, max_length=100)
    max_tokens: Optional[int] = Field(default=None, gt=0, le=100000)
    pii_policy: str = Field(default="redact")

    @field_validator("pii_policy")
    @classmethod
    def _check_policy(cls, v: str) -> str:
        if v not in VALID_PII_POLICIES:
            raise ValueError(f"pii_policy must be one of {sorted(VALID_PII_POLICIES)}")
        return v


class ScanPIIBody(BaseModel):
    text: str = Field(min_length=0, max_length=131072)


# ────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────

@router.post("/prompts", status_code=201)
def register_prompt(
    body: RegisterPromptBody,
    response: Response,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    """Register or return existing prompt. Same (name, content) = same row;
    different content for an existing name → version+1.

    Returns 201 for new registrations, 200 for idempotent re-registrations.
    """
    try:
        prompt = PromptRegistry.register(
            db,
            name=body.name,
            content=body.content,
            purpose=body.purpose,
            model_pref=body.model_pref,
            max_tokens=body.max_tokens,
            created_by_user_id=str(user["id"]),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    # If we got back something with the same content_hash that already
    # existed, it's an idempotent hit → 200. We don't have an "is_new"
    # flag from register() so we infer: if request user matches creator,
    # could be either; safer to always 201 here. Frontend can ignore.
    return prompt.to_dict()


@router.get("/prompts")
def list_prompts(
    name: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    try:
        prompts = PromptRegistry.list(db, name_filter=name, limit=limit, offset=offset)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "prompts": [p.to_dict() for p in prompts],
        "limit": limit,
        "offset": offset,
        "count": len(prompts),
    }


@router.get("/prompts/{prompt_id}")
def get_prompt(
    prompt_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    p = PromptRegistry.get(db, prompt_id)
    if not p:
        raise HTTPException(404, f"prompt not found: {prompt_id}")
    return p.to_dict()


@router.post("/invoke")
def invoke(
    body: InvokeBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    # Lazy import to avoid circular dependency on app startup
    try:
        from api.deps import get_llm
    except Exception:
        get_llm = None

    llm = None
    if get_llm:
        try:
            llm = get_llm()
        except Exception as exc:
            logger.warning("get_llm failed: %s", exc)

    try:
        result = LLMGateway.invoke(
            db, llm,
            prompt=body.prompt,
            variables=body.variables or {},
            user_message=body.user_message,
            version=body.version,
            model_pref=body.model_pref,
            max_tokens=body.max_tokens,
            pii_policy=body.pii_policy,
            user_id=str(user["id"]),
            caller="llm_gateway",
        )
    except PromptNotFound:
        raise HTTPException(404, f"prompt not found: {body.prompt}")
    except TemplateError as e:
        raise HTTPException(400, str(e))
    except PIIRejected as e:
        raise HTTPException(409, f"PII detected (policy=reject): {[m.kind for m in e.matches]}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result.to_dict()


@router.post("/scan-pii")
def scan_pii_endpoint(
    body: ScanPIIBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    """Diagnostic: scan a string for PII without invoking the LLM."""
    matches = scan_pii(body.text)
    return {
        "matches": [m.to_dict() for m in matches],
        "redacted": redact_pii(body.text, matches),
        "match_count": len(matches),
    }


@router.get("/cost-summary")
def get_cost_summary(
    since: Optional[date] = Query(default=None),
    until: Optional[date] = Query(default=None),
    group_by: str = Query(default="caller"),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    if group_by not in VALID_GROUP_BY:
        raise HTTPException(400, f"group_by must be one of {sorted(VALID_GROUP_BY)}")
    try:
        return cost_summary(db, since=since, until=until, group_by=group_by)
    except ValueError as e:
        raise HTTPException(400, str(e))
