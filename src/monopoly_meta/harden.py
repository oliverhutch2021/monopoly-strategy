"""Hardening the meta agents against the new moves (v0.5).

v0.4 found that every v0.3 meta agent can be beaten by 1.2-1.9x, mostly with the new moves (the housing
lock, auction sniping, borrowing to build). Hardening asks for meta agents that are hard to exploit
when those moves are known, by best-response iteration against a growing pool of known exploits: a
small version of the double oracle / PSRO idea (McMahan et al. 2003; Lanctot et al. 2017).

Each round
  1. evolves a population, new moves allowed, whose fitness is its win credit at *mixed* tables: every
     seat is drawn from the population, its hall of fame and the pool of known exploits (`sparring`).
     Tables made of one exploit are a poor test, because many exploits are counter-strategies that stall
     or leave whole colour groups to whoever joins (v0.4's leagues);
  2. picks, among the fittest few, the one the pool exploits least: each pool member sits in one seat at
     a table of the candidate, against the candidate itself in that seat (the placebo), on the same games.
     A candidate whose own table often runs out of time is passed over (MAX_SELF_CAPPED): stalling makes
     an agent look hard to exploit only because nobody wins;
  3. searches for fresh exploits of the pick with MAP-Elites (the oracle) and re-measures the strongest
     on fresh games. Those that beat it by `threshold` or more join the pool, and the next round starts.

The round's exploitability is the worst ratio it showed, known or fresh. Rounds stop once that is below
`threshold`. Because later rounds face a bigger pool, the agents of all rounds are finally measured
against the final pool (which holds the exploits found against every round's agent, the last one's
too), and the least exploited one is returned: the starting agent too, if no round did better (in v0.5's
first run at 6 players every round made things worse). After the full recheck, `keep_better` decides
between the old agent and the new one on their worst measured exploit.

Everything is checkpointed (the state after each phase, and the oracle's archive after each batch), so
a stopped run resumes where it was.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np

from . import watch
from .engine import Rules
from .meta import evaluate, evolve, paired_ratio
from .unconventional import (TACTIC_NAMES, TACTICS, Arena, random_genome_ext, search, tactics_on, validate, vary,
                             with_tactics)
from .provenance import check_resume, fingerprint

MAX_SELF_CAPPED = 0.15  # share of an agent's own games stopped by the time limit, above which it isn't picked


@dataclass(frozen=True)
class Budget:
    """What one hardening round may spend. `for_speed` shrinks the searches for slow table sizes."""
    generations: int = 10       # evolution, per round
    pop_size: int = 10
    games: int = 800            # games per candidate per generation, at mixed tables
    select_games: int = 2000    # fresh games to rank the evolved population
    top: int = 3                # fittest candidates whose exposure to the pool is measured
    exposure_games: int = 2000  # games per pool member at a table of a candidate
    oracle_evals: int = 800     # strategies MAP-Elites tries against the pick
    oracle_games: int = 400
    oracle_cells: int = 64
    oracle_batch: int = 32
    oracle_keep: int = 4        # the oracle's strongest finds, re-measured
    check_games: int = 3000     # games to re-measure them
    max_new: int = 3            # fresh exploits that may join the pool per round

    def for_speed(self, speed: float) -> "Budget":
        """Fewer generations and oracle strategies where games are slow (speed < 1 is slower than official
        rules at 4 players); the games per measurement stay, so the noise does."""
        return replace(self, generations=int(np.clip(round(self.generations * speed), 5, 12)),
                       oracle_evals=max(8 * self.oracle_batch, int(round(self.oracle_evals * min(speed, 1.5)))))


def _key(genome: dict) -> str:
    return json.dumps(with_tactics(genome), sort_keys=True)


def label(genome: dict) -> str:
    on = tactics_on(genome)
    return ", ".join(TACTIC_NAMES[k] for k in on) if on else "no new moves"


# ---------------------------------------------------------------------- measuring
def exposure(meta: dict, others: dict[str, dict], n_players: int, rules: Rules, *, games: int, seed: int,
             workers: int | None = None) -> list[dict]:
    """Each of `others` in one seat at a table of `meta`, against the placebo (the meta agent itself in
    that seat) on the same games: the paired ratio of their win credits with a 95% interval. Above 1,
    it exploits the meta agent."""
    names = list(others)
    with Arena(with_tactics(meta), n_players, rules, games, seed, workers) as arena:
        res = arena.play([with_tactics(meta)] + [others[k] for k in names], name="Challenger")
    base = res[0]["games"]
    rows = []
    for i, (name, r) in enumerate(zip(names, res[1:])):
        ratio, lo, hi = paired_ratio(r["games"], base, seed=seed + i)
        rows.append({"name": name, "ratio": ratio, "ci_low": lo, "ci_high": hi, "credit": r["credit"],
                     "meta_credit": res[0]["credit"], "capped": r["capped"], "meta_capped": res[0]["capped"],
                     "tactics": label(others[name])})
    return rows


def _worst(rows: list[dict]) -> dict:
    """The strongest exploit in an exposure table, and how often the agent's own table hit the time limit."""
    if not rows:
        return {"worst": 0.0, "worst_name": "", "self_capped": 0.0}
    w = max(rows, key=lambda x: x["ratio"])
    return {"worst": w["ratio"], "worst_name": w["name"], "self_capped": rows[0]["meta_capped"]}


