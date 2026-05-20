"""Apex — Fullhouse Hackathon entry.

A tight-aggressive (TAG) bot built on:
  * a 169-hand canonical preflop equity table (vs random hands)
  * Monte Carlo postflop equity vs N opponents
  * lightweight opponent modelling from match_action_log
  * position-aware sizing & bluffing

Single file, stdlib + eval7 only.
"""

import time
import math
import random
import eval7

BOT_NAME = "Apex"
BOT_AVATAR = "robot_1"

# ─────────────────────────────────────────────────────────────────────────────
# Constants & precomputed objects
# ─────────────────────────────────────────────────────────────────────────────

BIG_BLIND = 100
SMALL_BLIND = 50
STARTING_STACK = 10_000   # tournament starting stack; used for bust-protection SPR

RANK_ORDER = "23456789TJQKA"
_RANK_IDX = {r: i for i, r in enumerate(RANK_ORDER)}

DECK_STRINGS = [r + s for r in RANK_ORDER for s in "shdc"]

# Cache eval7.Card objects keyed by string — Card construction isn't free.
_CARD_CACHE = {s: eval7.Card(s) for s in DECK_STRINGS}

# ─────────────────────────────────────────────────────────────────────────────
# Preflop equity table (vs 1 random hand, heads-up).
# Values are well-known PokerStove equilibria; ordering is what matters.
# Format keys: "AA", "AKs", "AKo", "72o", "32s", etc.  Higher rank first.
# ─────────────────────────────────────────────────────────────────────────────

_HU_EQUITY = {
    # pocket pairs
    "AA": 0.852, "KK": 0.823, "QQ": 0.799, "JJ": 0.775, "TT": 0.751,
    "99": 0.722, "88": 0.691, "77": 0.660, "66": 0.633, "55": 0.605,
    "44": 0.578, "33": 0.555, "22": 0.531,
    # suited Ax
    "AKs": 0.670, "AQs": 0.661, "AJs": 0.652, "ATs": 0.647, "A9s": 0.629,
    "A8s": 0.621, "A7s": 0.614, "A6s": 0.604, "A5s": 0.598, "A4s": 0.590,
    "A3s": 0.583, "A2s": 0.575,
    # suited Kx
    "KQs": 0.633, "KJs": 0.624, "KTs": 0.616, "K9s": 0.589, "K8s": 0.564,
    "K7s": 0.555, "K6s": 0.546, "K5s": 0.538, "K4s": 0.531, "K3s": 0.524,
    "K2s": 0.518,
    # suited Qx
    "QJs": 0.604, "QTs": 0.598, "Q9s": 0.566, "Q8s": 0.539, "Q7s": 0.518,
    "Q6s": 0.510, "Q5s": 0.502, "Q4s": 0.495, "Q3s": 0.488, "Q2s": 0.481,
    # suited Jx
    "JTs": 0.585, "J9s": 0.557, "J8s": 0.531, "J7s": 0.502, "J6s": 0.476,
    "J5s": 0.469, "J4s": 0.463, "J3s": 0.457, "J2s": 0.451,
    # suited Tx
    "T9s": 0.547, "T8s": 0.522, "T7s": 0.494, "T6s": 0.467, "T5s": 0.435,
    "T4s": 0.430, "T3s": 0.424, "T2s": 0.419,
    # suited 9x
    "98s": 0.503, "97s": 0.477, "96s": 0.450, "95s": 0.422, "94s": 0.391,
    "93s": 0.386, "92s": 0.381,
    # suited 8x
    "87s": 0.467, "86s": 0.442, "85s": 0.416, "84s": 0.387, "83s": 0.358,
    "82s": 0.353,
    # suited 7x
    "76s": 0.427, "75s": 0.404, "74s": 0.376, "73s": 0.348, "72s": 0.319,
    # suited 6x
    "65s": 0.396, "64s": 0.370, "63s": 0.342, "62s": 0.314,
    # suited 5x
    "54s": 0.378, "53s": 0.351, "52s": 0.323,
    # suited 4x / 3x
    "43s": 0.336, "42s": 0.309, "32s": 0.297,

    # offsuit
    "AKo": 0.652, "AQo": 0.642, "AJo": 0.633, "ATo": 0.625, "A9o": 0.605,
    "A8o": 0.597, "A7o": 0.589, "A6o": 0.578, "A5o": 0.572, "A4o": 0.565,
    "A3o": 0.557, "A2o": 0.548,
    "KQo": 0.609, "KJo": 0.600, "KTo": 0.591, "K9o": 0.560, "K8o": 0.534,
    "K7o": 0.524, "K6o": 0.515, "K5o": 0.506, "K4o": 0.497, "K3o": 0.490,
    "K2o": 0.482,
    "QJo": 0.578, "QTo": 0.572, "Q9o": 0.539, "Q8o": 0.512, "Q7o": 0.488,
    "Q6o": 0.480, "Q5o": 0.471, "Q4o": 0.464, "Q3o": 0.456, "Q2o": 0.448,
    "JTo": 0.559, "J9o": 0.530, "J8o": 0.503, "J7o": 0.474, "J6o": 0.448,
    "J5o": 0.440, "J4o": 0.434, "J3o": 0.427, "J2o": 0.421,
    "T9o": 0.520, "T8o": 0.494, "T7o": 0.466, "T6o": 0.438, "T5o": 0.404,
    "T4o": 0.398, "T3o": 0.392, "T2o": 0.386,
    "98o": 0.476, "97o": 0.450, "96o": 0.421, "95o": 0.392, "94o": 0.359,
    "93o": 0.353, "92o": 0.347,
    "87o": 0.439, "86o": 0.413, "85o": 0.386, "84o": 0.354, "83o": 0.323,
    "82o": 0.317,
    "76o": 0.398, "75o": 0.374, "74o": 0.343, "73o": 0.313, "72o": 0.282,
    "65o": 0.367, "64o": 0.339, "63o": 0.310, "62o": 0.279,
    "54o": 0.348, "53o": 0.319, "52o": 0.289,
    "43o": 0.305, "42o": 0.275, "32o": 0.262,
}


def _canonical_hand(c1: str, c2: str) -> str:
    r1, s1 = c1[0], c1[1]
    r2, s2 = c2[0], c2[1]
    if _RANK_IDX[r1] < _RANK_IDX[r2]:
        r1, r2, s1, s2 = r2, r1, s2, s1
    if r1 == r2:
        return r1 + r2
    return r1 + r2 + ("s" if s1 == s2 else "o")


# MC-derived equity table built during the 30 s warmup window.  Maps
# (hand_key, n_opp) → equity vs that many random opponents.  Falls back to
# _HU_EQUITY + heuristic exponent for any cell the precompute didn't reach.
_PRECOMPUTED_EQUITY = {}


def _hu_equity(hand_key: str) -> float:
    eq = _PRECOMPUTED_EQUITY.get((hand_key, 1))
    if eq is not None:
        return eq
    return _HU_EQUITY.get(hand_key, 0.40)


def _multiway_equity(hand_key: str, n_opp: int) -> float:
    """Equity vs N random opponents.  Uses precomputed MC table when present,
    else falls back to a softer exponent on the heads-up baseline."""
    if n_opp <= 0:
        return 1.0
    if n_opp <= 1:
        return _hu_equity(hand_key)
    n_opp = min(n_opp, 5)
    eq = _PRECOMPUTED_EQUITY.get((hand_key, n_opp))
    if eq is not None:
        return eq
    e = _HU_EQUITY.get(hand_key, 0.40)
    return e ** (1.0 + (n_opp - 1) * 0.82)


def _representative_cards(hand_key: str):
    """Pick canonical hole cards for a 169-key — suit-symmetry makes the
    specific suits irrelevant to vs-random equity."""
    if len(hand_key) == 2:                 # pocket pair, e.g. "AA"
        r = hand_key[0]
        return [r + "s", r + "h"]
    r1, r2 = hand_key[0], hand_key[1]
    if hand_key.endswith("s"):             # suited
        return [r1 + "s", r2 + "s"]
    return [r1 + "s", r2 + "h"]            # offsuit


# ─────────────────────────────────────────────────────────────────────────────
# #7 — GTO-derived preflop blueprint (6-max, ~100 BB starting stacks).
#
# These ranges are taken from published CFR-solved 6-max preflop charts
# (Upswing Poker / GTO Wizard families).  They are approximations of pure
# Nash equilibrium strategies — solver output rounded to discrete
# always/never decisions.  The actual solver outputs use mixed frequencies
# for borderline hands; we round to the dominant action.
#
# Default OFF: A/B testing showed the published GTO charts regress against
# the exploitable reference field (current: -7K, hybrid_100: -5.5K).  Hand-
# tuned exploitative play beats theoretical optimal vs known-weak opponents.
# Charts kept here for use against unknown human-built bots in the live
# tournament — flip the toggle to True there if exploit-friendly play is no
# longer the right strategy.
# ─────────────────────────────────────────────────────────────────────────────

_USE_GTO_BLUEPRINT = False

# === RFI (Raise First In) ranges by position ====================================
# UTG (~12% of hands)
GTO_OPEN_UTG = {
    "AA","KK","QQ","JJ","TT","99","88",
    "AKs","AKo","AQs","AQo","AJs","ATs","KQs","KJs","QJs",
}
# MP / HJ (~17%)
GTO_OPEN_MP = GTO_OPEN_UTG | {
    "77","66","AJo","KQo","KTs","QTs","JTs","ATo","T9s","98s","87s","76s",
}
# CO (~28%)
GTO_OPEN_CO = GTO_OPEN_MP | {
    "55","44","33","22",
    "A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s",
    "K9s","Q9s","J9s","T8s","KJo","QJo","JTo","65s",
}
# BTN (~48%)
GTO_OPEN_BTN = GTO_OPEN_CO | {
    "K8s","K7s","K6s","K5s","K4s","K3s","K2s",
    "Q8s","Q7s","Q6s","Q5s","Q4s","Q3s","Q2s",
    "J8s","J7s","T7s","97s","86s","75s","54s",
    "A9o","A8o","A7o","A6o","A5o","A4o","A3o","A2o",
    "K9o","K8o","Q9o","J9o","T9o","98o","87o","76o",
}
# SB (when folded to) — slightly tighter than BTN due to OOP postflop
GTO_OPEN_SB = GTO_OPEN_BTN - {"K2s","Q2s","Q3s","75s","K8o","98o","87o","76o"}

_GTO_OPENS = {
    "utg": GTO_OPEN_UTG,
    "mp":  GTO_OPEN_MP,
    "co":  GTO_OPEN_CO,
    "btn": GTO_OPEN_BTN,
    "sb":  GTO_OPEN_SB,
}

# === 3-bet ranges (vs single open, by opener position) =========================
# Tighter vs early-position openers; wider vs late-position openers.
GTO_3BET_VS_UTG = {"AA","KK","QQ","AKs","AKo"}
GTO_3BET_VS_MP  = GTO_3BET_VS_UTG | {"JJ","AQs"}
GTO_3BET_VS_CO  = GTO_3BET_VS_MP  | {"TT","AQo","AJs","KQs","A5s","A4s"}
GTO_3BET_VS_BTN = GTO_3BET_VS_CO  | {"99","KJs","AJo","KQo","A3s","A2s","T9s"}
GTO_3BET_VS_SB  = GTO_3BET_VS_BTN

_GTO_3BETS = {
    "utg": GTO_3BET_VS_UTG,
    "mp":  GTO_3BET_VS_MP,
    "co":  GTO_3BET_VS_CO,
    "btn": GTO_3BET_VS_BTN,
    "sb":  GTO_3BET_VS_SB,
}

# === Calling ranges (call but not 3-bet) =======================================
# Hands we just call to see the flop in position with playability.
GTO_CALL_VS_UTG = {
    "JJ","TT","99","88","77","66","55",
    "AQs","AJs","ATs","KQs","KJs","KTs","QJs","QTs","JTs","T9s","98s","87s","76s",
    "AQo","AJo","KQo",
}
GTO_CALL_VS_MP = GTO_CALL_VS_UTG | {
    "44","33","22","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s","K9s","Q9s","J9s",
}
GTO_CALL_VS_CO = GTO_CALL_VS_MP | {
    "K8s","Q8s","J8s","T8s","97s","86s","75s","65s","54s","ATo","KJo","QJo",
}
GTO_CALL_VS_BTN = GTO_CALL_VS_CO | {
    "K7s","K6s","K5s","Q7s","J7s","T7s","96s","85s","74s","64s","53s","43s",
    "A9o","K9o","Q9o","J9o","T9o","98o","KJo","QJo",
}
GTO_CALL_VS_SB = GTO_CALL_VS_BTN

_GTO_CALLS = {
    "utg": GTO_CALL_VS_UTG,
    "mp":  GTO_CALL_VS_MP,
    "co":  GTO_CALL_VS_CO,
    "btn": GTO_CALL_VS_BTN,
    "sb":  GTO_CALL_VS_SB,
}

# === BB defending ranges =======================================================
# When facing a raise from BB (after posting), we defend wide due to discount.
# Combined call+3bet defend.  3-bet ranges are subset of GTO_3BETS by opener pos.
GTO_BB_CALL_VS_UTG = GTO_CALL_VS_UTG | {
    "44","33","22","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s",
    "K9s","K8s","Q9s","J9s","T8s","97s","86s","65s","54s",
    "ATo","KJo","KTo","QJo","QTo","JTo",
}
GTO_BB_CALL_VS_BTN = GTO_BB_CALL_VS_UTG | {
    "K7s","K6s","K5s","K4s","K3s","K2s","Q8s","Q7s","Q6s","Q5s",
    "J8s","J7s","T7s","96s","85s","75s","64s","53s","43s",
    "A9o","A8o","A7o","A6o","A5o","A4o","A3o","A2o","K9o","K8o",
    "Q9o","J9o","T9o","98o","87o","76o",
}
_GTO_BB_DEFENDS = {
    "utg": GTO_BB_CALL_VS_UTG,
    "mp":  GTO_BB_CALL_VS_UTG,
    "co":  GTO_BB_CALL_VS_BTN,         # CO and BTN: similar wide defending
    "btn": GTO_BB_CALL_VS_BTN,
    "sb":  GTO_BB_CALL_VS_BTN,
}

# === 4-bet response ranges (facing a 3-bet) ===================================
# Versus a 3-bet, we 4-bet only premium / call with strong / fold rest.
GTO_4BET = {"AA","KK"}
GTO_CALL_3BET = {"QQ","JJ","AKs","AKo"}      # standard call-3bet range
GTO_CALL_3BET_DEEP = GTO_CALL_3BET | {       # only deep stacks add these
    "TT","AQs","AQo","AJs","KQs",
}


