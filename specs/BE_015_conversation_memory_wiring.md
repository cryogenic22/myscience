# BE-15 — Wire ConversationMemory + surface coreference resolution

> Filed in `docs/AGENT_BACKLOG.md#be-15`. Loop opened 2026-05-10.
> Branch: `claude/be-015-wire-conversation-memory`.

## 1 · Where things stood

Investigation found that the frontend-side wiring was already mostly
in place — `api/routes/chat.py` already:

- accepts `session_id` from the chat body,
- resolves a `ConversationMemory` instance via
  `get_conversation_memory(session_id)`,
- feeds `memory.get_context()` into prompt assembly,
- calls `memory.resolve_reference(question)` for follow-up
  resolution,
- saves memory back via `save_conversation_memory(...)` after each
  handler.

What the **acceptance criteria** still required (BE-15):

> backend response includes `coreference_resolution: { "this drug":
> "tirzepatide", from_turn: 1 }` so frontend can render branch
> indicator under user messages.

That field did not exist anywhere — `resolve_reference` returned only
the rewritten string, no map of which phrase resolved to what.

## 2 · Design

### `ConversationMemory.resolve_reference_with_map`

New method that returns `(resolved_question, coreference_map)`. The
map shape matches the BE-15 spec exactly:

```python
{
    "<original phrase>": "<resolved entity>",
    ...,
    "from_turn": <int 1-based source turn index>,
}
```

Empty dict when no substitution happened (so the chat response can
omit the field rather than carrying a useless empty object).

The legacy `resolve_reference(question) -> str` keeps its signature
so any non-chat caller keeps working.

### Chat endpoint

`api/routes/chat.py` now calls
`memory.resolve_reference_with_map(...)` instead of
`memory.resolve_reference(...)`, captures the map, and splices it
into the response payload at every successful return path:

- unified handler return,
- compound-intent return,
- the main legacy-handler return.

The map is **omitted** on error responses (no need to leak
half-resolved state into a failure payload).

## 3 · Acceptance

- [x] `resolve_reference_with_map` exists and returns the spec-shaped
      tuple.
- [x] `from_turn` reflects the most-recent-with-an-entity source
      turn (1-based, matches `_Exchange.turn`).
- [x] Empty map when no substitution; non-empty + `from_turn` when
      one or more demonstratives resolved.
- [x] Chat response payload surfaces `coreference_resolution` only
      when populated.
- [x] Legacy `resolve_reference` signature preserved (back-compat).
