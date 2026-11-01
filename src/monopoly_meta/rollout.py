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


def play_recording(g: Game, horizon: int, own_turns: tuple = ()) -> tuple[list, np.ndarray, np.ndarray]:
    """Play `g` to the end, looking at net worth on the way (looking changes nothing in the game).

    Returns every player's net worth after `horizon` player-turns from now (or at the end, if the game ends
    first); each player's net worth right after their own k-th turn from now, for each k in `own_turns`, as a
    (players, len(own_turns)) array; and the number of their own turns each of those values was taken at. A
    player who goes bankrupt before their k-th turn is recorded at 0 (net worth at the horizon of a bankrupt
    player), and a player still in when the game ends first is recorded at the end. Own turns count the turns a
    player actually takes, so eliminations don't stretch or shrink anyone's horizon, and both arms of a paired
    comparison measure each player after the same number of their own turns."""
    n, start = g.s.n_players, g.s.turn
    at_horizon = None
    taken = [0] * n
    value = np.full((n, len(own_turns)), np.nan)
    turns = np.zeros((n, len(own_turns)), dtype=int)
    while not g.done:
        if at_horizon is None and g.s.turn >= start + horizon:
            at_horizon = [g.net_worth(p) for p in range(n)]
        p = g.s.current
        g.take_turn()
        taken[p] += 1
        for j, k in enumerate(own_turns):
            if taken[p] == k:
                value[p, j], turns[p, j] = g.net_worth(p), k
    if at_horizon is None:
        at_horizon = [g.net_worth(p) for p in range(n)]
    for q in range(n):
        for j in range(len(own_turns)):
            if np.isnan(value[q, j]):  # out of the game, or the game ended first
                value[q, j], turns[q, j] = g.net_worth(q), taken[q]
    return at_horizon, value, turns


def _later_deal(g: Game, start: int, watched: tuple) -> tuple[int, int, int, int]:
    """The first trade, after the start, that moved one of the `watched` squares: (player-turns from the start,
    the player who received it, the cash they paid for it, 1 if they also gave property in exchange: a swap, whose
    price is then only its cash part); (-1, -1, 0, 0) if none did."""
    for turn, a, b, a_gives, b_gives, cash in g.trade_log or ():
        if any(sq in a_gives for sq in watched):
            return turn - start, b, -cash, int(len(b_gives) > 0)
        if any(sq in b_gives for sq in watched):
            return turn - start, a, cash, int(len(a_gives) > 0)
    return -1, -1, 0, 0


def _rollouts(args):
    state, bot_kinds, seeds, rules, frozen, horizon, own_turns, watched = args
    n = state.n_players
    credit = np.zeros((len(seeds), n))
    outright = np.zeros((len(seeds), n))  # 1 for the outright winner of a game not stopped by the limit
    worth = np.zeros((len(seeds), n))
    later = np.zeros((len(seeds), n, len(own_turns)))  # net worth after k own turns
    capped = np.zeros(len(seeds), dtype=bool)
    deals = np.full((len(seeds), 4), -1, dtype=np.int64)  # the watched squares' first later trade
    for i, seed in enumerate(seeds):
        g = Game([make_bot(k) for k in bot_kinds], state=state, seed=seed, rules=rules,
                 reshuffle_decks=True, frozen_squares=frozen)
        if watched:
            g.trade_log = []
        worth[i], later[i], _ = play_recording(g, horizon, own_turns)
        r = g.result()
        credit[i] = [r.credit(p) for p in range(n)]
        if not r.capped:
            outright[i, r.winner] = 1.0
        capped[i] = r.capped
        if watched:
            deals[i] = _later_deal(g, state.turn, watched)
    return {"credit": credit, "worth": worth, "capped": capped, "later": later, "outright": outright,
            "deals": deals}


def rollouts(state: GameState, bot_kinds: list[str], n: int, seed0: int = 0, rules: Rules | None = None,
             frozen=(), horizon: int = 40, workers: int | None = None, own_turns: tuple = (),
             watched: tuple = ()) -> dict:
    """Play `state` out n times; every array has one row per rollout (seeds seed0 .. seed0 + n - 1).

    credit    (n, players) what the rules score (GameResult.credit, utility_name): 1 for an outright win; a game
              stopped by the turn limit scores by Rules.stalemate (a loss for everyone, or championship points ÷ 28)
    outright  (n, players) 1 for the outright winner of a game that wasn't stopped by the limit
    worth     (n, players) net worth after `horizon` player-turns (or at the end)
    capped    (n,) whether the game hit the turn limit
    later     (n, players, len(own_turns)) net worth after k of each player's own turns (play_recording)
    deals     (n, 4) for `watched` squares: the first later trade of one of them (player-turns from now, the
              player who got it, the cash they paid), or -1s; frozen squares never trade
    """
    rules = rules or Rules()
    workers = workers or os.cpu_count() or 1
    seeds = np.arange(seed0, seed0 + n)
    chunks = np.array_split(seeds, workers)
    args = [(state, bot_kinds, c.tolist(), rules, tuple(frozen), horizon, tuple(own_turns), tuple(watched))
            for c in chunks if len(c)]
    t0 = watch.started(n)  # counted by the live viewer (rollouts start mid-game, so none is replayed)
    if workers == 1:
        parts = [_rollouts(a) for a in args]
    else:
        with ProcessPoolExecutor(workers) as ex:
            parts = list(ex.map(_rollouts, args))
    watch.finished(n, t0)
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}


