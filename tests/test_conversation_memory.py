"""Tests for ConversationMemory — CTX-inspired token-budgeted conversation state.

TDD: These tests are written BEFORE the implementation.
Run with: pytest tests/test_conversation_memory.py -v
"""

from __future__ import annotations

import json

import pytest

from services.conversation_memory import ConversationMemory


# ── 1. TestMemoryConstruction ──


class TestMemoryConstruction:
    """Basic construction and default configuration."""

    def test_creates_memory(self):
        """ConversationMemory() instantiates without error."""
        mem = ConversationMemory()
        assert mem is not None

    def test_default_token_budget(self):
        """Default token budget is 4000."""
        mem = ConversationMemory()
        assert mem.token_budget == 4000

    def test_custom_budget(self):
        """Can set a custom token budget via constructor."""
        mem = ConversationMemory(token_budget=2000)
        assert mem.token_budget == 2000


# ── 2. TestAddExchange ──


class TestAddExchange:
    """Adding question/response exchanges to memory."""

    def test_add_single_exchange(self):
        """Adding a single question+response pair works without error."""
        mem = ConversationMemory()
        mem.add_exchange(
            question="What is semaglutide?",
            response="Semaglutide is a GLP-1 receptor agonist made by Novo Nordisk.",
        )
        # Should have at least one exchange stored
        ctx = mem.get_context()
        assert isinstance(ctx, str)

    def test_add_multiple_exchanges(self):
        """Can add 5+ exchanges without error."""
        mem = ConversationMemory()
        for i in range(5):
            mem.add_exchange(
                question=f"Question {i} about drug {i}",
                response=f"Response {i} about drug {i} details.",
            )
        ctx = mem.get_context()
        assert len(ctx) > 0

    def test_exchange_preserves_question(self):
        """Question text is retrievable from context."""
        mem = ConversationMemory()
        mem.add_exchange(
            question="Tell me about tirzepatide",
            response="Tirzepatide (Mounjaro) is a dual GIP/GLP-1 agonist by Eli Lilly.",
        )
        ctx = mem.get_context()
        assert "tirzepatide" in ctx.lower()

    def test_exchange_preserves_entities(self):
        """Entity names passed to add_exchange are stored and retrievable."""
        mem = ConversationMemory()
        mem.add_exchange(
            question="Compare semaglutide and tirzepatide",
            response="Both are GLP-1 agonists.",
            entities=["semaglutide", "tirzepatide"],
        )
        entities = mem.get_entities_discussed()
        assert "semaglutide" in entities
        assert "tirzepatide" in entities

    def test_exchange_preserves_intent(self):
        """Intent classification is stored with the exchange."""
        mem = ConversationMemory()
        mem.add_exchange(
            question="Compare semaglutide vs tirzepatide",
            response="Both are GLP-1 receptor agonists.",
            intent="compare",
            entities=["semaglutide", "tirzepatide"],
        )
        ctx = mem.get_context()
        assert "compare" in ctx.lower()


# ── 3. TestContextRetrieval ──


class TestContextRetrieval:
    """Getting compressed context for LLM prompts."""

    def test_get_context_returns_string(self):
        """get_context() returns a string."""
        mem = ConversationMemory()
        mem.add_exchange(question="Hello", response="Hi there.")
        result = mem.get_context()
        assert isinstance(result, str)

    def test_context_contains_recent(self):
        """Recent exchanges appear in context output."""
        mem = ConversationMemory()
        mem.add_exchange(
            question="What is Ozempic?",
            response="Ozempic is the brand name for semaglutide.",
        )
        mem.add_exchange(
            question="Who makes it?",
            response="Novo Nordisk manufactures Ozempic.",
        )
        ctx = mem.get_context()
        assert "Novo Nordisk" in ctx or "novo nordisk" in ctx.lower()

    def test_context_under_budget(self):
        """Context stays under the token budget (approximated as word count * 1.3)."""
        mem = ConversationMemory(token_budget=200)
        for i in range(20):
            mem.add_exchange(
                question=f"Tell me about drug number {i} in the pharmaceutical pipeline",
                response=f"Drug {i} is an innovative compound targeting receptor type {i}. "
                         f"It has shown promising results in Phase {i % 4 + 1} trials "
                         f"conducted by Company {i} across multiple therapeutic areas.",
            )
        ctx = mem.get_context()
        # Rough token estimate: words * 1.3
        word_count = len(ctx.split())
        estimated_tokens = word_count * 1.3
        assert estimated_tokens <= 200 * 1.5  # Allow 50% margin for estimation error

    def test_context_prioritizes_recent(self):
        """Recent exchanges are weighted higher / appear in context."""
        mem = ConversationMemory(token_budget=300)
        # Add an old exchange
        mem.add_exchange(
            question="Tell me about aspirin",
            response="Aspirin is an old NSAID.",
        )
        # Add many more to push old ones out
        for i in range(15):
            mem.add_exchange(
                question=f"What about newer drug {i}?",
                response=f"Newer drug {i} is a modern biologic compound with better efficacy.",
            )
        # The very last exchange
        mem.add_exchange(
            question="What about pembrolizumab?",
            response="Pembrolizumab (Keytruda) is a PD-1 inhibitor by Merck.",
        )
        ctx = mem.get_context()
        # Recent should appear, old may be evicted
        assert "pembrolizumab" in ctx.lower() or "keytruda" in ctx.lower()

    def test_empty_memory_returns_empty(self):
        """No exchanges produces empty or minimal context."""
        mem = ConversationMemory()
        ctx = mem.get_context()
        assert ctx == "" or len(ctx) < 20


