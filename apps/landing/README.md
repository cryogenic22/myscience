# @pulse/landing — Mission Control

The platform's first screen. Module switcher + platform health + cross-module recent activity + ⌘K command palette.

## Develop

```bash
pnpm install
pnpm --filter @pulse/landing dev   # http://localhost:5173
```

## Status

**Phase 0 / M0 skeleton.** Data is mocked. Wiring to platform APIs lands in Phase 1 sprint C1:

- `GET /catalog/health` → catalog freshness tile
- `GET /intel/health` → signals/guard tiles
- `GET /platform/recent-activity` → cross-module timeline
- `GET /platform/me/modules` → module access RBAC
- `GET /platform/budget` → LLM spend tile

## Architecture

This app is a thin SPA. It does not own data. It consumes platform APIs and routes the user to the chosen module. See SPEC-016 §3.
