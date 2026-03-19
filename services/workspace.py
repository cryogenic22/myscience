"""Workspace persistence for saved conversations and research jobs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class ChatWorkspaceService:
    """Persistence adapter over PostgreSQL for workspace artifacts."""

    def __init__(self, db):
        self.db = db

    def save_session(
        self,
        *,
        scope_key: str,
        title: str,
        transcript: list[dict],
        session_id: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> dict:
        sid = session_id or str(uuid4())
        summary_value = summary or self._infer_summary(transcript)
        now = datetime.now(timezone.utc).isoformat()
        transcript_json = json.dumps(transcript)

        existing = self.db.fetch_one(
            "SELECT id::text AS id FROM chat_sessions WHERE id::text = %s AND scope_key = %s LIMIT 1",
            [sid, scope_key],
        )
        if existing:
            self.db.execute(
                """
                UPDATE chat_sessions
                SET title = %s,
                    transcript = %s::jsonb,
                    summary = %s,
                    updated_at = NOW()
                WHERE id::text = %s AND scope_key = %s
                """,
                [title, transcript_json, summary_value, sid, scope_key],
            )
        else:
            self.db.execute(
                """
                INSERT INTO chat_sessions (id, scope_key, title, transcript, summary)
                VALUES (%s::uuid, %s, %s, %s::jsonb, %s)
                """,
                [sid, scope_key, title, transcript_json, summary_value],
            )

        row = self.db.fetch_one(
            """
            SELECT
                id::text AS id,
                scope_key,
                title,
                summary,
                created_at,
                updated_at
            FROM chat_sessions
            WHERE id::text = %s AND scope_key = %s
            """,
            [sid, scope_key],
        )
        if not row:
            return {
                "id": sid,
                "scope_key": scope_key,
                "title": title,
                "summary": summary_value,
                "created_at": now,
                "updated_at": now,
            }
        return self._serialize_session_row(row)

    def list_sessions(self, *, scope_key: str, limit: int = 20, offset: int = 0) -> list[dict]:
        try:
            rows = self.db.fetch_all(
                """
                SELECT
                    id::text AS id,
                    scope_key,
                    title,
                    summary,
                    created_at,
                    updated_at
                FROM chat_sessions
                WHERE scope_key = %s
                ORDER BY updated_at DESC
                LIMIT %s
                OFFSET %s
                """,
                [scope_key, limit, offset],
            )
            return [self._serialize_session_row(row) for row in rows]
        except Exception as exc:
            logger.warning("list_sessions unavailable: %s", exc)
            return []

    def get_session(self, *, session_id: str, scope_key: str) -> Optional[dict]:
        row = self.db.fetch_one(
            """
            SELECT
                id::text AS id,
                scope_key,
                title,
                summary,
                transcript,
                created_at,
                updated_at
            FROM chat_sessions
            WHERE id::text = %s AND scope_key = %s
            LIMIT 1
            """,
            [session_id, scope_key],
        )
        if not row:
            return None
        payload = self._serialize_session_row(row)
        payload["transcript"] = row.get("transcript") or []
        return payload

    def delete_session(self, *, session_id: str, scope_key: str) -> bool:
        before = self.db.fetch_one(
            "SELECT id::text AS id FROM chat_sessions WHERE id::text = %s AND scope_key = %s LIMIT 1",
            [session_id, scope_key],
        )
        if not before:
            return False
        self.db.execute(
            "DELETE FROM chat_sessions WHERE id::text = %s AND scope_key = %s",
            [session_id, scope_key],
        )
        return True

    def create_research_job(self, *, scope_key: str, question: str, options: dict) -> dict:
        job_id = str(uuid4())
        options_json = json.dumps(options or {})
        self.db.execute(
            """
            INSERT INTO deep_research_jobs (id, scope_key, question, options, status)
            VALUES (%s::uuid, %s, %s, %s::jsonb, 'queued')
            """,
            [job_id, scope_key, question, options_json],
        )
        job = self.get_research_job(job_id=job_id, scope_key=scope_key)
        if not job:
            return {
                "id": job_id,
                "scope_key": scope_key,
                "question": question,
                "options": options,
                "status": "queued",
            }
        return job

    def list_research_jobs(self, *, scope_key: str, limit: int = 20, offset: int = 0) -> list[dict]:
        rows = self.db.fetch_all(
            """
            SELECT
                id::text AS id,
                scope_key,
                question,
                options,
                status,
                error_message,
                created_at,
                updated_at,
                completed_at
            FROM deep_research_jobs
            WHERE scope_key = %s
            ORDER BY created_at DESC
            LIMIT %s
            OFFSET %s
            """,
            [scope_key, limit, offset],
        )
        return [self._serialize_job_row(row, include_result=False) for row in rows]

    def get_research_job(self, *, job_id: str, scope_key: str) -> Optional[dict]:
        row = self.db.fetch_one(
            """
            SELECT
                id::text AS id,
                scope_key,
                question,
                options,
                status,
                result_payload,
                error_message,
                created_at,
                updated_at,
                completed_at
            FROM deep_research_jobs
            WHERE id::text = %s AND scope_key = %s
            LIMIT 1
            """,
            [job_id, scope_key],
        )
        if not row:
            return None
        return self._serialize_job_row(row, include_result=True)

    def mark_research_job_running(self, *, job_id: str) -> None:
        self.db.execute(
            """
            UPDATE deep_research_jobs
            SET status = 'running',
                updated_at = NOW(),
                error_message = NULL
            WHERE id::text = %s
            """,
            [job_id],
        )

    def complete_research_job(self, *, job_id: str, payload: dict) -> None:
        payload_json = json.dumps(payload or {})
        self.db.execute(
            """
            UPDATE deep_research_jobs
            SET status = 'completed',
                result_payload = %s::jsonb,
                updated_at = NOW(),
                completed_at = NOW(),
                error_message = NULL
            WHERE id::text = %s
            """,
            [payload_json, job_id],
        )

    def fail_research_job(self, *, job_id: str, error_message: str) -> None:
        self.db.execute(
            """
            UPDATE deep_research_jobs
            SET status = 'failed',
                updated_at = NOW(),
                completed_at = NOW(),
                error_message = %s
            WHERE id::text = %s
            """,
            [error_message[:2000], job_id],
        )

    def _infer_summary(self, transcript: list[dict]) -> str:
        for item in transcript:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if role == "assistant" and content:
                return content[:280]
        for item in transcript:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if content:
                return content[:280]
        return ""

    @staticmethod
    def _serialize_session_row(row: dict) -> dict:
        return {
            "id": str(row.get("id")),
            "scope_key": str(row.get("scope_key") or "default"),
            "title": str(row.get("title") or ""),
            "summary": str(row.get("summary") or ""),
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at")),
        }

    @staticmethod
    def _serialize_job_row(row: dict, *, include_result: bool) -> dict:
        payload = {
            "id": str(row.get("id")),
            "scope_key": str(row.get("scope_key") or "default"),
            "question": str(row.get("question") or ""),
            "options": row.get("options") or {},
            "status": str(row.get("status") or "queued"),
            "error_message": row.get("error_message"),
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at")),
            "completed_at": _iso(row.get("completed_at")),
        }
        if include_result:
            payload["result_payload"] = row.get("result_payload")
        return payload


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
