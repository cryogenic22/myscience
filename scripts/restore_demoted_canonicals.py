"""Restore canonical drug rows the legacy consolidator silently demoted.

**#218/#220 follow-up.** A pre-#220 scheduled ``consolidate_drugs`` run picked
canonicals by *source authority* instead of *richness* and only moved
``entity_links`` — so it demoted rich canonical drug rows to
``record_status='merged'`` / ``'superseded'`` **without repointing their
facts/trials and without leaving an active survivor**. The facts still sit on the
demoted rows, but every ``record_status``-filtering read path (CTX corpus, the
resolver's richness rank, dossier assembly) skips them → a rich drug reads as
"no data". #220 (5b1f9ad) stopped the *vector* (``consolidate_drugs`` now
delegates to ``EntityConsolidator(rank_by_richness=True)``); this repairs the
*data* it left stranded spine-wide.

**Repair** = flip the richest demoted row back to ``'active'`` for each real-drug
name whose demoted row is richer than any active sibling. Facts already live on
the row, so this is a pure *visibility* restore — no fact mutation, fully
reversible (manifest → flip back to the recorded prior status). Idempotent: once
a name's richest row is active it is no longer selected.

Once the canonical is active again, the now-fixed scheduled consolidator will,
on its next run, absorb any remaining same-normalized duplicate rows *into* it
(rank_by_richness keeps the active canonical) — so this loop deliberately does
NOT re-merge the small dup rows; it just re-enables the correct machinery.

Usage::

    python -m scripts.restore_demoted_canonicals            # dry-run (default)
    python -m scripts.restore_demoted_canonicals --apply
    python -m scripts.restore_demoted_canonicals --reverse  # undo from manifest
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field

from db import Database
from scripts.clean_drug_names import _should_exclude
from scripts.consolidate_junk_drug_rows import _DISJUNCTION_RE, _NON_DRUG_TOKENS

_MANIFEST = os.path.join("benchmark", "reports",
                         "restore_demoted_canonicals_manifest.json")
_DEMOTED = ("merged", "superseded")


# ── pure core (DB-free, unit-tested) ───────────────────────────────────────

@dataclass
class Restoration:
    drug_id: str
    name: str
    prior_status: str
    richness: int


def is_restorable_name(name: str | None) -> bool:
    """A real single-drug name safe to re-activate. Rejects junk/ambiguous rows
    using the SAME discipline as the junk-consolidation loop, so the two never
    disagree: clean_drug_names junk patterns, a 'drugA or drugB' disjunction,
    and bare non-drug trial tokens ('placebo', 'comparator', 'medication')."""
    low = (name or "").strip().lower()
    if not low:
        return False
    if _should_exclude(name):
        return False
    if _DISJUNCTION_RE.search(low):
        return False
    if " " not in low and low in _NON_DRUG_TOKENS:
        return False
    return True


def select_restorations(rows: list[dict], *, min_richness: int = 10) -> list[Restoration]:
    """Pick the rows to re-activate.

    ``rows`` are the per-(lower-name) ranked rows carrying ``rk`` (1 = richest
    for that name), ``record_status``, ``richness`` and ``best_active_richness``
    (richest active sibling, 0 if none). A name is repaired when its richest row
    is demoted, is richer than any active sibling (silent degradation), clears
    the richness floor, and is a real drug name.
    """
    out: list[Restoration] = []
    for r in rows:
        if r["rk"] != 1:
            continue
        if r["record_status"] not in _DEMOTED:
            continue
        if r["best_active_richness"] >= r["richness"]:
            continue  # an active row already represents this name as well or better
        if r["richness"] < min_richness:
            continue
        if not is_restorable_name(r["gname"]):
            continue
        out.append(Restoration(r["id"], r["gname"], r["record_status"], r["richness"]))
    return out


# ── DB orchestration ───────────────────────────────────────────────────────

@dataclass
class RunStats:
    restored: int = 0
    plan: list = field(default_factory=list)


_RANKED_SQL = """
WITH fc AS (
    SELECT subject_entity_id k, count(*) n FROM facts
    WHERE subject_entity_type='drug' AND superseded_by IS NULL
    GROUP BY subject_entity_id
),
tc AS (
    SELECT drug_id::text k, count(*) n FROM clinical_trials
    WHERE drug_id IS NOT NULL GROUP BY drug_id
),
dr AS (
    SELECT d.id::text id, lower(d.generic_name) gname, d.record_status,
           COALESCE(fc.n,0)+COALESCE(tc.n,0) richness
    FROM drugs d
    LEFT JOIN fc ON fc.k=d.id::text
    LEFT JOIN tc ON tc.k=d.id::text
    WHERE d.generic_name IS NOT NULL
)
SELECT id, gname, record_status, richness,
       row_number() OVER (PARTITION BY gname ORDER BY richness DESC, id) AS rk,
       COALESCE(max(richness) FILTER (WHERE record_status='active')
                OVER (PARTITION BY gname), 0) AS best_active_richness
FROM dr
"""


def _fetch_ranked(db: Database) -> list[dict]:
    return [dict(r) for r in db.fetch_all(_RANKED_SQL)]


def restore(db: Database, *, dry_run: bool = True, min_richness: int = 10) -> RunStats:
    plan = select_restorations(_fetch_ranked(db), min_richness=min_richness)
    stats = RunStats(plan=[r.__dict__ for r in plan])
    if dry_run:
        return stats
    for r in plan:
        # idempotent guard: only touches a still-demoted row
        db.execute(
            "UPDATE drugs SET record_status='active', updated_at=NOW() "
            "WHERE id=%s AND record_status IN ('merged','superseded')",
            (r.drug_id,),
        )
        stats.restored += 1
    os.makedirs(os.path.dirname(_MANIFEST), exist_ok=True)
    with open(_MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(stats.plan, fh, indent=2)
    return stats


def reverse(db: Database) -> int:
    """Undo a prior apply: flip restored rows back to their recorded prior
    status. Reversibility per conservation gates."""
    if not os.path.exists(_MANIFEST):
        raise SystemExit("no manifest to reverse")
    with open(_MANIFEST, encoding="utf-8") as fh:
        plan = json.load(fh)
    n = 0
    for r in plan:
        db.execute(
            "UPDATE drugs SET record_status=%s, updated_at=NOW() "
            "WHERE id=%s AND record_status='active'",
            (r["prior_status"], r["drug_id"]),
        )
        n += 1
    return n


def _load_env():
    for base in (os.getcwd(), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
        p = os.path.join(base, ".env")
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="execute (default dry-run)")
    ap.add_argument("--reverse", action="store_true", help="undo from manifest")
    ap.add_argument("--min-richness", type=int, default=10)
    args = ap.parse_args()

    _load_env()
    db = Database(os.environ["DATABASE_URL"])
    db.connect()

    if args.reverse:
        print(f"reversed {reverse(db)} rows")
        return

    stats = restore(db, dry_run=not args.apply, min_richness=args.min_richness)
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"=== restore_demoted_canonicals [{mode}] — {len(stats.plan)} canonicals ===")
    for r in stats.plan:
        print(f"  {r['name']:<34} {r['prior_status']:<10} richness={r['richness']:>4} "
              f"id={r['drug_id']}")
    if not args.apply:
        print("\n(dry-run — re-run with --apply to restore)")


if __name__ == "__main__":
    main()
