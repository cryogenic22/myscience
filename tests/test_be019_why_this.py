"""BE-19 — /why-this explanation tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# explainer service
# ════════════════════════════════════════════════════════════════════

class TestExplainTemplateFallback:
    def test_unknown_surface_raises(self):
        from services.explainer import ExplanationRequest, explain
        with pytest.raises(ValueError, match="unknown surface"):
            explain(ExplanationRequest(surface="bogus", item_id="x"))

    def test_no_llm_uses_template(self):
        from services.explainer import ExplanationRequest, explain
        req = ExplanationRequest(
            surface="pulse", item_id="sig-1",
            context={
                "headline": "Tirzepatide Phase 3 readout positive",
                "materiality_score": 87,
                "source_name": "ClinicalTrials.gov",
            },
        )
        out = explain(req, llm=None)
        assert out.method == "template"
        text = out.explanation_paragraph
        assert "Pulse" in text or "scored" in text.lower()
        assert "87" in text
        assert "Tirzepatide" in text

    def test_template_handles_missing_optional_fields(self):
        from services.explainer import ExplanationRequest, explain
        out = explain(
            ExplanationRequest(surface="trigger_fire", item_id="trig-1"),
            llm=None,
        )
        assert out.method == "template"
        assert out.explanation_paragraph.endswith(".")


class TestDeepLinks:
    def test_pulse_emits_factor_breakdown_url(self):
        from services.explainer import ExplanationRequest, explain
        out = explain(
            ExplanationRequest(
                surface="pulse", item_id="sig-1",
                context={"materiality_score": 80, "source_id": "fda"},
            ),
            llm=None,
        )
        assert "factor_breakdown_url" in out.deep_links
        assert "source_registry_url" in out.deep_links
        assert "/sig-1/" in out.deep_links["factor_breakdown_url"]

    def test_trigger_fire_emits_trigger_config_url(self):
        from services.explainer import ExplanationRequest, explain
        out = explain(
            ExplanationRequest(
                surface="trigger_fire", item_id="fire-1",
                context={"trigger_id": "trig-42"},
            ),
            llm=None,
        )
        assert out.deep_links.get("trigger_config_url", "").endswith("trig-42")

    def test_no_id_means_no_link(self):
        from services.explainer import ExplanationRequest, explain
        # Pulse without source_id → no source registry link
        out = explain(
            ExplanationRequest(surface="pulse", item_id="sig-1", context={}),
            llm=None,
        )
        # We can still get factor_breakdown if signal_id implied; without
        # any context, no links surface.
        assert "source_registry_url" not in out.deep_links


class TestLLMPath:
    def test_llm_used_when_enabled(self):
        from services.explainer import ExplanationRequest, explain

        llm = MagicMock()
        llm.enabled = True
        llm.raw_chat.return_value = "This signal matters because the FDA approval shifts the competitive landscape."

        out = explain(
            ExplanationRequest(
                surface="pulse", item_id="sig-9",
                context={"headline": "FDA approves X"},
            ),
            llm=llm,
        )
        assert out.method == "llm"
        assert "FDA approval" in out.explanation_paragraph

    def test_llm_failure_falls_back_to_template(self):
        from services.explainer import ExplanationRequest, explain

        llm = MagicMock()
        llm.enabled = True
        llm.raw_chat.side_effect = RuntimeError("model timeout")

        out = explain(
            ExplanationRequest(
                surface="pulse", item_id="sig-9",
                context={"headline": "x"},
            ),
            llm=llm,
        )
        assert out.method == "template"
        assert out.explanation_paragraph  # non-empty

    def test_empty_llm_response_falls_back(self):
        from services.explainer import ExplanationRequest, explain

        llm = MagicMock()
        llm.enabled = True
        llm.raw_chat.return_value = ""

        out = explain(
            ExplanationRequest(surface="agent_suggestion", item_id="x"),
            llm=llm,
        )
        assert out.method == "template"


# ════════════════════════════════════════════════════════════════════
# /why-this endpoint
# ════════════════════════════════════════════════════════════════════

class TestWhyThisEndpoint:
    def _client(self):
        from fastapi.testclient import TestClient
        from api.app import create_app
        from api.deps import get_llm

        app = create_app()
        # No LLM → template path
        app.dependency_overrides[get_llm] = lambda: None
        return TestClient(app)

    def test_endpoint_returns_template_when_no_llm(self):
        client = self._client()
        r = client.post(
            "/why-this",
            json={
                "surface": "pulse",
                "item_id": "sig-1",
                "context": {
                    "headline": "Tirzepatide Phase 3 readout positive",
                    "materiality_score": 90,
                },
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["method"] == "template"
        assert "explanation_paragraph" in body
        assert "deep_links" in body

    def test_endpoint_rejects_unknown_surface(self):
        client = self._client()
        r = client.post(
            "/why-this",
            json={"surface": "bogus", "item_id": "sig-1"},
        )
        assert r.status_code == 400, r.text
