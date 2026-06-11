"""ContextGuard content-grounding — flag 'X dominates/leads' claims whose
subject is in NEITHER the hydrated context NOR the known-entity catalog.

High precision by design: a real player (in the catalog) or one present in the
retrieved context is never flagged; only a fabricated dominator (the
'Medtronic dominates diabetes' class) is.
"""
from __future__ import annotations

from ctxpack.modules.guard import ContextGuard


def _guard(known=None):
    return ContextGuard(known_entity_names=known or set(), on_low_confidence="warn")


def test_flags_ungrounded_dominator():
    g = _guard(known={"DRUG-SEMAGLUTIDE", "COMPANY-NOVO-NORDISK"})
    ctx = "GLP-1 receptor agonists: 49 drugs, 601 trials. Insulin: 68 drugs."
    res = g.check("**Medtronic Diabetes** dominates the diabetes drug market.", ctx)
    assert res.ungrounded_claims, "Medtronic (not in context or catalog) must be flagged"
    assert res.recommendation in ("warn", "retry", "new_session")


def test_does_not_flag_player_in_catalog():
    g = _guard(known={"COMPANY-NOVO-NORDISK", "DRUG-SEMAGLUTIDE"})
    ctx = "Diabetes Mellitus competition by mechanism."  # Novo not in THIS context
    res = g.check("**Novo Nordisk** leads the diabetes space.", ctx)
    assert not res.ungrounded_claims, "a known-catalog company must not be flagged"


def test_does_not_flag_subject_in_context():
    g = _guard(known=set())
    ctx = "Eli Lilly & Co — 52 drugs in diabetes."
    res = g.check("**Eli Lilly** dominates diabetes development.", ctx)
    assert not res.ungrounded_claims, "subject present in context must not be flagged"


def test_does_not_flag_mechanism_dominance():
    g = _guard(known={"MECHANISM-GLUCAGON-LIKE-PEPTIDE-1-RECEPTOR-AGONISTS"})
    ctx = "Glucagon-Like Peptide-1 Receptor Agonists lead with 49 drugs."
    res = g.check("**GLP-1 receptor agonists** dominate the obesity landscape.", ctx)
    # 'agonists'/'receptor' appear in context → grounded, not flagged
    assert not res.ungrounded_claims


def test_clean_narrative_is_ok():
    # Avoid "GLP-1" here — it matches the pre-existing ID-pattern check (XX-N),
    # which is unrelated to content grounding. We assert our feature in isolation.
    g = _guard(known={"DRUG-SEMAGLUTIDE"})
    res = g.check("Semaglutide is an incretin-based therapy with 47 trials.", "semaglutide context")
    assert not res.ungrounded_claims
    assert res.recommendation == "ok"


def test_backwards_compatible_result_shape():
    g = _guard()
    res = g.check("hello", "ctx")
    # New field must exist and default empty; old fields unchanged
    assert hasattr(res, "ungrounded_claims")
    assert res.ungrounded_claims == []
