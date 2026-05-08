"""PotOdds-03: pure equity-vs-pot-odds calculator."""
import eval7

BOT_NAME = "PotOdds-03"
_EPS = 0.08
_RAISE_T = 0.7
_EQ = {"AA":0.85, "KK":0.82, "QQ":0.8, "JJ":0.77, "TT":0.75, "99":0.72, "88":0.69, "77":0.66, "66":0.63, "55":0.6, "44":0.58, "33":0.55, "22":0.53, "AKs":0.67, "AQs":0.66, "AJs":0.65, "ATs":0.65, "A9s":0.63, "A8s":0.62, "A7s":0.61, "A6s":0.6, "A5s":0.6, "A4s":0.59, "A3s":0.58, "A2s":0.57, "KQs":0.63, "KJs":0.62, "KTs":0.62, "K9s":0.59, "K8s":0.56, "K7s":0.55, "K6s":0.55, "K5s":0.54, "K4s":0.53, "K3s":0.52, "K2s":0.52, "QJs":0.6, "QTs":0.6, "Q9s":0.57, "Q8s":0.54, "Q7s":0.52, "Q6s":0.51, "Q5s":0.5, "Q4s":0.5, "Q3s":0.49, "Q2s":0.48, "JTs":0.59, "J9s":0.56, "J8s":0.53, "J7s":0.5, "J6s":0.48, "J5s":0.47, "J4s":0.46, "J3s":0.46, "J2s":0.45, "T9s":0.55, "T8s":0.52, "T7s":0.49, "T6s":0.47, "T5s":0.44, "T4s":0.43, "T3s":0.42, "T2s":0.42, "98s":0.5, "97s":0.48, "96s":0.45, "95s":0.42, "94s":0.39, "93s":0.39, "92s":0.38, "87s":0.47, "86s":0.44, "85s":0.42, "84s":0.39, "83s":0.36, "82s":0.35, "76s":0.43, "75s":0.4, "74s":0.38, "73s":0.35, "72s":0.32, "65s":0.4, "64s":0.37, "63s":0.34, "62s":0.31, "54s":0.38, "53s":0.35, "52s":0.32, "43s":0.34, "42s":0.31, "32s":0.3, "AKo":0.65, "AQo":0.64, "AJo":0.63, "ATo":0.63, "A9o":0.61, "A8o":0.6, "A7o":0.59, "A6o":0.58, "A5o":0.57, "A4o":0.57, "A3o":0.56, "A2o":0.55, "KQo":0.61, "KJo":0.6, "KTo":0.59, "K9o":0.56, "K8o":0.53, "K7o":0.52, "K6o":0.52, "K5o":0.51, "K4o":0.5, "K3o":0.49, "K2o":0.48, "QJo":0.58, "QTo":0.57, "Q9o":0.54, "Q8o":0.51, "Q7o":0.49, "Q6o":0.48, "Q5o":0.47, "Q4o":0.46, "Q3o":0.46, "Q2o":0.45, "JTo":0.56, "J9o":0.53, "J8o":0.5, "J7o":0.47, "J6o":0.45, "J5o":0.44, "J4o":0.43, "J3o":0.43, "J2o":0.42, "T9o":0.52, "T8o":0.49, "T7o":0.47, "T6o":0.44, "T5o":0.4, "T4o":0.4, "T3o":0.39, "T2o":0.39, "98o":0.48, "97o":0.45, "96o":0.42, "95o":0.39, "94o":0.36, "93o":0.35, "92o":0.35, "87o":0.44, "86o":0.41, "85o":0.39, "84o":0.35, "83o":0.32, "82o":0.32, "76o":0.4, "75o":0.37, "74o":0.34, "73o":0.31, "72o":0.28, "65o":0.37, "64o":0.34, "63o":0.31, "62o":0.28, "54o":0.35, "53o":0.32, "52o":0.29, "43o":0.31, "42o":0.28, "32o":0.26}

def _hand_key(c1, c2):
    r = "23456789TJQKA"
    if r.index(c1[0]) < r.index(c2[0]):
        c1, c2 = c2, c1
    if c1[0] == c2[0]:
        return c1[0] + c2[0]
    return c1[0] + c2[0] + ("s" if c1[1] == c2[1] else "o")

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
        return {"ok": True}
    cards = state["your_cards"]; pot = state["pot"]; owed = state["amount_owed"]
    pot_odds = owed / max(pot + owed, 1)
    if state["street"] == "preflop":
        eq = _EQ.get(_hand_key(cards[0], cards[1]), 0.4)
    else:
        eq = _post_eq(cards, state["community_cards"])
    if state["can_check"]:
        if eq >= _RAISE_T:
            target = state["current_bet"] + int(pot * 0.6)
            return {"action": "raise", "amount": max(state["min_raise_to"], target)}
        return {"action": "check"}
    if eq >= _RAISE_T:
        target = state["current_bet"] + int(pot * 0.7)
        return {"action": "raise", "amount": max(state["min_raise_to"], target)}
    if eq >= pot_odds + _EPS:
        return {"action": "call"}
    return {"action": "fold"}
