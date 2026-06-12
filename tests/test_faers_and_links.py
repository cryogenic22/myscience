"""Lane-1: FAERS spontaneous-reporting discipline + entity-link sanitizer.

Both are deterministic synthesis-layer defences caught by live probing:
  * the safety paragraph misused FAERS (raw reaction terms, no caveat, a
    medication-error term presented as a drug property) — the PV-01 failure.
  * the model invented absolute 'https://www.example.com/entity/...' links despite
    the relative-link protocol.
"""

from services.unified_handler import _faers_safety_directive, _sanitize_entity_links


def test_faers_directive_fires_only_when_ae_facts_present():
    none = _faers_safety_directive([
        {"source": "ClinicalTrials.gov", "provenance": {"predicate": "clinical_trial"}},
    ])
    assert none == ""
    fired = _faers_safety_directive([
        {"source": "openFDA FAERS", "provenance": {"predicate": "adverse_event"}},
    ])
    low = fired.lower()
    assert "spontaneous report" in low
    assert "no denominator" in low
    assert "do not rank or compare two" in low
    assert "medication-error" in low
    assert "product dose omission" in low


def test_faers_directive_detects_ae_via_source_or_predicate():
    via_src = _faers_safety_directive([{"source": "openFDA FAERS", "provenance": {}}])
    via_pred = _faers_safety_directive([{"source": "x", "provenance": {"predicate": "adverse_event"}}])
    assert via_src and via_pred


def test_sanitize_strips_fabricated_domain_keeps_entity_path():
    n = "See [Tirzepatide](https://www.example.com/entity/drug/9da2b55d) for details."
    out = _sanitize_entity_links(n)
    assert "(/entity/drug/9da2b55d)" in out
    assert "example.com" not in out


def test_sanitize_drops_external_url_keeps_text():
    n = "Per [this study](https://example.com/some/article), results were positive."
    out = _sanitize_entity_links(n)
    assert "this study" in out
    assert "http" not in out
    assert "](" not in out  # link removed, text kept


def test_sanitize_leaves_relative_entity_links_untouched():
    n = "[Semaglutide](/entity/drug/15b2232d) is a GLP-1 agonist."
    assert _sanitize_entity_links(n) == n


def test_sanitize_handles_empty():
    assert _sanitize_entity_links("") == ""
