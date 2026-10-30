"""Rollout evaluation of a game state, and trade price curves.

The value of a position is estimated by playing it out many times. To compare two
positions (e.g. "accept this trade" vs "keep the property") we use **common random
numbers**: rollout i of both positions uses the same seed, hence the same dice and the
same reshuffled decks, so most of the luck cancels in the paired difference.
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from . import watch
from .engine import Game, GameState, Rules
from .policies import make_bot


def _rollouts(args):
    state, bot_kinds, seeds, rules, frozen, horizon, marks = args
    credit = np.zeros((len(seeds), state.n_players))
    worth = np.zeros((len(seeds), state.n_players))
    later = np.zeros((len(seeds), state.n_players, len(marks)))  # net worth at each extra mark
    capped = np.zeros(len(seeds), dtype=bool)
    for i, seed in enumerate(seeds):
        g = Game([make_bot(k) for k in bot_kinds], state=state, seed=seed, rules=rules,
                 reshuffle_decks=True, frozen_squares=frozen)
        seen = {}
        for mark in sorted({horizon, *marks}):  # pausing to look doesn't change the game
            while not g.done and g.s.turn < state.turn + mark:
                g.take_turn()
            seen[mark] = [g.net_worth(p) for p in range(state.n_players)]
        worth[i] = seen[horizon]
        for k, mark in enumerate(marks):
            later[i, :, k] = seen[mark]
        r = g.play()
        credit[i] = [r.credit(p) for p in range(state.n_players)]
        capped[i] = r.capped
    return credit, worth, capped, later


def rollout(state: GameState, bot_kinds: list[str], n: int, seed0: int = 0,
            rules: Rules | None = None, frozen=(), horizon: int = 40, workers: int | None = None,
            marks: tuple = ()):
    """Play `state` out n times.

    Returns (credit per rollout and player, net worth per player after `horizon` player-turns,
    whether each rollout hit the turn limit). Credit is what the rules score (GameResult.credit,
    utility_name): 1 for an outright win; a game stopped by the turn limit scores by Rules.stalemate,
    e.g. a loss for everyone or championship points ÷ 28. With `marks` (player-turns from now), a fourth
    array holds net worth at each mark: shape (n, players, len(marks)).
    """
    rules = rules or Rules()
    workers = workers or os.cpu_count() or 1
    seeds = np.arange(seed0, seed0 + n)
    chunks = np.array_split(seeds, workers)
    args = [(state, bot_kinds, c.tolist(), rules, tuple(frozen), horizon, tuple(marks)) for c in chunks if len(c)]
    t0 = watch.started(n)  # counted by the live viewer (rollouts start mid-game, so none is replayed)
    if workers == 1:
        parts = [_rollouts(a) for a in args]
    else:
        with ProcessPoolExecutor(workers) as ex:
            parts = list(ex.map(_rollouts, args))
    watch.finished(n, t0)
    return tuple(np.concatenate([p[k] for p in parts]) for k in range(4 if marks else 3))


def win_probabilities(state: GameState, bot_kinds: list[str], n: int, **kw) -> np.ndarray:
    credit, _, _ = rollout(state, bot_kinds, n, **kw)
    return credit.mean(axis=0)


def apply_trade(state: GameState, seller: int, buyer: int, squares, price: int,
                rules: Rules | None = None) -> GameState | None:
    """Return a copy of `state` after `seller` sells `squares` to `buyer` for `price`, or None if the trade is
    invalid under `rules` (default: the official rules), e.g. a buyer who can't pay, or any trade at all once only
    two players are left under championship rules."""
    g = Game([make_bot("balanced") for _ in range(state.n_players)], state=state, seed=0, rules=rules)
    if not g.execute_trade(seller, buyer, tuple(squares), (), -price):
        return None
    return g.s


def trade_allowed(state: GameState, seller: int, buyer: int, squares, rules: Rules | None = None) -> bool:
    """Do `rules` allow this sale at all (at a price of £0)? False for e.g. trades heads-up under championship
    rules; a price the buyer can't pay is a separate matter (apply_trade)."""
    return apply_trade(state, seller, buyer, squares, 0, rules) is not None


