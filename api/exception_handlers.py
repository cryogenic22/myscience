"""SPEC-021 D2 — standard error envelope.

Wraps `HTTPException` and `RequestValidationError` into a consistent
JSON shape:

  {
    "error": {
      "code": 404,
      "type": "not_found",
      "message": "war room not found: abc",
      "details": {...}
    },
    "detail": "war room not found: abc"   ← back-compat for legacy clients
  }

Existing clients that read `.detail` keep working. Newer clients can
read `.error.code` + `.error.type` for programmatic dispatch.

Drop the back-compat `.detail` key in a future cycle once the frontend
fully migrates to `.error.message`.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


_HTTP_STATUS_TYPE = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
}


def _envelope(*, code: int, message: str, type_: str | None = None,
              details: dict[str, Any] | None = None,
              headers: dict[str, str] | None = None) -> JSONResponse:
    body = {
        "error": {
            "code": code,
            "type": type_ or _HTTP_STATUS_TYPE.get(code, "error"),
            "message": message,
        },
        "detail": message,  # back-compat
    }
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=code, content=body, headers=headers)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Preserve any Retry-After or other headers the route attached
    headers = dict(getattr(exc, "headers", None) or {})
    detail = exc.detail
    # Detail might already be a dict (e.g. validation forwarded); flatten it.
    if isinstance(detail, dict) and "error" in detail:
        # Already enveloped — pass through
        return JSONResponse(status_code=exc.status_code, content=detail, headers=headers)
    message = str(detail) if detail is not None else _HTTP_STATUS_TYPE.get(exc.status_code, "error")
    return _envelope(code=exc.status_code, message=message, headers=headers)


def _sanitize_error_dict(err: dict) -> dict:
    """Pydantic v2 attaches the original Python exception object to
    ``ctx.error`` when a field_validator raises (e.g. ValueError). That
    object is not JSON-serializable. Replace any non-JSON-serializable
    values with their str() form."""
    import json as _json
    out = {}
    for k, v in err.items():
        try:
            _json.dumps(v)
            out[k] = v
        except (TypeError, ValueError):
            if isinstance(v, dict):
                out[k] = _sanitize_error_dict(v)
            else:
                out[k] = str(v)
    return out


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # FastAPI/Pydantic gives us a list of error dicts; surface the first
    # in `.message` and the full list in `.details.errors`.
    errors = [_sanitize_error_dict(e) for e in exc.errors()]
    first_msg = "Request validation failed"
    if errors:
        first = errors[0]
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        first_msg = f"{loc}: {first.get('msg', 'invalid')}" if loc else first.get("msg", first_msg)
    return _envelope(
        code=422,
        type_="validation_error",
        message=first_msg,
        details={"errors": errors},
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
