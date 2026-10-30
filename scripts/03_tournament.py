"""Monte Carlo tournaments at every player count from 2 to 6 (the championship maximum).

Win rates are outright wins, as a share of the decided games (so 1/n is the fair share). A game stopped by the turn
limit (4,000 player-turns; rare under these rules) has no outright winner: its richest survivor is counted apart
(limit_wins), and game_relative is the share of all games finished on top by either route, relative to 1/n.

Outputs
  results/tables/seat_advantage.csv     win rate by seat (identical bots, no rotation)
  results/tables/strategy_variants.csv  one variant vs (n-1) 'balanced' bots, seats rotated
  results/tables/house_rules.csv        game length / capped share / seat-1 edge under rule variants
  results/tables/game_lengths.csv       per-game lengths under the official rules (balanced bots)
"""
import time

import pandas as pd

from monopoly_meta.engine import Rules
from monopoly_meta.tournament import outcome_counts, outright_rate, run_games, win_rates

from run_config import TABLES as OUT, scaled  # noqa: E402
OUT.mkdir(parents=True, exist_ok=True)

PLAYER_COUNTS = [2, 3, 4, 5, 6]
VARIANTS = ["aggressive", "cautious", "three_house", "hoarder", "jail_short", "jail_long",
            "take_chance", "no_trade", "hard_bargain", "random"]


def seat_advantage(games=scaled(10000)):
    rows, lengths = [], []
    for n in PLAYER_COUNTS:
        df = run_games(["balanced"] * n, games, seed0=1_000_000 * n, rotate=False)
        wr = win_rates(df, by="seat")
        wr["n_players"] = n
        wr["fair_share"] = 1 / n
        rows.append(wr)
        # per-game lengths: the first 10,000 games per table size are plenty, and keep the file small in deep runs
        lengths.append(df[["seed", "turns", "rounds", "capped", "winner_seat"]].head(10_000).assign(n_players=n))
        print(f"{n} players: seat-1 win rate {wr.win_rate.iloc[0]:.3f} vs fair {1 / n:.3f}, "
              f"median {df.rounds.median():.1f} rounds")
    pd.concat(rows).to_csv(OUT / "seat_advantage.csv", index=False)
    pd.concat(lengths).to_csv(OUT / "game_lengths.csv", index=False)


def strategy_variants(games=scaled(10000)):
    rows = []
    for n in PLAYER_COUNTS:
        fair = 1 / n
        for i, v in enumerate(VARIANTS):
            lineup = [v] + ["balanced"] * (n - 1)
            df = run_games(lineup, games, seed0=10_000_000 * n + i * 100_000)
            k, k_limit = outcome_counts(df, "winner_bot", v)
            decided = games - int(df.capped.sum())
            rate, lo, hi = outright_rate(k, decided)
            rows.append({"n_players": n, "variant": v, "games": games, "wins": k, "limit_wins": k_limit,
                         "decided": decided, "win_rate": rate, "ci_low": lo, "ci_high": hi, "fair_share": fair,
                         "edge_pp": 100 * (rate - fair),
                         "relative": rate / fair, "rel_low": lo / fair, "rel_high": hi / fair,
                         "game_relative": (k + k_limit) / games / fair,
                         "median_rounds": df.rounds.median(), "median_turns": df.turns.median(),
                         "capped_share": df.capped.mean()})
        best = max((r for r in rows if r["n_players"] == n), key=lambda r: r["relative"])
        print(f"{n} players: best variant {best['variant']} ({best['relative']:.2f}x fair share)")
    pd.DataFrame(rows).to_csv(OUT / "strategy_variants.csv", index=False)


def house_rules(games=scaled(6000)):
    variants = {
        "official": Rules(),
        "free_parking_jackpot": Rules(free_parking_jackpot=True),
        "no_auctions": Rules(auctions=False),
    }
    rows = []
    for n in PLAYER_COUNTS:
        for i, (name, rules) in enumerate(variants.items()):
            df = run_games(["balanced"] * n, games, seed0=50_000_000 * n + i * 100_000,
                           rules=rules, rotate=False)
            k, _ = outcome_counts(df, "winner_seat", 0)
            rate, lo, hi = outright_rate(k, games - int(df.capped.sum()))
            rows.append({"n_players": n, "rules": name, "games": games, "median_turns": df.turns.median(),
                         "median_rounds": df.rounds.median(), "mean_rounds": df.rounds.mean(),
                         "p90_rounds": df.rounds.quantile(0.9), "capped_share": df.capped.mean(),
                         "seat1_win_rate": rate, "seat1_ci_low": lo, "seat1_ci_high": hi,
                         "fair_share": 1 / n})
        print(f"{n} players: house rules done")
    pd.DataFrame(rows).to_csv(OUT / "house_rules.csv", index=False)


if __name__ == "__main__":
    t = time.time()
    seat_advantage()
    strategy_variants()
    house_rules()
    print(f"done in {time.time() - t:.0f}s")
