"""Tests for COMPETES_WITH link derivation."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.fetch_all.return_value = [
        {
            'drug_a_id': 'id-sema', 'drug_a_name': 'semaglutide',
            'drug_b_id': 'id-tirz', 'drug_b_name': 'tirzepatide',
            'mechanism_id': 'mech-glp1', 'therapeutic_area_id': 'ta-dm2',
        },
        {
            'drug_a_id': 'id-sema', 'drug_a_name': 'semaglutide',
            'drug_b_id': 'id-dula', 'drug_b_name': 'dulaglutide',
            'mechanism_id': 'mech-glp1', 'therapeutic_area_id': 'ta-dm2',
        },
    ]
    return db


def test_dry_run_creates_no_links(mock_db):
    from scripts.derive_competition import derive_competition
    result = derive_competition(mock_db, dry_run=True)
    assert result['total_pairs'] == 2
    assert result['dry_run'] is True
    mock_db.execute.assert_not_called()


def test_creates_bidirectional_links(mock_db):
    from scripts.derive_competition import derive_competition
    result = derive_competition(mock_db, dry_run=False)
    assert result['total_pairs'] == 2
    assert result['links_created'] == 4  # 2 pairs × 2 directions
    assert mock_db.execute.call_count == 4


def test_link_type_is_competes_with(mock_db):
    from scripts.derive_competition import derive_competition
    derive_competition(mock_db, dry_run=False)
    call_args = mock_db.execute.call_args_list[0]
    sql = call_args[0][0]
    params = call_args[0][1]
    assert 'COMPETES_WITH' in sql
    assert params[0] in ('id-sema', 'id-tirz')


def test_confidence_is_set(mock_db):
    from scripts.derive_competition import derive_competition
    derive_competition(mock_db, dry_run=False)
    params = mock_db.execute.call_args_list[0][0][1]
    assert params[2] == 0.85  # confidence


def test_empty_pairs(mock_db):
    mock_db.fetch_all.return_value = []
    from scripts.derive_competition import derive_competition
    result = derive_competition(mock_db, dry_run=False)
    assert result['total_pairs'] == 0
    assert result['links_created'] == 0
