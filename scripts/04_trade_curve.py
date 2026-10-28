"""Trade price curves from rollouts with common random numbers, at 2-6 players.

Scenario 'orange squeeze' (scripts/scenarios.py): ten rounds in, Player 0 holds Bow Street and
Marlborough Street; Player 1 holds Vine Street; every other player is a bystander with four
unrelated properties. What is Vine Street worth, to whom, and how does that change with the
number of players at the table?

Outputs
  results/tables/trade_curve_orange_squeeze.csv   every price x player x player count
  results/tables/trade_curve_summary.csv          indifference prices and deal zones
"""
import time
from pathlib import Path

import pandas as pd

from monopoly_meta.rollout import deal_summary, trade_price_curve
from scenarios import orange_squeeze

OUT = Path(__file__).resolve().parents[1] / "results" / "tables"
OUT.mkdir(parents=True, exist_ok=True)
N = 2000
VINE = 19
PLAYER_COUNTS = [2, 3, 4, 5, 6]


def main():
    t = time.time()
    curves = []
    for n in PLAYER_COUNTS:
        state = orange_squeeze(n)
        bots = ["balanced"] * n
        # buyer 0 completes the orange set; buyer 2 (a bystander, if any) does not
        deals = [(0, range(0, 1201, 50))] + ([(2, range(0, 601, 50))] if n >= 3 else [])
        for buyer, prices in deals:
            c = trade_price_curve(state, bots, seller=1, buyer=buyer, squares=[VINE],
                                  prices=prices, n=N, seed0=777)
            c["buyer"] = buyer
            c["n_players"] = n
            curves.append(c)
            print(f"{n} players, buyer {buyer}: {time.time() - t:.0f}s")
    curve = pd.concat(curves)
    curve.to_csv(OUT / "trade_curve_orange_squeeze.csv", index=False)

    rows = [{"n_players": n, "buyer": buyer, **deal_summary(c, seller=1, buyer=buyer)}
            for (n, buyer), c in curve.groupby(["n_players", "buyer"])]
    summary = pd.DataFrame(rows)
    summary.to_csv(OUT / "trade_curve_summary.csv", index=False)
    print(summary.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
