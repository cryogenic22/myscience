"""Absorb wrongly-excluded real-config drug rows into their canonical.

**Loop A follow-up.** #218's junk pass quarantined some rows as
``record_status='excluded'`` that are actually real configurations of a drug
("ivabradine oral tablet", "finerenone oral tablet"). With the canonical merged
at the time, they kept their facts; now that Loop A (#222) restored the active
canonical, those excluded rows out-rank it via ``_exact_lookup`` (which excludes
merged/superseded but not excluded). The conservation-correct fix is to ABSORB
them — repoint their facts/trials/signals into the canonical and supersede —
NOT to hide them with a filter (which would silently lose real facts).

Targeted + safe: processes ONLY ``excluded`` rows (never the whole spine), and
only absorbs one that the shared junk classifier rules an attributable
fragment/dup of a now-ACTIVE canonical. Genuine junk ("placebo (matching)",
"drugA or drugB") stays excluded. Reuses ``classify`` and the hardened,
conflict-safe ``EntityConsolidator._merge_drug``. Reversible (manifest +
soft-delete), idempotent (a row with no remaining refs is a no-op).

    python -m scripts.absorb_excluded_configs            # dry-run
    python -m scripts.absorb_excluded_configs --apply
"""
from __future__ import annotations

import argparse
import json
import os

from db import Database
from scripts.consolidate_junk_drug_rows import (
    _ADDITIVE_COMBO_RE,
    _build_real_names,
    _norm,
    _owns_refs,
    classify,
    real_name_hits,
)


def _looks_combo(name: str, real_names: set) -> bool:
    """A multi-drug combo must NEVER be absorbed into one mono component (its
    facts are combo-specific — collapsing pollutes the mono). The shared
    classifier's additive guard catches '+/and/plus' but not the '/'-style
    "valsartan/amlodipine"; and it can under-count hits. Guard explicitly: a '/'
    joining tokens, an additive marker, or 2+ distinct embedded real drugs."""
    low = (name or "").lower()
    if "/" in low:
        return True
    if _ADDITIVE_COMBO_RE.search(low):
        return True
    return len(real_name_hits(name, real_names, self_name=name)) >= 2

_MANIFEST = os.path.join("benchmark", "reports", "absorb_excluded_configs_manifest.json")


def _load_env():
    for b in (os.getcwd(), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
        p = os.path.join(b, ".env")
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return


def run(db, *, dry_run: bool = True, min_richness: int = 5) -> dict:
    from integration.entity_consolidator import EntityConsolidator

    consolidator = EntityConsolidator(db, dry_run=dry_run, rank_by_richness=True)
    real_names = _build_real_names(db)

    # Candidates: ONLY excluded rows that still own evidence.
    excluded = db.fetch_all(
        "SELECT id, generic_name, brand_name, record_status FROM drugs "
        "WHERE record_status = 'excluded' AND generic_name IS NOT NULL")

    # The absorb targets are the canonicals for the excluded rows' base names AND
    # the real drugs their names embed (a "X oral tablet" absorbs into X). Scope
    # the (slow) richness ranking to just those norms — not the whole spine.
    from scripts.consolidate_junk_drug_rows import real_name_hits
    wanted_norms: set[str] = set()
    for c in excluded:
        nm = c["generic_name"]
        wanted_norms.add(_norm(nm))
        for hit in real_name_hits(nm, real_names, self_name=nm):
            wanted_norms.add(_norm(hit))
    wanted_norms.discard("")

    actives = db.fetch_all(
        "SELECT id, generic_name FROM drugs "
        "WHERE generic_name IS NOT NULL AND generic_name <> '' "
        "  AND record_status NOT IN ('merged','superseded','excluded')")
    by_norm: dict[str, list[dict]] = {}
    for a in actives:
        n = _norm(a["generic_name"])
        if n in wanted_norms:
            by_norm.setdefault(n, []).append(a)
    canonical_norm_to_id = {
        norm: str(max(rows, key=lambda r: consolidator._drug_richness(str(r["id"])))["id"])
        for norm, rows in by_norm.items() if norm
    }

    plan: list[dict] = []
    absorbed = skipped = 0
    for c in excluded:
        cid = str(c["id"])
        name = c["generic_name"]
        if not _owns_refs(db, cid):
            skipped += 1
            continue
        v = classify(name, real_names, _norm(name), canonical_norm_to_id, cid)
        if v.action != "absorb":
            skipped += 1  # genuine junk / ambiguous → stays excluded
            continue
        if _looks_combo(name, real_names):
            skipped += 1  # multi-drug combo → never collapse into one mono
            continue
        parent_id = canonical_norm_to_id.get(_norm(v.parent_name))
        if not parent_id or parent_id == cid:
            skipped += 1
            continue
        entry = {"id": cid, "name": name, "into": parent_id, "reason": v.reason}
        plan.append(entry)
        absorbed += 1
        if not dry_run:
            canonical = db.fetch_one("SELECT * FROM drugs WHERE id = %s", [parent_id])
            dup = db.fetch_one("SELECT * FROM drugs WHERE id = %s", [cid])
            consolidator._merge_drug(canonical, dup)

    if not dry_run and plan:
        os.makedirs(os.path.dirname(_MANIFEST), exist_ok=True)
        with open(_MANIFEST, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, indent=2)
    return {"absorbed": absorbed, "skipped": skipped, "plan": plan}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    _load_env()
    db = Database(os.environ["DATABASE_URL"])
    db.connect()
    stats = run(db, dry_run=not args.apply)
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"=== absorb_excluded_configs [{mode}] — {stats['absorbed']} absorbed, "
          f"{stats['skipped']} left excluded ===")
    for e in stats["plan"]:
        nm = e["name"].encode("ascii", "replace").decode()
        print(f"  {nm:<42} -> {e['into'][:8]} ({e['reason']})")


if __name__ == "__main__":
    main()
