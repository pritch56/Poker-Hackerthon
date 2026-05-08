"""Station-04: calls almost everything, rarely raises."""
import random

BOT_NAME = "Station-04"
_RNG = random.Random(2004)
_FOLD_THRESH = 0.4
_RAISE_FREQ = 0.15

def decide(state):
    if state.get("type") == "warmup":
        return {"ok": True}
    if state["can_check"]:
        if _RNG.random() < _RAISE_FREQ:
            target = state["current_bet"] + int(state["pot"] * 0.5)
            return {"action": "raise", "amount": max(state["min_raise_to"], target)}
        return {"action": "check"}
    pot = max(state["pot"], 1)
    owed = state["amount_owed"]
    if owed > pot * _FOLD_THRESH:
        return {"action": "fold"}
    if _RNG.random() < _RAISE_FREQ:
        target = state["current_bet"] + int(pot * 0.5)
        return {"action": "raise", "amount": max(state["min_raise_to"], target)}
    return {"action": "call"}
