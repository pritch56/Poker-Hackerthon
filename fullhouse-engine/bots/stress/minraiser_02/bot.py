"""MinRaiser-02: only ever min-raises."""

BOT_NAME = "MinRaiser-02"
_OPEN = {'AA', 'KK', 'QQ', 'JJ', 'AKs', 'TT', '99', 'AKo', 'AQs', 'AJs', 'KQs', 'AQo', '88', '77', 'ATs', 'KJs', 'QJs', 'AJo', 'KQo', 'JTs', 'T9s', 'KTs', '66'}
_CALL = 0.3

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
    if state["street"] == "preflop":
        hk = _hand_key(cards[0], cards[1])
        raised = sum(1 for a in state["action_log"] if a.get("action") in ("raise","all_in"))
        if hk in _OPEN:
            return {"action": "raise", "amount": state["min_raise_to"]}
        if raised >= 1 and hk in {"AA","KK","QQ","JJ","TT","AKs","AKo"}:
            return {"action": "call"}
        if state["can_check"]:
            return {"action": "check"}
        return {"action": "fold"}
    if state["can_check"]:
        if hk_strength(cards, state["community_cards"]) >= 0.6:
            return {"action": "raise", "amount": state["min_raise_to"]}
        return {"action": "check"}
    if state["amount_owed"] < pot * _CALL:
        return {"action": "call"}
    return {"action": "fold"}

def hk_strength(cards, board):
    if len(board) < 3:
        return 0.0
    import eval7
    full = [eval7.Card(c) for c in cards + board]
    ht = eval7.handtype(eval7.evaluate(full)).lower()
    if "two" in ht or "three" in ht or "straight" in ht or "flush" in ht or "full" in ht:
        return 0.85
    if "pair" in ht:
        return 0.5
    return 0.1