def _gto_position_label(state) -> str:
    """Determine our position label (utg/mp/co/btn/sb/bb) from action_log.
    Returns 'unknown' if we can't infer it."""
    action_log = state.get("action_log", [])
    your_seat = state["seat_to_act"]
    sb_seat = next((a["seat"] for a in action_log
                    if a.get("action") == "small_blind"), None)
    if sb_seat is None:
        return "unknown"
    seats_in_hand = sorted({p["seat"] for p in state["players"]
                            if p.get("state") != "busted"})
    n = len(seats_in_hand)
    if n < 2:
        return "unknown"
    if n == 2:
        return "btn" if your_seat == sb_seat else "bb"

    # Dealer = SB - 1 in seat order around the table
    if sb_seat in seats_in_hand:
        sb_idx = seats_in_hand.index(sb_seat)
        dealer = seats_in_hand[(sb_idx - 1) % n]
    else:
        return "unknown"
    if your_seat not in seats_in_hand:
        return "unknown"
    your_idx = seats_in_hand.index(your_seat)
    dealer_idx = seats_in_hand.index(dealer)
    offset = (your_idx - dealer_idx) % n
    # offset 0=BTN, 1=SB, 2=BB, 3=UTG, 4=MP/HJ, 5=CO (in 6-max)
    if offset == 0: return "btn"
    if offset == 1: return "sb"
    if offset == 2: return "bb"
    if offset == n - 1: return "co"
    if offset >= 3 and offset <= n - 2:
        # MP or UTG
        if n >= 5 and offset == 3:
            return "utg"
        return "mp"
    return "unknown"


def _gto_opener_position(state):
    """Find the position of the most recent preflop raiser.  Returns
    'unknown' if we can't pin it down."""
    action_log = state.get("action_log", [])
    last_raiser = None
    for a in action_log:
        if a.get("action") in ("raise", "all_in"):
            last_raiser = a.get("seat")
    if last_raiser is None:
        return "unknown"
    sb_seat = next((a["seat"] for a in action_log
                    if a.get("action") == "small_blind"), None)
    if sb_seat is None:
        return "unknown"
    seats_in_hand = sorted({p["seat"] for p in state["players"]
                            if p.get("state") != "busted"})
    n = len(seats_in_hand)
    if n < 2 or last_raiser not in seats_in_hand or sb_seat not in seats_in_hand:
        return "unknown"
    if n == 2:
        return "btn" if last_raiser == sb_seat else "bb"
    sb_idx = seats_in_hand.index(sb_seat)
    dealer = seats_in_hand[(sb_idx - 1) % n]
    raiser_idx = seats_in_hand.index(last_raiser)
    dealer_idx = seats_in_hand.index(dealer)
    offset = (raiser_idx - dealer_idx) % n
    if offset == 0: return "btn"
    if offset == 1: return "sb"
    if offset == 2: return "bb"
    if offset == n - 1: return "co"
    if offset >= 3 and offset <= n - 2:
        if n >= 5 and offset == 3:
            return "utg"
        return "mp"
    return "unknown"


def _gto_recommendation(state):
    """Look up the GTO action for the current preflop spot.

    Returns one of:
      ('open',)              — open-raise as RFI
      ('3bet',)              — 3-bet vs single open
      ('4bet',)              — 4-bet vs 3-bet
      ('call',)              — flat call vs raise
      ('check',)             — BB checks the option
      ('fold',)              — fold
      None                   — situation not covered, fall back to old logic
    """
    if state.get("street") != "preflop":
        return None

    cards = state["your_cards"]
    if len(cards) != 2:
        return None
    hand = _canonical_hand(cards[0], cards[1])
    our_pos = _gto_position_label(state)
    if our_pos == "unknown":
        return None

    raised_count = sum(1 for a in state["action_log"]
                       if a.get("action") in ("raise", "all_in"))
    can_check = state["can_check"]

    if raised_count == 0:
        # RFI / check option
        if our_pos == "bb" and can_check:
            return ("check",)
        opens = _GTO_OPENS.get(our_pos)
        if opens is None:
            return None
        if hand in opens:
            return ("open",)
        return ("fold",)

    if raised_count == 1:
        opener_pos = _gto_opener_position(state)
        if opener_pos == "unknown":
            return None
        # BB defending — uses widened defend range
        if our_pos == "bb":
            threebets = _GTO_3BETS.get(opener_pos)
            defends = _GTO_BB_DEFENDS.get(opener_pos)
            if threebets and hand in threebets:
                return ("3bet",)
            if defends and hand in defends:
                return ("call",)
            return ("fold",)
        # Non-BB facing a raise
        threebets = _GTO_3BETS.get(opener_pos)
        calls = _GTO_CALLS.get(opener_pos)
        if threebets and hand in threebets:
            return ("3bet",)
        if calls and hand in calls:
            return ("call",)
        return ("fold",)

    if raised_count >= 2:
        # Facing a 3-bet (or larger)
        if hand in GTO_4BET:
            return ("4bet",)
        if hand in GTO_CALL_3BET:
            return ("call",)
        return ("fold",)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Range infrastructure — for conditioning Monte Carlo on opponent action.
# A "range" is a list of hand_keys (canonical 169-form).  Combos are the
# concrete (c1, c2) tuples consistent with those keys.
# ─────────────────────────────────────────────────────────────────────────────

_HANDS_BY_RANK = sorted(_HU_EQUITY.keys(), key=lambda k: -_HU_EQUITY[k])

_TOP_PCT_CACHE = {}
_RANGE_COMBO_CACHE = {}


def _top_pct_hands(pct: float):
    """Return the top-pct fraction of canonical hand keys (by HU equity)."""
    pct = max(0.02, min(1.0, pct))
    key = round(pct, 2)
    cached = _TOP_PCT_CACHE.get(key)
    if cached is not None:
        return cached
    n = max(1, int(round(169 * pct)))
    result = _HANDS_BY_RANK[:n]
    _TOP_PCT_CACHE[key] = result
    return result


def _hand_combos(hand_keys):
    """Enumerate every (c1, c2) string-tuple consistent with the hand keys."""
    combos = []
    for hk in hand_keys:
        if len(hk) == 2:                       # pocket pair
            r = hk[0]
            cards = [r + s for s in "shdc"]
            for i in range(4):
                for j in range(i + 1, 4):
                    combos.append((cards[i], cards[j]))
        else:
            r1, r2 = hk[0], hk[1]
            suited = hk.endswith("s")
            if suited:
                for s in "shdc":
                    combos.append((r1 + s, r2 + s))
            else:
                for s1 in "shdc":
                    for s2 in "shdc":
                        if s1 == s2:
                            continue
                        combos.append((r1 + s1, r2 + s2))
    return combos


def _combos_for_range(hand_keys):
    """Cached combo enumeration; same range = same list (don't mutate!)."""
    if not hand_keys:
        return []
    key = tuple(hand_keys)
    cached = _RANGE_COMBO_CACHE.get(key)
    if cached is not None:
        return cached
    combos = _hand_combos(hand_keys)
    _RANGE_COMBO_CACHE[key] = combos
    return combos


def _infer_opp_range(state, opp_seat: int, opp_bot_id: str):
    """Estimate the range of hands `opp_seat` could hold, given:
      * what they did in the current hand (action_log)
      * their match-long aggression profile (_opp_profile + deep)
      * deep per-street stats from _deep when available

    Returns a list of canonical hand keys, or None to mean "no narrowing,
    use a wide-default range".  None is a signal to fall back to uniform
    sampling.
    """
    action_log = state.get("action_log", [])

    raised = False
    voluntary = False
    for a in action_log:
        if a.get("seat") != opp_seat:
            continue
        act = a.get("action")
        if act in ("raise", "all_in"):
            raised = True
            voluntary = True
        elif act == "call":
            voluntary = True

    raise_freq, _fold_freq, vol_freq, n_actions = _opp_profile(opp_bot_id)
    confident = n_actions >= 8

    # Prefer per-street raise frequency from the deep profile if we have a
    # decent sample (≥8 actions on that street).  This is much sharper than
    # an across-streets aggregate.
    deep = _deep.get(opp_bot_id)
    pf_raise_pct = None
    if deep is not None:
        pf_n = deep["street_n"]["preflop"]
        if pf_n >= 8:
            pf_raise_pct = deep["street_raise"]["preflop"] / pf_n

    if raised:
        # Raising range — prefer per-street pf-specific freq if available.
        if pf_raise_pct is not None:
            pct = pf_raise_pct
        elif confident:
            pct = raise_freq
        else:
            pct = 0.20
        return _top_pct_hands(max(0.05, min(0.90, pct)))

    if voluntary:
        pct = (vol_freq * 0.85) if confident else 0.30
        return _top_pct_hands(max(0.10, min(0.65, pct)))

    return _top_pct_hands(0.60)


# ─────────────────────────────────────────────────────────────────────────────
# Postflop Monte Carlo
# ─────────────────────────────────────────────────────────────────────────────

def _monte_carlo_equity(hole_strs, board_strs, n_opp, time_budget=0.45,
                        opp_ranges=None):
    """Monte-Carlo equity (expected pot share in [0, 1]).

    `opp_ranges`, if given, is a list of length n_opp.  Each entry is either
    None (uniform sampling for that opponent) or a list of canonical
    hand_keys to draw from.  Range conditioning makes equity reflect the
    *narrower* hands an opponent likely holds after their actions.
    """
    if n_opp <= 0:
        return 1.0, 0
    cache = _CARD_CACHE
    hole = [cache[s] for s in hole_strs]
    board = [cache[s] for s in board_strs]
    known = set(hole_strs) | set(board_strs)
    deck = [s for s in DECK_STRINGS if s not in known]

    board_left = 5 - len(board)
    cards_needed = board_left + 2 * n_opp
    if cards_needed > len(deck):
        return 0.5, 0

    # Pre-resolve each opponent's combo list once — filtering combos that
    # collide with already-known cards.  Uniform-sample fallback is None.
    if opp_ranges is None:
        opp_ranges = [None] * n_opp
    opp_combos = []
    for r in opp_ranges:
        if r is None:
            opp_combos.append(None)
            continue
        combos = _combos_for_range(r)
        # Filter for known-card collisions (with our hole + board).
        filtered = [(a, b) for (a, b) in combos
                    if a not in known and b not in known]
        opp_combos.append(filtered if filtered else None)

    fast_path = all(c is None for c in opp_combos)

    sample = random.sample
    randrange = random.randrange
    eval_fn = eval7.evaluate

    wins = 0.0
    sims = 0
    deadline = time.time() + time_budget

    # Run in chunks of 50 then check deadline; cheap and bounds latency.
    while True:
        for _ in range(50):
            if fast_path:
                # Original fast path: one big random.sample call.
                drawn = sample(deck, cards_needed)
                new_board = board + [cache[s] for s in drawn[:board_left]]
                my_score = eval_fn(hole + new_board)

                ties = 0
                beat = True
                base = board_left
                for i in range(n_opp):
                    opp = [cache[drawn[base + 2 * i]],
                           cache[drawn[base + 2 * i + 1]]]
                    opp_score = eval_fn(opp + new_board)
                    if opp_score > my_score:
                        beat = False
                        break
                    if opp_score == my_score:
                        ties += 1
            else:
                # Range-conditioned path: pick combos per opponent, retry on
                # collision, fall back to uniform if range is unrecoverable.
                used = set(known)
                opp_holes = []
                aborted = False
                for combos in opp_combos:
                    if combos is None:
                        # Uniform from remaining deck
                        a, b = None, None
                        for _att in range(8):
                            ca = deck[randrange(len(deck))]
                            cb = deck[randrange(len(deck))]
                            if ca != cb and ca not in used and cb not in used:
                                a, b = ca, cb
                                break
                        if a is None:
                            aborted = True
                            break
                    else:
                        a, b = None, None
                        for _att in range(10):
                            ca, cb = combos[randrange(len(combos))]
                            if ca not in used and cb not in used:
                                a, b = ca, cb
                                break
                        if a is None:
                            # Fall back to uniform
                            for _att in range(8):
                                ca = deck[randrange(len(deck))]
                                cb = deck[randrange(len(deck))]
                                if ca != cb and ca not in used and cb not in used:
                                    a, b = ca, cb
                                    break
                            if a is None:
                                aborted = True
                                break
                    used.add(a)
                    used.add(b)
                    opp_holes.append((a, b))
                if aborted:
                    continue
                # Deal remaining board
                avail = [c for c in deck if c not in used]
                if len(avail) < board_left:
                    continue
                if board_left:
                    extra = sample(avail, board_left)
                    new_board = board + [cache[s] for s in extra]
                else:
                    new_board = board
                my_score = eval_fn(hole + new_board)

                ties = 0
                beat = True
                for (a, b) in opp_holes:
                    opp_score = eval_fn([cache[a], cache[b]] + new_board)
                    if opp_score > my_score:
                        beat = False
                        break
                    if opp_score == my_score:
                        ties += 1

            if beat:
                wins += 1.0 / (ties + 1)
            sims += 1

        if time.time() > deadline:
            break
        if sims >= 4000:
            break

    return (wins / sims) if sims else 0.5, sims


def _build_equity_table(time_budget=22.0):
    """Build the 169 × 5 preflop equity table during module load.

    The Fullhouse runner gives bots a free ~30 s warmup window before hand 1.
    We use ~22 s of it to MC each (canonical hand, opponent count) pair so
    `_multiway_equity` returns a real Monte-Carlo estimate at decision time
    instead of a heuristic exponent on the heads-up baseline.  Falls back to
    the heuristic for any cell we ran out of time on.

    In real eval7 (Linux, C extension) this finishes in ~3-5 s.  The local
    treys shim is ~5-10× slower; the budget is sized for the slow case.
    """
    deadline = time.time() + time_budget
    hands = list(_HU_EQUITY.keys())
    n_opps = (1, 2, 3, 4, 5)

    n_combos = len(hands) * len(n_opps)
    per_combo = max(0.005, time_budget / n_combos)

    for hand_key in hands:
        cards = _representative_cards(hand_key)
        for n_opp in n_opps:
            if time.time() >= deadline:
                return
            remaining = deadline - time.time()
            budget = min(per_combo, remaining)
            eq, sims = _monte_carlo_equity(cards, [], n_opp,
                                           time_budget=budget)
            # Only commit cells with a meaningful sample size.
            if sims >= 50:
                _PRECOMPUTED_EQUITY[(hand_key, n_opp)] = eq


# Run the precompute at module load.  No timeout is enforced on imports, so
# the 22 s budget is the only cap.  The warmup decide() call returns instantly.
_build_equity_table()


# ─────────────────────────────────────────────────────────────────────────────
# Opponent modelling (from match_action_log)
# ─────────────────────────────────────────────────────────────────────────────

_opp_model = {}      # bot_id -> stats dict

# Deep profiler + predictive model activate once this many hands have been
# seen.  50 was best on the diverse 66-bot stress field (rank 1.9 mean,
# 7/10 outright wins, +107K mean cum delta) — the small-field reference
# A/B preferred 100 but tournaments care about robustness on a varied field.
# Set 0 to always activate, 1000 to disable entirely (Tier-2-only).
_DEEP_AFTER_HAND = 50


