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
  GET /zs                          the page (index.html)
  GET /zs/                         "
  GET /zs/zs-future-state-v2.jsx   the component source (fetched by the page)

The `/zs` first path-segment is auto-collected as an API prefix by the app's
SPA-fallback registry, so these 200s/401s are never replaced with index.html.
Purely additive — touches no existing route and needs no migration.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

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
