"""SPEC_034 — Decision Signing.

Immutable evidence_snapshot + HMAC-SHA256 signature on decision commit;
replay endpoint reconstructs the exact view at signing time.

Crypto: HMAC-SHA256 with server-side secret. Verifies "the server attests
to this state at this time." Asymmetric per-user signing is a follow-up.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


SIGNING_ALGO = "hmac-sha256-v1"
SECRET_ENV = "MZ_DECISION_SIGNING_SECRET"
DEV_FALLBACK_SECRET = "dev-only-change-me"  # logged with WARN if used


# ────────────────────────────────────────────────────────────────────
# Errors
# ────────────────────────────────────────────────────────────────────

class DecisionNotFound(Exception):
    pass


class DecisionAlreadySigned(Exception):
    """Caller tried to re-sign without `force=True`."""
    pass


class DecisionNotSigned(Exception):
    """verify/replay called on an unsigned decision."""
    pass


class NotDecisionOwner(Exception):
    """Signing user is not the decision owner."""
    pass


class SignatureInvalid(Exception):
    pass


# ────────────────────────────────────────────────────────────────────
# Crypto helpers (deterministic, public)
# ────────────────────────────────────────────────────────────────────

def get_server_secret() -> bytes:
    """Read signing secret from env. Falls back to dev-only constant
    with WARN log (so unit tests run without env setup but production
    misconfig is loud)."""
    secret = os.getenv(SECRET_ENV)
    if not secret:
        logger.warning(
            "%s not set; using dev-only fallback. SET THIS IN PROD.",
            SECRET_ENV,
        )
        secret = DEV_FALLBACK_SECRET
    return secret.encode("utf-8")


def canonical_json(obj: Any) -> str:
    """Deterministic JSON for content-addressing + signing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_snapshot_hash(*, decision_id: str, claim_ids: Iterable[str],
                          brief_id: Optional[str] = None) -> bytes:
    body = {
        "decision_id": str(decision_id),
        "claim_ids": sorted(str(c) for c in claim_ids),
    }
    if brief_id is not None:
        body["brief_id"] = str(brief_id)
    return hashlib.sha256(canonical_json(body).encode("utf-8")).digest()


def _normalize_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def build_signing_payload(decision: dict, *, snapshot_hash_hex: str,
                          signed_at_iso: str, signing_user_id: str) -> dict:
    """The canonical immutable-fields payload that gets HMAC-signed."""
    deadline = decision.get("deadline")
    if hasattr(deadline, "isoformat"):
        deadline = deadline.isoformat()
    return {
        "decision_id": str(decision["id"]),
        "title": decision.get("title"),
        "rationale": decision.get("rationale"),
        "owner_user_id": str(decision["owner_user_id"]) if decision.get("owner_user_id") else None,
        "target_metric": decision.get("target_metric"),
        "target_value": decision.get("target_value"),
        "deadline": deadline,
        "confidence_at_commit": (
            float(decision["confidence_at_commit"])
            if decision.get("confidence_at_commit") is not None else None
        ),
        "evidence_snapshot_hash": snapshot_hash_hex,
        "signing_algo": SIGNING_ALGO,
        "signed_at": signed_at_iso,
        "signing_user_id": str(signing_user_id),
    }


def compute_signature(payload: dict, *, secret: Optional[bytes] = None) -> bytes:
    """HMAC-SHA256 over canonical_json(payload). Returns 32-byte digest."""
    secret = secret or get_server_secret()
    canonical = canonical_json(payload).encode("utf-8")
    return hmac.new(secret, canonical, hashlib.sha256).digest()


def verify_signature(payload: dict, signature: bytes, *,
                     secret: Optional[bytes] = None) -> bool:
    """Constant-time signature comparison."""
    expected = compute_signature(payload, secret=secret)
    return hmac.compare_digest(expected, bytes(signature))


# ────────────────────────────────────────────────────────────────────
# Bytes-to-hex helper
# ────────────────────────────────────────────────────────────────────

