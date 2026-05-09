✓ Signed off by Claude
Pending sign-off by Antigravity (Cost dashboard is a frontend deliverable that consumes this)

# SPEC_026: LLM Gateway + Prompt Registry

## Goal
Promote the existing `services/llm_telemetry.chat_with_telemetry` into a
proper LLM Gateway with three guarantees:

1. **Versioned, addressable prompts.** Every prompt used in production is
   registered, has a stable `prompt_id`, and each call's `llm_call_log`
   row references that `prompt_id`. The Learning Service (SPEC-028) can
   then attribute prediction accuracy to specific prompt versions.
2. **PII filter.** Outbound prompts are scanned for emails, SSNs, phones,
   and credit-card-shaped strings. Detected PII is redacted (or the call
   rejected, depending on policy).
3. **Cost visibility.** A cost-summary endpoint aggregates `llm_call_log`
   so the user can see "how much have we spent on the war-game suggester
   in the last 7 days?" without writing SQL.

Per `specs/CI_Agent_Reimagined_Spec.md` §10.3: "non-negotiable" for cost
visibility, prompt versioning, provider portability, and PII safety.

## Why now (and what's deliberately out of scope)
This loop ships the registry + PII filter + cost endpoint. **Out of scope
for this loop** (deferred to follow-up):
- Provider abstraction beyond OpenAI (Anthropic, etc.) — current stack
  uses a single provider; multi-provider routing is premature
- Streaming variants
- Per-prompt budget caps (handled today by SPEC-021 D2 rate limiter; can
  layer prompt-level caps later)
- Migration of every existing caller to use the registry. Existing
  `chat_with_telemetry` calls keep working — they log with the old
  `prompt_version` string and `prompt_id` is null. Gateway invocation
  is opt-in until callers are migrated.

## Data contract

### Table: `prompt_registry`
| Column | Type | Notes |
|---|---|---|
| `prompt_id` | UUID PK | gen_random_uuid() |
| `name` | TEXT NOT NULL | Caller-facing identifier (`war_game.competitor_react`) |
| `version` | INTEGER NOT NULL | Auto-incremented per name on register-with-changed-content |
| `content` | TEXT NOT NULL | Mustache-style template (`Reply to {{question}}`) |
| `content_hash` | BYTEA NOT NULL | SHA-256 of `content` for dedup |
| `purpose` | TEXT | Free-form description (renders in admin UI) |
| `model_pref` | TEXT | Optional preferred model (`gpt-4o`, `gpt-4o-mini`) |
| `max_tokens` | INTEGER | Optional budget |
| `created_by_user_id` | UUID | Who registered |
| `created_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW() |

UNIQUE on `(name, version)` + UNIQUE on `(name, content_hash)` (idempotent
re-register: same name + same content → same row, returns 200).

### Augmentation to `llm_call_log` (existing from SPEC-021 D2)
Add nullable `prompt_id UUID` column referencing `prompt_registry(prompt_id)`.
NULL for legacy callers that haven't migrated to the gateway. Existing
`prompt_version` TEXT column stays (back-compat).

## API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/llm-gateway/prompts` | Register prompt (uploader+); idempotent on `(name, content_hash)` |
| GET | `/llm-gateway/prompts` | List prompts, optional `name` filter (viewer+) |
| GET | `/llm-gateway/prompts/{prompt_id}` | Get one prompt (viewer+) |
| POST | `/llm-gateway/invoke` | Invoke a registered prompt (uploader+) |
| POST | `/llm-gateway/scan-pii` | Public PII scanning (uploader+) |
| GET | `/llm-gateway/cost-summary` | Cost aggregation over date range (viewer+) |

### Invoke contract
```json
POST /llm-gateway/invoke
{
  "prompt": "war_game.competitor_react",   // name OR prompt_id
  "variables": {"competitor": "Pfizer", "option": "accelerate readout"},
  "user_message": "specific user-supplied context...",
  "model_pref": "gpt-4o",                  // optional override
  "pii_policy": "redact"                   // "redact" | "reject" | "allow"
}

→ 200 OK
{
  "response": "...",
  "prompt_id": "uuid",
  "model_used": "gpt-4o",
  "latency_ms": 1234,
  "prompt_tokens": 250,
  "completion_tokens": 800,
  "cost_estimate_usd": 0.0123,
  "pii_redactions": [
    {"kind": "email", "redacted": "[EMAIL]", "original_length": 18}
  ]
}
```

