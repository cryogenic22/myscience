"""SPEC_024 — Evidence Ledger service.

Content-addressed claim provenance. Every claim is backed by one or more
immutable evidence records; every Decision can be reproduced by re-hydrating
the evidence_snapshot that was frozen at commit time.

Hash specification (must be deterministic):

  claim_text_hash:    sha256(claim_text.strip().encode("utf-8"))
  source_content_hash sha256(extracted_text.encode("utf-8"))            (no trim — exact bytes)
  snapshot_hash:      sha256(canonical_json(body).encode("utf-8"))

Canonical JSON: sort_keys=True, separators=(",", ":"), ensure_ascii=False.
The snapshot body's `claims[]` is sorted by claim_id; each entry's
`evidence_ids[]` is sorted lexically.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# Caps that the API layer also enforces; defined here so service-level callers
# (autonomous agents, batch jobs) get the same protection.
MAX_CLAIM_TEXT_LEN = 8000
MAX_EXTRACTED_TEXT_LEN = 65536  # 64 KB

VALID_CLAIM_TYPES = {
    "regulatory", "clinical", "commercial", "pricing",
    "safety", "pipeline", "other",
}
VALID_ENTITY_TYPES = {
    "drug", "company", "trial", "indication", "mechanism",
    "therapeutic_area", "event", "patent", "literature",
}
VALID_RELATIONS = {"supports", "contradicts", "qualifies"}


# ────────────────────────────────────────────────────────────────────
# Hash helpers (deterministic, public)
# ────────────────────────────────────────────────────────────────────

def hash_claim_text(claim_text: str) -> bytes:
    """Hash for claim dedup. Strips leading/trailing whitespace before hashing
    to handle copy-paste noise. Body content (interior whitespace) matters."""
    if claim_text is None:
        raise ValueError("claim_text required")
    return hashlib.sha256(claim_text.strip().encode("utf-8")).digest()


def hash_source_content(extracted_text: str) -> bytes:
    """Hash for evidence dedup. NO trim — the exact bytes the extractor saw
    is what we attest to. Two extractions that differ in even one whitespace
    char are different evidence."""
    if extracted_text is None:
        raise ValueError("extracted_text required")
    return hashlib.sha256(extracted_text.encode("utf-8")).digest()


def canonical_json(obj: Any) -> str:
    """Deterministic JSON serialization for content-addressing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_snapshot_body(body: dict) -> bytes:
    """Hash a snapshot body to its content-addressed primary key."""
    return hashlib.sha256(canonical_json(body).encode("utf-8")).digest()


def normalize_snapshot_body(
    *,
    claims: list[dict],
    brief_id: Optional[str] = None,
    decision_id: Optional[str] = None,
    snapshot_at: Optional[str] = None,  # kept as kwarg for back-compat but excluded from hash
) -> dict:
    """Build the canonical snapshot body. `claims[]` becomes sorted by
    claim_id; each entry's `evidence_ids[]` becomes sorted lexically.

    NOTE: snapshot_at is intentionally NOT included in the hashed body.
    The snapshot's identity is the (claim → evidence_ids) mapping +
    optional brief/decision context. Two snapshots of identical content
    taken seconds apart produce the same snapshot_hash, which is the
    intended idempotency behavior. The actual snapshot time lives on
    `evidence_snapshots.created_at` (DB metadata, not part of identity)."""
    _ = snapshot_at  # accepted but discarded — see above
    norm_claims = []
    for c in claims:
        cid = str(c["claim_id"])
        eids = sorted(str(e) for e in c.get("evidence_ids", []))
        norm_claims.append({"claim_id": cid, "evidence_ids": eids})
    norm_claims.sort(key=lambda x: x["claim_id"])
    body: dict = {"claims": norm_claims}
    if brief_id is not None:
        body["brief_id"] = str(brief_id)
    if decision_id is not None:
        body["decision_id"] = str(decision_id)
    return body


# ────────────────────────────────────────────────────────────────────
# Domain dataclasses
# ────────────────────────────────────────────────────────────────────

