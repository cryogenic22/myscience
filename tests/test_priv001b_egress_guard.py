"""PRIV-001b — provider-agnostic egress guard: acceptance tests (SPEC_HANDOFF §H1.1.4).

Proves: (1) every runtime provider egress now flows through the ONE approved adapter
(the RED→GREEN driver); (2) a scan failure produces ZERO provider calls (capture test);
(3) direct and gateway paths redact the same PII fixture (parity); (4) MZ_PII_POLICY=allow
is forbidden in production.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from assurance.egress_scan import scan_keys
from services.llm_gateway import (
    guard_openai_chat,
    guard_anthropic_messages,
    guard_openai_embeddings,
    resolve_pii_policy,
    redact_pii,
    PIIRejected,
    PIIPolicyForbidden,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
_INVENTORY = json.loads(
    (REPO_ROOT / "assurance" / "contract" / "egress_inventory.json").read_text(encoding="utf-8")
)
_ADAPTER_FILE = "services/llm_gateway.py"
# Everything NOT marked APPROVED-ADAPTER is an explicitly-deferred operational script/benchmark.
_DEFERRED = {k for k, v in _INVENTORY["sites"].items() if "APPROVED-ADAPTER" not in v.get("reason", "")}


# ---- fakes that record every provider call ----
class _Sink:
    def __init__(self):
        self.calls: list[dict] = []

    def create(self, **kw):
        self.calls.append(kw)
        return dict(kw)


class FakeOpenAI:
    def __init__(self):
        self._chat = _Sink()
        self._emb = _Sink()
        self.chat = type("Chat", (), {"completions": self._chat})()
        self.embeddings = self._emb

    @property
    def chat_calls(self):
        return self._chat.calls

    @property
    def emb_calls(self):
        return self._emb.calls


class FakeAnthropic:
    def __init__(self):
        self.messages = _Sink()

    @property
    def calls(self):
        return self.messages.calls


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Neutral environment: no prod/dev markers, no policy override, unless a test sets them.
    A neutral env is now UNKNOWN (not dev) — 'allow' is fail-closed here."""
    for v in ("RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "MZ_ENV", "ENVIRONMENT",
              "APP_ENV", "MZ_PII_POLICY"):
        monkeypatch.delenv(v, raising=False)


# ============================ THE DRIVER (RED→GREEN) ============================

def test_all_provider_egress_is_inside_the_approved_adapter():
    """Before PRIV-001b wiring, 11 runtime sites lived outside the adapter (RED).
    After wiring, the only provider .create calls are the adapter + deferred scripts."""
    keys, unparseable = scan_keys(REPO_ROOT)
    assert not unparseable, f"fail-closed: unparseable files could hide egress: {unparseable}"
    outside = sorted(k for k in keys if k.split("::")[0] != _ADAPTER_FILE and k not in _DEFERRED)
    assert not outside, (
        "raw provider egress exists OUTSIDE the approved adapter (PRIV-001b incomplete) — "
        "route each through services.llm_gateway.guard_*:\n  " + "\n  ".join(outside)
    )


# ============================ Capture: scan-fail ⇒ 0 calls ======================

def test_reject_policy_makes_zero_openai_chat_calls():
    c = FakeOpenAI()
    with pytest.raises(PIIRejected):
        guard_openai_chat(c, model="m", messages=[{"role": "user", "content": "email a@b.com"}], pii_policy="reject")
    assert c.chat_calls == [], "provider was called despite a scan rejection — data would have leaked"


def test_reject_policy_makes_zero_embeddings_calls():
    c = FakeOpenAI()
    with pytest.raises(PIIRejected):
        guard_openai_embeddings(c, model="m", input="ssn 123-45-6789", pii_policy="reject")
    assert c.emb_calls == []


def test_reject_policy_makes_zero_anthropic_calls():
    c = FakeAnthropic()
    with pytest.raises(PIIRejected):
        guard_anthropic_messages(c, model="m", system="clean",
                                 messages=[{"role": "user", "content": "ssn 123-45-6789"}], pii_policy="reject")
    assert c.calls == []


# ============================ Redaction happens before the call =================

def test_openai_chat_redacts_before_call():
    c = FakeOpenAI()
    guard_openai_chat(c, model="m", messages=[{"role": "user", "content": "my ssn 123-45-6789"}], pii_policy="redact")
    assert c.chat_calls[0]["messages"][0]["content"] == "my ssn [SSN]"
    assert "123-45-6789" not in json.dumps(c.chat_calls)


def test_anthropic_redacts_system_and_messages():
    c = FakeAnthropic()
    guard_anthropic_messages(
        c, model="m", system="call 415-555-1234",
        messages=[{"role": "user", "content": "ssn 123-45-6789"}], max_tokens=16, pii_policy="redact",
    )
    dumped = json.dumps(c.calls)
    assert "415-555-1234" not in dumped and "123-45-6789" not in dumped
    assert c.calls[0]["system"] == "call [PHONE_US]"
    assert c.calls[0]["max_tokens"] == 16  # passthrough kwargs preserved


