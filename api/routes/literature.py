"""Literature Explorer API routes.

Provides structured article documents with parsed sections and cross-links
for the three-panel Literature Explorer frontend.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_db
from db import Database
from services.literature import parse_sections

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/literature", tags=["literature"])

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@router.get("/{article_id}/document")
def get_literature_document(article_id: str, db: Database = Depends(get_db)):
    """Return a structured article document with parsed sections and cross-links.

    Accepts UUID (pubmed_articles.id) or PMID string.
    """
    # Resolve article — try UUID first, then PMID
    if _UUID_RE.match(article_id):
        article = db.fetch_one(
            """
            SELECT pa.id, pa.pmid, pa.title, pa.abstract, pa.authors,
                   pa.journal, pa.publication_date, pa.mesh_terms,
                   pa.source_url
            FROM pubmed_articles pa
            WHERE pa.id = %s
            """,
            [article_id],
        )
    else:
        article = db.fetch_one(
            """
            SELECT pa.id, pa.pmid, pa.title, pa.abstract, pa.authors,
                   pa.journal, pa.publication_date, pa.mesh_terms,
                   pa.source_url
            FROM pubmed_articles pa
            WHERE pa.pmid = %s
            """,
            [article_id],
        )

    if not article:
        raise HTTPException(404, f"Article not found: {article_id}")

    pa_id = str(article["id"])
    pmid = article.get("pmid") or ""

    # Join PMC data if available
    pmc = db.fetch_one(
        """
        SELECT pmc_id, full_text, article_type, is_protocol, is_systematic_review
        FROM pmc_articles
        WHERE pubmed_article_id = %s OR pmid = %s
        LIMIT 1
        """,
        [pa_id, pmid],
    )

    full_text = pmc["full_text"] if pmc else None
    pmc_id = pmc["pmc_id"] if pmc else None

    # Parse sections
    sections = parse_sections(full_text, article.get("abstract"))

    # Cross-links from entity_links
    cross_links = _get_cross_links(db, pa_id)

    # Build response
    pub_date = article.get("publication_date")
    return {
        "article_id": pa_id,
        "pmid": pmid,
        "pmc_id": pmc_id,
        "title": article.get("title") or "",
        "journal": article.get("journal"),
        "publication_date": pub_date.isoformat() if hasattr(pub_date, "isoformat") else str(pub_date) if pub_date else None,
        "authors": article.get("authors") or [],
        "mesh_terms": article.get("mesh_terms") or [],
        "article_type": pmc["article_type"] if pmc else None,
        "is_protocol": bool(pmc and pmc.get("is_protocol")),
        "is_systematic_review": bool(pmc and pmc.get("is_systematic_review")),
        "has_full_text": bool(full_text),
        "sections": sections,
        "cross_links": cross_links,
        "external_urls": {
            "pubmed": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
            "pmc": f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/" if pmc_id else None,
        },
    }


def _get_cross_links(db: Database, article_id: str) -> dict:
    """Fetch linked drugs, trials, and mechanisms from entity_links."""
    drugs = []
    trials = []
    mechanisms = []

    try:
        rows = db.fetch_all(
            """
            SELECT el.link_type,
                   el.source_entity_id, el.source_entity_type,
                   el.target_entity_id, el.target_entity_type
            FROM entity_links el
            WHERE (el.source_entity_id = %s AND el.source_entity_type = 'literature')
               OR (el.target_entity_id = %s AND el.target_entity_type = 'literature')
            LIMIT 50
            """,
            [article_id, article_id],
        )

        for row in rows:
            # Determine the "other" entity (not the article)
            if row["source_entity_id"] == article_id:
                other_id = row["target_entity_id"]
                other_type = row["target_entity_type"]
            else:
                other_id = row["source_entity_id"]
                other_type = row["source_entity_type"]

            link_type = row["link_type"]

            if other_type == "drug":
                name_row = db.fetch_one(
                    "SELECT generic_name FROM drugs WHERE id::text = %s", [other_id]
                )
                drugs.append({
                    "id": other_id,
                    "name": name_row["generic_name"] if name_row else other_id,
                    "link_type": link_type,
                })
            elif other_type == "trial":
                name_row = db.fetch_one(
                    "SELECT title FROM clinical_trials WHERE id = %s", [other_id]
                )
                trials.append({
                    "id": other_id,
                    "title": name_row["title"] if name_row else other_id,
                    "link_type": link_type,
                })
            elif other_type == "mechanism":
                name_row = db.fetch_one(
                    "SELECT name FROM mechanisms_of_action WHERE id::text = %s", [other_id]
                )
                mechanisms.append({
                    "id": other_id,
                    "name": name_row["name"] if name_row else other_id,
                })
    except Exception:
        logger.debug("Failed to fetch cross-links for article %s", article_id, exc_info=True)

    return {"drugs": drugs, "trials": trials, "mechanisms": mechanisms}
