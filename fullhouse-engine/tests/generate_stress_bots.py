"""Generate ~60 stress-test bots under bots/stress/.

Each bot is a self-contained ~30-80 line script with parameterised
behaviour.  Run:  python tests/generate_stress_bots.py
"""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STRESS = REPO / "bots" / "stress"
STRESS.mkdir(parents=True, exist_ok=True)


# ─── Canonical hand-strength tiers (sorted by approx HU equity) ──────────────
# Top fraction lists — strictly nested for easy parameterisation.
TIER_TOP_5 = ["AA","KK","QQ","JJ","AKs"]
TIER_TOP_10 = TIER_TOP_5 + ["TT","99","AKo","AQs","AJs","KQs"]
TIER_TOP_15 = TIER_TOP_10 + ["AQo","88","77","ATs","KJs","QJs"]
TIER_TOP_20 = TIER_TOP_15 + ["AJo","KQo","JTs","T9s","KTs","66"]
TIER_TOP_25 = TIER_TOP_20 + ["55","44","33","22","ATo","KJo","QTs","98s","87s","A9s"]
TIER_TOP_35 = TIER_TOP_25 + ["A8s","A7s","A5s","A4s","A3s","A2s","K9s","Q9s","J9s","T8s",
                              "97s","86s","76s","65s","54s","KTo","QJo","JTo","T9o"]
TIER_TOP_45 = TIER_TOP_35 + ["A6s","K8s","K7s","Q8s","J8s","T7s","96s","85s","75s","64s",
                              "A9o","A8o","A7o","A6o","K9o","Q9o","J9o","T9o","98o"]
TIER_TOP_60 = TIER_TOP_45 + ["K6s","K5s","K4s","K3s","K2s","Q7s","Q6s","J7s","J6s","T6s",
                              "95s","84s","74s","53s","43s","A5o","A4o","A3o","A2o",
                              "K8o","K7o","Q8o","J8o","T8o","97o","87o","86o","76o","65o","54o"]


def _to_set_repr(lst):
    return "{" + ", ".join(repr(x) for x in lst) + "}"


HAND_KEY_FN = '''def _hand_key(c1, c2):
    r = "23456789TJQKA"
    if r.index(c1[0]) < r.index(c2[0]):
        c1, c2 = c2, c1
    if c1[0] == c2[0]:
        return c1[0] + c2[0]
    return c1[0] + c2[0] + ("s" if c1[1] == c2[1] else "o")
'''


def write_bot(name, body):
    d = STRESS / name
    d.mkdir(exist_ok=True)
    (d / "bot.py").write_text(body, encoding="utf-8")


# ─── Archetype 1: Nit ────────────────────────────────────────────────────────
def gen_nit(idx, open_range, call_3bet_range, postflop_threshold):
    name = f"nit_{idx:02d}"
    body = f'''"""Nit-{idx:02d}: tight; folds without premium hand."""
import eval7

BOT_NAME = "Nit-{idx:02d}"
_OPEN = {_to_set_repr(open_range)}
_CALL3B = {_to_set_repr(call_3bet_range)}
_POSTFLOP_THRESH = {postflop_threshold}

{HAND_KEY_FN}
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
        return {{"ok": True}}
    cards = state["your_cards"]
    if state["street"] == "preflop":
        hk = _hand_key(cards[0], cards[1])
        raised = sum(1 for a in state["action_log"] if a.get("action") in ("raise","all_in"))
        if raised >= 2:
            return {{"action": "call"}} if hk in {{"AA","KK"}} else {{"action": "fold"}}
        if raised == 1:
            return {{"action": "call"}} if hk in _CALL3B else {{"action": "fold"}}
        if hk in _OPEN:
            return {{"action": "raise", "amount": max(state["min_raise_to"], 300)}}
        if state["can_check"]:
            return {{"action": "check"}}
        return {{"action": "fold"}}
    s = _strength(cards, state["community_cards"])
    if s >= _POSTFLOP_THRESH:
        target = state["current_bet"] + int(state["pot"] * 0.65)
        return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
    if state["can_check"]:
        return {{"action": "check"}}
    if state["amount_owed"] < state["pot"] * 0.2 and s >= 0.5:
        return {{"action": "call"}}
    return {{"action": "fold"}}
'''
    write_bot(name, body)


