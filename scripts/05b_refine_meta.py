"""Harden the meta agents with best-response iteration, then validate and ablate them.

    python scripts/05b_refine_meta.py --mode standard
    python scripts/05b_refine_meta.py --mode championship
    python scripts/05b_refine_meta.py --mode standard --revalidate   # redo validation only

For each table size a fresh challenger is trained against a table of meta agents. If it does
5% or more better than the meta agent does at its own table, the challenger joins the opponent
pool permanently, evolution continues and a new meta agent is picked (up to four rounds).

Validation then plays, on the *same* 4,000 games (same seeds, seats and opponents):
the meta agent itself (the placebo), the best challenger, the simple bot and one-change
ablations of the meta agent, each against a table of meta agents. Every result is reported
relative to the placebo, with a 95% bootstrap interval over games, so luck cancels out.
A second set of games compares the meta agent with the simple bot at a table of simple bots.
"""
import json
import sys
import time

import numpy as np

from meta_common import EVAL_GAMES, MODES, ablations, aggregate, ckpt_dir, parse, rules_for
from monopoly_meta.meta import BALANCED, evaluate, paired_ratio, refine


def validate(mode: str, n: int, meta: dict, challenger: dict) -> tuple[list, list, float]:
    s0 = MODES[mode]["seed"]
    rules = rules_for(mode, n)
    named = {"meta agent (placebo)": meta, "best challenger": challenger, **ablations(meta)}
    names, genomes = zip(*named.items())
    evaluate(list(genomes), [meta], n, EVAL_GAMES, seed=s0 + 9_400 + n, rules=rules, fixed_opponents=True)
    games, capped = evaluate.last_games, evaluate.last_capped_share
    base = games[0]
    own = float(base.mean())
    rows = []
    for i, name in enumerate(names):
        rel, lo, hi = paired_ratio(games[i], base, seed=i)
        rows.append({"n_players": n, "name": name, "raw": float(games[i].mean()), "relative": rel,
                     "rel_low": lo, "rel_high": hi, "games": EVAL_GAMES, "capped_share": float(capped[i]),
                     "no_effect": bool(np.array_equal(games[i], base))})  # the change never altered a game
    by_name = {r["name"]: r for r in rows}
    val = [
        {**by_name["best challenger"], "name": "best challenger vs meta agents"},
        {**by_name["simple baseline bot"], "name": "baseline bot vs meta agents"},
        {**by_name["meta agent (placebo)"], "name": "meta agent at a table of meta agents",
         "relative": own, "rel_low": float("nan"), "rel_high": float("nan")},
    ]
    abl = [r for r in rows if r["name"] != "best challenger"]

    # the meta agent at a table of simple bots, paired with a simple bot in the same seat
    evaluate([meta, BALANCED], [BALANCED], n, EVAL_GAMES, seed=s0 + 9_100 + n, rules=rules, fixed_opponents=True)
    g = evaluate.last_games
    rel, lo, hi = paired_ratio(g[0], g[1], seed=99)
    val.append({"n_players": n, "name": "meta agent vs baseline bots", "raw": float(g[0].mean()),
                "relative": rel, "rel_low": lo, "rel_high": hi, "games": EVAL_GAMES,
                "capped_share": float(evaluate.last_capped_share[0])})
    return val, abl, own


def harden(mode: str, n: int, revalidate: bool = False) -> None:
    d = ckpt_dir(mode)
    path = d / f"{n}p.json"
    rec = json.loads(path.read_text())
    t = time.time()
    if rec.get("refined") and not revalidate:
        print(f"{n} players: already hardened")
        return
    if not rec.get("refined"):
        meta, challenger, rounds = refine(rec["meta"], rec.get("challenger"), n, rules=rules_for(mode, n),
                                          rounds=4, threshold=1.05, seed=MODES[mode]["seed"] + 300 + n,
                                          ckpt=d / f"refine_{n}p.json")
        rec.update({"meta": meta, "challenger": challenger, "refinement": rounds})
    val, abl, own = validate(mode, n, rec["meta"], rec["challenger"])
    rec.update({"validation": val, "ablations": abl, "self_play_credit": own, "refined": True,
                "validated_paired": True, "refine_seconds": rec.get("refine_seconds", 0) + time.time() - t})
    path.write_text(json.dumps(rec, indent=2))
    print(f"{n} players {'revalidated' if revalidate else 'hardened'} in {time.time() - t:.0f}s")


def main():
    revalidate = "--revalidate" in sys.argv
    if revalidate:
        sys.argv.remove("--revalidate")
    args = parse(__doc__)
    for n in args.players:
        if (ckpt_dir(args.mode) / f"{n}p.json").exists():
            harden(args.mode, n, revalidate)
            aggregate(args.mode)


if __name__ == "__main__":
    main()
