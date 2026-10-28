"""What is every property worth to the player it completes a set for? Price curves for all 28.

    python scripts/10_property_trades.py                    # simple bots, 2-6 players
    python scripts/10_property_trades.py --bots meta 4      # official-rules meta agents, 4 players

For each ownable square, `scenarios.set_completion` builds the orange-squeeze position with
that square in its place: Player 1 owns it, Player 0 owns the rest of its group, everyone
else holds unrelated properties. The sale is then played out with paired rollouts at each
price, exactly as for Vine Street (04_trade_curve.py), but with 1,000 rollouts per price on a
coarser price grid. Vine Street itself reuses the 2,000-rollout curves from 04 / 06.
Checkpointed per square and table size.

Outputs
  results/tables/property_trades/<bots>/<n>p_<square>.csv     checkpoints
  results/tables/property_trade_curve_<bots>.csv              every curve
  results/tables/property_trade_summary_<bots>.csv            seller's floor and buyer's ceiling
"""
import argparse
import json
import time

import pandas as pd

from monopoly_meta import load_edition
from monopoly_meta.engine import championship_rules
from monopoly_meta.meta import to_spec, tournament_rules
from monopoly_meta.rollout import deal_summary, trade_price_curve
from scenarios import set_completion

from run_config import TABLES as TAB, scaled  # noqa: E402

N = scaled(1000)
PRICES = [0, 25, 50, 75, 100, 150, 200, 250, 300, 400, 500, 600, 700, 800, 1000, 1200]
VINE = 19


MODE = {"meta": "standard", "championship": "championship"}  # --bots value: which meta agents play on


def players_for(bots: str, n: int):
    """Bot specs and rules for the rest of the game."""
    if bots == "simple":
        return ["balanced"] * n, None
    metas = json.loads((TAB / f"meta_agents_{MODE[bots]}.json").read_text())
    rules = championship_rules(n) if bots == "championship" else tournament_rules(n)
    return [to_spec(metas[str(n)], "meta")] * n, rules


def vine_curve(bots: str) -> pd.DataFrame:
    """The existing 2,000-rollout Vine Street curves, in this script's format."""
    if bots == "simple":
        c = pd.read_csv(TAB / "trade_curve_orange_squeeze.csv").query("buyer == 0").drop(columns="buyer")
    else:
        c = pd.read_csv(TAB / f"meta_trade_curve_{MODE[bots]}.csv")
    return c.assign(square=VINE)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bots", choices=["simple", "meta", "championship"], default="simple")
    ap.add_argument("players", nargs="*", type=int, default=[2, 3, 4, 5, 6])
    args = ap.parse_args()
    ed = load_edition()
    d = TAB / "property_trades" / args.bots
    d.mkdir(parents=True, exist_ok=True)
    squares = [sq for sq in range(len(ed.names)) if ed.is_ownable(sq) and sq != VINE]
    t = time.time()
    for n in args.players:
        bots, rules = players_for(args.bots, n)
        for sq in squares:
            path = d / f"{n}p_{sq:02d}.csv"
            if path.exists():
                continue
            c = trade_price_curve(set_completion(ed.names[sq], n), bots, seller=1, buyer=0, squares=[sq],
                                  prices=PRICES, n=N, seed0=777, rules=rules)
            c.assign(n_players=n, square=sq).to_csv(path, index=False)
            print(f"{n}p {ed.names[sq]:24s} {time.time() - t:6.0f}s", flush=True)
    curves = [pd.read_csv(p) for p in sorted(d.glob("*p_*.csv"))] + [vine_curve(args.bots)]
    curve = pd.concat(curves)
    curve = curve[curve.n_players.isin(sorted({int(p.name.split("p_")[0]) for p in d.glob("*p_*.csv")}))]
    curve.to_csv(TAB / f"property_trade_curve_{args.bots}.csv", index=False)
    rows = [{"n_players": n, "square": sq, "name": ed.names[sq], **deal_summary(c, seller=1, buyer=0)}
            for (n, sq), c in curve.groupby(["n_players", "square"])]
    summary = pd.DataFrame(rows)
    summary.to_csv(TAB / f"property_trade_summary_{args.bots}.csv", index=False)
    print(summary.round(0).to_string(index=False))


if __name__ == "__main__":
    main()
