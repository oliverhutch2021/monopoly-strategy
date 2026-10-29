"""Unconventional strategies (v0.4): can moves people rarely make beat the meta agents?

    python scripts/13_unconventional.py --mode standard [players ...]
    python scripts/13_unconventional.py --summary

For each table size, three stages, each checkpointed so a stopped run resumes where it was:

1. Tactics arm. The best-response search of scripts/12_exploitability.py (the control arm: the same
   starts, budget, seeds and evaluation games), except that variation can switch the tactic genes on
   (monopoly_meta.unconventional.TACTICS). Its challenger is measured on the very games the control's
   was, so the two compare head to head: do the new moves find a bigger exploit than the old ones?
2. MAP-Elites. A quality-diversity search for strong strategies of many different kinds against a
   table of meta agents (monopoly_meta.unconventional.search).
3. Checks. The strongest finds, overall and for each tactic, measured again on fresh games against
   the meta agent; then a league of them, the meta agent and the simple bot plays every pairing.

Outputs, under <results>/tables/unconventional/:
  tactics_<mode>.csv          the tactics arm against the meta agent and the control arm, per table size
  finalists_<mode>.csv        the re-measured finds, per table size
  league_<mode>_<n>p.csv      invasion matrix: one of the row's strategy at a table of the column's
  search_<mode>_<n>p.json     the MAP-Elites archive and its history (also its checkpoint)
  <mode>_<n>p.json            everything for that table size, read by --summary
  summary.md, summary.csv     what was found, in words and as a table (--summary)
MM_SMOKE=1 shrinks every budget for a quick end-to-end test.
"""
import argparse
import json
import os
import random
import time
from functools import partial

import numpy as np
import pandas as pd

from meta_common import EVAL_GAMES, MODES, PLAYER_COUNTS, TAB, rules_for
from run_config import scaled
from monopoly_meta import watch
from monopoly_meta.meta import BALANCED, evaluate, evolve, paired_ratio
from monopoly_meta.unconventional import (DESCRIPTORS, TACTIC_NAMES, TACTICS, league, league_picks, nash_mixture,
                                          pick_finalists, random_genome_ext, search, tactics_on, validate, vary,
                                          with_tactics)

log = partial(print, flush=True)
SMOKE = bool(os.environ.get("MM_SMOKE"))
OUT = TAB / "unconventional"