def utility_name(rules: Rules | None) -> str:
    """What a rollout's credit measures under these rules (GameResult.credit)."""
    return {"networth": "win share (a game stopped by the turn limit goes to the richest player)",
            "loss": "win share (a game stopped by the turn limit is a loss for everyone)",
            "draw": "win share (a game stopped by the turn limit is shared by the survivors)",
            "championship": "championship points ÷ 28 (games stopped by the time limit score by finishing place)",
            }[(rules or Rules()).stalemate]


def trade_price_curve(state: GameState, bot_kinds: list[str], seller: int, buyer: int, squares,
                      prices, n: int = 2000, seed0: int = 0, horizon: int = 40,
                      workers: int | None = None, rules: Rules | None = None,
                      hypothetical: bool = False, networth_rounds: tuple = (), boot: int = 0) -> pd.DataFrame:
    """Δ credit (and Δ net worth after `horizon` player-turns) for every player, at each price.

    Credit is what the rules score (utility_name): a share of wins, or championship points ÷ 28, which are not
    win probabilities (two survivors share 39/28). The columns keep their historical names (p_win_*, d_win).

    Baseline: the seller keeps the squares. In both arms the squares are then frozen (no further
    trades of them for the rest of the game), so the comparison isolates *this* deal: without the
    freeze, a third-party buyer would simply flip the property on to whoever needs it. So the curve is the
    value of a one-shot sale with no resale, to these bots, under these rules.

    A trade the rules forbid returns an empty curve, unless hypothetical=True: then it is applied as an
    intervention anyway (the continuation still uses `rules`) and the result's attrs["legal"] is False.

    networth_rounds adds d_networth_r<k> columns: the change in net worth k rounds later (k turns of each player
    alive now), the same horizon in own turns at every table size. boot > 0 resamples the rollouts, jointly across
    prices and players, that many times and puts the spread of the deal's ends in attrs["deal_bootstrap"].
    """
    squares = tuple(squares)
    legal = trade_allowed(state, seller, buyer, squares, rules)
    if not legal and not hypothetical:
        out = pd.DataFrame()
        out.attrs["legal"] = False
        return out
    marks = tuple(k * sum(state.alive) for k in networth_rounds)
    base = rollout(state, bot_kinds, n, seed0=seed0, frozen=squares, horizon=horizon, workers=workers,
                   rules=rules, marks=marks)
    base_w, base_nw, base_cap = base[:3]
    rows, paired = [], {}
    for price in prices:
        st = apply_trade(state, seller, buyer, squares, int(price), rules if legal else None)
        if st is None:
            continue
        res = rollout(st, bot_kinds, n, seed0=seed0, frozen=squares, horizon=horizon, workers=workers,
                      rules=rules, marks=marks)
        w, nw, cap = res[:3]
        if boot:
            paired[int(price)] = (w[:, buyer] - base_w[:, buyer], w[:, seller] - base_w[:, seller])
        for p in range(state.n_players):
            d_win = w[:, p] - base_w[:, p]  # paired by seed
            d_nw = nw[:, p] - base_nw[:, p]
            row = {
                "price": int(price), "player": p,
                "p_win_base": float(base_w[:, p].mean()), "p_win_trade": float(w[:, p].mean()),
                "d_win": d_win.mean(), "d_win_se": d_win.std(ddof=1) / np.sqrt(n),
                "d_networth": d_nw.mean(), "d_networth_se": d_nw.std(ddof=1) / np.sqrt(n),
                "capped_share_base": float(base_cap.mean()), "capped_share_trade": float(cap.mean()),
            }
            for k, rounds in enumerate(networth_rounds):
                d = res[3][:, p, k] - base[3][:, p, k]
                row[f"d_networth_r{rounds}"] = d.mean()
                row[f"d_networth_r{rounds}_se"] = d.std(ddof=1) / np.sqrt(n)
            rows.append(row)
    out = pd.DataFrame(rows)
    out.attrs["legal"] = legal
    if boot and paired:
        x = np.array(sorted(paired), float)
        out.attrs["deal_bootstrap"] = deal_bootstrap(x, np.array([paired[int(p)][0] for p in x]),
                                                     np.array([paired[int(p)][1] for p in x]), boot, seed=seed0)
    return out


