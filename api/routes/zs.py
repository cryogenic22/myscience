"""Password-gated static hosting for the standalone ZS Future State page.

A self-contained React/recharts dashboard (`static/zs/zs-future-state-v2.jsx`)
that we want reachable on the deployed Railway instance but behind a simple
password — without coupling it to the Vite frontend build (it pulls react +
recharts from a CDN and is transpiled in the browser; see static/zs/index.html).

This router serves the page and its source under `/zs`, gated by HTTP Basic auth
(the browser's native username/password prompt). Credentials come from env vars
so no secret lives in the repo:

  ZS_PAGE_USER      username (default "zs")
  ZS_PAGE_PASSWORD  password (default "zs-future" — OVERRIDE this in Railway)

Endpoints (all 401 without valid Basic credentials):
  GET    /zs                          the page (index.html)
  GET    /zs/                         "
  GET    /zs/zs-future-state-v2.jsx   the component source (fetched by the page)
  GET    /zs/api/cards                list the editable capability cards
  GET    /zs/api/cards/export         the full card set as a downloadable JSON
  POST   /zs/api/cards                create a card
  POST   /zs/api/cards/import         replace the whole set from a posted JSON
  PUT    /zs/api/cards/{id}           update a card
  DELETE /zs/api/cards/{id}           delete a card

The capability cards are persisted to a JSON file (no database) — see
``services/zs_store.py``. The `/zs` first path-segment is auto-collected as an
API prefix by the app's SPA-fallback registry, so these 200s/401s are never
replaced with index.html. Purely additive — touches no existing route and needs
no migration.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import ValidationError

from services import zs_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/zs", tags=["zs"])

# repo-root/static/zs  (this file is repo-root/api/routes/zs.py → parents[2] = root)
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static" / "zs"

_security = HTTPBasic(realm="ZS Future State")

# Default password is intentionally weak and documented — set ZS_PAGE_PASSWORD
# in the Railway environment to lock it down. Kept as a default (rather than
# failing closed) so the page is reachable the moment the deploy goes live.
_DEFAULT_USER = "zs"
_DEFAULT_PASSWORD = "zs-future"


def require_auth(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    """HTTP Basic gate. Constant-time compare against the env-configured creds."""
    exp_user = os.getenv("ZS_PAGE_USER", _DEFAULT_USER)
    exp_pw = os.getenv("ZS_PAGE_PASSWORD", _DEFAULT_PASSWORD)
    ok_user = secrets.compare_digest(credentials.username.encode("utf-8"), exp_user.encode("utf-8"))
    ok_pw = secrets.compare_digest(credentials.password.encode("utf-8"), exp_pw.encode("utf-8"))
    if not (ok_user and ok_pw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": 'Basic realm="ZS Future State"'},
        )
    return credentials.username


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def zs_index(_: str = Depends(require_auth)) -> FileResponse:
    """Serve the page shell."""
    index = _STATIC_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="page not found")
    return FileResponse(str(index), media_type="text/html; charset=utf-8")


@router.get("/zs-future-state-v2.jsx", include_in_schema=False)
def zs_source(_: str = Depends(require_auth)) -> FileResponse:
    """Serve the JSX source the page fetches and transpiles in-browser.

    Served as text/plain so the browser never tries to MIME-sniff/execute it as
    a module — the page reads it via fetch().text() and hands it to Babel.
    """
    src = _STATIC_DIR / "zs-future-state-v2.jsx"
    if not src.is_file():
        raise HTTPException(status_code=404, detail="source not found")
    return FileResponse(str(src), media_type="text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# Editable capability cards — file-backed JSON CRUD (no database).
# All gated by the same require_auth Basic gate as the page above.
# ---------------------------------------------------------------------------
def _card_or_422(payload: dict[str, Any]) -> zs_store.CapabilityCard:
    """Build + validate a card from a request body; map invalid → 422."""
    try:
        return zs_store.CapabilityCard(**payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=exc.errors(include_url=False, include_context=False)
        ) from exc


@router.get("/api/cards", include_in_schema=False)
def list_cards(_: str = Depends(require_auth)) -> dict[str, Any]:
    """Return the full set of editable capability cards (seeds on first read)."""
    return zs_store.export_dict()


@router.get("/api/cards/export", include_in_schema=False)
def export_cards(_: str = Depends(require_auth)) -> JSONResponse:
    """Return the card set as a downloadable JSON attachment."""
    return JSONResponse(
        content=zs_store.export_dict(),
        headers={"Content-Disposition": 'attachment; filename="zs_capability_cards.json"'},
    )


@router.post("/api/cards", include_in_schema=False, status_code=201)
def create_card(
    payload: dict[str, Any] = Body(...), _: str = Depends(require_auth)
) -> dict[str, Any]:
    """Create a capability card. Server assigns a slug id if absent; rejects dup ids."""
    card = _card_or_422(payload)
    try:
        created = zs_store.create(card)
    except ValueError as exc:  # duplicate id
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return created.model_dump()


@router.put("/api/cards/{card_id}", include_in_schema=False)
def update_card(
    card_id: str, payload: dict[str, Any] = Body(...), _: str = Depends(require_auth)
) -> dict[str, Any]:
    """Replace the card at ``card_id``. 404 if it doesn't exist."""
    card = _card_or_422(payload)
    updated = zs_store.update(card_id, card)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"card {card_id!r} not found")
    return updated.model_dump()


@router.delete("/api/cards/{card_id}", include_in_schema=False)
def delete_card(card_id: str, _: str = Depends(require_auth)) -> dict[str, Any]:
    """Delete the card at ``card_id``. 404 if it doesn't exist."""
    if not zs_store.delete(card_id):
        raise HTTPException(status_code=404, detail=f"card {card_id!r} not found")
    return {"deleted": card_id}


@router.post("/api/cards/import", include_in_schema=False)
def import_cards(
    payload: dict[str, Any] = Body(...), _: str = Depends(require_auth)
) -> dict[str, Any]:
    """Replace the entire card set from a posted JSON. Validates every card → 422."""
    try:
        cards = zs_store.replace_all(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=exc.errors(include_url=False, include_context=False)
        ) from exc
    except ValueError as exc:  # malformed payload / duplicate ids
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"cards": [c.model_dump() for c in cards]}
