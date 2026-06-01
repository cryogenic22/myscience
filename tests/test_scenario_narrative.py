"""PB-H16 — agentic scenario narrative: grounded synthesis + accuracy guards.

Verified offline with a stub LLM (any object exposing .enabled + .raw_chat).
The point of this loop is GROUNDING + ACCURACY, both deterministic and testable:
the prompt exposes only cited facts; hallucinated numbers and invalid citations
are stripped after generation (reusing services/llm.py guards).
"""
from __future__ import annotations

from services import scenario_narrative as sn
from services.dossier_kb import DossierFact, DossierSnapshot, build_domains
from services.scenarios import Scenario, derive_scenarios


def _fact(fid: str, claim: str) -> DossierFact:
    return DossierFact(id=fid, claim=claim, fact_class="corporate", source_label="s")


class _StubLLM:
    """Duck-types LLMSynthesizer: .enabled + .raw_chat(system, user)."""

    def __init__(self, text: str, enabled: bool = True):
        self._text = text
        self.enabled = enabled
        self.calls: list = []

    def raw_chat(self, system, user, max_tokens=400, temperature=0.2):
        self.calls.append((system, user))
        return self._text


def test_build_prompt_exposes_only_cited_facts():
    facts = [_fact("f1", "Trial success rate 86%"), _fact("f2", "Pipeline score 291.5")]
    s = Scenario(name="N", trigger_event="T", prior_prob=0.4)
    system, user = sn.build_prompt(s, facts)
    assert "86%" in user and "291.5" in user
    assert "[1]" in user and "[2]" in user
    assert "ONLY" in system          # grounding instruction present


def test_synthesize_returns_none_when_disabled_or_empty():
    facts = [_fact("f1", "metric 5")]
    s = Scenario(name="N", trigger_event="T", prior_prob=0.4)
    assert sn.synthesize_decision_output(s, facts, None) is None
    assert sn.synthesize_decision_output(s, facts, _StubLLM("hi", enabled=False)) is None
    assert sn.synthesize_decision_output(s, [], _StubLLM("hi")) is None


def test_synthesize_strips_hallucinated_number_keeps_grounded():
    # facts mention 86; the model invents **42%** → must lose its emphasis.
    facts = [_fact("f1", "Trial success rate 86%")]
    s = Scenario(name="N", trigger_event="T", prior_prob=0.4)
    llm = _StubLLM("Strong: success **86%**, but a **42%** churn risk looms [1].")
    out = sn.synthesize_decision_output(s, facts, llm)
    assert "**86%**" in out          # grounded number keeps its bold
    assert "**42%**" not in out      # hallucinated number de-emphasised
    assert "42%" in out              # text remains, just not a trust signal


def test_synthesize_strips_invalid_citation():
    facts = [_fact("f1", "Success 86%")]
    s = Scenario(name="N", trigger_event="T", prior_prob=0.4)
    llm = _StubLLM("Defensible [1]; downside [5].")   # only 1 fact → [5] invalid
    out = sn.synthesize_decision_output(s, facts, llm)
    assert "[1]" in out
    assert "[5]" not in out


def test_synthesize_returns_none_on_llm_error():
    class _Boom:
        enabled = True
        def raw_chat(self, *a, **k):
            raise RuntimeError("llm down")
    facts = [_fact("f1", "x 5")]
    s = Scenario(name="N", trigger_event="T", prior_prob=0.4)
    assert sn.synthesize_decision_output(s, facts, _Boom()) is None


def _snapshot_with_competitor() -> DossierSnapshot:
    related = [{"id": "d2", "type": "drug", "name": "tirzepatide",
                "relation": "COMPETES_WITH", "edge_count": 4}]
    domains, cov, cnt = build_domains([], None, None, related)
    return DossierSnapshot(engagement_id="e", focal_asset="drug:x", domains=domains,
                           coverage_score=cov, fact_count=cnt, id="snap1")


def test_enrich_populates_decision_output_when_enabled():
    snap = _snapshot_with_competitor()
    scenarios = derive_scenarios(snap)
    assert scenarios and all(s.decision_output is None for s in scenarios)
    sn.enrich_scenarios_with_narrative(scenarios, snap, _StubLLM("Grounded synthesis [1]."))
    assert any(s.decision_output for s in scenarios)


def test_enrich_is_noop_when_llm_disabled():
    snap = _snapshot_with_competitor()
    scenarios = derive_scenarios(snap)
    sn.enrich_scenarios_with_narrative(scenarios, snap, _StubLLM("x", enabled=False))
    assert all(s.decision_output is None for s in scenarios)
    sn.enrich_scenarios_with_narrative(scenarios, snap, None)
    assert all(s.decision_output is None for s in scenarios)
