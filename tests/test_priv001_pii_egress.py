"""PRIV-001 — the direct synthesis path must not egress PII to the model.

The primary synthesis calls in services/llm.py hit OpenAI directly, bypassing
LLMGateway's PII filter, so evidence text (investigator emails/phones, forwarded
web-result snippets) left the process unredacted. These tests pin that every
direct provider call now routes its outbound prompt through the same scan/redact
policy the gateway enforces — captured at the real call site, not just the helper.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.llm import LLMSynthesizer
from services.llm_gateway import PIIRejected


EMAIL = "jane.investigator@hospital.org"
PHONE = "(415) 555-0142"


def _make_config(pii_policy="redact"):
    return SimpleNamespace(
        llm=SimpleNamespace(
            enabled=True, api_key="sk-test", model="gpt-4o-mini",
            fallback_model="gpt-4o-mini", max_tokens=400, temperature=0.2,
            ctx_mode="ctx", pii_policy=pii_policy,
        )
    )


class _Capturing:
    """Fake OpenAI client that records the messages of the last create() call
    and can serve both streaming and non-streaming shapes."""

    def __init__(self, reply="ok"):
        self.reply = reply
        self.calls: list[list[dict]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs["messages"])
        if kwargs.get("stream"):
            def _gen():
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=self.reply))]
                )
            return _gen()
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))]
        )

    @property
    def last_outbound_text(self) -> str:
        return "\n".join(m["content"] for m in self.calls[-1])


def _synth(pii_policy="redact", reply="A narrative."):
    llm = LLMSynthesizer(_make_config(pii_policy))
    cap = _Capturing(reply=reply)
    llm._client = cap
    return llm, cap


# ── the helper in isolation ──────────────────────────────────────────

def test_redact_outbound_redacts_email_and_phone():
    llm, _ = _synth()
    out = llm._redact_outbound([{"role": "user", "content": f"call {PHONE} or {EMAIL}"}])
    assert EMAIL not in out[0]["content"] and PHONE not in out[0]["content"]
    assert "[EMAIL]" in out[0]["content"] and "[PHONE_US]" in out[0]["content"]


def test_redact_outbound_does_not_mutate_input():
    llm, _ = _synth()
    src = [{"role": "user", "content": f"reach {EMAIL}"}]
    llm._redact_outbound(src)
    assert src[0]["content"] == f"reach {EMAIL}"  # original untouched


def test_redact_outbound_reject_policy_fails_closed():
    llm, _ = _synth(pii_policy="reject")
    with pytest.raises(PIIRejected):
        llm._redact_outbound([{"role": "user", "content": f"email {EMAIL}"}])


def test_redact_outbound_allow_policy_passes_through():
    llm, _ = _synth(pii_policy="allow")
    out = llm._redact_outbound([{"role": "user", "content": f"email {EMAIL}"}])
    assert out[0]["content"] == f"email {EMAIL}"


def test_redact_outbound_clean_text_unchanged():
    llm, _ = _synth()
    clean = "Semaglutide reduced HbA1c by 1.8% in SUSTAIN-6 (NCT01720446)."
    out = llm._redact_outbound([{"role": "user", "content": clean}])
    assert out[0]["content"] == clean  # no false-positive redaction


def test_missing_pii_policy_defaults_to_redact():
    # a config without pii_policy (older shape) must still redact, not leak
    cfg = SimpleNamespace(llm=SimpleNamespace(
        enabled=True, api_key="sk-test", model="m", fallback_model="m",
        max_tokens=100, temperature=0.2, ctx_mode="ctx"))
    llm = LLMSynthesizer(cfg)
    out = llm._redact_outbound([{"role": "user", "content": f"email {EMAIL}"}])
    assert "[EMAIL]" in out[0]["content"]


# ── the real call sites (the actual egress boundary) ─────────────────

def test_synthesize_redacts_evidence_pii_before_egress():
    llm, cap = _synth()
    llm.synthesize(
        question="Who ran the trial?", intent="general",
        evidence_snippets=[f"PI contact: {EMAIL}, tel {PHONE}"],
    )
    assert cap.calls, "provider was never called"
    assert EMAIL not in cap.last_outbound_text
    assert PHONE not in cap.last_outbound_text
    assert "[EMAIL]" in cap.last_outbound_text


def test_raw_chat_redacts_before_egress():
    llm, cap = _synth(reply="ok")
    llm.raw_chat(system="You are a helper.", user=f"reach me at {EMAIL}")
    assert EMAIL not in cap.last_outbound_text
    assert "[EMAIL]" in cap.last_outbound_text


def test_synthesize_stream_redacts_before_egress():
    llm, cap = _synth(reply="chunk")
    list(llm.synthesize_stream(
        question="q", intent="general",
        evidence_snippets=[f"investigator {EMAIL}"],
    ))
    assert cap.calls, "stream provider was never called"
    assert EMAIL not in cap.last_outbound_text
    assert "[EMAIL]" in cap.last_outbound_text


def test_research_brief_redacts_web_result_pii_before_egress():
    llm, cap = _synth(reply="brief")
    llm.synthesize_research_report(
        question="landscape",
        web_results=[{"title": "contact", "snippet": f"write {EMAIL}"}],
    )
    assert cap.calls, "research provider was never called"
    assert EMAIL not in cap.last_outbound_text
