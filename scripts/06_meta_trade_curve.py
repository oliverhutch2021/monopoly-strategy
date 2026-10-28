"""Re-value the Vine Street trade when every player at the table is the meta agent.

    python scripts/06_meta_trade_curve.py --mode standard
    python scripts/06_meta_trade_curve.py --mode championship

Same orange-squeeze positions and paired rollouts as 04_trade_curve.py, but the rest of the
game is played by that mode's meta agent (under that mode's rules and scoring).
Checkpointed per table size.

Outputs
  results/tables/meta_trade_curve_<mode>.csv
  results/tables/meta_trade_summary_<mode>.csv
"""
import json
import time

import pandas as pd

from meta_common import TAB, ckpt_dir, parse, rules_for
from run_config import scaled
from monopoly_meta.meta import to_spec
from monopoly_meta.rollout import deal_summary, trade_price_curve
from scenarios import orange_squeeze

N = scaled(2000)
VINE = 19


def main():
    args = parse(__doc__)
    t = time.time()
    d = ckpt_dir(args.mode)
    metas = json.loads((TAB / f"meta_agents_{args.mode}.json").read_text())
    for key, genome in sorted(metas.items()):
        n = int(key)
        path = d / f"trade_{n}p.csv"
        if n not in args.players or path.exists():
            continue
        bots = [to_spec(genome, "meta")] * n
        state = orange_squeeze(n)
        c = trade_price_curve(state, bots, seller=1, buyer=0, squares=[VINE],
                              prices=range(0, 1201, 50), n=N, seed0=777, rules=rules_for(args.mode, n))
        c["n_players"] = n
        c.to_csv(path, index=False)
        print(f"{n} players: {time.time() - t:.0f}s")
    curve = pd.concat([pd.read_csv(p) for p in sorted(d.glob("trade_*p.csv"))])
    curve.to_csv(TAB / f"meta_trade_curve_{args.mode}.csv", index=False)
    rows = [{"n_players": n, **deal_summary(c, seller=1, buyer=0)} for n, c in curve.groupby("n_players")]
    pd.DataFrame(rows).to_csv(TAB / f"meta_trade_summary_{args.mode}.csv", index=False)
    print(pd.DataFrame(rows).round(1).to_string(index=False))


if __name__ == "__main__":
    main()
