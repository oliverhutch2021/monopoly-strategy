"""Rollout evaluation of a game state, and trade price curves.

The value of a position is estimated by playing it out many times. To compare two
positions (e.g. "accept this trade" vs "keep the property") we use **common random
numbers**: rollout i of both positions uses the same seed, hence the same dice and the
same reshuffled decks, so most of the luck cancels in the paired difference.
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from .engine import Game, GameState, Rules
from .policies import make_bot


def _rollouts(args):
    state, bot_kinds, seeds, rules, frozen, horizon = args
    credit = np.zeros((len(seeds), state.n_players))
    worth = np.zeros((len(seeds), state.n_players))
    capped = np.zeros(len(seeds), dtype=bool)
    for i, seed in enumerate(seeds):
        g = Game([make_bot(k) for k in bot_kinds], state=state, seed=seed, rules=rules,
                 reshuffle_decks=True, frozen_squares=frozen)
        stop = state.turn + horizon
        while not g.done and g.s.turn < stop:
            g.take_turn()
        worth[i] = [g.net_worth(p) for p in range(state.n_players)]
        r = g.play()
        credit[i] = [r.credit(p) for p in range(state.n_players)]
        capped[i] = r.capped
    return credit, worth, capped


def rollout(state: GameState, bot_kinds: list[str], n: int, seed0: int = 0,
            rules: Rules | None = None, frozen=(), horizon: int = 40, workers: int | None = None):
    """Play `state` out n times.

    Returns (win credit per rollout and player, net worth per player after `horizon` turns,
    whether each rollout hit the turn limit). Credit is 1 for an outright win; a rollout
    stopped by the turn limit is a draw shared by the survivors (GameResult.credit).
    """
    rules = rules or Rules()
    workers = workers or os.cpu_count() or 1
    seeds = np.arange(seed0, seed0 + n)
    chunks = np.array_split(seeds, workers)
    args = [(state, bot_kinds, c.tolist(), rules, tuple(frozen), horizon) for c in chunks if len(c)]
    if workers == 1:
        parts = [_rollouts(a) for a in args]
    else:
        with ProcessPoolExecutor(workers) as ex:
            parts = list(ex.map(_rollouts, args))
    return tuple(np.concatenate([p[k] for p in parts]) for k in range(3))


def win_probabilities(state: GameState, bot_kinds: list[str], n: int, **kw) -> np.ndarray:
    credit, _, _ = rollout(state, bot_kinds, n, **kw)
    return credit.mean(axis=0)


def apply_trade(state: GameState, seller: int, buyer: int, squares, price: int) -> GameState | None:
    """Return a copy of `state` after `seller` sells `squares` to `buyer` for `price`, or None if invalid."""
    g = Game([make_bot("balanced") for _ in range(state.n_players)], state=state, seed=0)
    if not g.execute_trade(seller, buyer, tuple(squares), (), -price):
        return None
    return g.s


def trade_price_curve(state: GameState, bot_kinds: list[str], seller: int, buyer: int, squares,
                      prices, n: int = 2000, seed0: int = 0, horizon: int = 40,
                      workers: int | None = None, rules: Rules | None = None) -> pd.DataFrame:
    """Δ win probability (and Δ net worth after `horizon` turns) for every player, at each price.

    Baseline: the seller keeps the squares. In both arms the squares are then frozen (no further
    trades of them for the rest of the game), so the comparison isolates *this* deal: without the
    freeze, a third-party buyer would simply flip the property on to whoever needs it.
    """
    squares = tuple(squares)
    base_w, base_nw, base_cap = rollout(state, bot_kinds, n, seed0=seed0, frozen=squares,
                                        horizon=horizon, workers=workers, rules=rules)
    rows = []
    for price in prices:
        st = apply_trade(state, seller, buyer, squares, int(price))
        if st is None:
            continue
        w, nw, cap = rollout(st, bot_kinds, n, seed0=seed0, frozen=squares, horizon=horizon,
                             workers=workers, rules=rules)
        for p in range(state.n_players):
            d_win = w[:, p] - base_w[:, p]  # paired by seed
            d_nw = nw[:, p] - base_nw[:, p]
            rows.append({
                "price": int(price), "player": p,
                "p_win_base": float(base_w[:, p].mean()), "p_win_trade": float(w[:, p].mean()),
                "d_win": d_win.mean(), "d_win_se": d_win.std(ddof=1) / np.sqrt(n),
                "d_networth": d_nw.mean(), "d_networth_se": d_nw.std(ddof=1) / np.sqrt(n),
                "capped_share_base": float(base_cap.mean()), "capped_share_trade": float(cap.mean()),
            })
    return pd.DataFrame(rows)


def indifference_price(curve: pd.DataFrame, player: int, col: str = "d_win") -> float | None:
    """Price at which `player`'s Δ crosses zero (linear interpolation), if it does."""
    c = curve[curve.player == player].sort_values("price")
    x, y = c.price.to_numpy(float), c[col].to_numpy(float)
    for i in range(len(x) - 1):
        if y[i] == 0:
            return float(x[i])
        if np.sign(y[i]) != np.sign(y[i + 1]):
            return float(x[i] + (x[i + 1] - x[i]) * (0 - y[i]) / (y[i + 1] - y[i]))
    return None


def deal_summary(curve: pd.DataFrame, seller: int, buyer: int) -> dict:
    """Seller's floor, buyer's ceiling and whether a mutually beneficial price exists.

    If the buyer still gains at the highest price tested (usually all the cash they have),
    the ceiling is reported as that price with ``buyer_max_censored=True``.
    """
    lo = indifference_price(curve, seller)
    hi = indifference_price(curve, buyer)
    b = curve[curve.player == buyer].sort_values("price")
    censored = hi is None and b.d_win.iloc[-1] > 0
    if censored:
        hi = float(b.price.iloc[-1])
    at0 = curve[curve.price == curve.price.min()].set_index("player")
    return {
        "seller_min_price_win": lo, "buyer_max_price_win": hi, "buyer_max_censored": censored,
        "deal_zone_exists": bool(lo is not None and hi is not None and hi > lo),
        "seller_min_price_networth": indifference_price(curve, seller, "d_networth"),
        "buyer_max_price_networth": indifference_price(curve, buyer, "d_networth"),
        "p_win_base_seller": at0.loc[seller, "p_win_base"],
        "p_win_base_buyer": at0.loc[buyer, "p_win_base"],
        "p_win_buyer_if_free": at0.loc[buyer, "p_win_trade"],
    }
