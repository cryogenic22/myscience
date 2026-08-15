"""WP-12C — LLM/provider egress scanner (alias-resolving, fail-closed static analysis).

Supersedes the first-pass scanner in tests/test_priv001b_egress_inventory.py, which
substring-matched provider call chains and could be defeated by an intermediate variable.
This scanner closes every STATICALLY-RESOLVABLE egress form that three independent review
rounds demonstrated the earlier passes missed:

  1. **Callable alias.**   f = client.chat.completions.create ; f(...)
  2. **Non-.create terminals.**  client.chat.completions.stream(...) / .parse(...)
  3. **Direct provider HTTP.**   requests.post("https://api.openai.com/v1/chat/completions", ...)
  4. **Intermediate-variable receiver.**  c = client.chat.completions ; c.create(...)
  5. **Non-Name receiver bases.**  get_client().chat...create ; clients["openai"].messages.create
  6. **Reflection / partial.**  getattr(chain, "create")(...) ; functools.partial(chain.create)(...)
  7. **Attribute-target cache.**  self._go = client...create (any method order, incl. the attr
     named like a terminal `self.create = ...create`, and transitively `self._go = self._raw`) ; self._go(...)
  8. **Tuple-unpack + walrus alias.**  go, _ = client...create, 1 ; go(...)  /  (go := client...create)(...)
  9. **Collapsed identity.** two egress calls in one scope, or a same-named method in two classes,
     no longer collapse to one inventory key — identity is (relpath, qualified-scope, kind,
     source-ordinal): unique per call site AND stable across line edits (line/col are reporting
     metadata, not the pinned key — a line-number key would churn on every refactor).

**Boundary (honest scope, not an overclaim):** this is *static* analysis. It cannot see forms
that are only decidable at runtime — a method/attr name computed at runtime (`getattr(o, name)`
where `name` is a variable), `exec`/`eval`, or a provider client injected via reflection/plugin.
It also does NOT model container/subscript indirection, even with a literal key
(`{"create": chain}["create"]()`), which would open an unbounded dict/`.get`/list surface. Those
are OUT of static reach BY CONSTRUCTION, tracked as ESC-2026-08-15-egress-static-limit, each
pinned by a strict=True xfail so it can never be silently claimed as covered; the backstop for
them is the *runtime* egress guard (PRIV-001b), not this scanner. A gate that cannot fail on a
real *statically-visible* bypass would be vacuous (principle #3);
tests/test_wp12c_egress_mutation.py proves each class 1–9 turns the scanner RED.

Importable so both the assurance gate and PRIV-001b consume ONE scanner, not two.
"""
from __future__ import annotations

