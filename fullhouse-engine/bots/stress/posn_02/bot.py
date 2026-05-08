"""Positional-02: only plays late position."""
import eval7

BOT_NAME = "Positional-02"
_LATE_OPEN = {'AA', 'KK', 'QQ', 'JJ', 'AKs', 'TT', '99', 'AKo', 'AQs', 'AJs', 'KQs', 'AQo', '88', '77', 'ATs', 'KJs', 'QJs', 'AJo', 'KQo', 'JTs', 'T9s', 'KTs', '66', '55', '44', '33', '22', 'ATo', 'KJo', 'QTs', '98s', '87s', 'A9s', 'A8s', 'A7s', 'A5s', 'A4s', 'A3s', 'A2s', 'K9s', 'Q9s', 'J9s', 'T8s', '97s', '86s', '76s', '65s', '54s', 'KTo', 'QJo', 'JTo', 'T9o'}
_THRESH_SEATS = 2

def _hand_key(c1, c2):
    r = "23456789TJQKA"
    if r.index(c1[0]) < r.index(c2[0]):
        c1, c2 = c2, c1
    if c1[0] == c2[0]:
        return c1[0] + c2[0]
    return c1[0] + c2[0] + ("s" if c1[1] == c2[1] else "o")

def _is_late(state):
    your = state["seat_to_act"]; n = len(state["players"])
    after = 0
    for off in range(1, n):
        s = (your + off) % n
        p = state["players"][s]
        if not p.get("is_folded") and not p.get("is_all_in") and p.get("state") != "busted":
            after += 1
    return after <= _THRESH_SEATS

def decide(state):
    if state.get("type") == "warmup":
        return {"ok": True}
    cards = state["your_cards"]; pot = state["pot"]
    if state["street"] == "preflop":
        if not _is_late(state):
            if state["can_check"]:
                return {"action": "check"}
            return {"action": "fold"}
        hk = _hand_key(cards[0], cards[1])
        if hk in _LATE_OPEN:
            return {"action": "raise", "amount": max(state["min_raise_to"], 300)}
        if state["can_check"]:
            return {"action": "check"}
        return {"action": "fold"}
    if state["can_check"]:
        return {"action": "check"}
    if state["amount_owed"] < pot * 0.25:
        return {"action": "call"}
    return {"action": "fold"}
