# Preservation — H0.1 (v2, corrected 2026-08-13)

Robust preservation of all local-only work **before** any H0.2 cleanup, per the owner's
hardening requirement ("binary staged/unstaged patches, a hashed untracked-file archive,
required Git bundles, and a **tested restore** — not a patch alone").

> **v2 correction:** the first pass used `git status --untracked-files=no`, so untracked-only
> content was invisible, and a `C:`-drive GNU-tar remote-host bug silently produced **0**
> `untracked.tgz` archives. Both fixed: full `--untracked-files=all` census + `tar --force-local`.
> Every archive is now created, entry-counted, and hashed.

## Location

Preservation binaries live **out of the repository** (backups, not source):
```
C:/Users/kapil/Documents/mz-handoff-preservation/
├── bundles/                 # 13 thin Git bundles (local-only branches)
└── worktrees/<name>/        # per dirty worktree: staged.patch · unstaged.patch · untracked.tgz
```
Only [`PRESERVATION_MANIFEST.csv`](PRESERVATION_MANIFEST.csv) (exact paths + full SHA-256) is
committed. *Off-machine backup of this dir is a separate concern (H2/H6 runbook); this set
protects against the H0.2 branch/worktree prune, given `origin/main` stays on GitHub.*

## What is preserved

| Set | Count | Artifact |
|---|---|---|
| **Local-only branches** (unique commits on **no** remote) | 13 | thin `*.bundle` (`--not origin/main`; prereq `origin/main@31d923a`) |
| **Dirty worktrees** (tracked-mod and/or untracked) | 42 | `staged.patch` (2) + `unstaged.patch` (26) — `git diff --binary` |
| **…of which with untracked content** | 33 | `untracked.tgz` (`--force-local`, `--exclude-standard`) — **90 entries total**, each archive hashed |

The **8 merged + truly-clean** worktrees carry nothing to preserve (Category B prune). The main
checkout's 96 untracked files are captured per-file (full SHA-256) in
`UNTRACKED_ARTIFACT_MANIFEST.csv`; its `.claude/ctx` session memory is **PROTECT** and deliberately
**excluded** from any tarball.

## Restore recipe

**Branch from a thin bundle** (into any clone with `origin/main`):
```bash
git init --bare recover.git
git -C recover.git fetch <clone-with-origin/main> refs/remotes/origin/main:refs/heads/base
git -C recover.git fetch bundles/<branch>.bundle <branch>:refs/heads/restored
```
**Dirty worktree — patch + untracked archive** (onto a clean checkout of its base commit):
```bash
git worktree add --detach ../recover-wt <base-sha>
git -C ../recover-wt apply --binary worktrees/<name>/staged.patch     # if present
git -C ../recover-wt apply --binary worktrees/<name>/unstaged.patch
tar --force-local -xzf worktrees/<name>/untracked.tgz -C ../recover-wt
```

## Tested restore — evidence (2026-08-13)

**1) Bundle (isolated)** — `claude/data/c1-orphan-floor`, tip `4e926db`:
```
unique commit present BEFORE : ABSENT
bundle verify                : OK
unique commit present AFTER  : PRESENT
restored tip == expected     : YES ✓ (4e926db36cf888f1b7016e5fae84875af361939f)
```

**2) Patch + archive (clean base)** — worktree `agent-a681a13b`, base `a64125d3`,
`unstaged.patch` (803 B) + `untracked.tgz` (10 entries):
```
git apply --check --binary unstaged.patch : OK
after patch                               : M frontend/src/App.tsx     (tracked change restored)
tar --force-local -xzf untracked.tgz      : extracted
restored untracked file on disk           : frontend/src/newui.css  ✓
```

All three mechanisms (bundle · patch · untracked archive) are proven recoverable end-to-end.