# ─── Archetype 2: Maniac ─────────────────────────────────────────────────────
def gen_maniac(idx, raise_freq, sizing_mult, allin_prob):
    name = f"maniac_{idx:02d}"
    body = f'''"""Maniac-{idx:02d}: raises constantly, jams often."""
import random

BOT_NAME = "Maniac-{idx:02d}"
_RNG = random.Random({1000 + idx})
_RAISE_FREQ = {raise_freq}
_SIZE = {sizing_mult}
_ALLIN_P = {allin_prob}

def decide(state):
    if state.get("type") == "warmup":
        return {{"ok": True}}
    stack = state["your_stack"]; pot = state["pot"]
    if _RNG.random() < _ALLIN_P:
        return {{"action": "all_in"}}
    if _RNG.random() < _RAISE_FREQ:
        target = state["current_bet"] + int(max(pot, state["min_raise_to"]) * _SIZE)
        target = max(target, state["min_raise_to"])
        if target >= stack + state["your_bet_this_street"]:
            return {{"action": "all_in"}}
        return {{"action": "raise", "amount": target}}
    if state["can_check"]:
        return {{"action": "check"}}
    return {{"action": "call"}}
'''
    write_bot(name, body)


# ─── Archetype 3: Calling Station ────────────────────────────────────────────
def gen_station(idx, fold_threshold_pot_frac, raise_freq):
    name = f"station_{idx:02d}"
    body = f'''"""Station-{idx:02d}: calls almost everything, rarely raises."""
import random

BOT_NAME = "Station-{idx:02d}"
_RNG = random.Random({2000 + idx})
_FOLD_THRESH = {fold_threshold_pot_frac}
_RAISE_FREQ = {raise_freq}

def decide(state):
    if state.get("type") == "warmup":
        return {{"ok": True}}
    if state["can_check"]:
        if _RNG.random() < _RAISE_FREQ:
            target = state["current_bet"] + int(state["pot"] * 0.5)
            return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
        return {{"action": "check"}}
    pot = max(state["pot"], 1)
    owed = state["amount_owed"]
    if owed > pot * _FOLD_THRESH:
        return {{"action": "fold"}}
    if _RNG.random() < _RAISE_FREQ:
        target = state["current_bet"] + int(pot * 0.5)
        return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
    return {{"action": "call"}}
'''
    write_bot(name, body)


# ─── Archetype 4: Random ─────────────────────────────────────────────────────
def gen_random(idx, fold_p, call_p, raise_p):
    name = f"random_{idx:02d}"
    body = f'''"""Random-{idx:02d}: random legal action, weighted."""
import random

BOT_NAME = "Random-{idx:02d}"
_RNG = random.Random({3000 + idx})
_FP = {fold_p}; _CP = {call_p}; _RP = {raise_p}

def decide(state):
    if state.get("type") == "warmup":
        return {{"ok": True}}
    if state["can_check"]:
        # check or raise
        r = _RNG.random()
        if r < _RP:
            target = state["current_bet"] + int(max(state["pot"], state["min_raise_to"]) * 0.7)
            return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
        return {{"action": "check"}}
    r = _RNG.random()
    if r < _FP:
        return {{"action": "fold"}}
    if r < _FP + _CP:
        return {{"action": "call"}}
    target = state["current_bet"] + int(max(state["pot"], state["min_raise_to"]) * 0.7)
    return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
'''
    write_bot(name, body)