def rollout(state: GameState, bot_kinds: list[str], n: int, seed0: int = 0,
            rules: Rules | None = None, frozen=(), horizon: int = 40, workers: int | None = None,
            own_turns: tuple = ()):
    """Play `state` out n times (see `rollouts`): (credit, net worth after `horizon` player-turns, capped), and
    with `own_turns` a fourth array, net worth after k of each player's own turns."""
    r = rollouts(state, bot_kinds, n, seed0=seed0, rules=rules, frozen=frozen, horizon=horizon, workers=workers,
                 own_turns=own_turns)
    out = (r["credit"], r["worth"], r["capped"])
    return out + (r["later"],) if own_turns else out


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
                      hypothetical: bool = False, own_turns: tuple = (), boot: int = 0,
                      freeze: bool = True) -> pd.DataFrame:
    """Δ credit (and Δ net worth after `horizon` player-turns) for every player, at each price.

    Credit is what the rules score (utility_name): a share of wins, or championship points ÷ 28, which are not
    win probabilities (two survivors share 39/28). The columns keep their historical names (p_win_*, d_win);
    d_outright is the change in outright wins (games won before any time limit), whatever the rules score.

    Two questions, two baselines (the 2026-10-31 review):
      freeze=True   sell now vs keep it for good: in both arms the squares are frozen (never traded again), so the
                    curve isolates what *this* deed is worth to each side: a one-shot sale with no resale.
      freeze=False  sell now vs carry on as normal: nothing is frozen, so in the keep arm the bots may still trade
                    the squares later, as they usually would. That is the comparison behind accepting or
                    declining an offer today. attrs["later_deals"] says what the keep arm did instead: how often
                    the squares changed hands later, after how long, to whom and for how much.

    Rows with player -1 are everyone except the buyer and the seller, summed game by game (so their standard error
    is paired, not a sum of independent errors).

    A trade the rules forbid returns an empty curve, unless hypothetical=True: then it is applied as an
    intervention anyway (the continuation still uses `rules`) and the result's attrs["legal"] is False.

    own_turns adds d_networth_own<k> columns: the change in each player's net worth after k of their own turns
    (play_recording), the same horizon at every table size, whoever goes bankrupt. boot > 0 resamples the
    rollouts, jointly across prices and players, that many times and puts the spread of the deal's ends in
    attrs["deal_bootstrap"].
    """
    squares = tuple(squares)
    legal = trade_allowed(state, seller, buyer, squares, rules)
    if not legal and not hypothetical:
        out = pd.DataFrame()
        out.attrs["legal"] = False
        return out
    frozen = squares if freeze else ()
    kw = dict(seed0=seed0, frozen=frozen, horizon=horizon, workers=workers, rules=rules, own_turns=own_turns)
    base = rollouts(state, bot_kinds, n, watched=() if freeze else squares, **kw)
    others = [p for p in range(state.n_players) if p not in (buyer, seller)]
    rows, paired = [], {}

    def stats(d):
        return d.mean(), d.std(ddof=1) / np.sqrt(n)

    for price in prices:
        st = apply_trade(state, seller, buyer, squares, int(price), rules if legal else None)
        if st is None:
            continue
        res = rollouts(st, bot_kinds, n, **kw)
        if boot:
            paired[int(price)] = (res["credit"][:, buyer] - base["credit"][:, buyer],
                                  res["credit"][:, seller] - base["credit"][:, seller])
        for p in list(range(state.n_players)) + ([-1] if len(others) > 1 else []):
            cols = others if p == -1 else [p]
            pick = (lambda a: a[:, cols].sum(axis=1))  # noqa: E731  (one player, or the bystanders summed)
            d_win, d_out, d_nw = (pick(res[k]) - pick(base[k]) for k in ("credit", "outright", "worth"))
            row = {"price": int(price), "player": p,
                   "p_win_base": float(pick(base["credit"]).mean()), "p_win_trade": float(pick(res["credit"]).mean()),
                   "capped_share_base": float(base["capped"].mean()), "capped_share_trade": float(res["capped"].mean())}
            row["d_win"], row["d_win_se"] = stats(d_win)
            row["d_outright"], row["d_outright_se"] = stats(d_out)
            row["d_networth"], row["d_networth_se"] = stats(d_nw)
            for k, turns in enumerate(own_turns):
                d = res["later"][:, cols, k].sum(axis=1) - base["later"][:, cols, k].sum(axis=1)
                row[f"d_networth_own{turns}"], row[f"d_networth_own{turns}_se"] = stats(d)
            rows.append(row)
    out = pd.DataFrame(rows)
    out.attrs["legal"] = legal
    out.attrs["frozen"] = freeze
    if not freeze:
        out.attrs["later_deals"] = later_deals(base["deals"], buyer, seller)
    if boot and paired:
        x = np.array(sorted(paired), float)
        out.attrs["deal_bootstrap"] = deal_bootstrap(x, np.array([paired[int(p)][0] for p in x]),
                                                     np.array([paired[int(p)][1] for p in x]), boot, seed=seed0)
    return out


