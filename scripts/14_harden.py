"""Harden the meta agents against the new moves (v0.5), then measure how exploitable they still are.

    python scripts/14_harden.py --mode standard [players ...]             # ablations, hardening, checks
    python scripts/14_harden.py --mode standard --recheck [players ...]   # v0.4's searches against the new agents
    python scripts/14_harden.py --summary

v0.4 (results/v04/tables) found that every v0.3 meta agent can be beaten by 1.2-1.9x. For each table size:

1. Ablations. v0.4's three strongest finds and its best new-moves challenger, each with one new move
   switched off at a time (and all of them), at a table of v0.3 meta agents: which moves do the work?
2. Hardening (monopoly_meta.harden): best-response iteration from the v0.3 agent, new moves allowed,
   against a pool of what v0.4 found that beat it, growing with fresh exploits each round.
3. Checks on fresh games: v0.4's exploits against the new agent and the old one (the same games); the new
   agent at a table of old ones and the other way round; both at a table of simple bots.
4. (--recheck) v0.4's two searches, with v0.4's budgets and seeds, against the new agent: the best-response
   search with the new moves (v0.4's tactics arm) and MAP-Elites. Before and after, like for like.
5. Keep the better agent. The new agent replaces the old one only if its worst measured exploit (the two
   searches and v0.4's exploits) is smaller than the old one's (v0.4's searches and the same exploits).

Outputs, under <results>/tables (MM_RESULTS=results/v05):
  hardened/ablations_<mode>.csv       step 1
  hardened/harden_<mode>_<n>p*.json   step 2's rounds (also its checkpoints)
  hardened/<mode>_<n>p.json           the new agent and steps 3-4
  meta_agents_<mode>.json             the meta agents kept (step 5): the new one where it is better
  hardened/summary.md, summary.csv    before and after (--summary)
v0.4's results are read from results/v04/tables (MM_FROM overrides). MM_SMOKE=1 shrinks every budget.
"""
import argparse
import json
import os
import random
import time
from functools import partial

import numpy as np
import pandas as pd

from meta_common import EVAL_GAMES, MODES, PLAYER_COUNTS, ROOT, TAB, rules_for
from run_config import scaled
from monopoly_meta import watch
from monopoly_meta.harden import Budget, ablate, exposure, harden, keep_better, label, worst_exploit
from monopoly_meta.meta import BALANCED, evaluate, evolve, paired_ratio
from monopoly_meta.unconventional import (TACTIC_NAMES, TACTICS, league_picks, pick_finalists, random_genome_ext,
                                          search, validate, vary, with_tactics)

log = partial(print, flush=True)
SMOKE = bool(os.environ.get("MM_SMOKE"))
V04 = ROOT / os.environ.get("MM_FROM", "results/v04/tables")
OUT = TAB / "hardened"

# 1. ablations
ABL_GAMES = 40 if SMOKE else scaled(600)
# 2. hardening: per round (monopoly_meta.harden.Budget); fewer generations and oracle strategies where games
# are slow. v0.4's MAP-Elites budgets were set for about the same time per table size, so they give the speed.
ROUNDS, THRESHOLD = (2, 1.05) if SMOKE else (4, 1.05)
BUDGET = (Budget(generations=2, pop_size=4, games=16, select_games=16, top=2, exposure_games=16, oracle_evals=24,
                 oracle_games=8, oracle_cells=8, oracle_batch=8, oracle_keep=2, check_games=16, max_new=2)
          if SMOKE else Budget())
EVALS = {"standard": {2: 6000, 3: 7000, 4: 5000, 5: 4000, 6: 3600},
         "championship": {2: 5400, 3: 6000, 4: 5000, 5: 1100, 6: 800}}
