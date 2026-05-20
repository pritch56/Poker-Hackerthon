"""
EquityBot — GTO-approximate opponent using Monte Carlo equity simulation.

Makes all decisions from computed hand equity vs pot odds, with
position-aware sizing and aggression.  Far stronger than hand-crafted
heuristic bots — use it as the primary benchmark.

Decision logic:
  Preflop  : rank/suitedness score mapped to a position-scaled threshold
  Postflop : 150-sample Monte Carlo equity via eval7; call/bet/fold from
             equity vs pot-odds with a small risk-premium margin
"""

import eval7
import random

BOT_NAME = "EquityBot"

RANK_ORDER = "23456789TJQKA"   # index 0 (deuce) … 12 (ace)
BIG_BLIND  = 100


# ---------------------------------------------------------------------------
# Preflop hand scoring
# ---------------------------------------------------------------------------

def _rank(c: str) -> int:
    return RANK_ORDER.index(c[0])


def _preflop_score(cards: list) -> float:
    """
    Returns 0-1 strength score for two hole cards.
    Pairs: 0.50 (22) – 1.00 (AA).
    Non-pairs: based on combined rank + suitedness + connectedness.
    """
    r1, r2 = _rank(cards[0]), _rank(cards[1])
    suited = cards[0][1] == cards[1][1]
    if r1 < r2:
        r1, r2 = r2, r1               # r1 >= r2

    if r1 == r2:                       # pocket pair
        return 0.50 + r1 / 24.0

    gap         = r1 - r2
    base        = (r1 + r2) / 24.0    # 0-1
    suit_bonus  = 0.04 if suited else 0.0
    conn_bonus  = max(0.0, (4 - gap) * 0.012)
    return min(1.0, base + suit_bonus + conn_bonus)


# Position-scaled VPIP thresholds (0 = tightest, 5 = loosest)
# [UTG, UTG+1, CO, BTN, SB, BB]
_VPIP_THRESHOLD = [0.62, 0.58, 0.52, 0.44, 0.54, 0.38]


def _position_idx(seat: int, players: list) -> int:
    """0-5 position index (0=EP, 5=BB/most liberal)."""
    active = [p for p in players if p["state"] != "busted"]
    n = len(active)
    if n <= 1:
        return 3
    seats = [p["seat"] for p in active]
    try:
        idx = seats.index(seat)
    except ValueError:
        return 2
    return min(5, int(idx / max(n - 1, 1) * 5))


def _position_float(seat: int, players: list) -> float:
    """0.0 (early) … 1.0 (latest / dealer)."""
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


# ---------------------------------------------------------------------------
# Monte Carlo equity
# ---------------------------------------------------------------------------

def _monte_carlo_equity(my_cards: list, board: list, num_opp: int,
                        n_samples: int = 150) -> float:
    """Win/tie equity vs `num_opp` random opponent hands."""
    if num_opp <= 0:
        return 1.0

    my_e7    = [eval7.Card(c) for c in my_cards]
    board_e7 = [eval7.Card(c) for c in board]
    known    = set(my_cards + board)

    deck = [eval7.Card(r + s)
            for r in RANK_ORDER for s in "shdc"
            if r + s not in known]

    board_needed  = 5 - len(board_e7)
    cards_needed  = board_needed + 2 * num_opp
    if len(deck) < cards_needed:
        return 0.5

    wins = ties = 0
    for _ in range(n_samples):
        sample    = random.sample(deck, cards_needed)
        run_out   = board_e7 + sample[:board_needed]
        my_score  = eval7.evaluate(my_e7 + run_out)
        opp_best  = max(
            eval7.evaluate(sample[board_needed + i * 2: board_needed + (i + 1) * 2] + run_out)
            for i in range(num_opp)
        )
        if my_score > opp_best:
            wins += 1
        elif my_score == opp_best:
            ties += 0.5

    return (wins + ties) / n_samples


# ---------------------------------------------------------------------------
# Sizing helpers
# ---------------------------------------------------------------------------

def _bet_size(pot: int, fraction: float, min_raise_to: int,
              my_bet: int, stack: int) -> int:
    """Return a valid raise-to amount for a bet of `fraction` of pot."""
    target = max(int(pot * fraction), min_raise_to)
    return min(target, stack + my_bet)   # can't bet more than stack


