"""W3 / PB-H13 — autonomous war-game play.

Runs an N-round campaign over a war room WITHOUT human prompting: each round
our side plays the next move from a catalog, the injected ``reactor`` returns
the adversaries' grounded reactions, and we narrate the exchange.

Pure + deterministic given a deterministic reactor. The route
(`POST /war-rooms/{id}/run-autonomous`) injects a reactor backed by the SAME
`services.war_game_engine.generate_reactions` the Guided path uses — so the
adversary reactions stay DB-grounded (no fabrication). This module owns only
the round/narration orchestration, so it unit-tests with a stub reactor and
no database.
"""
from __future__ import annotations

from typing import Callable, Optional

# Default opening campaign when the caller supplies no moves. These are valid
# war_game_engine MOVE_TYPES; the route validates any caller-supplied moves.
DEFAULT_MOVES: tuple[str, ...] = ("trial_readout", "label_expansion", "price_cut")

MAX_ROUNDS = 8

# reactor(move_type, round_num, history) -> list[reaction dict]
Reactor = Callable[[str, int, list[dict]], list[dict]]


def _confidence(reaction: dict) -> float:
    for key in ("confidence", "confidence_score"):
        v = reaction.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _dominant_reaction(reactions: list[dict]) -> Optional[dict]:
    """The highest-confidence reaction leads the round's narration."""
    if not reactions:
        return None
    return max(reactions, key=_confidence)


def _narrate(round_num: int, player_name: str, move: str, lead: Optional[dict]) -> str:
    pretty_move = move.replace("_", " ")
    if lead is None:
        return f"Round {round_num}: {player_name} plays {pretty_move}; no rival reaction surfaced."
    rival = lead.get("competitor_company_name") or "a rival"
    detail = (
        lead.get("headline")
        or lead.get("specific_action")
        or lead.get("reaction_type")
        or "reacts"
    )
    return f"Round {round_num}: {player_name} plays {pretty_move}; {rival} responds — {detail}."


def autoplay(
    *,
    our_moves: Optional[list[str]],
    reactor: Reactor,
    rounds: int = 3,
    player_name: str = "Player",
) -> dict:
    """Run an autonomous N-round campaign.

    Args:
        our_moves: ordered move catalog; cycled across rounds. Falls back to
            DEFAULT_MOVES when empty.
        reactor: ``(move_type, round_num, history) -> list[reaction dict]``.
            The route supplies a DB-grounded reactor; tests supply a stub.
        rounds: number of rounds to play (1..MAX_ROUNDS).
        player_name: the focal player's display name.

    Returns:
        {"rounds": [...], "narration": [...], "summary": {...}}.
    """
    if rounds < 1 or rounds > MAX_ROUNDS:
        raise ValueError(f"rounds must be in [1, {MAX_ROUNDS}] (got {rounds})")

    moves = [m for m in (our_moves or ()) if m] or list(DEFAULT_MOVES)

    history: list[dict] = []
    out_rounds: list[dict] = []
    narration: list[str] = []

    for i in range(rounds):
        move = moves[i % len(moves)]
        reactions = reactor(move, i + 1, history) or []
        lead = _dominant_reaction(reactions)
        line = _narrate(i + 1, player_name, move, lead)
        narration.append(line)
        out_rounds.append(
            {"round": i + 1, "our_move": move, "reactions": reactions, "narration": line}
        )
        history.append({"round": i + 1, "move_type": move, "player": player_name})

    summary = {
        "rounds_played": len(out_rounds),
        "moves": [r["our_move"] for r in out_rounds],
        "total_reactions": sum(len(r["reactions"]) for r in out_rounds),
    }
    return {"rounds": out_rounds, "narration": narration, "summary": summary}
