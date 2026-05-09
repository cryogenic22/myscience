# UI Changelog

Append-only log of every frontend surface change. **Antigravity writes; Claude
reads at the start of every session.**

Format per entry: `## YYYY-MM-DD` then sections `### Surfaces`,
`### New components`, `### Backend dependencies` (link to API_CHANGELOG entries
this depends on), `### Open issues`. Omit empty sections.

Screenshots of material visual changes live under `docs/screenshots/`.

---

## 2026-05-09

### Surfaces
- **AGENTS.md protocol adopted.** All UI changes from this date forward will
  be logged here.

### Backend dependencies
- See `docs/API_CHANGELOG.md` for the corresponding entry.

### Open issues
- **InboxTab login wall** (filed in `docs/AGENT_BACKLOG.md`). First PR target
  for Antigravity to validate the workflow end-to-end. (RESOLVED)

## 2026-05-09 (Inbox Login Wall Fix)

### Surfaces
- **CIPage**: Default tab for unauthenticated users is now `digest` (which works without auth).
- **InboxTab**: Replaced the login-wall message with a real login CTA + button that routes to `/login`.

## 2026-05-09 (Phase 1 Cockpit Primitives)

### New components
- `MetricRing`: SVG progress indicator with semantic thresholds.
- `Sparkline`: Minimalist SVG line chart for trend visualization.
- `HeroCard`: Elevated component wrapper using Phase F shadows.
- `Timeline`: Vertical chronological list with `framer-motion`.
- `AgentStatusBar`: Live telemetry ticker indicating agent loops.

### Surfaces
- `index.css`: Added Phase F dark theme tokens (`#0d1117`, `#161b22`, etc.) and `Syne` / `DM Mono` typography.