def _raise_size(pot: int, current_bet: int, min_raise_to: int,
                my_bet: int, stack: int) -> int:
    """Re-raise to roughly 3x the current bet, at least min_raise_to."""
    target = max(current_bet * 3, min_raise_to, int(pot * 0.7) + current_bet)
    return min(target, stack + my_bet)


# ---------------------------------------------------------------------------
# Main decision function
# ---------------------------------------------------------------------------

def decide(state: dict) -> dict:
    if state.get("type") == "warmup":
        return {"action": "fold"}

    street        = state["street"]
    my_cards      = state["your_cards"]
    board         = state["community_cards"]
    pot           = state["pot"]
    owed          = state["amount_owed"]
    stack         = state["your_stack"]
    seat          = state["seat_to_act"]
    can_check     = state["can_check"]
    min_raise_to  = state["min_raise_to"]
    my_bet        = state["your_bet_this_street"]
    current_bet   = state["current_bet"]
    players       = state["players"]

    active_opps = [p for p in players
                   if p["state"] in ("active", "all_in") and p["seat"] != seat]
    num_opp     = max(len(active_opps), 1)
    pos_float   = _position_float(seat, players)

    # -----------------------------------------------------------------------
    # PREFLOP
    # -----------------------------------------------------------------------
    if street == "preflop":
        score     = _preflop_score(my_cards)
        pos_idx   = _position_idx(seat, players)
        threshold = _VPIP_THRESHOLD[pos_idx]

        if score >= threshold:
            if score >= 0.78:
                # Premium hand — raise big
                raise_to = _bet_size(pot, 3.0, min_raise_to * 2, my_bet, stack)
                return {"action": "raise", "amount": raise_to}

            if score >= 0.65 and pos_float >= 0.4:
                # Strong hand in position — standard open
                raise_to = _bet_size(pot, 0.0, min_raise_to, my_bet, stack)
                # open to 2.5–3x BB
                raise_to = max(raise_to, BIG_BLIND * 3)
                raise_to = min(raise_to, stack + my_bet)
                return {"action": "raise", "amount": raise_to}

            # Marginal hand — call if cheap
            if can_check:
                return {"action": "check"}
            pot_odds = owed / (pot + owed) if (pot + owed) > 0 else 1.0
            if pot_odds < 0.22 or (pot_odds < 0.32 and pos_float > 0.5):
                return {"action": "call"}

        if can_check:
            return {"action": "check"}
        return {"action": "fold"}

    # -----------------------------------------------------------------------
    # POSTFLOP
    # -----------------------------------------------------------------------
    equity    = _monte_carlo_equity(my_cards, board, num_opp)
    pot_odds  = owed / (pot + owed) if owed > 0 and (pot + owed) > 0 else 0.0

    # Value-bet threshold: tighten OOP, loosen IP
    val_thresh   = 0.56 - pos_float * 0.06     # 0.56 OOP → 0.50 IP
    # Bluff threshold: only bluff in position with air
    bluff_thresh = 0.28

    if can_check:
        if equity >= val_thresh:
            # Size bet proportional to equity advantage
            edge     = (equity - 0.5) * 2          # 0-1
            fraction = 0.45 + edge * 0.55           # 45–100% pot
            bet = _bet_size(pot, fraction, min_raise_to, my_bet, stack)
            return {"action": "raise", "amount": bet}

        if (equity < bluff_thresh and pos_float > 0.65
                and random.random() < 0.22):
            # Semi-bluff / pure bluff in position
            bet = _bet_size(pot, 0.55, min_raise_to, my_bet, stack)
            return {"action": "raise", "amount": bet}

        return {"action": "check"}

    # Facing a bet
    margin = 0.04 + (1.0 - pos_float) * 0.04   # larger margin OOP
    if equity > pot_odds + margin:
        # Strong enough to raise?
        if equity > 0.72 and stack > owed * 2:
            raise_to = _raise_size(pot, current_bet, min_raise_to, my_bet, stack)
            return {"action": "raise", "amount": raise_to}
        return {"action": "call"}

    return {"action": "fold"}
