"""DR — regulatory-milestone fact emitter tests.

Turns already-ingested ``regulatory_milestones`` rows (FDA approval-timeline
events: ORIG/SUPPL submissions, AP/TA status) into governed facts that
``route_predicate_to_domain`` lands in the dossier's ``pipeline_and_macro``
domain. Pure mapping (row_to_facts, build_claim) needs no DB; idempotency uses
a MagicMock DB in the established style. See tests/test_fact_emitters.py.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from services.fact_emitters.base import get_emitters, run_emitter
from services.fact_emitters.regulatory_milestones import (
    RegulatoryMilestoneEmitter,
    build_claim,
)
from services.dossier_kb import route_predicate_to_domain


def _ms(**over):
    row = {
        "id": "ms-1",
        "drug_id": "drug-sema",
        "submission_type": "ORIG",
        "submission_number": "1",
        "submission_status": "AP",
        "submission_status_date": date(2017, 12, 5),
        "review_priority": "PRIORITY",
        "document_url": "https://fda.gov/doc",
        "source_api": "fda_drugsfda",
        "source_url": "https://fda.gov/milestone",
    }
    row.update(over)
    return row


# ── build_claim / row_to_facts (pure) ──────────────────────────────

class TestRegulatoryMilestoneMapping:
    def test_build_claim_reads_well(self):
        claim = build_claim(_ms())
        assert claim == "Original approval (Priority review) — 2017-12-05"

    def test_claim_handles_supplement_and_tentative(self):
        claim = build_claim(_ms(submission_type="SUPPL", submission_status="TA",
                                review_priority="STANDARD", submission_number="3"))
        assert "Supplement" in claim
        assert "tentative approval" in claim

    def test_row_to_facts_emits_one_milestone_fact(self):
        facts = RegulatoryMilestoneEmitter().row_to_facts(_ms())
        assert len(facts) == 1
        f = facts[0]
        assert f.predicate == "regulatory_milestone"
        assert f.subject_entity_type == "drug"
        assert f.subject_entity_id == "drug-sema"
        assert f.source_row_id == "ms-1"
        assert f.kind == "point"
        assert f.fact_class == "corporate"
        assert f.object_value["submission_type"] == "ORIG"
        assert f.object_value["status"] == "AP"
        assert f.evidence_text  # attestable snippet present

    def test_status_date_drives_valid_from(self):
        f = RegulatoryMilestoneEmitter().row_to_facts(_ms())[0]
        assert f.valid_from == datetime(2017, 12, 5, tzinfo=timezone.utc)

    def test_row_without_drug_id_emits_nothing(self):
        assert RegulatoryMilestoneEmitter().row_to_facts(_ms(drug_id=None)) == []

    def test_row_without_date_emits_nothing(self):
        assert RegulatoryMilestoneEmitter().row_to_facts(
            _ms(submission_status_date=None)) == []


# ── predicate routing (the whole point — facts must land in a domain) ──

class TestPredicateRouting:
    def test_routes_to_pipeline_and_macro(self):
        assert route_predicate_to_domain("regulatory_milestone") == "pipeline_and_macro"


# ── fetch_rows skip-counting + idempotency ─────────────────────────

class TestRunEmitter:
    def test_skip_counting_for_null_drug_and_date(self, monkeypatch):
        em = RegulatoryMilestoneEmitter()
        # 1 good, 1 null-drug, 1 null-date → only 1 emits a fact.
        monkeypatch.setattr(em, "fetch_rows", lambda *a, **k: [
            _ms(id="A"),
            _ms(id="B", drug_id=None),
            _ms(id="C", submission_status_date=None),
        ])
        db = MagicMock()
        db.fetch_all.return_value = []  # _fact_exists → no
        db.fetch_one.side_effect = [
            None, {"evidence_id": "e1"}, {"id": "f1"},  # A asserted
        ]
        stats = run_emitter(db, em)
        assert stats.scanned == 1   # only the row that produced a fact
        assert stats.asserted == 1
        assert stats.evidence_written == 1

    def test_idempotent_rerun_asserts_nothing(self, monkeypatch):
        em = RegulatoryMilestoneEmitter()
        monkeypatch.setattr(em, "fetch_rows", lambda *a, **k: [_ms(id="A")])
        db = MagicMock()
        db.fetch_all.return_value = [{"id": "existing"}]  # already present
        stats = run_emitter(db, em)
        assert stats.asserted == 0
        assert stats.skipped_existing == 1


class TestRegistry:
    def test_emitter_registered(self):
        assert "regulatory_milestones" in get_emitters()
