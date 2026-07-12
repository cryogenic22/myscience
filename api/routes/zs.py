"""Password-gated static hosting for the standalone ZS Future State page.

A self-contained React/recharts dashboard (`static/zs/zs-future-state-v2.jsx`)
that we want reachable on the deployed Railway instance but behind a simple
password — without coupling it to the Vite frontend build (it pulls react +
recharts from a CDN and is transpiled in the browser; see static/zs/index.html).

This router serves the page and its source under `/zs`, gated by HTTP Basic auth
(the browser's native username/password prompt). Credentials come from env vars
so no secret lives in the repo:

  ZS_PAGE_USER      username (REQUIRED — no default; unset => the page 503s)
  ZS_PAGE_PASSWORD  password (REQUIRED — no default; unset => the page 503s)

Endpoints (503 until ZS_PAGE_* configured; 401 without valid Basic credentials):
  GET    /zs                          the page (index.html)
  GET    /zs/                         "
  GET    /zs/zs-future-state-v2.jsx   the component source (fetched by the page)

  Editable, file-persisted card families — three of them, identical CRUD shape:
  GET    /zs/api/cards                list the capability cards (offerings)
  GET    /zs/api/cards/export         the full card set as a downloadable JSON
  POST   /zs/api/cards                create a card
  POST   /zs/api/cards/import         replace the whole set from a posted JSON
  PUT    /zs/api/cards/{id}           update a card
  DELETE /zs/api/cards/{id}           delete a card
  …and the same six under /zs/api/constructs* (commercial constructs) and
  /zs/api/bets* (capability bets).

The cards/constructs/bets are each persisted to their own JSON file (no
database) — see ``services/zs_store.py`` (one family registry, N files). The
`/zs` first path-segment is auto-collected as an API prefix by the app's
SPA-fallback registry, so these 200s/401s are never replaced with index.html.
Purely additive — touches no existing route and needs no migration.
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
from pydantic import BaseModel, ValidationError

from services import zs_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/zs", tags=["zs"])

# repo-root/static/zs  (this file is repo-root/api/routes/zs.py → parents[2] = root)
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static" / "zs"

_security = HTTPBasic(realm="ZS Future State")

# SEC-001a (red-team 2026-07-10): NO default-credential fallback. A documented
# default ("zs"/"zs-future") is equivalent to no auth, so the gate now fails
# CLOSED (503) when ZS_PAGE_USER / ZS_PAGE_PASSWORD are unset. Operators must set
# both in the environment to expose the page.


def require_auth(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    """HTTP Basic gate. Constant-time compare against the env-configured creds.

    Fails closed (503) when the creds are not configured — no known-default.
    """
    exp_user = os.getenv("ZS_PAGE_USER")
    exp_pw = os.getenv("ZS_PAGE_PASSWORD")
    if not exp_user or not exp_pw:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ZS page auth is not configured",
        )
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
# Editable card families — file-backed JSON CRUD (no database).
# One factory registers the six routes (list / export / create / update /
# delete / import) for a given family; cards / constructs / bets each get the
# identical shape. All gated by the same require_auth Basic gate as the page.
# ---------------------------------------------------------------------------
def _card_or_422(payload: dict[str, Any], family: str) -> BaseModel:
    """Build + validate a card for ``family`` from a request body; invalid → 422."""
    model = zs_store.model_for(family)
    try:
        return model(**payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=exc.errors(include_url=False, include_context=False)
        ) from exc


def _register_family(family: str, segment: str, download_name: str) -> None:
    """Register the six CRUD routes for one card family under ``/zs/api/<segment>``.

    ``family`` is the ``zs_store`` family key; ``segment`` the URL path segment.
    Kept as a factory so cards/constructs/bets share one implementation and can't
    drift apart — each closes over its own ``family`` so persistence stays per-file.

    INVARIANT: handlers reference the ``family`` closure variable DIRECTLY and must
    NOT take it as a parameter. A bare ``family: str`` (even with a default) in a
    handler signature would be promoted by FastAPI to a client-settable query
    param (``?family=bets``), letting a caller cross-read/write another family's
    file. The closure binds it at registration; the client cannot influence it.
    """
    base = f"/api/{segment}"

    @router.get(base, include_in_schema=False, name=f"list_{family}")
    def _list(_: str = Depends(require_auth)) -> dict[str, Any]:
        """Return the full set for this family (seeds the file on first read)."""
        return zs_store.export_dict(family)

    @router.get(f"{base}/export", include_in_schema=False, name=f"export_{family}")
    def _export(_: str = Depends(require_auth)) -> JSONResponse:
        """Return the set as a downloadable JSON attachment."""
        return JSONResponse(
            content=zs_store.export_dict(family),
            headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
        )

    @router.post(base, include_in_schema=False, status_code=201, name=f"create_{family}")
    def _create(
        payload: dict[str, Any] = Body(...),
        _: str = Depends(require_auth),
    ) -> dict[str, Any]:
        """Create a card. Server assigns a slug id if absent; rejects dup ids → 409."""
        card = _card_or_422(payload, family)
        try:
            created = zs_store.create(card, family)
        except ValueError as exc:  # duplicate id
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return created.model_dump()

    @router.put(f"{base}/{{card_id}}", include_in_schema=False, name=f"update_{family}")
    def _update(
        card_id: str,
        payload: dict[str, Any] = Body(...),
        _: str = Depends(require_auth),
    ) -> dict[str, Any]:
        """Replace the card at ``card_id``. 404 if it doesn't exist."""
        card = _card_or_422(payload, family)
        updated = zs_store.update(card_id, card, family)
        if updated is None:
            raise HTTPException(status_code=404, detail=f"{segment} {card_id!r} not found")
        return updated.model_dump()

    @router.delete(f"{base}/{{card_id}}", include_in_schema=False, name=f"delete_{family}")
    def _delete(
        card_id: str, _: str = Depends(require_auth)
    ) -> dict[str, Any]:
        """Delete the card at ``card_id``. 404 if it doesn't exist."""
        if not zs_store.delete(card_id, family):
            raise HTTPException(status_code=404, detail=f"{segment} {card_id!r} not found")
        return {"deleted": card_id}

    @router.post(f"{base}/import", include_in_schema=False, name=f"import_{family}")
    def _import(
        payload: dict[str, Any] = Body(...),
        _: str = Depends(require_auth),
    ) -> dict[str, Any]:
        """Replace the entire set from a posted JSON. Validates every card → 422."""
        try:
            cards = zs_store.replace_all(payload, family)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=exc.errors(include_url=False, include_context=False),
            ) from exc
        except ValueError as exc:  # malformed payload / duplicate ids / over-limit
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"cards": [c.model_dump() for c in cards]}


# Register the three families. `cards` keeps its original path + download name
# so existing callers and tests are untouched; the two new families mirror it.
_register_family("cards", "cards", "zs_capability_cards.json")
_register_family("constructs", "constructs", "zs_commercial_constructs.json")
_register_family("bets", "bets", "zs_capability_bets.json")
