"""D1 — RegulatoryMilestoneEmitter tests.

regulatory_milestones (FDA Orange Book) lands on prod but never becomes a fact,
so the regulatory lens renders empty for drugs that DO carry approval history.
This emitter converts approved submissions → governed regulatory_approval facts.
Pure row_to_facts; no DB.
"""

from __future__ import annotations

from services.fact_emitters.regulatory_milestones import RegulatoryMilestoneEmitter


def _row(**kw):
    base = {
        "id": "11111111-1111-1111-1111-111111111111",
        "drug_id": "drug-1",
        "submission_type": "ORIG",
        "submission_number": "021145",
        "submission_status": "AP",
        "submission_status_date": "2005-04-29",
        "review_priority": "STANDARD",
        "document_url": None,
        "source_api": "fda_orange_book",
        "source_url": "https://example/ob",
    }
    base.update(kw)
    return base


E = RegulatoryMilestoneEmitter()


class TestRowToFacts:
    def test_approved_emits_regulatory_approval(self):
        facts = E.row_to_facts(_row())
        assert len(facts) == 1
        f = facts[0]
        assert f.predicate == "regulatory_approval"
        assert f.subject_entity_id == "drug-1"
        assert f.fact_class == "corporate"
        assert "approved" in f.object_value["description"].lower()
        assert f.source_row_id == "11111111-1111-1111-1111-111111111111"
        assert f.valid_from is not None   # status date coerced

    def test_tentative_approval_phrasing(self):
        facts = E.row_to_facts(_row(submission_status="TA"))
        assert facts and "tentativ" in facts[0].object_value["description"].lower()

    def test_supplement_phrasing(self):
        facts = E.row_to_facts(_row(submission_type="EFFICACY_SUPPL"))
        assert facts and "supplement" in facts[0].object_value["description"].lower()

    def test_priority_review_noted(self):
        facts = E.row_to_facts(_row(review_priority="PRIORITY"))
        assert facts and "priority" in facts[0].object_value["description"].lower()

    def test_non_approval_status_skipped(self):
        # only AP/TA are asserted — never invent an approval we can't see
        assert E.row_to_facts(_row(submission_status="")) == []
        assert E.row_to_facts(_row(submission_status="PENDING")) == []

    def test_missing_drug_id_skipped(self):
        assert E.row_to_facts(_row(drug_id=None)) == []

    def test_idempotency_key_is_milestone_id(self):
        f = E.row_to_facts(_row(id="abc-123"))[0]
        assert f.source_row_id == "abc-123"


def test_registered_in_get_emitters():
    from services.fact_emitters.base import get_emitters
    assert "regulatory_milestones" in get_emitters()
