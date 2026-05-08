"""eval7 shim for local dev on Python 3.12+ (eval7's C extension requires Python <=3.11).
Uses treys under the hood. The competition sandbox runs Python 3.11 with the real eval7.
"""
from treys import Card as _TreysCard, Evaluator as _Evaluator

_evaluator = _Evaluator()


class Card:
    def __init__(self, s: str):
        self._s = s
        self._treys = _TreysCard.new(s)

    def __str__(self):
        return self._s

    def __repr__(self):
        return f"Card('{self._s}')"

    def __eq__(self, other):
        return isinstance(other, Card) and self._s == other._s

    def __hash__(self):
        return hash(self._s)


def evaluate(cards) -> int:
    # eval7 convention: higher score = stronger hand
    # treys convention: lower score = stronger hand (1 = Royal Flush, 7462 = worst)
    treys_cards = [c._treys for c in cards]
    hand = treys_cards[:2]   # hole cards
    board = treys_cards[2:]  # community cards
    return 7463 - _evaluator.evaluate(board, hand)


def handtype(score: int) -> str:
    treys_score = 7463 - score
    rank_class = _evaluator.get_rank_class(treys_score)
    return _evaluator.class_to_string(rank_class)
