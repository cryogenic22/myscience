"""
Step 3: Generate vector embeddings for text content.

Batches embedding requests for efficiency. Records without text_content
pass through with embedding=None.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional

from integration.entity_resolver import ResolvedRecord
from services.llm_gateway import guard_openai_embeddings  # PRIV-001b egress adapter

logger = logging.getLogger(__name__)

# Minimum text length worth embedding (shorter strings produce low-quality vectors)
_MIN_TEXT_LENGTH = 10


def _retry_with_backoff(fn, max_attempts=3, base_delay=1.0):
    """Retry a function with exponential backoff + jitter."""
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            if attempt == max_attempts - 1:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            logger.warning("Retry %d/%d after %.1fs: %s", attempt + 1, max_attempts, delay, e)
            time.sleep(delay)


@dataclass
class EmbeddedRecord:
    """A ResolvedRecord with its embedding computed."""

    resolved: ResolvedRecord
    embedding: Optional[list[float]] = None


class Embedder:
    """
    Generates embeddings for text content using OpenAI text-embedding-3-small.

    Supports batching: call embed_batch() for multiple records at once
    to minimize API calls, or embed() for single records.
    """

    def __init__(self, config):
        self.config = config
        self.model = config.embedding.model
        self.batch_size = config.embedding.batch_size
        self._client = None  # Lazy init

    @property
    def client(self):
        """Lazy-initialize the OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.config.embedding.api_key)
            except ImportError:
                raise RuntimeError(
                    "openai package not installed. Run: pip install openai"
                )
        return self._client

    def embed(self, record: ResolvedRecord) -> EmbeddedRecord:
        """Generate embedding for a single record."""
        text = record.normalized.text_content

        if not text or not text.strip():
            return EmbeddedRecord(resolved=record, embedding=None)

        # Skip very short text — produces low-quality vectors
        if len(text.strip()) < _MIN_TEXT_LENGTH:
            logger.debug(
                "Skipping embedding for record %s: text too short (%d chars)",
                record.normalized.raw.external_id,
                len(text.strip()),
            )
            return EmbeddedRecord(resolved=record, embedding=None)

        # Truncate to ~8000 tokens (~32000 chars) to stay within model limits
        truncated = text[:32000]

        try:
            response = _retry_with_backoff(
                lambda: guard_openai_embeddings(
                    self.client,
                    input=truncated,
                    model=self.model,
                )
            )
            embedding = response.data[0].embedding
            return EmbeddedRecord(resolved=record, embedding=embedding)

        except Exception as e:
            logger.warning(
                "Embedding failed for record %s: %s. Storing without embedding.",
                record.normalized.raw.external_id,
                e,
            )
            return EmbeddedRecord(resolved=record, embedding=None)

    def embed_batch(self, records: list[ResolvedRecord]) -> list[EmbeddedRecord]:
        """
        Generate embeddings for multiple records in batched API calls.
        Records without text_content are returned with embedding=None.
        """
        results: list[EmbeddedRecord] = []

        # Separate records with and without text
        with_text: list[tuple[int, ResolvedRecord, str]] = []
        for i, rec in enumerate(records):
            text = rec.normalized.text_content
            if text and text.strip():
                with_text.append((i, rec, text[:32000]))
            else:
                results.append(EmbeddedRecord(resolved=rec, embedding=None))

        if not with_text:
            return results

        # Batch embed
        for batch_start in range(0, len(with_text), self.batch_size):
            batch = with_text[batch_start : batch_start + self.batch_size]
            texts = [t[2] for t in batch]

            try:
                response = guard_openai_embeddings(
                    self.client,
                    input=texts,
                    model=self.model,
                )

                for (_, rec, _), emb_data in zip(batch, response.data):
                    results.append(
                        EmbeddedRecord(resolved=rec, embedding=emb_data.embedding)
                    )

            except Exception as e:
                logger.warning("Batch embedding failed: %s. Falling back to individual.", e)
                for _, rec, text in batch:
                    results.append(self.embed(rec))

        return results
