"""RangeBot — MC equity conditioned on opponent's likely hand range.

Stronger than EquityBot: instead of sampling opponent hands uniformly,
it narrows the range based on what the opponent did preflop and postflop
(raised/called/checked), then runs MC against that narrowed distribution.
This produces sharper equity estimates and better fold/call decisions.
"""
import random
import eval7

BOT_NAME = "RangeBot"

RANK_ORDER = "23456789TJQKA"
BIG_BLIND  = 100

# Preflop hand score table (same calibration as EquityBot).
_HU_EQUITY = {
    "AA":0.852,"KK":0.823,"QQ":0.799,"JJ":0.775,"TT":0.751,
    "99":0.722,"88":0.691,"77":0.660,"66":0.633,"55":0.605,
    "44":0.578,"33":0.555,"22":0.531,
    "AKs":0.670,"AQs":0.661,"AJs":0.652,"ATs":0.647,"A9s":0.629,
    "A8s":0.621,"A7s":0.614,"A6s":0.604,"A5s":0.598,"A4s":0.590,
    "A3s":0.583,"A2s":0.575,
    "KQs":0.633,"KJs":0.624,"KTs":0.616,"K9s":0.589,"K8s":0.564,
    "K7s":0.555,"K6s":0.546,"K5s":0.538,"K4s":0.531,"K3s":0.524,"K2s":0.518,
    "QJs":0.604,"QTs":0.598,"Q9s":0.566,"Q8s":0.539,"Q7s":0.518,
    "Q6s":0.510,"Q5s":0.502,"Q4s":0.495,"Q3s":0.488,"Q2s":0.481,
    "JTs":0.585,"J9s":0.557,"J8s":0.531,"J7s":0.502,"J6s":0.476,
    "J5s":0.469,"J4s":0.463,"J3s":0.457,"J2s":0.451,
    "T9s":0.547,"T8s":0.522,"T7s":0.494,"T6s":0.467,"T5s":0.435,
    "T4s":0.430,"T3s":0.424,"T2s":0.419,
    "98s":0.503,"97s":0.477,"96s":0.450,"95s":0.422,"94s":0.391,
    "93s":0.386,"92s":0.381,
    "87s":0.467,"86s":0.442,"85s":0.416,"84s":0.387,"83s":0.358,"82s":0.353,
    "76s":0.427,"75s":0.404,"74s":0.376,"73s":0.348,"72s":0.319,
    "65s":0.396,"64s":0.370,"63s":0.342,"62s":0.314,
    "54s":0.378,"53s":0.351,"52s":0.323,
    "43s":0.336,"42s":0.309,"32s":0.297,
    "AKo":0.652,"AQo":0.642,"AJo":0.633,"ATo":0.625,"A9o":0.605,
    "A8o":0.597,"A7o":0.589,"A6o":0.578,"A5o":0.572,"A4o":0.565,
    "A3o":0.557,"A2o":0.548,
    "KQo":0.609,"KJo":0.600,"KTo":0.591,"K9o":0.560,"K8o":0.534,
    "K7o":0.524,"K6o":0.515,"K5o":0.506,"K4o":0.497,"K3o":0.490,"K2o":0.482,
    "QJo":0.578,"QTo":0.572,"Q9o":0.539,"Q8o":0.512,"Q7o":0.488,
    "Q6o":0.480,"Q5o":0.471,"Q4o":0.464,"Q3o":0.456,"Q2o":0.448,
    "JTo":0.559,"J9o":0.530,"J8o":0.503,"J7o":0.474,"J6o":0.448,
    "J5o":0.440,"J4o":0.434,"J3o":0.427,"J2o":0.421,
    "T9o":0.520,"T8o":0.494,"T7o":0.466,"T6o":0.438,"T5o":0.404,
    "T4o":0.398,"T3o":0.392,"T2o":0.386,
    "98o":0.476,"97o":0.450,"96o":0.421,"95o":0.392,"94o":0.359,
    "93o":0.353,"92o":0.347,
    "87o":0.439,"86o":0.413,"85o":0.386,"84o":0.354,"83o":0.323,"82o":0.317,
    "76o":0.398,"75o":0.374,"74o":0.343,"73o":0.313,"72o":0.282,
    "65o":0.367,"64o":0.339,"63o":0.310,"62o":0.279,
    "54o":0.348,"53o":0.319,"52o":0.289,
    "43o":0.305,"42o":0.275,"32o":0.262,
}

_HANDS_SORTED = sorted(_HU_EQUITY.keys(), key=lambda k: -_HU_EQUITY[k])


