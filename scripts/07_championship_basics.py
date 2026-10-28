"""Seat advantage, game length and strategy tweaks under championship rules (Speed Die etc.).

Same designs as 03_tournament.py but with engine.championship_rules: Speed Die, the
championship tweaks, and finishing-position points for games that reach the 150-round limit.
Win rates here are outright wins (time-limited games are reported separately as capped).

Outputs
  results/tables/championship_seat_advantage.csv
  results/tables/championship_strategy_variants.csv
"""
import time
from pathlib import Path

import pandas as pd

from monopoly_meta.engine import championship_rules
from monopoly_meta.tournament import run_games, wilson, win_rates

OUT = Path(__file__).resolve().parents[1] / "results" / "tables"
PLAYER_COUNTS = [2, 3, 4, 5, 6]
VARIANTS = ["aggressive", "cautious", "three_house", "hoarder", "jail_short", "jail_long",
            "take_chance", "no_trade", "hard_bargain", "random"]


def main(games=6000):
    t = time.time()
    seats, variants = [], []
    for n in PLAYER_COUNTS:
        rules = championship_rules(n)
        df = run_games(["balanced"] * n, games, seed0=70_000_000 + n, rules=rules, rotate=False)
        wr = win_rates(df, by="seat").assign(n_players=n, fair_share=1 / n,
                                             median_rounds=df.rounds.median(),
                                             p90_rounds=df.rounds.quantile(0.9), capped_share=df.capped.mean())
        seats.append(wr)
        for i, v in enumerate(VARIANTS):
            d = run_games([v] + ["balanced"] * (n - 1), games, seed0=80_000_000 * n + i * 100_000, rules=rules)
            k = int((d.winner_bot == v).sum())
            lo, hi = wilson(k, games)
            variants.append({"n_players": n, "variant": v, "games": games, "win_rate": k / games,
                             "relative": k / games * n, "rel_low": lo * n, "rel_high": hi * n,
                             "capped_share": d.capped.mean()})
        print(f"{n} players done at {time.time() - t:.0f}s")
    pd.concat(seats).to_csv(OUT / "championship_seat_advantage.csv", index=False)
    pd.DataFrame(variants).to_csv(OUT / "championship_strategy_variants.csv", index=False)


if __name__ == "__main__":
    main()