# ─── Archetype 5: TAG ────────────────────────────────────────────────────────
def gen_tag(idx, open_range, cbet_freq, value_threshold):
    name = f"tag_{idx:02d}"
    body = f'''"""TAG-{idx:02d}: tight-aggressive with c-bet."""
import random, eval7

BOT_NAME = "TAG-{idx:02d}"
_RNG = random.Random({4000 + idx})
_OPEN = {_to_set_repr(open_range)}
_CBET = {cbet_freq}
_VAL = {value_threshold}

{HAND_KEY_FN}
def _strength(cards, board):
    if len(board) < 3:
        return 0.0
    full = [eval7.Card(c) for c in cards + board]
    s = eval7.evaluate(full)
    ht = eval7.handtype(s).lower()
    if "straight" in ht or "flush" in ht or "full" in ht or "four" in ht:
        return 0.95
    if "three" in ht or "two pair" in ht:
        return 0.85
    if "pair" in ht:
        ranks = "23456789TJQKA"
        my_ranks = sorted([ranks.index(c[0]) for c in cards], reverse=True)
        board_ranks = sorted([ranks.index(c[0]) for c in board], reverse=True)
        if my_ranks[0] == my_ranks[1]:
            return 0.7 if my_ranks[0] > board_ranks[0] else 0.4
        if my_ranks[0] in board_ranks and my_ranks[0] >= board_ranks[0]:
            return 0.6
        return 0.35
    return 0.15

def decide(state):
    if state.get("type") == "warmup":
        return {{"ok": True}}
    cards = state["your_cards"]; pot = state["pot"]
    raised = sum(1 for a in state["action_log"] if a.get("action") in ("raise","all_in"))
    if state["street"] == "preflop":
        hk = _hand_key(cards[0], cards[1])
        if raised >= 2:
            return {{"action": "call"}} if hk in {{"AA","KK","QQ","AKs","AKo"}} else {{"action": "fold"}}
        if raised == 1:
            if hk in {{"AA","KK","QQ","AKs"}}:
                t = state["current_bet"] * 3
                return {{"action": "raise", "amount": max(state["min_raise_to"], t)}}
            if hk in _OPEN and state["amount_owed"] < state["your_stack"] * 0.15:
                return {{"action": "call"}}
            return {{"action": "fold"}}
        if hk in _OPEN:
            return {{"action": "raise", "amount": max(state["min_raise_to"], 300)}}
        if state["can_check"]:
            return {{"action": "check"}}
        return {{"action": "fold"}}
    s = _strength(cards, state["community_cards"])
    am_aggr = state["seat_to_act"] in {{a["seat"] for a in state["action_log"] if a.get("action")=="raise"}}
    if state["can_check"]:
        if s >= _VAL:
            target = state["current_bet"] + int(pot * 0.65)
            return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
        if am_aggr and _RNG.random() < _CBET:
            target = state["current_bet"] + int(pot * 0.55)
            return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
        return {{"action": "check"}}
    pot_odds = state["amount_owed"] / max(pot + state["amount_owed"], 1)
    if s >= _VAL:
        target = state["current_bet"] + int(pot * 0.7)
        return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
    if s >= 0.45 and pot_odds < 0.3:
        return {{"action": "call"}}
    if s >= 0.6:
        return {{"action": "call"}}
    return {{"action": "fold"}}
'''
    write_bot(name, body)