@dataclass
class EvidenceRecord:
    evidence_id: str
    source_id: str
    source_url: Optional[str]
    source_content_hash_hex: str
    archived_snapshot_ref: Optional[str]
    retrieved_at: Optional[datetime]
    extraction_method: dict
    extracted_text: str
    confidence: Optional[float]
    retrieved_by_user_id: Optional[str]
    created_at: Optional[datetime]
    # BE-1 evidence-card fields
    source_name: Optional[str] = None
    source_tier: Optional[str] = None
    published_at: Optional[datetime] = None
    snippet: Optional[str] = None
    relation: Optional[str] = None  # populated when joined via claim_evidence_links

    def to_dict(self) -> dict:
        return {
            "evidence_id": str(self.evidence_id),
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_tier": self.source_tier,
            "source_url": self.source_url,
            "source_content_hash": self.source_content_hash_hex,
            "archived_snapshot_ref": self.archived_snapshot_ref,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "extraction_method": self.extraction_method or {},
            "extracted_text": self.extracted_text,
            "snippet": self.snippet,
            "confidence": self.confidence,
            "retrieved_by_user_id": str(self.retrieved_by_user_id) if self.retrieved_by_user_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "relation": self.relation,
        }


# ────────────────────────────────────────────────────────────────────
# BE-1 — source registry + snippet helper
# ────────────────────────────────────────────────────────────────────

# (source_id substring → source_name, source_tier). First match wins.
# Tier 1 — authoritative public; Tier 2 — disclosure & news;
# Tier 3 — scientific & conference; Tier 4 — licensed CI.
_SOURCE_REGISTRY: tuple[tuple[str, str, str], ...] = (
    ("clinical_trials_gov",   "ClinicalTrials.gov",      "T1"),
    ("clinicaltrials.gov",    "ClinicalTrials.gov",      "T1"),
    ("openfda_faers",         "FDA FAERS",               "T1"),
    ("openfda_labels",        "FDA Drug Labels",         "T1"),
    ("fda_orange_book",       "FDA Orange Book",         "T1"),
    ("fda_shortages",         "FDA Drug Shortages",      "T1"),
    ("fda_opdp",              "FDA OPDP",                "T1"),
    ("fda",                   "FDA",                     "T1"),
    ("ema",                   "EMA",                     "T1"),
    ("who_ictrp",             "WHO ICTRP",               "T1"),
    ("uspto",                 "USPTO PatentsView",       "T1"),
    ("epo",                   "EPO Patents",             "T1"),
    ("cms_partd",             "CMS Medicare Part D",     "T1"),
    ("cms_pricing",           "CMS Medicare Pricing",    "T1"),
    ("va_dod",                "VA / DoD Formulary",      "T1"),
    ("sec_edgar",             "SEC EDGAR",               "T2"),
    ("sec",                   "SEC",                     "T2"),
    ("biorxiv",               "bioRxiv",                 "T3"),
    ("medrxiv",               "medRxiv",                 "T3"),
    ("pubmed",                "PubMed",                  "T3"),
    ("pmc",                   "PubMed Central",          "T3"),
    ("mesh",                  "MeSH",                    "T3"),
    ("aacr",                  "AACR",                    "T3"),
    ("asco",                  "ASCO",                    "T3"),
    ("ash",                   "ASH",                     "T3"),
)


def lookup_source_metadata(source_id: str) -> tuple[Optional[str], Optional[str]]:
    """Return ``(source_name, source_tier)`` for a known source_id slug.

    The matcher is case-insensitive and substring-style (so
    ``"openfda_faers_pull_2026_05"`` still resolves). Falls back to
    ``(source_id, "T3")`` for unknown slugs — T3 is the safe scientific
    default per the materiality scoring documentation.
    """
    if not source_id:
        return None, None
    needle = source_id.lower()
    for slug, name, tier in _SOURCE_REGISTRY:
        if slug in needle:
            return name, tier
    return source_id, "T3"


_SENTENCE_END = (". ", "! ", "? ", "; ")


def make_snippet(text: str, max_chars: int = 200) -> Optional[str]:
    """Return a single-line ~2-line preview of ``text``.

    Truncates at the last sentence boundary inside ``max_chars``;
    appends ``"…"`` if anything was dropped. Collapses whitespace so
    the result fits on two display lines without surprises.
    """
    if not text:
        return None
    # Collapse whitespace so newlines / runs don't widow lines.
    flat = " ".join(text.split())
    if len(flat) <= max_chars:
        return flat
    cut = flat[:max_chars]
    best = -1
    for sep in _SENTENCE_END:
        idx = cut.rfind(sep)
        if idx > best:
            best = idx
    if best > 80:  # only respect the boundary if it's not the very start
        return cut[: best + 1].rstrip() + " …"
    return cut.rstrip() + " …"


