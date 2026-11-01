"""Trade price curves from rollouts with common random numbers, at 2-6 players.

Scenario 'orange squeeze' (scripts/scenarios.py): ten rounds in, Player 0 holds Bow Street and
Marlborough Street; Player 1 holds Vine Street; every other player is a bystander with four
unrelated properties. What is Vine Street worth, to whom, and how does that change with the
number of players at the table?

Two baselines, two questions (rollout.trade_price_curve):
  kept for good           sell now vs never trade it: the deed's own value to each side (the deal zone)
  later trades allowed    sell now vs carry on as normal, when the bots may still trade it later: the comparison
                          behind accepting or declining an offer today; later_deals says what the keep arm did
The curves also record the change in net worth after 5, 10 and 20 of each player's own turns, the change in
outright wins, and each deal's ends get a whole-curve paired bootstrap (rollout.deal_bootstrap).

Outputs
  results/tables/trade_curve_orange_squeeze.csv        kept for good: every price x player x player count
  results/tables/trade_curve_summary.csv               its deal ranges (trade_summaries.py), with bootstrap intervals
  results/tables/trade_curve_orange_squeeze_live.csv   later trades allowed
  results/tables/trade_curve_summary_live.csv
  results/tables/later_deals_simple.json               what the keep arm did, per table size and buyer
"""
import json
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
OWN_TURNS = (5, 10, 20)  # net-worth horizons, in each player's own turns
BOOT = 1000           # whole-curve bootstrap resamples for the ends of each deal


def main():
    t = time.time()
    for freeze, suffix in ((True, ""), (False, "_live")):
        curves, boot, later = [], {}, {}
        for n in PLAYER_COUNTS:
            state = orange_squeeze(n)
            bots = ["balanced"] * n
            # buyer 0 completes the orange set; buyer 2 (a bystander, if any) does not
            deals = [(0, range(0, 1201, 50))] + ([(2, range(0, 601, 50))] if n >= 3 else [])
            for buyer, prices in deals:
                c = trade_price_curve(state, bots, seller=1, buyer=buyer, squares=[VINE], prices=prices, n=N,
                                      seed0=777, own_turns=OWN_TURNS, boot=BOOT, freeze=freeze)
                boot[(n, buyer)] = c.attrs.get("deal_bootstrap", {})
                if not freeze:
                    later[f"{n}p_buyer{buyer}"] = c.attrs["later_deals"]
                c["buyer"] = buyer
                c["n_players"] = n
                curves.append(c)
                print(f"{'kept for good' if freeze else 'later trades allowed'}, {n} players, buyer {buyer}: "
                      f"{time.time() - t:.0f}s", flush=True)
        curve = pd.concat(curves)
        curve.to_csv(OUT / f"trade_curve_orange_squeeze{suffix}.csv", index=False)
        summary = vine_simple(curve, boot)
        summary.to_csv(OUT / f"trade_curve_summary{suffix}.csv", index=False)
        print(summary.round(2).to_string(index=False))
        if later:
            (OUT / "later_deals_simple.json").write_text(json.dumps(later, indent=1))


if __name__ == "__main__":
    main()
