# Preservation — H0.1 (2026-08-13)

Robust preservation of all local-only work **before** any H0.2 cleanup, per the owner's
hardening requirement ("binary staged/unstaged patches, a hashed untracked-file archive,
required Git bundles, and a **tested restore** — not a patch alone").

## Location

Preservation binaries live **out of the repository** (they are backups, not source):

```
C:/Users/kapil/Documents/mz-handoff-preservation/
├── bundles/                 # 13 thin Git bundles (local-only branches)
└── worktrees/<name>/        # per dirty worktree: staged.patch · unstaged.patch · untracked.tgz
```

Only the **manifest** ([`PRESERVATION_MANIFEST.csv`](PRESERVATION_MANIFEST.csv), full SHA-256)
is committed to the repo. Total size ≈ 665 KB. *Off-machine backup of this directory is a
separate concern (H2/H6 backup runbook) — this set protects against the H0.2 branch/worktree
prune, given `origin/main` remains on GitHub.*

## What is preserved

| Set | Count | Artifact |
|---|---|---|
| **Local-only branches** (unique commits on **no** remote) | 13 | thin `*.bundle` (`--not origin/main`; prereq = `origin/main@31d923a`, durable on GitHub) |
| **Dirty worktrees** | 29 | `staged.patch` + `unstaged.patch` (`git diff --binary`) + `untracked.tgz` (untracked files, `--exclude-standard`) |

The **202 merged** branches carry 0 unique commits (nothing to preserve). The **57 on-origin/no-PR**
and **36 on-origin/PR** branches are already preserved on the remote — no local bundle required.
The main checkout's untracked pile is captured by full SHA-256 in `UNTRACKED_ARTIFACT_MANIFEST.csv`
(its `.claude/ctx` session-memory is **PROTECT** and deliberately **not** archived into a tarball).

## Restore recipe

**A branch from a thin bundle** (into any clone that has `origin/main`):
```bash
git init --bare recover.git
git -C recover.git fetch <clone-with-origin/main> refs/remotes/origin/main:refs/heads/base
git -C recover.git fetch bundles/<branch>.bundle <branch>:refs/heads/restored
git -C recover.git rev-parse restored     # == the recorded tip
```

**A dirty worktree's working changes** (onto a clean checkout of its base commit):
```bash
git worktree add --detach ../recover-wt <base-sha>
git -C ../recover-wt apply --binary worktrees/<name>/staged.patch     # if non-empty
git -C ../recover-wt apply --binary worktrees/<name>/unstaged.patch
tar -xzf worktrees/<name>/untracked.tgz -C ../recover-wt              # untracked files
```

## Tested restore — evidence (2026-08-13)

**Bundle restore (isolated)** — `claude/data/c1-orphan-floor`, tip `4e926db`:
```
unique commit present BEFORE bundle fetch : ABSENT
bundle verify                             : OK
unique commit present AFTER  bundle fetch : PRESENT
restored tip == expected tip              : YES ✓ (4e926db36cf888f1b7016e5fae84875af361939f)
restored commit: 4e926db fix(data): C1 — clear pubmed FK-orphan RED + durable self-healing relink
```

**Binary patch re-apply (clean base)** — worktree `agent-a681a13b`, `unstaged.patch` (803 B):
```
base commit: a64125d3...
git apply --check --binary : APPLIES CLEANLY
after apply                : M frontend/src/App.tsx
```

Both preservation mechanisms are proven recoverable end-to-end — not patches alone.