def _reset_match_state():
    """Clear all per-match accumulators (preserve precomputed equity table).
    The test harness calls this before each match for a clean slate; in
    production each match runs in a fresh subprocess so this isn't needed."""
    global _last_log_anchor
    _opp_model.clear()
    _full_log.clear()
    _processed_hands.clear()
    _deep.clear()
    _archetype.clear()
    _self_pnl.clear()
    _opp_sig.clear()
    _opp_sig_total.clear()
    _spot_pnl.clear()
    _pending_spots.clear()
    _last_log_anchor = None
    _self_pnl_state["last_stack"] = None
    _self_pnl_state["last_hand"] = None
    _self_pnl_state["last_in_hand"] = set()


def _update_opp_model(state):
    """Recompute opponent stats from the rolling match action log.

    Walking the (≤200-entry) log is cheap — we used to gate by
    `len(log) == prev_len` but that breaks once the log saturates at 200,
    freezing the model for the remaining ~350 hands of the match.  Just
    recompute every call.
    """
    log = state.get("match_action_log") or []
    stats = {}
    for entry in log:
        bid = entry.get("bot_id")
        act = entry.get("action")
        if bid is None or act is None:
            continue
        s = stats.setdefault(bid, {
            "raises": 0, "calls": 0, "folds": 0, "checks": 0,
            "all_ins": 0, "blinds": 0, "voluntary": 0, "total": 0,
            # Bet-sizing tracking — sum and count of raise totals (in chips).
            # Match log doesn't have pot context, so we use absolute amounts
            # as a coarse "do they raise small or big" signal.
            "raise_sum": 0, "raise_n": 0,
        })
        s["total"] += 1
        amt = entry.get("amount") or 0
        if act in ("small_blind", "big_blind"):
            s["blinds"] += 1
        elif act == "raise":
            s["raises"] += 1
            s["voluntary"] += 1
            if amt > 0:
                s["raise_sum"] += amt
                s["raise_n"] += 1
        elif act == "all_in":
            s["all_ins"] += 1
            s["raises"] += 1
            s["voluntary"] += 1
            if amt > 0:
                s["raise_sum"] += amt
                s["raise_n"] += 1
        elif act == "call":
            s["calls"] += 1
            s["voluntary"] += 1
        elif act == "fold":
            s["folds"] += 1
        elif act == "check":
            s["checks"] += 1

    _opp_model.clear()
    _opp_model.update(stats)

    # Run the deep profiler — gated on hand count for the A/B toggle.
    # When _DEEP_AFTER_HAND > current max hand_num, fall back to Tier-2 logic
    # (deep profiler state stays empty → all downstream lookups return None
    # → decision functions degrade to their pre-profiler behaviour).
    log = state.get("match_action_log") or []
    max_hand = max((e.get("hand_num", 0) for e in log), default=0)
    if max_hand >= _DEEP_AFTER_HAND:
        try:
            _update_deep_profile(state)
        except Exception:
            # Deep profiler must never crash the main decide() flow.  Swallow.
            pass


def _opp_profile(bot_id):
    """Return (raise_freq, fold_freq, vol_freq, sample_n) for a given bot."""
    s = _opp_model.get(bot_id)
    if not s or s["total"] < 4:
        return 0.25, 0.40, 0.40, 0     # neutral default until we have data
    non_blind = max(s["total"] - s["blinds"], 1)
    raise_freq = s["raises"] / non_blind
    fold_freq = s["folds"] / non_blind
    vol_freq = s["voluntary"] / non_blind
    return raise_freq, fold_freq, vol_freq, non_blind


def _opp_avg_raise(bot_id):
    """Average raise total (chips) for an opponent.  Returns None if we
    don't have enough samples to be useful."""
    s = _opp_model.get(bot_id)
    if not s or s.get("raise_n", 0) < 4:
        return None
    return s["raise_sum"] / s["raise_n"]


# ─────────────────────────────────────────────────────────────────────────────
# Deep opponent profiler — builds richer per-bot signals than the rolling
# 200-entry _opp_model.  Maintains:
#   * an unbounded local log of every action we've seen this match (#1)
#   * a hand-replay engine that recovers street + position + pot-context (#2,#3)
#   * sequence patterns: cbet / double-barrel / triple-barrel rates (#4)
#   * per-opp bet-sizing histogram in (bet/pot) tiers (#5)
#   * archetype classification with simple counter-strategy hints (#6)
#   * our chip P&L vs each opponent (#7)
#   * fold-to-bet rate bucketed by bet size (#8)
# ─────────────────────────────────────────────────────────────────────────────

_full_log = []                     # cumulative match log (incremental)
_last_log_anchor = None            # signature of last entry processed
_processed_hands = set()           # hand_nums already replayed into deep stats
_deep = {}                         # bot_id -> deep stats dict
_archetype = {}                    # bot_id -> archetype label
_self_pnl = {}                     # bot_id -> our chip delta in pots vs them
_self_pnl_state = {                # ephemeral tracking
    "last_stack": None,
    "last_hand": None,
    "last_in_hand": set(),         # bot_ids in pot at last seen
}

_BET_SIZE_TIERS = ("small", "medium", "big", "overbet", "huge")  # <35,<65,<110,<200,>=200 % pot


def _bet_size_tier(bet_amount: int, pot_before: int) -> str:
    if pot_before <= 0 or bet_amount <= 0:
        return "small"
    r = bet_amount / pot_before
    if r < 0.35: return "small"
    if r < 0.65: return "medium"
    if r < 1.10: return "big"
    if r < 2.00: return "overbet"
    return "huge"


def _new_deep_entry():
    return {
        # action counts split by street
        "street_n": {s: 0 for s in ("preflop", "flop", "turn", "river")},
        "street_raise": {s: 0 for s in ("preflop", "flop", "turn", "river")},
        "street_call":  {s: 0 for s in ("preflop", "flop", "turn", "river")},
        "street_fold":  {s: 0 for s in ("preflop", "flop", "turn", "river")},
        "street_check": {s: 0 for s in ("preflop", "flop", "turn", "river")},
        # action counts by position role (btn/co/hj/utg/sb/bb)
        "pos_n":  {},   # pos -> total actions
        "pos_open": {}, # pos -> opens (preflop raises when no prior raise this hand)
        # Sequence patterns — voluntary continuation after own aggression
        "preflop_raises": 0,           # times this bot raised preflop
        "flop_cbet_after_pf_raise": 0, # times they bet flop after their own pf raise
        "flop_cbet_eligible": 0,       # times flop eligibility for cbet existed
        "turn_db_after_cbet": 0,       # double-barrel
        "turn_db_eligible": 0,
        "river_triple": 0,
        "river_triple_eligible": 0,
        # Bet sizing histogram (when they raise/bet) — counts per tier
        "size_hist": {t: 0 for t in _BET_SIZE_TIERS},
        # Fold-to-bet by size: when facing a bet/raise on flop+, did they fold?
        "fold_to_size": {t: {"fold": 0, "total": 0} for t in _BET_SIZE_TIERS},
        # Per-hand state (resets per hand)
        "_pf_raised_this_hand": False,
        "_flop_bet_this_hand": False,
        "_turn_bet_this_hand": False,
        "_last_hand_seen": -1,
    }


def _ingest_log(state):
    """Append new entries from match_action_log to our cumulative _full_log,
    using anchor-matching to deduplicate.  Returns the list of newly-seen
    entries (in chronological order)."""
    global _last_log_anchor
    log = state.get("match_action_log") or []
    if not log:
        return []

    new_entries = []
    if _last_log_anchor is None:
        new_entries = list(log)
    else:
        anchor_idx = -1
        for i in range(len(log) - 1, -1, -1):
            e = log[i]
            sig = (e.get("hand_num"), e.get("seat"),
                   e.get("action"), e.get("amount"))
            if sig == _last_log_anchor:
                anchor_idx = i
                break
        if anchor_idx >= 0:
            new_entries = list(log[anchor_idx + 1:])
        else:
            # Anchor was evicted — best-effort: include entries with hand_num
            # strictly newer than what we already have in _full_log.
            our_last_hand = _full_log[-1]["hand_num"] if _full_log else -1
            for e in log:
                if e.get("hand_num", -1) > our_last_hand:
                    new_entries.append(e)

    last = log[-1]
    _last_log_anchor = (last.get("hand_num"), last.get("seat"),
                        last.get("action"), last.get("amount"))

    for e in new_entries:
        _full_log.append(dict(e))
    return new_entries


def _replay_hand(actions):
    """Replay one hand's actions and yield (entry, street, pos, pot_before,
    bet_size_tier_or_None) for each non-blind action.  Best-effort — gets
    streets right for the common cases; some short all-in / 4-bet edge cases
    may be off by one street.  Good enough for stats aggregation."""
    if not actions:
        return
    seats_in_hand = sorted({a["seat"] for a in actions})
    if len(seats_in_hand) < 2:
        return
    sb_seat = next((a["seat"] for a in actions
                    if a["action"] == "small_blind"), None)
    bb_seat = next((a["seat"] for a in actions
                    if a["action"] == "big_blind"), None)
    if sb_seat is None or bb_seat is None:
        return

    # Position labels
    seat_order = seats_in_hand
    n = len(seat_order)
    if n == 2:
        dealer = sb_seat       # HU: dealer = SB
    else:
        sb_idx = seat_order.index(sb_seat)
        dealer = seat_order[(sb_idx - 1) % n]
    dealer_idx = seat_order.index(dealer)
    pos = {}
    for i, s in enumerate(seat_order):
        off = (i - dealer_idx) % n
        if n == 2:
            pos[s] = "btn" if off == 0 else "bb"
        else:
            if off == 0:
                pos[s] = "btn"
            elif off == 1:
                pos[s] = "sb"
            elif off == 2:
                pos[s] = "bb"
            elif off == n - 1:
                pos[s] = "co"
            elif off == n - 2 and n >= 5:
                pos[s] = "hj"
            else:
                pos[s] = "utg"

    folded = set()
    all_in = set()
    bet_this = {s: 0 for s in seat_order}
    pot = 0
    current_bet = 0
    last_aggression = 100  # BB
    streets = ["preflop", "flop", "turn", "river"]
    street_idx = 0
    acted_this_street = set()
    pf_raise_seen = False  # for BB option detection

    for a in actions:
        seat = a["seat"]; act = a["action"]; amt = a.get("amount") or 0
        if act == "small_blind":
            bet_this[seat] = amt; pot += amt
            current_bet = max(current_bet, amt)
            yield a, "preflop", pos.get(seat, "?"), pot - amt, None
            continue
        if act == "big_blind":
            bet_this[seat] = amt; pot += amt
            current_bet = max(current_bet, amt)
            yield a, "preflop", pos.get(seat, "?"), pot - amt, None
            continue
        if seat in folded or seat in all_in:
            continue

        cur_street = streets[street_idx] if street_idx < 4 else "river"
        pot_before = pot
        size_tier = None
        if act in ("raise", "all_in"):
            # bet the bot is making (their increment over the pot)
            new_chips = max(0, amt - bet_this[seat])
            size_tier = _bet_size_tier(new_chips, pot_before) if pot_before > 0 else "small"

        yield a, cur_street, pos.get(seat, "?"), pot_before, size_tier

        if act == "fold":
            folded.add(seat)
        elif act == "check":
            pass
        elif act == "call":
            owed = current_bet - bet_this[seat]
            bet_this[seat] += owed; pot += owed
        elif act == "raise":
            owed = max(0, amt - bet_this[seat])
            bet_this[seat] = amt; pot += owed
            new_size = amt - current_bet
            if new_size >= last_aggression:
                last_aggression = new_size
                acted_this_street = {seat}
            current_bet = amt
            if cur_street == "preflop":
                pf_raise_seen = True
        elif act == "all_in":
            owed = max(0, amt - bet_this[seat])
            bet_this[seat] = amt; pot += owed
            if amt > current_bet:
                new_size = amt - current_bet
                if new_size >= last_aggression:
                    last_aggression = new_size
                    acted_this_street = {seat}
                current_bet = amt
                if cur_street == "preflop":
                    pf_raise_seen = True
            all_in.add(seat)

        acted_this_street.add(seat)

        active = set(seat_order) - folded - all_in
        if not active:
            return
        all_acted = all(s in acted_this_street for s in active)
        all_match = all(bet_this[s] == current_bet for s in active)
        if all_acted and all_match:
            # Preflop BB option: if no one raised, BB still gets to check/raise
            if (cur_street == "preflop" and not pf_raise_seen
                    and bb_seat in active and bb_seat not in acted_this_street):
                continue
            street_idx += 1
            current_bet = 0
            last_aggression = 100
            for s in seat_order:
                bet_this[s] = 0
            acted_this_street = set()


def _process_complete_hands():
    """Replay each complete hand we haven't yet processed, updating _deep
    stats per opponent.  A hand is 'complete' when we've seen the start of
    a later hand (or the match log buffer has rolled past it)."""
    if not _full_log:
        return
    by_hand = {}
    for e in _full_log:
        by_hand.setdefault(e["hand_num"], []).append(e)

    # Heuristic: hand H is complete if max(_full_log hand_num) > H, i.e. there
    # is at least one entry from a later hand.
    max_hand = max(by_hand)
    for h, actions in sorted(by_hand.items()):
        if h >= max_hand:
            break  # current hand still in progress, skip
        if h in _processed_hands:
            continue
        _replay_into_deep(h, actions)
        _processed_hands.add(h)


