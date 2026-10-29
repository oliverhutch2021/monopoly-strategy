"""Unconventional strategies (v0.4): tactic genes and a quality-diversity search for them.

The meta agents of v0.3 came from evolving the HeuristicBot's ordinary settings. v0.4 asks whether
moves people rarely make do better against them: forcing auctions when rivals are short of cash,
hoarding houses so rivals can't build, borrowing against lone properties to build, sitting in jail by
the numbers, dodging dangerous squares, counting cards, taxing the leader and playing the clock
(TACTICS; HeuristicBot documents each one).

Search. MAP-Elites (Mouret & Clune 2015) over a centroidal Voronoi tessellation of behaviour space
(CVT-MAP-Elites, Vassiliades et al. 2018). A strategy is scored by its win credit at a table of meta
agents, divided by the meta agent's own credit on the same games (the exploitability ratio: above 1
beats the meta), and placed by how it plays (DESCRIPTORS, from the engine's per-player counters). The
archive keeps the best strategy for each region of behaviour, so it holds strong strategies of many
kinds rather than one; odd ideas survive long enough to be refined. The regions are fitted to where
strategies actually go: k-means over the behaviour of the first batch plus some uniform points.

Every candidate plays the same games (seeds and seats), so comparisons are paired; each iteration's
random numbers come from (seed, iteration), so a run is deterministic and resumes exactly from its
checkpoint.

Checking. The archive's scores are optimistic (the best of many noisy scores), so the strongest
strategies, overall and for each tactic, are measured again on fresh games (validate), and a league
of them plays every pairing (league): one of A at a table of B. Its Nash mixture names the
strategies a careful player has to be ready for.
"""
from __future__ import annotations

import json
import os
import random
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from . import watch
from .engine import (ST_AUCTION, ST_BOUGHT, ST_BUILT, ST_CASH, ST_HOTELS, ST_JAIL, ST_LEVELS, ST_MORTGAGED,
                     ST_TRADES, ST_TURNS, STAT_FIELDS, Game, Rules)
from .meta import BALANCED, CONTINUOUS, mutate, paired_ratio, random_genome, to_spec
from .policies import make_bot

# ---------------------------------------------------------------------- the tactic genes
TACTICS = {  # gene: (off, low, high). A tactic is either off or somewhere in [low, high].
    "snipe": (0.0, 0.3, 1.0),
    "lock": (0, 4, 24),
    "leverage": (0.0, 0.2, 1.0),
    "jail_exposure": (0.0, 20.0, 250.0),
    "dodge": (0.0, 0.2, 3.0),
    "count_cards": (False, True, True),
    "leader_tax": (1.0, 1.25, 3.0),
    "endgame_rounds": (0, 3, 40),
}
INT_TACTICS = {"lock", "endgame_rounds"}
ENDGAME_RESERVE = (0.0, 1000.0)  # the cash reserve kept while playing the clock
TACTIC_NAMES = {
    "snipe": "auction sniping", "lock": "housing lock", "leverage": "borrowing to build",
    "jail_exposure": "jail by the numbers", "dodge": "dodging", "count_cards": "card counting",
    "leader_tax": "taxing the leader", "endgame_rounds": "playing the clock",
}


def tactics_on(genome: dict) -> list[str]:
    return [k for k, (off, _, _) in TACTICS.items() if genome.get(k, off) != off]


def with_tactics(genome: dict) -> dict:
    """A genome with every tactic gene present (missing ones off): v0.3 genomes become v0.4 ones."""
    g = dict(genome)
    for k, (off, _, _) in TACTICS.items():
        g.setdefault(k, off)
    g.setdefault("endgame_reserve", 0.0)
    return g


def draw_tactic(k: str, rng: random.Random):
    off, lo, hi = TACTICS[k]
    if isinstance(off, bool):
        return True
    return rng.randint(lo, hi) if k in INT_TACTICS else rng.uniform(lo, hi)


def random_genome_ext(rng: random.Random, p_on: float = 0.25) -> dict:
    g = random_genome(rng)
    for k, (off, _, _) in TACTICS.items():
        g[k] = draw_tactic(k, rng) if rng.random() < p_on else off
    g["endgame_reserve"] = rng.uniform(*ENDGAME_RESERVE)
    return g


