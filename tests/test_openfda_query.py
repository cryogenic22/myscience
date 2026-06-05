"""D1: openFDA incremental-query syntax regression tests.

Root cause of the 19-Feb labels/FAERS death: the incremental `since` query was
built as ``field:"x"+AND+datefield:[YYYYMMDD+TO+20991231]``. ``requests``
URL-encodes the literal ``+`` to ``%2B``, which openFDA rejects with HTTP 500 →
every scheduled (incremental) run fetched 0 rows and still recorded SUCCESS, so
the tables silently went 105 days stale.

These tests pin the *correct* Lucene syntax that openFDA accepts: ``AND`` is a
space (``requests`` encodes it to ``+``), and the date range is a plain
``[YYYYMMDD TO YYYYMMDD]`` token — no embedded literal ``+``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from connectors.base import build_openfda_date_search


def test_no_since_returns_bare_field_query():
    """Full mode: no date clause appended."""
    q = build_openfda_date_search('openfda.generic_name:"semaglutide"', None, "effective_time")
    assert q == 'openfda.generic_name:"semaglutide"'


def test_since_appends_space_and_clause_not_literal_plus():
    """Incremental mode: AND is a literal space, never ``+AND+``."""
    since = datetime(2026, 2, 1, tzinfo=timezone.utc)
    q = build_openfda_date_search(
        'patient.drug.openfda.generic_name:"semaglutide"', since, "receivedate"
    )
    assert "+AND+" not in q
    assert "+TO+" not in q
    assert q == (
        'patient.drug.openfda.generic_name:"semaglutide" '
        "AND receivedate:[20260201 TO 20991231]"
    )


def test_since_uses_correct_date_field():
    """Labels use effective_time; FAERS use receivedate — caller supplies it."""
    since = datetime(2025, 12, 31, tzinfo=timezone.utc)
    q = build_openfda_date_search('openfda.generic_name:"x"', since, "effective_time")
    assert "effective_time:[20251231 TO 20991231]" in q


def test_naive_datetime_accepted():
    """Scheduler passes tz-naive datetimes from etl_runs; must not crash."""
    since = datetime(2026, 1, 15)  # naive
    q = build_openfda_date_search('openfda.generic_name:"x"', since, "effective_time")
    assert "effective_time:[20260115 TO 20991231]" in q
