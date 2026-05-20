"""ProBot — professional tight-aggressive with full equity stack.

Style: very selective preflop (top 15-25% by position), then hammer value
postflop with proportional bet sizing. Never bluffs without fold equity.
Tracks pot commitment correctly and never gets pot-committed by accident.

Key differences from EquityBot:
  * Tighter preflop (won't open garbage from EP)
  * Larger value bets when strong (extracts more)
  * Commitment-aware: jams when SPR is favourable, avoids marginal all-ins
  * Stack preservation: tightens when below 50% starting stack
"""
import random
import eval7

BOT_NAME = "ProBot"

RANK_ORDER    = "23456789TJQKA"
BIG_BLIND     = 100
STARTING_STACK = 10_000

# Position-scaled open thresholds (tighter than EquityBot across the board).
_OPEN_THRESH = {
    "ep":  0.635,   # ~top 12% (UTG/UTG+1)
    "mp":  0.595,   # ~top 18%
    "co":  0.555,   # ~top 25%
    "btn": 0.505,   # ~top 38%
    "sb":  0.530,   # ~top 30% (OOP postflop)
    "bb":  0.0,     # BB never opens; defend separately
}


def _monte_carlo_equity(my_cards, board, num_opp, n_samples=180):
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


def _position_label(seat, players, action_log):
    active  = sorted(p["seat"] for p in players if p.get("state") != "busted")
    n       = len(active)
    if n < 2 or seat not in active:
        return "mp"
    sb_seat = next((a["seat"] for a in action_log if a.get("action") == "small_blind"), None)
    if sb_seat is None or sb_seat not in active:
        return "mp"
    if n == 2:
        return "btn" if seat == sb_seat else "bb"
    sb_idx     = active.index(sb_seat)
    dealer     = active[(sb_idx - 1) % n]
    your_idx   = active.index(seat)
    dealer_idx = active.index(dealer)
    offset     = (your_idx - dealer_idx) % n
    if offset == 0:     return "btn"
    if offset == 1:     return "sb"
    if offset == 2:     return "bb"
    if offset == n - 1: return "co"
    if n >= 5 and offset == 3: return "ep"
    return "mp"


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
    pos_label   = _position_label(seat, players, action_log)
    spr         = stack / max(pot, 1)
    preserve    = stack < 0.50 * STARTING_STACK

    # ── Preflop ──────────────────────────────────────────────────────────
    if street == "preflop":
        score    = _preflop_score(my_cards)
        raised_n = sum(1 for a in action_log if a.get("action") in ("raise","all_in"))
        thresh   = _OPEN_THRESH.get(pos_label, 0.575)

        # Short-stack push/fold.
        if stack <= 15 * BIG_BLIND and owed > 0:
            if score >= 0.52 or stack <= 8 * BIG_BLIND:
                return {"action": "all_in"}
            pot_odds = owed / (pot + owed) if pot + owed > 0 else 1.0
            if pot_odds < 0.25:
                return {"action": "call"}
            return {"action": "fold"}

        n_callers   = sum(1 for a in action_log if a.get("action") == "call")
        open_size   = max(BIG_BLIND * (3 + n_callers), min_r)
        threebet_to = max(min_r, int(current_bet * 3.2))

        if raised_n == 0:
            if pos_label == "bb" and can_check:
                return {"action": "check"}
            if score >= thresh:
                return {"action": "raise", "amount": min(open_size, stack + my_bet)}
            if pos_label == "bb":
                pot_odds = owed / (pot + owed) if pot + owed > 0 else 1.0
                if score >= 0.50 and pot_odds < 0.22:
                    return {"action": "call"}
            if can_check:
                return {"action": "check"}
            return {"action": "fold"}

        # Facing a raise: 3-bet value hands, call strong hands, fold rest.
        if raised_n == 1:
            if score >= 0.79:
                return {"action": "raise", "amount": min(threebet_to, stack + my_bet)}
            pot_odds = owed / (pot + owed) if pot + owed > 0 else 1.0
            if score >= 0.60 and pot_odds < 0.22:
                return {"action": "call"}
            if score >= 0.50 and pot_odds < 0.15:
                return {"action": "call"}
            if can_check:
                return {"action": "check"}
            return {"action": "fold"}

        # Facing 3-bet+: only premiums.
        if score >= 0.83:
            fourbet = max(min_r, int(current_bet * 2.5))
            return {"action": "raise", "amount": min(fourbet, stack + my_bet)}
        if score >= 0.76 and owed < 0.22 * stack:
            return {"action": "call"}
        return {"action": "fold"}

    # ── Postflop: value-heavy equity decisions ────────────────────────────
    equity   = _monte_carlo_equity(my_cards, board, num_opp)
    pot_odds = owed / (pot + owed) if owed > 0 and pot + owed > 0 else 0.0

    # Tighten all-in thresholds in preservation mode.
    preserve_bonus = 0.06 if preserve else 0.0
    val_thresh     = 0.55 - pos_float * 0.05

    if can_check:
        if equity >= val_thresh:
            # Size aggressively — extract maximum value.
            edge     = (equity - 0.5) * 2
            fraction = 0.55 + edge * 0.55     # 0.55–1.10 pot
            fraction = min(1.0, fraction)
            target   = max(min_r, int(pot * fraction))
            target   = min(target, stack + my_bet)
            return {"action": "raise", "amount": target}
        # No bluffing without a real reason (fold equity).
        return {"action": "check"}

    # Commitment logic: jam when clearly ahead and SPR is right.
    if equity >= 0.80 + preserve_bonus and spr <= 3.0:
        return {"action": "all_in"}
    if equity >= 0.72 + preserve_bonus and spr <= 1.5 and num_opp <= 2:
        return {"action": "all_in"}

    margin = 0.04 + (1.0 - pos_float) * 0.04
    if equity > pot_odds + margin:
        # Raise with strong hands to build pot.
        if equity > 0.70 and stack > owed * 3:
            raise_to = max(min_r, int(current_bet * 2.8 + pot * 0.6))
            raise_to = min(raise_to, stack + my_bet)
            return {"action": "raise", "amount": raise_to}
        return {"action": "call"}

    # Chase cheap draws.
    if equity >= pot_odds and owed < 0.10 * stack and street != "river":
        return {"action": "call"}

    return {"action": "fold"}
