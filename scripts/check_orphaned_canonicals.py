"""Fail-loud detector for orphaned drug canonicals (conservation invariant).

A drug name is ORPHANED when it has live evidence (facts/trials) but **zero
active rows** — every row carrying its evidence is merged/superseded/excluded, so
every ``record_status``-filtering read path (CTX corpus, resolver richness rank,
dossier) skips it and a rich drug reads as "no data". This is the dominant
silent-degradation failure (#218/#220/#222) and it RECURS: a scheduled
consolidation re-demotes canonicals mid-cycle. #222 heals point-in-time; this
makes the next recurrence FAIL LOUD instead of silently rotting.

Pure core (``find_orphaned``) is Lane-1 unit-tested; ``scan`` is the live Lane-2
probe (behind DATABASE_URL). Exit code 1 if any name is orphaned above the floor.

    python -m scripts.check_orphaned_canonicals            # report + exit code
"""
from __future__ import annotations

import os
import sys

from db import Database

# Names below this live-evidence weight aren't worth flagging (long-tail noise /
# genuinely-empty). A real canonical (valsartan, ivabradine…) is far above this.
_MIN_EVIDENCE = 10


def _is_real_single_drug(name: str) -> bool:
    """Only a REAL single-drug name can be 'orphaned' — a combo, placebo arm, or
    junk row legitimately has no mono canonical, so it must not trip the invariant.
    Reuses the shared junk classifier so the detector and the consolidator agree."""
    from scripts.clean_drug_names import _should_exclude
    from scripts.consolidate_junk_drug_rows import _ADDITIVE_COMBO_RE, _NON_DRUG_TOKENS
    low = (name or "").strip().lower()
    if not low or low in _NON_DRUG_TOKENS:
        return False
    if "/" in low or _ADDITIVE_COMBO_RE.search(low):  # combo — not a mono canonical
        return False
    return not _should_exclude(name)


def find_orphaned(rows: list[dict], *, min_evidence: int = _MIN_EVIDENCE) -> list[dict]:
    """Pure: given per-row {name, status, richness}, return the REAL single-drug
    names that have >= min_evidence live evidence but NO active row holding any
    of it (the silent-degradation invariant). Junk/combo/placebo names are
    excluded — they legitimately have no mono canonical.
    """
    by_name: dict[str, dict] = {}
    for r in rows:
        nm = (r.get("name") or "").lower().strip()
        if not nm:
            continue
        agg = by_name.setdefault(nm, {"total": 0, "active": 0})
        rich = int(r.get("richness") or 0)
        agg["total"] += rich
        if r.get("status") == "active":
            agg["active"] += rich
    return [
        {"name": nm, "evidence": a["total"]}
        for nm, a in by_name.items()
        if a["total"] >= min_evidence and a["active"] == 0 and _is_real_single_drug(nm)
    ]


_SCAN_SQL = """
    WITH fc AS (SELECT subject_entity_id k, count(*) n FROM facts
                WHERE subject_entity_type='drug' AND superseded_by IS NULL
                GROUP BY subject_entity_id),
         tc AS (SELECT drug_id::text k, count(*) n FROM clinical_trials
                WHERE drug_id IS NOT NULL GROUP BY drug_id)
    SELECT lower(d.generic_name) AS name, d.record_status AS status,
           COALESCE(fc.n,0)+COALESCE(tc.n,0) AS richness
      FROM drugs d
      LEFT JOIN fc ON fc.k = d.id::text
      LEFT JOIN tc ON tc.k = d.id::text
     WHERE d.generic_name IS NOT NULL AND d.generic_name <> ''
"""


def scan(db, *, min_evidence: int = _MIN_EVIDENCE) -> list[dict]:
    rows = [dict(r) for r in (db.fetch_all(_SCAN_SQL) or [])]
    return sorted(find_orphaned(rows, min_evidence=min_evidence),
                  key=lambda o: -o["evidence"])


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


def main() -> None:
    _load_env()
    db = Database(os.environ["DATABASE_URL"])
    db.connect()
    orphaned = scan(db)
    if not orphaned:
        print("OK — no orphaned canonicals (every drug with evidence has an active row).")
        return
    print(f"FAIL — {len(orphaned)} orphaned canonical(s): evidence exists but no active row.")
    for o in orphaned[:40]:
        print(f"  {o['name']:<34} {o['evidence']:>5} live facts+trials, 0 active")
    sys.exit(1)


if __name__ == "__main__":
    main()
