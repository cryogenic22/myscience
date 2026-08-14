"""WP-12C — mutation proof for the egress scanner (SPEC_WP12 §3 WP-12C).

A security gate that cannot fail on a real bypass is a vacuous gate (conservation
principle #3). These tests inject synthetic raw provider calls — direct AND the
intermediate-variable alias form that defeated the first-pass scanner — and assert the
redesigned scanner turns RED. Plus: fail-closed on unparseable input, and the pinned
inventory matches the live tree.
"""
from __future__ import annotations

import json
from pathlib import Path

from assurance.egress_scan import scan_source, scan_tree, scan_keys, PROVIDER_CHAINS

REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = REPO_ROOT / "assurance" / "contract" / "egress_inventory.json"

_CLEAN = """
def do_work(client, payload):
    result = transform(payload)
    return summarize(result)
"""

_DIRECT_OPENAI = """
def synth(client, prompt):
    return client.chat.completions.create(model="gpt", messages=prompt)
"""

_DIRECT_ANTHROPIC = """
def synth(client, prompt):
    return client.messages.create(model="claude", messages=prompt)
"""

_DIRECT_EMBED = """
def embed(client, text):
    return client.embeddings.create(model="e", input=text)
"""

# The bypass that defeated the first-pass substring scanner:
_ALIAS_BYPASS = """
def synth(client, prompt):
    endpoint = client.chat.completions
    return endpoint.create(model="gpt", messages=prompt)
"""

# Two-hop alias, to stress transitive resolution:
_ALIAS_TWO_HOP = """
def synth(client, prompt):
    chat = client.chat
    comp = chat.completions
    return comp.create(model="gpt", messages=prompt)
"""


def test_scanner_finds_direct_openai_egress():
    hits = scan_source(_DIRECT_OPENAI)
    assert [h.kind for h in hits] == ["chat"], hits


def test_scanner_finds_anthropic_messages_egress():
    hits = scan_source(_DIRECT_ANTHROPIC)
    assert [h.kind for h in hits] == ["messages"], hits


def test_scanner_finds_embeddings_egress():
    hits = scan_source(_DIRECT_EMBED)
    assert [h.kind for h in hits] == ["embeddings"], hits


def test_scanner_catches_alias_bypass():
    """The key redesign: an aliased provider chain is still detected."""
    hits = scan_source(_ALIAS_BYPASS)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_scanner_catches_two_hop_alias():
    hits = scan_source(_ALIAS_TWO_HOP)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


# =========================================================================
# Hardening classes an independent review proved the first redesign missed.
# Each MUST turn the scanner RED (a gate blind to a real bypass is vacuous).
# =========================================================================

_CALLABLE_ALIAS = """
def synth(client, prompt):
    call = client.chat.completions.create
    return call(model="gpt", messages=prompt)
"""

_STREAM_TERMINAL = """
def synth(client, prompt):
    return client.chat.completions.stream(model="gpt", messages=prompt)
"""

_PARSE_TERMINAL = """
def synth(client, prompt):
    return client.chat.completions.parse(model="gpt", messages=prompt)
"""

_MESSAGES_STREAM = """
def synth(client, prompt):
    return client.messages.stream(model="claude", messages=prompt)
"""

_DIRECT_HTTP_LITERAL = """
import requests
def synth(prompt):
    return requests.post("https://api.openai.com/v1/chat/completions", json=prompt)
"""

_DIRECT_HTTP_CONST = """
import httpx
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
def synth(client, prompt):
    return client.post(OPENAI_URL, json=prompt)
"""

_DIRECT_HTTP_ANTHROPIC = """
import requests
def synth(prompt):
    return requests.post("https://api.anthropic.com/v1/messages", json=prompt)
"""

_TWO_CALLS_ONE_FUNC = """
def synth(client, a, b):
    x = client.chat.completions.create(model="gpt", messages=a)
    y = client.chat.completions.create(model="gpt", messages=b)
    return x, y
"""

