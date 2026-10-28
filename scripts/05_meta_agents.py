"""Evolve a first-pass meta agent for every table size by self-play (then run 05b to harden it).

    python scripts/05_meta_agents.py --mode standard        # official rules
    python scripts/05_meta_agents.py --mode championship    # Speed Die + championship scoring

Candidates play against the current population plus a hall of fame of past champions; the
final population is re-scored on fresh games and the best becomes the first-pass meta agent.
Each table size is checkpointed to results/tables/meta_<mode>/<n>p.json.
"""
import json
import time

from meta_common import MODES, ckpt_dir, parse, rules_for
from monopoly_meta.meta import BALANCED, evaluate, evolve


def main():
    args = parse(__doc__)
    d = ckpt_dir(args.mode)
    s0 = MODES[args.mode]["seed"]
    for n in args.players:
        path = d / f"{n}p.json"
        if path.exists():
            print(f"{n} players: first pass already done")
            continue
        t = time.time()
        rules = rules_for(args.mode, n)
        aggressive = {**BALANCED, "reserve": 0.0, "build_reserve": 0.0, "bid_frac": 1.2}
        res = evolve(n, generations=12, pop_size=8, games=700, seed=s0 + 100 + n,
                     init=[BALANCED, aggressive], rules=rules)
        pool = res.population + res.hall_of_fame
        fresh = evaluate(res.population, pool, n, 3000, seed=s0 + 9_000 + n, rules=rules)
        meta = res.population[int(fresh.argmax())]
        path.write_text(json.dumps({
            "n_players": n, "mode": args.mode, "meta": meta, "challenger": None, "refined": False,
            "history": [{**h, "n_players": n} for h in res.history], "seconds": time.time() - t,
        }, indent=2))
        print(f"{n} players first pass done in {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