def _least_exploited(cands: list[dict], fitness: bool = True) -> int:
    """The candidate with the smallest worst exploit (ties: the fitter), among those whose own table rarely
    stalls: an agent that stalls its games can look hard to exploit only because nobody wins."""
    ok = [j for j, c in enumerate(cands) if c["self_capped"] <= MAX_SELF_CAPPED] or list(range(len(cands)))
    return min(ok, key=lambda j: (round(cands[j]["worst"], 3), -cands[j].get("fitness", 0.0) if fitness else 0.0))


def ablations(genome: dict) -> dict[str, dict]:
    """The genome with each of its new moves switched off in turn, and with all of them off."""
    g = with_tactics(genome)
    on = tactics_on(g)
    out = {f"without {TACTIC_NAMES[k]}": {**g, k: TACTICS[k][0]} for k in on}
    if len(on) > 1:
        out["without any new move"] = {**g, **{k: TACTICS[k][0] for k in TACTICS}}
    return out


def ablate(strategies: dict[str, dict], meta: dict, n_players: int, rules: Rules, *, games: int, seed: int,
           workers: int | None = None) -> list[dict]:
    """Which new moves do the work? Every strategy and each of its ablations at a table of `meta`, all on
    the same games, each against the placebo."""
    cands = {}
    for name, g in strategies.items():
        cands[f"{name}|as found"] = g
        for v, gv in ablations(g).items():
            cands[f"{name}|{v}"] = gv
    rows = exposure(meta, cands, n_players, rules, games=games, seed=seed, workers=workers)
    full = {r["name"].split("|")[0]: r["ratio"] for r in rows if r["name"].endswith("|as found")}
    out = []
    for r in rows:
        name, variant = r["name"].split("|")
        out.append({**r, "name": name, "variant": variant, "change": r["ratio"] - full[name]})
    return out


