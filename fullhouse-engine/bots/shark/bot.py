"""Shark — tight preflop hand selection, MC equity postflop, position-aware."""
import random
import eval7

BOT_NAME = "The Shark"

RANK_ORDER = "23456789TJQKA"
BIG_BLIND  = 100

STRONG_HANDS = {
    ("A","A"), ("K","K"), ("Q","Q"), ("J","J"), ("T","T"),
    ("A","K"), ("A","Q"), ("A","J"), ("K","Q"),
}


def _hand_strength(cards):
    ranks  = tuple(sorted([c[0] for c in cards], reverse=True))
    suited = cards[0][1] == cards[1][1]
    if ranks in STRONG_HANDS:
        return "strong"
    if ranks[0] in "AKQJT" or suited:
        return "medium"
    return "weak"


def _position_float(seat, players):
    active = [p for p in players if p["state"] != "busted"]
    n      = len(active)
    if n <= 1:
        return 1.0
    seats = [p["seat"] for p in active]
    try:
        idx = seats.index(seat)
    except ValueError:
        return 0.5
    return idx / (n - 1)


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
    pos_float   = _position_float(seat, players)

    # Preflop: tight hand selection, same as original Shark.
    if street == "preflop":
        strength = _hand_strength(my_cards)
        if strength == "strong":
            raise_to = min(max(min_r, BIG_BLIND * 3), stack + my_bet)
            return {"action": "raise", "amount": raise_to}
        if strength == "medium" and pos_float > 0.45:
            if can_check:
                return {"action": "check"}
            pot_odds = owed / (pot + owed) if pot + owed > 0 else 1.0
            if pot_odds < 0.22:
                return {"action": "call"}
        if can_check:
            return {"action": "check"}
        return {"action": "fold"}

    # Postflop: MC equity replaces position-random heuristic.
    equity   = _monte_carlo_equity(my_cards, board, num_opp)
    pot_odds = owed / (pot + owed) if owed > 0 and pot + owed > 0 else 0.0

    # Value-bet threshold tightens OOP, loosens IP (same calibration as EquityBot).
    val_thresh = 0.56 - pos_float * 0.06

    if can_check:
        if equity >= val_thresh:
            edge     = (equity - 0.5) * 2
            fraction = 0.45 + edge * 0.50
            target   = max(min_r, int(pot * fraction))
            target   = min(target, stack + my_bet)
            return {"action": "raise", "amount": target}
        # Occasional semi-bluff in position with air.
        if equity < 0.30 and pos_float > 0.60 and random.random() < 0.18:
            target = max(min_r, int(pot * 0.50))
            target = min(target, stack + my_bet)
            return {"action": "raise", "amount": target}
        return {"action": "check"}

    margin = 0.04 + (1.0 - pos_float) * 0.04
    if equity > pot_odds + margin:
        if equity > 0.70 and stack > owed * 2:
            raise_to = max(min_r, int(state["current_bet"] * 2.8))
            raise_to = min(raise_to, stack + my_bet)
            return {"action": "raise", "amount": raise_to}
        return {"action": "call"}
    return {"action": "fold"}
