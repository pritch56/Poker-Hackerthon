"""Aggressor — raises constantly, sizes bets by MC equity edge."""
import random
import eval7

BOT_NAME = "The Aggressor"

RANK_ORDER = "23456789TJQKA"
BIG_BLIND = 100


def _monte_carlo_equity(my_cards, board, num_opp, n_samples=120):
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


def _position_float(seat, players):
    active = [p for p in players if p["state"] != "busted"]
    n = len(active)
    if n <= 1:
        return 1.0
    seats = [p["seat"] for p in active]
    try:
        idx = seats.index(seat)
    except ValueError:
        return 0.5
    return idx / (n - 1)


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

    # Preflop: still aggro — raise 75% of the time, size up vs callers.
    if street == "preflop":
        if random.random() < 0.75:
            raise_to = max(min_r, BIG_BLIND * 3)
            raise_to = min(raise_to * random.randint(1, 2), stack + my_bet)
            return {"action": "raise", "amount": raise_to}
        if can_check:
            return {"action": "check"}
        pot_odds = owed / (pot + owed) if pot + owed > 0 else 1.0
        if pot_odds < 0.30:
            return {"action": "call"}
        return {"action": "fold"}

    # Postflop: equity-scaled aggression.
    equity   = _monte_carlo_equity(my_cards, board, num_opp)
    pot_odds = owed / (pot + owed) if owed > 0 and pot + owed > 0 else 0.0

    if can_check:
        # Always bet — size based on equity edge.
        edge     = max(0.0, equity - 0.5)
        fraction = 0.40 + edge * 1.20     # 0.40–1.0 pot
        fraction = min(1.0, fraction)
        if equity < 0.38 and random.random() < 0.35:
            fraction = 0.55              # pure bluff at modest size
        elif equity < 0.38:
            return {"action": "check"}
        target = max(min_r, int(pot * fraction))
        target = min(target, stack + my_bet)
        return {"action": "raise", "amount": target}

    # Facing a bet: call/raise with equity edge, fold without.
    if equity > 0.75 and stack > owed * 2:
        raise_to = max(min_r, int(state["current_bet"] * 2.5))
        raise_to = min(raise_to, stack + my_bet)
        return {"action": "raise", "amount": raise_to}
    if equity > pot_odds + 0.04:
        return {"action": "call"}
    return {"action": "fold"}
