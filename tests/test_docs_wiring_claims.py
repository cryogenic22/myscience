"""TICKET-13 (F-backlog housekeeping): keep CLAUDE.md's CTX wiring claims honest
against the actual code.

A doc that says "NOT YET WIRED" while the symbol IS wired (or the reverse) is a
quiet integrity drift — readers and agents act on a false status. These tests
COUPLE the doc claim to the real wiring so it fails closed if either drifts.
Structural floor over discipline (conservation-gates.md principle 4).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _not_yet_wired_block(md: str) -> str:
    """The CLAUDE.md text from the 'NOT YET WIRED' heading to the next heading
    (empty string if the heading is absent)."""
    if "NOT YET WIRED" not in md:
        return ""
    return md.split("NOT YET WIRED", 1)[1].split("\n## ", 1)[0]


def test_conversation_memory_is_wired_in_live_chat_route():
    """ConversationMemory is used by the LIVE chat route — pin the wiring so the
    doc claim below has a real referent (and so a future un-wiring is caught)."""
    chat = _read("api/routes/chat.py")
    assert "get_conversation_memory(" in chat
    assert "save_conversation_memory(" in chat
    assert "resolve_reference_with_map(" in chat


def test_claude_md_does_not_misreport_conversation_memory_as_unwired():
    """Anti-drift: because the code wires it, CLAUDE.md must NOT file
    ConversationMemory under 'NOT YET WIRED'. RED before TICKET-13, GREEN after."""
    md = _read("CLAUDE.md")
    chat = _read("api/routes/chat.py")
    wired = "get_conversation_memory(" in chat and "save_conversation_memory(" in chat
    assert "ConversationMemory" in md, "CLAUDE.md should still document ConversationMemory"
    if wired:
        assert "ConversationMemory" not in _not_yet_wired_block(md), (
            "CLAUDE.md lists ConversationMemory as NOT YET WIRED, but it is wired in "
            "api/routes/chat.py (get/save_conversation_memory, resolve_reference_with_map)."
        )
        # Heading-independent guard: NO line naming ConversationMemory may also say
        # "not yet wired" — catches the Services-Layer table phrasing, which is not
        # under the exact-case heading the block parser keys on (review N2).
        for line in md.splitlines():
            if "ConversationMemory" in line:
                assert "not yet wired" not in line.lower(), (
                    f"CLAUDE.md still calls ConversationMemory not-yet-wired: {line!r}"
                )


def test_autonomous_research_agent_claim_matches_reality():
    """AutonomousResearchAgent is reachable via the enrichment route (manual
    run_loop), NOT a scheduled background loop. Guard BOTH halves of the doc claim:
    the route wiring exists AND no scheduler/ module registers it — so the doc's
    'not scheduled' wording fails closed if someone later wires it into the
    scheduler (review N1)."""
    enrich = _read("api/routes/enrichment.py")
    assert "AutonomousResearchAgent(" in enrich
    assert ".run_loop(" in enrich
    # Negative guard for the "not scheduled" half: the scheduler must not reference
    # the agent. If this fires, the agent became autonomous → update CLAUDE.md.
    sched_dir = ROOT / "scheduler"
    if sched_dir.is_dir():
        for py in sched_dir.rglob("*.py"):
            assert "AutonomousResearchAgent" not in py.read_text(encoding="utf-8"), (
                f"AutonomousResearchAgent now registered in {py.name} — it is "
                "scheduled; CLAUDE.md must no longer say 'not scheduled'."
            )
