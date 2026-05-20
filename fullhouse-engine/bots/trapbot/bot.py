"""TrapBot — passive/trapping style with MC equity.

Key character traits:
  * Slow-plays strong hands (check-calls instead of betting out)
  * Check-raises as the primary aggressive action (traps opponents who bluff)
  * Thin value bets only on the river when opponents can't fold
  * Calls down wide with draws (implied odds focus)

This style exploits opponents who over-bet and barrel too frequently.
"""
import random
import eval7

BOT_NAME = "TrapBot"

RANK_ORDER = "23456789TJQKA"
BIG_BLIND  = 100


def _monte_carlo_equity(my_cards, board, num_opp, n_samples=160):
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
        samp    = random.sample(deck, needed)
        run_out = board_e7 + samp[:board_left]
        my_sc   = eval7.evaluate(my_e7 + run_out)
        opp_b   = max(
            eval7.evaluate(samp[board_left + i*2 : board_left + (i+1)*2] + run_out)
            for i in range(num_opp)
        )
        if my_sc > opp_b:
            wins += 1
        elif my_sc == opp_b:
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


def _position_float(seat, players):
    active = [p for p in players if p["state"] != "busted"]
    n      = len(active)
    if n <= 1:
        return 1.0
    seats = [p["seat"] for p in active]
    try:
        return seats.index(seat) / (n - 1)
    except ValueError:
        return 0.5


def decide(state):
    if state.get("type") == "warmup":
        return {"action": "fold"}

    street      = state["street"]
    my_cards    = state["your_cards"]
    board       = state["community_cards"]
    pot         = state["pot"]
    owed        = state["amount_owed"]
    stack       = state["your_stack"]
    seat        = state["seat_to_act"]
    can_check   = state["can_check"]
    min_r       = state["min_raise_to"]
    my_bet      = state["your_bet_this_street"]
    players     = state["players"]
    action_log  = state.get("action_log", [])
    current_bet = state["current_bet"]

    active_opps = [p for p in players if p["state"] in ("active","all_in") and p["seat"] != seat]
    num_opp     = max(len(active_opps), 1)
    pos_float   = _position_float(seat, players)

    # ── Preflop: call wide to set traps, open/3-bet premiums ─────────────
    if street == "preflop":
        score    = _preflop_score(my_cards)
        raised_n = sum(1 for a in action_log if a.get("action") in ("raise","all_in"))

        if raised_n == 0:
            if score >= 0.72:
                raise_to = min(max(BIG_BLIND * 3, min_r), stack + my_bet)
                return {"action": "raise", "amount": raise_to}
            if can_check:
                return {"action": "check"}
            # Limp/call wide to set traps.
            if score >= 0.45 and owed <= BIG_BLIND:
                return {"action": "call"}
            return {"action": "fold"}

        if raised_n >= 1:
            # 3-bet only strong premiums; flat-call wide range.
            if score >= 0.82:
                threebet = min(max(min_r, int(current_bet * 3)), stack + my_bet)
                return {"action": "raise", "amount": threebet}
            pot_odds = owed / (pot + owed) if pot + owed > 0 else 1.0
            # Flat very wide — traps work better with wide ranges.
            if score >= 0.50 and pot_odds < 0.28:
                return {"action": "call"}
            if score >= 0.42 and pot_odds < 0.18:
                return {"action": "call"}
            if can_check:
                return {"action": "check"}
            return {"action": "fold"}

    # ── Postflop: check-raise trapping ────────────────────────────────────
    equity   = _monte_carlo_equity(my_cards, board, num_opp)
    pot_odds = owed / (pot + owed) if owed > 0 and pot + owed > 0 else 0.0

    if can_check:
        # Very strong hand: check to induce (will check-raise if they bet).
        if equity >= 0.72:
            return {"action": "check"}

        # Moderate strength on river: value bet thin (opponent can't fold river).
        if street == "river" and equity >= 0.58:
            edge     = (equity - 0.5) * 2
            fraction = 0.40 + edge * 0.40
            target   = max(min_r, int(pot * fraction))
            target   = min(target, stack + my_bet)
            return {"action": "raise", "amount": target}

        # Otherwise: check to control pot and induce bluffs.
        return {"action": "check"}

    # Facing a bet: trap by calling, check-raise the especially strong hands.
    bet_this = my_bet  # how much we've put in on this street already
    we_checked_then_bet = (bet_this == 0 and owed > 0)  # classic check-raise spot

    if we_checked_then_bet and equity >= 0.75:
        # Check-raise as a trap — big sizing to extract max.
        raise_to = max(min_r, int(current_bet * 3.0))
        raise_to = min(raise_to, stack + my_bet)
        return {"action": "raise", "amount": raise_to}

    if equity >= 0.72 and owed > 0.30 * stack:
        # All-in with monster vs big bet.
        return {"action": "all_in"}

    # Standard equity-based call (wide calling range to trap bluffs).
    margin = 0.02 + (1.0 - pos_float) * 0.02   # very loose calls (trapping)
    if equity > pot_odds + margin:
        return {"action": "call"}

    # Still call with draws when cheap.
    if equity >= pot_odds and owed < 0.12 * stack and street != "river":
        return {"action": "call"}

    return {"action": "fold"}
