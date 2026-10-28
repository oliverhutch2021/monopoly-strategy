"""Exact Markov-chain model of a single token's movement.

State space (123 states)
------------------------
* ``(pos, d)``: about to roll from square ``pos`` having already thrown ``d`` doubles
  this turn (d = 0, 1, 2). Square 10 here means *Just Visiting*.
* ``J1, J2, J3``: in jail, about to make attempt 1, 2 or 3 to roll a double.

One transition = one throw of the dice. Cards are modelled as drawn uniformly at random
(with replacement); the simulator uses real fixed-order decks, and comparing the two
measures the cost of that simplification.

Jail strategies
---------------
* ``short``: pay / use a card immediately, then take a normal turn (J1 behaves like (10, 0)).
* ``long``: roll for doubles each attempt; on a double move and end the turn; after the
  third failure pay and move by that throw.

Outputs (all exact, from the stationary distribution)
------------------------------------------------------
* ``visits_per_turn[k]``: expected landings on square k during one turn of one player
  (counts the card square *and* where the card sends you; being sent to jail is not a landing).
* ``jail_turn_share``: fraction of turns that start in jail.
* ``utility_dice_per_turn[k]``: E[dice total x 1{land on utility k}] per turn, for utility rent.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .edition import Edition, load_edition

JAIL = -1
DICE = [(a, b) for a in range(1, 7) for b in range(1, 7)]


@dataclass
class MarkovResult:
    edition: Edition
    jail_strategy: str
    take_chance_prob: float
    P: np.ndarray                      # roll-to-roll transition matrix (123 x 123)
    pi: np.ndarray                     # stationary distribution over roll-states
    visits_per_turn: np.ndarray        # (40,)
    utility_dice_per_turn: np.ndarray  # (40,), non-zero only on utility squares
    jail_turn_share: float
    rolls_per_turn: float

    @property
    def landing_share(self) -> np.ndarray:
        """Share of all landings that happen on each square (sums to 1)."""
        return self.visits_per_turn / self.visits_per_turn.sum()


def _state(pos: int, d: int) -> int:
    return pos * 3 + d


def _jail_state(n: int) -> int:  # n = 1, 2, 3
    return 120 + n - 1


def _resolve(ed: Edition, sq: int, take_chance_prob: float):
    """All outcomes of landing on sq: list of (prob, final square or JAIL, visited squares)."""
    return _resolve_cached(ed.name, sq, take_chance_prob)


@lru_cache(maxsize=None)
def _resolve_cached(ed_name: str, sq: int, take_chance_prob: float):
    ed = load_edition(ed_name)
    t = ed.types[sq]
    if t == "go_to_jail":
        return ((1.0, JAIL, (sq,)),)
    if t == "chance":
        inner = _card_outcomes(ed, "chance", sq, take_chance_prob)
    elif t == "community_chest":
        inner = _card_outcomes(ed, "community_chest", sq, take_chance_prob)
    else:
        return ((1.0, sq, (sq,)),)
    return tuple((p, final, (sq,) + visits) for p, final, visits in inner)


def _card_outcomes(ed: Edition, deck: str, sq: int, take_chance_prob: float):
    """Outcomes of drawing one card from `deck` while standing on sq (visits exclude sq)."""
    cards = ed.chance if deck == "chance" else ed.community_chest
    w = 1.0 / len(cards)
    out = []
    for c in cards:
        a = c.action
        if a == "advance" or a == "back_to":
            for p, final, visits in _resolve(ed, c.to, take_chance_prob):
                out.append((w * p, final, visits))
        elif a == "back":
            for p, final, visits in _resolve(ed, (sq - c.n) % ed.n_squares, take_chance_prob):
                out.append((w * p, final, visits))
        elif a == "jail":
            out.append((w, JAIL, ()))
        elif a == "fine_or_chance" and take_chance_prob > 0:
            out.append((w * (1 - take_chance_prob), sq, ()))
            for p, final, visits in _card_outcomes(ed, "chance", sq, take_chance_prob):
                out.append((w * take_chance_prob * p, final, visits))
        else:  # money cards, repairs, get-out-of-jail-free: token stays put
            out.append((w, sq, ()))
    return out


def build_chain(edition: Edition | None = None, jail_strategy: str = "long",
                take_chance_prob: float = 0.0) -> MarkovResult:
    ed = edition or load_edition()
    n_sq = ed.n_squares
    assert n_sq == 40, "state indexing assumes a 40-square board"
    n_states = 123
    jail_sq = ed.jail_square
    P = np.zeros((n_states, n_states))
    # expected visits per square for one roll *from* each state, and utility dice mass
    V = np.zeros((n_states, n_sq))
    U = np.zeros((n_states, n_sq))
    util = [i for i in range(n_sq) if ed.types[i] == "utility"]

    def add_move(row, start, total, prob, next_state_fn):
        dest = (start + total) % n_sq
        for p, final, visits in _resolve(ed, dest, take_chance_prob):
            pp = prob * p
            for v in visits:
                V[row, v] += pp
            if dest in util:
                U[row, dest] += pp * total
            col = _jail_state(1) if final == JAIL else next_state_fn(final)
            P[row, col] += pp

    for pos in range(n_sq):
        for d in range(3):
            row = _state(pos, d)
            for d1, d2 in DICE:
                prob = 1 / 36
                dbl = d1 == d2
                if dbl and d == 2:
                    P[row, _jail_state(1)] += prob  # third double: straight to jail
                    continue
                nxt = (lambda f, d=d: _state(f, d + 1)) if dbl else (lambda f: _state(f, 0))
                add_move(row, pos, d1 + d2, prob, nxt)

    for n in (1, 2, 3):
        row = _jail_state(n)
        if jail_strategy == "short":
            if n == 1:
                P[row] = P[_state(jail_sq, 0)]
                V[row] = V[_state(jail_sq, 0)]
                U[row] = U[_state(jail_sq, 0)]
            else:  # unreachable under the short strategy; keep the matrix stochastic
                P[row, _state(jail_sq, 0)] = 1.0
            continue
        for d1, d2 in DICE:
            prob = 1 / 36
            if d1 == d2 or n == 3:  # out on a double, or forced out after the third attempt
                add_move(row, jail_sq, d1 + d2, prob, lambda f: _state(f, 0))
            else:
                P[row, _jail_state(n + 1)] += prob

    assert np.allclose(P.sum(axis=1), 1.0), "transition rows must sum to 1"
    pi = stationary(P)

    turn_start = np.zeros(n_states, dtype=bool)
    turn_start[[_state(p, 0) for p in range(n_sq)]] = True
    turn_start[[_jail_state(n) for n in (1, 2, 3)]] = True
    turns_per_roll = pi[turn_start].sum()
    visits_per_turn = (pi @ V) / turns_per_roll
    util_per_turn = (pi @ U) / turns_per_roll
    jail_share = pi[[_jail_state(n) for n in (1, 2, 3)]].sum() / turns_per_roll
    return MarkovResult(ed, jail_strategy, take_chance_prob, P, pi, visits_per_turn,
                        util_per_turn, float(jail_share), float(1 / turns_per_roll))


def stationary(P: np.ndarray) -> np.ndarray:
    """Solve pi P = pi, sum(pi) = 1 by least squares on the augmented system."""
    n = P.shape[0]
    A = np.vstack([P.T - np.eye(n), np.ones(n)])
    b = np.zeros(n + 1)
    b[-1] = 1.0
    pi, *_ = np.linalg.lstsq(A, b, rcond=None)
    pi = np.clip(pi, 0, None)
    return pi / pi.sum()
