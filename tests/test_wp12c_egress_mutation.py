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

import pytest

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


# --- receiver-base classes an independent review found still uncovered ---

_FACTORY_CALL_RECEIVER = """
def synth(prompt):
    return get_client().chat.completions.create(model="gpt", messages=prompt)
"""

_SUBSCRIPT_RECEIVER = """
def synth(prompt):
    return clients["openai"].messages.create(model="claude", messages=prompt)
"""

_HTTP_CALLABLE_ALIAS = """
import requests
PROVIDER_URL = "https://api.openai.com/v1/chat/completions"
def synth(prompt):
    send = requests.post
    return send(PROVIDER_URL, json=prompt)
"""


def test_scanner_catches_factory_call_receiver():
    """get_client().chat.completions.create(...) — receiver is a Call, not a Name."""
    hits = scan_source(_FACTORY_CALL_RECEIVER)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_scanner_catches_subscript_receiver():
    """clients['openai'].messages.create(...) — receiver is a Subscript."""
    hits = scan_source(_SUBSCRIPT_RECEIVER)
    assert len(hits) == 1 and hits[0].kind == "messages", hits


def test_scanner_catches_http_callable_alias():
    """send = requests.post ; send(PROVIDER_URL, ...) — the HTTP verb aliased to a callable."""
    hits = scan_source(_HTTP_CALLABLE_ALIAS)
    assert len(hits) == 1 and hits[0].kind == "http", hits


# --- statically-resolvable forms a third independent review reproduced (round-3) ---

_GETATTR_REFLECTION = """
def synth(client, prompt):
    return getattr(client.chat.completions, "create")(model="gpt", messages=prompt)
"""

_FUNCTOOLS_PARTIAL = """
from functools import partial
def synth(client, prompt):
    go = partial(client.chat.completions.create, model="gpt")
    return go(messages=prompt)
"""

_PARTIAL_IMMEDIATE = """
from functools import partial
def synth(client, prompt):
    return partial(client.chat.completions.create)(model="gpt", messages=prompt)
"""

_SELF_ATTR_CACHE = """
class Worker:
    def __init__(self, client):
        self._go = client.chat.completions.create
    def run(self, prompt):
        return self._go(model="gpt", messages=prompt)
"""

_SELF_ATTR_CALL_BEFORE_INIT = """
class Worker:
    def run(self, prompt):
        return self._go(model="gpt", messages=prompt)
    def __init__(self, client):
        self._go = client.chat.completions.create
"""

_TUPLE_UNPACK = """
def synth(client, prompt):
    go, _ = client.chat.completions.create, 1
    return go(model="gpt", messages=prompt)
"""

_GETATTR_HTTP = """
import requests
def synth(prompt):
    return getattr(requests, "post")("https://api.openai.com/v1/chat/completions", json=prompt)
"""


def test_scanner_catches_getattr_reflection_terminal():
    hits = scan_source(_GETATTR_REFLECTION)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_scanner_catches_functools_partial_alias():
    hits = scan_source(_FUNCTOOLS_PARTIAL)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_scanner_catches_partial_immediate_call():
    hits = scan_source(_PARTIAL_IMMEDIATE)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_scanner_catches_self_attr_cached_callable():
    hits = scan_source(_SELF_ATTR_CACHE)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_scanner_catches_self_attr_even_when_call_precedes_init():
    """Instance attributes are not source-ordered like locals — a pre-pass collects them."""
    hits = scan_source(_SELF_ATTR_CALL_BEFORE_INIT)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_scanner_catches_tuple_unpack_alias():
    hits = scan_source(_TUPLE_UNPACK)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_scanner_catches_getattr_http():
    hits = scan_source(_GETATTR_HTTP)
    assert len(hits) == 1 and hits[0].kind == "http", hits


# --- urllib egress (owner-directed): urlopen bypasses the SDK gateway entirely -----------

_URLLIB_DIRECT = """
import urllib.request
def s(payload):
    return urllib.request.urlopen("https://api.openai.com/v1/chat/completions")
"""

_URLLIB_REQUEST_INLINE = """
import urllib.request
def s(payload):
    return urllib.request.urlopen(urllib.request.Request("https://api.anthropic.com/v1/messages", data=payload))
"""

