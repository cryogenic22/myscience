# SPEC-011: CTX ContextGuard as Default + A/B Rollout

*Date: 19 April 2026 (revised with A/B rollout design)*
*Priority: P1*
*Effort: 1 day*

---

## Goal

Promote the CTX-based UnifiedChatHandler from opt-in (`MZ_UNIFIED_HANDLER=true`) to the production default, with an **A/B rollout dial** so we can measure CTX impact on real production traffic before going to 100%.

This shifts hallucination prevention from post-hoc citation stripping (current state) to pre-emptive context constraint, AND grounds every LLM response against the packed pharma corpus instead of just search-hit evidence.

## Why A/B Instead of Hard Flip

The CTX path activates `PharmaCorpusBuilder` — a packed corpus of every drug, company, trial, and mechanism in the DB — as grounding context. This is a fundamentally different LLM input than the legacy 8-handler path. We need real-traffic evidence that:

1. Hallucination rate drops (measured via guard suppressions)
2. Token cost stays reasonable (CTX compression should net out the corpus inclusion)
3. Benchmark score doesn't regress
4. P50/P95 latency stays acceptable

A 50/50 split for 48h gives statistically meaningful comparison without committing to one side.

## Why This Matters

From the lead's review (Section 7.3 of `lead_notes_4_dev.md`):

> The pre-generation context guard that constrains the LLM's available fact set exists in the codebase but is not connected to the chat handler pipeline. Wiring it would shift hallucination prevention from post-hoc (stripping bad citations after generation) to pre-emptive. **This is the single highest-leverage change for intelligence quality.**

Currently:
- Default chat path: 8-handler intent fork → LLM synthesis → post-hoc citation validation
- Opt-in CTX path: `UnifiedChatHandler` → CTXQueryPipeline (understand → retrieve → reason) → CTX guard verifies output against retrieval set

The CTX path catches a class of hallucinations that the post-hoc validator misses: claims that contain *valid-looking* citation markers and *plausible-sounding* numbers but were not in the retrieval set at all.

## Configuration Surface

Two env vars control the rollout:

| Var | Type | Default | Purpose |
|-----|------|---------|---------|
| `MZ_UNIFIED_HANDLER` | bool | `true` (changed from `false`) | Hard kill switch. `false` = always legacy. `true` = honor rollout dial. |
| `MZ_UNIFIED_HANDLER_ROLLOUT` | float 0.0–1.0 | `1.0` | Fraction of sessions routed to unified handler. `0.5` = 50% A/B. |

**Promotion path:**
1. Ship with `MZ_UNIFIED_HANDLER=true`, `MZ_UNIFIED_HANDLER_ROLLOUT=0.5` → 50% A/B
2. Monitor 48h: compare guard suppressions, fallback rate, token cost, latency
3. If treatment wins: `ROLLOUT=1.0` (100% unified)
4. If treatment loses: `ROLLOUT=0.0` (revert), open follow-up issue

## Routing Logic

```python
# api/routes/chat.py
def _should_use_unified_handler(session_id: str) -> bool:
    if not config.agent.use_unified_handler:
        return False  # hard off
    rollout = config.agent.unified_handler_rollout
    if rollout >= 1.0:
        return True
    if rollout <= 0.0:
        return False
    # Deterministic per-session: same session always gets same handler
    # (avoids users seeing inconsistent behavior across messages)
    bucket = hashlib.md5(session_id.encode()).digest()[0]  # 0–255
    return bucket < (rollout * 256)
```

The bucket-by-session-hash means a user's full conversation runs on one path — no half-and-half experiences.

## Telemetry Contract

Every chat request must log a `chat_routing` event with:
- `handler`: "unified" | "legacy"
- `bucket`: 0–255 (for distribution audit)
- `session_id`: hashed
- `intent`: detected intent
- `tokens_input`, `tokens_output`, `latency_ms`
- `guard_suppressions`: count (unified only, 0 for legacy)
- `fallback_triggered`: bool (unified path that errored and fell back)

## Tests First

Create `tests/test_ctx_guard_default.py`:

