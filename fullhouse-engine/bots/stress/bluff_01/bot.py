"""Bluffer-01: relentless c-bet/double-barrel/triple."""
import random

BOT_NAME = "Bluffer-01"
_RNG = random.Random(11001)
_CBET = 0.85
_DB = 0.55
_TRIPLE = 0.3

def decide(state):
    if state.get("type") == "warmup":
        return {"ok": True}
    pot = state["pot"]
    if state["street"] == "preflop":
        ranks = [c[0] for c in state["your_cards"]]
        playable = ranks[0] in "AKQJT98765" or ranks[1] in "AKQJT98765"
        if playable:
            return {"action": "raise", "amount": max(state["min_raise_to"], 300)}
        if state["can_check"]:
            return {"action": "check"}
        return {"action": "fold"}
    rate = _CBET if state["street"] == "flop" else (_DB if state["street"] == "turn" else _TRIPLE)
    if state["can_check"]:
        if _RNG.random() < rate:
            target = state["current_bet"] + int(pot * 0.6)
            return {"action": "raise", "amount": max(state["min_raise_to"], target)}
        return {"action": "check"}
    if state["amount_owed"] < pot * 0.15:
        return {"action": "call"}
    return {"action": "fold"}
