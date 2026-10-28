"""Meta agents found by evolutionary self-play.

A *genome* is a full set of HeuristicBot parameters: cash buffers, auction aggression,
set-completion and blocking premiums, building caps, jail policy, trade prices and a
buying weight for every colour group. Evolution keeps the genomes that win most often
against the **current population plus a hall of fame of past champions**, rather than
against fixed hand-written bots. That is a cheap form of fictitious play. Iterated, it moves
the population towards strategies that are hard to beat at that table size, i.e. towards
the meta.

Two caveats are built into how results are reported:

* The search is over this bot family only. The meta found here is the best of *these*
  strategies, not provably optimal play.
* "Hard to beat" is measured, not assumed: ``exploitability`` trains a fresh challenger
  against a table of meta agents and reports how far above fair share it gets.
"""
from __future__ import annotations

import os
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from .engine import Game, Rules, championship_rules
from .policies import make_bot

GROUPS = ["brown", "light_blue", "pink", "orange", "red", "yellow", "green", "dark_blue",
          "stations", "utilities"]

CONTINUOUS = {  # name: (low, high)
    "reserve": (0.0, 600.0),
    "build_reserve": (0.0, 600.0),
    "bid_frac": (0.3, 2.0),
    "set_bonus": (1.0, 4.0),
    "block_bonus": (1.0, 3.0),
    "offer_mult": (1.0, 4.0),
    "ask_mult": (1.0, 4.0),
    **{f"w_{g}": (0.0, 2.0) for g in GROUPS},
}
DISCRETE = {
    "build_cap": [3, 4, 5],
    "max_level": [4, 5],
    "jail": ["short", "long", "adaptive"],
    "take_chance": [False, True],
    "trades": [False, True],
    "accept_trades": [False, True],
}

BALANCED = {
    "reserve": 150.0, "build_reserve": 150.0, "bid_frac": 1.0, "set_bonus": 2.0, "block_bonus": 1.3,
    "offer_mult": 2.0, "ask_mult": 2.0, **{f"w_{g}": 1.0 for g in GROUPS},
    "build_cap": 5, "max_level": 5, "jail": "adaptive", "take_chance": False,
    "trades": True, "accept_trades": True,
}


def to_spec(genome: dict, name: str) -> dict:
    """Genome -> keyword arguments for HeuristicBot (what make_bot accepts)."""
    spec = {k: v for k, v in genome.items() if not k.startswith("w_")}
    for k in ("reserve", "build_reserve"):
        spec[k] = int(round(spec[k]))
    spec["group_weight"] = {g: genome[f"w_{g}"] for g in GROUPS}
    spec["name"] = name
    return spec


def random_genome(rng: random.Random) -> dict:
    g = {k: rng.uniform(lo, hi) for k, (lo, hi) in CONTINUOUS.items()}
    g.update({k: rng.choice(v) for k, v in DISCRETE.items()})
    return g


def mutate(genome: dict, rng: random.Random, sigma: float = 0.12, p_discrete: float = 0.1) -> dict:
    """Gaussian step (sigma as a fraction of each range) on ~1/3 of the genes; resample discrete genes."""
    child = dict(genome)
    for k, (lo, hi) in CONTINUOUS.items():
        if rng.random() < 0.35:
            child[k] = min(hi, max(lo, child[k] + rng.gauss(0, sigma * (hi - lo))))
    for k, options in DISCRETE.items():
        if rng.random() < p_discrete:
            child[k] = rng.choice(options)
    return child


# ---------------------------------------------------------------------- evaluation
def game_credit(result, seat: int, n_players: int) -> float:
    """Win credit for `seat`: 1 for an outright win; a game stopped by the time limit is a draw
    shared equally by the players still in it (so stalling can never beat fair share)."""
    return result.credit(seat)


def _eval_chunk(args):
    tasks, rules = args
    out = []
    for cand_idx, game_idx, seat, lineup, seed in tasks:
        r = Game([make_bot(s) for s in lineup], seed=seed, rules=rules).play()
        out.append((cand_idx, game_idx, game_credit(r, seat, len(lineup)), r.capped))
    return out


