"""Trade price curves from rollouts with common random numbers, at 2-6 players.

Scenario 'orange squeeze' (scripts/scenarios.py): ten rounds in, Player 0 holds Bow Street and
Marlborough Street; Player 1 holds Vine Street; every other player is a bystander with four
unrelated properties. What is Vine Street worth, to whom, and how does that change with the
number of players at the table?

The curves also record the change in net worth 5, 10 and 20 rounds later (the same number of turns for each
player at every table size), and each deal's ends get a whole-curve paired bootstrap (rollout.deal_bootstrap).

Outputs
  results/tables/trade_curve_orange_squeeze.csv   every price x player x player count
  results/tables/trade_curve_summary.csv          deal ranges (trade_summaries.py), with bootstrap intervals
"""
import time

import pandas as pd

from monopoly_meta.rollout import trade_price_curve
from scenarios import orange_squeeze
from trade_summaries import vine_simple

from run_config import TABLES as OUT, scaled  # noqa: E402
OUT.mkdir(parents=True, exist_ok=True)
N = scaled(2000)
VINE = 19
PLAYER_COUNTS = [2, 3, 4, 5, 6]
ROUNDS = (5, 10, 20)  # net-worth horizons, in rounds
BOOT = 1000           # whole-curve bootstrap resamples for the ends of each deal


def main():
    t = time.time()
    curves, boot = [], {}
    for n in PLAYER_COUNTS:
        state = orange_squeeze(n)
        bots = ["balanced"] * n
        # buyer 0 completes the orange set; buyer 2 (a bystander, if any) does not
        deals = [(0, range(0, 1201, 50))] + ([(2, range(0, 601, 50))] if n >= 3 else [])
        for buyer, prices in deals:
            c = trade_price_curve(state, bots, seller=1, buyer=buyer, squares=[VINE],
                                  prices=prices, n=N, seed0=777, networth_rounds=ROUNDS, boot=BOOT)
            boot[(n, buyer)] = c.attrs.get("deal_bootstrap", {})
            c["buyer"] = buyer
            c["n_players"] = n
            curves.append(c)
            print(f"{n} players, buyer {buyer}: {time.time() - t:.0f}s")
    curve = pd.concat(curves)
    curve.to_csv(OUT / "trade_curve_orange_squeeze.csv", index=False)

    summary = vine_simple(curve, boot)
    summary.to_csv(OUT / "trade_curve_summary.csv", index=False)
    print(summary.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