def _canonical(c1, c2):
    r1, s1 = c1[0], c1[1]
    r2, s2 = c2[0], c2[1]
    if RANK_ORDER.index(r1) < RANK_ORDER.index(r2):
        r1, r2, s1, s2 = r2, r1, s2, s1
    if r1 == r2:
        return r1 + r2
    return r1 + r2 + ("s" if s1 == s2 else "o")


def _top_pct_combos(pct, exclude):
    """All concrete (c1, c2) pairs from the top-pct% of hands by HU equity,
    excluding cards already known (hole + board)."""
    n = max(1, int(round(169 * pct)))
    combos = []
    for hk in _HANDS_SORTED[:n]:
        if len(hk) == 2:                    # pocket pair
            r = hk[0]
            cards = [r + s for s in "shdc"]
            for i in range(4):
                for j in range(i + 1, 4):
                    a, b = cards[i], cards[j]
                    if a not in exclude and b not in exclude:
                        combos.append((a, b))
        else:
            r1, r2 = hk[0], hk[1]
            suited = hk.endswith("s")
            if suited:
                for s in "shdc":
                    a, b = r1 + s, r2 + s
                    if a not in exclude and b not in exclude:
                        combos.append((a, b))
            else:
                for s1 in "shdc":
                    for s2 in "shdc":
                        if s1 == s2:
                            continue
                        a, b = r1 + s1, r2 + s2
                        if a not in exclude and b not in exclude:
                            combos.append((a, b))
    return combos


def _infer_range_pct(action_log, opp_seat):
    """Estimate the top-X% of hands the opponent likely holds,
    based on their preflop action."""
    raised = any(
        a["seat"] == opp_seat and a.get("action") in ("raise", "all_in")
        for a in action_log
    )
    called = any(
        a["seat"] == opp_seat and a.get("action") == "call"
        for a in action_log
    )
    if raised:
        return 0.18   # typical open/3-bet range
    if called:
        return 0.35   # call range
    return 0.55       # limped / blind posted


def _monte_carlo_equity_ranged(my_cards, board, opp_seat, action_log,
                                n_samples=200):
    """MC equity vs a range-conditioned opponent hand."""
    my_e7    = [eval7.Card(c) for c in my_cards]
    board_e7 = [eval7.Card(c) for c in board]
    known    = set(my_cards + board)

    pct    = _infer_range_pct(action_log, opp_seat)
    combos = _top_pct_combos(pct, known)

    board_left  = 5 - len(board_e7)
    full_deck   = [r + s for r in RANK_ORDER for s in "shdc"]
    rem_deck    = [c for c in full_deck if c not in known]

    if not combos or board_left > len(rem_deck) - 2:
        # Fall back to uniform MC if range inference fails.
        deck  = [eval7.Card(c) for c in rem_deck]
        wins  = ties = 0
        for _ in range(n_samples):
            samp    = random.sample(deck, board_left + 2)
            run_out = board_e7 + samp[:board_left]
            opp_e7  = samp[board_left:]
            my_sc   = eval7.evaluate(my_e7 + run_out)
            op_sc   = eval7.evaluate(opp_e7 + run_out)
            if my_sc > op_sc:
                wins += 1
            elif my_sc == op_sc:
                ties += 0.5
        return (wins + ties) / n_samples

    wins = ties = 0
    for _ in range(n_samples):
        opp_pair = random.choice(combos)
        opp_e7   = [eval7.Card(opp_pair[0]), eval7.Card(opp_pair[1])]
        opp_excl = set(opp_pair)
        board_pool = [c for c in rem_deck if c not in opp_excl]
        if len(board_pool) < board_left:
            continue
        run_cards = random.sample(board_pool, board_left)
        run_out   = board_e7 + [eval7.Card(c) for c in run_cards]
        my_sc     = eval7.evaluate(my_e7 + run_out)
        op_sc     = eval7.evaluate(opp_e7 + run_out)
        if my_sc > op_sc:
            wins += 1
        elif my_sc == op_sc:
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
        idx = seats.index(seat)
    except ValueError:
        return 0.5
    return idx / (n - 1)


_VPIP = [0.62, 0.58, 0.52, 0.44, 0.54, 0.38]

def _pos_idx(seat, players):
    active = [p for p in players if p["state"] != "busted"]
    n      = len(active)
    if n <= 1:
        return 3
    seats = [p["seat"] for p in active]
    try:
        idx = seats.index(seat)
    except ValueError:
        return 2
    return min(5, int(idx / max(n - 1, 1) * 5))