def test_embeddings_redacts_str_and_list():
    c = FakeOpenAI()
    guard_openai_embeddings(c, model="m", input="mail a@b.com", pii_policy="redact")
    assert c.emb_calls[0]["input"] == "mail [EMAIL]"
    c2 = FakeOpenAI()
    guard_openai_embeddings(c2, model="m", input=["a@b.com", "clean text"], pii_policy="redact")
    assert c2.emb_calls[0]["input"] == ["[EMAIL]", "clean text"]


# ============================ Direct vs gateway parity =========================

def test_direct_vs_gateway_redact_the_same_fixture():
    fixture = "contact a@b.com or ssn 123-45-6789 or 415-555-1234"
    c = FakeOpenAI()
    guard_openai_chat(c, model="m", messages=[{"role": "user", "content": fixture}], pii_policy="redact")
    assert c.chat_calls[0]["messages"][0]["content"] == redact_pii(fixture)


# ============================ allow forbidden in production =====================

def test_allow_forbidden_in_production(monkeypatch):
    monkeypatch.setenv("MZ_ENV", "production")
    with pytest.raises(PIIPolicyForbidden):
        resolve_pii_policy("allow")
    c = FakeOpenAI()
    with pytest.raises(PIIPolicyForbidden):
        guard_openai_chat(c, model="m", messages=[{"role": "user", "content": "x"}], pii_policy="allow")
    assert c.chat_calls == [], "allow must not reach the provider in production"


