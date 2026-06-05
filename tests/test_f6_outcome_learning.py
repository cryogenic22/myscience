"""F6/C6 — decision outcome → learning closure.

The Learn arc was open: outcomes were recorded but produced no
signal_score_adjustments row. These tests pin the new
emit_signal_score_adjustment path that closes it, plus the kbq/rule
resolution that keys each learning row.

Pure unit tests over a tiny fake DB (no live connection).
"""

from __future__ import annotations

from services.learning_service import (
    DECISION_RULE_VERSION,
    _kbq_tags_for_decision,
    emit_signal_score_adjustment,
)


class _FakeDB:
    """Minimal DB double: scripted fetch_one responses + captured inserts."""

    def __init__(self, *, signals=None, proposals=None, existing_adj=None):
        self.signals = signals or {}          # signal_id -> {kbq_tags, rule_version_id}
        self.proposals = proposals or {}      # decision_id -> {signal_id}
        self.existing_adj = existing_adj or set()  # {(decision_id, kbq_tag)}
        self.inserts: list[tuple] = []

    def fetch_one(self, sql, params=None):
        s = (sql or "").lower()
        params = params or ()
        # confirmed proposal → signal
        if "from outcome_proposals p" in s and "join signals" in s:
            did = str(params[0])
            prop = self.proposals.get(did)
            if not prop:
                return None
            sig = self.signals.get(prop["signal_id"], {})
            return {
                "signal_id": prop["signal_id"],
                "kbq_tags": sig.get("kbq_tags"),
                "rule_version_id": sig.get("rule_version_id"),
            }
        # seed signal lookup
        if "from signals where id::text" in s:
            sig = self.signals.get(str(params[0]))
            return sig
        # idempotency guard
        if "from signal_score_adjustments" in s:
            did, tag = str(params[0]), params[1]
            return {"x": 1} if (did, tag) in self.existing_adj else None
        return None

    def execute(self, sql, params=None):
        s = (sql or "").lower()
        if "insert into signal_score_adjustments" in s:
            self.inserts.append(tuple(params))
        return None


def test_emit_uses_move_type_fallback_when_no_signal():
    db = _FakeDB()
    decision = {"id": "dec-1", "move_type": "trial_readout", "status": "verified"}

    n = emit_signal_score_adjustment(db, decision=decision, calibration_score=0.8)

    assert n == 1
    assert len(db.inserts) == 1
    rule_version, kbq_tag, decision_id, matched_signal, cal, delta, notes = db.inserts[0]
    assert rule_version == DECISION_RULE_VERSION
    assert kbq_tag == "trial_readout"      # move_type as the kbq fallback
    assert decision_id == "dec-1"
    assert matched_signal is None
    assert cal == 0.8
    assert delta > 0                        # verified → positive nudge


def test_emit_uses_seed_signal_kbqs():
    db = _FakeDB(signals={
        "sig-9": {"kbq_tags": ["clinical", "regulatory"], "rule_version_id": "rv-7"},
    })
    decision = {
        "id": "dec-2", "move_type": "new_indication",
        "status": "verified", "source_signal_id": "sig-9",
    }

    n = emit_signal_score_adjustment(db, decision=decision, calibration_score=0.6)

    assert n == 2  # one row per kbq tag
    rule_versions = {r[0] for r in db.inserts}
    kbqs = {r[1] for r in db.inserts}
    matched = {r[3] for r in db.inserts}
    assert rule_versions == {"rv-7"}
    assert kbqs == {"clinical", "regulatory"}
    assert matched == {"sig-9"}


def test_emit_prefers_confirmed_proposal_over_seed():
    db = _FakeDB(
        signals={
            "sig-seed": {"kbq_tags": ["strategic"], "rule_version_id": "rv-seed"},
            "sig-out": {"kbq_tags": ["m_and_a"], "rule_version_id": "rv-out"},
        },
        proposals={"dec-3": {"signal_id": "sig-out"}},
    )
    decision = {
        "id": "dec-3", "move_type": "acquisition",
        "status": "verified", "source_signal_id": "sig-seed",
    }
    tags, rv, matched = _kbq_tags_for_decision(db, decision)
    assert tags == ["m_and_a"]
    assert rv == "rv-out"
    assert matched == "sig-out"


def test_emit_is_idempotent_skips_existing_pair():
    db = _FakeDB(existing_adj={("dec-4", "trial_readout")})
    decision = {"id": "dec-4", "move_type": "trial_readout", "status": "verified"}

    n = emit_signal_score_adjustment(db, decision=decision, calibration_score=0.9)

    assert n == 0
    assert db.inserts == []


def test_emit_missed_outcome_negative_delta():
    db = _FakeDB()
    decision = {"id": "dec-5", "move_type": "price_cut", "status": "missed"}
    # missed + high confidence-derived calibration → negative weight delta
    emit_signal_score_adjustment(db, decision=decision, calibration_score=0.2)
    assert len(db.inserts) == 1
    delta = db.inserts[0][5]
    assert delta < 0