def evaluate(candidates: list[dict], pool: list[dict], n_players: int, games: int, seed: int,
             rules: Rules | None = None, workers: int | None = None, fixed_opponents: bool = False
             ) -> np.ndarray:
    """Win credit × n_players for each candidate genome (1.0 = fair share when every game ends).

    Every candidate plays the *same* games (same seeds, same opponents, same seat), so
    differences between candidates are not muddied by luck of the draw (common random numbers).
    Games stopped by the time limit are scored by rules.stalemate (GameResult.credit).
    Opponents are drawn from `pool` (genomes) for each game, or are all pool[0] if fixed_opponents.
    After a call, evaluate.last_games holds the per-game credits × n (candidates x games), for
    paired comparisons, and evaluate.last_capped_share the share of each candidate's games
    stopped by the time limit.
    """
    rules = rules or Rules()
    workers = workers or os.cpu_count() or 1
    rng = random.Random(seed)
    schedule = []
    for gi in range(games):
        seat = gi % n_players
        opp = [pool[0] if fixed_opponents else rng.choice(pool) for _ in range(n_players - 1)]
        schedule.append((seat, opp, seed * 1_000_003 + gi))
    tasks = []
    for ci, cand in enumerate(candidates):
        cspec = to_spec(cand, "candidate")
        for gi, (seat, opp, gseed) in enumerate(schedule):
            lineup = [to_spec(o, f"opp{j}") for j, o in enumerate(opp)]
            lineup.insert(seat, cspec)
            tasks.append((ci, gi, seat, lineup, gseed))
    chunks = [(tasks[i::workers], rules) for i in range(workers)]
    if workers == 1:
        results = _eval_chunk(chunks[0])
    else:
        with ProcessPoolExecutor(workers) as ex:
            results = [x for part in ex.map(_eval_chunk, chunks) for x in part]
    per_game = np.zeros((len(candidates), games))
    capped = np.zeros(len(candidates))
    for ci, gi, credit, was_capped in results:
        per_game[ci, gi] = credit
        capped[ci] += was_capped
    evaluate.last_capped_share = capped / games  # diagnostics for the caller
    evaluate.last_games = per_game * n_players
    return per_game.sum(axis=1) / games * n_players


