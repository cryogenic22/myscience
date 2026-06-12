"""Loop A — pure unit tests for the demoted-canonical restore selector.

RED→GREEN: the selector must restore a rich demoted canonical that has no (or a
poorer) active replacement, and must NOT touch active canonicals, excluded junk,
ambiguous 'A or B' rows, bare non-drug tokens, or sub-threshold rows.
"""
from scripts.restore_demoted_canonicals import (
    is_restorable_name,
    select_restorations,
)


def _row(gname, status, richness, rk=1, best_active=0, id="x"):
    return {
        "id": id, "gname": gname, "record_status": status,
        "richness": richness, "rk": rk, "best_active_richness": best_active,
    }


def test_restores_demoted_canonical_with_no_active_replacement():
    rows = [_row("valsartan", "merged", 1233, id="f433")]
    picks = select_restorations(rows)
    assert [p.drug_id for p in picks] == ["f433"]
    assert picks[0].prior_status == "merged"


def test_restores_superseded_canonical_too():
    rows = [_row("ivabradine", "superseded", 82, id="iva")]
    assert [p.name for p in select_restorations(rows)] == ["ivabradine"]


def test_restores_when_active_sibling_is_poorer():
    # rich demoted row (15) beats a thin active sibling (4) → still degraded.
    rows = [_row("fluvastatin", "merged", 15, rk=1, best_active=4, id="flu")]
    assert [p.drug_id for p in select_restorations(rows)] == ["flu"]


def test_skips_when_active_replacement_is_equal_or_richer():
    # the richest row IS active → nothing demoted to restore.
    rows = [_row("metformin", "active", 200, rk=1, best_active=200, id="met")]
    assert select_restorations(rows) == []


def test_skips_excluded_junk_rows():
    # 'excluded' is a deliberate quarantine, not a demotion — never revived.
    rows = [_row("placebo (matching)", "excluded", 285, id="plc")]
    assert select_restorations(rows) == []


def test_skips_ambiguous_disjunction_name():
    rows = [_row("semaglutide or tirzepatide", "merged", 40, id="amb")]
    assert select_restorations(rows) == []


def test_skips_bare_non_drug_token():
    rows = [_row("medication", "merged", 34, id="med")]
    assert select_restorations(rows) == []


def test_skips_below_richness_floor():
    rows = [_row("obscure-thing", "merged", 5, id="ob")]
    assert select_restorations(rows) == []


def test_only_richest_row_per_name_considered():
    # a non-richest demoted dup (rk=2) is left for the consolidator to absorb.
    rows = [_row("valsartan", "merged", 5, rk=2, best_active=0, id="dup")]
    assert select_restorations(rows) == []


def test_is_restorable_name_filters():
    assert is_restorable_name("valsartan")
    assert is_restorable_name("metformin hydrochloride")
    assert not is_restorable_name("semaglutide or tirzepatide")
    assert not is_restorable_name("placebo")
    assert not is_restorable_name("")