def deal_bootstrap(prices, d_buyer: np.ndarray, d_seller: np.ndarray, boot: int, seed: int = 0) -> dict:
    """How sure the deal's ends are: resample whole rollouts (the same games at every price, so a resample keeps
    the pairing across prices and between the two players), find the deal in each resample, and report the share
    of resamples with a deal and the 2.5-97.5% range of its lowest and highest price. d_buyer and d_seller are
    (prices, rollouts) arrays of paired changes in credit."""
    rng = np.random.default_rng(seed)
    n = d_buyer.shape[1]
    lows, highs, found = [], [], 0
    for start in range(0, boot, 50):  # batches keep memory small
        m = min(50, boot - start)
        counts = rng.multinomial(n, np.full(n, 1.0 / n), size=m).T / n  # (rollouts, m) resampling weights
        mb, ms = d_buyer @ counts, d_seller @ counts
        for k in range(m):
            deal = intersect(gain_ranges(prices, mb[:, k]), gain_ranges(prices, ms[:, k]))
            if deal:
                found += 1
                lows.append(deal[0][0])
                highs.append(deal[-1][1])

    def q(v):
        return (float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))) if v else (np.nan, np.nan)

    (l0, l1), (h0, h1) = q(lows), q(highs)
    return {"deal_share_of_resamples": found / boot, "deal_low_ci_low": l0, "deal_low_ci_high": l1,
            "deal_high_ci_low": h0, "deal_high_ci_high": h1, "resamples": boot}


def indifference_price(curve: pd.DataFrame, player: int, col: str = "d_win") -> float | None:
    """The FIRST price at which `player`'s Δ crosses zero (linear interpolation), if it does.

    Only meaningful for a monotone curve; deal_summary uses gain_ranges, which finds every range."""
    c = curve[curve.player == player].sort_values("price")
    x, y = c.price.to_numpy(float), c[col].to_numpy(float)
    for i in range(len(x) - 1):
        if y[i] == 0:
            return float(x[i])
        if np.sign(y[i]) != np.sign(y[i + 1]):
            return float(x[i] + (x[i + 1] - x[i]) * (0 - y[i]) / (y[i + 1] - y[i]))
    return None


Ranges = list[tuple[float, float]]


