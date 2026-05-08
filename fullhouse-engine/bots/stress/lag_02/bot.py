"""LAG-02: loose-aggressive, frequent 3-bets and barrels."""
import random, eval7

BOT_NAME = "LAG-02"
_RNG = random.Random(5002)
_OPEN = {'AA', 'KK', 'QQ', 'JJ', 'AKs', 'TT', '99', 'AKo', 'AQs', 'AJs', 'KQs', 'AQo', '88', '77', 'ATs', 'KJs', 'QJs', 'AJo', 'KQo', 'JTs', 'T9s', 'KTs', '66', '55', '44', '33', '22', 'ATo', 'KJo', 'QTs', '98s', '87s', 'A9s', 'A8s', 'A7s', 'A5s', 'A4s', 'A3s', 'A2s', 'K9s', 'Q9s', 'J9s', 'T8s', '97s', '86s', '76s', '65s', '54s', 'KTo', 'QJo', 'JTo', 'T9o', 'A6s', 'K8s', 'K7s', 'Q8s', 'J8s', 'T7s', '96s', '85s', '75s', '64s', 'A9o', 'A8o', 'A7o', 'A6o', 'K9o', 'Q9o', 'J9o', 'T9o', '98o'}
_3BP = 0.3
_BARREL = 0.65

def _hand_key(c1, c2):
    r = "23456789TJQKA"
    if r.index(c1[0]) < r.index(c2[0]):
        c1, c2 = c2, c1
    if c1[0] == c2[0]:
        return c1[0] + c2[0]
    return c1[0] + c2[0] + ("s" if c1[1] == c2[1] else "o")

def decide(state):
    if state.get("type") == "warmup":
        return {"ok": True}
    cards = state["your_cards"]; pot = state["pot"]
    raised = sum(1 for a in state["action_log"] if a.get("action") in ("raise","all_in"))
    if state["street"] == "preflop":
        hk = _hand_key(cards[0], cards[1])
        if raised >= 2:
            return {"action": "call"} if hk in {"AA","KK","QQ","JJ","AKs","AKo"} else {"action": "fold"}
        if raised == 1:
            if hk in {"AA","KK","QQ","AKs","AKo"} or (hk in _OPEN and _RNG.random() < _3BP):
                t = state["current_bet"] * 3
                return {"action": "raise", "amount": max(state["min_raise_to"], t)}
            if hk in _OPEN and state["amount_owed"] < state["your_stack"] * 0.18:
                return {"action": "call"}
            return {"action": "fold"}
        if hk in _OPEN:
            return {"action": "raise", "amount": max(state["min_raise_to"], 300)}
        if state["can_check"]:
            return {"action": "check"}
        return {"action": "fold"}
    # Postflop: aggressive
    if state["can_check"]:
        if _RNG.random() < _BARREL:
            target = state["current_bet"] + int(pot * 0.65)
            return {"action": "raise", "amount": max(state["min_raise_to"], target)}
        return {"action": "check"}
    pot_odds = state["amount_owed"] / max(pot + state["amount_owed"], 1)
    if pot_odds < 0.30 and _RNG.random() < _BARREL * 0.7:
        target = state["current_bet"] + int(pot * 0.8)
        return {"action": "raise", "amount": max(state["min_raise_to"], target)}
    if pot_odds < 0.35:
        return {"action": "call"}
    return {"action": "fold"}
