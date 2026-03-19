"""
Backfill embeddings for all records that have text content but NULL embedding columns.

Usage: python backfill_embeddings.py
"""

import logging
import time
from config import config
from db import Database
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 50  # OpenAI embedding batch size
MODEL = config.embedding.model

# Tables with embedding columns and their text source columns
EMBEDDING_TARGETS = [
    {
        "table": "therapeutic_areas",
        "embedding_col": "scope_note_embedding",
        "text_col": "scope_note",
        "id_col": "id",
    },
    {
        "table": "mechanisms_of_action",
        "embedding_col": "scope_note_embedding",
        "text_col": "scope_note",
        "id_col": "id",
    },
    {
        "table": "drugs",
        "embedding_col": "molecule_embedding",
        "text_col": "generic_name",  # concatenate with brand_name + dosage info
        "id_col": "id",
        "text_query": "generic_name || COALESCE(' (' || brand_name || ')', '') || COALESCE(' ' || dosage_form, '') || COALESCE(' ' || route, '')",
    },
    {
        "table": "companies",
        "embedding_col": "strategy_embedding",
        "text_col": "name",
        "id_col": "id",
        "text_query": "name || COALESCE(' (ticker: ' || ticker || ')', '') || COALESCE(' SIC: ' || sic_code, '')",
    },
    {
        "table": "pubmed_articles",
        "embedding_col": "abstract_embedding",
        "text_col": "abstract",
        "id_col": "id",
        "text_query": "COALESCE(title, '') || '. ' || COALESCE(abstract, '')",
    },
    {
        "table": "clinical_trials",
        "embedding_col": "protocol_embedding",
        "text_col": "detailed_description",
        "id_col": "id",
        "text_query": "COALESCE(detailed_description, '')",
    },
]


def backfill():
    client = OpenAI(api_key=config.embedding.api_key)
    db = Database(config.db.dsn)
    db.connect()

    total_updated = 0

    for target in EMBEDDING_TARGETS:
        table = target["table"]
        emb_col = target["embedding_col"]
        id_col = target["id_col"]
        text_query = target.get("text_query", target["text_col"])

        # Find rows with NULL embedding and non-empty text
        rows = db.fetch_all(
            f"SELECT {id_col}, {text_query} AS text_content "
            f"FROM {table} "
            f"WHERE {emb_col} IS NULL AND {text_query} IS NOT NULL AND {text_query} != '' "
            f"ORDER BY {id_col}"
        )

        if not rows:
            logger.info("%s: no rows need embedding", table)
            continue

        logger.info("%s: %d rows need embedding", table, len(rows))

        # Process in batches
        for batch_start in range(0, len(rows), BATCH_SIZE):
            batch = rows[batch_start:batch_start + BATCH_SIZE]
            texts = [r["text_content"][:32000] for r in batch]
            ids = [r[id_col] for r in batch]

            try:
                response = client.embeddings.create(input=texts, model=MODEL)

                for row_id, emb_data in zip(ids, response.data):
                    embedding = emb_data.embedding
                    db.execute(
                        f"UPDATE {table} SET {emb_col} = %s WHERE {id_col} = %s",
                        [embedding, row_id],
                    )

                total_updated += len(batch)
                logger.info(
                    "  %s: batch %d-%d done (%d/%d)",
                    table,
                    batch_start,
                    batch_start + len(batch),
                    min(batch_start + len(batch), len(rows)),
                    len(rows),
                )

            except Exception as e:
                logger.error("  %s: batch failed: %s", table, e)

            time.sleep(0.2)  # Rate limit courtesy

    logger.info("Backfill complete: %d embeddings generated", total_updated)

    # Show final counts
    print("\n=== Embedding Coverage ===")
    for target in EMBEDDING_TARGETS:
        table = target["table"]
        emb_col = target["embedding_col"]
        total = db.fetch_one(f"SELECT count(*) as c FROM {table}")["c"]
        filled = db.fetch_one(f"SELECT count(*) as c FROM {table} WHERE {emb_col} IS NOT NULL")["c"]
        print(f"  {table:30s} {filled:>5}/{total:<5} ({100*filled//max(total,1)}%)")

    db.close()


if __name__ == "__main__":
    backfill()
