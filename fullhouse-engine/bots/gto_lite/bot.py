"""GTO-Lite — GTO-approximate preflop ranges + MC equity postflop.

Uses published 6-max CFR-approximate open/3-bet/defend ranges preflop,
then switches to proportional MC equity sizing postflop with balanced
bet/check frequencies so opponents can't read its hand strength from sizing.
"""
import random
import eval7

BOT_NAME = "GTO-Lite"

RANK_ORDER = "23456789TJQKA"
BIG_BLIND  = 100

# ── Preflop range tables (6-max CFR-approximate) ──────────────────────────

GTO_OPEN_UTG = {
    "AA","KK","QQ","JJ","TT","99","88",
    "AKs","AKo","AQs","AQo","AJs","ATs","KQs","KJs","QJs",
}
GTO_OPEN_MP = GTO_OPEN_UTG | {
    "77","66","AJo","KQo","KTs","QTs","JTs","ATo","T9s","98s","87s","76s",
}
GTO_OPEN_CO = GTO_OPEN_MP | {
    "55","44","33","22",
    "A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s",
    "K9s","Q9s","J9s","T8s","KJo","QJo","JTo","65s",
}
GTO_OPEN_BTN = GTO_OPEN_CO | {
    "K8s","K7s","K6s","K5s","K4s","K3s","K2s",
    "Q8s","Q7s","Q6s","Q5s","Q4s","Q3s","Q2s",
    "J8s","J7s","T7s","97s","86s","75s","54s",
    "A9o","A8o","A7o","A6o","A5o","A4o","A3o","A2o",
    "K9o","K8o","Q9o","J9o","T9o","98o","87o","76o",
}
GTO_OPEN_SB = GTO_OPEN_BTN - {"K2s","Q2s","Q3s","75s","K8o","98o","87o","76o"}

_GTO_OPENS = {"utg": GTO_OPEN_UTG, "mp": GTO_OPEN_MP, "co": GTO_OPEN_CO,
              "btn": GTO_OPEN_BTN, "sb": GTO_OPEN_SB}

GTO_3BET_VS_UTG = {"AA","KK","QQ","AKs","AKo"}
GTO_3BET_VS_MP  = GTO_3BET_VS_UTG | {"JJ","AQs"}
GTO_3BET_VS_CO  = GTO_3BET_VS_MP  | {"TT","AQo","AJs","KQs","A5s","A4s"}
GTO_3BET_VS_BTN = GTO_3BET_VS_CO  | {"99","KJs","AJo","KQo","A3s","A2s","T9s"}
GTO_3BET_VS_SB  = GTO_3BET_VS_BTN

_GTO_3BETS = {"utg": GTO_3BET_VS_UTG, "mp": GTO_3BET_VS_MP,
              "co": GTO_3BET_VS_CO, "btn": GTO_3BET_VS_BTN, "sb": GTO_3BET_VS_SB}

GTO_CALL_VS_UTG = {
    "JJ","TT","99","88","77","66","55",
    "AQs","AJs","ATs","KQs","KJs","KTs","QJs","QTs","JTs","T9s","98s","87s","76s",
    "AQo","AJo","KQo",
}
GTO_CALL_VS_BTN = GTO_CALL_VS_UTG | {
    "44","33","22","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s",
    "K9s","Q9s","J9s","K8s","Q8s","J8s","T8s","97s","86s","75s","65s","54s",
    "ATo","KJo","QJo","A9o","K9o","Q9o","J9o","T9o","98o",
}
_GTO_CALLS = {"utg": GTO_CALL_VS_UTG, "mp": GTO_CALL_VS_UTG,
              "co": GTO_CALL_VS_BTN, "btn": GTO_CALL_VS_BTN, "sb": GTO_CALL_VS_BTN}

GTO_BB_DEFEND = GTO_CALL_VS_BTN | {
    "K7s","K6s","K5s","K4s","K3s","K2s","Q7s","Q6s","Q5s","J7s","T7s","96s","85s",
    "64s","53s","43s","A8o","A7o","A6o","A5o","K8o","87o","76o",
}


def _canonical(c1, c2):
    r1, s1 = c1[0], c1[1]
    r2, s2 = c2[0], c2[1]
    if RANK_ORDER.index(r1) < RANK_ORDER.index(r2):
        r1, r2, s1, s2 = r2, r1, s2, s1
    if r1 == r2:
        return r1 + r2
    return r1 + r2 + ("s" if s1 == s2 else "o")


def _position_label(seat, players, action_log):
    active  = sorted(p["seat"] for p in players if p.get("state") != "busted")
    n       = len(active)
    if n < 2 or seat not in active:
        return "unknown"
    sb_seat = next((a["seat"] for a in action_log if a.get("action") == "small_blind"), None)
    if sb_seat is None or sb_seat not in active:
        return "unknown"
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
    return "utg" if (n >= 5 and offset == 3) else "mp"


