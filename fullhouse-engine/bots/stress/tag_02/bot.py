"""TAG-02: tight-aggressive with c-bet."""
import random, eval7

BOT_NAME = "TAG-02"
_RNG = random.Random(4002)
_OPEN = {'AA', 'KK', 'QQ', 'JJ', 'AKs', 'TT', '99', 'AKo', 'AQs', 'AJs', 'KQs', 'AQo', '88', '77', 'ATs', 'KJs', 'QJs', 'AJo', 'KQo', 'JTs', 'T9s', 'KTs', '66'}
_CBET = 0.55
_VAL = 0.6

def _hand_key(c1, c2):
    r = "23456789TJQKA"
    if r.index(c1[0]) < r.index(c2[0]):
        c1, c2 = c2, c1
    if c1[0] == c2[0]:
        return c1[0] + c2[0]
    return c1[0] + c2[0] + ("s" if c1[1] == c2[1] else "o")

def _strength(cards, board):
    if len(board) < 3:
        return 0.0
    full = [eval7.Card(c) for c in cards + board]
    s = eval7.evaluate(full)
    ht = eval7.handtype(s).lower()
    if "straight" in ht or "flush" in ht or "full" in ht or "four" in ht:
        return 0.95
    if "three" in ht or "two pair" in ht:
        return 0.85
    if "pair" in ht:
        ranks = "23456789TJQKA"
        my_ranks = sorted([ranks.index(c[0]) for c in cards], reverse=True)
        board_ranks = sorted([ranks.index(c[0]) for c in board], reverse=True)
        if my_ranks[0] == my_ranks[1]:
            return 0.7 if my_ranks[0] > board_ranks[0] else 0.4
        if my_ranks[0] in board_ranks and my_ranks[0] >= board_ranks[0]:
            return 0.6
        return 0.35
    return 0.15

def decide(state):
    if state.get("type") == "warmup":
        return {"ok": True}
    cards = state["your_cards"]; pot = state["pot"]
    raised = sum(1 for a in state["action_log"] if a.get("action") in ("raise","all_in"))
    if state["street"] == "preflop":
        hk = _hand_key(cards[0], cards[1])
        if raised >= 2:
            return {"action": "call"} if hk in {"AA","KK","QQ","AKs","AKo"} else {"action": "fold"}
        if raised == 1:
            if hk in {"AA","KK","QQ","AKs"}:
                t = state["current_bet"] * 3
                return {"action": "raise", "amount": max(state["min_raise_to"], t)}
            if hk in _OPEN and state["amount_owed"] < state["your_stack"] * 0.15:
                return {"action": "call"}
            return {"action": "fold"}
        if hk in _OPEN:
            return {"action": "raise", "amount": max(state["min_raise_to"], 300)}
        if state["can_check"]:
            return {"action": "check"}
        return {"action": "fold"}
    s = _strength(cards, state["community_cards"])
    am_aggr = state["seat_to_act"] in {a["seat"] for a in state["action_log"] if a.get("action")=="raise"}
    if state["can_check"]:
        if s >= _VAL:
            target = state["current_bet"] + int(pot * 0.65)
            return {"action": "raise", "amount": max(state["min_raise_to"], target)}
        if am_aggr and _RNG.random() < _CBET:
            target = state["current_bet"] + int(pot * 0.55)
            return {"action": "raise", "amount": max(state["min_raise_to"], target)}
        return {"action": "check"}
    pot_odds = state["amount_owed"] / max(pot + state["amount_owed"], 1)
    if s >= _VAL:
        target = state["current_bet"] + int(pot * 0.7)
        return {"action": "raise", "amount": max(state["min_raise_to"], target)}
    if s >= 0.45 and pot_odds < 0.3:
        return {"action": "call"}
    if s >= 0.6:
        return {"action": "call"}
    return {"action": "fold"}
