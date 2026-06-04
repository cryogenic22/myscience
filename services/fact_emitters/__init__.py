"""DR-0 — fact-emitter framework (Epic E19, data richness).

Lifts latent entity-table rows (clinical_trials, adverse_events, drug_labels,
…) into the temporal facts ledger as typed, domain-routed, evidence-bearing
facts. See services/fact_emitters/base.py for the framework and the per-source
emitter modules for each lift.
"""

from services.fact_emitters.base import (
    EmittedFact,
    EmitStats,
    FactEmitter,
    emit_one,
    run_emitter,
    get_emitters,
    run_all_emitters,
)

__all__ = [
    "EmittedFact",
    "EmitStats",
    "FactEmitter",
    "emit_one",
    "run_emitter",
    "get_emitters",
    "run_all_emitters",
]