# ── 4. TestEntityTracking ──


class TestEntityTracking:
    """Tracking entities across conversation turns."""

    def test_tracks_entities_across_turns(self):
        """Entities from turn 1 are still visible after turn 5."""
        mem = ConversationMemory()
        mem.add_exchange(
            question="Tell me about semaglutide",
            response="Semaglutide is a GLP-1 agonist.",
            entities=["semaglutide"],
        )
        for i in range(4):
            mem.add_exchange(
                question=f"Other question {i}",
                response=f"Other response {i}.",
                entities=[f"entity_{i}"],
            )
        entities = mem.get_entities_discussed()
        assert "semaglutide" in entities

    def test_entity_list(self):
        """get_entities_discussed() returns unique entity names."""
        mem = ConversationMemory()
        mem.add_exchange(
            question="Compare drugs",
            response="Comparing semaglutide and tirzepatide.",
            entities=["semaglutide", "tirzepatide"],
        )
        mem.add_exchange(
            question="Add another",
            response="Also consider dulaglutide.",
            entities=["dulaglutide", "semaglutide"],  # semaglutide repeated
        )
        entities = mem.get_entities_discussed()
        assert len(set(entities)) == len(entities)  # All unique
        assert "semaglutide" in entities
        assert "tirzepatide" in entities
        assert "dulaglutide" in entities

    def test_entity_frequency(self):
        """Most-discussed entities are ranked higher in the list."""
        mem = ConversationMemory()
        # Mention semaglutide 4 times
        for _ in range(4):
            mem.add_exchange(
                question="About semaglutide",
                response="Semaglutide info.",
                entities=["semaglutide"],
            )
        # Mention tirzepatide once
        mem.add_exchange(
            question="About tirzepatide",
            response="Tirzepatide info.",
            entities=["tirzepatide"],
        )
        entities = mem.get_entities_discussed()
        sem_idx = entities.index("semaglutide")
        tir_idx = entities.index("tirzepatide")
        assert sem_idx < tir_idx  # More frequent → earlier in list

    def test_entity_from_bold(self):
        """Extracts **bold** entities from assistant responses."""
        mem = ConversationMemory()
        mem.add_exchange(
            question="What drugs are important?",
            response="The key drugs are **semaglutide** and **tirzepatide** in the GLP-1 space.",
        )
        entities = mem.get_entities_discussed()
        assert "semaglutide" in entities
        assert "tirzepatide" in entities


# ── 5. TestCoreference ──


class TestCoreference:
    """Resolving coreferences like 'this drug', 'that company'."""

    def test_resolves_this_drug(self):
        """'this drug' resolves to the last mentioned drug name."""
        mem = ConversationMemory()
        mem.add_exchange(
            question="Tell me about semaglutide",
            response="**Semaglutide** is a GLP-1 receptor agonist.",
            entities=["semaglutide"],
            intent="general",
        )
        resolved = mem.resolve_reference("What trials does this drug have?")
        assert "semaglutide" in resolved.lower()

    def test_resolves_that_company(self):
        """'that company' resolves to the last mentioned company."""
        mem = ConversationMemory()
        mem.add_exchange(
            question="Tell me about Novo Nordisk",
            response="**Novo Nordisk** is a Danish pharma company.",
            entities=["Novo Nordisk"],
            intent="dossier",
        )
        resolved = mem.resolve_reference("What is that company's pipeline?")
        assert "novo nordisk" in resolved.lower()

    def test_resolves_its_pipeline(self):
        """'its pipeline' resolves to last entity + pipeline."""
        mem = ConversationMemory()
        mem.add_exchange(
            question="Tell me about Eli Lilly",
            response="**Eli Lilly** is a major pharma company.",
            entities=["Eli Lilly"],
            intent="dossier",
        )
        resolved = mem.resolve_reference("Show me its pipeline")
        assert "eli lilly" in resolved.lower()
        assert "pipeline" in resolved.lower()

    def test_no_resolution_without_context(self):
        """No history means original question is returned unchanged."""
        mem = ConversationMemory()
        original = "What about this drug?"
        resolved = mem.resolve_reference(original)
        assert resolved == original