# 1. the tactics arm: scripts/12_exploitability.py's budget and protocol
GENERATIONS, POP, GAMES = (2, 4, 40) if SMOKE else (16, 10, 1000)
STARTS = ["meta agent", "simple bot", "random genome"]
FRESH_GAMES = 40 if SMOKE else max(1000, EVAL_GAMES // 4)
# 2. MAP-Elites: strategies tried per table size (about 15 minutes each on a 16-thread PC; championship
# games at 5-6 players often run to the time limit, so those sizes get fewer), games per strategy, regions
EVALS = {"standard": {2: 6000, 3: 7000, 4: 5000, 5: 4000, 6: 3600},
         "championship": {2: 5400, 3: 6000, 4: 5000, 5: 1100, 6: 800}}
SEARCH_GAMES, CELLS, BATCH = (20, 12, 8) if SMOKE else (600, 128, 32)
# 3. the checks
VAL_GAMES = 60 if SMOKE else scaled(1000)
LEAGUE_GAMES = 30 if SMOKE else scaled(200)
LEAGUE_SIZE = 10


def label(genome: dict) -> str:
    on = tactics_on(genome)
    return ", ".join(TACTIC_NAMES[k] for k in on) if on else "no tactics"


def control_challenger(mode: str, n: int) -> dict | None:
    """The control arm's best challenger (scripts/12_exploitability.py), if it has run."""
    p = TAB / f"exploitability_{mode}.csv"
    if not p.exists():
        return None
    rows = pd.read_csv(p)
    rows = rows[rows.n_players == n]
    return json.loads(rows.iloc[-1]["challenger"]) if len(rows) else None


def tactics_arm(mode: str, n: int, meta: dict, rules, s0: int) -> dict:
    d = OUT / f"tactics_{mode}"
    d.mkdir(parents=True, exist_ok=True)
    watch.context.update(candidate="Challenger", opponents="Meta agent",
                         about=f"Tactics arm ({mode} rules, {n} players): a challenger trained against the meta "
                               "agents, now allowed the new moves")
    found = []
    for i, start in enumerate(STARTS):
        path = d / f"{n}p_{i}.json"
        if path.exists():
            found.append(json.loads(path.read_text()))
            continue
        t = time.time()
        init = [with_tactics(meta)] if i == 0 else [with_tactics(BALANCED)] if i == 1 else \
            [random_genome_ext(random.Random(s0 + 77 * n))]
        res = evolve(n, generations=GENERATIONS, pop_size=POP, games=GAMES, seed=s0 + 4_000 + 10 * n + i, init=init,
                     opponents=[meta], rules=rules, mutator=vary, sampler=random_genome_ext, log=log)
        rec = {"n_players": n, "start": start, "challenger": res.best, "train_fitness": res.best_fitness,
               "seconds": round(time.time() - t)}
        path.write_text(json.dumps(rec, indent=1))
        found.append(rec)
        log(f"  [{n}p] tactics arm, start '{start}': trained {res.best_fitness:.3f}x ({label(res.best)})")
    cands = [r["challenger"] for r in found]
    fresh = evaluate(cands, [meta], n, FRESH_GAMES, seed=s0 + 5_000 + n, rules=rules, fixed_opponents=True)
    best = int(np.argmax(fresh))
    control = control_challenger(mode, n)
    # the control arm's final games (same seed, same number), so the two challengers meet on equal terms
    evaluate([cands[best], meta] + ([control] if control else []), [meta], n, EVAL_GAMES, seed=s0 + 6_000 + n,
             rules=rules, fixed_opponents=True)
    g = evaluate.last_games
    rel, lo, hi = paired_ratio(g[0], g[1], seed=n)
    row = {"n_players": n, "mode": mode, "best_start": found[best]["start"], "tactics": label(cands[best]),
           "tactics_vs_meta": rel, "ci_low": lo, "ci_high": hi, "games": EVAL_GAMES,
           "challenger": json.dumps(cands[best])}
    if control:
        c, c_lo, c_hi = paired_ratio(g[2], g[1], seed=n)
        tc, tc_lo, tc_hi = paired_ratio(g[0], g[2], seed=n)
        row.update(control_vs_meta=c, control_ci_low=c_lo, control_ci_high=c_hi,
                   tactics_vs_control=tc, tvc_ci_low=tc_lo, tvc_ci_high=tc_hi)
    log(f"{n} players: tactics arm {rel:.3f}x the meta agent [{lo:.3f}, {hi:.3f}] ({row['tactics']})"
        + (f"; control arm {row['control_vs_meta']:.3f}x; tactics/control {row['tactics_vs_control']:.3f} "
           f"[{row['tvc_ci_low']:.3f}, {row['tvc_ci_high']:.3f}]" if control else "; control arm not run yet"))
    return row


def run(mode: str, n: int, metas: dict) -> None:
    done = OUT / f"{mode}_{n}p.json"
    if done.exists():
        log(f"{n} players: already done")
        return
    s0 = MODES[mode]["seed"]
    meta = {k: v for k, v in metas[str(n)].items() if k != "name"}
    rules = rules_for(mode, n)
    t0 = time.time()
    # 1. tactics arm, against the control arm
    arm_csv = OUT / f"tactics_{mode}.csv"
    arm_rows = pd.read_csv(arm_csv).to_dict("records") if arm_csv.exists() else []
    arm = next((r for r in arm_rows if int(r["n_players"]) == n), None)
    if arm is None:
        arm = tactics_arm(mode, n, meta, rules, s0)
        arm_rows.append(arm)
        pd.DataFrame(arm_rows).to_csv(arm_csv, index=False)
    # 2. MAP-Elites
    watch.context.update(candidate="Explorer", opponents="Meta agent",
                         about=f"MAP-Elites ({mode} rules, {n} players): strong strategies of every kind against "
                               "the meta agents, new moves allowed")
    evals = 3 * CELLS + 2 * BATCH if SMOKE else EVALS[mode][n]
    state = search(meta, n, rules, seed=s0 + 7_000 + n, games=SEARCH_GAMES, cells=CELLS,
                   init=min(3 * CELLS, evals // 2), batch=BATCH, evals=evals, ckpt=OUT / f"search_{mode}_{n}p.json",
                   log=log)
    # 3. checks: the finalists on fresh games, then the league
    watch.context.update(candidate="Finalist", opponents="Meta agent",
                         about=f"Checking the finds ({mode} rules, {n} players) on fresh games")
    rows = validate(pick_finalists(state), meta, n, rules, seed=s0 + 8_000 + n, games=VAL_GAMES)
    for r in sorted(rows, key=lambda r: -r["ratio"])[:5]:
        log(f"  [{n}p] find {r['ratio']:.3f}x the meta [{r['ci_low']:.3f}, {r['ci_high']:.3f}] "
            f"(search said {r['search_fitness']:.3f}x): {label(r['genome'])}")
    picks = league_picks(meta, rows, LEAGUE_SIZE)
    watch.context.update(candidate="Challenger", opponents="League member",
                         about=f"League ({mode} rules, {n} players): every pairing of the finalists")
    m = league(picks, n, rules, seed=s0 + 9_000 + 100 * n, games=LEAGUE_GAMES, log=log)
    names = list(picks)
    nash = nash_mixture(m)
    pd.DataFrame(m, index=names, columns=names).to_csv(OUT / f"league_{mode}_{n}p.csv")
    fin_csv = OUT / f"finalists_{mode}.csv"
    old = pd.read_csv(fin_csv).to_dict("records") if fin_csv.exists() else []
    old += [{"n_players": n, "mode": mode, "ratio": r["ratio"], "ci_low": r["ci_low"], "ci_high": r["ci_high"],
             "search_fitness": r["search_fitness"], "tactics": label(r["genome"]), "capped": r["capped"],
             **{f"d_{k}": v for k, v in zip(DESCRIPTORS, r["desc"])}, "genome": json.dumps(r["genome"])}
            for r in rows]
    pd.DataFrame(old).to_csv(fin_csv, index=False)
    hist = state["history"]
    done.write_text(json.dumps({
        "mode": mode, "n_players": n, "seconds": round(time.time() - t0),
        "tactics_arm": arm,
        "search": {"evals": state["evals"], "games_each": SEARCH_GAMES, "regions": CELLS,
                   "filled": len(state["elites"]), "meta_credit": state["meta_credit"], "history": hist},
        "finalists": [{**{k: v for k, v in r.items() if k != "genome"}, "label": label(r["genome"]),
                       "genome": r["genome"]} for r in rows],
        "league": {"names": names, "matrix": np.round(m, 4).tolist(), "nash": np.round(nash, 4).tolist(),
                   "games": LEAGUE_GAMES},
    }, indent=1, default=float))
    best = max(rows, key=lambda r: r["ratio"])
    log(f"{n} players done in {round(time.time() - t0)} s: best find {best['ratio']:.3f}x the meta agent "
        f"[{best['ci_low']:.3f}, {best['ci_high']:.3f}] ({label(best['genome'])})")


# ---------------------------------------------------------------------- summary
def num(x):
    """A number, or None for a missing one (None, or NaN from a CSV)."""
    return None if x is None or x != x else float(x)


def summarize() -> None:
    parts = [json.loads(p.read_text()) for mode in MODES for p in sorted(OUT.glob(f"{mode}_[0-9]p.json"))]
    if not parts:
        raise SystemExit(f"nothing to summarise yet in {OUT}")
    rows, lines = [], ["# Unconventional strategies (v0.4)", "",
                       "Ratios are win credit against a table of meta agents, divided by the meta agent's own credit "
                       "on the same games (above 1 beats the meta agent), with 95% intervals.", ""]
    for mode in ("standard", "championship"):
        ps = [p for p in parts if p["mode"] == mode]
        if not ps:
            continue
        lines += [f"## {'Official' if mode == 'standard' else 'Championship'} rules", "",
                  "| Players | Control arm | Tactics arm | Tactics / control | Best find (re-measured) | Its tactics |",
                  "|---|---|---|---|---|---|"]
        for p in ps:
            a, fins = p["tactics_arm"], p["finalists"]
            best = max(fins, key=lambda r: r["ratio"])
            plain = max((r for r in fins if not r["tactics"]), key=lambda r: r["ratio"], default=None)
            ctrl, tvc = num(a.get("control_vs_meta")), num(a.get("tactics_vs_control"))
            ci = (lambda r, lo, hi: f"{r:.3f} [{lo:.3f}, {hi:.3f}]")
            lines.append(f"| {p['n_players']} | {f'{ctrl:.3f}' if ctrl is not None else '-'} "
                         f"| {ci(a['tactics_vs_meta'], a['ci_low'], a['ci_high'])} "
                         f"| {ci(tvc, a['tvc_ci_low'], a['tvc_ci_high']) if tvc is not None else '-'} "
                         f"| {ci(best['ratio'], best['ci_low'], best['ci_high'])} | {best['label']} |")
            lg = p["league"]
            mix = sorted(zip(lg["names"], lg["nash"]), key=lambda x: -x[1])
            meta_col = lg["names"].index("meta agent")
            invaders = [(nm, row[meta_col]) for nm, row in zip(lg["names"], lg["matrix"]) if row[meta_col] > 1.05]
            rows.append({"mode": mode, "n_players": p["n_players"], "control_vs_meta": ctrl,
                         "tactics_vs_meta": a["tactics_vs_meta"], "tactics_vs_control": tvc,
                         "best_find": best["ratio"], "best_find_ci_low": best["ci_low"],
                         "best_find_ci_high": best["ci_high"],
                         "best_find_tactics": best["label"], "best_plain": plain["ratio"] if plain else None,
                         "strategies_tried": p["search"]["evals"], "regions_filled": p["search"]["filled"],
                         "nash_mixture": "; ".join(f"{nm} {w:.0%}" for nm, w in mix if w >= 0.05),
                         "invade_meta": "; ".join(f"{nm} {v:.2f}x" for nm, v in invaders)})
        lines.append("")
        for r in (r for r in rows if r["mode"] == mode):
            lines.append(f"- **{r['n_players']} players.** {r['strategies_tried']:,} strategies tried, "
                         f"{r['regions_filled']} kinds of play kept. League mixture: {r['nash_mixture'] or '-'}. "
                         f"Can invade a table of meta agents: {r['invade_meta'] or 'nothing'}.")
        lines.append("")
    # which tactics show up among finds that beat the meta agent
    lines += ["## Tactics among finds that beat the meta agent (interval above 1)", ""]
    counts = {k: 0 for k in TACTICS}
    total = 0
    for p in parts:
        for r in p["finalists"]:
            if r["ci_low"] > 1:
                total += 1
                for k in r["tactics"]:
                    counts[k] += 1
    lines += [f"- {TACTIC_NAMES[k]}: {c} of {total}" for k, c in sorted(counts.items(), key=lambda x: -x[1])] or ["-"]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n")
    pd.DataFrame(rows).to_csv(OUT / "summary.csv", index=False)
    log("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=list(MODES), default="standard")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("players", nargs="*", type=int, default=PLAYER_COUNTS)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.summary:
        summarize()
        return
    metas = json.loads((TAB / f"meta_agents_{args.mode}.json").read_text())
    for n in args.players:
        if str(n) in metas:
            run(args.mode, n, metas)


if __name__ == "__main__":
    main()