def test_allow_forbidden_on_railway_environment_name(monkeypatch):
    """The exact bypass an independent review found: Railway injects RAILWAY_ENVIRONMENT_NAME,
    not RAILWAY_ENVIRONMENT. 'allow' must be blocked when that var names production."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    with pytest.raises(PIIPolicyForbidden):
        resolve_pii_policy("allow")
    c = FakeOpenAI()
    with pytest.raises(PIIPolicyForbidden):
        guard_openai_chat(c, model="m", messages=[{"role": "user", "content": "a@b.com"}], pii_policy="allow")
    assert c.chat_calls == [], "allow must not reach the provider on Railway production"


def test_allow_forbidden_when_environment_unknown():
    """Fail closed: an unset/unknown environment is NOT permission to pass PII through.
    (Absence of a prod marker must not equal 'safe' — the Railway gap's root lesson.)"""
    with pytest.raises(PIIPolicyForbidden):
        resolve_pii_policy("allow")


def test_allow_permitted_only_with_positive_dev_designation(monkeypatch):
    """'allow' is permitted ONLY when the environment is POSITIVELY designated dev/test."""
    monkeypatch.setenv("MZ_ENV", "development")
    assert resolve_pii_policy("allow") == "allow"
    c = FakeOpenAI()
    guard_openai_chat(c, model="m", messages=[{"role": "user", "content": "a@b.com"}], pii_policy="allow")
    assert c.chat_calls[0]["messages"][0]["content"] == "a@b.com"  # allow = no redaction (dev only)


# ============================ scan failure ⇒ fail closed (0 calls) =============

@pytest.mark.parametrize("guard,client_factory,call", [
    ("chat", FakeOpenAI, lambda g, c: guard_openai_chat(c, model="m", messages=[{"role": "user", "content": "x"}], pii_policy="redact")),
    ("emb", FakeOpenAI, lambda g, c: guard_openai_embeddings(c, model="m", input="x", pii_policy="redact")),
    ("anthropic", FakeAnthropic, lambda g, c: guard_anthropic_messages(c, model="m", messages=[{"role": "user", "content": "x"}], pii_policy="redact")),
])
def test_scan_failure_fails_closed_no_provider_call(guard, client_factory, call, monkeypatch):
    """If scan_pii itself raises unexpectedly, the guard must NOT call the provider (fail closed):
    a scanner bug must never become a silent PII leak."""
    import services.llm_gateway as gw

    def boom(_text):
        raise RuntimeError("scanner blew up")
    monkeypatch.setattr(gw, "scan_pii", boom)
    c = client_factory()
    with pytest.raises(RuntimeError):
        call(guard, c)
    calls = c.chat_calls if guard == "chat" else (c.emb_calls if guard == "emb" else c.calls)
    assert calls == [], "provider was called despite a scanner failure — data would have leaked"


# ============================ LLMGateway.invoke enforces the policy =============

def test_invoke_enforces_allow_forbidden_off_dev():
    """The higher-level LLMGateway.invoke path also fails closed on 'allow' off an explicit
    dev/test env — the policy gate runs before any prompt resolution or provider call."""
    from services.llm_gateway import LLMGateway
    with pytest.raises(PIIPolicyForbidden):
        LLMGateway.invoke(None, None, prompt="anything", pii_policy="allow")


# ============================ operational scripts are really routed ============

def test_operational_scripts_are_not_deferred_anymore():
    """Blocker: the three operational scripts must be ROUTED through the guard, not left as
    allowlisted raw egress. They no longer appear in the inventory at all."""
    sites = set(_INVENTORY["sites"])
    for script in ("backfill_embeddings.py", "backfill_resolution.py", "scripts/ai_enrich.py"):
        assert not any(k.startswith(script + "::") for k in sites), f"{script} still an inventoried egress site"
    # Only the 3 adapter functions + the offline benchmark judge remain.
    assert len(sites) == 4, sorted(sites)


def test_backfill_script_call_site_fails_closed_on_pii(monkeypatch):
    """Real per-call-site capture at an operational script: with reject policy and PII in the
    row text, the wired guard rejects and the provider is never called (0 embedding calls)."""
    monkeypatch.setenv("MZ_PII_POLICY", "reject")
    import backfill_resolution

    class FakeDB:
        def __init__(self, rows):
            self._rows = rows
            self.updates = []
        def fetch_all(self, *a, **k):
            return self._rows
        def execute(self, *a, **k):
            self.updates.append((a, k))

    client = FakeOpenAI()
    db = FakeDB([{"id": 1, "generic_name": "contact a@b.com for details"}])
    backfill_resolution.backfill_new_drug_embeddings(db, client)
    assert client.emb_calls == [], "operational script reached the provider despite PII+reject"
    assert db.updates == [], "a redacted/leaked embedding was written despite rejection"


# ============================ round-3: fail-closed gaps a review found =========

def test_allow_forbidden_when_prod_marker_coexists_with_dev(monkeypatch):
    """A production marker DOMINATES a coexisting dev marker: on Railway
    RAILWAY_ENVIRONMENT_NAME=production is always injected, so ALSO setting MZ_ENV=dev must NOT
    re-enable passthrough."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    monkeypatch.setenv("MZ_ENV", "dev")
    with pytest.raises(PIIPolicyForbidden):
        resolve_pii_policy("allow")
    c = FakeOpenAI()
    with pytest.raises(PIIPolicyForbidden):
        guard_openai_chat(c, model="m", messages=[{"role": "user", "content": "ssn 123-45-6789"}], pii_policy="allow")
    assert c.chat_calls == []


def test_nested_anthropic_tool_result_is_deep_redacted():
    """PII nested inside an Anthropic tool_result content block must be redacted, not passed
    through (the shallow sanitizer failed open on this mainstream tool-use shape)."""
    c = FakeAnthropic()
    guard_anthropic_messages(
        c, model="m",
        messages=[{"role": "user", "content": [
            {"type": "tool_result", "content": [{"type": "text", "text": "ssn 123-45-6789"}]}
        ]}],
        pii_policy="redact",
    )
    dumped = json.dumps(c.calls)
    assert "123-45-6789" not in dumped and "[SSN]" in dumped


def test_nested_reject_makes_zero_calls():
    c = FakeAnthropic()
    with pytest.raises(PIIRejected):
        guard_anthropic_messages(
            c, model="m",
            messages=[{"role": "user", "content": [
                {"type": "tool_result", "content": [{"type": "text", "text": "ssn 123-45-6789"}]}
            ]}],
            pii_policy="reject",
        )
    assert c.calls == []


def test_dict_content_and_name_field_are_sanitized():
    """Non-string message content (dict) and the message `name` field are string leaves too."""
    c = FakeOpenAI()
    guard_openai_chat(
        c, model="m",
        messages=[{"role": "user", "name": "mail a@b.com",
                   "content": {"type": "text", "text": "call 415-555-1234"}}],
        pii_policy="redact",
    )
    dumped = json.dumps(c.chat_calls)
    assert "a@b.com" not in dumped and "415-555-1234" not in dumped


def test_anthropic_system_as_list_is_redacted_not_crashed():
    """system may be a list of content blocks (a valid API shape) — deep-sanitize, don't crash."""
    c = FakeAnthropic()
    guard_anthropic_messages(
        c, model="m",
        system=[{"type": "text", "text": "ssn 123-45-6789"}],
        messages=[{"role": "user", "content": "hello"}],
        pii_policy="redact",
    )
    assert "123-45-6789" not in json.dumps(c.calls)


def test_default_policy_is_redact():
    assert resolve_pii_policy() == "redact"


def test_env_policy_override_is_honored():
    import os
    os.environ["MZ_PII_POLICY"] = "reject"
    try:
        assert resolve_pii_policy() == "reject"
    finally:
        del os.environ["MZ_PII_POLICY"]