# ─── Archetype 6: LAG ────────────────────────────────────────────────────────
def gen_lag(idx, open_range, threebet_freq, barrel_freq):
    name = f"lag_{idx:02d}"
    body = f'''"""LAG-{idx:02d}: loose-aggressive, frequent 3-bets and barrels."""
import random, eval7

BOT_NAME = "LAG-{idx:02d}"
_RNG = random.Random({5000 + idx})
_OPEN = {_to_set_repr(open_range)}
_3BP = {threebet_freq}
_BARREL = {barrel_freq}

{HAND_KEY_FN}
def decide(state):
    if state.get("type") == "warmup":
        return {{"ok": True}}
    cards = state["your_cards"]; pot = state["pot"]
    raised = sum(1 for a in state["action_log"] if a.get("action") in ("raise","all_in"))
    if state["street"] == "preflop":
        hk = _hand_key(cards[0], cards[1])
        if raised >= 2:
            return {{"action": "call"}} if hk in {{"AA","KK","QQ","JJ","AKs","AKo"}} else {{"action": "fold"}}
        if raised == 1:
            if hk in {{"AA","KK","QQ","AKs","AKo"}} or (hk in _OPEN and _RNG.random() < _3BP):
                t = state["current_bet"] * 3
                return {{"action": "raise", "amount": max(state["min_raise_to"], t)}}
            if hk in _OPEN and state["amount_owed"] < state["your_stack"] * 0.18:
                return {{"action": "call"}}
            return {{"action": "fold"}}
        if hk in _OPEN:
            return {{"action": "raise", "amount": max(state["min_raise_to"], 300)}}
        if state["can_check"]:
            return {{"action": "check"}}
        return {{"action": "fold"}}
    # Postflop: aggressive
    if state["can_check"]:
        if _RNG.random() < _BARREL:
            target = state["current_bet"] + int(pot * 0.65)
            return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
        return {{"action": "check"}}
    pot_odds = state["amount_owed"] / max(pot + state["amount_owed"], 1)
    if pot_odds < 0.30 and _RNG.random() < _BARREL * 0.7:
        target = state["current_bet"] + int(pot * 0.8)
        return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
    if pot_odds < 0.35:
        return {{"action": "call"}}
    return {{"action": "fold"}}
'''
    write_bot(name, body)


# ─── Archetype 7: Min-raiser ─────────────────────────────────────────────────
def gen_minraiser(idx, open_range, call_pot_frac):
    name = f"minraiser_{idx:02d}"
    body = f'''"""MinRaiser-{idx:02d}: only ever min-raises."""

BOT_NAME = "MinRaiser-{idx:02d}"
_OPEN = {_to_set_repr(open_range)}
_CALL = {call_pot_frac}

{HAND_KEY_FN}
def decide(state):
    if state.get("type") == "warmup":
        return {{"ok": True}}
    cards = state["your_cards"]; pot = state["pot"]
    if state["street"] == "preflop":
        hk = _hand_key(cards[0], cards[1])
        raised = sum(1 for a in state["action_log"] if a.get("action") in ("raise","all_in"))
        if hk in _OPEN:
            return {{"action": "raise", "amount": state["min_raise_to"]}}
        if raised >= 1 and hk in {{"AA","KK","QQ","JJ","TT","AKs","AKo"}}:
            return {{"action": "call"}}
        if state["can_check"]:
            return {{"action": "check"}}
        return {{"action": "fold"}}
    if state["can_check"]:
        if hk_strength(cards, state["community_cards"]) >= 0.6:
            return {{"action": "raise", "amount": state["min_raise_to"]}}
        return {{"action": "check"}}
    if state["amount_owed"] < pot * _CALL:
        return {{"action": "call"}}
    return {{"action": "fold"}}

def hk_strength(cards, board):
    if len(board) < 3:
        return 0.0
    import eval7
    full = [eval7.Card(c) for c in cards + board]
    ht = eval7.handtype(eval7.evaluate(full)).lower()
    if "two" in ht or "three" in ht or "straight" in ht or "flush" in ht or "full" in ht:
        return 0.85
    if "pair" in ht:
        return 0.5
    return 0.1
'''
    write_bot(name, body)


