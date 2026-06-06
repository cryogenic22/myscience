"""C1 (learning loops) — LLMSynthesizer routes every production call through
llm_call_log when a DB handle is injected.

Closes the gateway-bypass gap: chat synthesis previously hit OpenAI directly,
so llm_call_log under-counted real LLM usage (~26 logged vs ~78 queries).
These tests prove a row is written on success AND failure, and that the
DB-free path (db=None) is unchanged (no logging, no error).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from services.llm import LLMSynthesizer


def _make_config():
    """Minimal config shaped like AppConfig.llm that enables the synthesizer."""
    return SimpleNamespace(
        llm=SimpleNamespace(
            enabled=True,
            api_key="sk-test",
            model="gpt-4o-mini",
            fallback_model="gpt-4o-mini",
            max_tokens=400,
            temperature=0.2,
            ctx_mode="ctx",
        )
    )


class _FakeChoice:
    def __init__(self, text):
        self.message = SimpleNamespace(content=text)


class _FakeCompletions:
    def __init__(self, reply, raise_exc=None):
        self._reply = reply
        self._raise = raise_exc

    def create(self, **kwargs):
        if self._raise is not None:
            raise self._raise
        return SimpleNamespace(choices=[_FakeChoice(self._reply)])


class _FakeClient:
    def __init__(self, reply="A synthesized narrative.", raise_exc=None):
        self.chat = SimpleNamespace(completions=_FakeCompletions(reply, raise_exc))


def _synth_with_client(db, reply="A synthesized narrative.", raise_exc=None):
    llm = LLMSynthesizer(_make_config(), db=db)
    llm._client = _FakeClient(reply=reply, raise_exc=raise_exc)
    return llm


def test_synthesize_logs_a_call_row():
    db = MagicMock()
    llm = _synth_with_client(db)
    out = llm.synthesize(question="What is X?", intent="general")
    assert out  # narrative returned
    assert db.execute.called
    sql = db.execute.call_args[0][0].lower()
    assert "insert into llm_call_log" in sql
    # caller carries the intent so we can attribute by surface later
    params = db.execute.call_args[0][1]
    assert any("llm.synthesize" in str(p) for p in params)


def test_raw_chat_logs_a_call_row():
    db = MagicMock()
    llm = _synth_with_client(db, reply="raw reply")
    out = llm.raw_chat(system="sys", user="hi")
    assert out == "raw reply"
    assert db.execute.called
    sql = db.execute.call_args[0][0].lower()
    assert "insert into llm_call_log" in sql


def test_failed_synthesis_still_logs_with_succeeded_false():
    db = MagicMock()
    llm = _synth_with_client(db, raise_exc=RuntimeError("boom"))
    out = llm.synthesize(
        question="q", intent="general", fallback_narrative="fallback",
    )
    assert out == "fallback"
    assert db.execute.called  # failure path logs too
    sql = db.execute.call_args[0][0].lower()
    assert "insert into llm_call_log" in sql


def test_no_db_means_no_logging_and_no_error():
    """DB-free path (db=None) must behave exactly as before — no log call,
    no exception (preserves the many DB-free unit tests that mock LLMs)."""
    llm = _synth_with_client(db=None)
    out = llm.synthesize(question="q", intent="general")
    assert out  # still returns a narrative


def test_logging_failure_does_not_break_synthesis():
    """A telemetry insert failure must never break the response."""
    db = MagicMock()
    db.execute.side_effect = RuntimeError("db down")
    llm = _synth_with_client(db)
    out = llm.synthesize(question="q", intent="general")
    assert out  # narrative still returned despite log failure


# ════════════════════════════════════════════════════════════════════
# C1 depth — prompt-versioned synthesis (llm_call_log.prompt_id)
# ════════════════════════════════════════════════════════════════════

# A stable UUID the fake registry hands back; the synthesis log row must
# carry it as prompt_id.
_FAKE_PROMPT_ID = "11111111-2222-3333-4444-555555555555"


class _FakeRegistryDB:
    """Fake DB whose fetch_one mimics PromptRegistry.get_latest by returning a
    registered synthesis prompt row, and records execute() calls so we can
    assert the prompt_id lands in the llm_call_log insert.

    Substring matching is on `from prompt_registry` (a stable, unambiguous
    fragment present in every registry SELECT) — NOT a brittle full-clause
    match.
    """

    def __init__(self):
        self.executes: list = []

    def fetch_one(self, sql, params=None):
        s = " ".join(sql.lower().split())
        if "from prompt_registry" in s:
            return {
                "prompt_id": _FAKE_PROMPT_ID,
                "name": "synthesis.default",
                "version": 1,
                "content": "x",
                "content_hash": b"\x00",
                "purpose": None,
                "model_pref": None,
                "max_tokens": None,
                "created_by_user_id": None,
                "created_at": None,
            }
        return None

    def execute(self, sql, params=None):
        self.executes.append((sql, params))


def _last_insert(db: _FakeRegistryDB):
    for sql, params in reversed(db.executes):
        if "insert into llm_call_log" in sql.lower():
            return sql, params
    return None, None


def test_synthesize_logs_non_null_prompt_id():
    """The success path resolves a prompt_id from the registry and persists it
    in the llm_call_log row (the C1-depth gate, in unit form)."""
    from services.llm import _SYNTHESIS_PROMPT_ID_CACHE
    _SYNTHESIS_PROMPT_ID_CACHE.clear()
    db = _FakeRegistryDB()
    llm = _synth_with_client(db)
    out = llm.synthesize(question="What is X?", intent="default")
    assert out
    sql, params = _last_insert(db)
    assert sql is not None
    assert "prompt_id" in sql.lower()
    assert _FAKE_PROMPT_ID in [str(p) for p in (params or [])]


def test_resolve_synthesis_prompt_id_uses_registry():
    from services.llm import _resolve_synthesis_prompt_id, _SYNTHESIS_PROMPT_ID_CACHE
    _SYNTHESIS_PROMPT_ID_CACHE.clear()
    db = _FakeRegistryDB()
    pid = _resolve_synthesis_prompt_id(db, "dossier")
    assert pid == _FAKE_PROMPT_ID
    # None db → None (DB-free path unchanged)
    assert _resolve_synthesis_prompt_id(None, "dossier") is None
