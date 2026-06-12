"""FS-2 / OQ3 — a contradicted scenario surfaces as contradicted, not averaged.

The stance mix of the latest calibration move is carried onto the scenario
(read-time, from scenario_calibration_history) and serialized so the UI can show
a contradiction badge instead of silently reconciling conflicting evidence.
"""
from services.scenarios import Scenario


def _scn(**kw):
    return Scenario(name="Competitive pressure: tirzepatide",
                    trigger_event="rival readout", prior_prob=0.5, **kw)


def test_default_scenario_is_not_contradicted():
    d = _scn().to_dict()
    assert d["contradicted"] is False
    assert d["stanceMix"] == {"supporting": 0, "contradicting": 0}


def test_contradicting_signals_mark_scenario_contradicted():
    d = _scn(n_supporting=1, n_contradicting=2).to_dict()
    assert d["contradicted"] is True
    assert d["stanceMix"] == {"supporting": 1, "contradicting": 2}


def test_only_supporting_is_not_contradicted():
    d = _scn(n_supporting=3, n_contradicting=0).to_dict()
    assert d["contradicted"] is False
    assert d["stanceMix"]["supporting"] == 3
