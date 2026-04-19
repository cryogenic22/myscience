# SPEC-011: CTX ContextGuard as Default

*Date: 19 April 2026*
*Priority: P1*
*Effort: 1 day*

---

## Goal

Promote the CTX-based UnifiedChatHandler from opt-in (`MZ_UNIFIED_HANDLER=true`) to the production default. This shifts hallucination prevention from post-hoc citation stripping (current state) to pre-emptive context constraint (CTX guard checks model output against the verified evidence set before serving).

## Why This Matters

From the lead's review (Section 7.3 of `lead_notes_4_dev.md`):

> The pre-generation context guard that constrains the LLM's available fact set exists in the codebase but is not connected to the chat handler pipeline. Wiring it would shift hallucination prevention from post-hoc (stripping bad citations after generation) to pre-emptive. **This is the single highest-leverage change for intelligence quality.**

Currently:
- Default chat path: 8-handler intent fork → LLM synthesis → post-hoc citation validation
- Opt-in CTX path: `UnifiedChatHandler` → CTXQueryPipeline (understand → retrieve → reason) → CTX guard verifies output against retrieval set

The CTX path catches a class of hallucinations that the post-hoc validator misses: claims that contain *valid-looking* citation markers and *plausible-sounding* numbers but were not in the retrieval set at all.

## Tests First

Create `tests/test_ctx_guard_default.py`:

```python
"""Verify CTX guard is wired as default chat path and catches hallucinations."""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from api.app import create_app
from config import config
from services.unified_handler import UnifiedChatHandler
from services.ctx_pipeline import CTXQueryPipeline, ReasoningResult


def test_unified_handler_is_default_in_config(monkeypatch):
    """SPEC_011: MZ_UNIFIED_HANDLER must default to true."""
    # Even with no env override, the unified handler is enabled
    monkeypatch.delenv("MZ_UNIFIED_HANDLER", raising=False)
    from importlib import reload
    import config as config_module
    reload(config_module)
    assert config_module.config.unified_handler_enabled is True


def test_chat_route_uses_unified_handler_by_default(monkeypatch):
    """A chat request with no env override must hit UnifiedChatHandler."""
    monkeypatch.delenv("MZ_UNIFIED_HANDLER", raising=False)

    handler_calls = []
    def fake_handle(self, query, session_id=None, **kw):
        handler_calls.append(query)
        return {
            "narrative": "stub",
            "evidence": [],
            "metadata": {"handler": "unified"},
        }

    monkeypatch.setattr(UnifiedChatHandler, "handle", fake_handle)
    app = create_app()
    client = TestClient(app)
    r = client.post("/chat", json={"query": "what drugs target GLP-1?"})
    assert r.status_code == 200
    assert handler_calls == ["what drugs target GLP-1?"]


def test_ctx_guard_blocks_hallucinated_citation():
    """If LLM produces a citation marker not in the evidence set, guard suppresses it."""
    pipeline = CTXQueryPipeline(
        llm=MagicMock(),
        retriever=MagicMock(),
    )
    evidence_ids = {"E1", "E2", "E3"}
    raw_response = "Semaglutide reduces A1C by 1.5% [E1] and weight by 12% [E99]."

    cleaned, suppressed = pipeline.check_response(raw_response, evidence_ids)

    assert "[E1]" in cleaned
    assert "[E99]" not in cleaned
    assert "E99" in suppressed


def test_ctx_guard_passes_valid_response_unchanged():
    pipeline = CTXQueryPipeline(llm=MagicMock(), retriever=MagicMock())
    evidence_ids = {"E1", "E2"}
    raw = "Tirzepatide showed 22% weight loss [E1] in SURMOUNT-1 [E2]."
    cleaned, suppressed = pipeline.check_response(raw, evidence_ids)
    assert cleaned == raw
    assert suppressed == set()


def test_unified_handler_falls_back_on_pipeline_error(monkeypatch):
    """If CTXQueryPipeline raises, fall back to legacy 8-handler path. Must not 500."""
    monkeypatch.delenv("MZ_UNIFIED_HANDLER", raising=False)
    monkeypatch.setattr(
        CTXQueryPipeline, "reason",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("forced fail"))
    )
    app = create_app()
    client = TestClient(app)
    r = client.post("/chat", json={"query": "test"})
    assert r.status_code == 200
    body = r.json()
    # Indicate which path served the response
    assert body["metadata"].get("handler") in ("legacy_fallback", "legacy")


def test_ctx_guard_telemetry_logged(monkeypatch, db_session):
    """Each guard suppression must log a telemetry event."""
    from services.telemetry import log_ctx_event
    events = []
    monkeypatch.setattr(
        "services.telemetry.log_ctx_event",
        lambda **kw: events.append(kw)
    )
    pipeline = CTXQueryPipeline(llm=MagicMock(), retriever=MagicMock())
    pipeline.check_response("foo [E99] bar", {"E1"})
    assert any(e.get("event_type") == "guard_suppression" for e in events)


def test_no_regression_on_known_good_query(monkeypatch):
    """A query that worked under the legacy path must still produce a valid response under CTX."""
    monkeypatch.delenv("MZ_UNIFIED_HANDLER", raising=False)
    app = create_app()
    client = TestClient(app)
    r = client.post("/chat", json={"query": "compare semaglutide and tirzepatide"})
    assert r.status_code == 200
    body = r.json()
    assert "narrative" in body
    assert len(body["narrative"]) > 50  # not an empty failure response
```

