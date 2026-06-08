# `docs/archive/` — superseded markdown documents

Historical / superseded `.md` files moved here on **2026-05-09** as part
of [SPEC-042](../../specs/SPEC_042_centralized_product_backlog.md).
Originals are preserved (with content unchanged) so `git log -- <path>`
and `grep -r` against this tree still surface historical context.

A 1-line redirect header was inserted at each file's *original* path
pointing readers to the canonical replacement.

| Subdirectory | What lives here |
|---|---|
| `brainstorms/` | Pre-Phase-F vision rough drafts (Feb–Mar 2026) |
| `communications/` | Internal lead/dev notes that have since been folded into specs |
| `reports/` | One-time test / analysis reports (single-snapshot, not living docs) |
| `benchmarks/` | Auto-generated benchmark eval reports from Mar 2026 |
| `superseded-specs/` | Specs SPEC_001–SPEC_018 superseded by the SPEC-021+ series. Plus drafts (HARNESS_AUDIT, SESSION_REPORT, EXECUTION_PLAN, etc.) |
| `legacy-backlogs/` | The four files SPEC-042 replaced with `docs/PRODUCT_BACKLOG.md` |

### Added 2026-06-08
- `AGENT_BACKLOG.md` — the old cross-agent board (last live 2026-05-11). It
  assumed one backend + one frontend agent and had no convention for two
  concurrent backend sessions, which caused a real collision (a MeSH fix swept
  into an unrelated PR, #190). **Superseded by `docs/COORDINATION.md`.** A
  redirect stub remains at `docs/AGENT_BACKLOG.md`.

If you need to revive an archived doc, copy it back to its original
path and delete the redirect header. Or, more usefully, file a
`PB-NNN` row in `docs/PRODUCT_BACKLOG.md` capturing what's live now
and reference the archived source there.
