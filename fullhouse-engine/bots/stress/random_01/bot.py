"""Random-01: random legal action, weighted."""
import random

BOT_NAME = "Random-01"
_RNG = random.Random(3001)
_FP = 0.4; _CP = 0.4; _RP = 0.2

def decide(state):
    if state.get("type") == "warmup":
        return {"ok": True}
    if state["can_check"]:
        # check or raise
        r = _RNG.random()
        if r < _RP:
            target = state["current_bet"] + int(max(state["pot"], state["min_raise_to"]) * 0.7)
            return {"action": "raise", "amount": max(state["min_raise_to"], target)}
        return {"action": "check"}
    r = _RNG.random()
    if r < _FP:
        return {"action": "fold"}
    if r < _FP + _CP:
        return {"action": "call"}
    target = state["current_bet"] + int(max(state["pot"], state["min_raise_to"]) * 0.7)
    return {"action": "raise", "amount": max(state["min_raise_to"], target)}
