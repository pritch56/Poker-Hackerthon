"""PushFold-01: only jams or folds."""

BOT_NAME = "PushFold-01"
_JAM = {'AA', 'KK', 'QQ', 'JJ', 'AKs', 'TT', '99', 'AKo', 'AQs', 'AJs', 'KQs'}
_CALL_JAM = {'AA', 'KK', 'QQ'}

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
    cards = state["your_cards"]
    if state["street"] == "preflop":
        hk = _hand_key(cards[0], cards[1])
        raised = sum(1 for a in state["action_log"] if a.get("action") in ("raise","all_in"))
        if raised:
            if hk in _CALL_JAM:
                return {"action": "all_in"}
            return {"action": "fold"}
        if hk in _JAM:
            return {"action": "all_in"}
        if state["can_check"]:
            return {"action": "check"}
        return {"action": "fold"}
    # Postflop: never voluntarily commit
    if state["can_check"]:
        return {"action": "check"}
    return {"action": "fold"}