def later_deals(deals: np.ndarray, buyer: int, seller: int) -> dict:
    """What the keep arm of a live continuation did with the squares: the share of games in which they changed
    hands by a later trade, the share in which the buyer got them, the median wait (player-turns), the share of those
    that were swaps (the buyer also gave property), and the median and commonest cash paid (a swap's cash part)."""
    moved = deals[:, 0] >= 0
    to_buyer = moved & (deals[:, 1] == buyer)
    out = {"games": int(len(deals)), "traded_later": float(moved.mean()), "to_buyer": float(to_buyer.mean())}
    if to_buyer.any():
        cash = pd.Series(deals[to_buyer, 2])
        mode = int(cash.mode().iloc[0])
        out.update(median_wait=float(np.median(deals[to_buyer, 0])), median_price=float(cash.median()),
                   price_mode=mode, price_mode_share=float((cash == mode).mean()),
                   swap_share=float(deals[to_buyer, 3].mean()) if deals.shape[1] > 3 else 0.0)
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
      sampled_deal_prices               the prices actually played at which both changes are above zero; the
                                        ranges between them are interpolated
      confident_sampled_prices          ... and above zero by more than 1.96 standard errors each
      whole_pound_ranges                the whole-pound prices strictly inside the deal ranges (a deal narrower
                                        than £1 may hold none, so nobody could actually pay it)
      evidence                          the strongest of: "confident at a sampled price", "at a sampled price",
                                        "between sampled prices only", "no whole-pound price" (or "" for no deal)
    The net-worth versions use the same ranges on the change in net worth, after the curve's horizon in
    player-turns and, where the curve has them (d_networth_own<k>), after k of each player's own turns. Credit is
    whatever the rules score: a share of wins, or championship points ÷ 28 (see trade_price_curve)."""
    b = curve[curve.player == buyer].sort_values("price")
    s = curve[curve.player == seller].sort_values("price")
    x = b.price.to_numpy(float)
    out = {"legal": bool(legal)}
    marks = [c for c in curve.columns if re.fullmatch(r"d_networth_own\d+", c)]
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
            both = (b[col].to_numpy(float) > 0) & (s[col].to_numpy(float) > 0)
            sure_at = (b[col].to_numpy(float) - 1.96 * se_b > 0) & (s[col].to_numpy(float) - 1.96 * se_s > 0)
            gains_at = set(x[both].tolist())  # a range's end is either a zero crossing or a price where both gain
            pounds = [(int(a) if a in gains_at else int(np.floor(a)) + 1, int(z) if z in gains_at else
                       int(np.ceil(z)) - 1) for a, z in deal]
            pounds = [(a, z) for a, z in pounds if a <= z]
            out["sampled_deal_prices"] = "; ".join(str(int(v)) for v in x[both]) if legal else ""
            out["confident_sampled_prices"] = "; ".join(str(int(v)) for v in x[sure_at]) if legal else ""
            out["whole_pound_ranges"] = "; ".join(f"{a}-{z}" for a, z in pounds)
            out["evidence"] = ("" if not deal else "no whole-pound price" if not pounds else
                               "confident at a sampled price" if legal and sure_at.any() else
                               "at a sampled price" if legal and both.any() else "between sampled prices only")
    at0 = curve[curve.price == curve.price.min()].set_index("player")
    out.update(p_win_base_seller=at0.loc[seller, "p_win_base"], p_win_base_buyer=at0.loc[buyer, "p_win_base"],
               p_win_buyer_if_free=at0.loc[buyer, "p_win_trade"])
    return out