# ─── Archetype 8: Overbettor ─────────────────────────────────────────────────
def gen_overbettor(idx, open_range, pot_mult, value_only):
    name = f"overbet_{idx:02d}"
    body = f'''"""Overbet-{idx:02d}: raises 1.5-3x pot, polarised."""
import random, eval7

BOT_NAME = "Overbet-{idx:02d}"
_RNG = random.Random({7000 + idx})
_OPEN = {_to_set_repr(open_range)}
_MULT = {pot_mult}
_VALUE_ONLY = {value_only}

{HAND_KEY_FN}
def _strong(cards, board):
    if len(board) < 3:
        return False
    full = [eval7.Card(c) for c in cards + board]
    ht = eval7.handtype(eval7.evaluate(full)).lower()
    return any(x in ht for x in ("two pair","three","straight","flush","full","four"))

def decide(state):
    if state.get("type") == "warmup":
        return {{"ok": True}}
    cards = state["your_cards"]; pot = state["pot"]
    raised = sum(1 for a in state["action_log"] if a.get("action") in ("raise","all_in"))
    if state["street"] == "preflop":
        hk = _hand_key(cards[0], cards[1])
        if hk in _OPEN:
            target = state["current_bet"] + int(max(pot, 300) * _MULT)
            return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
        if raised and hk in {{"AA","KK"}}:
            return {{"action": "call"}}
        if state["can_check"]:
            return {{"action": "check"}}
        return {{"action": "fold"}}
    strong = _strong(cards, state["community_cards"])
    if state["can_check"]:
        if strong or (not _VALUE_ONLY and _RNG.random() < 0.4):
            target = state["current_bet"] + int(pot * _MULT)
            return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
        return {{"action": "check"}}
    if strong:
        target = state["current_bet"] + int(pot * _MULT)
        return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
    if state["amount_owed"] < pot * 0.2:
        return {{"action": "call"}}
    return {{"action": "fold"}}
'''
    write_bot(name, body)


# ─── Archetype 9: Push-or-fold ───────────────────────────────────────────────
def gen_pushfold(idx, jam_range, call_jam_range):
    name = f"pushfold_{idx:02d}"
    body = f'''"""PushFold-{idx:02d}: only jams or folds."""

BOT_NAME = "PushFold-{idx:02d}"
_JAM = {_to_set_repr(jam_range)}
_CALL_JAM = {_to_set_repr(call_jam_range)}

{HAND_KEY_FN}
def decide(state):
    if state.get("type") == "warmup":
        return {{"ok": True}}
    cards = state["your_cards"]
    if state["street"] == "preflop":
        hk = _hand_key(cards[0], cards[1])
        raised = sum(1 for a in state["action_log"] if a.get("action") in ("raise","all_in"))
        if raised:
            if hk in _CALL_JAM:
                return {{"action": "all_in"}}
            return {{"action": "fold"}}
        if hk in _JAM:
            return {{"action": "all_in"}}
        if state["can_check"]:
            return {{"action": "check"}}
        return {{"action": "fold"}}
    # Postflop: never voluntarily commit
    if state["can_check"]:
        return {{"action": "check"}}
    return {{"action": "fold"}}
'''
    write_bot(name, body)


# ─── Archetype 10: Positional ────────────────────────────────────────────────
def gen_positional(idx, late_open_range, threshold_seats):
    name = f"posn_{idx:02d}"
    body = f'''"""Positional-{idx:02d}: only plays late position."""
import eval7

BOT_NAME = "Positional-{idx:02d}"
_LATE_OPEN = {_to_set_repr(late_open_range)}
_THRESH_SEATS = {threshold_seats}

{HAND_KEY_FN}
def _is_late(state):
    your = state["seat_to_act"]; n = len(state["players"])
    after = 0
    for off in range(1, n):
        s = (your + off) % n
        p = state["players"][s]
        if not p.get("is_folded") and not p.get("is_all_in") and p.get("state") != "busted":
            after += 1
    return after <= _THRESH_SEATS

def decide(state):
    if state.get("type") == "warmup":
        return {{"ok": True}}
    cards = state["your_cards"]; pot = state["pot"]
    if state["street"] == "preflop":
        if not _is_late(state):
            if state["can_check"]:
                return {{"action": "check"}}
            return {{"action": "fold"}}
        hk = _hand_key(cards[0], cards[1])
        if hk in _LATE_OPEN:
            return {{"action": "raise", "amount": max(state["min_raise_to"], 300)}}
        if state["can_check"]:
            return {{"action": "check"}}
        return {{"action": "fold"}}
    if state["can_check"]:
        return {{"action": "check"}}
    if state["amount_owed"] < pot * 0.25:
        return {{"action": "call"}}
    return {{"action": "fold"}}
'''
    write_bot(name, body)