def _hex(b) -> str:
    if b is None:
        return ""
    if isinstance(b, str):
        return b
    if isinstance(b, (bytes, bytearray, memoryview)):
        return bytes(b).hex()
    return str(b)


# ────────────────────────────────────────────────────────────────────
# Service
# ────────────────────────────────────────────────────────────────────

@dataclass
class SignedDecision:
    decision_id: str
    snapshot_hash_hex: str
    signature_hex: str
    signing_algo: str
    signed_at: datetime
    signing_user_id: str
    metadata: dict

    def to_dict(self) -> dict:
        return {
            "decision_id": str(self.decision_id),
            "snapshot_hash": self.snapshot_hash_hex,
            "signature": self.signature_hex,
            "signing_algo": self.signing_algo,
            "signed_at": self.signed_at.isoformat() if self.signed_at else None,
            "signing_user_id": str(self.signing_user_id),
            "metadata": self.metadata or {},
        }


@dataclass
class ReplayBundle:
    decision: dict
    evidence_snapshot: dict
    signature: dict
    claims: list = field(default_factory=list)
    evidence_records: list = field(default_factory=list)
    llm_calls: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "evidence_snapshot": self.evidence_snapshot,
            "signature": self.signature,
            "claims": self.claims,
            "evidence_records": self.evidence_records,
            "llm_calls": self.llm_calls,
        }