# ── 6. TestEviction ──


class TestEviction:
    """Token budget enforcement via eviction."""

    def test_eviction_under_budget(self):
        """Adding 20 exchanges with small budget doesn't exceed budget."""
        mem = ConversationMemory(token_budget=300)
        for i in range(20):
            mem.add_exchange(
                question=f"Question {i} about pharmaceutical compound number {i}",
                response=f"Compound {i} is a novel drug targeting mechanism {i}. "
                         f"It was developed by Company {i} and is in Phase {i % 4 + 1}.",
                entities=[f"compound_{i}"],
            )
        ctx = mem.get_context()
        word_count = len(ctx.split())
        # Token estimate: ~1.3 words per token, allow margin
        assert word_count < 300 * 1.5

    def test_eviction_removes_oldest(self):
        """Oldest exchanges are evicted first when budget is tight."""
        mem = ConversationMemory(token_budget=200)
        mem.add_exchange(
            question="Tell me about aspirin",
            response="Aspirin is an ancient drug. Very old. NSAID category.",
            entities=["aspirin"],
        )
        # Add enough exchanges to force eviction
        for i in range(15):
            mem.add_exchange(
                question=f"What about modern drug {i}?",
                response=f"Modern drug {i} is a cutting-edge biologic therapy in development.",
                entities=[f"drug_{i}"],
            )
        ctx = mem.get_context()
        # Oldest content should be evicted, recent should remain
        # (aspirin exchange is old and should be gone from the context text)
        last_drug = "drug_14"
        assert last_drug in ctx.lower()

    def test_eviction_preserves_entities(self):
        """Entity names survive eviction even if their exchange text is removed."""
        mem = ConversationMemory(token_budget=200)
        mem.add_exchange(
            question="Tell me about semaglutide",
            response="Semaglutide is a GLP-1 agonist.",
            entities=["semaglutide"],
        )
        for i in range(15):
            mem.add_exchange(
                question=f"Other drug {i}",
                response=f"Drug {i} is interesting.",
                entities=[f"drug_{i}"],
            )
        # Even though semaglutide's exchange may be evicted from context,
        # the entity should still be tracked
        entities = mem.get_entities_discussed()
        assert "semaglutide" in entities

    def test_eviction_preserves_key_facts(self):
        """Important facts (intent, entities) survive eviction."""
        mem = ConversationMemory(token_budget=200)
        mem.add_exchange(
            question="Compare semaglutide vs tirzepatide",
            response="Both are GLP-1 agonists. Semaglutide by Novo Nordisk, tirzepatide by Eli Lilly.",
            intent="compare",
            entities=["semaglutide", "tirzepatide"],
        )
        for i in range(15):
            mem.add_exchange(
                question=f"Drug {i}?",
                response=f"Info about drug {i}.",
                entities=[f"drug_{i}"],
            )
        # Entities from the evicted exchange should persist
        entities = mem.get_entities_discussed()
        assert "semaglutide" in entities
        assert "tirzepatide" in entities


# ── 7. TestSerialization ──


class TestSerialization:
    """Snapshot and restore for persistence."""

    def test_snapshot_returns_string(self):
        """snapshot() returns a JSON-serializable string."""
        mem = ConversationMemory()
        mem.add_exchange(
            question="Hello",
            response="Hi there.",
            entities=["greeting"],
        )
        state = mem.snapshot()
        assert isinstance(state, str)
        # Should be valid JSON
        parsed = json.loads(state)
        assert isinstance(parsed, dict)

    def test_restore_from_snapshot(self):
        """Can restore state from a snapshot string."""
        mem = ConversationMemory()
        mem.add_exchange(
            question="Tell me about semaglutide",
            response="Semaglutide is a GLP-1 agonist.",
            entities=["semaglutide"],
        )
        state = mem.snapshot()

        # Create new memory and restore
        mem2 = ConversationMemory()
        mem2.restore(state)
        entities = mem2.get_entities_discussed()
        assert "semaglutide" in entities

    def test_round_trip(self):
        """Add exchanges -> snapshot -> restore -> same entities and context."""
        mem = ConversationMemory()
        mem.add_exchange(
            question="Compare drugs",
            response="Semaglutide vs tirzepatide analysis.",
            intent="compare",
            entities=["semaglutide", "tirzepatide"],
        )
        mem.add_exchange(
            question="Who makes them?",
            response="Novo Nordisk and Eli Lilly.",
            entities=["Novo Nordisk", "Eli Lilly"],
        )

        state = mem.snapshot()
        mem2 = ConversationMemory()
        mem2.restore(state)

        # Same entities
        orig_entities = set(mem.get_entities_discussed())
        restored_entities = set(mem2.get_entities_discussed())
        assert orig_entities == restored_entities

        # Context should be equivalent
        orig_ctx = mem.get_context()
        restored_ctx = mem2.get_context()
        assert orig_ctx == restored_ctx
