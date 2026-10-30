"""Monte Carlo tournaments between bots, with seat rotation and confidence intervals."""
from __future__ import annotations

import math
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict

import pandas as pd

from . import watch
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
    if watch.folder():  # the live viewer: offer one of these games for replay
        def describe(seed):
            shift = seed % len(lineup) if rotate else 0
            return {"lineup": lineup[shift:] + lineup[:shift], "seat": None, "seed": seed}
        watch.sample(seeds, rules, describe)
    t0 = watch.started(n_games)
    if workers == 1:
        rows = [r for a in args for r in _play_chunk(a)]
    else:
        with ProcessPoolExecutor(workers) as ex:
            rows = [r for chunk in ex.map(_play_chunk, args) for r in chunk]
    watch.finished(n_games, t0)
    return pd.DataFrame(rows).sort_values("seed").reset_index(drop=True)


def outcome_counts(df: pd.DataFrame, column: str, value) -> tuple[int, int]:
    """(outright wins, time-limit wins) of `value` in a run_games table. A game stopped by the turn limit has no
    outright winner; its `winner_*` is the richest survivor (Game.result), which championship rules call the winner
    of the table. The two are counted apart so that each analysis can say which outcome it reports."""
    hit = df[column] == value
    return int((hit & ~df.capped).sum()), int((hit & df.capped).sum())


def outright_rate(k: int, decided: int) -> tuple[float, float, float]:
    """Share of the decided games (those not stopped by the turn limit) won outright, with its Wilson interval.
    Its fair share is 1/n whatever the number of stopped games, so it compares directly with 1/n."""
    lo, hi = wilson(k, decided)
    return (k / decided if decided else math.nan), lo, hi


def win_rates(df: pd.DataFrame, by: str = "winner_bot", lineup: list[str] | None = None) -> pd.DataFrame:
    """Outright win rate per bot (or per seat), with 95% Wilson intervals: the share of the decided games won
    outright, so 1/n is its fair share. Beside it, so that no outcome is hidden: outright_share, the share of all
    games won outright; limit_share, the share of all games stopped by the turn limit with this bot (or seat) on
    top, the richest survivor (limit_wins); and game_win_rate, the two together.

    For bots that appear k times in the lineup the rate is per *bot instance*,
    so it is directly comparable with the 1/n 'fair share'.
    """
    n = len(df)
    decided = n - int(df.capped.sum())
    out = []
    if by == "winner_bot":
        lineup = [bot_label(x) for x in lineup] if lineup else \
            [df[c].iloc[0] for c in df.columns if c.startswith("seat")]
        for bot in sorted(set(lineup)):
            copies = lineup.count(bot)
            k, k_limit = outcome_counts(df, "winner_bot", bot)
            rate, lo, hi = outright_rate(k, decided)
            out.append({"bot": bot, "copies": copies, "wins": k, "limit_wins": k_limit, "games": n,
                        "decided": decided, "win_rate": rate / copies, "ci_low": lo / copies,
                        "ci_high": hi / copies, "outright_share": k / (n * copies),
                        "limit_share": k_limit / (n * copies), "game_win_rate": (k + k_limit) / (n * copies)})
    else:
        for seat in sorted(df.winner_seat.unique()):
            k, k_limit = outcome_counts(df, "winner_seat", seat)
            rate, lo, hi = outright_rate(k, decided)
            out.append({"seat": seat, "wins": k, "limit_wins": k_limit, "games": n, "decided": decided,
                        "win_rate": rate, "ci_low": lo, "ci_high": hi, "outright_share": k / n,
                        "limit_share": k_limit / n, "game_win_rate": (k + k_limit) / n})
    return pd.DataFrame(out)