import ast
import os
import warnings
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
        # Attribute-target callable aliases (e.g. `self._go = client...create`), keyed by the
        # dotted target ("self._go"). Module-wide (NOT scope-stacked) because an instance
        # attribute set in __init__ is called from another method — a different scope.
        self.attr_alias: dict[str, str] = {}
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
        """Resolved dotted chain for an attribute/name expr.

        Name base -> alias-resolved full chain (e.g. ``client.chat.completions``). Non-Name
        base (a Call like ``get_client()`` or a Subscript like ``clients["openai"]``) -> the
        attribute SUFFIX alone (e.g. ``chat.completions``), so a provider chain hanging off a
        factory call or a dict lookup is still detected. None only if there is no attribute
        suffix and no Name base to resolve."""
        attrs: list[str] = []
        while isinstance(node, ast.Attribute):
            attrs.append(node.attr)
            node = node.value
        tail = ".".join(reversed(attrs))
        if isinstance(node, ast.Name):
            base = self._resolve(node.id)
            return base + ("." + tail if tail else "")
        # base is a Call/Subscript/etc: the receiver is not a stable name, but the attribute
        # path off it can still carry a provider chain (get_client().chat.completions.create).
        return tail or None

    def _getattr_chain(self, call: ast.Call) -> str | None:
        """getattr(<expr>, "<method>") -> resolved '<chain>.<method>' (string-literal method)."""
        fn = call.func
        is_getattr = (isinstance(fn, ast.Name) and fn.id == "getattr") or \
                     (isinstance(fn, ast.Attribute) and fn.attr == "getattr")
        if is_getattr and len(call.args) >= 2:
            obj, meth = call.args[0], call.args[1]
            if isinstance(meth, ast.Constant) and isinstance(meth.value, str) \
                    and isinstance(obj, (ast.Attribute, ast.Name)):
                base = self._chain_of(obj)
                if base is not None:
                    return f"{base}.{meth.value}"
        return None

    def _partial_inner_chain(self, call: ast.Call) -> str | None:
        """(functools.)partial(<callable>, ...) -> the resolved chain of its first arg."""
        fn = call.func
        is_partial = (isinstance(fn, ast.Name) and fn.id == "partial") or \
                     (isinstance(fn, ast.Attribute) and fn.attr == "partial")
        if is_partial and call.args:
            return self._callable_chain_of(call.args[0])
        return None

    def _callable_chain_of(self, value: ast.AST) -> str | None:
        """The dotted chain a value resolves to WHEN USED AS A CALLABLE: a plain attribute/name
        chain, or the callable hidden inside getattr(...) / partial(...)."""
        if isinstance(value, (ast.Attribute, ast.Name)):
            return self._chain_of(value)
        if isinstance(value, ast.Call):
            return self._getattr_chain(value) or self._partial_inner_chain(value)
        return None

    def _store_alias(self, target: ast.AST, value: ast.AST) -> None:
        """Record target <- value for later callable resolution (Name in scope; self.x module-wide)."""
        if isinstance(target, ast.Name):
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                self.str_alias_stack[-1][target.id] = value.value
                return
            chain = self._callable_chain_of(value)
            if chain is not None:
                self.alias_stack[-1][target.id] = chain
        elif isinstance(target, ast.Attribute):
            key = self._chain_of(target)           # e.g. "self._go"
            chain = self._callable_chain_of(value)
            if key is not None and chain is not None:
                self.attr_alias[key] = chain

    def _resolve_attr(self, key: str) -> str | None:
        """Transitively resolve an attribute-target alias through attr_alias
        (self._go -> self._raw -> client...create). Cycle-safe."""
        v = self.attr_alias.get(key)
        seen: set[str] = set()
        while v is not None and v in self.attr_alias and v not in seen:
            seen.add(v)
            v = self.attr_alias[v]
        return v

    def visit_Assign(self, n: ast.Assign) -> None:
        for tgt in n.targets:
            if isinstance(tgt, (ast.Tuple, ast.List)) and isinstance(n.value, (ast.Tuple, ast.List)) \
                    and len(tgt.elts) == len(n.value.elts):
                for t, v in zip(tgt.elts, n.value.elts):   # go, _ = client...create, 1
                    self._store_alias(t, v)
            else:
                self._store_alias(tgt, n.value)
        self.generic_visit(n)

    def visit_NamedExpr(self, n: ast.NamedExpr) -> None:
        # walrus: (go := client...create) — record the alias for later `go(...)` uses.
        self._store_alias(n.target, n.value)
        self.generic_visit(n)

    def _record_callable(self, chain: str | None, node: ast.Call) -> bool:
        """Record a hit if `chain` is a provider SDK terminal or an HTTP verb hitting a provider
        URL in `node`'s args. Returns True if recorded."""
        if not chain:
            return False
        last = chain.rsplit(".", 1)[-1]
        if last in TERMINAL_METHODS and any(c in chain for c in PROVIDER_CHAINS):
            self._record(_kind(chain), node)
            return True
        if last in HTTP_VERBS and any(any(m in u for m in PROVIDER_URL_MARKERS) for u in self._arg_urls(node)):
            self._record("http", node)
            return True
        return False

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
            recorded = False
            # (a) SDK terminal call: <chain>.create/.stream/.parse(...)
            if f.attr in TERMINAL_METHODS:
                chain = self._chain_of(f)
                if chain and any(c in chain for c in PROVIDER_CHAINS):
                    self._record(_kind(chain), n)
                    recorded = True
            # (b) direct provider HTTP: session.post("https://api.openai.com/...", ...)
            elif f.attr in HTTP_VERBS:
                if any(any(m in u for m in PROVIDER_URL_MARKERS) for u in self._arg_urls(n)):
                    self._record("http", n)
                    recorded = True
            # (e) attribute-target callable alias — ALWAYS also consult attr_alias, even when the
            #     attr name IS a terminal/http word (self.create = client...create ; self.create(...)):
            #     the direct-chain check above misses it because 'self.create' has no provider substring.
            if not recorded:
                self._record_callable(self._resolve_attr(self._chain_of(f) or ""), n)

        elif isinstance(f, ast.Name):
            # (c)/(d) callable alias (incl. getattr/partial assigned to a name): f(...)
            resolved = self._resolve(f.id)
            if resolved != f.id:
                self._record_callable(resolved, n)

        elif isinstance(f, ast.NamedExpr):
            # (g) walrus as callable: (go := client...create)(...)
            self._record_callable(self._callable_chain_of(f.value), n)

        elif isinstance(f, ast.Call):
            # (f) immediate reflection/partial: getattr(chain,"create")(...) / partial(chain.create)(...)
            self._record_callable(self._getattr_chain(f) or self._partial_inner_chain(f), n)

        self.generic_visit(n)


def scan_source(src: str, relpath: str = "<mem>") -> list[Hit]:
    """Scan one Python source string. Raises SyntaxError on unparseable input.

    We are parsing OTHER files to find egress, not linting them; suppress their benign
    SyntaxWarnings (e.g. an unescaped '\\s' in a non-raw string) so they don't pollute the
    gate's output. A real SyntaxError still propagates and is reported as unparseable upstream.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(src)
    s = _Scanner()
    # Pre-pass: collect instance-attribute callable aliases (self.x = client...create) BEFORE
    # visiting calls, so a `self.x(...)` call in a method defined ABOVE __init__ still resolves
    # (instance attributes are not source-ordered like locals).
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Attribute):
                    s._store_alias(tgt, node.value)
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
