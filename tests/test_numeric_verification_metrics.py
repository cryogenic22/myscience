"""F6 / TICKET-5 — computed metrics must verify, and the ``[unverified]``
marker must never leak into user-facing text.

Two failures the reviewer hit on Q4 ("pipeline score of 1530.4 [unverified]"):

  1. A provenance-stamped metric value — even when a metrics row carries it as
     a *display string* (e.g. ``{"metric": "Pipeline Score", "value": "1530.4"}``)
     — was NOT reaching ``source_numbers``, so the most authoritative on-screen
     number got flagged as untrustworthy.
  2. The suppression appended a literal ``[unverified]`` string into the prose,
     which leaked to the reader and looked like a UI bug.

TDD: these tests are written FIRST; the fix lands in ``services/llm.py``.
"""

from __future__ import annotations


class TestComputedMetricsVerify:
    """Provenance-stamped metric values count as grounded — not flagged."""

    def test_string_encoded_metric_reaches_source_numbers(self):
        from services.llm import _extract_source_numbers

        # Metrics rows frequently carry figures as display strings (the shape
        # services/chat_handlers/handlers.py builds: {"value": str(round(...))}).
        metrics = {"pipeline": [{"metric": "Pipeline Score", "value": "1530.4"}]}
        nums = _extract_source_numbers(metrics, None)
        assert 1530.4 in nums

    def test_float_encoded_metric_reaches_source_numbers(self):
        from services.llm import _extract_source_numbers

        metrics = {"competitive": [{"segment": "Obesity", "total_pipeline_score": 1530.4}]}
        assert 1530.4 in _extract_source_numbers(metrics, None)

    def test_quoted_metric_value_is_not_flagged(self):
        """The F6 repro: a narrative quoting a metric value that is present in a
        (string-encoded) metrics row must NOT be marked unverified."""
        from services.llm import _extract_source_numbers, verify_narrative_numbers

        metrics = {"pipeline": [{"metric": "Pipeline Score", "value": "1530.4"}]}
        src = _extract_source_numbers(metrics, None)
        result = verify_narrative_numbers(
            "The leader shows a pipeline score of **1530.4**.", src
        )
        assert result["flagged"] == 0
        assert "[unverified]" not in result["narrative"]
        assert "1530.4" in result["narrative"]
        # The grounded bold figure keeps its emphasis (it is real).
        assert "**1530.4**" in result["narrative"]


class TestNoMarkerLeak:
    """A genuinely invented number is de-emphasised, but the literal
    ``[unverified]`` string must never reach user-facing text."""

    def test_invented_bold_number_demoted_without_marker_leak(self):
        from services.llm import verify_narrative_numbers

        result = verify_narrative_numbers(
            "Efficacy reached **47%** weight loss.", source_numbers={5, 10}
        )
        assert result["flagged"] >= 1          # still detected (server log / telemetry)
        assert "[unverified]" not in result["narrative"]   # no leak
        assert "**47%**" not in result["narrative"]        # bold trust-signal removed
        assert "47%" in result["narrative"]                # number text kept

    def test_invented_unbolded_stat_no_marker_leak(self):
        from services.llm import verify_narrative_numbers

        result = verify_narrative_numbers(
            "Patients saw 23% weight loss.", source_numbers={5}
        )
        assert result["flagged"] >= 1
        assert "[unverified]" not in result["narrative"]
        assert "23%" in result["narrative"]

    def test_no_marker_anywhere_even_with_multiple_flags(self):
        from services.llm import verify_narrative_numbers

        result = verify_narrative_numbers(
            "Saw **47%** response and a 2.5x advantage.", source_numbers={5}
        )
        assert "[unverified]" not in result["narrative"]
        assert result["flagged"] >= 2


class TestStringMiningIsValueScoped:
    """Only numeric value-like strings are mined for source numbers. A free-text
    label's incidental date/id digits must NOT enter the grounded set, or they
    would launder an invented narrative number into "grounded" (review NIT-1)."""

    def test_freetext_label_digits_do_not_leak(self):
        from services.llm import _extract_source_numbers

        metrics = {"rows": [{"label": "Report dated 2023-04-23, id 999", "value": "1530.4"}]}
        nums = _extract_source_numbers(metrics, None)
        assert 1530.4 in nums      # the real metric value IS grounded
        assert 999 not in nums     # an id digit is NOT
        assert 2023 not in nums    # a date digit is NOT
        assert 23 not in nums

    def test_invented_number_not_grounded_by_label_date(self):
        from services.llm import _extract_source_numbers, verify_narrative_numbers

        metrics = {"rows": [{"label": "Report dated 2023-04-23, id 999"}]}
        src = _extract_source_numbers(metrics, None)
        out = verify_narrative_numbers("Efficacy reached **23%** in the cohort.", src)
        assert out["flagged"] >= 1               # the invented 23% is still caught
        assert "**23%**" not in out["narrative"]  # bold de-emphasised

    def test_value_like_units_are_still_mined(self):
        from services.llm import _extract_source_numbers

        metrics = {"rows": [{"value": "2.5x"}, {"value": "82.5%"}, {"value": "47"}]}
        nums = _extract_source_numbers(metrics, None)
        assert 2.5 in nums
        assert 82.5 in nums
        assert 47.0 in nums