def paired_ratio(a: np.ndarray, b: np.ndarray, n_boot: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Ratio of mean(a) to mean(b) for per-game results played on the same games, with a
    95% bootstrap interval that resamples games (so the pairing is kept)."""
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), size=(n_boot, len(a)))
    boot = a[idx].mean(axis=1) / np.maximum(b[idx].mean(axis=1), 1e-12)
    return float(a.mean() / max(b.mean(), 1e-12)), float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))


# ---------------------------------------------------------------------- evolution
@dataclass
class EvolutionResult:
    n_players: int
    best: dict
    best_fitness: float
    population: list[dict]
    hall_of_fame: list[dict]
    history: list[dict] = field(default_factory=list)


def evolve(n_players: int, generations: int = 12, pop_size: int = 8, games: int = 800,
           seed: int = 0, hof_size: int = 6, init: list[dict] | None = None,
           opponents: list[dict] | None = None, workers: int | None = None,
           rules: Rules | None = None, hof_init: list[dict] | None = None, log=print) -> EvolutionResult:
    """(mu + lambda) evolution strategy with self-play fitness.

    If `opponents` is given, candidates are scored against that fixed table instead of
    against the population (used to train a best-response challenger).
    """
    rng = random.Random(seed)
    population = [dict(g) for g in (init or [])]
    while len(population) < pop_size:
        population.append(random_genome(rng) if len(population) % 2 else mutate(BALANCED, rng, 0.25, 0.3))
    population = population[:pop_size]
    hof: list[dict] = [dict(g) for g in (hof_init or [])]
    history = []
    for gen in range(generations):
        children = [mutate(rng.choice(population), rng) for _ in range(pop_size)]
        candidates = population + children
        if opponents is not None:
            pool, fixed = opponents, True
        else:
            pool, fixed = population + hof, False
        fit = evaluate(candidates, pool, n_players, games, seed=seed * 1000 + gen,
                       rules=rules, workers=workers, fixed_opponents=fixed)
        order = np.argsort(-fit)
        population = [candidates[i] for i in order[:pop_size]]
        champion = candidates[order[0]]
        if opponents is None:
            hof = (hof + [champion])[-hof_size:]
        history.append({"generation": gen, "best": float(fit[order[0]]), "median": float(np.median(fit)),
                        "parents_mean": float(fit[:pop_size].mean())})
        log(f"  [{n_players}p] gen {gen:2d}: best {fit[order[0]]:.2f}x  median {np.median(fit):.2f}x")
    return EvolutionResult(n_players, population[0], float(fit[order[0]]), population, hof, history)


def tournament_rules(n_players: int, rounds: int = 150) -> Rules:
    """Standard (official) rules plus a time limit of `rounds` full rounds, for self-play.

    The limit is well above the 90th-percentile game length at every table size (93 rounds
    at 2 players, 55 at 6) and only stops stalled games, keeping self-play affordable.
    A stopped game scores as a loss for everyone ("loss"). Two other choices were tried and
    each produced a degenerate meta:
      * richest player wins: 5-player self-play learned to refuse trades and run out the clock;
      * shared draw: 5-6 player self-play settled into a trade embargo, because stalling
        guaranteed a fair share.
    Making an unfinished game worthless is the only rule under which stalling never pays.
    """
    return Rules(max_turns=rounds * n_players, stalemate="loss")


def championship_mode(n_players: int, rounds: int = 150) -> Rules:
    """Championship tournament mode (Speed Die, tournament tweaks, finishing-position points)."""
    return championship_rules(n_players, rounds)


def exploitability(meta: dict, n_players: int, generations: int = 6, pop_size: int = 6,
                   games: int = 600, seed: int = 0, workers: int | None = None,
                   rules: Rules | None = None, log=print):
    """Train a challenger against (n-1) copies of `meta`; return its EvolutionResult."""
    res = evolve(n_players, generations=generations, pop_size=pop_size, games=games, seed=seed,
                 init=[meta], opponents=[meta], workers=workers, rules=rules, log=log)
    return res


def self_play_credit(meta: dict, n_players: int, games: int, seed: int, rules: Rules | None = None,
                     workers: int | None = None) -> float:
    """Win credit × n of the meta agent in a table of meta agents (1.0 when every game is decisive)."""
    return float(evaluate([meta], [meta], n_players, games, seed=seed, rules=rules, workers=workers,
                          fixed_opponents=True)[0])


def refine(meta: dict, challenger: dict | None, n_players: int, rules: Rules | None = None, rounds: int = 3,
           threshold: float = 1.05, eval_games: int = 4000, seed: int = 0, workers: int | None = None,
           ckpt=None, log=print) -> tuple[dict, dict, list[dict]]:
    """Best-response iteration: while a challenger beats the meta by more than `threshold`,
    put the challenger into the opponent pool, evolve further, and re-pick the meta.

    This is a small version of the double-oracle / PSRO idea: strategies that exploit the
    current meta become permanent sparring partners, so the next meta has to handle them.

    Exploitability is measured as a *ratio*: the challenger's win credit against a table of
    meta agents divided by the meta agent's own credit at that table, on the same games. With
    "loss" or "championship" scoring a table of meta agents can earn less than 1.0 in total
    (unfinished games pay nobody), so comparing the challenger with 1.0 would understate it.

    Self-play can cycle (strategy A is beaten by B, B by C, C by A). If no round gets below
    `threshold`, the least exploitable meta seen in any round is returned.
    If `challenger` is None a fresh one is trained first. `ckpt` (a pathlib.Path) saves
    progress so a long run can resume. Returns (meta, challenger, per-round log).
    """
    import json

    rng = random.Random(seed)
    state = {"meta": meta, "challenger": challenger, "beaten": [meta], "log": [], "next": 0, "seen": []}
    if ckpt is not None and ckpt.exists():
        state = json.loads(ckpt.read_text())
        log(f"  [{n_players}p] resuming refinement at round {state['next']}")
        if "seen" not in state:  # checkpoint from before 'seen' existed: rebuild it
            b = state["beaten"]
            state["seen"] = [{"round": r["round"], "meta": b[2 * r["round"]], "challenger": b[2 * r["round"] + 1],
                              "ratio": r["challenger_vs_meta"]} for r in state["log"] if 2 * r["round"] + 1 < len(b)]

    def save():
        if ckpt is not None:
            ckpt.write_text(json.dumps(state))

    for it in range(state["next"], rounds + 1):
        meta, challenger, beaten = state["meta"], state["challenger"], state["beaten"]
        if challenger is None:
            challenger = exploitability(meta, n_players, generations=6, pop_size=6, games=700,
                                        seed=seed * 7 + 50 + it, rules=rules, workers=workers, log=log).best
            state["challenger"] = challenger
            save()
        evaluate([challenger, meta], [meta], n_players, eval_games, seed=seed * 10 + it,
                 rules=rules, workers=workers, fixed_opponents=True)
        ch, own = (float(x) for x in evaluate.last_games.mean(axis=1))
        ratio = ch / max(own, 1e-9)
        state["log"].append({"n_players": n_players, "round": it, "challenger_credit": ch,
                             "meta_self_credit": own, "challenger_vs_meta": ratio})
        state["seen"].append({"round": it, "meta": meta, "challenger": challenger, "ratio": ratio})
        log(f"  [{n_players}p] refine round {it}: challenger {ch:.3f} vs meta self-play {own:.3f} "
            f"-> {ratio:.3f}x")
        if ratio < threshold or it == rounds:
            break
        beaten.append(challenger)
        init = [meta, challenger] + [mutate(meta, rng) for _ in range(3)] + [mutate(challenger, rng) for _ in range(3)]
        res = evolve(n_players, generations=8, pop_size=8, games=900, seed=seed * 100 + it, init=init,
                     hof_init=beaten[-6:], rules=rules, workers=workers, log=log)
        pool = res.population + beaten
        fresh = evaluate(res.population, pool, n_players, 3000, seed=seed * 1000 + it, rules=rules,
                         workers=workers)
        meta = res.population[int(fresh.argmax())]
        beaten.append(meta)
        state.update({"meta": meta, "challenger": None, "beaten": beaten, "next": it + 1})
        save()
    best = min(state["seen"], key=lambda r: r["ratio"])
    if best["ratio"] < state["seen"][-1]["ratio"]:
        log(f"  [{n_players}p] self-play cycled: keeping the round-{best['round']} meta "
            f"({best['ratio']:.3f}x), the least exploitable seen")
    for row in state["log"]:
        row["selected"] = row["round"] == best["round"]
    return best["meta"], best["challenger"], state["log"]