**Run them**: `python -m pytest tests/test_ctx_guard_default.py -v`. All must FAIL initially.

## Implementation Plan

### Step 1 — Flip the default in `config.py`

Find the `unified_handler_enabled` flag (likely in `AppConfig` or read from env). Change default from `False` to `True`:

```python
# BEFORE
unified_handler_enabled: bool = field(
    default_factory=lambda: os.getenv("MZ_UNIFIED_HANDLER", "false").lower() == "true"
)

# AFTER
unified_handler_enabled: bool = field(
    default_factory=lambda: os.getenv("MZ_UNIFIED_HANDLER", "true").lower() == "true"
)
```

### Step 2 — Verify `api/routes/chat.py` actually uses the flag

Confirm the chat route checks `config.unified_handler_enabled` and routes through `UnifiedChatHandler` when true. Trace the existing opt-in path; the only change should be that it's now opt-out.

### Step 3 — Strengthen the fallback handler

When `UnifiedChatHandler.handle()` raises, the route must catch and fall through to the legacy 8-handler path. Add the catch with a telemetry event:

```python
try:
    return unified_handler.handle(query, session_id=session_id)
except Exception as exc:
    log_ctx_event(event_type="unified_handler_fallback", metadata={"error": str(exc)})
    return legacy_handle(query, session_id=session_id)
```

The metadata must mark `"handler": "legacy_fallback"` so we can monitor fallback rate.

### Step 4 — Add guard suppression telemetry

In `services/ctx_pipeline.py::check_response`, after computing `suppressed`, log:

```python
if suppressed:
    log_ctx_event(
        event_type="guard_suppression",
        metadata={
            "suppressed_count": len(suppressed),
            "suppressed_ids": list(suppressed),
        },
    )
```

### Step 5 — Add a fallback rate dashboard panel (optional, ship in follow-up)

Surface `unified_handler_fallback` event count in `/metrics/ctx-telemetry`. If fallback rate > 5%, the CTX path has a regression that needs fixing.

## Acceptance Criteria

- [ ] All tests in `tests/test_ctx_guard_default.py` pass
- [ ] Existing chat tests do not regress
- [ ] After deploy: `MZ_UNIFIED_HANDLER` env var is set to `true` in Railway (or unset, with new default)
- [ ] Chat queries return responses (`/chat` returns 200) — no 500s
- [ ] Manually verify in production: send a query, check response metadata shows `"handler": "unified"`
- [ ] Telemetry: `unified_handler_fallback` event count < 5% of total chat requests over 24 hours
- [ ] Telemetry: `guard_suppression` events appear in `/metrics/ctx-telemetry` (proves the guard is firing)

## Rollout / Rollback

**Rollout:**
1. Local test suite passes.
2. Deploy to Railway.
3. Set `MZ_UNIFIED_HANDLER=true` explicitly in Railway env (defensive — even though default is now true).
4. Monitor `/metrics/ctx-telemetry` and `/health` for 4 hours.
5. Send 5 representative queries via the UI to confirm response quality.

**Rollback:**
- Set `MZ_UNIFIED_HANDLER=false` in Railway env. Effective immediately on next request.
- If config rollback isn't enough, `git revert` the commit.

## Out of Scope

- Improving CTX retrieval quality itself (separate work — this spec is about wiring, not algorithm improvements)
- Removing the legacy 8-handler fork (deferred until fallback rate stays at 0% for 30 days)
- Adding new CTX guard rules (current rule set is sufficient — citation marker validation)