_URLLIB_REQUEST_ASSIGNED = """
import urllib.request
def s(payload):
    req = urllib.request.Request("https://api.openai.com/v1/embeddings", data=payload)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()
"""

_URLLIB_IMPORTED_BARE = """
from urllib.request import urlopen, Request
def s(payload):
    r = Request("https://api.anthropic.com/v1/messages", data=payload)
    return urlopen(r)
"""

_URLLIB_MODULE_ALIAS = """
import urllib.request as U
def s(payload):
    return U.urlopen(U.Request("https://api.openai.com/v1/chat/completions", data=payload))
"""

_URLLIB_KEYWORD_URL = """
import urllib.request
def s(payload):
    req = urllib.request.Request(url="https://api.openai.com/v1/chat/completions", data=payload)
    return urllib.request.urlopen(req)
"""

_URLLIB_GEMINI_FSTRING = """
import urllib.request
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
def s(model, payload):
    url = f"{GEMINI_API_BASE}/{model}:generateContent?key=k"
    req = urllib.request.Request(url, data=payload)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()
"""

_URLLIB_CONST_CONCAT = """
import urllib.request
BASE = "https://api.openai.com"
def s(payload):
    return urllib.request.urlopen(urllib.request.Request(BASE + "/v1/chat/completions", data=payload))
"""

# Non-provider urllib egress MUST NOT be flagged (fda / localhost / raw.githubusercontent).
_URLLIB_NON_PROVIDER = """
import urllib.request
def s():
    return urllib.request.urlopen(urllib.request.Request("https://api.fda.gov/drug/label.json"))
def t(path):
    return urllib.request.urlopen(urllib.request.Request("http://localhost:8000" + path))
"""


@pytest.mark.parametrize("src,label", [
    (_URLLIB_DIRECT, "direct urlopen(URL)"),
    (_URLLIB_REQUEST_INLINE, "urlopen(Request(URL))"),
    (_URLLIB_REQUEST_ASSIGNED, "req=Request(URL); urlopen(req)"),
    (_URLLIB_IMPORTED_BARE, "imported bare urlopen"),
    (_URLLIB_MODULE_ALIAS, "aliased urllib module"),
    (_URLLIB_KEYWORD_URL, "keyword url= arg"),
    (_URLLIB_GEMINI_FSTRING, "gemini f-string + constant"),
    (_URLLIB_CONST_CONCAT, "'+'-concatenated constant URL"),
])
def test_scanner_catches_urllib_provider_egress(src, label):
    """Every urllib shape the owner enumerated turns the scanner RED (kind='http')."""
    hits = scan_source(src)
    assert len(hits) == 1 and hits[0].kind == "http", (label, hits)


def test_scanner_ignores_non_provider_urllib():
    """urllib to non-provider hosts (FDA public API, localhost) is NOT flagged (no false positive)."""
    assert scan_source(_URLLIB_NON_PROVIDER) == []


def test_urllib_covers_all_three_provider_hosts():
    """OpenAI, Anthropic, and Gemini hosts are each recognized."""
    for host in ("https://api.openai.com/v1/chat/completions",
                 "https://api.anthropic.com/v1/messages",
                 "https://generativelanguage.googleapis.com/v1beta/models/x:generateContent"):
        src = f'import urllib.request\ndef s(p): return urllib.request.urlopen(urllib.request.Request("{host}", data=p))\n'
        assert len(scan_source(src)) == 1, host


def test_prior_scanner_was_blind_to_urllib():
    """Proof this is a real gap the fix closes: the SDK-chain/requests-verb scanner never
    inspected urlopen, so all urllib provider egress scanned to zero before this change."""
    import ast as _ast
    # A faithful model of the pre-urllib scanner: only Attribute .create/HTTP-verb calls.
    def pre_urllib_hits(src):
        n = 0
        for node in _ast.walk(_ast.parse(src)):
            if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Attribute):
                if node.func.attr in ("create", "post", "put", "patch", "request", "send", "stream"):
                    n += 1
        return n
    for src in (_URLLIB_DIRECT, _URLLIB_REQUEST_INLINE, _URLLIB_GEMINI_FSTRING):
        assert pre_urllib_hits(src) == 0        # pre-fix: blind to urlopen
        assert len(scan_source(src)) == 1       # fixed: caught