def vary(parent: dict, rng: random.Random, other: dict | None = None, p_toggle: float = 0.06) -> dict:
    """A child of `parent`. The ordinary genes mutate as in v0.3 (meta.mutate). With `other`, the child
    also takes a random step along the line from parent to other (Iso+LineDD) and some of other's
    tactics. Each tactic is switched on or off with probability p_toggle, and nudged when on."""
    parent = with_tactics(parent)
    child = mutate(parent, rng)
    if other is not None:
        other = with_tactics(other)
        t = rng.gauss(0, 0.3)
        for k, (lo, hi) in CONTINUOUS.items():
            child[k] = min(hi, max(lo, child[k] + t * (other[k] - parent[k])))
        for k in TACTICS:
            if rng.random() < 0.3:
                child[k] = other[k]
    for k, (off, lo, hi) in TACTICS.items():
        on = child[k] != off
        if rng.random() < p_toggle:
            child[k] = off if on else draw_tactic(k, rng)
        elif on and not isinstance(off, bool) and rng.random() < 0.35:
            v = min(hi, max(lo, child[k] + rng.gauss(0, 0.12 * (hi - lo))))
            child[k] = int(round(v)) if k in INT_TACTICS else v
    if rng.random() < 0.35:
        lo, hi = ENDGAME_RESERVE
        child["endgame_reserve"] = min(hi, max(lo, child["endgame_reserve"] + rng.gauss(0, 0.12 * (hi - lo))))
    return child


def seed_genomes(meta: dict) -> list[dict]:
    """Where the search starts besides random genomes: the meta agent and the simple bot, each with
    every single tactic switched on at the middle of its range."""
    out = []
    for base in (with_tactics(meta), with_tactics(BALANCED)):
        out.append(dict(base))
        for k, (off, lo, hi) in TACTICS.items():
            mid = True if isinstance(off, bool) else (lo + hi) / 2
            out.append({**base, k: int(round(mid)) if k in INT_TACTICS else mid,
                        **({"endgame_reserve": 300.0} if k == "endgame_rounds" else {})})
    return out


# ---------------------------------------------------------------------- how a strategy plays
DESCRIPTORS = ("cash", "acquire", "auctions", "trades", "build", "hotels", "jail", "mortgaged")
DESCRIPTOR_TEXT = {
    "cash": "average cash held (0 to £2,500)",
    "acquire": "properties gained per game, as a share of twice a fair share",
    "auctions": "share of those won at auction",
    "trades": "trades per game (0 to 3)",
    "build": "average building levels owned (0 to 20)",
    "hotels": "share of built squares with a hotel",
    "jail": "share of own turns starting in jail (0 to 40%)",
    "mortgaged": "average mortgaged properties held (0 to 6)",
}


def describe(stats, games: int, n_players: int, n_ownable: int = 28) -> list[float]:
    """Behaviour descriptors in [0, 1] from a strategy's summed STAT_FIELDS counters over `games` games."""
    st = stats
    turns = max(1, st[ST_TURNS])
    acq = st[ST_BOUGHT] + st[ST_AUCTION]
    return [
        min(1.0, st[ST_CASH] / turns / 2500),
        min(1.0, acq / max(1, games) / (n_ownable / n_players) / 2),
        st[ST_AUCTION] / acq if acq else 0.0,
        min(1.0, st[ST_TRADES] / max(1, games) / 3),
        min(1.0, st[ST_LEVELS] / turns / 20),
        st[ST_HOTELS] / st[ST_BUILT] if st[ST_BUILT] else 0.0,
        min(1.0, st[ST_JAIL] / turns / 0.4),
        min(1.0, st[ST_MORTGAGED] / turns / 6),
    ]


# ---------------------------------------------------------------------- playing candidates
def _lineup(table, spec, n: int, seat: int) -> list:
    return [spec if q == seat else table for q in range(n)]


def _play_chunk(args):
    specs, table, n, tasks, rules = args  # the specs travel once per chunk, not once per game
    out = []
    for ci, gi, seat, seed in tasks:
        g = Game([make_bot(s) for s in _lineup(table, specs[ci], n, seat)], seed=seed, rules=rules,
                 track_stats=True)
        r = g.play()
        out.append((ci, gi, r.credit(seat), r.capped, g.stats[seat]))
    return out


