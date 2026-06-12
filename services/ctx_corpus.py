"""PharmaCorpusBuilder — Export market_zero entities to CTX knowledge corpus.

Converts DB entities (drugs, companies, trials, mechanisms) into a structured
corpus directory, then runs the CTX packer to produce L2 + L3 documents.

Usage:
    builder = PharmaCorpusBuilder(db)
    result = builder.pack("/path/to/output")
    # result.document → L2 CTXDocument
    # result.l3_document → L3 directory index

Also exposes get_l3_summary(db) — a short universe-bounding summary
("Universe: N drugs, M companies...") injected into every chat system
prompt per SPEC_016 §1C so the LLM knows the world is finite.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── L3 directory summary (SPEC_016 Track 2 §1C) ────────────────────

# Cache counts for 5 minutes — these are small numbers that change slowly
# and we'd rather serve a slightly-stale count than hammer the DB per chat.
_L3_CACHE_TTL_SECONDS = 300
_l3_cache: dict = {"summary": "", "built_at": 0.0}


def get_l3_summary(db) -> str:
    """Return a short universe-bounding summary for every chat system prompt.

    Example output:
        "Universe: 1,247 drugs, 412 companies, 8,103 trials, 89 mechanisms.
        Full data hydrated per query; do NOT cite entities outside this set."

    Defensive: returns empty string on any DB error. Cached 5 min.

    Per intelligent_enterprise pattern (lib/ctx/catalog-context.ts::generateL3Index)
    — give the LLM a finite world model at the top of every prompt so it
    can't hallucinate counts like "~300 trials typical for this class".
    """
    now = time.time()
    if _l3_cache["summary"] and (now - _l3_cache["built_at"]) < _L3_CACHE_TTL_SECONDS:
        return _l3_cache["summary"]

    try:
        parts = []
        for display_name, sql in (
            ("drugs", "SELECT COUNT(*) AS n FROM drugs"),
            ("companies", "SELECT COUNT(*) AS n FROM companies"),
            ("trials", "SELECT COUNT(*) AS n FROM clinical_trials"),
            ("mechanisms", "SELECT COUNT(*) AS n FROM mechanisms_of_action"),
        ):
            try:
                row = db.fetch_one(sql)
                n = int(row.get("n", 0)) if row else 0
                if n > 0:
                    parts.append(f"{n:,} {display_name}")
            except Exception:
                # Per-count failure shouldn't kill the whole summary
                continue

        if not parts:
            return ""
        summary = (
            "Universe: " + ", ".join(parts) + ". "
            "Full data hydrated per query below; "
            "do NOT cite entities outside this set."
        )
        _l3_cache["summary"] = summary
        _l3_cache["built_at"] = now
        return summary
    except Exception as exc:
        logger.debug("get_l3_summary failed: %s", exc)
        return ""


def _clear_l3_cache() -> None:
    """For tests — force next get_l3_summary() to re-query the DB."""
    _l3_cache["summary"] = ""
    _l3_cache["built_at"] = 0.0

# Add ctxpack to path if not installed




try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

from ctxpack.core.packer import pack as ctx_pack, PackResult


# ── SQL queries for entity export ──

# ONE section per drug NAME: the best available row — prefer active, then richest.
# Two failure modes this guards against:
#   1. Empty/junk shadowing: the corpus carried merged dup rows + 'excluded' junk
#      (e.g. the 0-fact dup tirzepatide e8499246, or the pseudo-drug "Anti-obesity
#      medication with … semaglutide" that substring-matched), so hydrate_by_name
#      could report a rich, approved drug as having no data.
#   2. Silent drop (conservation): a strict active-only filter would DROP drugs
#      whose canonical was marked 'merged' with no active replacement (a real prod
#      state after the dup-consolidation loop left ~11 high-fact drugs — valsartan,
#      tirzepatide, … — with only a merged canonical). Dropping a drug that owns
#      hundreds of facts is itself silent data loss.
# So: exclude only 'excluded'/'stale' junk; among the rest prefer active, then
# richest (facts + trials). DISTINCT ON collapses to one row per name. This picks
# the canonical when the data is healthy and the richest survivor when it isn't —
# and forward-compatibly upgrades to the active row once the data is repaired.
_DRUGS_SQL = """
SELECT DISTINCT ON (LOWER(d.generic_name))
    d.id,
    d.generic_name,
    d.brand_name,
    m.name AS mechanism_name,
    c.name AS company_name,
    ta.name AS therapeutic_area,
    d.marketing_status AS approval_status,
    d.nda_number,
    d.supply_status
