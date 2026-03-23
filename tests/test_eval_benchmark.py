"""Tests for evaluation benchmark scorers — prerequisite for Phase 2.

TDD: Tests written FIRST, then scorers implementation.
"""

from __future__ import annotations

import pytest


# ── Intent Scoring ──


class TestScoreIntent:

    def test_correct_intent_scores_1(self):
        from benchmark.scorers import score_intent
        response = {"intent": "dossier"}
        expected = {"intent": "dossier"}
        assert score_intent(response, expected) == 1.0

    def test_wrong_intent_scores_0(self):
        from benchmark.scorers import score_intent
        response = {"intent": "general"}
        expected = {"intent": "dossier"}
        assert score_intent(response, expected) == 0.0


# ── Entity Grounding ──


class TestScoreEntityGrounding:

    def test_expected_entities_found(self):
        from benchmark.scorers import score_entity_grounding
        response = {
            "narrative": "**Semaglutide** is a GLP-1 agonist by **Novo Nordisk**.",
            "data": {"entity_focus": [
                {"label": "semaglutide", "entity_type": "drug"},
            ]},
        }
        expected = {"entities": ["semaglutide"], "must_mention": ["Novo Nordisk"]}
        score = score_entity_grounding(response, expected)
        assert score >= 0.8

    def test_missing_entity_penalized(self):
        from benchmark.scorers import score_entity_grounding
        response = {
            "narrative": "No data found.",
            "data": {"entity_focus": []},
        }
        expected = {"entities": ["semaglutide"], "must_mention": ["Novo Nordisk"]}
        score = score_entity_grounding(response, expected)
        assert score < 0.5

    def test_must_not_mention_penalized(self):
        from benchmark.scorers import score_entity_grounding
        response = {
            "narrative": "**Semaglutide** shows promise. Training data suggests 89% efficacy.",
            "data": {"entity_focus": [{"label": "semaglutide"}]},
        }
        expected = {
            "entities": ["semaglutide"],
            "must_mention": [],
            "must_not_mention": ["training data"],
        }
        score = score_entity_grounding(response, expected)
        assert score < 1.0


# ── Factual Accuracy ──


class TestScoreFactualAccuracy:

    def test_matching_numbers_score_high(self):
        from benchmark.scorers import score_factual_accuracy
        response = {
            "narrative": "Pipeline score of **42.5** across **47** trials.",
            "data": {"metrics_context": {"d1": {"pipeline": {"pipeline_score": 42.5, "total_trials": 47}}}},
        }
        score = score_factual_accuracy(response)
        assert score >= 0.8

    def test_mismatched_numbers_score_low(self):
        from benchmark.scorers import score_factual_accuracy
        response = {
            "narrative": "Pipeline score of **99.9** with **500** trials.",
            "data": {"metrics_context": {"d1": {"pipeline": {"pipeline_score": 42.5, "total_trials": 47}}}},
        }
        score = score_factual_accuracy(response)
        assert score < 0.5

    def test_no_bold_numbers_neutral(self):
        from benchmark.scorers import score_factual_accuracy
        response = {
            "narrative": "Semaglutide is a promising drug.",
            "data": {"metrics_context": {}},
        }
        score = score_factual_accuracy(response)
        assert score == 1.0  # nothing to verify → pass


# ── Evidence Completeness ──


class TestScoreEvidenceCompleteness:

    def test_sufficient_evidence(self):
        from benchmark.scorers import score_evidence_completeness
        response = {
            "narrative": "Based on **Novo Nordisk** data for **GLP-1**.",
            "data": {"evidence": [{"content": "ev1"}, {"content": "ev2"}, {"content": "ev3"}]},
        }
        expected = {"min_evidence": 3, "must_mention": ["Novo Nordisk", "GLP-1"]}
        score = score_evidence_completeness(response, expected)
        assert score >= 0.8

    def test_insufficient_evidence(self):
        from benchmark.scorers import score_evidence_completeness
        response = {
            "narrative": "Limited data.",
            "data": {"evidence": [{"content": "ev1"}]},
        }
        expected = {"min_evidence": 5, "must_mention": []}
        score = score_evidence_completeness(response, expected)
        assert score < 0.8

    def test_must_mention_terms_present(self):
        from benchmark.scorers import score_evidence_completeness
        response = {
            "narrative": "**Semaglutide** targets **obesity** via **GLP-1** mechanism.",
            "data": {"evidence": [{"content": "ev1"}, {"content": "ev2"}, {"content": "ev3"}]},
        }
        expected = {"min_evidence": 2, "must_mention": ["obesity", "GLP-1"]}
        score = score_evidence_completeness(response, expected)
        assert score >= 0.9


# ── Citation Validity ──


class TestScoreCitationValidity:

    def test_all_valid_citations(self):
        from benchmark.scorers import score_citation_validity
        response = {
            "narrative": "Evidence [1] shows results [2].",
            "data": {"evidence": [{"c": 1}, {"c": 2}, {"c": 3}]},
        }
        assert score_citation_validity(response) == 1.0

    def test_invalid_citations_penalize(self):
        from benchmark.scorers import score_citation_validity
        response = {
            "narrative": "Evidence [1] and [99] support this.",
            "data": {"evidence": [{"c": 1}, {"c": 2}]},
        }
        score = score_citation_validity(response)
        assert score < 1.0


# ── Composite Score ──


class TestCompositeScore:

    def test_weighted_average(self):
        from benchmark.scorers import composite_score
        dimensions = {
            "intent": 1.0,
            "grounding": 0.8,
            "factual": 0.6,
            "completeness": 0.9,
            "citation": 1.0,
        }
        score = composite_score(dimensions)
        # Weights: intent=0.10, grounding=0.25, factual=0.25, completeness=0.25, citation=0.15
        expected = 0.10 * 1.0 + 0.25 * 0.8 + 0.25 * 0.6 + 0.25 * 0.9 + 0.15 * 1.0
        assert score == pytest.approx(expected, abs=0.01)

    def test_perfect_query(self):
        from benchmark.scorers import composite_score
        dimensions = {k: 1.0 for k in ["intent", "grounding", "factual", "completeness", "citation"]}
        assert composite_score(dimensions) == pytest.approx(1.0, abs=0.01)
