"""DI-5 — SME playbook authoring service (CRUD + validation + versioning).

Makes playbooks editable at RUNTIME via the API — no code deploy. A DB-stored
playbook (migration 080 `playbooks` table) overrides/extends the YAML seed; the
PlaybookRegistry serves the edited version to the planner on the next query.

Governance (non-negotiable for a regulated domain):
  * Validated on save — every dimension route must resolve to a real ledger
    predicate / whitelisted link / whitelisted source (services.domain_intelligence
    .validation), and a trigger may not ambiguously duplicate another playbook.
  * Versioned + audited — every create / update / rollback appends an immutable
    snapshot + diff + author + timestamp to `playbook_versions` (migration 082).
  * Reversible — fetch history + rollback to any prior version (the rollback is
    itself a new forward version, so the audit trail is never rewritten).

Reuse, not duplication: the Playbook/Dimension/Route model + PlaybookRegistry
DB-override path (DI-1) already exist — this service writes the rows that path
reads. Mirrors the FramingTriggerService CRUD/validation shape.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from services.domain_intelligence.playbook import Playbook, PlaybookRegistry
from services.domain_intelligence.validation import (
    PlaybookValidationError,
    validate_playbook,
)

logger = logging.getLogger(__name__)


class PlaybookNotFound(Exception):
    """Raised when a playbook_id has no DB-backed row."""


class PlaybookConflict(Exception):
    """Raised when creating a playbook whose id already exists in the DB."""


# ── diff (audit payload) ────────────────────────────────────────────────


def diff_playbooks(before: Optional[dict], after: dict) -> dict:
    """Field-level diff between two playbook dicts → {field: {from, to}}.

    Used as the audit payload on each version. `before` is None for a create.
    Only the four authorable fields are diffed (id is the key, never changes)."""
    fields = ("pack", "trigger", "dimensions", "synthesis")
    out: dict[str, dict] = {}
    b = before or {}
    for f in fields:
        bv = b.get(f)
        av = after.get(f)
        if bv != av:
            out[f] = {"from": bv, "to": av}
    return out


# ── row helpers ─────────────────────────────────────────────────────────


def _row_to_playbook(row: dict) -> Playbook:
    """A `playbooks` row → a Playbook (JSONB cols may arrive as str under some
    drivers, so coerce defensively)."""
    def _j(v: Any, default: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (TypeError, ValueError):
                return default
        return v if v is not None else default

    return Playbook.from_dict({
        "id": row["id"],
        "pack": row.get("pack") or "pharma",
        "trigger": _j(row.get("trigger"), {}),
        "dimensions": _j(row.get("dimensions"), []),
        "synthesis": _j(row.get("synthesis"), {}),
    })


def _row_to_meta(row: dict) -> dict:
    """The DB-only metadata (version/author/active/timestamps) for API responses."""
    return {
        "version": row.get("version"),
        "author": row.get("author"),
        "active": bool(row.get("active", True)),
        "tenant_scope": row.get("tenant_scope"),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


# ── service ──────────────────────────────────────────────────────────────


class PlaybookAuthoringService:
    """CRUD + validation + versioning over the `playbooks` / `playbook_versions`
    tables. Stateless; pass the db handle to each call (mirrors FramingTriggerService)."""

    # ── reads ──

    @staticmethod
    def get_row(db: Any, playbook_id: str) -> Optional[dict]:
        """The raw DB row (current version) for a DB-backed playbook, or None."""
        return db.fetch_one(
            "SELECT id, pack, trigger, dimensions, synthesis, active, version, "
            "author, tenant_scope, created_at, updated_at "
            "FROM playbooks WHERE id = %s",
            [playbook_id],
        )

    @staticmethod
    def get(db: Any, playbook_id: str) -> Optional[dict]:
        """A DB-backed playbook as {playbook, meta}, or None if no DB row."""
        row = PlaybookAuthoringService.get_row(db, playbook_id)
        if not row:
            return None
        return {"playbook": _row_to_playbook(row).to_dict(), "meta": _row_to_meta(row)}

    @staticmethod
    def list(db: Any, *, include_seed: bool = True) -> list[dict]:
        """List playbooks. DB-backed rows carry meta + source='db'; YAML seeds
        not overridden in the DB are appended with source='seed' (read-only)."""
        rows = db.fetch_all(
            "SELECT id, pack, trigger, dimensions, synthesis, active, version, "
            "author, tenant_scope, created_at, updated_at "
            "FROM playbooks ORDER BY id"
        ) or []
        out: list[dict] = []
        db_ids: set[str] = set()
        for row in rows:
            db_ids.add(row["id"])
            out.append({
                "playbook": _row_to_playbook(row).to_dict(),
                "meta": _row_to_meta(row),
                "source": "db",
            })
        if include_seed:
            seed = PlaybookRegistry(load_seed=True)  # seed-only, no DB
            for pb in seed.all():
                if pb.id in db_ids:
                    continue
                out.append({
                    "playbook": pb.to_dict(),
                    "meta": {"version": None, "author": None, "active": True},
                    "source": "seed",
                })
        return out

    @staticmethod
    def list_versions(db: Any, playbook_id: str) -> list[dict]:
        """Full version history (newest first) for a playbook."""
        rows = db.fetch_all(
            "SELECT version, action, snapshot, diff, author, note, "
            "rolled_back_from, created_at FROM playbook_versions "
            "WHERE playbook_id = %s ORDER BY version DESC",
            [playbook_id],
        ) or []
        out = []
        for r in rows:
            out.append({
                "version": r.get("version"),
                "action": r.get("action"),
                "snapshot": r.get("snapshot") if not isinstance(r.get("snapshot"), str)
                else json.loads(r["snapshot"]),
                "diff": r.get("diff") if not isinstance(r.get("diff"), str)
                else json.loads(r["diff"]),
                "author": r.get("author"),
                "note": r.get("note"),
                "rolled_back_from": r.get("rolled_back_from"),
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            })
        return out

    # ── version-history writer (append-only audit) ──

    @staticmethod
    def _record_version(
        db: Any,
        *,
        playbook_id: str,
        version: int,
        action: str,
        snapshot: dict,
        diff: dict,
        author: Optional[str],
        note: Optional[str] = None,
        rolled_back_from: Optional[int] = None,
    ) -> None:
        db.execute(
            "INSERT INTO playbook_versions "
            "(playbook_id, version, action, snapshot, diff, author, note, rolled_back_from) "
            "VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)",
            [
                playbook_id, version, action,
                json.dumps(snapshot), json.dumps(diff),
                author, note, rolled_back_from,
            ],
        )

    # ── writes ──

    @staticmethod
    def _existing_for_overlap(db: Any, exclude_id: str) -> list[Playbook]:
        """All selectable playbooks (seed + DB) except the one being saved —
        the corpus the trigger-overlap rule checks against."""
        reg = PlaybookRegistry(db=db, load_seed=True)
        return [pb for pb in reg.all() if pb.id != exclude_id]

    @staticmethod
    def create(db: Any, payload: dict, *, author: Optional[str] = None) -> dict:
        """Create a new DB-backed playbook (version 1). Validates first; raises
        PlaybookConflict if the id already has a DB row, PlaybookValidationError
        on a bad route / overlapping trigger."""
        pb = Playbook.from_dict(payload)
        if not (pb.id or "").strip():
            raise PlaybookValidationError(["playbook id is required"])
        if PlaybookAuthoringService.get_row(db, pb.id):
            raise PlaybookConflict(f"playbook already exists: {pb.id}")

        validate_playbook(pb, existing=PlaybookAuthoringService._existing_for_overlap(db, pb.id))

        body = pb.to_dict()
        row = db.fetch_one(
            "INSERT INTO playbooks (id, pack, trigger, dimensions, synthesis, "
            "active, version, author) "
            "VALUES (%s, %s, %s::jsonb, %s::jsonb, %s::jsonb, true, 1, %s) "
            "RETURNING id, pack, trigger, dimensions, synthesis, active, version, "
            "author, tenant_scope, created_at, updated_at",
            [
                pb.id, pb.pack, json.dumps(body["trigger"]),
                json.dumps(body["dimensions"]), json.dumps(body["synthesis"]), author,
            ],
        )
        if not row:
            raise RuntimeError("create: insert returned no row")
        PlaybookAuthoringService._record_version(
            db, playbook_id=pb.id, version=1, action="create",
            snapshot=body, diff=diff_playbooks(None, body), author=author,
        )
        return {"playbook": _row_to_playbook(row).to_dict(), "meta": _row_to_meta(row)}

    @staticmethod
    def update(
        db: Any,
        playbook_id: str,
        payload: dict,
        *,
        author: Optional[str] = None,
        note: Optional[str] = None,
    ) -> dict:
        """Edit a DB-backed playbook → a NEW version (validated + audited).

        `payload` is a partial: only the keys present (pack/trigger/dimensions/
        synthesis) are changed; the rest carry over from the current version.
        Raises PlaybookNotFound / PlaybookValidationError."""
        current = PlaybookAuthoringService.get_row(db, playbook_id)
        if not current:
            raise PlaybookNotFound(f"playbook not found: {playbook_id}")
        before = _row_to_playbook(current).to_dict()

        merged = dict(before)
        for k in ("pack", "trigger", "dimensions", "synthesis"):
            if k in payload and payload[k] is not None:
                merged[k] = payload[k]
        merged["id"] = playbook_id  # id is the key, never editable

        pb = Playbook.from_dict(merged)
        validate_playbook(
            pb, existing=PlaybookAuthoringService._existing_for_overlap(db, playbook_id)
        )

        new_version = int(current.get("version") or 1) + 1
        body = pb.to_dict()
        row = db.fetch_one(
            "UPDATE playbooks SET pack=%s, trigger=%s::jsonb, dimensions=%s::jsonb, "
            "synthesis=%s::jsonb, version=%s, author=%s, updated_at=NOW() "
            "WHERE id=%s "
            "RETURNING id, pack, trigger, dimensions, synthesis, active, version, "
            "author, tenant_scope, created_at, updated_at",
            [
                pb.pack, json.dumps(body["trigger"]), json.dumps(body["dimensions"]),
                json.dumps(body["synthesis"]), new_version, author, playbook_id,
            ],
        )
        PlaybookAuthoringService._record_version(
            db, playbook_id=playbook_id, version=new_version, action="update",
            snapshot=body, diff=diff_playbooks(before, body), author=author, note=note,
        )
        return {"playbook": _row_to_playbook(row).to_dict(), "meta": _row_to_meta(row)}

    @staticmethod
    def rollback(
        db: Any,
        playbook_id: str,
        target_version: int,
        *,
        author: Optional[str] = None,
        note: Optional[str] = None,
    ) -> dict:
        """Restore a prior version's content as a NEW forward version. The audit
        trail is never rewritten; the rollback row records rolled_back_from."""
        current = PlaybookAuthoringService.get_row(db, playbook_id)
        if not current:
            raise PlaybookNotFound(f"playbook not found: {playbook_id}")
        target = db.fetch_one(
            "SELECT snapshot FROM playbook_versions WHERE playbook_id=%s AND version=%s",
            [playbook_id, target_version],
        )
        if not target:
            raise PlaybookNotFound(
                f"version {target_version} not found for playbook {playbook_id}"
            )
        snap = target["snapshot"]
        if isinstance(snap, str):
            snap = json.loads(snap)

        before = _row_to_playbook(current).to_dict()
        pb = Playbook.from_dict({**snap, "id": playbook_id})
        # Re-validate on rollback too — vocabularies may have changed since.
        validate_playbook(
            pb, existing=PlaybookAuthoringService._existing_for_overlap(db, playbook_id)
        )

        new_version = int(current.get("version") or 1) + 1
        body = pb.to_dict()
        row = db.fetch_one(
            "UPDATE playbooks SET pack=%s, trigger=%s::jsonb, dimensions=%s::jsonb, "
            "synthesis=%s::jsonb, version=%s, author=%s, updated_at=NOW() "
            "WHERE id=%s "
            "RETURNING id, pack, trigger, dimensions, synthesis, active, version, "
            "author, tenant_scope, created_at, updated_at",
            [
                pb.pack, json.dumps(body["trigger"]), json.dumps(body["dimensions"]),
                json.dumps(body["synthesis"]), new_version, author, playbook_id,
            ],
        )
        PlaybookAuthoringService._record_version(
            db, playbook_id=playbook_id, version=new_version, action="rollback",
            snapshot=body, diff=diff_playbooks(before, body), author=author,
            note=note or f"rollback to v{target_version}", rolled_back_from=target_version,
        )
        return {"playbook": _row_to_playbook(row).to_dict(), "meta": _row_to_meta(row)}

    @staticmethod
    def delete(db: Any, playbook_id: str, *, author: Optional[str] = None) -> None:
        """Delete the DB-backed playbook (reverting the planner to the YAML seed
        if one exists for this id). Records a final 'delete' audit version; the
        version history is preserved (append-only)."""
        current = PlaybookAuthoringService.get_row(db, playbook_id)
        if not current:
            raise PlaybookNotFound(f"playbook not found: {playbook_id}")
        before = _row_to_playbook(current).to_dict()
        new_version = int(current.get("version") or 1) + 1
        PlaybookAuthoringService._record_version(
            db, playbook_id=playbook_id, version=new_version, action="delete",
            snapshot=before, diff=diff_playbooks(before, {}), author=author,
        )
        db.execute("DELETE FROM playbooks WHERE id = %s", [playbook_id])