FROM drugs d
LEFT JOIN mechanisms_of_action m ON d.mechanism_id = m.id
LEFT JOIN companies c ON d.company_id = c.id
LEFT JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
WHERE COALESCE(d.record_status, 'active') NOT IN ('excluded', 'stale')
ORDER BY LOWER(d.generic_name),
    (COALESCE(d.record_status, 'active') = 'active') DESC,
    (SELECT count(*) FROM facts f
       WHERE f.subject_entity_type = 'drug'
         AND f.subject_entity_id = d.id::text
         AND f.superseded_by IS NULL)
    + (SELECT count(*) FROM clinical_trials ct WHERE ct.drug_id = d.id) DESC,
    d.id
"""

_COMPANIES_SQL = """
SELECT
    c.id,
    c.name AS company_name,
    COUNT(DISTINCT d.id) AS drug_count,
    COUNT(DISTINCT ct.id) AS trial_count,
    COALESCE(SUM(mv.pipeline_score), 0) AS pipeline_score_total
FROM companies c
LEFT JOIN drugs d ON d.company_id = c.id
LEFT JOIN clinical_trials ct ON ct.drug_id = d.id
LEFT JOIN mv_drug_pipeline_strength mv ON mv.drug_id = d.id
GROUP BY c.id, c.name
ORDER BY pipeline_score_total DESC
"""

_TRIALS_SQL = """
SELECT
    ct.id::text AS nct_id,
    ct.official_title AS title,
    ct.phase,
    ct.status,
    d.generic_name AS drug_name,
    COALESCE(ct.actual_enrollment, ct.enrollment_target) AS enrollment,
    ct.start_date
FROM clinical_trials ct
LEFT JOIN drugs d ON ct.drug_id = d.id
ORDER BY ct.start_date DESC NULLS LAST
LIMIT 500
"""

_MECHANISMS_SQL = """
SELECT
    m.id,
    m.name AS mechanism_name,
    COUNT(DISTINCT d.id) AS drug_count,
    COUNT(DISTINCT ct.id) AS trial_count