_SAME_METHOD_TWO_CLASSES = """
class Alpha:
    def call(self, client, p):
        return client.chat.completions.create(model="gpt", messages=p)

class Beta:
    def call(self, client, p):
        return client.chat.completions.create(model="gpt", messages=p)
"""


def test_scanner_catches_callable_alias():
    """f = client.chat.completions.create ; f(...) — the SDK method aliased to a callable."""
    hits = scan_source(_CALLABLE_ALIAS)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_scanner_catches_stream_terminal():
    """.stream(...) is live egress, not only .create(...)."""
    hits = scan_source(_STREAM_TERMINAL)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_scanner_catches_parse_terminal():
    hits = scan_source(_PARSE_TERMINAL)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_scanner_catches_anthropic_stream():
    hits = scan_source(_MESSAGES_STREAM)
    assert len(hits) == 1 and hits[0].kind == "messages", hits


def test_scanner_catches_direct_http_literal():
    """A provider endpoint literal on an HTTP verb bypasses SDK-chain detection entirely."""
    hits = scan_source(_DIRECT_HTTP_LITERAL)
    assert len(hits) == 1 and hits[0].kind == "http", hits


def test_scanner_catches_direct_http_via_const():
    """URL hidden behind a module constant is resolved and still caught."""
    hits = scan_source(_DIRECT_HTTP_CONST)
    assert len(hits) == 1 and hits[0].kind == "http", hits


def test_scanner_catches_direct_http_anthropic():
    hits = scan_source(_DIRECT_HTTP_ANTHROPIC)
    assert len(hits) == 1 and hits[0].kind == "http", hits


def test_two_calls_in_one_function_get_distinct_keys():
    """Two egress calls in one scope must NOT collapse to one inventory key — else one
    could be added or removed silently (the review's 'hits=2, unique keys=1' defect)."""
    hits = scan_source(_TWO_CALLS_ONE_FUNC, "prod/mod.py")
    keys = {h.key() for h in hits}
    assert len(hits) == 2, hits
    assert len(keys) == 2, sorted(keys)
    assert {h.ordinal for h in hits} == {0, 1}, hits


def test_same_method_name_in_two_classes_get_distinct_keys():
    """Same-named method in two classes must NOT collapse (qualified scope in the key)."""
    hits = scan_source(_SAME_METHOD_TWO_CLASSES, "prod/mod.py")
    keys = {h.key() for h in hits}
    assert len(hits) == 2, hits
    assert len(keys) == 2, sorted(keys)
    assert any("Alpha.call" in k for k in keys), sorted(keys)
    assert any("Beta.call" in k for k in keys), sorted(keys)


def test_first_pass_and_prior_redesign_both_miss_the_new_classes():
    """Proof these are genuine gaps the CURRENT hardening closes (not already-covered):
    the prior redesign only matched `.attr == 'create'`, so callable-alias / .stream /
    .parse / direct-HTTP all scanned to ZERO under it. Ours catches each."""
    import ast

    def prior_redesign_hits(src: str) -> int:
        """Faithful model of the pre-hardening scanner: only Attribute `.create` calls,
        with alias resolution on the receiver chain."""
        aliases: dict[str, str] = {}

        def chain_of(node):
            attrs = []
            while isinstance(node, ast.Attribute):
                attrs.append(node.attr)
                node = node.value
            if isinstance(node, ast.Name):
                base = aliases.get(node.id, node.id)
                tail = ".".join(reversed(attrs))
                return base + ("." + tail if tail else "")
            return None

        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                c = chain_of(node.value)
                if c:
                    aliases[node.targets[0].id] = c
        n = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "create":
                c = chain_of(node.func)
                if c and any(pc in c for pc in PROVIDER_CHAINS):
                    n += 1
        return n

    for src in (_CALLABLE_ALIAS, _STREAM_TERMINAL, _PARSE_TERMINAL, _DIRECT_HTTP_LITERAL):
        assert prior_redesign_hits(src) == 0        # prior: blind
        assert len(scan_source(src)) == 1           # hardened: catches it