```python
"""Verify CTX guard is default + A/B rollout works correctly."""
import hashlib
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from api.app import create_app
from config import config
from services.unified_handler import UnifiedChatHandler
from services.ctx_pipeline import CTXQueryPipeline


# ── Config defaults ──

def test_unified_handler_is_default_in_config(monkeypatch):
    """SPEC_011: MZ_UNIFIED_HANDLER must default to true."""
    monkeypatch.delenv("MZ_UNIFIED_HANDLER", raising=False)
    from importlib import reload
    import config as config_module
    reload(config_module)
    assert config_module.config.agent.use_unified_handler is True


def test_rollout_defaults_to_full(monkeypatch):
    """SPEC_011: MZ_UNIFIED_HANDLER_ROLLOUT must default to 1.0."""
    monkeypatch.delenv("MZ_UNIFIED_HANDLER_ROLLOUT", raising=False)
    from importlib import reload
    import config as config_module
    reload(config_module)
    assert config_module.config.agent.unified_handler_rollout == 1.0


# ── Rollout routing ──

def test_routing_hard_off_when_disabled(monkeypatch):
    monkeypatch.setenv("MZ_UNIFIED_HANDLER", "false")
    monkeypatch.setenv("MZ_UNIFIED_HANDLER_ROLLOUT", "1.0")
    from importlib import reload
    import config as config_module
    reload(config_module)
    from api.routes.chat import _should_use_unified_handler
    assert _should_use_unified_handler("any-session") is False


def test_routing_full_rollout_routes_all_to_unified(monkeypatch):
    monkeypatch.setenv("MZ_UNIFIED_HANDLER", "true")
    monkeypatch.setenv("MZ_UNIFIED_HANDLER_ROLLOUT", "1.0")
    from importlib import reload
    import config as config_module
    reload(config_module)
    from api.routes.chat import _should_use_unified_handler
    for sid in ("a", "b", "c", "d"):
        assert _should_use_unified_handler(sid) is True


def test_routing_zero_rollout_routes_none(monkeypatch):
    monkeypatch.setenv("MZ_UNIFIED_HANDLER", "true")
    monkeypatch.setenv("MZ_UNIFIED_HANDLER_ROLLOUT", "0.0")
    from importlib import reload
    import config as config_module
    reload(config_module)
    from api.routes.chat import _should_use_unified_handler
    for sid in ("a", "b", "c", "d"):
        assert _should_use_unified_handler(sid) is False


def test_routing_50_percent_distribution(monkeypatch):
    """50% rollout should split traffic roughly 50/50 across many sessions."""
    monkeypatch.setenv("MZ_UNIFIED_HANDLER", "true")
    monkeypatch.setenv("MZ_UNIFIED_HANDLER_ROLLOUT", "0.5")
    from importlib import reload
    import config as config_module
    reload(config_module)
    from api.routes.chat import _should_use_unified_handler
    routed_unified = sum(
        1 for i in range(1000)
        if _should_use_unified_handler(f"session-{i}")
    )
    # Allow ±5% variance — md5 distribution is uniform but small samples vary
    assert 450 <= routed_unified <= 550, (
        f"Expected ~500 of 1000, got {routed_unified}"
    )


def test_routing_is_deterministic_per_session(monkeypatch):
    """Same session_id must always route the same way (no flapping mid-conversation)."""
    monkeypatch.setenv("MZ_UNIFIED_HANDLER", "true")
    monkeypatch.setenv("MZ_UNIFIED_HANDLER_ROLLOUT", "0.5")
    from importlib import reload
    import config as config_module
    reload(config_module)
    from api.routes.chat import _should_use_unified_handler
    sid = "user-abc-123"
    first = _should_use_unified_handler(sid)
    for _ in range(50):
        assert _should_use_unified_handler(sid) is first


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

### Step 1 — Flip the default + add rollout dial in `config.py`

Current at config.py:168:
```python
use_unified_handler: bool = os.getenv("MZ_UNIFIED_HANDLER", "false").lower() == "true"
```

Change to:
```python
use_unified_handler: bool = os.getenv("MZ_UNIFIED_HANDLER", "true").lower() == "true"
unified_handler_rollout: float = float(os.getenv("MZ_UNIFIED_HANDLER_ROLLOUT", "1.0"))
```

(The variable name `use_unified_handler` already exists — the SPEC originally said `unified_handler_enabled`. Use the existing name.)

### Step 2 — Add `_should_use_unified_handler()` in `api/routes/chat.py`

```python
import hashlib

def _should_use_unified_handler(session_id: str) -> bool:
    if not config.agent.use_unified_handler:
        return False
    rollout = config.agent.unified_handler_rollout
    if rollout >= 1.0:
        return True
    if rollout <= 0.0:
        return False
    bucket = hashlib.md5(session_id.encode()).digest()[0]
    return bucket < (rollout * 256)
