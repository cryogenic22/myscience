"""WP-12C — LLM/provider egress scanner (alias-resolving, terminal-complete, fail-closed).

Supersedes the first-pass scanner in tests/test_priv001b_egress_inventory.py, which
substring-matched provider call chains and could be defeated by an intermediate variable.
This scanner is hardened against the bypass classes an independent review demonstrated the
earlier redesign still missed:

  1. **Callable alias.**   f = client.chat.completions.create ; f(...)
  2. **Non-.create terminals.**  client.chat.completions.stream(...) / .parse(...)
  3. **Direct provider HTTP.**   requests.post("https://api.openai.com/v1/chat/completions", ...)
  4. **Intermediate-variable receiver.**  c = client.chat.completions ; c.create(...)
  5. **Collapsed identity.** two egress calls in one function, or a same-named method in two
     classes, previously collapsed to ONE inventory key — so one could be added/removed
     silently. Identity is now (relpath, qualified-scope, kind, source-ordinal): unique per
     call site AND stable across line edits (line/col are carried as reporting metadata, not
     as the pinned key — a line-number key would make the inventory break on every refactor,
     which trains reviewers to ignore it: exactly the failure mode conservation-gates warns of).

A security gate that cannot fail on a real bypass is a vacuous gate (conservation principle
#3); tests/test_wp12c_egress_mutation.py proves each class above turns the scanner RED.

Importable so both the assurance gate and PRIV-001b consume ONE scanner, not two.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

# Provider egress chains we treat as raw SDK calls when they terminate in a provider method.
# chat.completions/responses/embeddings = OpenAI; messages = Anthropic.
PROVIDER_CHAINS = ("chat.completions", "responses", "embeddings", "messages")

# Terminal SDK methods that actually send a request. .create WAS the only one detected; the
# review showed .stream / .parse (and their async twins) are equally live egress.
TERMINAL_METHODS = frozenset({
    "create", "acreate", "stream", "astream", "parse", "aparse",
})

# Direct-HTTP egress: a provider endpoint literal passed to an HTTP verb defeats SDK-chain
# detection entirely. Match the host / path markers, resolved through simple str constants.
PROVIDER_URL_MARKERS = (
    "api.openai.com", "api.anthropic.com", "openai.azure.com",
    "/v1/chat/completions", "/v1/messages", "/v1/embeddings", "/v1/responses",
)
HTTP_VERBS = frozenset({"post", "put", "patch", "request", "send", "stream"})

# Only genuinely non-production trees are skipped. apps/ and packages/ are NOT skipped so a
# future .py egress there is caught (fail-closed). tests/ and assurance/ are skipped because
# they carry SYNTHETIC provider calls as fixtures/tooling, not runtime egress; the production
# -directory mutation test guards that this list can never grow to hide a real runtime dir.
DEFAULT_SKIP_DIRS = {
    ".git", "node_modules", "frontend", ".claude", "venv", ".venv", "dist", "build",
    "__pycache__", ".pytest_cache", "tests", "assurance", ".mypy_cache", ".ruff_cache",
    "site-packages", ".egg-info",
}


@dataclass(frozen=True)
class Hit:
    relpath: str
    scope: str        # qualified enclosing scope, e.g. "ExtractionLLM.call" or "<module>"
    kind: str         # chat | responses | embeddings | messages | http
    ordinal: int      # 0-based index among (relpath, scope, kind) in source order
    lineno: int       # reporting metadata (NOT part of the identity key — see module docstring)
    col: int          # reporting metadata

    def key(self) -> str:
        # Identity = scope + kind + ordinal. Unique per call site; stable across line edits.
        return f"{self.relpath}::{self.scope}::{self.kind}#{self.ordinal}"

    def location(self) -> str:
        return f"{self.relpath}:{self.lineno}:{self.col}"


def _kind(chain: str) -> str:
    if "chat.completions" in chain:
        return "chat"
    if "embeddings" in chain:
        return "embeddings"
    if "responses" in chain:
        return "responses"
    if "messages" in chain:
        return "messages"
    return "other"


class _Scanner(ast.NodeVisitor):
    """Detect provider egress: SDK-chain terminal calls (incl. callable aliases) and direct
    provider-HTTP calls. Resolves per-scope local aliases (attribute chains AND str consts)."""

    def __init__(self) -> None:
        self.scope_stack: list[str] = ["<module>"]
        self.alias_stack: list[dict[str, str]] = [{}]       # name -> resolved dotted chain
        self.str_alias_stack: list[dict[str, str]] = [{}]   # name -> str constant value
        self.raw: list[tuple[str, str, int, int]] = []      # (scope, kind, lineno, col)

    # --- scope handling: inner scopes inherit outer aliases (module-level client, etc.) ---
    def _push(self, name: str) -> None:
        self.scope_stack.append(name)
        self.alias_stack.append(dict(self.alias_stack[-1]))
        self.str_alias_stack.append(dict(self.str_alias_stack[-1]))

    def _pop(self) -> None:
        self.scope_stack.pop()
        self.alias_stack.pop()
        self.str_alias_stack.pop()

    def visit_FunctionDef(self, n: ast.AST) -> None:
        self._push(n.name)
        self.generic_visit(n)
        self._pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, n: ast.ClassDef) -> None:
        self._push(n.name)
        self.generic_visit(n)
        self._pop()

    def _qualscope(self) -> str:
        inner = ".".join(self.scope_stack[1:])
        return inner or "<module>"

    def _resolve(self, name: str) -> str:
        for scope in reversed(self.alias_stack):
            if name in scope:
                return scope[name]
        return name

    def _resolve_str(self, name: str) -> str | None:
        for scope in reversed(self.str_alias_stack):
            if name in scope:
                return scope[name]
        return None

    def _chain_of(self, node: ast.AST) -> str | None:
        """Resolved dotted chain for an attribute/name expr; None if the base is not a Name."""
        attrs: list[str] = []
        while isinstance(node, ast.Attribute):
            attrs.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            base = self._resolve(node.id)
            tail = ".".join(reversed(attrs))
            return base + ("." + tail if tail else "")
        return None  # base is a Call/Subscript/etc — not aliasable, do not record

    def visit_Assign(self, n: ast.Assign) -> None:
        if len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            target = n.targets[0].id
            if isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
                self.str_alias_stack[-1][target] = n.value.value
            else:
                chain = self._chain_of(n.value)
                if chain is not None:
                    self.alias_stack[-1][target] = chain
        self.generic_visit(n)

    def _record(self, kind: str, node: ast.AST) -> None:
        self.raw.append((self._qualscope(), kind, node.lineno, node.col_offset))

    def _arg_urls(self, call: ast.Call) -> list[str]:
        """String literals (resolved through str-const aliases) among a call's arguments."""
        out: list[str] = []
        parts: list[ast.AST] = list(call.args) + [kw.value for kw in call.keywords]
        for a in parts:
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                out.append(a.value)
            elif isinstance(a, ast.Name):
                s = self._resolve_str(a.id)
                if s is not None:
                    out.append(s)
            elif isinstance(a, ast.JoinedStr):  # f-string: check its literal parts
                for v in a.values:
                    if isinstance(v, ast.Constant) and isinstance(v.value, str):
                        out.append(v.value)
        return out

    def visit_Call(self, n: ast.Call) -> None:
        f = n.func

        if isinstance(f, ast.Attribute):
            # (a) SDK terminal call: <chain>.create/.stream/.parse(...)
            if f.attr in TERMINAL_METHODS:
                chain = self._chain_of(f)
                if chain and any(c in chain for c in PROVIDER_CHAINS):
                    self._record(_kind(chain), n)
            # (b) direct provider HTTP: session.post("https://api.openai.com/...", ...)
            elif f.attr in HTTP_VERBS:
                if any(any(m in u for m in PROVIDER_URL_MARKERS) for u in self._arg_urls(n)):
                    self._record("http", n)

        elif isinstance(f, ast.Name):
            # (c) callable alias: f = client.chat.completions.create ; f(...)
            resolved = self._resolve(f.id)
            if resolved != f.id and any(c in resolved for c in PROVIDER_CHAINS):
                last = resolved.rsplit(".", 1)[-1]
                if last in TERMINAL_METHODS:
                    self._record(_kind(resolved), n)

        self.generic_visit(n)