# =========================================================================
# 2026-08-20 correction round — six STATICALLY-RESOLVABLE forms two independent
# reviews reproduced as scanning to ZERO. Each is fixable by construction (NOT a
# runtime residual), so each MUST turn the scanner RED — an xfail here would be a
# vacuous-green mislabel (principle #3).
# =========================================================================

_IMPORTED_REQUESTS_POST = """
from requests import post
def synth(prompt):
    return post("https://api.openai.com/v1/chat/completions", json=prompt)
"""

_RENAMED_REQUESTS_POST = """
from requests import post as xpost
def synth(prompt):
    return xpost("https://api.openai.com/v1/chat/completions", json=prompt)
"""

_RENAMED_URLLIB_URLOPEN = """
from urllib.request import urlopen as uo, Request
def s(payload):
    return uo(Request("https://api.anthropic.com/v1/messages", data=payload))
"""

_FORMAT_URL = """
import requests
def synth(prompt):
    return requests.post("https://api.openai.com/v1/{}".format("chat/completions"), json=prompt)
"""

_PERCENT_URL = """
import requests
def synth(prompt, path):
    return requests.post("https://api.openai.com/v1/%s" % path, json=prompt)
"""

_ANNOTATED_SELF_ATTR_CALL_BEFORE_INIT = """
class Worker:
    def run(self, prompt):
        return self._go(model="gpt", messages=prompt)
    def __init__(self, client):
        self._go: Callable = client.chat.completions.create
"""


def test_scanner_catches_imported_requests_post():
    """`from requests import post ; post(URL)` — a bare-Name HTTP verb, never modeled before."""
    hits = scan_source(_IMPORTED_REQUESTS_POST)
    assert len(hits) == 1 and hits[0].kind == "http", hits


def test_scanner_catches_renamed_requests_post():
    """`from requests import post as xpost ; xpost(URL)` — the ImportFrom alias must be resolved."""
    hits = scan_source(_RENAMED_REQUESTS_POST)
    assert len(hits) == 1 and hits[0].kind == "http", hits


def test_scanner_catches_renamed_urllib_urlopen():
    """`from urllib.request import urlopen as uo ; uo(Request(URL))` — a renamed urlopen."""
    hits = scan_source(_RENAMED_URLLIB_URLOPEN)
    assert len(hits) == 1 and hits[0].kind == "http", hits


def test_scanner_catches_format_url():
    """`requests.post("https://api.openai.com/v1/{}".format(...))` — the provider host is in the
    static .format template prefix, so it is statically resolvable."""
    hits = scan_source(_FORMAT_URL)
    assert len(hits) == 1 and hits[0].kind == "http", hits


def test_scanner_catches_percent_url():
    """`requests.post("https://api.openai.com/v1/%s" % path)` — the host is in the %-template prefix."""
    hits = scan_source(_PERCENT_URL)
    assert len(hits) == 1 and hits[0].kind == "http", hits


def test_scanner_catches_annotated_self_attr_call_before_init():
    """`self._go: Callable = client...create` (an AnnAssign attribute target) called from a method
    ABOVE __init__ — the pre-pass must include AnnAssign, not only Assign."""
    hits = scan_source(_ANNOTATED_SELF_ATTR_CALL_BEFORE_INIT)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_correction_round_forms_are_real_gaps_not_already_covered():
    """These six are statically resolvable and therefore MUST be RED (>=1 hit each) — the negation
    of an xfail. Guards against a future refactor silently regressing any of them back to zero."""
    for src in (_IMPORTED_REQUESTS_POST, _RENAMED_REQUESTS_POST, _RENAMED_URLLIB_URLOPEN,
                _FORMAT_URL, _PERCENT_URL, _ANNOTATED_SELF_ATTR_CALL_BEFORE_INIT):
        assert len(scan_source(src)) >= 1, src


# --- cross-class attribute-alias collision (2026-08-20 review round-2 blocker) ---------------
# attr_alias was keyed GLOBALLY by the dotted target (self._go) without the enclosing class, so a
# harmless self._go in one class could overwrite a provider self._go in another — blinding the
# scanner (a vacuous-green false negative). Order-permutation + same-name coverage.

