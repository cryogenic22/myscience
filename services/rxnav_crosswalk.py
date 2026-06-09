#!/usr/bin/env python
"""Loop L1b-ii — bulk RxNorm / ATC crosswalk load from the RxNav REST API.

Loop L1b seeded crosswalk_records from an SME smoke-test set (5 drugs). This is
the bulk path: for each active drug it asks RxNav (NLM, free, no licence, no file
download) for the drug's RxNorm ingredient (IN) concept and its ATC class
membership, then runs each through the SAME governed engine
(services.ontology_crosswalk.classify) and the SAME write path
(services.crosswalk_loader.persist_crosswalk_record) as the seed loader — one
governed pipeline, not a second drifting copy.

Two records per drug where available:
  * RxNorm IN  → identity-grade (exact, substance_level) — this is what lifts
    semantic_resolution.ontology_support to full identity grade for that drug.
  * ATC class  → class-level ONLY (the SME rule: ATC never grades exact identity).
    Loaded UNCURATED (source_curated=False): a raw release code is not an
    SME-reviewed mapping, so it earns no curated-crosswalk confidence boost.

Conservation: the governed engine decides accept / audit / review / reject and only
an accepted ATC mapping enriches drugs.atc_codes; every verdict is recorded
(auditable, never silently dropped). Idempotent (upsert on the natural key).
Network failures per drug are counted and skipped, never fatal. Dry-run by default.

Usage (module form so cwd wins over the editable-install config shadow):
    DATABASE_URL=... python -m services.rxnav_crosswalk --limit 200        # dry run
    DATABASE_URL=... python -m services.rxnav_crosswalk --limit 200 --apply
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from collections import Counter
from typing import Optional

from services.ontology_crosswalk import CrosswalkCandidate, load_crosswalk_pack
from services.crosswalk_loader import persist_crosswalk_record

logger = logging.getLogger(__name__)

RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"
SOURCE_VERSION = "rxnav_rest_2026-06-09"


# ── pure: response parsers ──────────────────────────────────────────────────────

def parse_rxcui(payload: dict) -> Optional[str]:
    """First RxCUI from an /rxcui.json idGroup response, or None."""
    ids = ((payload or {}).get("idGroup") or {}).get("rxnormId") or []
    return str(ids[0]) if ids else None


def atc_level(code: Optional[str]) -> Optional[int]:
    """ATC level from code length: A=1, A10=2, A10B=3, A10BJ=4, A10BJ06=5."""
    by_len = {1: 1, 3: 2, 4: 3, 5: 4, 7: 5}
    return by_len.get(len((code or "").strip())) if code else None


def parse_deepest_atc(payload: dict) -> Optional[dict]:
    """The most specific (deepest-level) ATC class in an /rxclass byRxcui response,
    as {code, label, level}. The deepest class implies its parents, so recording it
    alone avoids flooding the ledger with every ancestor level."""
    infos = (((payload or {}).get("rxclassDrugInfoList") or {})
             .get("rxclassDrugInfo") or [])
    best: Optional[dict] = None
    for di in infos:
        mc = di.get("rxclassMinConceptItem") or {}
        code = mc.get("classId")
        lvl = atc_level(code)
        if lvl is None:
            continue
        if best is None or lvl > best["level"]:
            best = {"code": code, "label": mc.get("className") or code, "level": lvl}
    return best


# ── pure: governed candidate builders ───────────────────────────────────────────

def build_rxnorm_ingredient_candidate(rxcui: str) -> CrosswalkCandidate:
    """An RxNorm ingredient (IN) asserting molecule identity — identity-grade."""
    return CrosswalkCandidate(
        from_system="rxnorm", tty="IN", to_target="molecule",
        method="exact_identifier", external_id=str(rxcui), source_curated=False)


def build_rxnav_atc_candidate(code: str, level: int, pack: dict) -> CrosswalkCandidate:
    """An ATC class at ``level`` asserting class membership. The to_target is the
    level's first allowed target from the pack (drug_class / therapeutic_area), so
    it can never trip the identity-grade allowlist. UNCURATED (raw release)."""
    allowed = ((pack.get("atc_level") or {}).get(level) or {}).get("allowed_targets") or ["drug_class"]
    return CrosswalkCandidate(
        from_system="atc", level=level, to_target=allowed[0],
        method="external_source_crosswalk", external_id=str(code), source_curated=False)


# ── HTTP fetch (live RxNav) ─────────────────────────────────────────────────────

def fetch_drug_ontology(client, name: str) -> dict:
    """{rxcui_in, rxcui_any, atc:{code,label,level}|None} for a drug name. Best-effort;
    a missing concept is simply absent (caller counts it)."""
    out: dict = {"rxcui_in": None, "rxcui_any": None, "atc": None}
    in_resp = client.get(f"{RXNAV_BASE}/rxcui.json",
                         params={"name": name, "tty": "IN"})
    out["rxcui_in"] = parse_rxcui(in_resp.json()) if in_resp.status_code == 200 else None
    rxcui_any = out["rxcui_in"]
    if not rxcui_any:
        any_resp = client.get(f"{RXNAV_BASE}/rxcui.json", params={"name": name})
        rxcui_any = parse_rxcui(any_resp.json()) if any_resp.status_code == 200 else None
    out["rxcui_any"] = rxcui_any
    if rxcui_any:
        cls = client.get(f"{RXNAV_BASE}/rxclass/class/byRxcui.json",
                         params={"rxcui": rxcui_any, "relaSource": "ATC"})
        if cls.status_code == 200:
            out["atc"] = parse_deepest_atc(cls.json())
    return out


# ── bulk loader ──────────────────────────────────────────────────────────────────

def _active_drugs(db, limit: Optional[int]) -> list[dict]:
    """Active drugs, richest first (so a bounded run covers the drugs that matter)."""
    sql = (
        "SELECT id::text AS id, generic_name FROM drugs "
        "WHERE record_status = 'active' AND generic_name IS NOT NULL "
        "  AND length(generic_name) >= 3 "
        "ORDER BY (SELECT count(*) FROM facts f WHERE f.subject_entity_id = drugs.id::text) "
        "       + (SELECT count(*) FROM clinical_trials ct WHERE ct.drug_id = drugs.id) DESC, id "
    )
    if limit is not None:
        sql += f"LIMIT {int(limit)}"
    return db.fetch_all(sql) or []


def load_rxnav_crosswalk(db, *, limit: Optional[int] = None, apply: bool = False,
                         client=None, pause: float = 0.05) -> Counter:
    """Bulk-load RxNorm IN + ATC class crosswalk records for active drugs."""
    from services.ontology_crosswalk import classify
    pack = load_crosswalk_pack()
    stats: Counter = Counter()

    owns_client = client is None
    if owns_client:
        import httpx
        client = httpx.Client(timeout=20)
    try:
        for drug in _active_drugs(db, limit):
            stats["drugs"] += 1
            name = drug["generic_name"]
            try:
                onto = fetch_drug_ontology(client, name)
            except Exception:
                stats["fetch_error"] += 1
                logger.debug("RxNav fetch failed for %r", name, exc_info=True)
                continue

            if onto["rxcui_in"]:
                rec = classify(build_rxnorm_ingredient_candidate(onto["rxcui_in"]), pack)
                res = persist_crosswalk_record(
                    db, internal_entity_id=drug["id"], external_system="rxnorm",
                    external_id=onto["rxcui_in"],
                    external_label=f"RxNorm IN {onto['rxcui_in']} ({name})",
                    rec=rec, source_version=SOURCE_VERSION,
                    method="exact_identifier", apply=apply)
                stats["rxnorm_written"] += res["written"]
            else:
                stats["no_rxcui"] += 1

            atc = onto["atc"]
            if atc:
                rec = classify(build_rxnav_atc_candidate(atc["code"], atc["level"], pack), pack)
                res = persist_crosswalk_record(
                    db, internal_entity_id=drug["id"], external_system="atc",
                    external_id=atc["code"], external_label=f"{atc['code']} ({atc['label']})",
                    rec=rec, source_version=SOURCE_VERSION, apply=apply)
                stats["atc_written"] += res["written"]
                stats["atc_spine_backfilled"] += res["backfilled"]
                stats[f"atc_verdict_{rec.action}"] += 1
            else:
                stats["no_atc"] += 1

            if pause:
                time.sleep(pause)
    finally:
        if owns_client:
            client.close()
    return stats


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="max drugs (richest first)")
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = ap.parse_args()

    from db import Database
    dsn = os.environ.get("DATABASE_URL") or __import__("config").config.db.dsn
    db = Database(dsn)
    db.connect()
    try:
        stats = load_rxnav_crosswalk(db, limit=args.limit, apply=args.apply)
    finally:
        db.close()
    mode = "APPLY" if args.apply else "DRY-RUN"
    logger.info("[%s] %s", mode, dict(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
