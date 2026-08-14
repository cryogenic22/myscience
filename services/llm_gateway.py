"""SPEC_026 — LLM Gateway.

Three responsibilities:
  1. Versioned prompt registry — every production prompt is registered and
     each call's llm_call_log row references the prompt_id (so SPEC-028
     Learning Service can attribute accuracy to specific prompt versions).
  2. PII filter — outbound prompts are scanned; matched PII is redacted or
     the call rejected, depending on policy.
  3. Cost summary — aggregate llm_call_log over a date range without writing
     SQL by hand.

Templating: Mustache-style `{{var}}`. Single-pass substitution; values are
inserted verbatim and NEVER re-rendered (blocks template injection from
caller-controlled variable values).

Provider abstraction is deliberately deferred — current stack uses one
OpenAI-shaped provider; multi-provider routing is premature. The Gateway
delegates the actual chat call to the existing `chat_with_telemetry`
wrapper so all calls flow through the same telemetry path.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


MAX_PROMPT_CONTENT_BYTES = 32 * 1024  # 32 KB
MAX_PROMPT_NAME_LEN = 200
DEFAULT_MAX_TOKENS = 900

# ────────────────────────────────────────────────────────────────────
# PII patterns
# ────────────────────────────────────────────────────────────────────

# Order matters: check more-specific patterns (SSN, CC) before broader ones.
_PII_PATTERNS = [
    ("ssn",         re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone_us",    re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")),
    ("email",       re.compile(r"[\w._%+-]+@[\w.-]+\.[A-Za-z]{2,}")),
    # Credit-card candidates: 13-19 digits with optional spaces/hyphens.
    # Each match is then Luhn-checked before being declared PII.
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
]

VALID_PII_POLICIES = {"redact", "reject", "allow"}


def _luhn_valid(number: str) -> bool:
    """Standard Luhn checksum validation. Strips non-digits first."""
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    s = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return s % 10 == 0


@dataclass
class PIIMatch:
    kind: str
    start: int
    end: int
    original: str

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "redacted": f"[{self.kind.upper()}]",
            "original_length": len(self.original),
        }


def scan_pii(text: str) -> list[PIIMatch]:
    """Scan text for PII patterns. Returns matches in order of position.
    Overlapping matches are deduplicated (longest wins). Credit-card
    candidates that fail Luhn are not reported."""
    if not text:
        return []
    raw: list[PIIMatch] = []
    for kind, pattern in _PII_PATTERNS:
        for m in pattern.finditer(text):
            if kind == "credit_card" and not _luhn_valid(m.group(0)):
                continue
            raw.append(PIIMatch(kind=kind, start=m.start(), end=m.end(), original=m.group(0)))

    # Dedup overlapping matches; keep longest, ties broken by earlier start.
    raw.sort(key=lambda x: (x.start, -(x.end - x.start)))
    out: list[PIIMatch] = []
    last_end = -1
    for m in raw:
        if m.start < last_end:
            continue  # overlaps a previous accepted match
        out.append(m)
        last_end = m.end
    return out


def redact_pii(text: str, matches: Optional[list[PIIMatch]] = None) -> str:
    """Replace each matched span with `[KIND]`. Matches in input order;
    if not provided, computed via scan_pii."""
    if matches is None:
        matches = scan_pii(text)
    if not matches:
        return text
    out_parts: list[str] = []
    cursor = 0
    for m in matches:
        out_parts.append(text[cursor:m.start])
        out_parts.append(f"[{m.kind.upper()}]")
        cursor = m.end
    out_parts.append(text[cursor:])
    return "".join(out_parts)


# ────────────────────────────────────────────────────────────────────
# Template substitution
# ────────────────────────────────────────────────────────────────────

_TEMPLATE_VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\}\}")


class TemplateError(Exception):
    """Template substitution failed — usually missing variables."""
    def __init__(self, missing: list[str]):
        self.missing = sorted(set(missing))
        super().__init__(f"missing template variables: {self.missing}")


def render_template(template: str, variables: dict) -> str:
    """Single-pass Mustache-style substitution. Values are inserted verbatim;
    they are NEVER re-rendered (blocks template injection)."""
    if not template:
        return ""
    if variables is None:
        variables = {}

    missing: list[str] = []
    def _sub(match):
        key = match.group(1)
        if key not in variables:
            missing.append(key)
            return match.group(0)
        return str(variables[key])

    rendered = _TEMPLATE_VAR_RE.sub(_sub, template)
    if missing:
        raise TemplateError(missing)
    return rendered


def extract_template_variables(template: str) -> list[str]:
    """Return the unique set of `{{var}}` names referenced in the template,
    in order of first appearance."""
    seen: list[str] = []
    seen_set: set[str] = set()
    for m in _TEMPLATE_VAR_RE.finditer(template or ""):
        k = m.group(1)
        if k not in seen_set:
            seen.append(k)
            seen_set.add(k)
    return seen


# ────────────────────────────────────────────────────────────────────
# Domain dataclasses
# ────────────────────────────────────────────────────────────────────

@dataclass
class Prompt:
    prompt_id: str
    name: str
    version: int
    content: str
    content_hash_hex: str
    purpose: Optional[str]
    model_pref: Optional[str]
    max_tokens: Optional[int]
    created_by_user_id: Optional[str]
    created_at: Optional[datetime]

    def variables(self) -> list[str]:
        return extract_template_variables(self.content)

    def to_dict(self) -> dict:
        return {
            "prompt_id": str(self.prompt_id),
            "name": self.name,
            "version": self.version,
            "content": self.content,
            "content_hash": self.content_hash_hex,
            "purpose": self.purpose,
            "model_pref": self.model_pref,
            "max_tokens": self.max_tokens,
            "created_by_user_id": str(self.created_by_user_id) if self.created_by_user_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "variables": self.variables(),
        }


# ────────────────────────────────────────────────────────────────────
# Errors
# ────────────────────────────────────────────────────────────────────

class PromptNotFound(Exception):
    pass


class PIIRejected(Exception):
    """Raised when policy=reject and PII was detected."""
    def __init__(self, matches: list[PIIMatch]):
        self.matches = matches
        super().__init__(f"PII detected: {[m.kind for m in matches]}")


class PIIPolicyForbidden(Exception):
    """Raised when MZ_PII_POLICY=allow is used in a production environment."""


# ────────────────────────────────────────────────────────────────────
# PRIV-001b — provider-agnostic egress guard (the ONE approved adapter)
# ────────────────────────────────────────────────────────────────────
#
# These `guard_*` functions are the ONLY code permitted to call a provider
# `.create(...)`. Every runtime egress site routes its outbound text through
# here, so PII is scanned/redacted (or the call rejected) BEFORE anything leaves
# the process. The WP-12C scanner (assurance/egress_scan.py) enforces structurally
# that no raw provider `.create` exists outside this adapter — see
# assurance/contract/egress_inventory.json and SPEC_HANDOFF §H1.1.4.

_PROD_ENV_VARS = ("RAILWAY_ENVIRONMENT", "MZ_ENV", "ENVIRONMENT", "APP_ENV")
_PROD_VALUES = {"production", "prod"}


def _is_production() -> bool:
    for var in _PROD_ENV_VARS:
        if os.environ.get(var, "").strip().lower() in _PROD_VALUES:
            return True
    return False


def resolve_pii_policy(policy: Optional[str] = None) -> str:
    """Resolve the effective PII policy: explicit arg, else env MZ_PII_POLICY, else 'redact'.

    'allow' (pass PII through unredacted) is FORBIDDEN in production — a builder cannot
    disable the filter on the live path by flipping an env var.
    """
    p = (policy or os.environ.get("MZ_PII_POLICY") or "redact").strip().lower()
    if p not in VALID_PII_POLICIES:
        raise ValueError(f"pii_policy must be one of {sorted(VALID_PII_POLICIES)}, got {p!r}")
    if p == "allow" and _is_production():
        raise PIIPolicyForbidden(
            "MZ_PII_POLICY=allow is forbidden in production — outbound PII must be redacted or rejected"
        )
    return p


def _apply_policy_to_text(text: Optional[str], policy: str) -> Optional[str]:
    """Sanitize one text value under the resolved policy.

    reject + match -> PIIRejected (the provider is never called by the guard).
    redact + match -> redacted text.  allow / no-match -> unchanged.
    """
    if not text:
        return text
    matches = scan_pii(text)
    if not matches:
        return text
    if policy == "reject":
        raise PIIRejected(matches)
    if policy == "redact":
        return redact_pii(text, matches)
    return text  # allow (unreachable in production — resolve_pii_policy blocks it)


def _sanitize_messages(messages, policy: str):
    """Return a NEW messages list with each textual content sanitized.

    Handles both string content and Anthropic-style content-block lists.
    """
    out = []
    for m in messages or []:
        if isinstance(m, dict) and isinstance(m.get("content"), str):
            out.append({**m, "content": _apply_policy_to_text(m["content"], policy)})
        elif isinstance(m, dict) and isinstance(m.get("content"), list):
            blocks = []
            for b in m["content"]:
                if isinstance(b, dict) and isinstance(b.get("text"), str):
                    blocks.append({**b, "text": _apply_policy_to_text(b["text"], policy)})
                else:
                    blocks.append(b)
            out.append({**m, "content": blocks})
        else:
            out.append(m)
    return out


def _sanitize_input(value, policy: str):
    """Embeddings input may be a single string or a list of strings."""
    if isinstance(value, str):
        return _apply_policy_to_text(value, policy)
    if isinstance(value, list):
        return [_apply_policy_to_text(v, policy) if isinstance(v, str) else v for v in value]
    return value


def guard_openai_chat(client, *, model, messages, pii_policy: Optional[str] = None, **kwargs):
    """Approved adapter for OpenAI chat.completions.create. Sanitizes `messages`
    BEFORE the call; passes stream/tools/temperature/etc. straight through."""
    policy = resolve_pii_policy(pii_policy)
    safe_messages = _sanitize_messages(messages, policy)
    return client.chat.completions.create(model=model, messages=safe_messages, **kwargs)


def guard_anthropic_messages(client, *, model, messages, system=None,
                             pii_policy: Optional[str] = None, **kwargs):
    """Approved adapter for Anthropic messages.create. Sanitizes `system` + `messages`."""
    policy = resolve_pii_policy(pii_policy)
    safe_messages = _sanitize_messages(messages, policy)
    call_kwargs = dict(kwargs)
    if system is not None:
        call_kwargs["system"] = _apply_policy_to_text(system, policy)
    return client.messages.create(model=model, messages=safe_messages, **call_kwargs)


def guard_openai_embeddings(client, *, model, input, pii_policy: Optional[str] = None, **kwargs):
    """Approved adapter for OpenAI embeddings.create. `input` may be str or list[str]."""
    policy = resolve_pii_policy(pii_policy)
    safe_input = _sanitize_input(input, policy)
    return client.embeddings.create(model=model, input=safe_input, **kwargs)


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _bytes_to_hex(b) -> str:
    if b is None:
        return ""
    if isinstance(b, str):
        return b
    if isinstance(b, (bytes, bytearray, memoryview)):
        return bytes(b).hex()
    return str(b)


def _row_to_prompt(row: dict) -> Prompt:
    return Prompt(
        prompt_id=str(row["prompt_id"]),
        name=row["name"],
        version=row["version"],
        content=row["content"],
        content_hash_hex=_bytes_to_hex(row.get("content_hash")),
        purpose=row.get("purpose"),
        model_pref=row.get("model_pref"),
        max_tokens=row.get("max_tokens"),
        created_by_user_id=str(row["created_by_user_id"]) if row.get("created_by_user_id") else None,
        created_at=row.get("created_at"),
    )


def hash_content(content: str) -> bytes:
    return hashlib.sha256(content.encode("utf-8")).digest()


# ────────────────────────────────────────────────────────────────────
# Prompt registry
# ────────────────────────────────────────────────────────────────────

class PromptRegistry:
    """Stateless service. All methods take db on each call."""

    @staticmethod
    def register(
        db,
        *,
        name: str,
        content: str,
        purpose: Optional[str] = None,
        model_pref: Optional[str] = None,
        max_tokens: Optional[int] = None,
        created_by_user_id: Optional[str] = None,
    ) -> Prompt:
        """Register or return existing prompt.

        Idempotency:
          - Same (name, content) → returns existing row (200 from route)
          - Same name, different content → new row with version = max + 1

        Raises ValueError on bad input.
        """
        if not name or not name.strip():
            raise ValueError("name required")
        if len(name) > MAX_PROMPT_NAME_LEN:
            raise ValueError(f"name exceeds {MAX_PROMPT_NAME_LEN} chars")
        if not name.replace(".", "").replace("_", "").replace("-", "").isalnum():
            raise ValueError("name must be alphanumeric (with .-_ allowed)")
        if not content or not content.strip():
            raise ValueError("content required")
        if len(content.encode("utf-8")) > MAX_PROMPT_CONTENT_BYTES:
            raise ValueError(f"content exceeds {MAX_PROMPT_CONTENT_BYTES} bytes")
        if max_tokens is not None and (max_tokens <= 0 or max_tokens > 100_000):
            raise ValueError("max_tokens must be in (0, 100000]")

        c_hash = hash_content(content)

        # Idempotency: same (name, content_hash) → existing row
        existing = db.fetch_one(
            """
            SELECT prompt_id, name, version, content, content_hash,
                   purpose, model_pref, max_tokens, created_by_user_id, created_at
              FROM prompt_registry
             WHERE name = %s AND content_hash = %s
             LIMIT 1
            """,
            (name, c_hash),
        )
        if existing:
            return _row_to_prompt(existing)

        # New version: max(version) + 1 for this name
        latest = db.fetch_one(
            "SELECT COALESCE(MAX(version), 0) AS max_v FROM prompt_registry WHERE name = %s",
            (name,),
        )
        next_version = (latest["max_v"] if latest else 0) + 1

        row = db.fetch_one(
            """
            INSERT INTO prompt_registry (
                name, version, content, content_hash, purpose,
                model_pref, max_tokens, created_by_user_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING prompt_id, name, version, content, content_hash,
                      purpose, model_pref, max_tokens, created_by_user_id, created_at
            """,
            (name, next_version, content, c_hash, purpose,
             model_pref, max_tokens, created_by_user_id),
        )
        if not row:
            raise RuntimeError("register: insert returned no row")
        return _row_to_prompt(row)

    @staticmethod
    def get(db, prompt_id: str) -> Optional[Prompt]:
        row = db.fetch_one(
            """
            SELECT prompt_id, name, version, content, content_hash,
                   purpose, model_pref, max_tokens, created_by_user_id, created_at
              FROM prompt_registry
             WHERE prompt_id::text = %s
            """,
            (str(prompt_id),),
        )
        return _row_to_prompt(row) if row else None

    @staticmethod
    def get_latest(db, name: str) -> Optional[Prompt]:
        row = db.fetch_one(
            """
            SELECT prompt_id, name, version, content, content_hash,
                   purpose, model_pref, max_tokens, created_by_user_id, created_at
              FROM prompt_registry
             WHERE name = %s
             ORDER BY version DESC
             LIMIT 1
            """,
            (name,),
        )
        return _row_to_prompt(row) if row else None

    @staticmethod
    def get_by_name_version(db, name: str, version: int) -> Optional[Prompt]:
        row = db.fetch_one(
            """
            SELECT prompt_id, name, version, content, content_hash,
                   purpose, model_pref, max_tokens, created_by_user_id, created_at
              FROM prompt_registry
             WHERE name = %s AND version = %s
            """,
            (name, version),
        )
        return _row_to_prompt(row) if row else None

    @staticmethod
    def list(
        db,
        *,
        name_filter: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Prompt]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be in [1, 500]")
        where = ["1=1"]
        params: list[Any] = []
        if name_filter:
            where.append("name ILIKE %s")
            params.append(f"%{name_filter}%")
        params.extend([limit, offset])
        rows = db.fetch_all(
            f"""
            SELECT prompt_id, name, version, content, content_hash,
                   purpose, model_pref, max_tokens, created_by_user_id, created_at
              FROM prompt_registry
             WHERE {' AND '.join(where)}
             ORDER BY name ASC, version DESC
             LIMIT %s OFFSET %s
            """,
            tuple(params),
        ) or []
        return [_row_to_prompt(r) for r in rows]


# ────────────────────────────────────────────────────────────────────
# Gateway invoke
# ────────────────────────────────────────────────────────────────────

@dataclass
class InvokeResult:
    response: Optional[str]
    prompt_id: str
    prompt_name: str
    prompt_version: int
    model_used: Optional[str]
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    cost_estimate_usd: float
    pii_redactions: list[PIIMatch] = field(default_factory=list)
    succeeded: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "response": self.response,
            "prompt_id": str(self.prompt_id),
            "prompt_name": self.prompt_name,
            "prompt_version": self.prompt_version,
            "model_used": self.model_used,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_estimate_usd": round(self.cost_estimate_usd, 6),
            "pii_redactions": [m.to_dict() for m in self.pii_redactions],
            "succeeded": self.succeeded,
            "error": self.error,
        }


class LLMGateway:
    """Routes invocation through the registry + PII filter + telemetry path."""

    @staticmethod
    def invoke(
        db,
        llm,
        *,
        prompt: str,                            # name or prompt_id (UUID)
        variables: Optional[dict] = None,
        user_message: Optional[str] = None,
        version: Optional[int] = None,          # explicit version pin
        model_pref: Optional[str] = None,       # invoke-time override
        max_tokens: Optional[int] = None,
        pii_policy: str = "redact",
        user_id: Optional[str] = None,
        caller: str = "llm_gateway",
    ) -> InvokeResult:
        """Resolve prompt, render template, scan PII, invoke chat_with_telemetry,
        return result with telemetry baked in."""
        if pii_policy not in VALID_PII_POLICIES:
            raise ValueError(f"pii_policy must be one of {sorted(VALID_PII_POLICIES)}")

        # Resolve prompt by UUID or name (+ optional version)
        resolved: Optional[Prompt] = None
        if _looks_like_uuid(prompt):
            resolved = PromptRegistry.get(db, prompt)
        else:
            if version is not None:
                resolved = PromptRegistry.get_by_name_version(db, prompt, version)
            else:
                resolved = PromptRegistry.get_latest(db, prompt)
        if not resolved:
            raise PromptNotFound(prompt)

        # Render template
        try:
            system_text = render_template(resolved.content, variables or {})
        except TemplateError:
            raise

        # PII scan + apply policy
        scan_target = system_text + ("\n" + (user_message or "") if user_message else "")
        matches = scan_pii(scan_target)
        if matches:
            if pii_policy == "reject":
                raise PIIRejected(matches)
            if pii_policy == "redact":
                system_text = redact_pii(system_text)
                if user_message:
                    user_message = redact_pii(user_message)

        # Resolve model + budget
        effective_model = model_pref or resolved.model_pref
        effective_max_tokens = max_tokens or resolved.max_tokens or DEFAULT_MAX_TOKENS

        # Delegate to existing telemetry wrapper. We need to pass a `caller`
        # that carries the prompt_id so log_llm_call can persist it.
        from services.llm_telemetry import chat_with_telemetry, log_llm_call, _est_tokens, _estimate_cost_usd
        import time

        # Override the inner log_llm_call call: use chat_with_telemetry's
        # raw call without auto-logging (it always logs), then log ourselves
        # with the prompt_id field. To keep this simple we just call
        # chat_with_telemetry but add a follow-up update isn't possible.
        # Strategy: bypass chat_with_telemetry's built-in log and replicate
        # the timeout+telemetry logic here, this time with prompt_id.

        if llm is None or not getattr(llm, "enabled", False):
            return InvokeResult(
                response=None,
                prompt_id=resolved.prompt_id,
                prompt_name=resolved.name,
                prompt_version=resolved.version,
                model_used=effective_model,
                latency_ms=0,
                prompt_tokens=0,
                completion_tokens=0,
                cost_estimate_usd=0.0,
                pii_redactions=matches,
                succeeded=False,
                error="llm_disabled",
            )

        import concurrent.futures
        t0 = time.perf_counter()
        text: Optional[str] = None
        error: Optional[str] = None

        def _invoke() -> Optional[str]:
            return llm.raw_chat(
                system=system_text,
                user=(user_message or ""),
                max_tokens=effective_max_tokens,
                temperature=0.2,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_invoke)
            try:
                text = future.result(timeout=45.0)
            except concurrent.futures.TimeoutError:
                error = "timeout after 45.0s"
            except Exception as exc:
                error = str(exc)[:500]

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        succeeded = bool(text)
        prompt_tokens = _est_tokens(system_text + "\n" + (user_message or ""))
        completion_tokens = _est_tokens(text or "")

        # Persist with prompt_id
        try:
            cost = _estimate_cost_usd(effective_model, prompt_tokens, completion_tokens)
            db.execute(
                """INSERT INTO llm_call_log
                       (caller, model, prompt_version, user_id, latency_ms,
                        prompt_tokens, completion_tokens, cost_estimate_usd,
                        succeeded, error_message, prompt_id)
                   VALUES (%s, %s, %s, %s::uuid, %s, %s, %s, %s, %s, %s, %s::uuid)""",
                [
                    caller, effective_model, f"{resolved.name}:v{resolved.version}",
                    user_id, elapsed_ms, prompt_tokens, completion_tokens, cost,
                    succeeded, error, resolved.prompt_id,
                ],
            )
        except Exception as exc:
            logger.warning("llm_call_log insert failed: %s", exc)
            cost = _estimate_cost_usd(effective_model, prompt_tokens, completion_tokens)

        return InvokeResult(
            response=text,
            prompt_id=resolved.prompt_id,
            prompt_name=resolved.name,
            prompt_version=resolved.version,
            model_used=effective_model,
            latency_ms=elapsed_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_estimate_usd=cost,
            pii_redactions=matches,
            succeeded=succeeded,
            error=error,
        )


def _looks_like_uuid(s: str) -> bool:
    if not s or len(s) != 36:
        return False
    try:
        import uuid
        uuid.UUID(s)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


# ────────────────────────────────────────────────────────────────────
# Cost summary
# ────────────────────────────────────────────────────────────────────

VALID_GROUP_BY = {"caller", "model", "day", "user", "prompt_id"}


def cost_summary(
    db,
    *,
    since: Optional[date] = None,
    until: Optional[date] = None,
    group_by: str = "caller",
) -> dict:
    """Aggregate llm_call_log over [since, until). Returns
    `{since, until, group_by, total_usd, total_calls, buckets[]}`.
    Default range is the last 7 days."""
    if group_by not in VALID_GROUP_BY:
        raise ValueError(f"group_by must be one of {sorted(VALID_GROUP_BY)}")

    today = datetime.now(timezone.utc).date()
    if until is None:
        until = today
    if since is None:
        from datetime import timedelta
        since = until - timedelta(days=7)
    if since > until:
        raise ValueError("since must be <= until")

    # group_by mapping → SQL expression. Whitelisted to avoid injection.
    group_sql = {
        "caller":    "caller",
        "model":     "COALESCE(model, 'unknown')",
        "day":       "(created_at::date)::text",
        "user":      "COALESCE(user_id::text, 'anonymous')",
        "prompt_id": "COALESCE(prompt_id::text, 'unregistered')",
    }[group_by]

    rows = db.fetch_all(
        f"""
        SELECT {group_sql} AS bucket,
               COUNT(*) AS calls,
               SUM(cost_estimate_usd) AS total_usd,
               AVG(latency_ms) AS avg_latency_ms,
               SUM(prompt_tokens) AS total_prompt_tokens,
               SUM(completion_tokens) AS total_completion_tokens
          FROM llm_call_log
         WHERE created_at >= %s
           AND created_at < (%s::date + INTERVAL '1 day')
         GROUP BY 1
         ORDER BY total_usd DESC NULLS LAST
        """,
        (since, until),
    ) or []

    buckets = []
    total_usd = 0.0
    total_calls = 0
    for r in rows:
        usd = float(r.get("total_usd") or 0.0)
        calls = int(r.get("calls") or 0)
        total_usd += usd
        total_calls += calls
        buckets.append({
            "key": r["bucket"],
            "calls": calls,
            "total_usd": round(usd, 6),
            "avg_latency_ms": float(r.get("avg_latency_ms") or 0.0),
            "total_prompt_tokens": int(r.get("total_prompt_tokens") or 0),
            "total_completion_tokens": int(r.get("total_completion_tokens") or 0),
        })

    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "group_by": group_by,
        "total_usd": round(total_usd, 6),
        "total_calls": total_calls,
        "buckets": buckets,
    }
