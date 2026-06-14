"""Loop 0 (data-strategy audit) — regression for the ON_NEW_ENTITY auto-create path.

integration/pipeline.py `_process_record` fires an ON_NEW_ENTITY hook when entity
resolution auto-creates an entity. That branch referenced an undefined module-global
`RECORD_TYPE_TO_ENTITY` (a NameError landmine), while the rest of the method correctly
uses the instance map `self._record_type_to_entity` keyed by `record_type.value`. The
crash was latent because auto-create is off in the default resolver config, so it would
detonate the moment auto-create is enabled. This test drives the auto-create branch in
isolation (heavy pipeline deps stubbed) and asserts (a) it does NOT raise, and (b) the
fired ON_NEW_ENTITY context carries the correct entity_type.

DB-free, no network. Fails (NameError) without the one-line fix; passes with it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from connectors.base import Provenance, RawRecord, RecordType, SourceType
from integration.pipeline import IntegrationPipeline


class _AutoCreateLink:
    """Stand-in for a resolver link that auto-created its entity."""
    method = "auto_create"
    entity_id = 4242
    confidence = 0.91
    raw_value = "Novo Nordisk"


class _Resolved:
    resolved_links = {"company": _AutoCreateLink()}


def _record(record_type: RecordType = RecordType.DRUG) -> RawRecord:
    return RawRecord(
        record_type=record_type,
        external_id="D1",
        source_name="probe",
        provenance=Provenance(
            source_type=SourceType.CLINICAL_TRIALS_GOV,
            api_endpoint="https://example.test",
            query_params={},
            retrieved_at=datetime.now(timezone.utc),
            raw_response_hash="0" * 64,
        ),
        data={},
    )


def _pipeline_with_stubs(captured: list):
    """Build an IntegrationPipeline with only the attributes _process_record touches,
    bypassing the heavy __init__."""
    p = IntegrationPipeline.__new__(IntegrationPipeline)
    p.db = MagicMock()
    p.normalizer = MagicMock()
    p.normalizer.normalize.return_value = MagicMock(canonical_data={})
    p.resolver = MagicMock()
    p.resolver.resolve.return_value = _Resolved()
    p.embedder = MagicMock()
    p.embedder.embed.return_value = MagicMock()
    p.store = MagicMock()
    p.store.store.return_value = ("stored-1", True)
    p.linker = MagicMock()
    p.linker.cross_link.return_value = []
    p._record_type_to_entity = {"drug": "drug", "company": "company", "trial": "trial"}

    hooks = MagicMock()
    hooks.fire.side_effect = lambda point, ctx: captured.append((point, ctx)) or []
    hooks.has_block.return_value = False
    p.hooks = hooks
    return p


def test_auto_create_branch_does_not_raise_and_sets_entity_type():
    captured: list = []
    p = _pipeline_with_stubs(captured)

    # Would raise NameError on the unfixed code (RECORD_TYPE_TO_ENTITY undefined).
    p._process_record(_record(RecordType.DRUG), "run-1", MagicMock())

    on_new = [ctx for point, ctx in captured if point == "ON_NEW_ENTITY"]
    assert on_new, "ON_NEW_ENTITY hook was not fired on the auto_create path"
    assert on_new[0].entity_type == "drug"
    assert on_new[0].metadata["resolution_method"] == "auto_create"
