"""C2 (learning loops) — chat answer feedback (thumbs up/down).

The missing training signal: a per-answer rating from the user. Records into
chat_answer_feedback (migration 080), keyed by session + question_hash so it
can be joined back to query_telemetry. Pure DB helpers; the route is a thin
wrapper. Idempotent in spirit (append-only history — a user may flip a vote;
reads return the latest).
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def question_hash(question: str) -> str:
    """Match the hashing used by query_telemetry (sha256[:16]) so feedback
    rows align with the telemetry row for the same question."""
    return hashlib.sha256((question or "").encode()).hexdigest()[:16]


def record_feedback(
    db,
    *,
    question: str,
    rating: int,
    session_id: Optional[str] = None,
    comment: Optional[str] = None,
    intent: Optional[str] = None,
    answer_excerpt: Optional[str] = None,
) -> dict:
    """Persist one feedback row. `rating` must be +1 (up) or -1 (down).

    Returns the inserted row as a dict. Raises ValueError on bad input.
    """
    if rating not in (-1, 1):
        raise ValueError("rating must be -1 (down) or +1 (up)")
    if not question or not question.strip():
        raise ValueError("question is required")

    q_hash = question_hash(question)
    # Best-effort link to the most recent telemetry row for this question.
    telemetry_id = None
    try:
        row = db.fetch_one(
            """SELECT id FROM query_telemetry
                WHERE question_hash = %s
                ORDER BY created_at DESC LIMIT 1""",
            [q_hash],
        )
        if row and row.get("id"):
            telemetry_id = str(row["id"])
    except Exception:
        logger.debug("query_telemetry lookup failed for feedback", exc_info=True)

    inserted = db.fetch_one(
        """
        INSERT INTO chat_answer_feedback
            (session_id, question_hash, question_text, rating, comment,
             intent, answer_excerpt, query_telemetry_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::uuid)
        RETURNING id, session_id, question_hash, rating, intent,
                  query_telemetry_id, created_at
        """,
        [
            session_id, q_hash, question[:2000], int(rating), comment,
            intent, (answer_excerpt or "")[:500] or None, telemetry_id,
        ],
    )
    if not inserted:
        raise RuntimeError("record_feedback: insert returned no row")
    return {
        "id": str(inserted["id"]),
        "session_id": inserted.get("session_id"),
        "question_hash": inserted["question_hash"],
        "rating": int(inserted["rating"]),
        "intent": inserted.get("intent"),
        "query_telemetry_id": (
            str(inserted["query_telemetry_id"])
            if inserted.get("query_telemetry_id") else None
        ),
        "created_at": (
            inserted["created_at"].isoformat()
            if inserted.get("created_at") else None
        ),
    }


def list_feedback_for_question(db, question: str, *, limit: int = 50) -> list[dict]:
    """Return feedback rows for a question (latest first)."""
    q_hash = question_hash(question)
    rows = db.fetch_all(
        """
        SELECT id, session_id, question_hash, rating, comment, intent,
               query_telemetry_id, created_at
          FROM chat_answer_feedback
         WHERE question_hash = %s
         ORDER BY created_at DESC
         LIMIT %s
        """,
        [q_hash, limit],
    ) or []
    return [
        {
            "id": str(r["id"]),
            "session_id": r.get("session_id"),
            "question_hash": r["question_hash"],
            "rating": int(r["rating"]),
            "comment": r.get("comment"),
            "intent": r.get("intent"),
            "query_telemetry_id": (
                str(r["query_telemetry_id"]) if r.get("query_telemetry_id") else None
            ),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        for r in rows
    ]


def feedback_summary(db, *, days: int = 30) -> dict:
    """Aggregate up/down counts over the window — a quick answer-quality gauge."""
    row = db.fetch_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE rating = 1)  AS up,
            COUNT(*) FILTER (WHERE rating = -1) AS down,
            COUNT(*) AS total
          FROM chat_answer_feedback
         WHERE created_at > NOW() - make_interval(days := %s)
        """,
        [days],
    ) or {}
    up = int(row.get("up") or 0)
    down = int(row.get("down") or 0)
    total = int(row.get("total") or 0)
    return {
        "days": days,
        "up": up,
        "down": down,
        "total": total,
        "satisfaction_pct": round(100.0 * up / total, 1) if total else None,
    }