class Arena:
    """Plays candidate strategies, one at a time, at a table of copies of `table`, on a fixed list of
    games (seat and seed); the same games for every candidate, so comparisons are paired. Keeps a pool
    of worker processes open between batches."""

    def __init__(self, table: dict, n_players: int, rules: Rules, games: int, seed: int,
                 workers: int | None = None, table_name: str = "Meta agent"):
        self.n, self.rules = n_players, rules
        self.table = to_spec(table, table_name) if isinstance(table, dict) and "group_weight" not in table else table
        self.schedule = [(gi % n_players, seed * 1_000_003 + gi) for gi in range(games)]
        self.workers = workers or os.cpu_count() or 1
        self.ex = ProcessPoolExecutor(self.workers) if self.workers > 1 else None

    def play(self, candidates: list[dict], name: str = "Candidate") -> list[dict]:
        """Per candidate: credit (mean win credit x n_players), games (per-game credit x n), capped
        (share of games stopped by the time limit) and stats (summed STAT_FIELDS)."""
        specs = [to_spec(c, name) if "group_weight" not in c else c for c in candidates]
        tasks = [(ci, gi, seat, gseed) for ci in range(len(specs)) for gi, (seat, gseed) in enumerate(self.schedule)]
        k = max(1, min(len(tasks), self.workers * 3))
        chunks = [(specs, self.table, self.n, tasks[i::k], self.rules) for i in range(k)]
        if watch.folder():  # the live viewer: offer one of these games for replay
            watch.sample(tasks, self.rules, lambda t: {"lineup": _lineup(self.table, specs[t[0]], self.n, t[2]),
                                                       "seat": t[2], "seed": t[3]})
        t0 = watch.started(len(tasks))
        parts = map(_play_chunk, chunks) if self.ex is None else self.ex.map(_play_chunk, chunks)
        games = len(self.schedule)
        out = [{"games": np.zeros(games), "capped": 0, "stats": [0] * len(STAT_FIELDS)} for _ in candidates]
        for part in parts:
            for ci, gi, credit, capped, stats in part:
                o = out[ci]
                o["games"][gi] = credit * self.n
                o["capped"] += capped
                o["stats"] = [a + b for a, b in zip(o["stats"], stats)]
        watch.finished(len(tasks), t0)
        for o in out:
            o["credit"] = float(o["games"].mean())
            o["capped"] /= games
        return out

    def close(self) -> None:
        if self.ex is not None:
            self.ex.shutdown()
            self.ex = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ---------------------------------------------------------------------- the archive
def kmeans(points: np.ndarray, k: int, seed: int, iters: int = 60) -> np.ndarray:
    """Lloyd's algorithm with k-means++ starts (numpy only, deterministic given the seed)."""
    rng = np.random.default_rng(seed)
    pts = np.asarray(points, dtype=float)
    centres = [pts[rng.integers(len(pts))]]
    for _ in range(1, k):
        d2 = np.min(((pts[:, None, :] - np.asarray(centres)[None]) ** 2).sum(-1), axis=1)
        total = d2.sum()
        centres.append(pts[rng.choice(len(pts), p=d2 / total)] if total > 0 else pts[rng.integers(len(pts))])
    c = np.asarray(centres)
    for _ in range(iters):
        lab = np.argmin(((pts[:, None, :] - c[None]) ** 2).sum(-1), axis=1)
        new = np.array([pts[lab == j].mean(axis=0) if np.any(lab == j) else c[j] for j in range(k)])
        if np.allclose(new, c):
            break
        c = new
    return c


def fit_cells(descs: list[list[float]], cells: int, seed: int) -> list[list[float]]:
    """Region centres: k-means over the first batch's behaviour and a jittered copy of it, so the regions
    sit where strategies actually play, with a margin around it for behaviour the first batch never
    showed. (Uniform points instead would leave many regions where nothing can play.)"""
    rng = np.random.default_rng(seed + 1)
    d = np.asarray(descs, dtype=float)
    pts = np.vstack([d, np.clip(d + rng.normal(0, 0.08, d.shape), 0, 1)])
    return np.round(kmeans(pts, cells, seed), 6).tolist()


def nearest(centres: np.ndarray, x) -> int:
    return int(np.argmin(((centres - np.asarray(x)) ** 2).sum(axis=1)))


def _elite(genome: dict, res: dict, meta_credit: float, desc: list[float], born: int) -> dict:
    return {"genome": genome, "fitness": res["credit"] / max(meta_credit, 1e-9), "credit": res["credit"],
            "capped": res["capped"], "desc": [round(x, 4) for x in desc], "born": born, "tactics": tactics_on(genome)}