FROM mechanisms_of_action m
LEFT JOIN drugs d ON d.mechanism_id = m.id
LEFT JOIN clinical_trials ct ON ct.drug_id = d.id
GROUP BY m.id, m.name
ORDER BY drug_count DESC
"""


class PharmaCorpusBuilder:
    """Export market_zero entities to CTX-packable corpus."""

    def __init__(self, db: Any):
        self.db = db

    def export_drugs(self, limit: int | None = None) -> list[dict]:
        """Export drugs with mechanism, company, therapeutic area."""
        rows = self.db.fetch_all(_DRUGS_SQL)
        if limit:
            rows = rows[:limit]
        return [
            {
                "name": r.get("generic_name", "Unknown"),
                "brand_name": r.get("brand_name", ""),
                "mechanism": r.get("mechanism_name", ""),
                "company": r.get("company_name", ""),
                "therapeutic_area": r.get("therapeutic_area", ""),
                "approval_status": r.get("approval_status", ""),
                "nda_number": r.get("nda_number", ""),
                "supply_status": r.get("supply_status", ""),
                "id": r.get("id", ""),
            }
            for r in rows
        ]

    def export_companies(self, limit: int | None = None) -> list[dict]:
        """Export companies with portfolio metrics."""
        rows = self.db.fetch_all(_COMPANIES_SQL)
        if limit:
            rows = rows[:limit]
        return [
            {
                "name": r.get("company_name", "Unknown"),
                "drug_count": r.get("drug_count", 0),
                "trial_count": r.get("trial_count", 0),
                "pipeline_score": r.get("pipeline_score_total", 0),
                "id": r.get("id", ""),
            }
            for r in rows
        ]

    def export_trials(self, limit: int | None = None) -> list[dict]:
        """Export clinical trials with key metadata."""
        rows = self.db.fetch_all(_TRIALS_SQL)
        if limit:
            rows = rows[:limit]
        return [
            {
                "nct_id": r.get("nct_id", ""),
                "title": r.get("title", ""),
                "phase": r.get("phase", ""),
                "status": r.get("status", ""),
                "drug_name": r.get("drug_name", ""),
                "enrollment": r.get("enrollment", 0),
                "start_date": str(r.get("start_date", "")),
            }
            for r in rows
        ]

    def export_mechanisms(self, limit: int | None = None) -> list[dict]:
        """Export mechanisms with drug/trial counts."""
        rows = self.db.fetch_all(_MECHANISMS_SQL)
        if limit:
            rows = rows[:limit]
        return [
            {
                "name": r.get("mechanism_name", "Unknown"),
                "drug_count": r.get("drug_count", 0),
                "trial_count": r.get("trial_count", 0),
                "id": r.get("id", ""),
            }
            for r in rows
        ]

    def build_corpus_dir(self, output_dir: str) -> str:
        """Write entity YAML files to corpus directory.

        Creates:
            output_dir/drugs.yaml
            output_dir/companies.yaml
            output_dir/trials.yaml
            output_dir/mechanisms.yaml
            output_dir/ctxpack.yaml  (packer config)
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        drugs = self.export_drugs()
        companies = self.export_companies()
        trials = self.export_trials()
        mechanisms = self.export_mechanisms()

        # Write entity files — one YAML file per entity for CTX packer
        # Each file uses {"entity": name, ...fields} format
        for drug in drugs:
            name = drug["name"]
            safe_name = self._safe_slug(name)
            self._write_yaml(out / f"drug_{safe_name}.yaml", {
                "entity": f"DRUG-{name.upper().replace(' ', '-')}",
                "type": "drug",
                "identifier": drug.get("id", ""),
                **{k: v for k, v in drug.items() if k != "id" and v},
            })

        for company in companies:
            name = company["name"]
            safe_name = self._safe_slug(name)
            self._write_yaml(out / f"company_{safe_name}.yaml", {
                "entity": f"COMPANY-{name.upper().replace(' ', '-')}",
                "type": "company",
                "identifier": company.get("id", ""),
                **{k: v for k, v in company.items() if k != "id" and v},
            })

        for mech in mechanisms:
            name = mech["name"]
            safe_name = self._safe_slug(name)
            self._write_yaml(out / f"mechanism_{safe_name}.yaml", {
                "entity": f"MECHANISM-{name.upper().replace(' ', '-')[:60]}",
                "type": "mechanism",
                "identifier": mech.get("id", ""),
                **{k: v for k, v in mech.items() if k != "id" and v},
            })

        # Trials: group top trials as a list within a single entity file
        # (too many for individual files)
        if trials:
            trial_entries = {}
            for trial in trials[:200]:  # cap at 200
                nct = trial.get("nct_id", "unknown")
                trial_entries[nct] = {
                    "title": trial.get("title", ""),
                    "phase": trial.get("phase", ""),
                    "status": trial.get("status", ""),
                    "drug": trial.get("drug_name", ""),
                    "enrollment": trial.get("enrollment", 0),
                }
            self._write_yaml(out / "trials.yaml", trial_entries)

        # Write packer config
        config = {
            "domain": "pharma-intelligence",
            "scope": "market-zero-knowledge-base",
            "author": "market-zero-pipeline",
            "layers": ["L2", "L3"],
            "preset": "balanced",
            "provenance": "inline",
        }
        self._write_yaml(out / "ctxpack.yaml", config)

        logger.info(
            "Corpus built: %d drugs, %d companies, %d trials, %d mechanisms → %s",
            len(drugs), len(companies), len(trials), len(mechanisms), output_dir,
        )
        return output_dir

    def pack(self, output_dir: str) -> PackResult:
        """Build corpus directory and run CTX packer → L2 + L3 documents."""
        self.build_corpus_dir(output_dir)
        result = ctx_pack(
            output_dir,
            domain="pharma-intelligence",
            scope="market-zero-knowledge-base",
            author="market-zero-pipeline",
            layers=["L2", "L3"],
            preset="balanced",
        )
        logger.info(
            "Packed: %d entities, %d source tokens, %d warnings",
            result.entity_count,
            result.source_token_count,
            result.warning_count,
        )
        return result

    @staticmethod
    def _safe_slug(name: str) -> str:
        """Filesystem-safe slug for a per-entity filename. Entity names carry
        characters illegal in Windows paths (" : < > | ? *) and awkward on any
        FS; keep only [a-z0-9._-], collapse the rest to '_'. (A drug literally
        named 'Karolinska Cocktail' with a quote crashed pack() on Windows.)"""
        import re as _re
        slug = _re.sub(r"[^a-z0-9._-]+", "_", (name or "").lower()).strip("_")
        return (slug or "unnamed")[:50]

    @staticmethod
    def _corpus_safe_str(s: str) -> str:
        """Neutralise characters the ctxpack YAML parser rejects as anchors/
        aliases/tags. Its naive regex flags ``&word`` / ``*word`` / ``!word``
        anywhere on a line, and real entity names carry them ("R&D"). The corpus
        is a DERIVED artifact (the DB keeps the original), so render ID-safe:
        ``&`` -> "and"; drop a ``*`` / ``!`` that directly precedes a letter."""
        import re as _re
        s = s.replace("&", "and")
        return _re.sub(r"[*!](?=[A-Za-z])", "", s)

    @staticmethod
    def _plain(obj):
        """Coerce DB-derived values to plain Python types before YAML dump.
        psycopg2 returns numerics as Decimal and timestamps as datetime; PyYAML
        serialises those with a ``!!python/...`` tag that the ctxpack YAML parser
        rejects — which silently broke pack() and with it the whole unified
        handler. Decimal -> float, datetime/date -> ISO, str -> corpus-safe."""
        from decimal import Decimal
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, str):
            return PharmaCorpusBuilder._corpus_safe_str(obj)
        if isinstance(obj, dict):
            return {k: PharmaCorpusBuilder._plain(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [PharmaCorpusBuilder._plain(v) for v in obj]
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return obj

    @staticmethod
    def _write_yaml(path: Path, data: Any) -> None:
        """Write data to YAML file.

        The ctxpack YAML parser supports only a restricted subset: no Python
        tags, no anchors/aliases, no block scalars. So we coerce to plain types
        (_plain) and force a no-alias dumper, otherwise pack() raises and the
        unified handler silently dies back to the legacy path.
        """
        data = PharmaCorpusBuilder._plain(data)
        if yaml is not None:
            class _NoAliasDumper(yaml.Dumper):
                def ignore_aliases(self, data):  # never emit &anchors / *aliases
                    return True

            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(
                    data, f, Dumper=_NoAliasDumper,
                    default_flow_style=False, allow_unicode=True, sort_keys=False,
                    width=10**9,  # don't wrap long scalars into block style
                )
        else:
            # Fallback: write as JSON (CTX packer can read JSON too)
            json_path = path.with_suffix(".json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
