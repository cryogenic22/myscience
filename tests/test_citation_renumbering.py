"""TICKET-10 (F8): contiguous citation renumbering + a resolvable source list.

Reviewer Q2/Q4 cited [5][6][8] / [1][3][6][7] with no mapping to the surfaced
sources — `validate_citations` only strips out-of-range [N], it never renumbers,
so surviving sparse indices don't line up with the evidence array the UI shows.

The fix renumbers the surviving [N] to a contiguous 1..K in first-appearance order
and reorders evidence_items so the k-th cited source sits at index k-1 — every [N]
in the prose then resolves to a visible card. Uncited evidence is kept (after the
cited items), so nothing is dropped.

TDD: RED before the change.
"""

from __future__ import annotations

import tempfile
from unittest.mock import MagicMock

import pytest

from tests.test_ctx_corpus import (
    MOCK_DRUGS,
    MOCK_COMPANIES,
    MOCK_TRIALS,
    MOCK_MECHANISMS,
    MockDB,
)


def _ev(n):
    return [{"content": f"evidence {i}", "source": f"src{i}", "entity_id": f"e{i}"}
            for i in range(1, n + 1)]


class TestRenumberCitations:
    """Pure function: services.llm.renumber_citations."""

    def test_sparse_indices_renumbered_contiguously(self):
        from services.llm import renumber_citations

        out = renumber_citations("Alpha [5] beta [6] gamma [8].", _ev(8))
        assert out["narrative"] == "Alpha [1] beta [2] gamma [3]."
        assert out["renumbered"] == 3

    def test_evidence_reordered_to_match(self):
        from services.llm import renumber_citations

        ev = _ev(8)
        out = renumber_citations("X [5] Y [6] Z [8].", ev)
        # cited evidence leads, in citation order; then the uncited, preserved.
        assert [e["entity_id"] for e in out["evidence_items"][:3]] == ["e5", "e6", "e8"]
        assert len(out["evidence_items"]) == 8                 # nothing dropped
        assert {e["entity_id"] for e in out["evidence_items"]} == {f"e{i}" for i in range(1, 9)}

    def test_first_appearance_order(self):
        from services.llm import renumber_citations

        out = renumber_citations("First [6], then [3], then [6] again.", _ev(6))
        assert out["narrative"] == "First [1], then [2], then [1] again."

    def test_already_contiguous_is_noop(self):
        from services.llm import renumber_citations

        ev = _ev(3)
        out = renumber_citations("A [1] b [2] c [3].", ev)
        assert out["narrative"] == "A [1] b [2] c [3]."
        assert out["evidence_items"] == ev
        assert out["renumbered"] == 0

    def test_no_citations_noop(self):
        from services.llm import renumber_citations

        ev = _ev(3)
        out = renumber_citations("No citations here.", ev)
        assert out["narrative"] == "No citations here."
        assert out["evidence_items"] == ev
        assert out["renumbered"] == 0

    def test_out_of_range_indices_stripped(self):
        from services.llm import renumber_citations

        # [9] exceeds evidence count (3) — it can't resolve, so it is stripped while
        # the valid ones renumber contiguously: [2]->[1], [3]->[2].
        out = renumber_citations("A [2] b [9] c [3].", _ev(3))
        assert "[9]" not in out["narrative"]
        assert "[1]" in out["narrative"] and "[2]" in out["narrative"]
        assert out["renumbered"] == 2

    def test_out_of_range_strip_leaves_clean_punctuation(self):
        from services.llm import renumber_citations

        # Stripping [9] (only 3 items) must not orphan a space before the period.
        out = renumber_citations("Donanemab slowed decline [9].", _ev(3))
        assert out["narrative"] == "Donanemab slowed decline."
        assert out["changed"] is True

    def test_changed_flag_tracks_actual_mutation(self):
        from services.llm import renumber_citations

        # All-out-of-range: narrative IS mutated (markers stripped) but no valid
        # marker was renumbered — `changed` must be True so the log fires honestly.
        out = renumber_citations("A [9] B [10].", _ev(3))
        assert out["renumbered"] == 0
        assert out["changed"] is True
        # Already-contiguous: genuine no-op, `changed` False.
        out2 = renumber_citations("A [1] b [2].", _ev(2))
        assert out2["changed"] is False

    def test_empty(self):
        from services.llm import renumber_citations

        out = renumber_citations("", _ev(3))
        assert out["renumbered"] == 0
        assert out["changed"] is False


class TestLivePathRenumbers:
    @pytest.fixture
    def handler(self):
        from services.ctx_corpus import PharmaCorpusBuilder
        from services.unified_handler import UnifiedChatHandler

        db = MockDB()
        for t, rows in (("drugs", MOCK_DRUGS), ("companies", MOCK_COMPANIES),
                        ("clinical_trials", MOCK_TRIALS), ("mechanisms", MOCK_MECHANISMS)):
            db.set_results(t, rows)
        packed = PharmaCorpusBuilder(db).pack(tempfile.mkdtemp())
        return UnifiedChatHandler(corpus_doc=packed.document, l3_doc=packed.l3_document,
                                  llm=MagicMock(), metrics_svc=MagicMock())

    def test_sparse_citations_become_contiguous_and_resolve(self, handler):
        # Cite sparse, high-ish indices the corpus evidence does contain.
        handler.llm.synthesize.side_effect = lambda **kw: (
            "Semaglutide shows benefit [2] and a strong safety profile [4]."
        )
        result = handler.handle("Tell me about semaglutide")
        narrative = result["narrative"]
        import re
        # Scope to the PROSE only. The deterministic provenance footer appends
        # [1]..[n] for ALL evidence, so a whole-narrative citation scan is vacuous —
        # min()==1 / in-range would pass even if the prose were never renumbered.
        prose = narrative.split("\n\n**Provenance**")[0]
        n_ev = len(result["data"]["evidence"])
        prose_nums = [int(x) for x in re.findall(r"\[(\d+)\]", prose)]
        assert prose_nums, "expected citations in the prose"
        assert all(1 <= n <= n_ev for n in prose_nums)
        # The fix: the sparse markers the model emitted ([2],[4]) are renumbered to a
        # contiguous 1..K in first-appearance order, so the distinct prose citations
        # are exactly 1..K. Without the renumber this is {2,4} and FAILS (RED).
        distinct = sorted(set(prose_nums))
        assert distinct == list(range(1, len(distinct) + 1)), prose
        # And the original high index is gone from the prose — proves renumber fired
        # on the prose itself, not just the footer (which legitimately lists [4]).
        assert "[4]" not in prose, prose
