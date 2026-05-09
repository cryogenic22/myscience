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

## 2026-05-09 (Phase 2-4 Cockpit Primitives)

### New components
- `ConfidenceBadge`: A primitive to display explicit uncertainty bands and scores.
- `EvidenceAffordance`: A primitive to render deep-linkable evidence chains with source/passage visibility.
- `DisagreementPanel`: A surface for side-by-side agent/source conflict resolution.

### Surfaces
- **Sensing Feed**: Implemented `SensingFeed` as the new Always-On continuous feed.
- **InboxTab**: Replaced the default layout entirely with `SensingFeed`.

## 2026-05-09 (SPEC-023 Sign-off & Main Shell Upgrade)

### Surfaces
- **LandingPage**: Full visual overhaul using Phase F Cockpit design. Added dark glassmorphic components, `AgentStatusBar` telemetry, and dynamic background.
- **CIPage**: Redesigned the main application shell. Replaced horizontal topbar with a dark high-density sidebar. Added global agent telemetry monitoring the Flywheel.

### Cross-Cutting
- Signed off `SPEC_023_decision_briefs.md` for the backend data contract.
