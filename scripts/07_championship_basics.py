"""Seat advantage, game length and strategy tweaks under championship rules (Speed Die etc.).

Same designs as 03_tournament.py but with engine.championship_rules: Speed Die, the
championship tweaks, and finishing-position points for games that reach the 150-round limit.
Win rates here are outright wins, as a share of the decided games (so 1/n is the fair share). A game that reaches the
limit has no outright winner; championship rules rank it by net worth, and its richest player is counted apart
(limit_wins) and included in game_relative / game_win_rate (finishing on top by either route, out of all games).

Outputs
  results/tables/championship_seat_advantage.csv
  results/tables/championship_strategy_variants.csv
"""
import time

import pandas as pd

from monopoly_meta.engine import championship_rules
from monopoly_meta.tournament import outcome_counts, outright_rate, run_games, win_rates

from run_config import TABLES as OUT, scaled  # noqa: E402
PLAYER_COUNTS = [2, 3, 4, 5, 6]
VARIANTS = ["aggressive", "cautious", "three_house", "hoarder", "jail_short", "jail_long",
            "take_chance", "no_trade", "hard_bargain", "random"]


def main(games=scaled(6000)):
    t = time.time()
    seats, variants = [], []
    for n in PLAYER_COUNTS:
        rules = championship_rules(n)
        df = run_games(["balanced"] * n, games, seed0=70_000_000 + n, rules=rules, rotate=False)
        wr = win_rates(df, by="seat").assign(n_players=n, fair_share=1 / n,
                                             median_rounds=df.rounds.median(), median_turns=df.turns.median(),
                                             p90_rounds=df.rounds.quantile(0.9), capped_share=df.capped.mean())
        seats.append(wr)
        for i, v in enumerate(VARIANTS):
            d = run_games([v] + ["balanced"] * (n - 1), games, seed0=80_000_000 * n + i * 100_000, rules=rules)
            k, k_limit = outcome_counts(d, "winner_bot", v)
            decided = games - int(d.capped.sum())
            rate, lo, hi = outright_rate(k, decided)
            variants.append({"n_players": n, "variant": v, "games": games, "decided": decided, "win_rate": rate,
                             "relative": rate * n, "rel_low": lo * n, "rel_high": hi * n,
                             "limit_wins": k_limit, "game_relative": (k + k_limit) / games * n,
                             "capped_share": d.capped.mean()})
        print(f"{n} players done at {time.time() - t:.0f}s")
    pd.concat(seats).to_csv(OUT / "championship_seat_advantage.csv", index=False)
    pd.DataFrame(variants).to_csv(OUT / "championship_strategy_variants.csv", index=False)


if __name__ == "__main__":
    main()