_XCLASS_PROVIDER_FIRST = """
class Provider:
    def run(self, p):
        return self._go(model="gpt", messages=p)
    def __init__(self, client):
        self._go = client.chat.completions.create

class Harmless:
    def __init__(self, helper):
        self._go = helper.run
"""

_XCLASS_HARMLESS_FIRST = """
class Harmless:
    def __init__(self, helper):
        self._go = helper.run

class Provider:
    def run(self, p):
        return self._go(model="gpt", messages=p)
    def __init__(self, client):
        self._go = client.chat.completions.create
"""

_XCLASS_SAME_NAME = """
class W:
    def run(self, p):
        return self._go(model="gpt", messages=p)
    def __init__(self, client):
        self._go = client.chat.completions.create

class W:
    def __init__(self, helper):
        self._go = helper.run
"""


@pytest.mark.parametrize("src,label", [
    (_XCLASS_PROVIDER_FIRST, "provider class defined BEFORE the harmless collider"),
    (_XCLASS_HARMLESS_FIRST, "provider class defined AFTER the harmless collider"),
    (_XCLASS_SAME_NAME, "two classes with the SAME name both using self._go"),
])
def test_scanner_isolates_cross_class_attr_aliases(src, label):
    """A harmless `self._go` in ANOTHER class must never overwrite a provider `self._go`. Aliases
    are keyed by the enclosing class/receiver scope, so neither definition order nor a duplicated
    class name can blind the scanner. Exactly ONE provider hit in every permutation."""
    hits = scan_source(src)
    assert len(hits) == 1 and hits[0].kind == "chat", (label, hits)


@pytest.mark.xfail(strict=True, reason=(
    "runtime-computed attribute name is beyond STATIC analysis by construction; the backstop is "
    "the PRIV-001b runtime egress guard (ESC-2026-08-15-egress-static-limit). strict=True: if "
    "this ever XPASSes, the scanner changed — update the incident before claiming coverage."))
def test_runtime_dynamic_dispatch_is_a_known_static_limit():
    """A method name only known at runtime cannot be resolved statically. This xfail names the
    boundary so it is never silently claimed as covered."""
    src = "def synth(client, p, method):\n    return getattr(client.chat.completions, method)(messages=p)\n"
    assert len(scan_source(src)) >= 1


@pytest.mark.xfail(strict=True, reason=(
    "container/subscript indirection (even a literal key) is not modeled; a static residual, "
    "backstopped by the PRIV-001b runtime guard (ESC-2026-08-15-egress-static-limit). strict=True "
    "flips this to a failure if someone closes it without updating the incident."))
def test_dict_subscript_indirection_is_a_known_static_limit():
    src = 'def synth(client, p):\n    return {"create": client.chat.completions.create}["create"](messages=p)\n'
    assert len(scan_source(src)) >= 1


@pytest.mark.xfail(strict=True, reason=(
    "cross-receiver attribute-cache (cls.create set via classmethod, read via self.create) aliases "
    "the same slot through Python's class/instance attribute semantics, which static name-resolution "
    "does not unify; a static residual backstopped by the PRIV-001b runtime guard "
    "(ESC-2026-08-15-egress-static-limit). SAME-receiver forms (self.x/self.x) are closed."))
def test_cross_receiver_attr_cache_is_a_known_static_limit():
    src = ("class W:\n"
           "    @classmethod\n"
           "    def setup(cls, client):\n"
           "        cls.create = client.chat.completions.create\n"
           "    def run(self, prompt):\n"
           "        return self.create(model='gpt', messages=prompt)\n")
    assert len(scan_source(src)) >= 1


# --- forms a round-3 verification review reproduced; now CLOSED ---

_SELF_TERMINAL_NAME_CACHE = """
class Worker:
    def __init__(self, client):
        self.create = client.chat.completions.create
    def run(self, prompt):
        return self.create(model="gpt", messages=prompt)
"""

_WALRUS_IMMEDIATE = """
def synth(client, prompt):
    return (go := client.chat.completions.create)(model="gpt", messages=prompt)
"""

