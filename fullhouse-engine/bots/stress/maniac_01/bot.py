"""Maniac-01: raises constantly, jams often."""
import random

BOT_NAME = "Maniac-01"
_RNG = random.Random(1001)
_RAISE_FREQ = 0.85
_SIZE = 0.6
_ALLIN_P = 0.05

def decide(state):
    if state.get("type") == "warmup":
        return {"ok": True}
    stack = state["your_stack"]; pot = state["pot"]
    if _RNG.random() < _ALLIN_P:
        return {"action": "all_in"}
    if _RNG.random() < _RAISE_FREQ:
        target = state["current_bet"] + int(max(pot, state["min_raise_to"]) * _SIZE)
        target = max(target, state["min_raise_to"])
        if target >= stack + state["your_bet_this_street"]:
            return {"action": "all_in"}
        return {"action": "raise", "amount": target}
    if state["can_check"]:
        return {"action": "check"}
    return {"action": "call"}