def decide(state):
    if state.get("type") == "warmup":
        return {"action": "fold"}

    street     = state["street"]
    my_cards   = state["your_cards"]
    board      = state["community_cards"]
    pot        = state["pot"]
    owed       = state["amount_owed"]
    stack      = state["your_stack"]
    seat       = state["seat_to_act"]
    can_check  = state["can_check"]
    min_r      = state["min_raise_to"]
    my_bet     = state["your_bet_this_street"]
    players    = state["players"]
    action_log = state.get("action_log", [])
    current_bet = state["current_bet"]

    active_opps = [p for p in players
                   if p["state"] in ("active", "all_in") and p["seat"] != seat]
    num_opp    = max(len(active_opps), 1)
    pos_float  = _position_float(seat, players)

    # ── Preflop ──────────────────────────────────────────────────────────────
    if street == "preflop":
        score     = _preflop_score(my_cards)
        threshold = _VPIP[_pos_idx(seat, players)]
        if score >= threshold:
            if score >= 0.76:
                raise_to = max(BIG_BLIND * 3, min_r)
                raise_to = min(raise_to * 2, stack + my_bet)
                return {"action": "raise", "amount": raise_to}
            if score >= 0.60 and pos_float >= 0.35:
                raise_to = max(BIG_BLIND * 3, min_r)
                raise_to = min(raise_to, stack + my_bet)
                return {"action": "raise", "amount": raise_to}
            if can_check:
                return {"action": "check"}
            pot_odds = owed / (pot + owed) if pot + owed > 0 else 1.0
            if pot_odds < 0.25:
                return {"action": "call"}
        if can_check:
            return {"action": "check"}
        return {"action": "fold"}

    # ── Postflop: range-conditioned MC equity ─────────────────────────────
    # Use only the primary (most aggressive) opponent for range conditioning.
    primary_opp = max(
        (p for p in active_opps),
        key=lambda p: sum(1 for a in action_log
                          if a["seat"] == p["seat"]
                          and a.get("action") in ("raise", "all_in")),
        default=None,
    )
    if primary_opp and num_opp == 1:
        equity = _monte_carlo_equity_ranged(
            my_cards, board, primary_opp["seat"], action_log, n_samples=180
        )
    else:
        # Multi-way: uniform sampling (range conditioning too uncertain).
        from functools import reduce
        my_e7    = [eval7.Card(c) for c in my_cards]
        board_e7 = [eval7.Card(c) for c in board]
        known    = set(my_cards + board)
        deck     = [eval7.Card(r + s) for r in RANK_ORDER for s in "shdc"
                    if r + s not in known]
        board_left = 5 - len(board_e7)
        needed   = board_left + 2 * num_opp
        wins = ties = 0
        n_samples = 150
        for _ in range(n_samples):
            samp    = random.sample(deck, needed)
            run_out = board_e7 + samp[:board_left]
            my_sc   = eval7.evaluate(my_e7 + run_out)
            opp_best = max(
                eval7.evaluate(samp[board_left + i*2 : board_left + (i+1)*2] + run_out)
                for i in range(num_opp)
            )
            if my_sc > opp_best:
                wins += 1
            elif my_sc == opp_best:
                ties += 0.5
        equity = (wins + ties) / n_samples

    pot_odds  = owed / (pot + owed) if owed > 0 and pot + owed > 0 else 0.0
    val_thresh = 0.55 - pos_float * 0.05   # 0.50 IP, 0.55 OOP

    if can_check:
        if equity >= val_thresh:
            edge     = (equity - 0.5) * 2
            fraction = 0.45 + edge * 0.60
            fraction = min(1.10, fraction)
            target   = max(min_r, int(pot * fraction))
            target   = min(target, stack + my_bet)
            return {"action": "raise", "amount": target}
        # Semi-bluff in position with near-air.
        if equity < 0.32 and pos_float > 0.60 and random.random() < 0.22:
            target = max(min_r, int(pot * 0.55))
            target = min(target, stack + my_bet)
            return {"action": "raise", "amount": target}
        return {"action": "check"}

    # Facing a bet: range conditioning makes our equity sharper — tighten margin.
    margin = 0.03 + (1.0 - pos_float) * 0.03   # 0.03–0.06
    if equity > pot_odds + margin:
        if equity > 0.72 and stack > owed * 2:
            raise_to = max(min_r, int(current_bet * 2.8))
            raise_to = min(raise_to, stack + my_bet)
            return {"action": "raise", "amount": raise_to}
        return {"action": "call"}
    return {"action": "fold"}
