"""Maniac-03: raises constantly, jams often."""
import random

BOT_NAME = "Maniac-03"
_RNG = random.Random(1003)
_RAISE_FREQ = 0.92
_SIZE = 0.7
_ALLIN_P = 0.02

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
