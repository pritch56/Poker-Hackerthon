"""Nit-02: tight; folds without premium hand."""
import eval7

BOT_NAME = "Nit-02"
_OPEN = {'AA', 'KK', 'QQ', 'JJ', 'AKs', 'TT', '99', 'AKo', 'AQs', 'AJs', 'KQs'}
_CALL3B = {'AA', 'KK', 'QQ', 'JJ', 'AKs', 'AKo'}
_POSTFLOP_THRESH = 0.7

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
    if "two pair" in ht or "three" in ht or "straight" in ht or "flush" in ht or "full" in ht or "four" in ht:
        return 0.95
    if "pair" in ht:
        # Top pair check
        ranks = "23456789TJQKA"
        my_ranks = sorted([ranks.index(c[0]) for c in cards], reverse=True)
        board_ranks = sorted([ranks.index(c[0]) for c in board], reverse=True)
        if my_ranks[0] == my_ranks[1]:
            return 0.6 if my_ranks[0] > board_ranks[0] else 0.3
        if my_ranks[0] in board_ranks and my_ranks[0] >= board_ranks[0]:
            return 0.55
        return 0.3
    return 0.1

def decide(state):
    if state.get("type") == "warmup":
        return {"ok": True}
    cards = state["your_cards"]
    if state["street"] == "preflop":
        hk = _hand_key(cards[0], cards[1])
        raised = sum(1 for a in state["action_log"] if a.get("action") in ("raise","all_in"))
        if raised >= 2:
            return {"action": "call"} if hk in {"AA","KK"} else {"action": "fold"}
        if raised == 1:
            return {"action": "call"} if hk in _CALL3B else {"action": "fold"}
        if hk in _OPEN:
            return {"action": "raise", "amount": max(state["min_raise_to"], 300)}
        if state["can_check"]:
            return {"action": "check"}
        return {"action": "fold"}
    s = _strength(cards, state["community_cards"])
    if s >= _POSTFLOP_THRESH:
        target = state["current_bet"] + int(state["pot"] * 0.65)
        return {"action": "raise", "amount": max(state["min_raise_to"], target)}
    if state["can_check"]:
        return {"action": "check"}
    if state["amount_owed"] < state["pot"] * 0.2 and s >= 0.5:
        return {"action": "call"}
    return {"action": "fold"}