```

### Step 3 — Wire routing into the chat route

Replace the existing `MZ_UNIFIED_HANDLER` check with `_should_use_unified_handler(session_id)`. Tag responses:

```python
use_unified = _should_use_unified_handler(session_id)
if use_unified:
    try:
        result = unified_handler.handle(query, session_id=session_id, ...)
        result["metadata"] = {**result.get("metadata", {}), "handler": "unified"}
        _log_chat_routing("unified", session_id, intent, result, fallback=False)
        return result
    except Exception as exc:
        logger.warning("UnifiedChatHandler failed, falling back: %s", exc)
        _log_chat_routing("unified", session_id, intent, None, fallback=True, error=str(exc))
        # fall through to legacy below
result = legacy_handle(query, ...)
result["metadata"] = {**result.get("metadata", {}), "handler": "legacy"}
_log_chat_routing("legacy", session_id, intent, result, fallback=False)
return result
```

### Step 4 — Add `_log_chat_routing()` helper

Logs to existing telemetry with structured fields per the Telemetry Contract above. Reuse `log_ctx_event` infrastructure with `event_type="chat_routing"`.

### Step 5 — Add guard suppression telemetry

In `services/ctx_pipeline.py::check_response`, when `suppressed` is non-empty:

```python
log_ctx_event(
    event_type="guard_suppression",
    metadata={
        "suppressed_count": len(suppressed),
        "suppressed_ids": list(suppressed)[:10],  # cap for log size
    },
)
```

### Step 6 — A/B observation dashboard (deferred PR)

Add a `/metrics/ab-summary` endpoint that returns side-by-side stats for `handler="unified"` vs `handler="legacy"` over a configurable window. Useful but not blocking — can ship via direct SQL queries during the 48h observation window.

## Acceptance Criteria

**Code:**
- [ ] All tests in `tests/test_ctx_guard_default.py` pass
- [ ] Existing chat tests do not regress (1100+ baseline)
- [ ] Both env vars work: `MZ_UNIFIED_HANDLER` (true/false), `MZ_UNIFIED_HANDLER_ROLLOUT` (0.0-1.0)
- [ ] Routing is deterministic per session_id (same session → same handler)

**Production (after deploy):**
- [ ] Initial state: `MZ_UNIFIED_HANDLER=true`, `MZ_UNIFIED_HANDLER_ROLLOUT=0.5` (50% A/B)
- [ ] Chat queries return 200 — no 500s
- [ ] Response metadata includes `"handler": "unified"` or `"handler": "legacy"`
- [ ] `chat_routing` telemetry events show ~50/50 distribution

**A/B observation (48h window after rollout):**
- [ ] `unified` fallback rate < 5% (tells us the unified path is robust)
- [ ] `unified` p95 latency within 1.5x of `legacy` (corpus loading shouldn't tank UX)
- [ ] `guard_suppression` events appear (proves the guard catches real hallucinations)
- [ ] Token cost per query: `unified` should be ≤ 1.3x of `legacy` despite the corpus inclusion (CTX compression should net it out)
- [ ] Benchmark `ci_eval` ≥75% under both handlers

**Promotion decision (after 48h):**
- [ ] If acceptance criteria met → set `MZ_UNIFIED_HANDLER_ROLLOUT=1.0` (100% unified)
- [ ] If not → set `MZ_UNIFIED_HANDLER_ROLLOUT=0.0`, file follow-up issue

## Rollout / Rollback

**Rollout (staged):**
1. Local test suite passes
2. Deploy to Railway with code changes
3. Set Railway env: `MZ_UNIFIED_HANDLER=true`, `MZ_UNIFIED_HANDLER_ROLLOUT=0.5`
4. Smoke test: 5 manual queries, verify both handlers shown in response metadata across attempts
5. Monitor `/metrics/ctx-telemetry` for 4 hours — confirm events flowing for both paths
6. Continue 48h observation
7. Promote to `ROLLOUT=1.0` if criteria met

**Rollback (instant):**
- `MZ_UNIFIED_HANDLER_ROLLOUT=0.0` → all traffic to legacy immediately
- Or `MZ_UNIFIED_HANDLER=false` → hard kill switch
- Both effective on next request, no code redeploy needed

## Out of Scope

- Improving CTX retrieval quality itself (separate work — this spec is about wiring, not algorithm improvements)
- Removing the legacy 8-handler fork (deferred until fallback rate stays at 0% for 30 days)
- Adding new CTX guard rules (current rule set is sufficient — citation marker validation)