### Cost summary contract
```json
GET /llm-gateway/cost-summary?since=2026-05-01&until=2026-05-09&group_by=caller

→ 200 OK
{
  "since": "2026-05-01",
  "until": "2026-05-09",
  "group_by": "caller",
  "total_usd": 12.47,
  "total_calls": 3421,
  "buckets": [
    {"key": "war_game_engine", "calls": 1230, "total_usd": 8.20, "avg_latency_ms": 1820},
    {"key": "move_suggester",  "calls": 980,  "total_usd": 2.10, "avg_latency_ms": 1450},
    ...
  ]
}
```

`group_by` ∈ `caller | model | day | user` (default `caller`).

## PII patterns (initial regex set)

| Kind | Pattern | Example |
|---|---|---|
| `email` | `[\w._%+-]+@[\w.-]+\.[A-Za-z]{2,}` | `kapil@example.com` |
| `ssn` | `\b\d{3}-\d{2}-\d{4}\b` | `123-45-6789` |
| `phone_us` | `\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b` | `(415) 555-0100` |
| `credit_card` | `\b(?:\d[ -]*?){13,19}\b` (then Luhn check) | `4111 1111 1111 1111` |

Future additions (deferred): passport numbers, NPI, date-of-birth.

## Template substitution

Mustache-style `{{var}}` substitution. **Hard rule**: variable values are
inserted verbatim — they are NOT re-interpreted as templates. This blocks
template-injection: a user-supplied `{{variable}}` value that itself
contains `{{system_prompt}}` is rendered as the literal string, not
expanded recursively.

Missing variables → 400 with the missing-key list (no silent empty-string
substitution that could let a malicious caller exploit a missing field).

## Red-team

| # | Vector | Mitigation |
|---|---|---|
| R1 | Template injection via `variables` | Single-pass substitution; values are not re-rendered |
| R2 | PII bypass via base64 / homoglyphs | Out of scope — initial filter is regex; adding NLP-level scanning later |
| R3 | Prompt-id enumeration | UUID v4; not enumerable |
| R4 | Cost-bypass via huge `variables` | Per-call `max_tokens` cap from prompt registry; can't be overridden at invoke unless explicit param |
| R5 | SQL injection via `name` filter | Parameterized; name filter ILIKE is parameterized too |
| R6 | Replay/idempotency on register | UNIQUE on (name, content_hash) means re-registering same content is a no-op |
| R7 | DoS via massive content | Cap content at 32 KB at registration |
| R8 | Privilege escalation by registering "system" prompts | All prompts are equal at the data layer; only admin/uploader can register |
| R9 | PII in extracted_text leaks to evidence ledger | Out of scope here; ledger PII handling is its own concern |
| R10 | Cost-summary leaks per-user data to viewer role | Aggregation only; no user_id in default response unless `group_by=user` |

## Success criteria
- [ ] Migration 054 applies; back-compat with existing llm_call_log rows
- [ ] Registering same `(name, content)` twice returns same prompt_id (idempotent)
- [ ] Registering same `name` with different content increments `version`
- [ ] PII filter detects email/SSN/phone/credit-card; Luhn-validates cards
- [ ] Template substitution refuses missing variables (400)
- [ ] Template substitution does NOT recursively expand variable values
- [ ] Cost summary correctly aggregates over date range
- [ ] Auth: register requires uploader+; cost-summary visible to viewer+
- [ ] Full test suite green; no regressions

## Out of scope (for follow-up specs)
- Provider abstraction (Anthropic, etc.)
- Per-prompt budget enforcement (D2 rate limit suffices today)
- Prompt A/B testing harness (Phase H)
- Per-prompt accuracy attribution (rolls into SPEC-028 Learning Service)