def scan_source(src: str, relpath: str = "<mem>") -> list[Hit]:
    """Scan one Python source string. Raises SyntaxError on unparseable input."""
    tree = ast.parse(src)
    s = _Scanner()
    s.visit(tree)
    # Assign a stable source-order ordinal per (scope, kind) so duplicate calls in one scope
    # and same-named methods across classes each get a distinct identity key.
    counters: dict[tuple[str, str], int] = {}
    hits: list[Hit] = []
    for scope, kind, lineno, col in sorted(s.raw, key=lambda r: (r[2], r[3])):
        idx = counters.get((scope, kind), 0)
        counters[(scope, kind)] = idx + 1
        hits.append(Hit(relpath, scope, kind, idx, lineno, col))
    return hits


def scan_tree(root: str | Path, skip_dirs: set[str] | None = None) -> tuple[list[Hit], list[str]]:
    """Walk `root`, return (hits, unparseable_relpaths).

    Unparseable files are RETURNED, never silently skipped — a syntax-error file could
    otherwise hide an egress call from the gate (fail-closed).
    """
    root = Path(root)
    skip = DEFAULT_SKIP_DIRS if skip_dirs is None else skip_dirs
    hits: list[Hit] = []
    unparseable: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            p = Path(dirpath) / fn
            rel = p.relative_to(root).as_posix()
            try:
                src = p.read_text(encoding="utf-8")
                hits.extend(scan_source(src, rel))
            except (SyntaxError, UnicodeDecodeError):
                unparseable.append(rel)
    return hits, unparseable


def scan_keys(root: str | Path, skip_dirs: set[str] | None = None) -> tuple[set[str], list[str]]:
    hits, unparseable = scan_tree(root, skip_dirs)
    return {h.key() for h in hits}, unparseable