def test_production_directories_are_not_skipped(tmp_path):
    """The skip list must never grow to hide a real runtime dir. A synthetic egress placed
    under a production-shaped path (services/, apps/, packages/) is still found."""
    from assurance.egress_scan import DEFAULT_SKIP_DIRS
    for prod_dir in ("services", "apps", "packages", "integration", "connectors", "scripts"):
        assert prod_dir not in DEFAULT_SKIP_DIRS, f"{prod_dir} must be scanned"
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "leak.py").write_text(_DIRECT_OPENAI, encoding="utf-8")
    hits, unparseable = scan_tree(tmp_path)
    assert not unparseable
    assert [h.kind for h in hits] == ["chat"], hits
    assert hits[0].relpath == "services/leak.py", hits


def _first_pass_scanner_hits(src: str) -> int:
    """Faithful model of the first-pass scanner: AST `.create` calls whose chain — walked
    WITHOUT alias resolution — contains a provider chain. This is what missed the alias
    bypass (endpoint.create -> chain 'endpoint.create' -> no provider substring)."""
    import ast

    def chain_str(node):
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts))

    n = 0
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "create":
            chain = chain_str(node.func)
            if any(c in chain for c in PROVIDER_CHAINS):
                n += 1
    return n


def test_alias_bypass_is_a_real_gap_the_redesign_closes():
    """Proof the redesign is not vacuous: the first-pass scanner missed the alias bypass; ours catches it."""
    assert _first_pass_scanner_hits(_ALIAS_BYPASS) == 0       # first-pass: blind to the alias
    assert len(scan_source(_ALIAS_BYPASS)) == 1               # redesign: sees it
    # sanity: both agree on the un-aliased direct form
    assert _first_pass_scanner_hits(_DIRECT_OPENAI) == 1
    assert len(scan_source(_DIRECT_OPENAI)) == 1


def test_mutation_turns_clean_module_red():
    """The mutation meta-test: a clean module scans to zero; inject a raw egress and it goes RED."""
    assert scan_source(_CLEAN) == []                          # GREEN before mutation
    mutated = _CLEAN + "\n" + _DIRECT_OPENAI                  # inject synthetic direct provider call
    assert len(scan_source(mutated)) == 1                     # RED after mutation


def test_scan_tree_fails_closed_on_unparseable(tmp_path):
    """A syntax-error file is REPORTED as unparseable, never silently skipped."""
    (tmp_path / "good.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("def f(:\n    return\n", encoding="utf-8")  # syntax error
    hits, unparseable = scan_tree(tmp_path)
    assert "bad.py" in unparseable, unparseable
    assert hits == []


# ---- the gate is wired to reality: pinned inventory == live tree ----

def _inventory_keys() -> set[str]:
    data = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    return set(data["sites"])


def test_no_new_uninventoried_egress_site():
    keys, unparseable = scan_keys(REPO_ROOT)
    assert not unparseable, f"fail-closed: unparseable files hide egress: {unparseable}"
    new = sorted(keys - _inventory_keys())
    assert not new, f"new egress site(s) not in the pinned inventory: {new}"


def test_inventory_has_no_stale_entries():
    keys, _ = scan_keys(REPO_ROOT)
    stale = sorted(_inventory_keys() - keys)
    assert not stale, f"inventory lists site(s) that no longer exist: {stale}"


def test_inventory_is_wellformed():
    data = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    for key, meta in data["sites"].items():
        assert meta.get("class") in {"runtime", "allowlist"}, key
        if meta["class"] == "allowlist":
            assert meta.get("reason"), f"allowlisted site needs a reason: {key}"
        else:
            assert meta.get("guard_status") in {"unguarded", "guarded"}, key
