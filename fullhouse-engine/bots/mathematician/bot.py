"""Mathematician — calls when MC equity beats pot odds; bets for value."""
import random
import eval7

BOT_NAME = "The Mathematician"

RANK_ORDER = "23456789TJQKA"
BIG_BLIND  = 100


def _monte_carlo_equity(my_cards, board, num_opp, n_samples=150):
    if num_opp <= 0:
        return 1.0
    my_e7    = [eval7.Card(c) for c in my_cards]
    board_e7 = [eval7.Card(c) for c in board]
    known    = set(my_cards + board)
    deck     = [eval7.Card(r + s) for r in RANK_ORDER for s in "shdc" if r + s not in known]
    needed   = (5 - len(board_e7)) + 2 * num_opp
    if len(deck) < needed:
        return 0.5
    wins = ties = 0
    board_left = 5 - len(board_e7)
    for _ in range(n_samples):
        samp     = random.sample(deck, needed)
        run_out  = board_e7 + samp[:board_left]
        my_score = eval7.evaluate(my_e7 + run_out)
        opp_best = max(
            eval7.evaluate(samp[board_left + i*2 : board_left + (i+1)*2] + run_out)
            for i in range(num_opp)
        )
        if my_score > opp_best:
            wins += 1
        elif my_score == opp_best:
            ties += 0.5
    return (wins + ties) / n_samples


def _preflop_score(cards):
    r1, r2  = RANK_ORDER.index(cards[0][0]), RANK_ORDER.index(cards[1][0])
    suited  = cards[0][1] == cards[1][1]
    if r1 < r2:
        r1, r2 = r2, r1
    if r1 == r2:
        return 0.50 + r1 / 24.0
    gap        = r1 - r2
    base       = (r1 + r2) / 24.0
    suit_bonus = 0.04 if suited else 0.0
    conn_bonus = max(0.0, (4 - gap) * 0.012)
    return min(1.0, base + suit_bonus + conn_bonus)


def decide(state):
    if state.get("type") == "warmup":
        return {"action": "fold"}

    street    = state["street"]
    my_cards  = state["your_cards"]
    board     = state["community_cards"]
    pot       = state["pot"]
    owed      = state["amount_owed"]
    stack     = state["your_stack"]
    seat      = state["seat_to_act"]
    can_check = state["can_check"]
    min_r     = state["min_raise_to"]
    my_bet    = state["your_bet_this_street"]
    players   = state["players"]

    active_opps = [p for p in players if p["state"] in ("active", "all_in") and p["seat"] != seat]
    num_opp     = max(len(active_opps), 1)

    # Preflop: call/raise with mathematically justified hand strength.
    if street == "preflop":
        score = _preflop_score(my_cards)
        if score >= 0.72:
            raise_to = min(max(BIG_BLIND * 3, min_r), stack + my_bet)
            return {"action": "raise", "amount": raise_to}
        if can_check:
            return {"action": "check"}
        pot_odds = owed / (pot + owed) if pot + owed > 0 else 1.0
        # Call if hand score exceeds the mathematical break-even threshold.
        if score >= 0.50 and pot_odds < 0.30:
            return {"action": "call"}
        if score >= 0.40 and pot_odds < 0.18:
            return {"action": "call"}
        return {"action": "fold"}

    # Postflop: full MC equity vs pot odds with a value-bet layer.
    equity   = _monte_carlo_equity(my_cards, board, num_opp)
    pot_odds = owed / (pot + owed) if owed > 0 and pot + owed > 0 else 0.0

    if can_check:
        if equity >= 0.58:
            # Value bet — size proportional to equity advantage.
            edge     = (equity - 0.5) * 2
            fraction = 0.45 + edge * 0.45
            target   = max(min_r, int(pot * fraction))
            target   = min(target, stack + my_bet)
            return {"action": "raise", "amount": target}
        return {"action": "check"}

    # Call if equity justifies it (equity > pot_odds + small margin for EV).
    margin = 0.04
    if equity > pot_odds + margin:
        if equity > 0.70 and stack > owed * 2:
            raise_to = max(min_r, int(state["current_bet"] * 2.8))
            raise_to = min(raise_to, stack + my_bet)
            return {"action": "raise", "amount": raise_to}
        return {"action": "call"}
    return {"action": "fold"}