def gain_ranges(x, y) -> Ranges:
    """Every price range where the curve through (x, y) is above zero, linearly interpolated between the prices
    sampled: a list of (start, end), merged where they touch. A single positive sample is a zero-width range."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    out: Ranges = []

    def add(a: float, b: float) -> None:
        if out and a <= out[-1][1] + 1e-9:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))

    if len(x) == 1:
        return [(x[0], x[0])] if y[0] > 0 else []
    for x0, x1, y0, y1 in zip(x[:-1], x[1:], y[:-1], y[1:]):
        if y0 > 0 and y1 > 0:
            add(x0, x1)
        elif y0 > 0:  # falls to zero or below inside the step
            add(x0, x0 + (x1 - x0) * y0 / (y0 - y1))
        elif y1 > 0:  # rises above zero inside the step
            add(x0 + (x1 - x0) * -y0 / (y1 - y0), x1)
    return out


def intersect(a: Ranges, b: Ranges) -> Ranges:
    """Where two sets of ranges overlap (by more than a point)."""
    out, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if hi > lo:
            out.append((lo, hi))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def show_ranges(r: Ranges) -> str:
    """'500-650; 800-1200' (whole pounds), '' for none."""
    return "; ".join(f"{lo:.0f}-{hi:.0f}" for lo, hi in r)


def reversals(y, se, direction: int, z: float = 2.0) -> int:
    """Steps between neighbouring prices that go the wrong way by more than z standard errors: the buyer's change
    should fall as the price rises (direction -1), the seller's should rise (+1). A reversal means the player does
    better after paying more (or receiving less) - the fixed policy misuses cash in that position, which a player
    who could simply hold the money never would. Such a curve says more about the policy than about the property.

    Conservative: each step's standard error is taken as if the two prices' estimates were independent, but every
    price is played on the same games, so the true error of a step is smaller. A flagged reversal is real; a small
    one can go unflagged."""
    y, se = np.asarray(y, float), np.asarray(se, float)
    step = np.diff(y) * direction
    return int((step < -z * np.sqrt(se[1:] ** 2 + se[:-1] ** 2)).sum())


def deal_summary(curve: pd.DataFrame, seller: int, buyer: int, legal: bool = True) -> dict:
    """Where a sale suits both sides, read from a price curve without assuming its shape.

    The deal is every price range where both the buyer's and the seller's change in credit is above zero (a union of
    ranges, not one floor and ceiling: a curve that is not monotone can cross zero several times). Reported:
      deal_ranges, deal_pieces          the ranges themselves and how many there are
      seller_min_price_win              the lowest price in the deal (with no deal: the lowest price the seller
                                        gains at, 0 if even a gift helps them, NaN if they never gain)
      buyer_max_price_win               the highest price in the deal (with no deal: the highest price the buyer
                                        gains at, NaN if never), buyer_max_censored when the buyer still gains at
                                        the highest price tested (usually all the cash they have)
      confident_deal_ranges             prices where both changes are above zero by more than 1.96 standard errors
                                        (pointwise, so a guide rather than a joint interval)
      buyer_reversals, seller_reversals steps against the expected direction (see `reversals`); monotone = none
      legal                             False when the rules forbid the trade (e.g. championship rules heads-up):
                                        the curve is then a hypothetical intervention and deal_zone_exists is False
    The net-worth versions use the same ranges on the change in net worth, after the curve's horizon in
    player-turns and, where the curve has them (d_networth_r<k>), after k of each player's own turns. Credit is
    whatever the rules score: a share of wins, or championship points ÷ 28 (see trade_price_curve)."""
    b = curve[curve.player == buyer].sort_values("price")
    s = curve[curve.player == seller].sort_values("price")
    x = b.price.to_numpy(float)
    out = {"legal": bool(legal)}
    marks = [c for c in curve.columns if re.fullmatch(r"d_networth_r\d+", c)]
    for col, tag in [("d_win", "win"), ("d_networth", "networth")] + [(c, c[2:]) for c in marks]:
        bg, sg = gain_ranges(x, b[col]), gain_ranges(x, s[col])
        deal = intersect(bg, sg) if legal else []
        out[f"seller_min_price_{tag}"] = deal[0][0] if deal else (sg[0][0] if sg else np.nan)
        out[f"buyer_max_price_{tag}"] = deal[-1][1] if deal else (bg[-1][1] if bg else np.nan)
        if tag == "win":
            out.update(deal_zone_exists=bool(deal), deal_ranges=show_ranges(deal), deal_pieces=len(deal),
                       buyer_max_censored=bool(b[col].iloc[-1] > 0), seller_gains_free=bool(s[col].iloc[0] > 0),
                       buyer_gain_ranges=show_ranges(bg), seller_gain_ranges=show_ranges(sg))
            se_b, se_s = b[f"{col}_se"].to_numpy(float), s[f"{col}_se"].to_numpy(float)
            sure = intersect(gain_ranges(x, b[col] - 1.96 * se_b), gain_ranges(x, s[col] - 1.96 * se_s))
            out["confident_deal_ranges"] = show_ranges(sure) if legal else ""
            out["buyer_reversals"] = reversals(b[col], se_b, -1)
            out["seller_reversals"] = reversals(s[col], se_s, +1)
            out["monotone"] = out["buyer_reversals"] == out["seller_reversals"] == 0
    at0 = curve[curve.price == curve.price.min()].set_index("player")
    out.update(p_win_base_seller=at0.loc[seller, "p_win_base"], p_win_base_buyer=at0.loc[buyer, "p_win_base"],
               p_win_buyer_if_free=at0.loc[buyer, "p_win_trade"])
    return out