def insert(state: dict, genome: dict, res: dict, n_ownable: int = 28) -> bool:
    """Put a played strategy in its region if the region is empty or it beats the elite there."""
    desc = describe(res["stats"], len(res["games"]), state["n_players"], n_ownable)
    cell = str(nearest(np.asarray(state["centroids"]), desc))
    e = _elite(genome, res, state["meta_credit"], desc, state["evals"])
    cur = state["elites"].get(cell)
    if cur is None or e["fitness"] > cur["fitness"]:
        state["elites"][cell] = e
        return True
    return False


def summary(state: dict) -> dict:
    el = list(state["elites"].values())
    if not el:
        return {"evals": state["evals"], "filled": 0}
    fit = np.array([e["fitness"] for e in el])
    plain = [e["fitness"] for e in el if not e["tactics"]]
    return {"iteration": state["iteration"], "evals": state["evals"], "filled": len(el), "best": float(fit.max()),
            "mean": float(fit.mean()), "best_plain": max(plain) if plain else None,
            "with_tactics": sum(1 for e in el if e["tactics"])}


def search(meta: dict, n_players: int, rules: Rules, *, seed: int, games: int, cells: int, init: int, batch: int,
           evals: int, workers: int | None = None, ckpt: Path | None = None, log=print) -> dict:
    """CVT-MAP-Elites against a table of meta agents. Returns the archive state (also saved to `ckpt`
    after every batch, from which an interrupted search resumes exactly)."""
    if ckpt is not None and ckpt.exists():
        state = json.loads(ckpt.read_text())
        if (state["games"], state["cells"]) != (games, cells):
            raise SystemExit(f"{ckpt} was made with {state['games']} games and {state['cells']} regions, not "
                             f"{games} and {cells}: delete it to start this search again")
        log(f"  [{n_players}p] resuming the search at {state['evals']} strategies tried")
    else:
        state = {"version": 1, "n_players": n_players, "seed": seed, "games": games, "cells": cells,
                 "meta": meta, "meta_credit": None, "centroids": None, "pending": [], "elites": {},
                 "evals": 0, "iteration": 0, "history": []}

    def save():
        if ckpt is not None:
            tmp = ckpt.with_suffix(".tmp")
            tmp.write_text(json.dumps(state))
            os.replace(tmp, ckpt)

    with Arena(meta, n_players, rules, games, seed, workers) as arena:
        n_own = 28
        if state["meta_credit"] is None:
            state["meta_credit"] = arena.play([with_tactics(meta)], name="Meta agent")[0]["credit"]
            save()
        if state["centroids"] is None:
            # 1. a first batch: the seeds and random genomes; its behaviour shapes the regions
            rng = random.Random(f"{seed}:init")
            starts = seed_genomes(meta)
            starts += [random_genome_ext(rng) for _ in range(max(0, init - len(starts)))]
            done = len(state["pending"])
            for i in range(done, len(starts), batch):
                part = starts[i:i + batch]
                for g, res in zip(part, arena.play(part)):
                    state["pending"].append({"genome": g, "credit": res["credit"], "capped": res["capped"],
                                             "stats": res["stats"]})
                state["evals"] = len(state["pending"])
                save()
            descs = [describe(p["stats"], games, n_players, n_own) for p in state["pending"]]
            state["centroids"] = fit_cells(descs, cells, seed)
            for p in state["pending"]:
                insert(state, p["genome"], {"credit": p["credit"], "capped": p["capped"], "stats": p["stats"],
                                            "games": [0] * games}, n_own)
            state["pending"] = []
            state["history"].append(summary(state))
            save()
            s = state["history"][-1]
            log(f"  [{n_players}p] first batch: {s['filled']} of {cells} regions filled, "
                f"best {s['best']:.3f}x the meta")
        # 2. MAP-Elites: children of random elites, each kept if it is the best in its region
        while state["evals"] < evals:
            rng = random.Random(f"{seed}:{state['iteration']}")
            keys = sorted(state["elites"], key=int)
            kids = []
            for _ in range(min(batch, evals - state["evals"])):
                parent = state["elites"][rng.choice(keys)]["genome"]
                other = state["elites"][rng.choice(keys)]["genome"] if rng.random() < 0.5 else None
                kids.append(vary(parent, rng, other))
            for kid, res in zip(kids, arena.play(kids)):
                insert(state, kid, res, n_own)
            state["evals"] += len(kids)
            state["iteration"] += 1
            state["history"].append(summary(state))
            save()
            if state["iteration"] % 10 == 0 or state["evals"] >= evals:
                s = state["history"][-1]
                plain = f"{s['best_plain']:.3f}x" if s["best_plain"] is not None else "-"
                log(f"  [{n_players}p] {s['evals']:5d} tried: {s['filled']} regions, best {s['best']:.3f}x "
                    f"(without tactics {plain}), {s['with_tactics']} elites use a tactic")
    return state


