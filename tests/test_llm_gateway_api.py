"""SPEC_026 — LLM Gateway tests.

Covers: prompt registry idempotency + version increment, PII detection
(email, SSN, phone, credit-card with Luhn), template rendering with
injection protection, cost summary aggregation, auth gates, and red-team
edge cases (R1-R10 from SPEC_026 §Red-team).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, date, timedelta
from unittest.mock import MagicMock

import pytest


# ────────────────────────────────────────────────────────────────────
# Pure tests (no DB, no LLM)
# ────────────────────────────────────────────────────────────────────

class TestPIIScan:
    def test_detects_email(self):
        from services.llm_gateway import scan_pii
        m = scan_pii("Contact kapil@example.com today")
        assert len(m) == 1
        assert m[0].kind == "email"
        assert m[0].original == "kapil@example.com"

    def test_detects_ssn(self):
        from services.llm_gateway import scan_pii
        m = scan_pii("SSN: 123-45-6789")
        kinds = [x.kind for x in m]
        assert "ssn" in kinds

    def test_detects_phone_us(self):
        from services.llm_gateway import scan_pii
        m = scan_pii("Call (415) 555-0100 anytime")
        kinds = [x.kind for x in m]
        assert "phone_us" in kinds

    def test_detects_valid_credit_card(self):
        """4111-1111-1111-1111 is a Luhn-valid Visa test number."""
        from services.llm_gateway import scan_pii
        m = scan_pii("Card: 4111-1111-1111-1111")
        kinds = [x.kind for x in m]
        assert "credit_card" in kinds

    def test_rejects_invalid_credit_card(self):
        """1234-5678-9012-3456 is NOT Luhn-valid; should not flag as CC."""
        from services.llm_gateway import scan_pii
        m = scan_pii("Number: 1234-5678-9012-3456 (not a real card)")
        kinds = [x.kind for x in m]
        assert "credit_card" not in kinds

    def test_overlapping_matches_dedup(self):
        from services.llm_gateway import scan_pii
        # An email contains @ which is not a phone; no overlap. Test multiple
        # distinct kinds:
        m = scan_pii("Email: a@b.com and SSN 123-45-6789")
        kinds = [x.kind for x in m]
        assert "email" in kinds and "ssn" in kinds

    def test_empty_text_returns_empty(self):
        from services.llm_gateway import scan_pii
        assert scan_pii("") == []
        assert scan_pii(None) == []

    def test_clean_text_returns_empty(self):
        from services.llm_gateway import scan_pii
        assert scan_pii("Hello world. Just normal text.") == []


class TestPIIRedact:
    def test_redact_email(self):
        from services.llm_gateway import redact_pii
        out = redact_pii("Contact kapil@example.com today")
        assert "kapil@example.com" not in out
        assert "[EMAIL]" in out

    def test_redact_multiple(self):
        from services.llm_gateway import redact_pii
        out = redact_pii("Email a@b.com SSN 111-22-3333")
        assert "[EMAIL]" in out
        assert "[SSN]" in out
        assert "a@b.com" not in out
        assert "111-22-3333" not in out

    def test_redact_preserves_surrounding(self):
        from services.llm_gateway import redact_pii
        out = redact_pii("X email a@b.com Y")
        assert out.startswith("X")
        assert out.endswith("Y")


class TestTemplate:
    def test_simple_substitution(self):
        from services.llm_gateway import render_template
        assert render_template("Hello {{name}}!", {"name": "world"}) == "Hello world!"

    def test_multiple_vars(self):
        from services.llm_gateway import render_template
        out = render_template("{{a}} + {{b}} = {{c}}", {"a": "1", "b": "2", "c": 3})
        assert out == "1 + 2 = 3"

    def test_missing_var_raises(self):
        from services.llm_gateway import render_template, TemplateError
        with pytest.raises(TemplateError) as exc_info:
            render_template("Hello {{name}}!", {})
        assert "name" in exc_info.value.missing

    def test_no_recursive_expansion(self):
        """R1: A variable value that itself looks like a template must NOT be
        re-rendered. This blocks template injection."""
        from services.llm_gateway import render_template
        out = render_template("Reply: {{user_input}}", {
            "user_input": "{{admin_secret}}"
        })
        # The literal string is rendered, not expanded
        assert out == "Reply: {{admin_secret}}"

    def test_extract_variables(self):
        from services.llm_gateway import extract_template_variables
        vars_ = extract_template_variables("{{a}} {{b}} {{a}} something {{c}}")
        assert vars_ == ["a", "b", "c"]

    def test_template_with_whitespace(self):
        from services.llm_gateway import render_template
        assert render_template("X{{ name }}Y", {"name": "Z"}) == "XZY"


class TestHash:
    def test_hash_content_deterministic(self):
        from services.llm_gateway import hash_content
        assert hash_content("hello") == hash_content("hello")
        assert hash_content("hello") != hash_content("Hello")

    def test_hash_returns_32_bytes(self):
        from services.llm_gateway import hash_content
        assert len(hash_content("anything")) == 32


class TestLuhn:
    def test_valid_visa(self):
        from services.llm_gateway import _luhn_valid
        assert _luhn_valid("4111111111111111")
        assert _luhn_valid("4111-1111-1111-1111")

    def test_invalid(self):
        from services.llm_gateway import _luhn_valid
        assert not _luhn_valid("1234567890123456")

    def test_too_short(self):
        from services.llm_gateway import _luhn_valid
        assert not _luhn_valid("411111")


# ────────────────────────────────────────────────────────────────────
# Fake DB for API tests
# ────────────────────────────────────────────────────────────────────

def _make_db():
    from services.auth import hash_password

    users = {
        "viewer@test.io": {
            "id": "uuid-viewer", "email": "viewer@test.io",
            "password_hash": hash_password("demo"), "role": "viewer", "is_active": True,
        },
        "editor@test.io": {
            "id": "uuid-editor", "email": "editor@test.io",
            "password_hash": hash_password("demo"), "role": "uploader", "is_active": True,
        },
    }

    prompts: dict[str, dict] = {}
    llm_calls: list[dict] = []
    next_id = [1]

    def _gen(prefix):
        n = next_id[0]; next_id[0] += 1
        return f"{prefix}-{n:04d}"

    def fake_fetch_one(sql, params=None):
        s = (sql or "").lower()

        if "from users" in s and params:
            if "where lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id::text" in s or "where id =" in s:
                for u in users.values():
                    if u["id"] == params[0]: return u
                return None

        # Existence check by name + content_hash
        if (
            "from prompt_registry" in s
            and "name = %s and content_hash = %s" in s
            and params
        ):
            target_name = params[0]
            target_hash = bytes(params[1]) if isinstance(params[1], (bytes, bytearray, memoryview)) else params[1]
            for p in prompts.values():
                if p["name"] == target_name and bytes(p["content_hash"]) == target_hash:
                    return p
            return None

        # max version lookup
        if "coalesce(max(version), 0) as max_v" in s and params:
            target_name = params[0]
            v = max((p["version"] for p in prompts.values() if p["name"] == target_name), default=0)
            return {"max_v": v}

        # INSERT prompt RETURNING
        if "insert into prompt_registry" in s and "returning" in s and params:
            pid = _gen("pmt")
            row = {
                "prompt_id": pid,
                "name": params[0],
                "version": params[1],
                "content": params[2],
                "content_hash": bytes(params[3]) if isinstance(params[3], (bytes, bytearray, memoryview)) else params[3],
                "purpose": params[4],
                "model_pref": params[5],
                "max_tokens": params[6],
                "created_by_user_id": params[7],
                "created_at": datetime.now(timezone.utc),
            }
            prompts[pid] = row
            return row

        # Get prompt by id
        if "from prompt_registry" in s and "prompt_id::text = %s" in s and params:
            return prompts.get(str(params[0]))

        # Get latest by name
        if (
            "from prompt_registry" in s
            and "where name = %s" in s
            and "order by version desc" in s
            and params
        ):
            cands = [p for p in prompts.values() if p["name"] == params[0]]
            if not cands: return None
            return max(cands, key=lambda p: p["version"])

        # Get by name + version
        if (
            "from prompt_registry" in s
            and "where name = %s and version = %s" in s
            and params
        ):
            for p in prompts.values():
                if p["name"] == params[0] and p["version"] == params[1]:
                    return p
            return None

        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()

        # LIST prompts
        if "from prompt_registry" in s and "limit" in s:
            out = list(prompts.values())
            if params:
                idx = 0
                if "name ilike %s" in s:
                    needle = params[idx].replace("%", "").lower()
                    out = [p for p in out if needle in p["name"].lower()]
                    idx += 1
                limit = params[-2]; offset = params[-1]
                out = sorted(out, key=lambda p: (p["name"], -p["version"]))
                out = out[offset:offset + limit]
            return out

        # cost summary aggregation
        if "from llm_call_log" in s and "group by 1" in s and params:
            since, until = params[0], params[1]
            buckets: dict[str, dict] = {}
            for c in llm_calls:
                ts = c.get("created_at")
                if ts is None: continue
                ts_date = ts.date() if hasattr(ts, "date") else ts
                if ts_date < since or ts_date > until: continue
                if "caller" in s.split("group by")[0]:
                    key = c.get("caller") or "unknown"
                elif "model" in s.split("group by")[0]:
                    key = c.get("model") or "unknown"
                elif "created_at::date" in s:
                    key = ts_date.isoformat()
                elif "user_id::text" in s:
                    key = str(c.get("user_id") or "anonymous")
                elif "prompt_id::text" in s:
                    key = str(c.get("prompt_id") or "unregistered")
                else:
                    key = "unknown"
                b = buckets.setdefault(key, {
                    "bucket": key, "calls": 0, "total_usd": 0.0,
                    "avg_latency_ms": 0.0, "lat_sum": 0.0,
                    "total_prompt_tokens": 0, "total_completion_tokens": 0,
                })
                b["calls"] += 1
                b["total_usd"] += c.get("cost_estimate_usd") or 0.0
                b["lat_sum"] += c.get("latency_ms") or 0.0
                b["total_prompt_tokens"] += c.get("prompt_tokens") or 0
                b["total_completion_tokens"] += c.get("completion_tokens") or 0
            out = []
            for b in buckets.values():
                b["avg_latency_ms"] = b["lat_sum"] / max(b["calls"], 1)
                del b["lat_sum"]
                out.append(b)
            out.sort(key=lambda x: -x["total_usd"])
            return out

        return []

    def fake_execute(sql, params=None):
        s = (sql or "").lower()
        if "insert into llm_call_log" in s and params:
            llm_calls.append({
                "caller": params[0],
                "model": params[1],
                "prompt_version": params[2],
                "user_id": params[3],
                "latency_ms": params[4],
                "prompt_tokens": params[5],
                "completion_tokens": params[6],
                "cost_estimate_usd": params[7],
                "succeeded": params[8],
                "error_message": params[9],
                "prompt_id": params[10] if len(params) > 10 else None,
                "created_at": datetime.now(timezone.utc),
            })
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = fake_execute
    return db, prompts, llm_calls


def _client(db):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _login(client, email):
    r = client.post("/auth/login", json={"email": email, "password": "demo"})
    return r.json().get("access_token", "") if r.status_code == 200 else ""


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"} if tok else {}


# ────────────────────────────────────────────────────────────────────
# Module + route registration
# ────────────────────────────────────────────────────────────────────

def test_module_imports():
    from api.routes import llm_gateway as r
    from services.llm_gateway import LLMGateway, PromptRegistry, scan_pii
    assert r.router.prefix == "/llm-gateway"


def test_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/llm-gateway/prompts" in paths
    assert "/llm-gateway/prompts/{prompt_id}" in paths
    assert "/llm-gateway/invoke" in paths
    assert "/llm-gateway/scan-pii" in paths
    assert "/llm-gateway/cost-summary" in paths


# ────────────────────────────────────────────────────────────────────
# Prompt registry
# ────────────────────────────────────────────────────────────────────

def test_register_prompt_minimal():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/llm-gateway/prompts", json={
        "name": "test.simple",
        "content": "Hello {{name}}",
    }, headers=_hdr(tok))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "test.simple"
    assert body["version"] == 1
    assert body["content"] == "Hello {{name}}"
    assert body["variables"] == ["name"]


def test_register_idempotent_same_content():
    """Same name + same content → same prompt_id (idempotent)."""
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    payload = {"name": "test.idem", "content": "Hello {{x}}"}
    r1 = client.post("/llm-gateway/prompts", json=payload, headers=_hdr(tok))
    r2 = client.post("/llm-gateway/prompts", json=payload, headers=_hdr(tok))
    assert r1.json()["prompt_id"] == r2.json()["prompt_id"]
    assert r1.json()["version"] == r2.json()["version"] == 1


def test_register_new_version_when_content_changes():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r1 = client.post("/llm-gateway/prompts", json={
        "name": "test.v", "content": "v1 content"
    }, headers=_hdr(tok)).json()
    r2 = client.post("/llm-gateway/prompts", json={
        "name": "test.v", "content": "v2 content (different)"
    }, headers=_hdr(tok)).json()
    assert r1["version"] == 1
    assert r2["version"] == 2
    assert r1["prompt_id"] != r2["prompt_id"]


def test_register_rejects_bad_name():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    # Special chars not in [.-_]
    r = client.post("/llm-gateway/prompts", json={
        "name": "bad name!", "content": "x"
    }, headers=_hdr(tok))
    assert r.status_code == 400


def test_register_rejects_oversized_content():
    """R7: cap content at 32KB."""
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    huge = "x" * 40000
    r = client.post("/llm-gateway/prompts", json={
        "name": "test.huge", "content": huge
    }, headers=_hdr(tok))
    assert r.status_code == 422


def test_get_prompt_by_id():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    p = client.post("/llm-gateway/prompts", json={
        "name": "test.get", "content": "abc"
    }, headers=_hdr(tok)).json()

    vtok = _login(client, "viewer@test.io")
    r = client.get(f"/llm-gateway/prompts/{p['prompt_id']}", headers=_hdr(vtok))
    assert r.status_code == 200
    assert r.json()["name"] == "test.get"


def test_list_prompts_with_filter():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    client.post("/llm-gateway/prompts", json={"name": "war_game.x", "content": "a"}, headers=_hdr(tok))
    client.post("/llm-gateway/prompts", json={"name": "war_game.y", "content": "b"}, headers=_hdr(tok))
    client.post("/llm-gateway/prompts", json={"name": "framing.z", "content": "c"}, headers=_hdr(tok))

    vtok = _login(client, "viewer@test.io")
    r = client.get("/llm-gateway/prompts?name=war_game", headers=_hdr(vtok))
    body = r.json()
    assert body["count"] == 2
    assert all("war_game" in p["name"] for p in body["prompts"])


# ────────────────────────────────────────────────────────────────────
# Invoke (with disabled LLM — exercises validation paths only)
# ────────────────────────────────────────────────────────────────────

def test_invoke_404_for_unknown_prompt():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/llm-gateway/invoke", json={
        "prompt": "does.not.exist",
        "variables": {},
    }, headers=_hdr(tok))
    assert r.status_code == 404


def test_invoke_400_for_missing_variables():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    p = client.post("/llm-gateway/prompts", json={
        "name": "test.vars", "content": "Hello {{name}} {{role}}"
    }, headers=_hdr(tok)).json()

    r = client.post("/llm-gateway/invoke", json={
        "prompt": p["name"],
        "variables": {"name": "Alice"},  # role missing
    }, headers=_hdr(tok))
    assert r.status_code == 400
    assert "role" in r.json().get("detail", "").lower()


def test_invoke_409_for_pii_with_reject_policy():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    p = client.post("/llm-gateway/prompts", json={
        "name": "test.pii", "content": "Reply to {{msg}}"
    }, headers=_hdr(tok)).json()

    r = client.post("/llm-gateway/invoke", json={
        "prompt": p["name"],
        "variables": {"msg": "Email me at foo@bar.com"},
        "pii_policy": "reject",
    }, headers=_hdr(tok))
    assert r.status_code == 409
    assert "email" in r.json().get("detail", "").lower()


def test_invoke_returns_envelope_with_telemetry():
    """Invoke returns the standard envelope with prompt_id, model_used,
    latency, tokens, cost, regardless of whether the LLM is enabled in
    the test env. (When LLM is disabled, succeeded=False + error='llm_disabled'.)"""
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    p = client.post("/llm-gateway/prompts", json={
        "name": "test.noop", "content": "ping"
    }, headers=_hdr(tok)).json()

    r = client.post("/llm-gateway/invoke", json={
        "prompt": p["name"], "variables": {}
    }, headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    # Envelope shape — these are the contract
    assert "response" in body
    assert "succeeded" in body
    assert body["prompt_id"] == p["prompt_id"]
    assert body["prompt_name"] == p["name"]
    assert body["prompt_version"] == p["version"]
    assert "latency_ms" in body
    assert "prompt_tokens" in body
    assert "completion_tokens" in body
    assert "cost_estimate_usd" in body
    assert "pii_redactions" in body


# ────────────────────────────────────────────────────────────────────
# Scan PII endpoint
# ────────────────────────────────────────────────────────────────────

def test_scan_pii_endpoint_finds_email():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/llm-gateway/scan-pii", json={
        "text": "Send to alice@example.com please"
    }, headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["match_count"] == 1
    assert "[EMAIL]" in body["redacted"]


def test_scan_pii_endpoint_clean_text():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/llm-gateway/scan-pii", json={
        "text": "Just normal product names like Tirzepatide"
    }, headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["match_count"] == 0


# ────────────────────────────────────────────────────────────────────
# Cost summary
# ────────────────────────────────────────────────────────────────────

def test_cost_summary_empty_returns_zeroes():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/llm-gateway/cost-summary", headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["total_usd"] == 0.0
    assert body["total_calls"] == 0
    assert body["buckets"] == []
    assert body["group_by"] == "caller"


def test_cost_summary_aggregates_calls():
    db, _, llm_calls = _make_db()
    # Seed some calls directly
    today = datetime.now(timezone.utc)
    llm_calls.extend([
        {"caller": "war_game", "model": "gpt-4o", "cost_estimate_usd": 0.01,
         "latency_ms": 100, "prompt_tokens": 100, "completion_tokens": 50,
         "created_at": today, "user_id": None, "prompt_id": None},
        {"caller": "war_game", "model": "gpt-4o", "cost_estimate_usd": 0.02,
         "latency_ms": 200, "prompt_tokens": 100, "completion_tokens": 50,
         "created_at": today, "user_id": None, "prompt_id": None},
        {"caller": "framing", "model": "gpt-4o-mini", "cost_estimate_usd": 0.001,
         "latency_ms": 50, "prompt_tokens": 50, "completion_tokens": 25,
         "created_at": today, "user_id": None, "prompt_id": None},
    ])
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/llm-gateway/cost-summary", headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["total_calls"] == 3
    assert body["total_usd"] == round(0.01 + 0.02 + 0.001, 6)
    # Sorted by total_usd DESC
    assert body["buckets"][0]["key"] == "war_game"
    assert body["buckets"][0]["calls"] == 2
    assert body["buckets"][0]["total_usd"] == 0.03


def test_cost_summary_invalid_group_by():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/llm-gateway/cost-summary?group_by=foobar", headers=_hdr(tok))
    assert r.status_code == 400


# ────────────────────────────────────────────────────────────────────
# Auth
# ────────────────────────────────────────────────────────────────────

def test_register_requires_uploader():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/llm-gateway/prompts", json={"name": "x", "content": "y"},
                    headers=_hdr(tok))
    assert r.status_code in (401, 403)


def test_invoke_requires_uploader():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/llm-gateway/invoke", json={"prompt": "x"}, headers=_hdr(tok))
    assert r.status_code in (401, 403)


def test_unauth_list_prompts():
    db, _, _ = _make_db()
    client = _client(db)
    r = client.get("/llm-gateway/prompts")
    assert r.status_code in (401, 403)


def test_unauth_cost_summary():
    db, _, _ = _make_db()
    client = _client(db)
    r = client.get("/llm-gateway/cost-summary")
    assert r.status_code in (401, 403)


# ────────────────────────────────────────────────────────────────────
# Red-team
# ────────────────────────────────────────────────────────────────────

def test_R1_template_injection_does_not_expand_user_value():
    """R1: A user-supplied variable value containing {{X}} must NOT be
    re-rendered. Verified at the API level — the rendered system message
    that goes to the LLM contains the literal string."""
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    p = client.post("/llm-gateway/prompts", json={
        "name": "test.inject",
        "content": "User said: {{user_input}}"
    }, headers=_hdr(tok)).json()

    # Invoke with a value that itself looks like a template
    r = client.post("/llm-gateway/invoke", json={
        "prompt": p["name"],
        "variables": {"user_input": "{{secret_admin_prompt}}"},
    }, headers=_hdr(tok))
    # Template should render fine (no missing-var error since the 'secret'
    # var would only be missing if recursion happened)
    assert r.status_code == 200, r.text
    # LLM is disabled in tests; the test passes if no recursive rendering
    # happened (which would have caused a "missing template variables:
    # ['secret_admin_prompt']" 400)


def test_R5_sql_injection_via_name_filter():
    """R5: SQL injection via list name filter is parameterized — round-trips."""
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/llm-gateway/prompts?name='%20OR%201=1--", headers=_hdr(tok))
    # Even with malicious filter, it just doesn't match anything.
    # Critical: didn't 500.
    assert r.status_code == 200
    assert r.json()["count"] == 0