# ---------------------------------------------------------------------- hardening
def harden(meta: dict, pool: dict[str, dict], n_players: int, rules: Rules, *, seed: int, budget: Budget,
           rounds: int = 4, threshold: float = 1.05, workers: int | None = None, ckpt: Path | None = None,
           log=print) -> dict:
    """Best-response iteration from `meta` against the known exploits in `pool` (see the module notes).
    Returns {"meta", "selected_round" (0: the starting agent was kept, k: round k's), "rounds", "final", "pool"}."""
    b = budget
    fp = fingerprint(meta=meta, pool=pool, n_players=n_players, rules=asdict(rules), seed=seed, budget=asdict(b),
                     rounds=rounds, threshold=threshold)
    if ckpt is not None and ckpt.exists():
        state = json.loads(ckpt.read_text())
        if state["budget"] != asdict(b) or state["seed"] != seed:
            raise SystemExit(f"{ckpt} was made with another budget or seed: delete it to start again")
        check_resume(state, fp, ckpt, log)
        log(f"  [{n_players}p] resuming hardening at round {state['round']}")
    else:
        state = {"version": 1, "n_players": n_players, "seed": seed, "budget": asdict(b), "threshold": threshold,
                 "start": with_tactics(meta), "meta": with_tactics(meta),
                 "pool": {k: with_tactics(v) for k, v in pool.items()}, "round": 0, "rounds": [], "work": {},
                 "final": None, "fingerprint": fp}

    def save():
        if ckpt is not None:
            tmp = ckpt.with_suffix(".tmp")
            tmp.write_text(json.dumps(state))
            os.replace(tmp, ckpt)

    n = n_players
    while state["final"] is None and state["round"] < rounds and not state.get("stopped"):
        r, w, cur = state["round"], state["work"], state["meta"]
        pool = state["pool"]
        # 1. evolve at mixed tables: the population, its hall of fame and the known exploits
        if "population" not in w:
            watch.context.update(candidate="Candidate", opponents="Mixed table",
                                 about=f"Hardening, round {r + 1} ({n} players): evolving meta agents against "
                                       "each other and the known exploits, new moves allowed")
            strongest = sorted(state["rounds"][-1]["exposure"], key=lambda x: -x["ratio"]) if state["rounds"] else []
            init = [cur] + [pool[x["name"]] for x in strongest[:2] if x["name"] in pool]
            res = evolve(n, generations=b.generations, pop_size=b.pop_size, games=b.games, seed=seed * 100 + r,
                         init=init, sparring=list(pool.values()), rules=rules, workers=workers, mutator=vary,
                         sampler=random_genome_ext, log=log)
            w["population"], w["history"] = res.population, res.history
            save()
        # 2. the fittest few at mixed tables, then the one the pool exploits least
        if "chosen" not in w:
            pop = w["population"]
            fit = evaluate(pop, pop + list(pool.values()), n, b.select_games, seed=seed * 1000 + r, rules=rules,
                           workers=workers)
            cands = []
            for i in np.argsort(-fit)[:b.top]:
                watch.context.update(candidate="Known exploit", opponents="Candidate meta agent",
                                     about=f"Hardening, round {r + 1} ({n} players): how much do the known "
                                           "exploits take from a candidate?")
                exp = exposure(pop[i], pool, n, rules, games=b.exposure_games, seed=seed * 10_000 + r,
                               workers=workers)
                cands.append({"genome": pop[i], "fitness": float(fit[i]), "exposure": exp, **_worst(exp)})
            w["candidates"] = cands
            w["chosen"] = _least_exploited(cands)
            save()
        pick = w["candidates"][w["chosen"]]
        # 3. the oracle: fresh exploits of the pick
        if "oracle" not in w:
            watch.context.update(candidate="Explorer", opponents="Candidate meta agent",
                                 about=f"Hardening, round {r + 1} ({n} players): MAP-Elites looking for new ways "
                                       "to beat the candidate")
            st = search(pick["genome"], n, rules, seed=seed * 7 + r, games=b.oracle_games, cells=b.oracle_cells,
                        init=min(3 * b.oracle_cells, b.oracle_evals // 2), batch=b.oracle_batch,
                        evals=b.oracle_evals, workers=workers,
                        ckpt=ckpt.with_name(f"{ckpt.stem}_oracle{r}.json") if ckpt is not None else None, log=log)
            top = sorted(st["elites"].values(), key=lambda e: -e["fitness"])[:b.oracle_keep]
            rows = validate(top, pick["genome"], n, rules, seed=seed * 11 + r, games=b.check_games, workers=workers)
            w["oracle"] = [{k: v for k, v in x.items() if k != "desc"} for x in rows]
            save()
        fresh = sorted(w["oracle"], key=lambda x: -x["ratio"])
        worst_new = fresh[0]["ratio"] if fresh else 0.0
        expl = max(pick["worst"], worst_new)
        state["rounds"].append({
            "round": r, "meta": pick["genome"], "fitness": pick["fitness"], "exposure": pick["exposure"],
            "worst_known": pick["worst"], "worst_known_name": pick["worst_name"], "self_capped": pick["self_capped"],
            "worst_new": worst_new,
            "new_tactics": label(fresh[0]["genome"]) if fresh else "", "exploitability": expl,
            "evolution": w["history"], "candidates": [{k: v for k, v in c.items() if k != "genome"}
                                                      for c in w["candidates"]],
            "pool_size": len(pool), "tactics": label(pick["genome"])})
        log(f"  [{n}p] hardening round {r + 1}: pick ({label(pick['genome'])}) - worst known exploit "
            f"{pick['worst']:.3f}x ({pick['worst_name']}), best fresh exploit {worst_new:.3f}x")
        state["meta"] = pick["genome"]
        state["round"] = r + 1
        state["work"] = {}
        if expl < threshold:
            state["stopped"] = True
            save()
            break
        added = 0
        for x in fresh:
            if x["ratio"] >= threshold and added < b.max_new and _key(x["genome"]) not in {_key(g) for g in
                                                                                           pool.values()}:
                pool[f"round {r + 1} exploit {added + 1}"] = with_tactics(x["genome"])
                added += 1
        save()
    # every round's pick (and the starting agent, for reference) against the final pool, on the same games
    if state["final"] is None:
        watch.context.update(candidate="Known exploit", opponents="Meta agent",
                             about=f"Hardening ({n} players): every round's agent against all the exploits found")
        pool = state["pool"]
        final = []
        for name, g in [("start", state["start"])] + [(f"round {x['round'] + 1}", x["meta"]) for x in state["rounds"]]:
            exp = exposure(g, pool, n, rules, games=b.exposure_games, seed=seed * 20_000, workers=workers)
            final.append({"agent": name, **_worst(exp), "exposure": exp})
        state["final"] = final
        save()
    best = _least_exploited(state["final"], fitness=False)  # the starting agent too: hardening can make it worse
    pick = state["final"][best]
    who = "the starting agent" if best == 0 else f"round {best}'s agent"
    log(f"  [{n}p] hardening done: {who} is the least exploited by the final pool ({pick['worst']:.3f}x, "
        f"{pick['worst_name']}); the starting agent {state['final'][0]['worst']:.3f}x")
    return {"meta": state["start"] if best == 0 else state["rounds"][best - 1]["meta"], "selected_round": best,
            "rounds": state["rounds"], "final": state["final"], "pool": state["pool"]}


def worst_exploit(searches: list[float], known: list[dict]) -> float:
    """An agent's exploitability as measured: the strongest of what the searches found against it and of the
    known exploits played against it."""
    return max([*searches, *(r["ratio"] for r in known)], default=0.0)


def keep_better(old: float, new: float) -> str:
    """Which agent to keep after hardening: the new one only if its worst measured exploit is smaller."""
    return "new" if new < old else "old"