# ---------------------------------------------------------------------- checking the finds
def pick_finalists(state: dict, top: int = 8) -> list[dict]:
    """The strongest elites overall, the strongest using each tactic, and the strongest using none."""
    el = sorted(state["elites"].values(), key=lambda e: -e["fitness"])
    chosen = el[:top]
    for k in TACTICS:
        best = next((e for e in el if k in e["tactics"]), None)
        if best is not None:
            chosen.append(best)
    plain = next((e for e in el if not e["tactics"]), None)
    if plain is not None:
        chosen.append(plain)
    seen, out = set(), []
    for e in chosen:
        key = json.dumps(e["genome"], sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def validate(finalists: list[dict], meta: dict, n_players: int, rules: Rules, *, seed: int, games: int,
             workers: int | None = None) -> list[dict]:
    """Each finalist and the meta agent on fresh games at a table of meta agents; the paired ratio of
    their credits with a 95% bootstrap interval."""
    with Arena(meta, n_players, rules, games, seed, workers) as arena:
        res = arena.play([e["genome"] for e in finalists] + [with_tactics(meta)])
    base = res[-1]
    rows = []
    for i, (e, r) in enumerate(zip(finalists, res[:-1])):
        ratio, lo, hi = paired_ratio(r["games"], base["games"], seed=seed + i)
        rows.append({"search_fitness": e["fitness"], "ratio": ratio, "ci_low": lo, "ci_high": hi,
                     "credit": r["credit"], "meta_credit": base["credit"], "capped": r["capped"],
                     "tactics": e["tactics"], "desc": describe(r["stats"], games, n_players), "genome": e["genome"]})
    return rows


def league_picks(meta: dict, rows: list[dict], size: int = 10) -> dict:
    """The league's members: the meta agent, the simple bot, the top three finds (validated rows), and the
    best find for each tactic and for none; at most `size`, each genome once."""
    picks = {"meta agent": with_tactics(meta), "simple bot": with_tactics(BALANCED)}
    ranked = sorted(rows, key=lambda r: -r["ratio"])
    for i, r in enumerate(ranked[:3], 1):
        picks[f"find {i}"] = r["genome"]
    for k in TACTICS:
        r = next((r for r in ranked if k in r["tactics"]), None)
        if r is not None:
            picks[f"best {TACTIC_NAMES[k]}"] = r["genome"]
    r = next((r for r in ranked if not r["tactics"]), None)
    if r is not None:
        picks["best without tactics"] = r["genome"]
    out, seen = {}, set()
    for name, gnm in picks.items():
        key = json.dumps(gnm, sort_keys=True)
        if key not in seen and len(out) < size:
            seen.add(key)
            out[name] = gnm
    return out


def league(strategies: dict[str, dict], n_players: int, rules: Rules, *, seed: int, games: int,
           workers: int | None = None, log=print) -> np.ndarray:
    """M[a, b]: win credit of one `a` at a table of `b`s, divided by a `b`'s own credit there (paired:
    the same games). M[a, b] > 1 means a can invade a table of b."""
    names = list(strategies)
    m = np.ones((len(names), len(names)))
    for j, b in enumerate(names):
        with Arena(strategies[b], n_players, rules, games, seed + 31 * j, workers, table_name=b) as arena:
            res = arena.play([strategies[a] for a in names], name="Challenger")
        own = max(res[j]["credit"], 1e-9)
        m[:, j] = [r["credit"] / own for r in res]
        log(f"  [{n_players}p] league: table of {b} done")
    return m


def nash_mixture(m: np.ndarray, iters: int = 20000) -> np.ndarray:
    """Nash mixture of the symmetric zero-sum game with payoff log M[a, b] - log M[b, a] (who invades
    whom more easily), by fictitious play."""
    p = np.log(np.maximum(m, 1e-9))
    p = p - p.T
    counts = np.zeros(len(m))
    counts[0] = 1.0
    for _ in range(iters):
        counts[int(np.argmax(p @ (counts / counts.sum())))] += 1.0
    return counts / counts.sum()