def _replay_into_deep(hand_num, actions):
    """Take one complete hand and update _deep stats from its replay.
    Also records action signatures into _opp_sig for the predictive model."""
    seen_seats = {a["seat"] for a in actions}
    seat_to_bid = {}
    for a in actions:
        seat_to_bid[a["seat"]] = a.get("bot_id")
    for s in seen_seats:
        bid = seat_to_bid.get(s)
        if bid is None:
            continue
        d = _deep.setdefault(bid, _new_deep_entry())
        d["_pf_raised_this_hand"] = False
        d["_flop_bet_this_hand"] = False
        d["_turn_bet_this_hand"] = False
        d["_last_hand_seen"] = hand_num

    # Track per-street state we need for signature labelling.  The replay
    # generator yields the post-action state of street/pot but we need the
    # raises_before count *at the moment of each action*, so we re-track here.
    raises_in_street = {}            # street -> int
    pf_aggressor_seat = None
    last_street = "preflop"
    # Track the size tier of the most recent aggression on this street so we
    # can attribute subsequent fold/call decisions to the right size bucket.
    cur_aggression_tier = None       # str | None — None means no live bet

    for entry, street, pos, pot_before, size_tier in _replay_hand(actions):
        bid = entry.get("bot_id")
        seat = entry.get("seat")
        act = entry.get("action")
        if bid is None or act is None:
            continue
        if act in ("small_blind", "big_blind"):
            continue

        # Reset per-street state on street transition
        if street != last_street:
            raises_in_street[street] = 0
            cur_aggression_tier = None
            last_street = street

        raises_before = raises_in_street.get(street, 0)
        was_pf_aggr = (seat == pf_aggressor_seat)
        sig = _action_signature(act, street, raises_before,
                                was_pf_aggressor=was_pf_aggr)
        if sig is not None:
            _record_opp_signature(bid, sig)

        d = _deep.setdefault(bid, _new_deep_entry())
        d["street_n"][street] = d["street_n"].get(street, 0) + 1
        d["pos_n"][pos] = d["pos_n"].get(pos, 0) + 1

        # Fold-to-size / call-to-size tracking: if there's a live aggression
        # tier when this player acts, log their response (fold or continue) to
        # that tier.  Only meaningful postflop and only when actually facing
        # a bet (i.e. cur_aggression_tier set).
        if (street != "preflop" and cur_aggression_tier is not None
                and act in ("fold", "call", "raise", "all_in")):
            tier = cur_aggression_tier
            d["fold_to_size"][tier]["total"] += 1
            if act == "fold":
                d["fold_to_size"][tier]["fold"] += 1

        if act == "fold":
            d["street_fold"][street] += 1
        elif act == "call":
            d["street_call"][street] += 1
        elif act == "check":
            d["street_check"][street] += 1
        elif act in ("raise", "all_in"):
            d["street_raise"][street] += 1
            if size_tier is not None:
                d["size_hist"][size_tier] = d["size_hist"].get(size_tier, 0) + 1
                # The aggression tier for subsequent actions is now THIS bet.
                cur_aggression_tier = size_tier
            if street == "preflop":
                d["pos_open"][pos] = d["pos_open"].get(pos, 0) + 1
                d["_pf_raised_this_hand"] = True
                d["preflop_raises"] += 1
                pf_aggressor_seat = seat
            elif street == "flop":
                if d["_pf_raised_this_hand"]:
                    d["flop_cbet_after_pf_raise"] += 1
                d["_flop_bet_this_hand"] = True
            elif street == "turn":
                if d["_flop_bet_this_hand"]:
                    d["turn_db_after_cbet"] += 1
                d["_turn_bet_this_hand"] = True
            elif street == "river":
                if d["_turn_bet_this_hand"]:
                    d["river_triple"] += 1
            raises_in_street[street] = raises_in_street.get(street, 0) + 1

        # Eligibility tracking — when does a player get to "have a chance" at
        # cbet/db/triple?  For now we count via the seat-based heuristic: if
        # this player raised pre and they reached the flop, eligible for cbet.
        # We approximate by setting eligibility flags when we process actions.

    # Eligibility increments — once per hand after replay
    for s in seen_seats:
        bid = seat_to_bid.get(s)
        if bid is None:
            continue
        d = _deep[bid]
        if d["_pf_raised_this_hand"]:
            d["flop_cbet_eligible"] += 1
            if d["_flop_bet_this_hand"]:
                d["turn_db_eligible"] += 1
                if d["_turn_bet_this_hand"]:
                    d["river_triple_eligible"] += 1


# ─────────────────────────────────────────────────────────────────────────────
# Archetype classification (#6) — labels each opponent based on cumulative
# behaviour after a minimum sample size, then surfaces counter hints to
# the decision logic.
# ─────────────────────────────────────────────────────────────────────────────

def _classify_archetypes():
    """(Re-)label each opponent with a coarse archetype tag."""
    for bid, d in _deep.items():
        total = sum(d["street_n"].values())
        pf_n = d["street_n"]["preflop"]
        pf_raise = d["street_raise"]["preflop"] / max(pf_n, 1)

        # Early maniac signal: ≥4 PF actions, ≥80% raise rate.
        # Don't wait for the full 12-action threshold — by then we've already
        # lost chips before applying wide defense.
        if pf_n >= 4 and pf_raise >= 0.80:
            _archetype[bid] = "maniac"
            continue

        # Bootstrap from rolling model when deep data is still thin.
        # Uses coarser raise/fold freq from the match-action-log model.
        if total < 12:
            profile = _opp_profile(bid)
            roll_raise, roll_fold, _, roll_n = profile
            if roll_n >= 5:
                if roll_raise >= 0.75:  # 0.65 was catching overbet/aggressor as false maniacs
                    _archetype[bid] = "maniac"
                elif roll_fold >= 0.65:
                    _archetype[bid] = "nit"
                else:
                    _archetype[bid] = "unknown"
            else:
                _archetype[bid] = "unknown"
            continue

        pf_fold = d["street_fold"]["preflop"] / max(pf_n, 1)
        post_n = d["street_n"]["flop"] + d["street_n"]["turn"] + d["street_n"]["river"]
        post_raise = (d["street_raise"]["flop"] + d["street_raise"]["turn"]
                      + d["street_raise"]["river"]) / max(post_n, 1)
        post_fold = (d["street_fold"]["flop"] + d["street_fold"]["turn"]
                     + d["street_fold"]["river"]) / max(post_n, 1)
        post_call = (d["street_call"]["flop"] + d["street_call"]["turn"]
                     + d["street_call"]["river"]) / max(post_n, 1)

        # Order matters — earliest match wins.
        # Overbet archetype: most bets are 85%+ pot sized
        total_raises = sum(d["size_hist"].values())
        big_bets = d["size_hist"].get("overbet", 0) + d["size_hist"].get("huge", 0)
        if total_raises >= 6 and big_bets / total_raises >= 0.50:
            _archetype[bid] = "overbet"
            continue
        if pf_raise > 0.55 or post_raise > 0.55:
            _archetype[bid] = "maniac"
        elif pf_fold > 0.70 and pf_raise < 0.10:
            _archetype[bid] = "nit"
        elif post_call > 0.55 and post_fold < 0.20 and post_raise < 0.20:
            _archetype[bid] = "station"
        elif pf_raise > 0.25 and post_raise > 0.25 and pf_fold < 0.55:
            _archetype[bid] = "lag"
        elif pf_raise > 0.10 and pf_raise < 0.30 and post_fold < 0.40:
            _archetype[bid] = "tag"
        else:
            _archetype[bid] = "default"


def _opp_archetype(bot_id):
    return _archetype.get(bot_id, "unknown")


def _archetype_counters(archetype: str) -> dict:
    """Return additive threshold tweaks for the decision logic.

    Equity deltas are deliberately small because range-conditioned MC already
    accounts for opponent type to first order.  These counters mostly affect
    *off-equity* dimensions (bluff frequency, opening width) that MC can't.

    * 'value_eq_delta'     — added to value-bet eq thresholds (small)
    * 'call_eq_delta'      — added to call edge requirement (small)
    * 'bluff_freq_mult'    — multiplier on bluff frequencies (large effect)
    * 'open_threshold_delta' — added to preflop open thresholds (medium effect)
    """
    if archetype == "maniac":
        # Never folds → never bluff; open tighter to reduce pot exposure.
        # Neutral deltas: their range IS wide so calling is fine, but don't
        # loosen thresholds — we need to avoid marginal all-in commits.
        return {"value_eq_delta": 0.0, "call_eq_delta": 0.0,
                "bluff_freq_mult": 0.0, "open_threshold_delta": +0.05,
                "three_bet_defense_wide": True, "value_size_mult": 1.05}
    if archetype == "overbet":
        # Overbets everything — range is wide, NOT polarized.  Call wider,
        # raise for value with any made hand, never fold to size alone.
        return {"value_eq_delta": -0.04, "call_eq_delta": -0.04,
                "bluff_freq_mult": 0.0, "open_threshold_delta": 0.0,
                "three_bet_defense_wide": False, "value_size_mult": 1.0}
    if archetype == "nit":
        # Folds to anything → bluff more; smaller value bets to keep them in
        return {"value_eq_delta": +0.03, "call_eq_delta": +0.025,
                "bluff_freq_mult": 1.6, "open_threshold_delta": -0.04,
                "three_bet_defense_wide": False, "value_size_mult": 0.80}
    if archetype == "station":
        # Calls wide → bet 1.0–1.2× pot for value, never bluff
        return {"value_eq_delta": -0.05, "call_eq_delta": 0.0,
                "bluff_freq_mult": 0.0, "open_threshold_delta": 0.0,
                "three_bet_defense_wide": False, "value_size_mult": 1.20}
    if archetype == "lag":
        return {"value_eq_delta": 0.0, "call_eq_delta": -0.01,
                "bluff_freq_mult": 0.7, "open_threshold_delta": 0.0,
                "three_bet_defense_wide": False, "value_size_mult": 1.0}
    if archetype == "tag":
        return {"value_eq_delta": +0.01, "call_eq_delta": +0.01,
                "bluff_freq_mult": 0.85, "open_threshold_delta": 0.0,
                "three_bet_defense_wide": False, "value_size_mult": 1.0}
    return {"value_eq_delta": 0.0, "call_eq_delta": 0.0,
            "bluff_freq_mult": 1.0, "open_threshold_delta": 0.0,
            "three_bet_defense_wide": False, "value_size_mult": 1.0}


def _aggregated_counters(in_hand_bot_ids):
    """Average the counters for opponents currently in the hand."""
    counters = [_archetype_counters(_opp_archetype(bid)) for bid in in_hand_bot_ids]
    if not counters:
        return _archetype_counters("unknown")
    keys = counters[0].keys()
    return {k: sum(c[k] for c in counters) / len(counters) for k in keys}


# ─────────────────────────────────────────────────────────────────────────────
# Self vs opponent P&L tracker (#7)
# ─────────────────────────────────────────────────────────────────────────────

def _update_self_pnl(state):
    """Track our chip flow and attribute it to opponents in the prior hand."""
    your_seat = state["seat_to_act"]
    me = next((p for p in state["players"] if p["seat"] == your_seat), None)
    if me is None:
        return
    cur_stack = me.get("stack", 0)
    hand_id = state.get("hand_id", "")
    last_stack = _self_pnl_state["last_stack"]
    last_hand = _self_pnl_state["last_hand"]
    last_in = _self_pnl_state["last_in_hand"]

    if last_stack is not None and last_hand is not None and hand_id != last_hand:
        # New hand started — attribute the stack delta of the previous hand.
        delta = cur_stack - last_stack
        if delta != 0 and last_in:
            share = delta / len(last_in)
            for bid in last_in:
                _self_pnl[bid] = _self_pnl.get(bid, 0) + share
        # Also flush #9 per-spot tracker — distribute the same delta across
        # whichever spots we played in the previous hand.
        _flush_pending_spots(delta)

    # Record current hand's opponents (for future attribution)
    in_hand_now = {p["bot_id"] for p in state["players"]
                   if p["seat"] != your_seat
                   and not p.get("is_folded")
                   and p.get("state") != "busted"}
    _self_pnl_state["last_stack"] = cur_stack
    _self_pnl_state["last_hand"] = hand_id
    _self_pnl_state["last_in_hand"] = in_hand_now