_WALRUS_IN_CONDITION = """
def synth(client, prompt):
    if (go := client.chat.completions.create):
        return go(model="gpt", messages=prompt)
"""

_TWO_HOP_SELF_ATTR = """
class Worker:
    def __init__(self, client):
        self._raw = client.chat.completions.create
        self._go = self._raw
    def run(self, prompt):
        return self._go(model="gpt", messages=prompt)
"""


def test_scanner_catches_self_attr_named_like_terminal():
    """self.create = client...create ; self.create(...) — the natural attr name must NOT slip
    through the terminal-method branch (the round-3 recurrence of the attribute-cache class)."""
    hits = scan_source(_SELF_TERMINAL_NAME_CACHE)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_scanner_catches_walrus_immediate():
    hits = scan_source(_WALRUS_IMMEDIATE)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_scanner_catches_walrus_in_condition():
    hits = scan_source(_WALRUS_IN_CONDITION)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_scanner_catches_two_hop_self_attr_alias():
    hits = scan_source(_TWO_HOP_SELF_ATTR)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


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
        assert meta.get("class") in {"runtime", "allowlist", "fixture-only"}, key
        if meta["class"] in {"allowlist", "fixture-only"}:
            # A non-runtime classification is NEVER a bare skip — it must carry a per-site,
            # narrowly-proven reason (no broad directory allowlist).
            assert meta.get("reason"), f"{meta['class']} site needs a per-site reason: {key}"
        else:
            assert meta.get("guard_status") in {"unguarded", "guarded"}, key


def test_fixture_only_sites_are_confined_to_benchmark_eval_trees():
    """A 'fixture-only' classification is only honest for offline benchmark/eval code. Guard
    that the class can never be applied to a production module to wave egress through."""
    data = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    for key, meta in data["sites"].items():
        if meta.get("class") == "fixture-only":
            relpath = key.split("::", 1)[0]
            assert relpath.startswith(("ctxpack/benchmarks/", "benchmark/")), (
                f"fixture-only must live under a benchmark/eval tree, not production: {key}"
            )


# --- co-review round (2026-08-17): forms that returned zero hits before the fix ---

# FINDING #4a: an annotated callable alias. The type hint makes it an AnnAssign, not an Assign,
# so without visit_AnnAssign the alias was invisible and f(...) slipped past.
_ANNOTATED_CALLABLE_ALIAS = """
from typing import Callable
def synth(client, prompt):
    f: Callable = client.chat.completions.create
    return f(model="gpt", messages=prompt)
"""

# FINDING #4a (str variant): an annotated provider-URL alias used in a later HTTP verb.
_ANNOTATED_URL_ALIAS = """
import requests
def synth(prompt):
    url: str = "https://api.openai.com/v1/chat/completions"
    return requests.post(url, json=prompt)
"""

# FINDING #4b: a fixed provider base concatenated with a runtime path, INLINE in the call.
_HTTP_CONCAT_INLINE = """
import requests
OPENAI_BASE = "https://api.openai.com/v1"
def synth(path, body):
    return requests.post(OPENAI_BASE + path, json=body)
"""

# FINDING #4b (kwarg + concat): url=<provider base> + runtime segment as a keyword arg.
_HTTP_CONCAT_KWARG = """
import httpx
def synth(client, seg, body):
    base = "https://api.anthropic.com"
    return client.post(url=base + "/v1/messages" + seg, json=body)
"""


def test_scanner_catches_annotated_callable_alias():
    hits = scan_source(_ANNOTATED_CALLABLE_ALIAS)
    assert len(hits) == 1 and hits[0].kind == "chat", hits


def test_scanner_catches_annotated_url_alias():
    hits = scan_source(_ANNOTATED_URL_ALIAS)
    assert len(hits) == 1 and hits[0].kind == "http", hits


def test_scanner_catches_inline_provider_base_plus_path():
    hits = scan_source(_HTTP_CONCAT_INLINE)
    assert len(hits) == 1 and hits[0].kind == "http", hits


def test_scanner_catches_inline_concat_kwarg_url():
    hits = scan_source(_HTTP_CONCAT_KWARG)
    assert len(hits) == 1 and hits[0].kind == "http", hits