def _opener_label(players, action_log):
    active  = sorted(p["seat"] for p in players if p.get("state") != "busted")
    n       = len(active)
    sb_seat = next((a["seat"] for a in action_log if a.get("action") == "small_blind"), None)
    last_r  = next((a["seat"] for a in reversed(action_log)
                    if a.get("action") in ("raise", "all_in")), None)
    if sb_seat is None or last_r is None or last_r not in active:
        return "unknown"
    if n == 2:
        return "btn" if last_r == sb_seat else "bb"
    sb_idx     = active.index(sb_seat)
    dealer     = active[(sb_idx - 1) % n]
    r_idx      = active.index(last_r)
    d_idx      = active.index(dealer)
    offset     = (r_idx - d_idx) % n
    if offset == 0:     return "btn"
    if offset == 1:     return "sb"
    if offset == 2:     return "bb"
    if offset == n - 1: return "co"
    return "utg" if (n >= 5 and offset == 3) else "mp"


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

    # ── Preflop: GTO-approximate ranges ──────────────────────────────────
    if street == "preflop":
        hand     = _canonical(my_cards[0], my_cards[1])
        our_pos  = _position_label(seat, players, action_log)
        raised_n = sum(1 for a in action_log if a.get("action") in ("raise","all_in"))

        # Short-stack shove: ignore ranges when < 15 BB.
        if stack <= 15 * BIG_BLIND and owed > 0:
            h_eq = 0.50 + RANK_ORDER.index(my_cards[0][0]) / 24.0 * 0.35
            if h_eq >= 0.50 or hand in ("AA","KK","QQ","JJ","AKs","AKo"):
                return {"action": "all_in"}
            pot_odds = owed / (pot + owed) if pot + owed > 0 else 1.0
            if pot_odds < 0.28:
                return {"action": "call"}
            return {"action": "fold"}

        open_size   = max(BIG_BLIND * 3, min_r)
        threebet_to = max(min_r, int(current_bet * 3.0))
        fourbet_to  = max(min_r, int(current_bet * 2.5))

        if raised_n == 0:
            if our_pos == "bb" and can_check:
                return {"action": "check"}
            opens = _GTO_OPENS.get(our_pos)
            if opens and hand in opens:
                open_size = min(open_size, stack + my_bet)
                return {"action": "raise", "amount": open_size}
            if can_check:
                return {"action": "check"}
            return {"action": "fold"}

        if raised_n == 1:
            opener_pos = _opener_label(players, action_log)
            if our_pos == "bb":
                threebet_set = _GTO_3BETS.get(opener_pos, set())
                defend_set   = GTO_BB_DEFEND
                if hand in threebet_set:
                    return {"action": "raise", "amount": min(threebet_to, stack + my_bet)}
                if hand in defend_set and owed < 0.30 * stack:
                    return {"action": "call"}
                return {"action": "fold"}
            threebet_set = _GTO_3BETS.get(opener_pos, set())
            call_set     = _GTO_CALLS.get(opener_pos, set())
            if hand in threebet_set:
                return {"action": "raise", "amount": min(threebet_to, stack + my_bet)}
            if hand in call_set and owed < 0.25 * stack:
                return {"action": "call"}
            return {"action": "fold"}

        # Facing 3-bet+
        if hand in ("AA","KK"):
            return {"action": "raise", "amount": min(fourbet_to, stack + my_bet)}
        if hand in ("QQ","JJ","AKs","AKo") and owed < 0.25 * stack:
            return {"action": "call"}
        return {"action": "fold"}

    # ── Postflop: proportional MC equity, balanced sizing ─────────────────
    equity   = _monte_carlo_equity(my_cards, board, num_opp)
    pot_odds = owed / (pot + owed) if owed > 0 and pot + owed > 0 else 0.0

    # GTO-inspired: mix bet frequencies rather than always betting with equity.
    # Bet ~60% of range when ahead (val_thresh), ~15% bluff frequency.
    val_thresh = 0.54 - pos_float * 0.05

    if can_check:
        if equity >= val_thresh:
            # Balanced sizing: vary between 40-90% pot pseudo-randomly to avoid reads.
            edge     = (equity - 0.5) * 2
            base_frac = 0.45 + edge * 0.50
            # ±15% size variation to balance bet sizes.
            fraction = base_frac * random.uniform(0.85, 1.15)
            fraction = max(0.35, min(0.95, fraction))
            target   = max(min_r, int(pot * fraction))
            target   = min(target, stack + my_bet)
            return {"action": "raise", "amount": target}
        # Balanced bluff range: semi-bluff + pure bluff in position.
        if pos_float > 0.55 and random.random() < 0.18:
            target = max(min_r, int(pot * random.uniform(0.45, 0.65)))
            target = min(target, stack + my_bet)
            return {"action": "raise", "amount": target}
        return {"action": "check"}

    # Facing a bet: GTO-approximate calling margin.
    margin = 0.04 + (1.0 - pos_float) * 0.03
    if equity > pot_odds + margin:
        if equity > 0.73 and stack > owed * 2:
            raise_to = max(min_r, int(current_bet * 2.8))
            raise_to = min(raise_to, stack + my_bet)
            return {"action": "raise", "amount": raise_to}
        return {"action": "call"}
    return {"action": "fold"}
