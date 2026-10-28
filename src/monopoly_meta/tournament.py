"""Monte Carlo tournaments between bots, with seat rotation and confidence intervals."""
from __future__ import annotations

import math
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict

import pandas as pd

from .engine import Game, Rules
from .policies import bot_label, make_bot


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _play_chunk(args):
    lineup, seeds, rules_dict, rotate = args
    rules = Rules(**rules_dict)
    rows = []
    n = len(lineup)
    for seed in seeds:
        shift = seed % n if rotate else 0
        seated = lineup[shift:] + lineup[:shift]  # seat i gets seated[i]
        bots = [make_bot(kind) for kind in seated]
        r = Game(bots, seed=seed, rules=rules).play()
        rows.append({
            "seed": seed, "winner_seat": r.winner, "winner_bot": bot_label(seated[r.winner]),
            "turns": r.turns, "rounds": r.turns / n, "capped": r.capped,
            **{f"seat{i}": bot_label(k) for i, k in enumerate(seated)},
        })
    return rows


def run_games(lineup: list, n_games: int, seed0: int = 0, rules: Rules | None = None,
              rotate: bool = True, workers: int | None = None) -> pd.DataFrame:
    """Play n_games with the given bot lineup (rotated through the seats if rotate=True).

    Lineup entries are preset names or dicts of HeuristicBot parameters (with a "name").
    """
    rules = rules or Rules()
    workers = workers or os.cpu_count() or 1
    seeds = list(range(seed0, seed0 + n_games))
    chunks = [seeds[i::workers] for i in range(workers)]
    args = [(lineup, c, asdict(rules), rotate) for c in chunks if c]
    if workers == 1:
        rows = [r for a in args for r in _play_chunk(a)]
    else:
        with ProcessPoolExecutor(workers) as ex:
            rows = [r for chunk in ex.map(_play_chunk, args) for r in chunk]
    return pd.DataFrame(rows).sort_values("seed").reset_index(drop=True)


def win_rates(df: pd.DataFrame, by: str = "winner_bot", lineup: list[str] | None = None) -> pd.DataFrame:
    """Win rate per bot (or per seat) with 95% Wilson intervals.

    For bots that appear k times in the lineup the rate is per *bot instance*,
    so it is directly comparable with the 1/n 'fair share'.
    """
    n = len(df)
    out = []
    if by == "winner_bot":
        lineup = [bot_label(x) for x in lineup] if lineup else \
            [df[c].iloc[0] for c in df.columns if c.startswith("seat")]
        for bot in sorted(set(lineup)):
            copies = lineup.count(bot)
            k = int((df.winner_bot == bot).sum())
            lo, hi = wilson(k, n * copies) if copies == 1 else _scaled(k, n, copies)
            out.append({"bot": bot, "copies": copies, "wins": k, "games": n,
                        "win_rate": k / (n * copies), "ci_low": lo, "ci_high": hi})
    else:
        for seat in sorted(df.winner_seat.unique()):
            k = int((df.winner_seat == seat).sum())
            lo, hi = wilson(k, n)
            out.append({"seat": seat, "wins": k, "games": n, "win_rate": k / n, "ci_low": lo, "ci_high": hi})
    return pd.DataFrame(out)


def _scaled(k: int, n: int, copies: int) -> tuple[float, float]:
    lo, hi = wilson(k, n)  # share of games won by any copy, then per copy
    return lo / copies, hi / copies
