"""Why does a meta agent sometimes lose to the simple bot? Swap its settings back one group at a time.

    python scripts/09_meta_vs_simple.py --mode standard

Every candidate takes the same seat in the same games against a table of simple bots (common
random numbers): the meta agent, the simple bot itself, and the meta agent with one group of
settings copied from the simple bot. Each is reported relative to the simple bot in that seat
(1.0 = level with the simple bot), with a 95% paired bootstrap interval over games.

Output: results/tables/meta_vs_simple_<mode>.csv
"""
import json
import time

import pandas as pd
from meta_common import MODES, TAB, parse, rules_for
from run_config import scaled

from monopoly_meta.meta import BALANCED, GROUPS, evaluate, paired_ratio

GAMES = scaled(3000)
SWAPS = {
    "cash buffers": ["reserve", "build_reserve"],
    "auction limit": ["bid_frac"],
    "set and blocking premiums": ["set_bonus", "block_bonus"],
    "trade prices": ["offer_mult", "ask_mult"],
    "offer for a set piece": ["offer_mult"],
    "asking price for a set piece": ["ask_mult"],
    "trading on or off": ["trades", "accept_trades"],
    "building caps": ["build_cap", "max_level"],
    "jail and Chance choices": ["jail", "take_chance"],
    "all buying weights": [f"w_{g}" for g in GROUPS],
    **{f"buying weight, {g.replace('_', ' ')}": [f"w_{g}"] for g in GROUPS},
}


def main():
    args = parse(__doc__)
    metas = json.loads((TAB / f"meta_agents_{args.mode}.json").read_text())
    rows = []
    t = time.time()
    for n in args.players:
        meta = {k: v for k, v in metas[str(n)].items() if k != "name"}
        named = {"meta agent": meta, "simple bot": dict(BALANCED)}
        for label, keys in SWAPS.items():
            variant = {**meta, **{k: BALANCED[k] for k in keys}}
            if variant != meta:  # skip swaps that change nothing
                named[f"meta agent, simple bot's {label}"] = variant
        names, genomes = zip(*named.items())
        evaluate(list(genomes), [BALANCED], n, GAMES, seed=MODES[args.mode]["seed"] + 12_000 + n,
                 rules=rules_for(args.mode, n), fixed_opponents=True)
        games = evaluate.last_games
        base = games[names.index("simple bot")]
        for i, name in enumerate(names):
            rel, lo, hi = paired_ratio(games[i], base, seed=i)
            rows.append({"n_players": n, "candidate": name, "relative": rel, "rel_low": lo, "rel_high": hi,
                         "raw": float(games[i].mean()), "games": GAMES})
        print(f"{n} players done at {time.time() - t:.0f}s", flush=True)
        pd.DataFrame(rows).to_csv(TAB / f"meta_vs_simple_{args.mode}.csv", index=False)


if __name__ == "__main__":
    main()