# ─── Archetype 11: Bluffer ───────────────────────────────────────────────────
def gen_bluffer(idx, cbet_freq, db_freq, triple_freq):
    name = f"bluff_{idx:02d}"
    body = f'''"""Bluffer-{idx:02d}: relentless c-bet/double-barrel/triple."""
import random

BOT_NAME = "Bluffer-{idx:02d}"
_RNG = random.Random({11000 + idx})
_CBET = {cbet_freq}
_DB = {db_freq}
_TRIPLE = {triple_freq}

def decide(state):
    if state.get("type") == "warmup":
        return {{"ok": True}}
    pot = state["pot"]
    if state["street"] == "preflop":
        ranks = [c[0] for c in state["your_cards"]]
        playable = ranks[0] in "AKQJT98765" or ranks[1] in "AKQJT98765"
        if playable:
            return {{"action": "raise", "amount": max(state["min_raise_to"], 300)}}
        if state["can_check"]:
            return {{"action": "check"}}
        return {{"action": "fold"}}
    rate = _CBET if state["street"] == "flop" else (_DB if state["street"] == "turn" else _TRIPLE)
    if state["can_check"]:
        if _RNG.random() < rate:
            target = state["current_bet"] + int(pot * 0.6)
            return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
        return {{"action": "check"}}
    if state["amount_owed"] < pot * 0.15:
        return {{"action": "call"}}
    return {{"action": "fold"}}
'''
    write_bot(name, body)


# ─── Archetype 12: Pot-odds drone ────────────────────────────────────────────
# Hand-vs-random equity table (approximate, ordered by HU equity)
EQUITY_VS_RANDOM = {
    "AA":0.85,"KK":0.82,"QQ":0.80,"JJ":0.77,"TT":0.75,"99":0.72,"88":0.69,"77":0.66,
    "66":0.63,"55":0.60,"44":0.58,"33":0.55,"22":0.53,
    "AKs":0.67,"AQs":0.66,"AJs":0.65,"ATs":0.65,"A9s":0.63,"A8s":0.62,"A7s":0.61,"A6s":0.60,
    "A5s":0.60,"A4s":0.59,"A3s":0.58,"A2s":0.57,
    "KQs":0.63,"KJs":0.62,"KTs":0.62,"K9s":0.59,"K8s":0.56,"K7s":0.55,"K6s":0.55,"K5s":0.54,
    "K4s":0.53,"K3s":0.52,"K2s":0.52,
    "QJs":0.60,"QTs":0.60,"Q9s":0.57,"Q8s":0.54,"Q7s":0.52,"Q6s":0.51,"Q5s":0.50,"Q4s":0.50,
    "Q3s":0.49,"Q2s":0.48,
    "JTs":0.59,"J9s":0.56,"J8s":0.53,"J7s":0.50,"J6s":0.48,"J5s":0.47,"J4s":0.46,"J3s":0.46,
    "J2s":0.45,
    "T9s":0.55,"T8s":0.52,"T7s":0.49,"T6s":0.47,"T5s":0.44,"T4s":0.43,"T3s":0.42,"T2s":0.42,
    "98s":0.50,"97s":0.48,"96s":0.45,"95s":0.42,"94s":0.39,"93s":0.39,"92s":0.38,
    "87s":0.47,"86s":0.44,"85s":0.42,"84s":0.39,"83s":0.36,"82s":0.35,
    "76s":0.43,"75s":0.40,"74s":0.38,"73s":0.35,"72s":0.32,
    "65s":0.40,"64s":0.37,"63s":0.34,"62s":0.31,
    "54s":0.38,"53s":0.35,"52s":0.32,
    "43s":0.34,"42s":0.31,"32s":0.30,
    "AKo":0.65,"AQo":0.64,"AJo":0.63,"ATo":0.63,"A9o":0.61,"A8o":0.60,"A7o":0.59,"A6o":0.58,
    "A5o":0.57,"A4o":0.57,"A3o":0.56,"A2o":0.55,
    "KQo":0.61,"KJo":0.60,"KTo":0.59,"K9o":0.56,"K8o":0.53,"K7o":0.52,"K6o":0.52,"K5o":0.51,
    "K4o":0.50,"K3o":0.49,"K2o":0.48,
    "QJo":0.58,"QTo":0.57,"Q9o":0.54,"Q8o":0.51,"Q7o":0.49,"Q6o":0.48,"Q5o":0.47,"Q4o":0.46,
    "Q3o":0.46,"Q2o":0.45,
    "JTo":0.56,"J9o":0.53,"J8o":0.50,"J7o":0.47,"J6o":0.45,"J5o":0.44,"J4o":0.43,"J3o":0.43,
    "J2o":0.42,
    "T9o":0.52,"T8o":0.49,"T7o":0.47,"T6o":0.44,"T5o":0.40,"T4o":0.40,"T3o":0.39,"T2o":0.39,
    "98o":0.48,"97o":0.45,"96o":0.42,"95o":0.39,"94o":0.36,"93o":0.35,"92o":0.35,
    "87o":0.44,"86o":0.41,"85o":0.39,"84o":0.35,"83o":0.32,"82o":0.32,
    "76o":0.40,"75o":0.37,"74o":0.34,"73o":0.31,"72o":0.28,
    "65o":0.37,"64o":0.34,"63o":0.31,"62o":0.28,
    "54o":0.35,"53o":0.32,"52o":0.29,
    "43o":0.31,"42o":0.28,"32o":0.26,
}


