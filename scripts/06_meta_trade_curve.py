"""Re-value the Vine Street trade when every player at the table is the meta agent.

    python scripts/06_meta_trade_curve.py --mode standard
    python scripts/06_meta_trade_curve.py --mode championship

Same orange-squeeze positions and paired rollouts as 04_trade_curve.py, but the rest of the
game is played by that mode's meta agent (under that mode's rules and scoring). Championship rules forbid
trades heads-up, so the 2-player championship curve is a hypothetical intervention, marked legal=False.
As in 04, both baselines: the deed kept for good, and later trades allowed (the decision to accept today).
Under championship rules the curves also carry the change in outright wins (d_outright) beside the credit,
finishing points ÷ 28. Checkpointed per table size and baseline; a checkpoint is reused only if its inputs
match (run_config.fresh).

Outputs
  results/tables/meta_trade_curve_<mode>.csv, meta_trade_summary_<mode>.csv              kept for good
  results/tables/meta_trade_curve_<mode>_live.csv, meta_trade_summary_<mode>_live.csv    later trades allowed
  results/tables/later_deals_<mode>.json                                                 what the keep arm did
"""
import json
import time
from dataclasses import asdict

import pandas as pd

from meta_common import TAB, ckpt_dir, parse, rules_for
from run_config import code_hash, fresh, scaled, stamp, state_hash
from monopoly_meta.meta import to_spec
from monopoly_meta.rollout import trade_price_curve
from scenarios import orange_squeeze
from trade_summaries import vine_meta

N = scaled(2000)
VINE = 19
PRICES = list(range(0, 1201, 50))
OWN_TURNS = (5, 10, 20)  # net-worth horizons, in each player's own turns
BOOT = 1000           # whole-curve bootstrap resamples for the ends of the deal


def main():
    args = parse(__doc__)
    t = time.time()
    d = ckpt_dir(args.mode)
    metas = json.loads((TAB / f"meta_agents_{args.mode}.json").read_text())
    code = code_hash(__file__)
    for freeze, suffix in ((True, ""), (False, "_live")):
        for key, genome in sorted(metas.items()):
            n = int(key)
            path = d / f"trade_{n}p{suffix}.csv"
            rules = rules_for(args.mode, n)
            inputs = {"genome": genome, "rules": asdict(rules), "n": N, "seed0": 777, "prices": PRICES,
                      "scenario": "orange_squeeze", "state": state_hash(orange_squeeze(n)), "own_turns": OWN_TURNS,
                      "boot": BOOT, "code": code, "freeze": freeze}
            if n not in args.players or fresh(path, inputs):
                continue
            bots = [to_spec(genome, "meta")] * n
            c = trade_price_curve(orange_squeeze(n), bots, seller=1, buyer=0, squares=[VINE], prices=PRICES, n=N,
                                  seed0=777, rules=rules, hypothetical=True, own_turns=OWN_TURNS, boot=BOOT,
                                  freeze=freeze)
            c["n_players"] = n
            c.to_csv(path, index=False)
            extra = {"deal_bootstrap": c.attrs.get("deal_bootstrap", {}), "later_deals": c.attrs.get("later_deals")}
            path.with_name(path.stem + ".boot.json").write_text(json.dumps(extra))
            stamp(path, inputs)
            print(f"{'kept for good' if freeze else 'later trades allowed'}, {n} players: {time.time() - t:.0f}s",
                  flush=True)
        paths = sorted(d.glob(f"trade_*p{suffix}.csv"))
        curve = pd.concat([pd.read_csv(p) for p in paths])
        curve.to_csv(TAB / f"meta_trade_curve_{args.mode}{suffix}.csv", index=False)
        boot, later = {}, {}
        for p in paths:
            b = p.with_name(p.stem + ".boot.json")
            if b.exists():
                saved = json.loads(b.read_text())
                n = int(p.stem.split("_")[1][:-1])
                boot[(n,)] = saved.get("deal_bootstrap", saved)  # older files hold the bootstrap alone
                if saved.get("later_deals"):
                    later[f"{n}p"] = saved["later_deals"]
        summary = vine_meta(curve, args.mode, boot)
        summary.to_csv(TAB / f"meta_trade_summary_{args.mode}{suffix}.csv", index=False)
        print(summary.round(1).to_string(index=False))
        if later:
            (TAB / f"later_deals_{args.mode}.json").write_text(json.dumps(later, indent=1))


if __name__ == "__main__":
    main()
