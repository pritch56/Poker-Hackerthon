"""Overbet-03: raises 1.5-3x pot, polarised."""
import random, eval7

BOT_NAME = "Overbet-03"
_RNG = random.Random(7003)
_OPEN = {'AA', 'KK', 'QQ', 'JJ', 'AKs', 'TT', '99', 'AKo', 'AQs', 'AJs', 'KQs'}
_MULT = 2.5
_VALUE_ONLY = True

def _hand_key(c1, c2):
    r = "23456789TJQKA"
    if r.index(c1[0]) < r.index(c2[0]):
        c1, c2 = c2, c1
    if c1[0] == c2[0]:
        return c1[0] + c2[0]
    return c1[0] + c2[0] + ("s" if c1[1] == c2[1] else "o")

def _strong(cards, board):
    if len(board) < 3:
        return False
    full = [eval7.Card(c) for c in cards + board]
    ht = eval7.handtype(eval7.evaluate(full)).lower()
    return any(x in ht for x in ("two pair","three","straight","flush","full","four"))

def decide(state):
    if state.get("type") == "warmup":
        return {"ok": True}
    cards = state["your_cards"]; pot = state["pot"]
    raised = sum(1 for a in state["action_log"] if a.get("action") in ("raise","all_in"))
    if state["street"] == "preflop":
        hk = _hand_key(cards[0], cards[1])
        if hk in _OPEN:
            target = state["current_bet"] + int(max(pot, 300) * _MULT)
            return {"action": "raise", "amount": max(state["min_raise_to"], target)}
        if raised and hk in {"AA","KK"}:
            return {"action": "call"}
        if state["can_check"]:
            return {"action": "check"}
        return {"action": "fold"}
    strong = _strong(cards, state["community_cards"])
    if state["can_check"]:
        if strong or (not _VALUE_ONLY and _RNG.random() < 0.4):
            target = state["current_bet"] + int(pot * _MULT)
            return {"action": "raise", "amount": max(state["min_raise_to"], target)}
        return {"action": "check"}
    if strong:
        target = state["current_bet"] + int(pot * _MULT)
        return {"action": "raise", "amount": max(state["min_raise_to"], target)}
    if state["amount_owed"] < pot * 0.2:
        return {"action": "call"}
    return {"action": "fold"}