def gen_potodds(idx, epsilon, raise_threshold):
    name = f"potodds_{idx:02d}"
    eq_repr = "{" + ", ".join(f'"{k}":{v}' for k,v in EQUITY_VS_RANDOM.items()) + "}"
    body = f'''"""PotOdds-{idx:02d}: pure equity-vs-pot-odds calculator."""
import eval7

BOT_NAME = "PotOdds-{idx:02d}"
_EPS = {epsilon}
_RAISE_T = {raise_threshold}
_EQ = {eq_repr}

{HAND_KEY_FN}
def _post_eq(cards, board):
    if len(board) < 3:
        return 0.5
    full = [eval7.Card(c) for c in cards + board]
    ht = eval7.handtype(eval7.evaluate(full)).lower()
    if "straight flush" in ht or "four" in ht: return 0.99
    if "full" in ht or "flush" in ht: return 0.95
    if "straight" in ht: return 0.90
    if "three" in ht: return 0.85
    if "two" in ht: return 0.75
    if "pair" in ht: return 0.55
    return 0.20

def decide(state):
    if state.get("type") == "warmup":
        return {{"ok": True}}
    cards = state["your_cards"]; pot = state["pot"]; owed = state["amount_owed"]
    pot_odds = owed / max(pot + owed, 1)
    if state["street"] == "preflop":
        eq = _EQ.get(_hand_key(cards[0], cards[1]), 0.4)
    else:
        eq = _post_eq(cards, state["community_cards"])
    if state["can_check"]:
        if eq >= _RAISE_T:
            target = state["current_bet"] + int(pot * 0.6)
            return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
        return {{"action": "check"}}
    if eq >= _RAISE_T:
        target = state["current_bet"] + int(pot * 0.7)
        return {{"action": "raise", "amount": max(state["min_raise_to"], target)}}
    if eq >= pot_odds + _EPS:
        return {{"action": "call"}}
    return {{"action": "fold"}}
'''
    write_bot(name, body)


# ─── Generate everything ─────────────────────────────────────────────────────

