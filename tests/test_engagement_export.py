"""UX12 / L8 — Executive Brief printable-HTML export tests."""
from __future__ import annotations

from services.engagement_export import (
    render_dossier_html,
    render_executive_brief_html,
)


def _render(**over):
    kw = dict(
        engagement_name="Wegovy Launch",
        asset="semaglutide",
        readiness=0.62,
        recommendation="Defend & differentiate on cardiovascular outcomes.",
        scenarios=[
            {"name": "Competitive pressure: tirzepatide", "probability": 0.73},
            {"name": "Payer step-therapy tightening", "probability": None},
        ],
        generated_label="engagement db4fe801",
    )
    kw.update(over)
    return render_executive_brief_html(**kw)


class TestExecutiveBriefHtml:
    def test_is_a_full_html_doc_with_print_css(self):
        doc = _render()
        assert doc.lstrip().startswith("<!DOCTYPE html>")
        assert "@media print" in doc
        assert "@page" in doc

    def test_includes_engagement_asset_and_readiness(self):
        doc = _render()
        assert "Wegovy Launch" in doc
        assert "semaglutide" in doc
        assert "62%" in doc                      # 0.62 → 62%

    def test_renders_recommendation_and_scenarios(self):
        doc = _render()
        assert "Defend &amp; differentiate" in doc   # escaped &
        assert "Competitive pressure: tirzepatide" in doc
        assert "73% likely" in doc

    def test_escapes_dynamic_text(self):
        doc = _render(engagement_name="<script>evil()</script>")
        assert "<script>evil()</script>" not in doc
        assert "&lt;script&gt;" in doc

    def test_degrades_honestly_with_no_data(self):
        doc = _render(readiness=None, recommendation=None, scenarios=[])
        assert "No committed recommendation" in doc
        assert "No scenarios derived" in doc
        assert "—" in doc                        # readiness placeholder

    def test_brief_summary_optional(self):
        assert "Summary" not in _render(brief_summary=None)
        assert "Summary" in _render(brief_summary="One-line situation.")


def _render_dossier(**over):
    kw = dict(
        engagement_name="Wegovy Launch",
        asset="semaglutide",
        readiness=0.47,
        fact_count=464,
        domains=[
            {"domain": "clinical_profile", "priority": "critical", "state": "complete",
             "readiness": 1.0, "facts": [
                 {"claim": "STEP 1 — 68 weeks", "factClass": "corporate",
                  "sourceLabel": "ctgov", "sourceUrl": "https://clinicaltrials.gov/x"},
                 {"claim": "Boxed warning: thyroid", "factClass": "signal", "sourceLabel": "SPL"},
             ]},
            {"domain": "pricing_and_access", "priority": "critical", "state": "gap",
             "readiness": 0.0, "facts": []},
        ],
        generated_label="engagement db4fe801",
    )
    kw.update(over)
    return render_dossier_html(**kw)


class TestDossierHtml:
    def test_full_doc_with_print_css(self):
        doc = _render_dossier()
        assert doc.lstrip().startswith("<!DOCTYPE html>")
        assert "@media print" in doc
        assert "Intelligence Dossier" in doc

    def test_renders_domains_prettified(self):
        doc = _render_dossier()
        assert "Clinical Profile" in doc       # slug → Title Case
        assert "Pricing And Access" in doc

    def test_renders_facts_with_source_link(self):
        doc = _render_dossier()
        assert "STEP 1 — 68 weeks" in doc
        assert 'href="https://clinicaltrials.gov/x"' in doc

    def test_empty_domain_degrades(self):
        doc = _render_dossier()
        assert "No facts in this domain yet" in doc

    def test_escapes_fact_claims(self):
        doc = _render_dossier(domains=[
            {"domain": "x", "priority": "high", "state": "complete", "readiness": 1.0,
             "facts": [{"claim": "<img src=x onerror=1>", "factClass": "signal", "sourceLabel": "s"}]},
        ])
        assert "<img src=x" not in doc
        assert "&lt;img" in doc


class TestRouteRegistered:
    def test_export_routes_on_the_wire(self):
        """SL10 lesson: prove the routes are registered (not just the service)."""
        from api.app import create_app
        app = create_app()
        paths = {getattr(r, "path", "") for r in app.routes}
        assert "/engagements/{eid}/export/brief.html" in paths
        assert "/engagements/{eid}/export/dossier.html" in paths