@dataclass
class Claim:
    claim_id: str
    claim_text: str
    claim_text_hash_hex: str
    claim_type: str
    entity_type: Optional[str]
    entity_id: Optional[str]
    confidence: Optional[float]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    evidence: list[EvidenceRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "claim_id": str(self.claim_id),
            "claim_text": self.claim_text,
            "claim_text_hash": self.claim_text_hash_hex,
            "claim_type": self.claim_type,
            "entity_type": self.entity_type,
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass
class Snapshot:
    snapshot_hash_hex: str
    body: dict
    brief_id: Optional[str]
    decision_id: Optional[str]
    created_at: Optional[datetime]

    def to_dict(self) -> dict:
        return {
            "snapshot_hash": self.snapshot_hash_hex,
            "body": self.body,
            "brief_id": str(self.brief_id) if self.brief_id else None,
            "decision_id": str(self.decision_id) if self.decision_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ────────────────────────────────────────────────────────────────────
# Errors
# ────────────────────────────────────────────────────────────────────

class ClaimNotFound(Exception):
    pass


class EvidenceNotFound(Exception):
    pass


class SnapshotNotFound(Exception):
    pass


class AppendOnlyViolation(Exception):
    """Caller tried to UPDATE/DELETE evidence; route returns 409."""
    pass


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _bytes_to_hex(b) -> str:
    if b is None:
        return ""
    if isinstance(b, str):
        # Already hex
        return b
    if isinstance(b, (bytes, bytearray, memoryview)):
        return bytes(b).hex()
    return str(b)


def _row_to_evidence(row: dict) -> EvidenceRecord:
    method = row.get("extraction_method") or {}
    if isinstance(method, str):
        try:
            method = json.loads(method)
        except (TypeError, ValueError):
            method = {}

    # BE-1 — fall back to the registry so older rows without
    # source_name / source_tier still render as cards.
    source_id = row["source_id"]
    name = row.get("source_name")
    tier = row.get("source_tier")
    if name is None or tier is None:
        reg_name, reg_tier = lookup_source_metadata(source_id)
        name = name if name is not None else reg_name
        tier = tier if tier is not None else reg_tier

    snippet = row.get("snippet")
    if snippet is None and row.get("extracted_text"):
        snippet = make_snippet(row["extracted_text"])

    return EvidenceRecord(
        evidence_id=str(row["evidence_id"]),
        source_id=source_id,
        source_url=row.get("source_url"),
        source_content_hash_hex=_bytes_to_hex(row.get("source_content_hash")),
        archived_snapshot_ref=row.get("archived_snapshot_ref"),
        retrieved_at=row.get("retrieved_at"),
        extraction_method=method,
        extracted_text=row["extracted_text"],
        confidence=row.get("confidence"),
        retrieved_by_user_id=str(row["retrieved_by_user_id"]) if row.get("retrieved_by_user_id") else None,
        created_at=row.get("created_at"),
        source_name=name,
        source_tier=tier,
        published_at=row.get("published_at"),
        snippet=snippet,
        relation=row.get("relation"),
    )


def _row_to_claim(row: dict, evidence: Optional[list[EvidenceRecord]] = None) -> Claim:
    return Claim(
        claim_id=str(row["claim_id"]),
        claim_text=row["claim_text"],
        claim_text_hash_hex=_bytes_to_hex(row.get("claim_text_hash")),
        claim_type=row.get("claim_type") or "other",
        entity_type=row.get("entity_type"),
        entity_id=str(row["entity_id"]) if row.get("entity_id") else None,
        confidence=row.get("confidence"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        evidence=evidence or [],
    )


def _validate_claim_inputs(*, claim_text: str, claim_type: str, entity_type: Optional[str]) -> None:
    if not claim_text or not claim_text.strip():
        raise ValueError("claim_text required")
    if len(claim_text) > MAX_CLAIM_TEXT_LEN:
        raise ValueError(f"claim_text exceeds {MAX_CLAIM_TEXT_LEN} chars")
    if claim_type not in VALID_CLAIM_TYPES:
        raise ValueError(f"claim_type must be one of {sorted(VALID_CLAIM_TYPES)}")
    if entity_type is not None and entity_type not in VALID_ENTITY_TYPES:
        raise ValueError(f"entity_type must be one of {sorted(VALID_ENTITY_TYPES)} or null")


def _validate_evidence_inputs(*, source_id: str, extracted_text: str, retrieved_at: Any) -> None:
    if not source_id or not source_id.strip():
        raise ValueError("source_id required")
    if not extracted_text:
        raise ValueError("extracted_text required")
    if len(extracted_text) > MAX_EXTRACTED_TEXT_LEN:
        raise ValueError(f"extracted_text exceeds {MAX_EXTRACTED_TEXT_LEN} bytes")
    if retrieved_at is None:
        raise ValueError("retrieved_at required")


# ────────────────────────────────────────────────────────────────────
# Service
# ────────────────────────────────────────────────────────────────────

class EvidenceLedgerService:
    """Stateless service. All methods take db on each call; no instance binding."""

    # ── Claims ──

    @staticmethod
    def upsert_claim(
        db,
        *,
        claim_text: str,
        claim_type: str = "other",
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> Claim:
        """Create or return existing claim. Dedup key: (claim_text_hash,
        entity_type, entity_id) — or for entity-less claims, (claim_text_hash,
        claim_type)."""
        _validate_claim_inputs(claim_text=claim_text, claim_type=claim_type, entity_type=entity_type)
        if confidence is not None and not (0.0 <= confidence <= 1.0):
            raise ValueError("confidence must be in [0, 1]")

        text_hash = hash_claim_text(claim_text)

        # Check existing
        existing = db.fetch_one(
            """
            SELECT claim_id, claim_text, claim_text_hash, claim_type,
                   entity_type, entity_id, confidence, created_at, updated_at
              FROM claims
             WHERE claim_text_hash = %s
               AND COALESCE(entity_type, '') = COALESCE(%s, '')
               AND (
                    (entity_id IS NULL AND %s IS NULL)
                 OR (entity_id::text = %s)
               )
             LIMIT 1
            """,
            (text_hash, entity_type, entity_id, str(entity_id) if entity_id else None),
        )
        if existing:
            return _row_to_claim(existing)

        row = db.fetch_one(
            """
            INSERT INTO claims (
                claim_text, claim_text_hash, claim_type, entity_type,
                entity_id, confidence
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            RETURNING claim_id, claim_text, claim_text_hash, claim_type,
                      entity_type, entity_id, confidence, created_at, updated_at
            """,
            (claim_text, text_hash, claim_type, entity_type, entity_id, confidence),
        )
        if not row:
            # Lost the race — fetch the existing one
            existing = db.fetch_one(
                """
                SELECT claim_id, claim_text, claim_text_hash, claim_type,
                       entity_type, entity_id, confidence, created_at, updated_at
                  FROM claims
                 WHERE claim_text_hash = %s
                   AND COALESCE(entity_type, '') = COALESCE(%s, '')
                """,
                (text_hash, entity_type),
            )
            if existing:
                return _row_to_claim(existing)
            raise RuntimeError("upsert_claim: insert returned no row and no race winner found")
        return _row_to_claim(row)

    @staticmethod
    def get_claim(db, claim_id: str, *, include_evidence: bool = True) -> Optional[Claim]:
        row = db.fetch_one(
            """
            SELECT claim_id, claim_text, claim_text_hash, claim_type,
                   entity_type, entity_id, confidence, created_at, updated_at
              FROM claims WHERE claim_id::text = %s
            """,
            (str(claim_id),),
        )
        if not row:
            return None
        evidence: list[EvidenceRecord] = []
        if include_evidence:
            ev_rows = db.fetch_all(
                """
                SELECT e.evidence_id, e.source_id, e.source_url,
                       e.source_content_hash, e.archived_snapshot_ref,
                       e.retrieved_at, e.extraction_method, e.extracted_text,
                       e.confidence, e.retrieved_by_user_id, e.created_at,
                       l.relation
                  FROM claim_evidence_links l
                  JOIN evidence_records e ON e.evidence_id = l.evidence_id
                 WHERE l.claim_id::text = %s
                 ORDER BY e.confidence DESC NULLS LAST, e.retrieved_at DESC
                """,
                (str(claim_id),),
            ) or []
            evidence = [_row_to_evidence(r) for r in ev_rows]
        return _row_to_claim(row, evidence=evidence)

    @staticmethod
    def list_claims(
        db,
        *,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        claim_type: Optional[str] = None,
        text_query: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Claim]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be in [1, 500]")
        if claim_type is not None and claim_type not in VALID_CLAIM_TYPES:
            raise ValueError(f"claim_type must be one of {sorted(VALID_CLAIM_TYPES)}")
        if entity_type is not None and entity_type not in VALID_ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of {sorted(VALID_ENTITY_TYPES)}")

        where = ["1=1"]
        params: list[Any] = []
        if entity_type is not None:
            where.append("entity_type = %s")
            params.append(entity_type)
        if entity_id is not None:
            where.append("entity_id::text = %s")
            params.append(str(entity_id))
        if claim_type is not None:
            where.append("claim_type = %s")
            params.append(claim_type)
        if text_query:
            where.append("claim_text ILIKE %s")
            params.append(f"%{text_query}%")
        params.extend([limit, offset])

        rows = db.fetch_all(
            f"""
            SELECT claim_id, claim_text, claim_text_hash, claim_type,
                   entity_type, entity_id, confidence, created_at, updated_at
              FROM claims
             WHERE {' AND '.join(where)}
             ORDER BY created_at DESC
             LIMIT %s OFFSET %s
            """,
            tuple(params),
        ) or []
        return [_row_to_claim(r) for r in rows]

    # ── Evidence ──

    @staticmethod
    def append_evidence(
        db,
        claim_id: str,
        *,
        source_id: str,
        extracted_text: str,
        retrieved_at: Optional[datetime] = None,
        source_url: Optional[str] = None,
        extraction_method: Optional[dict] = None,
        confidence: Optional[float] = None,
        retrieved_by_user_id: Optional[str] = None,
        relation: str = "supports",
    ) -> EvidenceRecord:
        """Append an evidence record to a claim. Idempotent on
        (source_content_hash, source_id, retrieved_at::date)."""
        if relation not in VALID_RELATIONS:
            raise ValueError(f"relation must be one of {sorted(VALID_RELATIONS)}")
        if confidence is not None and not (0.0 <= confidence <= 1.0):
            raise ValueError("confidence must be in [0, 1]")
        if retrieved_at is None:
            retrieved_at = datetime.now(timezone.utc)
        _validate_evidence_inputs(source_id=source_id, extracted_text=extracted_text, retrieved_at=retrieved_at)

        # Verify claim exists
        claim = db.fetch_one("SELECT claim_id FROM claims WHERE claim_id::text = %s",
                             (str(claim_id),))
        if not claim:
            raise ClaimNotFound(claim_id)

        content_hash = hash_source_content(extracted_text)

        # Try to find existing evidence record (dedup by content + source + day)
        existing = db.fetch_one(
            """
            SELECT evidence_id, source_id, source_url, source_content_hash,
                   archived_snapshot_ref, retrieved_at, extraction_method,
                   extracted_text, confidence, retrieved_by_user_id, created_at,
                   source_name, source_tier, published_at, snippet
              FROM evidence_records
             WHERE source_content_hash = %s
               AND source_id = %s
               AND retrieved_at::date = %s::date
             LIMIT 1
            """,
            (content_hash, source_id, retrieved_at),
        )
        if existing:
            evidence = _row_to_evidence(existing)
        else:
            # BE-1 — derive card defaults from the registry + snippet helper
            reg_name, reg_tier = lookup_source_metadata(source_id)
            row = db.fetch_one(
                """
                INSERT INTO evidence_records (
                    source_id, source_url, source_content_hash,
                    retrieved_at, extraction_method, extracted_text,
                    confidence, retrieved_by_user_id,
                    source_name, source_tier, published_at, snippet
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s,
                          %s, %s, %s, %s)
                RETURNING evidence_id, source_id, source_url, source_content_hash,
                          archived_snapshot_ref, retrieved_at, extraction_method,
                          extracted_text, confidence, retrieved_by_user_id, created_at,
                          source_name, source_tier, published_at, snippet
                """,
                (
                    source_id, source_url, content_hash,
                    retrieved_at, json.dumps(extraction_method or {}),
                    extracted_text, confidence, retrieved_by_user_id,
                    reg_name, reg_tier, retrieved_at, make_snippet(extracted_text),
                ),
            )
            evidence = _row_to_evidence(row)

        # Link claim ↔ evidence; ON CONFLICT for idempotency
        db.execute(
            """
            INSERT INTO claim_evidence_links (claim_id, evidence_id, relation)
            VALUES (%s, %s, %s)
            ON CONFLICT (claim_id, evidence_id, relation) DO NOTHING
            """,
            (str(claim_id), evidence.evidence_id, relation),
        )
        evidence.relation = relation
        return evidence

    @staticmethod
    def get_evidence(db, evidence_id: str) -> Optional[EvidenceRecord]:
        row = db.fetch_one(
            """
            SELECT evidence_id, source_id, source_url, source_content_hash,
                   archived_snapshot_ref, retrieved_at, extraction_method,
                   extracted_text, confidence, retrieved_by_user_id, created_at
              FROM evidence_records
             WHERE evidence_id::text = %s
            """,
            (str(evidence_id),),
        )
        if not row:
            return None
        return _row_to_evidence(row)

    # ── Snapshots ──

    @staticmethod
    def snapshot_for_claims(
        db,
        *,
        claim_ids: Iterable[str],
        brief_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        snapshot_at: Optional[datetime] = None,
    ) -> Snapshot:
        """Freeze the current (claim → evidence_ids) mapping for the given
        set of claims into a content-addressed snapshot. Idempotent: re-
        snapshotting the same set returns the same hash and reuses the row.

        snapshot_at is normalized to ISO-8601 UTC for hash determinism. If
        not provided, NOW() is used."""
        # snapshot_at is metadata only; not part of the content hash.
        # Caller may pass it for record-keeping; if absent, DB stamps NOW().
        _ = snapshot_at
        claim_id_list = sorted(set(str(c) for c in claim_ids))
        if not claim_id_list:
            raise ValueError("snapshot requires at least one claim_id")

        # Pull current evidence_ids for each claim
        rows = db.fetch_all(
            """
            SELECT claim_id::text AS claim_id, evidence_id::text AS evidence_id
              FROM claim_evidence_links
             WHERE claim_id::text = ANY(%s)
            """,
            (claim_id_list,),
        ) or []

        per_claim: dict[str, list[str]] = {cid: [] for cid in claim_id_list}
        for r in rows:
            per_claim.setdefault(str(r["claim_id"]), []).append(str(r["evidence_id"]))

        claims_arr = [{"claim_id": cid, "evidence_ids": per_claim[cid]} for cid in claim_id_list]
        body = normalize_snapshot_body(
            claims=claims_arr,
            brief_id=brief_id,
            decision_id=decision_id,
        )
        s_hash = hash_snapshot_body(body)

        # Idempotent insert
        row = db.fetch_one(
            """
            INSERT INTO evidence_snapshots (snapshot_hash, body, brief_id, decision_id)
            VALUES (%s, %s::jsonb, %s, %s)
            ON CONFLICT (snapshot_hash) DO NOTHING
            RETURNING snapshot_hash, body, brief_id, decision_id, created_at
            """,
            (s_hash, json.dumps(body), brief_id, decision_id),
        )
        if not row:
            row = db.fetch_one(
                """
                SELECT snapshot_hash, body, brief_id, decision_id, created_at
                  FROM evidence_snapshots
                 WHERE snapshot_hash = %s
                """,
                (s_hash,),
            )
        return Snapshot(
            snapshot_hash_hex=_bytes_to_hex(row["snapshot_hash"]),
            body=row["body"] if isinstance(row["body"], dict) else json.loads(row["body"]),
            brief_id=str(row["brief_id"]) if row.get("brief_id") else None,
            decision_id=str(row["decision_id"]) if row.get("decision_id") else None,
            created_at=row.get("created_at"),
        )

    @staticmethod
    def get_snapshot(db, snapshot_hash_hex: str) -> Optional[Snapshot]:
        try:
            s_hash = bytes.fromhex(snapshot_hash_hex)
        except (ValueError, TypeError):
            raise ValueError("snapshot_hash must be hex-encoded")
        row = db.fetch_one(
            """
            SELECT snapshot_hash, body, brief_id, decision_id, created_at
              FROM evidence_snapshots
             WHERE snapshot_hash = %s
            """,
            (s_hash,),
        )
        if not row:
            return None
        return Snapshot(
            snapshot_hash_hex=_bytes_to_hex(row["snapshot_hash"]),
            body=row["body"] if isinstance(row["body"], dict) else json.loads(row["body"]),
            brief_id=str(row["brief_id"]) if row.get("brief_id") else None,
            decision_id=str(row["decision_id"]) if row.get("decision_id") else None,
            created_at=row.get("created_at"),
        )