# 3. checks
VAL_GAMES = 60 if SMOKE else scaled(1000)
# 4. v0.4's searches: scripts/13_unconventional.py's budgets and seeds
GENERATIONS, POP, GAMES = (2, 4, 40) if SMOKE else (16, 10, 1000)
STARTS = ["meta agent", "simple bot", "random genome"]
FRESH_GAMES = 40 if SMOKE else max(1000, EVAL_GAMES // 4)
FINAL_GAMES = 60 if SMOKE else EVAL_GAMES  # v0.4's final measurement: 40,000 games
SEARCH_GAMES, CELLS, BATCH = (20, 12, 8) if SMOKE else (600, 128, 32)


def key(genome: dict) -> str:
    return json.dumps(with_tactics(genome), sort_keys=True)


def ci(r, lo, hi) -> str:
    return f"{r:.3f} [{lo:.3f}, {hi:.3f}]"


# ---------------------------------------------------------------------- v0.4's results
def v04_inputs(mode: str, n: int) -> dict:
    """The v0.3 meta agent v0.4 tested, and what v0.4 found that beat it."""
    metas = json.loads((V04 / f"meta_agents_{mode}.json").read_text())
    meta = {k: v for k, v in metas[str(n)].items() if k != "name"}
    d = json.loads((V04 / "unconventional" / f"{mode}_{n}p.json").read_text())
    ranked = sorted(d["finalists"], key=lambda r: -r["ratio"])
    exploits = {f"v0.4 find {i}": r["genome"] for i, r in enumerate(ranked[:3], 1)}
    exploits["v0.4 new-moves challenger"] = json.loads(d["tactics_arm"]["challenger"])
    ctrl = pd.read_csv(V04 / f"exploitability_{mode}.csv")
    exploits["v0.4 old-moves challenger"] = json.loads(ctrl[ctrl.n_players == n].iloc[-1]["challenger"])
    picks = league_picks(meta, d["finalists"])
    for name, w in zip(d["league"]["names"], d["league"]["nash"]):
        if w >= 0.1 and name not in ("meta agent", "simple bot"):
            exploits[f"v0.4 league: {name}"] = picks[name]
    out, seen = {}, {key(meta), key(BALANCED)}
    for name, g in exploits.items():
        if key(g) not in seen:
            seen.add(key(g))
            out[name] = with_tactics(g)
    return {"meta": with_tactics(meta), "exploits": out,
            "before": {"tactics_arm": d["tactics_arm"]["tactics_vs_meta"], "tactics_arm_ci":
                       [d["tactics_arm"]["ci_low"], d["tactics_arm"]["ci_high"]],
                       "best_find": ranked[0]["ratio"], "best_find_ci": [ranked[0]["ci_low"], ranked[0]["ci_high"]],
                       "best_find_tactics": ranked[0]["label"]}}


# ---------------------------------------------------------------------- steps 1-3
def harden_size(mode: str, n: int) -> None:
    path = OUT / f"{mode}_{n}p.json"
    if path.exists():
        log(f"{n} players: already hardened")
        return
    s0, rules, t0 = MODES[mode]["seed"], rules_for(mode, n), time.time()
    inp = v04_inputs(mode, n)
    meta, exploits = inp["meta"], inp["exploits"]
    # 1. which new moves do the work in what v0.4 found
    abl_csv = OUT / f"ablations_{mode}.csv"
    rows = pd.read_csv(abl_csv).to_dict("records") if abl_csv.exists() else []
    if not any(int(r["n_players"]) == n for r in rows):
        watch.context.update(candidate="Ablated find", opponents="Meta agent",
                             about=f"Ablations ({mode} rules, {n} players): v0.4's finds with one new move "
                                   "switched off at a time")
        strategies = {k: v for k, v in exploits.items() if k.startswith(("v0.4 find", "v0.4 new-moves"))}
        abl = ablate(strategies, meta, n, rules, games=ABL_GAMES, seed=s0 + 10_000 + n)
        rows += [{"n_players": n, "mode": mode, **r} for r in abl]
        pd.DataFrame(rows).to_csv(abl_csv, index=False)
        for r in abl:
            if r["variant"] != "as found" and r["change"] <= -0.05:
                log(f"  [{n}p] {r['name']}: {r['variant']} costs {-r['change']:.2f} ({r['ratio']:.3f}x)")
    # 2. hardening
    pool = {"v0.3 meta agent": meta, "simple bot": with_tactics(BALANCED), **exploits}
    budget = BUDGET if SMOKE else BUDGET.for_speed(EVALS[mode][n] / 5000)
    log(f"  [{n}p] hardening against a pool of {len(pool)}: {', '.join(pool)}")
    res = harden(meta, pool, n, rules, seed=s0 + 11_000 + n, budget=budget, rounds=ROUNDS, threshold=THRESHOLD,
                 ckpt=OUT / f"harden_{mode}_{n}p.json", log=log)
    new = res["meta"]
    # 3. checks on fresh games
    watch.context.update(candidate="v0.4 exploit", opponents="Meta agent",
                         about=f"Checks ({mode} rules, {n} players): v0.4's exploits against the old and the new "
                               "meta agent")
    before = exposure(meta, exploits, n, rules, games=VAL_GAMES, seed=s0 + 12_000 + n)
    after = exposure(new, exploits, n, rules, games=VAL_GAMES, seed=s0 + 12_000 + n)
    watch.context.update(candidate="Meta agent", opponents="Meta agent",
                         about=f"Checks ({mode} rules, {n} players): the new meta agent against the old one")
    new_in_old = exposure(meta, {"v0.5 meta agent": new}, n, rules, games=VAL_GAMES, seed=s0 + 13_000 + n)[0]
    old_in_new = exposure(new, {"v0.3 meta agent": meta}, n, rules, games=VAL_GAMES, seed=s0 + 13_000 + n)[0]
    vs_simple = exposure(with_tactics(BALANCED), {"v0.5 meta agent": new, "v0.3 meta agent": meta}, n, rules,
                         games=VAL_GAMES, seed=s0 + 14_000 + n)
    worst_before, worst_after = max(before, key=lambda r: r["ratio"]), max(after, key=lambda r: r["ratio"])
    rec = {"mode": mode, "n_players": n, "v03": meta, "v05": new, "v05_tactics": label(new),
           "before": inp["before"], "pool": list(pool),
           "hardening": {"selected_round": res["selected_round"], "rounds": [
               {k: v for k, v in r.items() if k not in ("meta", "exposure", "evolution", "candidates")}
               for r in res["rounds"]], "final": [{k: v for k, v in f.items() if k != "exposure"} for f in
                                                  res["final"]], "final_pool": list(res["pool"])},
           "known_before": before, "known_after": after, "new_in_old": new_in_old, "old_in_new": old_in_new,
           "vs_simple": vs_simple, "seconds": round(time.time() - t0)}
    path.write_text(json.dumps(rec, indent=1, default=float))
    log(f"{n} players hardened in {rec['seconds']} s: new agent ({label(new)}); v0.4's worst exploit "
        f"{worst_before['ratio']:.3f}x -> {worst_after['ratio']:.3f}x ({worst_after['name']}); new agent at a "
        f"table of old ones {new_in_old['ratio']:.3f}x, old at a table of new {old_in_new['ratio']:.3f}x")


# ---------------------------------------------------------------------- step 4
def recheck(mode: str, n: int) -> None:
    path = OUT / f"{mode}_{n}p.json"
    if not path.exists():
        raise SystemExit(f"{n} players: harden first (scripts/14_harden.py --mode {mode} {n})")
    rec = json.loads(path.read_text())
    if "recheck" in rec:
        log(f"{n} players: already rechecked")
        return
    s0, rules, t0 = MODES[mode]["seed"], rules_for(mode, n), time.time()
    new = rec["v05"]
    inp = v04_inputs(mode, n)
    # (a) v0.4's tactics arm (best-response search with the new moves), against the new agent
    d = OUT / f"recheck_{mode}"
    d.mkdir(parents=True, exist_ok=True)
    watch.context.update(candidate="Challenger", opponents="v0.5 meta agent",
                         about=f"Recheck ({mode} rules, {n} players): v0.4's challenger search against the new "
                               "meta agents")
    found = []
    for i, start in enumerate(STARTS):
        p = d / f"{n}p_{i}.json"
        if p.exists():
            found.append(json.loads(p.read_text()))
            continue
        t = time.time()
        init = [with_tactics(new)] if i == 0 else [with_tactics(BALANCED)] if i == 1 else \
            [random_genome_ext(random.Random(s0 + 77 * n))]
        res = evolve(n, generations=GENERATIONS, pop_size=POP, games=GAMES, seed=s0 + 4_000 + 10 * n + i, init=init,
                     opponents=[new], rules=rules, mutator=vary, sampler=random_genome_ext, log=log)
        r = {"n_players": n, "start": start, "challenger": res.best, "train_fitness": res.best_fitness,
             "seconds": round(time.time() - t)}
        p.write_text(json.dumps(r, indent=1))
        found.append(r)
        log(f"  [{n}p] recheck, start '{start}': trained {res.best_fitness:.3f}x ({label(res.best)})")
    cands = [r["challenger"] for r in found]
    fresh = evaluate(cands, [new], n, FRESH_GAMES, seed=s0 + 5_000 + n, rules=rules, fixed_opponents=True)
    best = int(np.argmax(fresh))
    old_arm = inp["exploits"].get("v0.4 new-moves challenger")
    evaluate([cands[best], new] + ([old_arm] if old_arm else []), [new], n, FINAL_GAMES, seed=s0 + 6_000 + n,
             rules=rules, fixed_opponents=True)
    g = evaluate.last_games
    arm = dict(zip(("ratio", "ci_low", "ci_high"), paired_ratio(g[0], g[1], seed=n)))
    arm.update(start=found[best]["start"], tactics=label(cands[best]), challenger=cands[best], games=FINAL_GAMES)
    if old_arm:
        arm["v04_challenger"] = dict(zip(("ratio", "ci_low", "ci_high"), paired_ratio(g[2], g[1], seed=n)))
    log(f"  [{n}p] recheck: best challenger {ci(arm['ratio'], arm['ci_low'], arm['ci_high'])} the new agent "
        f"({arm['tactics']}); against the old agent it was {inp['before']['tactics_arm']:.3f}")
    # (b) MAP-Elites against the new agent, v0.4's budget and seed
    watch.context.update(candidate="Explorer", opponents="v0.5 meta agent",
                         about=f"Recheck ({mode} rules, {n} players): MAP-Elites against the new meta agents")
    evals = 3 * CELLS + 2 * BATCH if SMOKE else EVALS[mode][n]
    state = search(new, n, rules, seed=s0 + 7_000 + n, games=SEARCH_GAMES, cells=CELLS,
                   init=min(3 * CELLS, evals // 2), batch=BATCH, evals=evals, ckpt=OUT / f"search_{mode}_{n}p.json",
                   log=log)
    watch.context.update(candidate="Finalist", opponents="v0.5 meta agent",
                         about=f"Recheck ({mode} rules, {n} players): the strongest finds on fresh games")
    rows = validate(pick_finalists(state), new, n, rules, seed=s0 + 8_000 + n, games=VAL_GAMES)
    rows.sort(key=lambda r: -r["ratio"])
    finds = [{**{k: v for k, v in r.items() if k != "desc"}, "label": label(r["genome"])} for r in rows]
    rec["recheck"] = {"tactics_arm": arm, "search": {"evals": state["evals"], "filled": len(state["elites"]),
                                                     "history": state["history"]},
                      "finalists": finds, "seconds": round(time.time() - t0)}
    path.write_text(json.dumps(rec, indent=1, default=float))
    keep_agents(mode)
    b = finds[0]
    log(f"{n} players rechecked in {rec['recheck']['seconds']} s: best MAP-Elites find "
        f"{ci(b['ratio'], b['ci_low'], b['ci_high'])} the new agent ({b['label']}); against the old agent "
        f"{inp['before']['best_find']:.3f}")


# ---------------------------------------------------------------------- step 5
def choice(rec: dict) -> dict | None:
    """Old agent or new: the one whose worst measured exploit is smaller (None before the recheck)."""
    rc = rec.get("recheck")
    if rc is None:
        return None
    old = worst_exploit([rec["before"]["tactics_arm"], rec["before"]["best_find"]], rec["known_before"])
    new = worst_exploit([rc["tactics_arm"]["ratio"], rc["finalists"][0]["ratio"]], rec["known_after"])
    return {"agent": "v0.5" if keep_better(old, new) == "new" else "v0.3", "worst_v03": old, "worst_v05": new}


def keep_agents(mode: str) -> None:
    """Record the choice in each table size's results and write the meta agents kept."""
    kept = {}
    for p in sorted(OUT.glob(f"{mode}_[0-9]p.json")):
        rec = json.loads(p.read_text())
        c = choice(rec)
        if c is None:
            continue
        if rec.get("chosen") != c:
            rec["chosen"] = c
            p.write_text(json.dumps(rec, indent=1, default=float))
        kept[str(rec["n_players"])] = rec["v05"] if c["agent"] == "v0.5" else rec["v03"]
        log(f"  [{rec['n_players']}p] keeping the {c['agent']} agent: worst exploit {c['worst_v03']:.3f}x for v0.3, "
            f"{c['worst_v05']:.3f}x for v0.5")
    if kept:
        (TAB / f"meta_agents_{mode}.json").write_text(json.dumps(dict(sorted(kept.items())), indent=2))


# ---------------------------------------------------------------------- summary
def summarize() -> None:
    parts = [json.loads(p.read_text()) for mode in MODES for p in sorted(OUT.glob(f"{mode}_[0-9]p.json"))]
    if not parts:
        raise SystemExit(f"nothing in {OUT} yet")
    lines = ["# Hardened meta agents (v0.5)", "",
             "Ratios are a strategy's win credit at a table of meta agents, divided by the meta agent's own credit in "
             "that seat on the same games (above 1 beats the meta agent), with 95% intervals. *Before* is v0.4's "
             "measurement against the v0.3 agents; *after* repeats it against the v0.5 agents. *Kept* is the agent "
             "with the smaller worst exploit (the two searches and v0.4's exploits), so a table size where "
             "hardening made things worse keeps its v0.3 agent.", ""]
    rows = []
    for mode in MODES:
        keep_agents(mode)
    parts = [json.loads(p.read_text()) for mode in MODES for p in sorted(OUT.glob(f"{mode}_[0-9]p.json"))]
    for mode in MODES:
        ps = sorted((x for x in parts if x["mode"] == mode), key=lambda x: x["n_players"])
        if not ps:
            continue
        lines += [f"## {'Official' if mode == 'standard' else 'Championship'} rules", "",
                  "| Players | Kept | Worst exploit: v0.3 -> v0.5 | Hardening rounds | v0.4's exploits, worst: "
                  "before -> after | Challenger search: before -> after | MAP-Elites: before -> after | New agent at a "
                  "table of old | Old agent at a table of new | New agent's moves |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for x in ps:
            n = x["n_players"]
            wb = max(x["known_before"], key=lambda r: r["ratio"])
            wa = max(x["known_after"], key=lambda r: r["ratio"])
            rc = x.get("recheck")
            ta, bf = (rc["tactics_arm"], rc["finalists"][0]) if rc else (None, None)
            arm = f"{x['before']['tactics_arm']:.3f} -> " + (ci(ta["ratio"], ta["ci_low"], ta["ci_high"]) if rc
                                                             else "not run")
            me = f"{x['before']['best_find']:.3f} -> " + (ci(bf["ratio"], bf["ci_low"], bf["ci_high"]) if rc
                                                          else "not run")
            h = x["hardening"]
            c = x.get("chosen")
            kept = c["agent"] if c else "not decided"
            worst = f"{c['worst_v03']:.3f} -> {c['worst_v05']:.3f}" if c else "-"
            rnd = "kept the old agent" if h["selected_round"] == 0 else f"kept round {h['selected_round']}"
            lines.append(f"| {n} | {kept} | {worst} | {len(h['rounds'])} ({rnd}) | {wb['ratio']:.3f} -> "
                         f"{ci(wa['ratio'], wa['ci_low'], wa['ci_high'])} ({wa['name']}) | {arm} | {me} | "
                         f"{ci(x['new_in_old']['ratio'], x['new_in_old']['ci_low'], x['new_in_old']['ci_high'])} | "
                         f"{ci(x['old_in_new']['ratio'], x['old_in_new']['ci_low'], x['old_in_new']['ci_high'])} | "
                         f"{x['v05_tactics']} |")
            rows.append({"mode": mode, "n_players": n, "kept": kept, "worst_v03": c["worst_v03"] if c else None,
                         "worst_v05": c["worst_v05"] if c else None,
                         "rounds": len(h["rounds"]), "kept_round": h["selected_round"],
                         "known_worst_before": wb["ratio"], "known_worst_after": wa["ratio"],
                         "known_worst_after_name": wa["name"], "arm_before": x["before"]["tactics_arm"],
                         "arm_after": rc["tactics_arm"]["ratio"] if rc else None,
                         "find_before": x["before"]["best_find"],
                         "find_after": rc["finalists"][0]["ratio"] if rc else None,
                         "new_in_old": x["new_in_old"]["ratio"], "old_in_new": x["old_in_new"]["ratio"],
                         "new_vs_simple": next(r["ratio"] for r in x["vs_simple"] if r["name"] == "v0.5 meta agent"),
                         "old_vs_simple": next(r["ratio"] for r in x["vs_simple"] if r["name"] == "v0.3 meta agent"),
                         "new_tactics": x["v05_tactics"], "new_agent": json.dumps(x["v05"])})
        lines.append("")
    # which new moves do the work in v0.4's finds
    abl = [pd.read_csv(p) for p in sorted(OUT.glob("ablations_*.csv"))]
    if abl:
        a = pd.concat(abl)
        a = a[a.variant.str.startswith("without ") & (a.variant != "without any new move")]
        lines += ["## Which new moves do the work (v0.4's finds, one move switched off at a time)", "",
                  "| Move | Strategies using it | Switching it off costs 0.05 or more | Average change |",
                  "|---|---|---|---|"]
        for k in TACTICS:
            s = a[a.variant == f"without {TACTIC_NAMES[k]}"]
            if len(s):
                lines.append(f"| {TACTIC_NAMES[k]} | {len(s)} | {(s.change <= -0.05).sum()} | {s.change.mean():+.3f} |")
        lines.append("")
    (OUT / "summary.md").write_text("\n".join(lines))
    pd.DataFrame(rows).to_csv(OUT / "summary.csv", index=False)
    log("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=list(MODES), default="standard")
    ap.add_argument("--recheck", action="store_true")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("players", nargs="*", type=int, default=PLAYER_COUNTS)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.summary:
        summarize()
        return
    for n in args.players:
        (recheck if args.recheck else harden_size)(args.mode, n)


if __name__ == "__main__":
    main()
