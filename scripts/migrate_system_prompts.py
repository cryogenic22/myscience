"""BE-40 — seed prompt_registry from the SYSTEM_PROMPTS dict.

Idempotent: looks up each (name, content_hash) and skips when the
row already exists. Marks the latest version per name as
``is_active = TRUE``. Safe to run repeatedly as the in-file dict
evolves.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


def _hash_content(content: str) -> bytes:
    return hashlib.sha256(content.encode("utf-8")).digest()


def upsert_seed(db: Any, *, name: str, content: str, purpose: str = "") -> dict:
    """Idempotent INSERT — returns the prompt_id either way.

    Increments version when content changes; reuses the row when
    content_hash matches an existing version.
    """
    h = _hash_content(content)
    existing = db.fetch_one(
        "SELECT prompt_id::text AS prompt_id, version "
        "FROM prompt_registry WHERE name = %s AND content_hash = %s",
        [name, h],
    )
    if existing:
        return {"prompt_id": existing["prompt_id"], "version": int(existing["version"]),
                "created": False}

    next_version_row = db.fetch_one(
        "SELECT COALESCE(MAX(version), 0) + 1 AS v FROM prompt_registry WHERE name = %s",
        [name],
    )
    next_version = int((next_version_row or {}).get("v") or 1)

    row = db.fetch_one(
        """INSERT INTO prompt_registry (name, version, content, content_hash, purpose)
           VALUES (%s, %s, %s, %s, %s)
           RETURNING prompt_id::text AS prompt_id, version""",
        [name, next_version, content, h, purpose],
    )
    if not row:
        raise RuntimeError("upsert_seed: insert returned no row")

    # Mark this version as active and demote any previous active row
    # for the same name. Wrapped in a try so a missing is_active column
    # (pre-076 deploy) is non-fatal — the registry still works without
    # the active flag.
    try:
        db.execute(
            "UPDATE prompt_registry SET is_active = FALSE WHERE name = %s AND is_active = TRUE",
            [name],
        )
        db.execute(
            "UPDATE prompt_registry SET is_active = TRUE WHERE prompt_id::text = %s",
            [row["prompt_id"]],
        )
    except Exception:
        logger.debug("is_active flip skipped (column missing?)", exc_info=True)
    return {"prompt_id": row["prompt_id"], "version": int(row["version"]),
            "created": True}


def seed_all(db: Any) -> dict:
    """Push every entry in services.llm.SYSTEM_PROMPTS into the registry."""
    from services.llm import SYSTEM_PROMPTS

    created = 0
    skipped = 0
    out_rows: list[dict] = []
    for intent, content in SYSTEM_PROMPTS.items():
        name = f"system.{intent}"
        try:
            res = upsert_seed(db, name=name, content=content,
                              purpose=f"intent={intent} (seeded by BE-40)")
        except Exception as exc:
            logger.warning("seed_all: %s failed: %s", name, exc)
            continue
        if res.get("created"):
            created += 1
        else:
            skipped += 1
        out_rows.append({"name": name, **res})
    return {"created": created, "skipped": skipped, "rows": out_rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed prompt_registry from SYSTEM_PROMPTS.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    from db import Database
    from config import config

    db = Database(config.db.dsn)
    summary = seed_all(db)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