def _opp_self_pnl(bot_id) -> float:
    return _self_pnl.get(bot_id, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# #9 — Online per-spot P&L tracker (passive, no decision biasing yet)
#
# Original Tier-3 spec called for an online classifier that predicts opponent
# ranges from observed outcomes.  But the runner only delivers `warmup` and
# `action_request` states to bots — never `hand_complete` or showdown
# reveals.  So we cannot actually observe opponent hands.
#
# What we *can* observe: our own chip delta when a hand ends.  This tracker
# attributes that delta to coarse "spot signatures" we encountered (e.g.
# "flop bet vs single opp on wet board").  Over enough hands the running
# average becomes useful for diagnosing leaky spots.
#
# Currently *not wired into decisions* — both #7 (GTO blueprint) and the
# minimal #8 line awareness regressed when biasing decisions on this kind
# of data.  Kept as data infrastructure: future improvements (e.g.
# offline analysis, per-bot tuning between matches) can read these stats.
# ─────────────────────────────────────────────────────────────────────────────

_spot_pnl = {}                  # spot_sig -> [sum_pnl, count]
_pending_spots = set()          # spots from this hand, attributed at hand-end


def _spot_signature(state, action_kind: str) -> tuple:
    """Coarse description of the current spot we just took an action in.
    Tuple of (street, action_kind, n_active_opps, board_wetness_bucket)."""
    n_opp = _n_active_opponents(state)
    wet = _board_wetness(state.get("community_cards") or [])
    return (state.get("street", "?"), action_kind, min(n_opp, 3),
            "dry" if wet == 0 else "wet")


def _record_my_spot(state, action_kind: str):
    """Note that I just took `action_kind` in this spot.  At hand-end the
    chip delta is attributed equally across all spots I encountered."""
    sig = _spot_signature(state, action_kind)
    _pending_spots.add(sig)


def _flush_pending_spots(pnl_delta: float):
    """Distribute a hand's chip delta evenly across the spots played."""
    if not _pending_spots:
        return
    share = pnl_delta / len(_pending_spots)
    for sig in _pending_spots:
        cur = _spot_pnl.get(sig, [0.0, 0])
        cur[0] += share
        cur[1] += 1
        _spot_pnl[sig] = cur
    _pending_spots.clear()


def _spot_avg_pnl(sig):
    """Mean P&L for this spot, or None when sample too small.
    Minimum 30 samples required to reduce variance-driven drift.
    """
    bucket = _spot_pnl.get(sig)
    if bucket is None or bucket[1] < 30:
        return None
    return bucket[0] / bucket[1]


# ─────────────────────────────────────────────────────────────────────────────
# Deep-profile accessors for #1, #2, #3 from the Tier-1-improvements list:
#   * position-conditional open frequencies
#   * cbet / double-barrel / triple-barrel frequencies
#   * fold-to-size rate by bet sizing tier
# All return None when sample size is too small to be reliable.
# ─────────────────────────────────────────────────────────────────────────────

def _opp_pos_open_freq(bot_id, position):
    """Position-specific raise-frequency.  E.g. how often does this opp raise
    when sitting at BTN vs UTG?  Returns None unless we have ≥6 actions from
    the requested position."""
    d = _deep.get(bot_id)
    if d is None:
        return None
    n = d["pos_n"].get(position, 0)
    if n < 6:
        return None
    return d["pos_open"].get(position, 0) / n


def _opp_cbet_freq(bot_id):
    """How often the opp continuation-bets the flop after raising preflop.
    Returns None unless we have ≥4 cbet-eligible spots."""
    d = _deep.get(bot_id)
    if d is None or d["flop_cbet_eligible"] < 4:
        return None
    return d["flop_cbet_after_pf_raise"] / d["flop_cbet_eligible"]


def _opp_double_barrel_freq(bot_id):
    """Turn-bet frequency conditional on having c-bet the flop."""
    d = _deep.get(bot_id)
    if d is None or d["turn_db_eligible"] < 3:
        return None
    return d["turn_db_after_cbet"] / d["turn_db_eligible"]


def _opp_triple_barrel_freq(bot_id):
    """River-bet frequency conditional on having barreled both flop and turn."""
    d = _deep.get(bot_id)
    if d is None or d["river_triple_eligible"] < 2:
        return None
    return d["river_triple"] / d["river_triple_eligible"]


def _opp_fold_to_size_rate(bot_id, tier):
    """Fold rate when this opp faces a bet/raise of the given size tier.
    `tier` ∈ _BET_SIZE_TIERS.  Returns None unless ≥4 observations of that
    tier (≥6 for 'huge' / 'overbet' since they're more variance-prone)."""
    d = _deep.get(bot_id)
    if d is None:
        return None
    bucket = d["fold_to_size"].get(tier)
    if bucket is None:
        return None
    min_n = 6 if tier in ("huge", "overbet") else 4
    if bucket["total"] < min_n:
        return None
    return bucket["fold"] / bucket["total"]


def _avg_opp_fold_to_size(bot_ids, tier):
    """Average fold-to-size rate across a list of opponents.  Returns None if
    none of them have data for this tier."""
    rates = [r for r in (_opp_fold_to_size_rate(b, tier) for b in bot_ids)
             if r is not None]
    if not rates:
        return None
    return sum(rates) / len(rates)


# ─────────────────────────────────────────────────────────────────────────────
# Deep update entry-point — called from _update_opp_model
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Predictive opponent model (Layer 4 — beyond deep profiler)
#
# Builds per-opponent action-signature frequencies during hand replay, then
# uses the most-informative signature in the current hand to infer a Bayesian
# range posterior that's strictly sharper than the aggregate raise_freq.
#
# Reward feedback: per-opponent cumulative P&L (`_self_pnl`) drives a caution
# multiplier — if we're net-negative against an opp, tighten value & call
# thresholds against them.
# ─────────────────────────────────────────────────────────────────────────────

# Per-opponent action signature counts.  Updated during _replay_into_deep so
# we don't duplicate replay work.
_opp_sig = {}            # bot_id -> {signature: count}
_opp_sig_total = {}      # bot_id -> int (sum of all counts)

# Signature → typical range character.  Frequencies less than the listed
# floor are clamped (so a one-off open doesn't imply a 0%-of-hands range).
_SIG_RANGE_BOUNDS = {
    "pf_open":         (0.05, 0.85),
    "pf_3bet":         (0.02, 0.30),
    "pf_4bet":         (0.01, 0.10),
    "pf_limp":         (0.10, 0.65),
    "pf_call_open":    (0.10, 0.50),
    "pf_call_3bet":    (0.04, 0.20),
    "pf_check":        (0.20, 0.70),    # BB checking option
    "flop_cbet":       (0.20, 0.85),    # cbet ranges are wide; use floor 20%
    "flop_lead":       (0.10, 0.50),    # leading without pf init = stronger
    "flop_raise":      (0.04, 0.20),    # flop raise = much narrower
    "flop_call":       (0.20, 0.65),
    "flop_check":      (0.30, 0.90),
    "flop_fold":       (0.40, 1.00),
    "turn_barrel":     (0.10, 0.50),
    "turn_lead":       (0.06, 0.30),
    "turn_raise":      (0.03, 0.15),
    "turn_call":       (0.15, 0.45),
    "turn_check":      (0.30, 0.85),
    "turn_fold":       (0.40, 1.00),
    "river_barrel":    (0.05, 0.30),
    "river_lead":      (0.04, 0.20),
    "river_raise":     (0.02, 0.10),
    "river_call":      (0.10, 0.35),
    "river_check":     (0.30, 0.80),
    "river_fold":      (0.40, 1.00),
}


def _action_signature(action: str, street: str, raises_before: int,
                      was_pf_aggressor: bool) -> str:
    """Map (action, street, prior raises this street, pf-aggressor flag) to a
    coarse strategic signature.  Returns None for blinds."""
    if action in ("small_blind", "big_blind"):
        return None
    if street == "preflop":
        if action in ("raise", "all_in"):
            return ["pf_open", "pf_3bet", "pf_4bet"][min(raises_before, 2)]
        if action == "call":
            return ["pf_limp", "pf_call_open", "pf_call_3bet"][min(raises_before, 2)]
        if action == "fold":
            return "pf_fold"
        return "pf_check"
    # postflop
    if action in ("raise", "all_in"):
        if raises_before == 0:
            # First aggression on this street — distinguish cbet vs lead
            return f"{street}_cbet" if (was_pf_aggressor and street == "flop") \
                else (f"{street}_barrel" if (was_pf_aggressor and street != "flop")
                      else f"{street}_lead")
        return f"{street}_raise"
    if action == "call":
        return f"{street}_call"
    if action == "fold":
        return f"{street}_fold"
    return f"{street}_check"


def _record_opp_signature(bot_id: str, signature: str):
    if signature is None:
        return
    bucket = _opp_sig.setdefault(bot_id, {})
    bucket[signature] = bucket.get(signature, 0) + 1
    _opp_sig_total[bot_id] = _opp_sig_total.get(bot_id, 0) + 1


def _opp_sig_freq(bot_id: str, signature: str):
    """Relative frequency of this signature for this opponent.  Returns None
    if we don't have enough data on either:
      * the opp overall (≥10 total actions), OR
      * this specific signature (≥3 observations)
    A 1/100 single-sighting of a rare signature would otherwise produce a
    misleadingly tight range estimate."""
    total = _opp_sig_total.get(bot_id, 0)
    if total < 10:
        return None
    sig_count = _opp_sig.get(bot_id, {}).get(signature, 0)
    if sig_count < 3:
        return None
    return sig_count / total


def _signature_to_range_pct(signature: str, freq: float) -> float:
    """Map a signature + observed frequency to an estimated range percentile.
    Honors per-signature bounds so a single-action sample doesn't produce
    crazy ranges."""
    bounds = _SIG_RANGE_BOUNDS.get(signature)
    if bounds is None:
        return max(0.05, min(0.90, freq))
    lo, hi = bounds
    return max(lo, min(hi, freq))


def _infer_opp_range_v2(state, opp_seat: int, opp_bot_id: str):
    """V2 range inference: walk this hand's action_log, classify each of the
    opponent's actions into a signature, and return the range implied by the
    *narrowest* signature they've shown.

    Beyond plain signature frequency, v2 also conditions on:
      * **position** — `pf_open` from BTN ≠ `pf_open` from UTG; uses
        `_opp_pos_open_freq` when we have ≥6 actions from that position
      * **street-continuation rates** — `flop_cbet` is interpreted as
        cbet_freq × open_range, much sharper than the raw cbet signature
        frequency.  Same logic for `turn_barrel` (×db_freq) and
        `river_barrel` (×triple_freq)
    Falls back to plain signature frequency, then v1, when data is sparse."""
    actions = state.get("action_log", [])
    if not actions:
        return _infer_opp_range(state, opp_seat, opp_bot_id)

    seats_in_hand = sorted({a["seat"] for a in actions})
    if len(seats_in_hand) < 2:
        return _infer_opp_range(state, opp_seat, opp_bot_id)

    raises_in_street = {}
    pf_aggressor_seat = None
    last_street = "preflop"
    best_pct = None

    # _replay_hand walks actions and yields (entry, street, position, pot_before, size_tier)
    # — exactly what we need for position-aware signature lookups.
    for entry, street, pos, _pot_before, _size_tier in _replay_hand(actions):
        seat = entry["seat"]; act = entry["action"]
        if act in ("small_blind", "big_blind"):
            continue

        if street != last_street:
            raises_in_street[street] = 0
            last_street = street

        raises_before = raises_in_street.get(street, 0)

        if seat == opp_seat:
            sig = _action_signature(act, street, raises_before,
                                    was_pf_aggressor=(opp_seat == pf_aggressor_seat))
            pct = _range_pct_for_signature(opp_bot_id, sig, pos)
            if pct is not None and (best_pct is None or pct < best_pct):
                best_pct = pct

        # Update raises counter when we see aggression this street
        if act in ("raise", "all_in"):
            raises_in_street[street] = raises_in_street.get(street, 0) + 1
            if street == "preflop":
                pf_aggressor_seat = seat

    if best_pct is None:
        return _infer_opp_range(state, opp_seat, opp_bot_id)
    return _top_pct_hands(best_pct)


def _range_pct_for_signature(opp_bot_id, sig, pos):
    """Best-available range percentile for a (signature, position) pair.

    Tries in priority order:
      1. position-conditional pf-open freq (most specific)
      2. street-continuation chain (cbet → cbet × open; db → db × cbet × open;
         triple → triple × db × cbet × open)
      3. plain signature frequency
    Returns None if no path produces enough samples.
    """
    # --- 1. Position-conditional preflop open ---
    if sig == "pf_open":
        pf_pct = _opp_pos_open_freq(opp_bot_id, pos)
        if pf_pct is not None:
            return max(0.05, min(0.85, pf_pct))

    # --- 2. Postflop continuation chains ---
    if sig in ("flop_cbet",):
        cb = _opp_cbet_freq(opp_bot_id)
        if cb is not None:
            base = (_opp_pos_open_freq(opp_bot_id, pos)
                    or _opp_sig_freq(opp_bot_id, "pf_open")
                    or 0.25)
            # cbet range = cbet_freq × open_range
            return max(0.05, min(0.85, cb * base))

    if sig == "turn_barrel":
        db = _opp_double_barrel_freq(opp_bot_id)
        if db is not None:
            cb = _opp_cbet_freq(opp_bot_id) or 0.6
            base = (_opp_pos_open_freq(opp_bot_id, pos)
                    or _opp_sig_freq(opp_bot_id, "pf_open")
                    or 0.25)
            return max(0.04, min(0.50, db * cb * base))

    if sig == "river_barrel":
        tb = _opp_triple_barrel_freq(opp_bot_id)
        if tb is not None:
            db = _opp_double_barrel_freq(opp_bot_id) or 0.5
            cb = _opp_cbet_freq(opp_bot_id) or 0.6
            base = (_opp_pos_open_freq(opp_bot_id, pos)
                    or _opp_sig_freq(opp_bot_id, "pf_open")
                    or 0.25)
            return max(0.02, min(0.30, tb * db * cb * base))

    # --- 3. Generic signature-frequency fallback ---
    freq = _opp_sig_freq(opp_bot_id, sig)
    if freq is not None:
        return _signature_to_range_pct(sig, freq)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Reward feedback: per-opponent caution multiplier based on cumulative P&L.
# ─────────────────────────────────────────────────────────────────────────────

def _opp_caution_factor(bot_ids):
    """Return a caution multiplier in [0.7, 1.3] based on our cumulative P&L
    vs the opponents currently in the hand.  >1.0 = tighten (we're losing to
    them), <1.0 = loosen (we're winning)."""
    if not bot_ids:
        return 1.0
    total = 0.0
    samples = 0
    for bid in bot_ids:
        pnl = _self_pnl.get(bid)
        if pnl is None:
            continue
        # Normalize by ~1 BB unit: every -1000 chips lost → 0.05 caution.
        total += pnl
        samples += 1
    if samples == 0:
        return 1.0
    avg = total / samples
    # Map avg P&L to caution factor: -10000 → 1.3, +10000 → 0.7
    factor = 1.0 - (avg / 50000.0)  # 50k full swing
    return max(0.7, min(1.3, factor))


def _maybe_reset_for_new_match(state):
    """Production runs each match in a fresh subprocess so module state is
    clean.  In local in-process test harnesses we need to detect a fresh
    match (hand_num goes backwards) and reset to avoid contaminating stats
    across matches.  This is also a free safety net even in production."""
    global _last_log_anchor
    log = state.get("match_action_log") or []
    if not _full_log:
        return
    if log:
        first_hand_in_log = log[0].get("hand_num", -1)
    else:
        first_hand_in_log = -1
    last_local_hand = _full_log[-1].get("hand_num", -1)
    # If we have a local cumulative log that ends at hand X but the engine
    # is now sending us a log that starts at hand 0 (or smaller), the match
    # must have restarted.
    if first_hand_in_log == 0 and last_local_hand > 5:
        _full_log.clear()
        _processed_hands.clear()
        _deep.clear()
        _archetype.clear()
        _self_pnl.clear()
        _opp_sig.clear()
        _opp_sig_total.clear()
        _spot_pnl.clear()
        _pending_spots.clear()
        _last_log_anchor = None
        _self_pnl_state["last_stack"] = None
        _self_pnl_state["last_hand"] = None
        _self_pnl_state["last_in_hand"] = set()


def _update_deep_profile(state):
    """Run the deep profiler: ingest log, replay completed hands, classify."""
    _maybe_reset_for_new_match(state)
    _ingest_log(state)
    _process_complete_hands()
    _classify_archetypes()
    _update_self_pnl(state)


def _tournament_pressure(state) -> float:
    """Return a stack-pressure multiplier in [0.75, 1.25].
    > 1.0 means we have chips to spare and should apply pressure;
    < 1.0 means we are short and should tighten commit thresholds."""
    players = state.get("players", [])
    stacks = [p.get("stack", 0) for p in players
              if p.get("state") != "busted" and p.get("stack", 0) > 0]
    if len(stacks) < 2:
        return 1.0
    avg = sum(stacks) / len(stacks)
    if avg <= 0:
        return 1.0
    your_seat = state["seat_to_act"]
    me = next((p for p in players if p["seat"] == your_seat), None)
    if me is None:
        return 1.0
    ratio = me.get("stack", avg) / avg
    # ratio > 1 → big stack → pressure multiplier > 1 (loosen)
    # ratio < 1 → short stack → pressure multiplier < 1 (tighten)
    return max(0.75, min(1.25, 0.75 + 0.50 * ratio))


# ─────────────────────────────────────────────────────────────────────────────
# Mixed strategies — sigmoid for smoothing hard equity cliffs
# ─────────────────────────────────────────────────────────────────────────────

def _smooth_p(value: float, threshold: float, sharpness: float = 18.0) -> float:
    """Probability that `value` exceeds `threshold` under a smooth transition.
    Higher `sharpness` ≈ closer to a hard threshold; lower ≈ more mixing.
    Used to soften cliff decisions where MC noise can flip-flop us."""
    x = (value - threshold) * sharpness
    if x > 12:
        return 1.0
    if x < -12:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


# ─────────────────────────────────────────────────────────────────────────────
# Implied / reverse-implied odds adjustments
# ─────────────────────────────────────────────────────────────────────────────

def _implied_pot_odds(pot: int, owed: int, tier: str, draw: str,
                      stack: int, n_opp: int) -> float:
    """Adjusted pot odds that account for implied / reverse-implied odds.

    For drawing hands and concealed monsters (sets), we expect to win extra
    chips on later streets when we hit — so the *effective* pot is bigger
    than the literal current pot.  For weak made hands prone to being
    dominated, the effective pot is *smaller* (we lose more on bad runouts
    than we win on good ones).

    Returns a pot_odds value in [0, 1].
    """
    if owed <= 0:
        return 0.0
    spr = stack / max(pot, 1)
    factor = 1.0

    # Implied: expect future bets when we hit
    if tier == "set":
        factor += min(0.55, 0.18 * spr)
    elif draw == "combo_draw":
        factor += min(0.50, 0.15 * spr)
    elif draw == "flush_draw":
        factor += min(0.40, 0.12 * spr)
    elif draw == "oesd":
        factor += min(0.30, 0.10 * spr)
    elif draw == "gutshot":
        factor += min(0.18, 0.06 * spr)

    # Reverse implied: weak made hands that bleed when behind
    if tier in ("tp_weak", "low_pair", "mid_pair", "underpair"):
        factor -= min(0.35, 0.10 * spr)
    elif tier == "weak_pair":
        factor -= min(0.30, 0.08 * spr)

    # Multi-way damps implied odds (people fold; harder to get paid)
    if n_opp >= 3:
        factor = max(1.0, factor) * 0.85 + (1.0 - 0.85) * 1.0

    factor = max(0.5, min(2.0, factor))
    effective_pot = pot * factor
    return owed / max(1, effective_pot + owed)


# ─────────────────────────────────────────────────────────────────────────────
# Position
# ─────────────────────────────────────────────────────────────────────────────

def _position_score(state):
    """Return a 0..1 lateness score where 1.0 means last to act this street.
    Uses sorted active seat list so sparse seat numbers don't break position."""
    your_seat = state["seat_to_act"]
    players = state["players"]

    def is_active(p):
        return (not p.get("is_folded")
                and not p.get("is_all_in")
                and p.get("state") != "busted"
                and p.get("stack", 0) > 0)

    me = next((p for p in players if p["seat"] == your_seat), None)
    if me is None or not is_active(me):
        return 0.5

    active_seats = sorted(p["seat"] for p in players if is_active(p))
    n_active = len(active_seats)
    if n_active <= 1:
        return 1.0

    my_idx = active_seats.index(your_seat) if your_seat in active_seats else -1
    if my_idx < 0:
        return 0.5

    # Count how many active players act after me in seat order
    after = n_active - 1 - my_idx
    return 1.0 - after / max(n_active - 1, 1)


def _n_active_opponents(state):
    your_seat = state["seat_to_act"]
    cnt = 0
    for p in state["players"]:
        if p["seat"] == your_seat:
            continue
        if p.get("is_folded") or p.get("state") == "busted":
            continue
        # all-in players are still opponents (they'll be in the showdown)
        cnt += 1
    return cnt


# ─────────────────────────────────────────────────────────────────────────────
# Sizing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_raise(target_total, state):
    """Build a {action:raise|all_in} dict with safe bounds."""
    my_bet = state["your_bet_this_street"]
    stack = state["your_stack"]
    min_raise_to = state["min_raise_to"]
    max_total = stack + my_bet
    target_total = max(min_raise_to, int(target_total))
    if target_total >= max_total:
        return {"action": "all_in"}
    return {"action": "raise", "amount": target_total}


def _safe_call_or_check(state):
    if state["can_check"]:
        return {"action": "check"}
    return {"action": "call"}


# ─────────────────────────────────────────────────────────────────────────────
# Main decision
# ─────────────────────────────────────────────────────────────────────────────

def decide(game_state: dict) -> dict:
    if game_state.get("type") == "warmup":
        return {"ok": True}
    try:
        result = _decide(game_state)
    except Exception:
        return {"action": "fold"}
    # #9 — record our spot for the per-spot P&L tracker.  Best-effort: a
    # bug in the tracker must never affect the action we return.
    try:
        action_kind = (result.get("action", "fold") or "fold").lower()
        _record_my_spot(game_state, action_kind)
    except Exception:
        pass
    return result


def _decide(state):
    _update_opp_model(state)

    street = state["street"]
    pot = state["pot"]
    owed = state["amount_owed"]
    stack = state["your_stack"]
    can_check = state["can_check"]
    bet_this = state["your_bet_this_street"]
    min_raise_to = state["min_raise_to"]

    n_opp = _n_active_opponents(state)
    if n_opp == 0:
        return _safe_call_or_check(state)

    pos = _position_score(state)
    is_late = pos >= 0.6
    is_early = pos <= 0.34

    # Heads-up flag: only two players left at the table.  Triggers a much
    # wider strategy because every hand has positive expected value.
    n_active_total = sum(1 for p in state["players"]
                         if not p.get("is_folded")
                         and p.get("state") != "busted"
                         and p.get("stack", 0) > 0)
    is_hu = n_active_total <= 2

    # Profile the opponents currently in the hand (folded/busted excluded).
    your_seat = state["seat_to_act"]
    in_hand = [p for p in state["players"]
               if p["seat"] != your_seat
               and not p.get("is_folded")
               and p.get("state") != "busted"]
    if in_hand:
        avg_fold = sum(_opp_profile(p["bot_id"])[1] for p in in_hand) / len(in_hand)
        avg_raise = sum(_opp_profile(p["bot_id"])[0] for p in in_hand) / len(in_hand)
        max_sample = max((_opp_profile(p["bot_id"])[3] for p in in_hand), default=0)
    else:
        avg_fold = 0.4
        avg_raise = 0.25
        max_sample = 0
    field_is_foldy = (max_sample >= 8 and avg_fold >= 0.55)
    field_is_aggro = (max_sample >= 8 and avg_raise >= 0.45)

    # Aggregate archetype counter hints across in-hand opponents (#6).
    counters = _aggregated_counters([p["bot_id"] for p in in_hand])

    # Rolling-model early maniac override: if any in-hand opponent has a high
    # raise rate from the match-log (≥5 samples, ≥72% raises) but the deep
    # profiler hasn't classified them yet, blend maniac counters in immediately.
    if in_hand and not any(_opp_archetype(p["bot_id"]) == "maniac" for p in in_hand):
        mc = _archetype_counters("maniac")
        for p in in_hand:
            rf, _, _, sn = _opp_profile(p["bot_id"])
            if sn >= 5 and rf >= 0.72:
                for k, v in mc.items():
                    if isinstance(v, bool):
                        counters[k] = counters[k] or v
                    else:
                        counters[k] = (counters[k] + v) * 0.5
                break

    # Pot odds (break-even equity).
    pot_odds = owed / (pot + owed) if owed > 0 else 0.0
    spr = stack / max(pot, 1)

    # ---------------- Preflop ------------------------------------------------
    if street == "preflop":
        return _preflop_decision(
            state, n_opp, pos, is_late, is_early, is_hu,
            avg_fold, avg_raise, field_is_foldy, field_is_aggro,
            pot_odds, spr, counters,
        )

    # ---------------- Postflop -----------------------------------------------
    return _postflop_decision(
        state, n_opp, pos, is_late, is_early, is_hu,
        avg_fold, avg_raise, field_is_foldy, field_is_aggro,
        pot_odds, spr, counters,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Preflop decision
# ─────────────────────────────────────────────────────────────────────────────

def _preflop_decision(state, n_opp, pos, is_late, is_early, is_hu,
                      avg_fold, avg_raise, foldy, aggro,
                      pot_odds, spr, counters=None):
    if counters is None:
        counters = _archetype_counters("unknown")
    cards = state["your_cards"]
    hand = _canonical_hand(cards[0], cards[1])
    eq_hu = _hu_equity(hand)
    eq_multi = _multiway_equity(hand, n_opp)

    pot = state["pot"]
    owed = state["amount_owed"]
    stack = state["your_stack"]
    bet_this = state["your_bet_this_street"]
    min_raise_to = state["min_raise_to"]
    can_check = state["can_check"]

    # Did anyone raise (i.e., is there real action besides blinds)?
    raised_count = sum(1 for a in state["action_log"]
                       if a.get("action") in ("raise", "all_in"))
    facing_raise = raised_count > 0
    # 3-bet+ pots: tighten further
    facing_three_bet = raised_count >= 2

    # Squeeze spot: exactly one raise + ≥1 callers behind it.
    # Callers' ranges are capped (no strong hand), so fold equity is huge.
    n_callers_pre = sum(1 for a in state["action_log"] if a.get("action") == "call")
    is_squeeze_spot = (raised_count == 1 and n_callers_pre >= 1)

    # Stack-based push/fold for very short stacks (overrides GTO blueprint —
    # GTO charts are calibrated for ~100bb stacks, irrelevant when shoving)
    if stack <= 17 * BIG_BLIND and owed > 0:
        push_eq = 0.45 if is_hu else 0.55
        if eq_hu >= push_eq or hand in ("AA", "KK", "QQ", "JJ", "TT", "AKs", "AKo", "AQs"):
            return {"action": "all_in"}
        if eq_hu >= push_eq - 0.05 and is_late:
            return {"action": "all_in"}
        if pot_odds > 0 and eq_multi > pot_odds + 0.06:
            return {"action": "call"}
        return {"action": "fold"}

    # ---------------- GTO blueprint (#7) -----------------------------------
    # Try the published 6-max GTO chart first.  Falls through to the existing
    # logic when the situation is unusual (multi-way limps, deep 4-bet pots,
    # missing position info).  HU is handled by its own branch below since
    # GTO 6-max charts don't apply.
    if _USE_GTO_BLUEPRINT and not is_hu and stack >= 30 * BIG_BLIND:
        rec = _gto_recommendation(state)
        if rec is not None:
            n_callers = sum(1 for a in state["action_log"]
                            if a.get("action") == "call")
            open_size = (3 * BIG_BLIND) + (BIG_BLIND * max(0, n_callers))
            open_size = max(open_size, min_raise_to)
            current_bet = state["current_bet"]
            kind = rec[0]
            if kind == "open":
                return _make_raise(open_size, state)
            if kind == "3bet":
                threebet_to = max(min_raise_to, int(current_bet * 3.0))
                return _make_raise(threebet_to, state)
            if kind == "4bet":
                fourbet_to = max(min_raise_to, int(current_bet * 2.5))
                return _make_raise(fourbet_to, state)
            if kind == "call":
                return {"action": "call"}
            if kind == "check":
                return {"action": "check"} if can_check else {"action": "fold"}
            if kind == "fold":
                # BB checking option overrides "fold" if available
                if can_check:
                    return {"action": "check"}
                return {"action": "fold"}

    # ---------------- Heads-up specialization ------------------------------
    # In HU, ranges should be MUCH wider — open ~70% on the button (SB),
    # defend ~70% in BB.  Without this override the multi-way thresholds
    # leave too much money on the table.
    if is_hu:
        # Open size — smaller HU is fine, opp will defend wide either way.
        n_callers = sum(1 for a in state["action_log"] if a.get("action") == "call")
        open_size = max(min_raise_to, int(2.5 * BIG_BLIND))

        if facing_raise:
            current_bet = state["current_bet"]
            threebet_to = max(min_raise_to, int(current_bet * 3.0))

            # Facing a 3-bet+ in HU: still tight (AA/KK 4-bet, QQ/JJ/AKs/AKo
            # call, AQs/AKo set-mine).  Don't get cute.
            if facing_three_bet:
                if hand in ("AA", "KK"):
                    return _make_raise(threebet_to, state)
                if hand in ("QQ", "JJ", "AKs", "AKo") and owed < 0.25 * stack:
                    return {"action": "call"}
                if aggro and hand in ("TT", "AQs", "AQo") and owed < 0.18 * stack:
                    return {"action": "call"}
                if hand in ("99", "88", "77", "66", "55", "44", "33", "22") \
                        and owed < 0.06 * stack:
                    return {"action": "call"}
                return {"action": "fold"}

            # Facing a single open in HU — defend wide.
            # 3-bet for value with strong hands.
            if hand in ("AA", "KK", "QQ", "AKs"):
                return _make_raise(threebet_to, state)
            if hand in ("JJ", "TT", "AKo", "AQs"):
                if aggro:
                    return _make_raise(threebet_to, state)
                return {"action": "call"}
            # Defend ~65-75% by HU equity.  0.42 ≈ top 70%.
            if eq_hu >= 0.42 and owed < 0.20 * stack:
                return {"action": "call"}
            return {"action": "fold"}

        # No raise yet — HU open / check option.
        # SB (acts first preflop): raise/fold ~70% of hands.
        # BB (acts last with check option): can raise vs limp or check.
        if can_check:
            # BB facing limp — raise wider than usual to punish limp.
            if eq_hu >= 0.50:
                return _make_raise(open_size, state)
            return {"action": "check"}
        # SB unopened: open top ~70%, fold the rest.
        if eq_hu >= 0.42:
            return _make_raise(open_size, state)
        return {"action": "fold"}

    # ---------------- Multi-way preflop (3+ players) ----------------------

    # Open-raise sizing: ~3 BB unopened, larger if many limpers
    n_callers = sum(1 for a in state["action_log"] if a.get("action") == "call")
    open_size = (3 * BIG_BLIND) + (BIG_BLIND * max(0, n_callers))
    open_size = max(open_size, min_raise_to)

    # === Facing a raise (re-raise, call, or fold) ===
    if facing_raise:
        current_bet = state["current_bet"]
        threebet_to = max(min_raise_to, int(current_bet * 3.0))

        # Squeeze: raise + ≥1 callers → enormous fold equity. Size to 4×+.
        # Caller's range is capped (strong hands 3-bet), raiser opens wide.
        if is_squeeze_spot and not facing_three_bet:
            squeeze_size = max(min_raise_to,
                               int(current_bet * (3.5 + 0.5 * n_callers_pre)))
            # Squeeze only with hands that can comfortably call a 4-bet.
            # JJ/TT/AQs create bloat-and-fold risk vs a strong 4-bet.
            if hand in ("AA", "KK", "QQ", "AKs", "AKo"):
                return _make_raise(squeeze_size, state)

        # Adjust thresholds based on opponent profile.  Aggressive openers have
        # wider ranges → we should call lighter and seldom 4-bet bluff.
        if aggro:
            call_eq = 0.50
        elif foldy:
            call_eq = 0.58
        else:
            call_eq = 0.55

        # Facing a 3-bet (or larger) — premiums and strong calls only.
        if facing_three_bet:
            wide_defense = counters.get("three_bet_defense_wide", False)
            # 4-bet/jam premiums — wider vs maniacs since their 3-bet range is huge.
            # QQ/AKs: call rather than jam to keep pot manageable (~60% eq vs random).
            if wide_defense:
                if hand in ("AA", "KK"):
                    return _make_raise(threebet_to, state)
                if hand in ("QQ", "AKs"):
                    if owed < 0.35 * stack:
                        return {"action": "call"}
                    return _make_raise(threebet_to, state)  # forced all-in size
            else:
                if hand in ("AA", "KK"):
                    return _make_raise(threebet_to, state)
            # Strong calls — flat with QQ/JJ/AKs/AKo vs normal; wider vs maniacs
            if wide_defense:
                if hand in ("JJ", "TT", "AKo", "AQs", "AQo", "AJs", "KQs"):
                    if owed < 0.28 * stack:
                        return {"action": "call"}
                # Medium pairs and suited broadways — very profitable vs maniac 3-bets
                if hand in ("99", "88", "77", "ATs", "KJs", "QJs"):
                    if owed < 0.15 * stack:
                        return {"action": "call"}
            else:
                if hand in ("QQ", "JJ", "AKs", "AKo"):
                    if owed < 0.22 * stack:
                        return {"action": "call"}
                # Vs aggressive 3-bettor, expand range slightly
                if aggro and hand in ("TT", "AQs", "AQo"):
                    if owed < 0.15 * stack:
                        return {"action": "call"}
            # Cheap pocket-pair set-mine in deep 3-bet pots
            if hand in ("TT", "99", "88", "77", "66", "55", "44", "33", "22"):
                threshold = 0.10 if wide_defense else 0.05
                if owed < threshold * stack:
                    return {"action": "call"}

            # Cold 4-bet bluff: raise + call(s) + 3-bet means caller's range
            # is capped (they'd have 3-bet strong hands), so 3-bettor's range
            # is actually narrower.  Mix in 4-bet bluffs with blockers.
            cold_4bet = n_callers_pre >= 1 and not wide_defense
            if cold_4bet and hand in ("AQs", "KQs") and owed < 0.30 * stack:
                if random.random() < 0.30:
                    return _make_raise(threebet_to, state)

            return {"action": "fold"}

        # First 3-bet decision.
        # Premium hands: 3-bet for value.
        if hand in ("AA", "KK", "QQ", "AKs"):
            return _make_raise(threebet_to, state)

        # Strong hands: 3-bet against aggressive openers, call to trap others.
        strong = hand in ("JJ", "TT", "AKo", "AQs", "AQo", "AJs", "KQs")
        if strong:
            if aggro and not is_early:
                return _make_raise(threebet_to, state)
            return {"action": "call"}

        # Wide value-call vs aggressive openers (their range is wide).
        # Require either decent equity AND playability (suited / connected),
        # or a genuinely strong hand.  Offsuit junk realises equity poorly.
        suited = cards[0][1] == cards[1][1]
        connected = abs(_RANK_IDX[cards[0][0]] - _RANK_IDX[cards[1][0]]) <= 2
        playable = suited or connected
        if eq_hu >= 0.58 and owed < 0.18 * stack:
            return {"action": "call"}
        if eq_hu >= call_eq and playable and owed < 0.15 * stack:
            return {"action": "call"}

        # Pocket pairs 22-99 set-mine: call if cheap relative to stack
        if hand in ("99", "88", "77", "66", "55", "44", "33", "22"):
            implied_ratio = owed / max(stack, 1)
            if implied_ratio < 0.07:
                return {"action": "call"}
            return {"action": "fold"}

        # Speculative suited hands in late position (cheap)
        speculative = hand in ("ATs", "KJs", "KTs", "QJs", "QTs", "JTs",
                               "T9s", "98s", "87s", "76s", "65s",
                               "A9s", "A8s", "A7s", "A6s", "A5s", "A4s", "A3s", "A2s")
        if speculative and is_late and owed < 0.05 * stack:
            return {"action": "call"}

        # BB defending vs steal: call wider when price is good
        is_bb = bet_this >= BIG_BLIND
        if is_bb and pot_odds <= 0.34:
            if eq_multi >= pot_odds + 0.04 or eq_hu >= 0.48:
                return {"action": "call"}

        return {"action": "fold"}

    # === No raise yet — open or fold (or check BB) ===
    # Position-dependent open thresholds based on heads-up equity
    if is_late:
        threshold_open = 0.51       # ~top 35% of hands
    elif is_early:
        threshold_open = 0.600      # ~top 8%; A7o/Q9o leak chips from EP
    else:
        threshold_open = 0.555      # ~top 22% of hands

    # Small steal incentive when only foldy opponents remain
    if foldy:
        threshold_open -= 0.04
    # Archetype counters: opening wider vs nits, tighter vs maniacs/stations.
    threshold_open += counters.get("open_threshold_delta", 0.0)

    if eq_hu >= threshold_open:
        return _make_raise(open_size, state)

    # BB with check option — take it
    if can_check:
        return {"action": "check"}

    # SB completing: only with playable hands (rarely correct in a vacuum;
    # but vs foldy fields raising is better — handled above).
    if owed <= SMALL_BLIND and eq_hu >= 0.42:
        return {"action": "call"}

    return {"action": "fold"}


# ─────────────────────────────────────────────────────────────────────────────
# Postflop decision
# ─────────────────────────────────────────────────────────────────────────────

def _postflop_decision(state, n_opp, pos, is_late, is_early, is_hu,
                       avg_fold, avg_raise, foldy, aggro,
                       pot_odds, spr, counters=None):
    if counters is None:
        counters = _archetype_counters("unknown")
    pot = state["pot"]
    owed = state["amount_owed"]
    stack = state["your_stack"]
    bet_this = state["your_bet_this_street"]
    min_raise_to = state["min_raise_to"]
    can_check = state["can_check"]
    street = state["street"]
    cards = state["your_cards"]
    board = state["community_cards"]

    # Time budget for MC: more sims when the decision is for a big chunk of
    # our stack (variance hurts most when committing big).
    base = 0.40 if street == "flop" else (0.35 if street == "turn" else 0.30)
    if owed >= 0.20 * stack:
        budget = base + 0.40
    elif owed >= 0.08 * stack:
        budget = base + 0.20
    else:
        budget = base

    # Range conditioning: MC against each opponent's likely hands rather than
    # uniform-random.  Each opponent's range is inferred from their action
    # this hand + their match-long aggression profile.
    your_seat = state["seat_to_act"]
    in_hand_seats = [(p["seat"], p["bot_id"]) for p in state["players"]
                     if p["seat"] != your_seat
                     and not p.get("is_folded")
                     and p.get("state") != "busted"]
    # Use v2 (signature-based) range inference — strictly sharper than v1.
    # v2 internally falls back to v1 when no signature data is available.
    opp_ranges = [_infer_opp_range_v2(state, seat, bid)
                  for (seat, bid) in in_hand_seats]
    equity, _sims = _monte_carlo_equity(
        cards, board, n_opp, time_budget=budget, opp_ranges=opp_ranges,
    )

    any_maniac_in_hand = any(_opp_archetype(bid) == "maniac"
                             for (_, bid) in in_hand_seats)

    # Reward-feedback caution: tighten thresholds against opponents we're
    # losing chips to (cumulatively), loosen against ones we're winning from.
    caution = _opp_caution_factor([bid for (_, bid) in in_hand_seats])
    tp = _tournament_pressure(state)
    # Blend tournament pressure into caution: big stacks loosen, short stacks tighten
    caution = max(0.7, min(1.3, caution * (2.0 - tp)))

    # Stack preservation mode: tighten all-in commit thresholds as stack
    # shrinks to avoid tournament elimination on marginal spots.
    # Smooth ICM curve: tightening begins at 80% stack, maxes out at 40%.
    stack_ratio = stack / STARTING_STACK
    preservation_mode = stack_ratio < 0.60  # kept for spr/sizing gates below
    if stack_ratio >= 0.80:
        preserve_equity_bonus = 0.0
    elif stack_ratio >= 0.40:
        # Linear ramp: 0.0 at 80% → 0.10 at 40%
        preserve_equity_bonus = 0.10 * (0.80 - stack_ratio) / 0.40
    else:
        preserve_equity_bonus = 0.10

    # Hand classification — categorical strength + draw type.
    hc = _classify_postflop(cards, board)
    tier = hc["tier"]
    is_strong = hc["is_strong"]                     # two pair or better
    is_top_pair_plus = hc["is_top_pair_plus"]       # tptk / overpair / better
    is_made_pair_plus = hc["is_made_pair_plus"]     # mid pair or better
    has_strong_draw = hc["has_strong_draw"]         # OESD / FD / combo

    # Aggressor identification: was last raiser the bot itself?
    last_aggressor_seat = None
    for a in state["action_log"]:
        if a.get("action") in ("raise", "all_in"):
            last_aggressor_seat = a["seat"]
    am_aggressor = (last_aggressor_seat == state["seat_to_act"])

    wetness = _board_wetness(board)
    btex = _board_texture(board)

    # NOTE: a separate `_river_decision` branch (MDF + combo counting + polar
    # value sizing) was tested here but rolled back — it improved the small
    # reference-field A/B by +1-2K but blew up the floor on the 66-bot stress
    # field (rank 1.9 → 9.9 mean, min cum_delta dropped to -29K).  The
    # adaptive sizing helpers still apply through the generic logic below.
    # Keeping the helper around for future reference; not invoked here.

    vsm = min(1.30, counters.get("value_size_mult", 1.0))  # cap at 130% pot

    # ---------------- Can check? --------------------------------------------
    if can_check:
        # Strong hands (2 pair+) — bet for value almost always.
        if is_strong:
            if street == "river":
                size_mult = 0.90 * vsm   # realize full value on river
            elif wetness:
                size_mult = 0.75 * vsm
            else:
                size_mult = 0.65 * vsm
            size_mult = min(1.25, size_mult)
            return _make_raise(int(state["current_bet"] + pot * size_mult), state)

        # Top pair / overpair — value bet, but check-call vs aggressors to
        # avoid getting blown off our hand.
        if is_top_pair_plus:
            if aggro and n_opp == 1 and tier in ("tptk", "overpair"):
                return {"action": "check"}
            if street == "river":
                size_mult = 0.75 * vsm
            else:
                size_mult = (0.62 if not wetness else 0.70) * vsm
            size_mult = min(1.20, size_mult)
            return _make_raise(int(state["current_bet"] + pot * size_mult), state)

        # Strong draw — semi-bluff probabilistically.
        if has_strong_draw and street != "river":
            sb_prob = 0.55
            if aggro:   sb_prob += 0.10   # re-raise folds aggro air; semi-bluff is good here
            if is_late: sb_prob += 0.15
            if foldy:   sb_prob += 0.15
            if n_opp >= 3: sb_prob -= 0.30
            if random.random() < sb_prob:
                return _make_raise(int(state["current_bet"] + pot * 0.55), state)

        # Mid pair / weak made hand — pot control.
        if is_made_pair_plus:
            return {"action": "check"}

        # Probe bet (delayed cbet): we raised preflop, checked the flop, now on
        # the turn.  Fire to represent continued strength and deny free cards.
        if (street == "turn" and n_opp == 1
                and _my_raises_this_hand(state) >= 1
                and not _my_prev_street_aggression(state)   # checked flop
                and equity >= 0.50 and not btex["paired"]):
            probe_mult = 0.50 if equity < 0.56 else 0.62
            return _make_raise(int(state["current_bet"] + pot * probe_mult), state)

        # Thin value bet when MC says we're clearly ahead but hand has no tier match.
        # Size proportional to edge — small with marginal, up to 60% pot with solid lead.
        # Skip river (bet on river only when classified strong); skip multi-way (variance).
        if equity >= 0.60 and street != "river" and n_opp == 1:
            edge = equity - 0.50
            size_mult = min(0.60, 0.38 + edge * 1.1)
            return _make_raise(int(state["current_bet"] + pot * size_mult), state)

        # High-equity (per MC) but uncategorised — check to extract on later streets.
        if equity >= 0.55:
            return {"action": "check"}

        # Pure bluff: HU vs wet boards, not river.  Suppressed on paired boards
        # (opp may have flopped trips/FH) and monotone boards (flush likely out).
        if (is_late and wetness
                and not btex["paired"] and not btex["monotone"]
                and street != "river" and n_opp == 1
                and not aggro):
            target_bet = int(pot * 0.55)
            bet_tier = _bet_size_tier(target_bet, pot)
            in_hand_ids = [p["bot_id"] for p in state["players"]
                           if p["seat"] != state["seat_to_act"]
                           and not p.get("is_folded")
                           and p.get("state") != "busted"]
            f_rate = _avg_opp_fold_to_size(in_hand_ids, bet_tier)
            if f_rate is not None:
                target_bet_ev = int(pot * 0.55)
                bluff_ev = f_rate * pot - (1 - f_rate) * target_bet_ev
                if bluff_ev > 0 and f_rate >= 0.50:
                    bluff_prob = min(0.90, f_rate)
                else:
                    bluff_prob = 0.0
            elif foldy:
                # No exact fold-to-size data — fall back to old heuristic.
                bluff_prob = 0.70 + (0.05 if avg_fold > 0.65 else 0.0)
            else:
                bluff_prob = 0.0
            if random.random() < bluff_prob:
                return _make_raise(int(state["current_bet"] + target_bet), state)
        return {"action": "check"}

    # ---------------- Facing a bet ------------------------------------------
    margin_strong = 0.14
    margin_thin = 0.04

    facing_reraise = bet_this > 0 and owed > 0
    big_commit = owed > 0.25 * stack

    # Bet-sizing classification — opponent's bet relative to current pot.
    bet_to_pot = owed / max(pot, 1)
    huge_bet = bet_to_pot >= 1.20      # >120% pot — polarised strong/bluff
    overbet = bet_to_pot >= 0.85
    small_bet = 0 < bet_to_pot <= 0.35  # weakness signal

    # Cross-hand context: is this opponent's raise unusually big or small
    # compared to their match-long average raise size?
    last_raiser_seat = None
    last_raise_amt = 0
    for a in state["action_log"]:
        if a.get("action") in ("raise", "all_in"):
            last_raiser_seat = a["seat"]
            last_raise_amt = a.get("amount") or 0
    last_raiser_bid = next((p["bot_id"] for p in state["players"]
                            if p["seat"] == last_raiser_seat), None) if last_raiser_seat is not None else None
    raise_unusually_big = False
    raise_unusually_small = False
    if last_raiser_bid:
        avg_raise_chips = _opp_avg_raise(last_raiser_bid)
        if avg_raise_chips and last_raise_amt:
            ratio = last_raise_amt / avg_raise_chips
            raise_unusually_big = ratio >= 1.6
            raise_unusually_small = ratio <= 0.6

    # Implied / reverse-implied pot odds.  Replace pot_odds with the adjusted
    # value for call decisions on draws and weak made hands.
    pot_odds_eff = _implied_pot_odds(pot, owed, tier, hc["draw"], stack, n_opp)

    # Commit thresholds — strong hands jam, weak ones never.
    # In preservation mode, require higher equity to avoid busting on marginal spots.
    # Vs maniacs: tighten SPR gate (1.5 not 3.0) and equity jam gate (0.80 not 0.72)
    # to avoid busting on marginal ~60% equity all-ins against volatile wide ranges.
    commit_strong_spr = (1.5 if any_maniac_in_hand
                         else (3.0 if not preservation_mode else 1.5))
    commit_eq_hi     = 0.80 + preserve_equity_bonus
    commit_eq_lo     = 0.72 + preserve_equity_bonus

    if is_strong and spr <= commit_strong_spr:
        return {"action": "all_in"}
    if is_strong and spr <= 5.0 and n_opp <= 2 and not preservation_mode:
        size_mult = 0.85
        target = state["current_bet"] + int(pot * size_mult)
        return _make_raise(target, state)
    if equity >= commit_eq_hi and spr <= 2.5:
        return {"action": "all_in"}
    equity_jam_lo = commit_eq_hi if any_maniac_in_hand else commit_eq_lo
    if equity >= equity_jam_lo and spr <= 1.5 and n_opp <= 2 and not facing_reraise:
        return {"action": "all_in"}

    # Facing a re-raise on the same street — opponent's range narrows hard.
    if facing_reraise:
        if is_strong:
            if equity >= 0.70 + preserve_equity_bonus and street != "river":
                size_mult = 0.85
                return _make_raise(state["current_bet"] + int(pot * size_mult), state)
            return {"action": "call"}
        # Unusually large re-raise = polarised; call top-pair-plus only if
        # it's cheap, fold marginal value.
        if raise_unusually_big or huge_bet:
            if is_top_pair_plus and owed < 0.20 * stack and equity >= pot_odds_eff + 0.05:
                return {"action": "call"}
            if has_strong_draw and owed < 0.12 * stack and street != "river":
                return {"action": "call"}
            return {"action": "fold"}
        # Top pair / overpair facing re-raise: call cautiously.
        if is_top_pair_plus and equity >= pot_odds_eff + 0.05 and owed < 0.30 * stack:
            return {"action": "call"}
        # Strong draw with implied odds: chase if cheap.
        if has_strong_draw and owed < 0.18 * stack and street != "river":
            return {"action": "call"}
        # Otherwise standard tightening — only continue with real equity.
        if equity < pot_odds + 0.10:
            return {"action": "fold"}
        if owed >= 0.30 * stack and equity < 0.65:
            return {"action": "fold"}
        return {"action": "call"}

    # Huge bet awareness.
    # If the raiser is a known overbet-archetype (bets huge with wide range),
    # treat as a normal wide-range bet — call with standard equity edge.
    # Otherwise treat as polarized and require stronger hands.
    if huge_bet:
        last_raiser_bid_arch = _opp_archetype(last_raiser_bid) if last_raiser_bid else "unknown"
        opp_is_overbet_type = (last_raiser_bid_arch == "overbet")
        if opp_is_overbet_type:
            # Range is wide, not polarized — call with any positive equity edge
            # over pot odds (same as standard call zone but applied here early).
            edge_vs_overbet = equity - pot_odds_eff
            if edge_vs_overbet >= margin_thin - 0.02:
                pass  # fall through to standard value/call logic below
            else:
                return {"action": "fold"}
        else:
            # Genuinely polarized overbet — strong hands call/raise, rest fold.
            if is_strong:
                pass  # fall through to value logic
            elif is_top_pair_plus and owed < 0.30 * stack and equity >= pot_odds_eff + 0.05:
                return {"action": "call"}
            elif has_strong_draw and owed < 0.18 * stack and street != "river":
                return {"action": "call"}
            else:
                return {"action": "fold"}

    # Big-commit / overbet awareness for the standard case.
    if big_commit or overbet:
        if not (is_strong or is_top_pair_plus or has_strong_draw):
            # Known aggro/maniac/overbet archetypes genuinely bet wide — need more edge to call.
            # Unclassified opponents (e.g., equity-aware bots) size proportionally, not polarized;
            # treat their overbets with the same thin margin as normal bets.
            last_raiser_arch = _opp_archetype(last_raiser_bid) if last_raiser_bid else "unknown"
            fold_margin = 0.08 if last_raiser_arch in ("maniac", "lag", "overbet") else 0.04
            required = pot_odds_eff + fold_margin
            if equity < required:
                return {"action": "fold"}

    # Bluff-raise vs small bet from a foldy player (float spot).
    # Use measured fold-to-size rate for our intended raise size when we have
    # data; fall back to the generic `foldy` flag.
    if (small_bet and is_late and n_opp == 1 and not aggro
            and not is_made_pair_plus and not has_strong_draw
            and owed < 0.10 * stack
            and street != "river"):
        raise_target = int(pot * 0.85)
        raise_tier = _bet_size_tier(raise_target, pot + owed)
        in_hand_ids = [p["bot_id"] for p in state["players"]
                       if p["seat"] != state["seat_to_act"]
                       and not p.get("is_folded")
                       and p.get("state") != "busted"]
        f_rate = _avg_opp_fold_to_size(in_hand_ids, raise_tier)
        if f_rate is not None:
            bluff_ev = f_rate * pot - (1 - f_rate) * raise_target
            if bluff_ev > 0 and f_rate >= 0.50:
                bluff_p = min(0.85, f_rate) * counters.get("bluff_freq_mult", 1.0)
            else:
                bluff_p = 0.0
        elif foldy:
            bluff_p = 0.45 * counters.get("bluff_freq_mult", 1.0)
        else:
            bluff_p = 0.0
        if random.random() < bluff_p:
            target = state["current_bet"] + raise_target
            return _make_raise(target, state)

    # Semi-bluff check-raise with strong draws vs high-cbet opponents.
    # A high-cbet bot fires air on the flop frequently; raising them with a draw
    # takes the pot immediately or builds equity when called.
    if (has_strong_draw and not facing_reraise and not huge_bet
            and n_opp == 1 and street != "river"
            and owed < 0.25 * stack and not btex["monotone"]):
        in_hand_ids_cr = [p["bot_id"] for p in state["players"]
                          if p["seat"] != state["seat_to_act"]
                          and not p.get("is_folded")
                          and p.get("state") != "busted"]
        avg_cbet_cr = None
        if in_hand_ids_cr:
            cbets_cr = [_opp_cbet_freq(bid) for bid in in_hand_ids_cr]
            cbets_cr = [c for c in cbets_cr if c is not None]
            if cbets_cr:
                avg_cbet_cr = sum(cbets_cr) / len(cbets_cr)
        if avg_cbet_cr is not None and avg_cbet_cr >= 0.65:
            cr_size = max(min_raise_to, int((pot + owed) * 2.2))
            if cr_size <= stack:
                return _make_raise(cr_size, state)

    # Apply archetype counters to call/raise thresholds (#6).
    # caution > 1 → losing to these opps → tighten (subtract less / add more)
    # caution < 1 → winning from these opps → loosen
    value_delta = counters.get("value_eq_delta", 0.0)
    call_delta = counters.get("call_eq_delta", 0.0)
    caution_shift = (caution - 1.0) * 0.09   # max ±0.027 effect

    if equity >= pot_odds + margin_strong + call_delta + caution_shift:
        min_raise_eq = 0.58 + value_delta + caution_shift
        if n_opp >= 2:
            min_raise_eq = max(min_raise_eq, 0.65 + value_delta + caution_shift)
        if aggro:
            min_raise_eq = max(min_raise_eq, 0.68 + value_delta + caution_shift)
        if foldy:
            min_raise_eq = max(min_raise_eq, 0.78 + value_delta)
        if street == "river":
            min_raise_eq = max(min_raise_eq, 0.80 + value_delta)
        if is_strong:
            min_raise_eq = min(min_raise_eq, 0.55)
        if equity < min_raise_eq:
            return {"action": "call"}
        size_mult = 0.70 if street != "river" else 0.85
        target = state["current_bet"] + int(pot * size_mult)
        target = int(target * random.uniform(0.95, 1.05))
        return _make_raise(target, state)

    # Standard call zone — equity edge over pot odds.  Use implied/reverse
    # pot odds: drawing hands call wider, weak made hands call tighter.
    # Archetype call_delta tightens against maniacs (call wider) or loosens
    # against rocks.
    edge = equity - pot_odds_eff
    effective_thin = margin_thin + call_delta
    if edge >= effective_thin:
        if n_opp >= 3 and edge < 0.10 and owed >= 0.15 * stack:
            return {"action": "fold"}
        return {"action": "call"}

    # Mixed-strategy soft border just below the call threshold.  Reduces
    # MC-noise flip-flops and is harder for opponents to read.  Probability
    # of calling rises smoothly through the [pot_odds, pot_odds+margin_thin]
    # band when the call is cheap.
    if owed < 0.08 * stack and edge >= 0.0:
        if random.random() < _smooth_p(edge, margin_thin / 2, sharpness=40.0):
            return {"action": "call"}

    # Strong draw with implied odds: chase if cheap.
    if has_strong_draw and owed < 0.15 * stack and street != "river" and n_opp <= 2:
        return {"action": "call"}

    # Backup big-draw path for non-classified equity hands.
    if equity >= pot_odds and owed < 0.10 * stack and street != "river" and n_opp <= 2:
        return {"action": "call"}

    return {"action": "fold"}


def _board_wetness(board_strs):
    if len(board_strs) < 3:
        return 0
    suits = [c[1] for c in board_strs]
    ranks_idx = sorted({_RANK_IDX[c[0]] for c in board_strs})
    flush_draw = max(suits.count(s) for s in set(suits)) >= 2
    # Rank spread <= 4 implies straight-y
    spread = ranks_idx[-1] - ranks_idx[0]
    straight_y = spread <= 4 and len(ranks_idx) >= 3
    return int(flush_draw) + int(straight_y)


def _board_texture(board_strs):
    """Extended board classification used to gate bluffing and size value bets.

    Returns a dict:
      paired   — board has a pair (reduces bluff credibility; opp may have trips)
      monotone — all visible cards same suit (flush almost always out there)
      wet      — _board_wetness score (0/1/2)
      dry      — no draws, no pair, not monotone
    """
    if len(board_strs) < 3:
        return {"paired": False, "monotone": False, "wet": 0, "dry": True}
    ranks = [c[0] for c in board_strs]
    suits = [c[1] for c in board_strs]
    paired = len(ranks) != len(set(ranks))
    max_suit_n = max(suits.count(s) for s in set(suits))
    monotone = (max_suit_n == len(board_strs))
    wet = _board_wetness(board_strs)
    dry = (wet == 0 and not paired and not monotone)
    return {"paired": paired, "monotone": monotone, "wet": wet, "dry": dry}


# ─────────────────────────────────────────────────────────────────────────────
# #8 — Multi-street line awareness
#
# Tracks our own aggression history this hand, lets later-street decisions
# bias toward continuing the line we started.  Specifically: if we cbet flop,
# our turn-bet threshold should be slightly lower (we're committed to telling
# a coherent story rather than firing once and giving up — a known leak).
# ─────────────────────────────────────────────────────────────────────────────

def _my_prev_street_aggression(state) -> bool:
    """Return True if I raised/bet on the most-recent completed street.

    NOTE: action_log is never reset between hands — it grows to 15k+ entries
    over a 300-hand match.  We cap the scan at the last 120 entries which is
    always enough to cover one full hand (max ~96 actions for 6 players × 4
    streets × 4 actions each) without O(n) overhead.
    """
    your_seat = state["seat_to_act"]
    cur_street = state["street"]
    if cur_street == "preflop":
        return False
    actions = state.get("action_log", [])[-120:]
    if not actions:
        return False
    target_street = {"flop": "preflop", "turn": "flop", "river": "turn"}[cur_street]
    for entry, st, _pos, _pot, _tier in _replay_hand(actions):
        if st == target_street and entry.get("seat") == your_seat \
                and entry.get("action") in ("raise", "all_in"):
            return True
    return False


def _my_raises_this_hand(state) -> int:
    """Total raises/all-ins by us this hand. Capped to last 120 entries."""
    your_seat = state["seat_to_act"]
    return sum(1 for a in state.get("action_log", [])[-120:]
               if a.get("seat") == your_seat
               and a.get("action") in ("raise", "all_in"))


# ─────────────────────────────────────────────────────────────────────────────
# Hand classifier — categorical strength label.  Pure equity misses key
# distinctions: top-pair-weak-kicker has the same MC equity as middle set
# on a dry board, but should play very differently.  These tags drive the
# postflop tier overrides (commit vs pot-control vs give-up).
# ─────────────────────────────────────────────────────────────────────────────

# Tier ordinals — higher = stronger.
_TIER_RANK = {
    "high_card": 0, "underpair": 1, "low_pair": 2, "weak_pair": 2,
    "mid_pair": 3, "tp_weak": 4, "tptk": 5, "overpair": 5,
    "two_pair": 6, "trips": 7, "set": 8, "straight": 9, "flush": 10,
    "fullhouse": 11, "quads": 12, "straight_flush": 13,
}


def _classify_postflop(hole_strs, board_strs):
    """Return a small dict describing made-hand strength + draws."""
    if not board_strs:
        return {"tier": "preflop", "draw": "none",
                "is_strong": False, "is_top_pair_plus": False,
                "is_made_pair_plus": False, "has_strong_draw": False}

    hole = [_CARD_CACHE[s] for s in hole_strs]
    board = [_CARD_CACHE[s] for s in board_strs]
    handtype = eval7.handtype(eval7.evaluate(hole + board)).lower()

    hole_ranks = [c[0] for c in hole_strs]
    hole_suits = [c[1] for c in hole_strs]
    board_ranks = [c[0] for c in board_strs]
    board_suits = [c[1] for c in board_strs]
    pocket_pair = hole_ranks[0] == hole_ranks[1]

    if "straight flush" in handtype or "royal" in handtype:
        tier = "straight_flush"
    elif "four of a kind" in handtype:
        tier = "quads"
    elif "full house" in handtype:
        tier = "fullhouse"
    elif "flush" in handtype:
        tier = "flush"
    elif "straight" in handtype:
        tier = "straight"
    elif "three of a kind" in handtype:
        tier = "set" if pocket_pair else "trips"
    elif "two pair" in handtype:
        tier = "two_pair"
    elif "pair" in handtype:
        if pocket_pair:
            pp_idx = _RANK_IDX[hole_ranks[0]]
            board_max = max(_RANK_IDX[r] for r in board_ranks)
            tier = "overpair" if pp_idx > board_max else "underpair"
        else:
            paired = next((r for r in hole_ranks if r in board_ranks), None)
            if paired is None:
                tier = "weak_pair"
            else:
                paired_idx = _RANK_IDX[paired]
                sorted_board = sorted({_RANK_IDX[r] for r in board_ranks},
                                      reverse=True)
                if paired_idx == sorted_board[0]:
                    other = hole_ranks[1] if hole_ranks[0] == paired else hole_ranks[0]
                    kicker = _RANK_IDX[other]
                    tier = "tptk" if kicker >= _RANK_IDX["J"] else "tp_weak"
                elif len(sorted_board) > 1 and paired_idx == sorted_board[1]:
                    tier = "mid_pair"
                else:
                    tier = "low_pair"
    else:
        tier = "high_card"

    # Draws (ignore on river)
    has_flush_draw = False
    has_oesd = False
    has_gutshot = False
    if len(board_strs) < 5:
        all_suits = hole_suits + board_suits
        for s in "shdc":
            if all_suits.count(s) == 4:
                has_flush_draw = True
                break
        all_idx = sorted({_RANK_IDX[r] for r in hole_ranks + board_ranks})
        # Wheel: A also acts as -1 for A-2-3-4-5
        if 12 in all_idx:
            wheel = sorted(set(all_idx) | {-1})
        else:
            wheel = all_idx
        for ranks in (all_idx, wheel):
            for i in range(len(ranks) - 3):
                if ranks[i + 3] - ranks[i] == 3:
                    has_oesd = True
                    break
            if has_oesd:
                break
        if not has_oesd:
            for ranks in (all_idx, wheel):
                for i in range(len(ranks) - 3):
                    if ranks[i + 3] - ranks[i] == 4:
                        has_gutshot = True
                        break
                if has_gutshot:
                    break

    if has_flush_draw and has_oesd:
        draw = "combo_draw"
    elif has_flush_draw:
        draw = "flush_draw"
    elif has_oesd:
        draw = "oesd"
    elif has_gutshot:
        draw = "gutshot"
    else:
        draw = "none"

    return {
        "tier": tier,
        "draw": draw,
        "is_strong": _TIER_RANK[tier] >= _TIER_RANK["two_pair"],
        "is_top_pair_plus": _TIER_RANK[tier] >= _TIER_RANK["tptk"],
        "is_made_pair_plus": _TIER_RANK[tier] >= _TIER_RANK["mid_pair"],
        "has_strong_draw": draw in ("combo_draw", "flush_draw", "oesd"),
    }
