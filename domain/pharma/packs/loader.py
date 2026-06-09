"""
Domain-pack loader — makes the semantic-resolution engine pack-driven.

The engine (drug_mention_parser + semantic_resolution) stays pure and generic;
ALL pharma judgement (lexicon terms, confidence weights, thresholds, combo-only
components, merge policy) lives in versioned YAML packs under this directory and
is loaded here. This is the "configurable" half of modular+configurable: swap the
pack (or override fields per use-case / market / tenant) without touching code.

Pack suite (per docs/domain_pack_raw.md + docs/YAML_pack1.md):
  pharma_core, pharma_semantic_resolution (this engine), pharma_source_contracts,
  pharma_fact_signal_gap_contracts, pharma_confidence_stewardship_eval,
  obesity_metabolic_playbooks, eval_semantic_resolution.
Only the two the engine consumes are wired today; the rest are the roadmap.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Optional

import yaml

from domain.pharma.drug_mention_parser import DEFAULT_LEXICON, DrugLexicon
from services.semantic_resolution import DEFAULT_POLICY, ResolutionPolicy

PACK_DIR = pathlib.Path(__file__).parent


@dataclass
class PackBundle:
    """Loaded, engine-ready configuration from a semantic-resolution pack."""
    lexicon: DrugLexicon
    policy: ResolutionPolicy
    pack_id: str
    version: str
    raw: dict


def _frozen(value, default):
    return frozenset(value) if value is not None else default


def load_pack(name: str = "pharma_semantic_resolution",
              pack_dir: Optional[pathlib.Path] = None) -> PackBundle:
    """Load a semantic-resolution pack YAML into a DrugLexicon + ResolutionPolicy.

    Missing file or missing keys fall back to the engine defaults — the pack
    only overrides what it declares, so a partial pack is valid.
    """
    path = (pack_dir or PACK_DIR) / f"{name}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    data = data or {}

    lex = data.get("lexicon", {}) or {}
    lexicon = DrugLexicon(
        formulations=_frozen(lex.get("formulations"), DEFAULT_LEXICON.formulations),
        routes=_frozen(lex.get("routes"), DEFAULT_LEXICON.routes),
        release_qualifiers=_frozen(lex.get("release_qualifiers"), DEFAULT_LEXICON.release_qualifiers),
        salt_tokens=_frozen(lex.get("salt_tokens"), DEFAULT_LEXICON.salt_tokens),
        regimen=lex.get("regimen") or dict(DEFAULT_LEXICON.regimen),
        context=lex.get("context") or dict(DEFAULT_LEXICON.context),
        brands=lex.get("brands") or {},
    )

    pol = data.get("policy", {}) or {}
    d = DEFAULT_POLICY
    policy = ResolutionPolicy(
        auto_resolve_threshold=pol.get("auto_resolve_threshold", d.auto_resolve_threshold),
        min_margin_over_second=pol.get("min_margin_over_second", d.min_margin_over_second),
        collapse_salt=pol.get("collapse_salt", d.collapse_salt),
        collapse_release=pol.get("collapse_release", d.collapse_release),
        distinguish_market=pol.get("distinguish_market", d.distinguish_market),
        distinguish_formulation=pol.get("distinguish_formulation", d.distinguish_formulation),
        distinguish_route=pol.get("distinguish_route", d.distinguish_route),
        low_source_reliability=pol.get("low_source_reliability", d.low_source_reliability),
        combo_only_components=frozenset(
            c.lower() for c in (pol.get("combo_only_components") or [])),
        weights=pol.get("weights") or dict(d.weights),
    )

    return PackBundle(
        lexicon=lexicon,
        policy=policy,
        pack_id=(data.get("pack") or {}).get("id", name),
        version=str((data.get("pack") or {}).get("version", "0")),
        raw=data,
    )