def main():
    print("Generating stress bots into", STRESS)

    # Nits — varying open range tightness and post-flop strength threshold
    nit_3bet = ["AA","KK","QQ","JJ","AKs","AKo"]
    for i, (open_r, t) in enumerate([
        (TIER_TOP_5, 0.85), (TIER_TOP_10, 0.70), (TIER_TOP_5, 0.95),
        (TIER_TOP_10, 0.80), (TIER_TOP_15, 0.75),
    ], start=1):
        gen_nit(i, open_r, nit_3bet, t)

    # Maniacs
    for i, (rf, sm, ap) in enumerate([
        (0.85, 0.6, 0.05), (0.70, 1.0, 0.10), (0.92, 0.7, 0.02),
        (0.80, 1.5, 0.15), (0.95, 0.5, 0.08),
    ], start=1):
        gen_maniac(i, rf, sm, ap)

    # Calling stations
    for i, (ft, rf) in enumerate([
        (0.55, 0.05), (0.45, 0.10), (0.65, 0.02),
        (0.40, 0.15), (0.50, 0.08),
    ], start=1):
        gen_station(i, ft, rf)

    # Random
    for i, (fp, cp, rp) in enumerate([
        (0.40, 0.40, 0.20), (0.30, 0.45, 0.25), (0.50, 0.30, 0.20),
        (0.25, 0.50, 0.25), (0.35, 0.35, 0.30),
    ], start=1):
        gen_random(i, fp, cp, rp)

    # TAGs
    for i, (open_r, cb, vt) in enumerate([
        (TIER_TOP_15, 0.65, 0.65), (TIER_TOP_20, 0.55, 0.60),
        (TIER_TOP_10, 0.75, 0.70), (TIER_TOP_25, 0.50, 0.55),
        (TIER_TOP_15, 0.60, 0.65),
    ], start=1):
        gen_tag(i, open_r, cb, vt)

    # LAGs
    for i, (open_r, tb, br) in enumerate([
        (TIER_TOP_35, 0.20, 0.55), (TIER_TOP_45, 0.30, 0.65),
        (TIER_TOP_25, 0.15, 0.50), (TIER_TOP_45, 0.35, 0.60),
        (TIER_TOP_35, 0.25, 0.70),
    ], start=1):
        gen_lag(i, open_r, tb, br)

    # Min-raisers
    for i, (open_r, cf) in enumerate([
        (TIER_TOP_15, 0.20), (TIER_TOP_20, 0.30), (TIER_TOP_25, 0.15),
        (TIER_TOP_10, 0.25), (TIER_TOP_15, 0.10),
    ], start=1):
        gen_minraiser(i, open_r, cf)

    # Overbettors
    for i, (open_r, mult, vo) in enumerate([
        (TIER_TOP_15, 1.5, True), (TIER_TOP_20, 2.0, False),
        (TIER_TOP_10, 2.5, True), (TIER_TOP_25, 1.8, False),
        (TIER_TOP_15, 3.0, True),
    ], start=1):
        gen_overbettor(i, open_r, mult, vo)

    # Push-or-fold
    for i, (jr, cj) in enumerate([
        (TIER_TOP_10, ["AA","KK","QQ"]),
        (TIER_TOP_15, ["AA","KK","QQ","JJ","AKs","AKo"]),
        (TIER_TOP_5, ["AA","KK"]),
        (TIER_TOP_20, ["AA","KK","QQ","JJ","TT","AKs","AKo","AQs"]),
        (TIER_TOP_10, ["AA","KK","QQ","JJ"]),
    ], start=1):
        gen_pushfold(i, jr, cj)

    # Positional
    for i, (open_r, ts) in enumerate([
        (TIER_TOP_25, 1), (TIER_TOP_35, 2), (TIER_TOP_20, 1),
        (TIER_TOP_45, 2), (TIER_TOP_25, 0),
    ], start=1):
        gen_positional(i, open_r, ts)

    # Bluffers
    for i, (cb, db, tr) in enumerate([
        (0.85, 0.55, 0.30), (0.95, 0.70, 0.50), (0.75, 0.40, 0.20),
        (0.90, 0.65, 0.45), (0.80, 0.50, 0.25),
    ], start=1):
        gen_bluffer(i, cb, db, tr)

    # Pot-odds drones
    for i, (eps, rt) in enumerate([
        (0.05, 0.65), (0.02, 0.60), (0.08, 0.70), (0.00, 0.55), (0.10, 0.75),
    ], start=1):
        gen_potodds(i, eps, rt)

    written = sorted(p.name for p in STRESS.iterdir() if p.is_dir())
    print(f"\nGenerated {len(written)} bots:")
    for n in written:
        print(f"  {n}")


if __name__ == "__main__":
    main()
