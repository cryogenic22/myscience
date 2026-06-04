"""DR-0/DR-1 — tests for the fact-emitter framework + clinical-trials lift.

Pure mapping (row_to_facts, build_claim) needs no DB. Idempotency + evidence
use a MagicMock DB in the established style: _fact_exists / _write_evidence use
db.fetch_all / db.fetch_one, assert_fact uses db.fetch_one — see
tests/test_fact_ingest.py for the same convention.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import services.fact_emitters.base as base
from services.fact_emitters.base import (
    EmittedFact,
    emit_one,
    run_emitter,
    get_emitters,
)
from services.fact_emitters.clinical_trials import (
    ClinicalTrialEmitter,
    build_claim,
)
from services.dossier_kb import route_predicate_to_domain


def _trial(**over):
    base_row = {
        "id": "NCT05646706",
        "drug_id": "drug-sema",
        "phase": "Phase 3",
        "status": "COMPLETED",
        "conditions": ["Obesity"],
        "official_title": "STEP 1: Semaglutide 2.4 mg in adults with obesity",
        "enrollment_target": 1961,
        "actual_enrollment": 1961,
        "start_date": date(2018, 6, 1),
        "completion_date": date(2020, 3, 1),
        "primary_completion_date": date(2020, 2, 1),
        "failure_reason": None,
        "source_api": "clinical_trials_gov",
        "source_url": "https://clinicaltrials.gov/study/NCT05646706",
        "quality_score": 0.9,
    }
    base_row.update(over)
    return base_row


# ── build_claim / row_to_facts (pure) ──────────────────────────────

class TestClinicalTrialMapping:
    def test_build_claim_reads_well(self):
        claim = build_claim(_trial())
        assert claim == "Phase 3, Completed, in Obesity (NCT05646706) — enrollment 1,961"

    def test_claim_handles_missing_phase_and_enrollment(self):
        claim = build_claim(_trial(phase=None, actual_enrollment=None, enrollment_target=None))
        assert claim == "Completed, in Obesity (NCT05646706)"
        assert "enrollment" not in claim

    def test_na_phase_is_not_printed_as_phase(self):
        claim = build_claim(_trial(phase="N/A"))
        assert "N/A" not in claim
        assert claim.startswith("Completed")

    def test_row_to_facts_emits_one_clinical_trial_fact(self):
        facts = ClinicalTrialEmitter().row_to_facts(_trial())
        assert len(facts) == 1
        f = facts[0]
        assert f.predicate == "clinical_trial"
        assert f.subject_entity_type == "drug"
        assert f.subject_entity_id == "drug-sema"
        assert f.source_row_id == "NCT05646706"
        assert f.fact_class == "corporate"
        assert f.object_value["description"].startswith("Phase 3, Completed")
        assert f.object_value["source_url"].endswith("NCT05646706")
        assert f.evidence_text  # DR-5: attestable snippet present

    def test_completion_date_drives_valid_from(self):
        f = ClinicalTrialEmitter().row_to_facts(_trial())[0]
        assert f.valid_from == datetime(2020, 3, 1, tzinfo=timezone.utc)

    def test_row_without_drug_id_emits_nothing(self):
        assert ClinicalTrialEmitter().row_to_facts(_trial(drug_id=None)) == []

    def test_failure_reason_enriches_evidence(self):
        f = ClinicalTrialEmitter().row_to_facts(
            _trial(status="TERMINATED", failure_reason="Slow enrollment"))[0]
        assert "Slow enrollment" in f.evidence_text

    def test_quality_score_on_0_100_scale_is_rescaled(self):
        f = ClinicalTrialEmitter().row_to_facts(_trial(quality_score=90))[0]
        assert f.confidence == 0.9


# ── predicate routing (the whole point — facts must land in a domain) ──

class TestPredicateRouting:
    def test_clinical_trial_routes_to_clinical_profile(self):
        assert route_predicate_to_domain("clinical_trial") == "clinical_profile"


# ── emit_one (idempotent + evidence) ───────────────────────────────

def _emitted(**over):
    d = dict(
        predicate="clinical_trial",
        subject_entity_type="drug",
        subject_entity_id="drug-sema",
        object_value={"description": "Phase 3 trial"},
        source_row_id="NCT1",
        evidence_text="STEP 1 trial",
        source_id="clinical_trials_gov",
        source_url="https://ct.gov/NCT1",
    )
    d.update(over)
    return EmittedFact(**d)


class TestEmitOne:
    def test_asserts_and_writes_evidence_when_new(self):
        db = MagicMock()
        db.fetch_all.return_value = []  # _fact_exists → no
        # 1st fetch_one = evidence exists check (None), 2nd = evidence insert,
        # 3rd = assert_fact insert.
        db.fetch_one.side_effect = [
            None,
            {"evidence_id": "ev-1"},
            {"id": "fact-1"},
        ]
        status, fid = emit_one(db, "clinical_trials", _emitted())
        assert status == "asserted"
        assert fid == "fact-1"

    def test_skips_when_fact_already_exists(self):
        db = MagicMock()
        db.fetch_all.return_value = [{"id": "existing"}]  # _fact_exists → yes
        status, fid = emit_one(db, "clinical_trials", _emitted())
        assert status == "skipped_existing"
        assert fid is None
        db.fetch_one.assert_not_called()  # no evidence/assert writes

    def test_no_subject_skips_without_write(self):
        db = MagicMock()
        status, fid = emit_one(db, "clinical_trials", _emitted(subject_entity_id=""))
        assert status == "skipped_no_subject"
        db.fetch_all.assert_not_called()

    def test_reuses_existing_evidence_record(self):
        db = MagicMock()
        db.fetch_all.return_value = []
        db.fetch_one.side_effect = [
            {"evidence_id": "ev-existing"},  # evidence dedup hit
            {"id": "fact-2"},                # assert_fact
        ]
        status, fid = emit_one(db, "clinical_trials", _emitted())
        assert status == "asserted"
        assert fid == "fact-2"

    def test_write_evidence_disabled_skips_evidence(self):
        db = MagicMock()
        db.fetch_all.return_value = []
        db.fetch_one.side_effect = [{"id": "fact-3"}]  # only assert_fact
        status, fid = emit_one(db, "clinical_trials", _emitted(), write_evidence=False)
        assert status == "asserted"
        assert fid == "fact-3"


# ── run_emitter ────────────────────────────────────────────────────

class TestRunEmitter:
    def test_counts_asserted_and_existing(self, monkeypatch):
        em = ClinicalTrialEmitter()
        monkeypatch.setattr(em, "fetch_rows",
                            lambda *a, **k: [_trial(id="A"), _trial(id="B")])
        db = MagicMock()
        db.fetch_all.return_value = []
        db.fetch_one.side_effect = [
            None, {"evidence_id": "e1"}, {"id": "f1"},   # A asserted
            None, {"evidence_id": "e2"}, {"id": "f2"},   # B asserted
        ]
        stats = run_emitter(db, em)
        assert stats.scanned == 2
        assert stats.asserted == 2
        assert stats.evidence_written == 2

    def test_idempotent_rerun_asserts_nothing(self, monkeypatch):
        em = ClinicalTrialEmitter()
        monkeypatch.setattr(em, "fetch_rows", lambda *a, **k: [_trial(id="A")])
        db = MagicMock()
        db.fetch_all.return_value = [{"id": "existing"}]  # already present
        stats = run_emitter(db, em)
        assert stats.asserted == 0
        assert stats.skipped_existing == 1


class TestRegistry:
    def test_clinical_trials_emitter_registered(self):
        assert "clinical_trials" in get_emitters()