class DecisionSigningService:

    @staticmethod
    def sign(
        db,
        *,
        decision_id: str,
        signing_user_id: str,
        claim_ids: list[str],
        brief_id: Optional[str] = None,
        force: bool = False,
    ) -> SignedDecision:
        """Sign a decision. Validates ownership + (re-)sign rules; freezes
        snapshot; HMAC-signs canonical payload; persists to decisions row."""
        if not claim_ids:
            raise ValueError("claim_ids required (≥1)")
        # Stringify + dedup; keeps SQL params clean
        claim_ids_clean = sorted({str(c) for c in claim_ids if c})
        if not claim_ids_clean:
            raise ValueError("claim_ids required (≥1 non-empty)")

        decision = db.fetch_one(
            """
            SELECT id, title, rationale, owner_user_id, target_metric,
                   target_value, deadline, confidence_at_commit,
                   evidence_snapshot_hash, signature, signing_algo,
                   signed_at, signing_user_id, signing_metadata_jsonb
              FROM decisions WHERE id::text = %s
            """,
            (str(decision_id),),
        )
        if not decision:
            raise DecisionNotFound(decision_id)

        # Ownership check
        if str(decision.get("owner_user_id") or "") != str(signing_user_id):
            raise NotDecisionOwner(
                f"signing user {signing_user_id!r} is not decision owner "
                f"{decision.get('owner_user_id')!r}"
            )

        # Re-sign guard
        if decision.get("signature") is not None and not force:
            raise DecisionAlreadySigned(
                f"decision {decision_id} already signed at "
                f"{decision.get('signed_at')}; pass force=True to override"
            )

        # Compute snapshot + signature
        snapshot_hash = compute_snapshot_hash(
            decision_id=decision_id,
            claim_ids=claim_ids_clean,
            brief_id=brief_id,
        )
        snapshot_hex = snapshot_hash.hex()
        signed_at = datetime.now(timezone.utc)
        signed_at_iso = signed_at.isoformat()

        payload = build_signing_payload(
            decision,
            snapshot_hash_hex=snapshot_hex,
            signed_at_iso=signed_at_iso,
            signing_user_id=str(signing_user_id),
        )
        sig = compute_signature(payload)

        metadata = {
            "claim_ids": claim_ids_clean,
            "brief_id": str(brief_id) if brief_id else None,
            "secret_version": "v1",
        }

        # Persist
        db.execute(
            """
            UPDATE decisions
               SET evidence_snapshot_hash = %s,
                   signature = %s,
                   signing_algo = %s,
                   signed_at = %s,
                   signing_user_id = %s,
                   signing_metadata_jsonb = %s::jsonb
             WHERE id::text = %s
            """,
            (
                snapshot_hash, sig, SIGNING_ALGO,
                signed_at, str(signing_user_id),
                json.dumps(metadata), str(decision_id),
            ),
        )

        # Best-effort: also write to evidence_snapshots if SPEC-024 service is present
        try:
            from services.evidence_ledger import EvidenceLedgerService
            EvidenceLedgerService.snapshot_for_claims(
                db,
                claim_ids=claim_ids_clean,
                brief_id=brief_id,
                decision_id=str(decision_id),
            )
        except Exception as exc:
            logger.debug("evidence_ledger snapshot side-effect skipped: %s", exc)

        return SignedDecision(
            decision_id=str(decision_id),
            snapshot_hash_hex=snapshot_hex,
            signature_hex=sig.hex(),
            signing_algo=SIGNING_ALGO,
            signed_at=signed_at,
            signing_user_id=str(signing_user_id),
            metadata=metadata,
        )

    @staticmethod
    def verify(db, decision_id: str) -> dict:
        """Re-compute signature from stored fields; compare to stored
        signature. Returns `{valid: bool, decision_id, ...details}`."""
        decision = db.fetch_one(
            """
            SELECT id, title, rationale, owner_user_id, target_metric,
                   target_value, deadline, confidence_at_commit,
                   evidence_snapshot_hash, signature, signing_algo,
                   signed_at, signing_user_id, signing_metadata_jsonb
              FROM decisions WHERE id::text = %s
            """,
            (str(decision_id),),
        )
        if not decision:
            raise DecisionNotFound(decision_id)
        if decision.get("signature") is None:
            raise DecisionNotSigned(decision_id)

        snapshot_hash_hex = _hex(decision.get("evidence_snapshot_hash"))
        signed_at_iso = _normalize_iso(decision.get("signed_at"))
        signing_user_id = str(decision.get("signing_user_id") or "")

        payload = build_signing_payload(
            decision,
            snapshot_hash_hex=snapshot_hash_hex,
            signed_at_iso=signed_at_iso,
            signing_user_id=signing_user_id,
        )
        stored_sig = bytes(decision["signature"])
        valid = verify_signature(payload, stored_sig)
        return {
            "decision_id": str(decision_id),
            "valid": valid,
            "signing_algo": decision.get("signing_algo"),
            "signed_at": signed_at_iso,
            "signing_user_id": signing_user_id,
            "snapshot_hash": snapshot_hash_hex,
        }

    @staticmethod
    def replay(db, decision_id: str) -> ReplayBundle:
        """Reconstruct the immutable bundle. Best-effort hydration of
        claims/evidence_records/llm_calls (skipped if those tables aren't
        present yet)."""
        decision = db.fetch_one(
            """
            SELECT id, title, rationale, owner_user_id, owner_display_name,
                   target_metric, target_value, deadline, confidence_at_commit,
                   status, actual_outcome, calibration_score,
                   evidence_snapshot_hash, signature, signing_algo,
                   signed_at, signing_user_id, signing_metadata_jsonb,
                   war_room_id, source_signal_id, created_at, updated_at
              FROM decisions WHERE id::text = %s
            """,
            (str(decision_id),),
        )
        if not decision:
            raise DecisionNotFound(decision_id)
        if decision.get("signature") is None:
            raise DecisionNotSigned(decision_id)

        metadata = decision.get("signing_metadata_jsonb") or {}
        if isinstance(metadata, str):
            try: metadata = json.loads(metadata)
            except (TypeError, ValueError): metadata = {}
        claim_ids = metadata.get("claim_ids") or []
        brief_id = metadata.get("brief_id")

        bundle_decision = {
            "decision_id": str(decision["id"]),
            "title": decision.get("title"),
            "rationale": decision.get("rationale"),
            "owner_user_id": str(decision["owner_user_id"]) if decision.get("owner_user_id") else None,
            "owner_display_name": decision.get("owner_display_name"),
            "target_metric": decision.get("target_metric"),
            "target_value": decision.get("target_value"),
            "deadline": decision["deadline"].isoformat() if hasattr(decision.get("deadline"), "isoformat") else decision.get("deadline"),
            "confidence_at_commit": float(decision["confidence_at_commit"]) if decision.get("confidence_at_commit") is not None else None,
            "status": decision.get("status"),
            "actual_outcome": decision.get("actual_outcome"),
            "calibration_score": float(decision["calibration_score"]) if decision.get("calibration_score") is not None else None,
            "war_room_id": str(decision["war_room_id"]) if decision.get("war_room_id") else None,
            "source_signal_id": str(decision["source_signal_id"]) if decision.get("source_signal_id") else None,
            "created_at": decision["created_at"].isoformat() if hasattr(decision.get("created_at"), "isoformat") else None,
        }

        snapshot = {
            "hash": _hex(decision.get("evidence_snapshot_hash")),
            "claim_ids": claim_ids,
            "brief_id": brief_id,
        }
        signature = {
            "value_hex": _hex(decision.get("signature")),
            "algo": decision.get("signing_algo"),
            "signed_at": _normalize_iso(decision.get("signed_at")),
            "signing_user_id": str(decision["signing_user_id"]) if decision.get("signing_user_id") else None,
        }

        # Best-effort hydration when SPEC-024 ledger present
        claims_out: list[dict] = []
        evidence_out: list[dict] = []
        if claim_ids:
            try:
                rows = db.fetch_all(
                    """
                    SELECT claim_id::text AS claim_id, claim_text, claim_type,
                           entity_type, entity_id, confidence
                      FROM claims WHERE claim_id::text = ANY(%s)
                    """,
                    (list(claim_ids),),
                )
                claims_out = [dict(r) for r in (rows or [])]
            except Exception as exc:
                logger.debug("claims hydration skipped: %s", exc)

            try:
                rows = db.fetch_all(
                    """
                    SELECT er.evidence_id::text AS evidence_id,
                           er.source_id, er.source_url,
                           er.retrieved_at, er.extraction_method,
                           er.extracted_text, er.confidence,
                           cel.claim_id::text AS claim_id, cel.relation
                      FROM claim_evidence_links cel
                      JOIN evidence_records er ON er.evidence_id = cel.evidence_id
                     WHERE cel.claim_id::text = ANY(%s)
                    """,
                    (list(claim_ids),),
                )
                for r in (rows or []):
                    d = dict(r)
                    if d.get("retrieved_at") and hasattr(d["retrieved_at"], "isoformat"):
                        d["retrieved_at"] = d["retrieved_at"].isoformat()
                    evidence_out.append(d)
            except Exception as exc:
                logger.debug("evidence hydration skipped: %s", exc)

        # llm_calls within the brief lifecycle (best-effort)
        llm_calls_out: list[dict] = []
        if brief_id:
            try:
                rows = db.fetch_all(
                    """
                    SELECT lcl.created_at, lcl.caller, lcl.model, lcl.prompt_id,
                           lcl.prompt_version, lcl.latency_ms,
                           lcl.prompt_tokens, lcl.completion_tokens,
                           lcl.cost_estimate_usd, lcl.succeeded
                      FROM llm_call_log lcl
                     WHERE lcl.created_at <= %s
                       AND lcl.user_id::text = %s
                     ORDER BY lcl.created_at DESC
                     LIMIT 100
                    """,
                    (decision.get("signed_at"), str(decision.get("owner_user_id") or "")),
                )
                for r in (rows or []):
                    d = dict(r)
                    if d.get("created_at") and hasattr(d["created_at"], "isoformat"):
                        d["created_at"] = d["created_at"].isoformat()
                    if d.get("prompt_id"):
                        d["prompt_id"] = str(d["prompt_id"])
                    if d.get("cost_estimate_usd") is not None:
                        d["cost_estimate_usd"] = float(d["cost_estimate_usd"])
                    llm_calls_out.append(d)
            except Exception as exc:
                logger.debug("llm_calls hydration skipped: %s", exc)

        return ReplayBundle(
            decision=bundle_decision,
            evidence_snapshot=snapshot,
            signature=signature,
            claims=claims_out,
            evidence_records=evidence_out,
            llm_calls=llm_calls_out,
        )
