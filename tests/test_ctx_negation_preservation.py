"""Negation preservation in the CTX corpus — a compressor must never invert
clinical meaning ("did not meet its primary endpoint" -> "meet ...").

Why this file exists (finding 2026-07-04):
    market_zero's app code loads a VENDORED ctxpack 0.3.0 (`market_zero/ctxpack/`),
    whose prose compressor `md_parser._compress_prose` lists "no"/"not" as filler
    words and strips them — a full clinical inversion (the 4 cases in
    PHARMA_NEGATIONS below all invert under 0.3.0, all survive under >=0.5.0). The
    installed >=0.5.0 (used by the ctx hooks/MCP via `python -P`) fixed
    this and guards it. `PharmaCorpusBuilder` is safe *today* only by an accident of
    data shape: it emits YAML entity files, and the vendored 0.3.0 *YAML* value path
    preserves negations — but the moment a markdown/prose source enters the corpus
    dir, packing routes it through `_compress_prose` and the inversion goes live,
    silently. These tests fail closed on both failure modes until the vendored copy
    is upgraded to >=0.5.0 (Track B). See memory: project_ctx_literals_ledger.

These import the SAME ctxpack the application loads (the vendored copy, because
pytest runs with the repo root on sys.path) — so they assert the behavior that
actually ships, not the installed >=0.5.0.
"""

import re
import tempfile
from pathlib import Path

import pytest

# Negation tokens whose loss inverts meaning.
_NEG_RE = re.compile(r"\b(no|not|never|none|cannot|without|n't)\b", re.IGNORECASE)


def _neg_count(text: str) -> int:
    return len(_NEG_RE.findall(text or ""))


# Pharma negations whose inversion is a safety event.
PHARMA_NEGATIONS = [
    "did not meet its primary endpoint",
    "not approved for pediatric use",
    "no significant difference between arms",
    "should not be co-administered with warfarin",
]


class _MockDB:
    """Minimal DB stub routing by the FROM table (mirrors tests/test_ctx_corpus.py)."""

    def __init__(self, results: dict):
        self._results = results

    def fetch_all(self, sql: str, params=None):
        m = re.search(r"\bfrom\s+(\w+)", sql.lower())
        if m and m.group(1) in self._results:
            return self._results[m.group(1)]
        for key, rows in self._results.items():
            if key in sql.lower():
                return rows
        return []

    def fetch_one(self, sql: str, params=None):
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None


# ── Failure mode 1: the YAML value path (what makes the corpus safe today) ──

def test_app_yaml_value_compressor_preserves_negations():
    """The vendored YAML value compressor is the ONLY reason today's corpus is
    negation-safe. Pin it: if a future ctxpack regresses the YAML path, fail here."""
    from ctxpack.core.packer.yaml_parser import _compress_value, _compress_scalar

    for phrase in PHARMA_NEGATIONS:
        for fn in (_compress_value, _compress_scalar):
            out = fn(phrase)
            assert _neg_count(out) >= _neg_count(phrase), (
                f"{fn.__name__} dropped a negation: {phrase!r} -> {out!r}"
            )


# ── Failure mode 2: prose/markdown must never enter the corpus dir ──

def test_corpus_dir_is_yaml_only():
    """Only the YAML path is negation-safe on the vendored 0.3.0. A prose/markdown
    source would be routed through the inverting `_compress_prose`. Contract: the
    corpus builder emits YAML sources only. Fails closed if that ever changes."""
    from services.ctx_corpus import PharmaCorpusBuilder

    db = _MockDB({
        "drugs": [{"generic_name": "canary-drug",
                   "approval_status": "not approved for pediatric use", "id": "D1"}],
    })
    with tempfile.TemporaryDirectory() as tmp:
        PharmaCorpusBuilder(db).build_corpus_dir(tmp)
        prose = [p.name for p in Path(tmp).iterdir()
                 if p.suffix.lower() in {".md", ".markdown", ".txt", ".rst"}]
        assert not prose, (
            f"prose/markdown source(s) in the corpus dir: {prose} — the vendored "
            f"0.3.0 prose compressor strips negations; keep the corpus YAML-only "
            f"until ctxpack is upgraded to >=0.5.0"
        )


# ── End-to-end: a planted negation is never inverted by a full pack ──

def test_negation_never_inverted_end_to_end():
    """Pack a corpus carrying pharma negations and assert each negation SURVIVES in
    the serialized L2. The MockDB input is fixed and the balanced preset keeps these
    fields (verified), so survival is deterministic — asserting it directly is
    stronger than a substring "no-inversion" check, which a real prose regression
    could dodge by ALSO stripping "its" (so the bare phrase never matches and the
    guard silently no-ops). Stripping "not" trips these. If a future budgeter ever
    starts eliding a safety-relevant field, that red is itself worth surfacing."""
    from services.ctx_corpus import PharmaCorpusBuilder
    from ctxpack.core.serializer import serialize

    db = _MockDB({
        "drugs": [{"generic_name": "canary-drug",
                   "approval_status": "not approved for pediatric use", "id": "D1"}],
        "clinical_trials": [{"nct_id": "NCT00000000",
                             "title": "Phase 3 study did not meet its primary endpoint",
                             "phase": "3", "status": "Completed",
                             "drug_name": "canary-drug", "enrollment": 100,
                             "start_date": "2024-01-01"}],
    })
    with tempfile.TemporaryDirectory() as tmp:
        result = PharmaCorpusBuilder(db).pack(tmp)
    text = serialize(result.document).lower()

    # Each planted negation must survive with its claim; a prose regression strips
    # "not" (and "its"), which trips these regexes (robust to filler-stripping).
    assert re.search(r"not\s+approved", text), (
        "approval negation lost or inverted in the packed corpus "
        "(expected 'not approved …' to survive)"
    )
    assert re.search(r"not\s+meet|did\s+not\s+meet", text), (
        "trial-endpoint negation lost or inverted in the packed corpus "
        "(expected 'did not meet …' to survive)"
    )


# ── Documents the live defect; xpasses (strict -> RED) once Track B upgrade lands ──

@pytest.mark.xfail(
    strict=True,
    reason="Vendored ctxpack 0.3.0's _compress_prose strips 'no'/'not' (clinical "
           "inversion). Safe today only because ctx_corpus emits YAML, not prose. "
           "This XPASSES once the vendored copy is upgraded to >=0.5.0 — when it "
           "does, delete this xfail marker (the hazard is gone).",
)
def test_vendored_prose_compressor_is_the_known_hazard():
    from ctxpack.core.packer.md_parser import _compress_prose

    for phrase in PHARMA_NEGATIONS:
        out = _compress_prose(phrase)
        assert _neg_count(out) >= _neg_count(phrase), (
            f"_compress_prose dropped a negation: {phrase!r} -> {out!r}"
        )
