"""Do the housing findings survive the rules the engine simplifies? (from the methodology review, 2026-10-30)

    MM_RESULTS=results/final python scripts/15_rule_sensitivity.py

The engine lets players build only after their own move, and the last houses go to whoever builds first. The
official rules let anyone build at any time, and auction the houses when two or more players want more than the
bank has. The engine also leaves mortgaged stations and utilities out of the count that sets their rent, and a
player who receives a mortgaged deed always pays the 10% then (and again on lifting it later), where the official
rules let them lift it at once for its value + 10% instead. This replays the comparisons the housing findings rest
on under each variant (engine.Rules: build_any_time, house_auctions, both, mortgaged_count_for_rent,
mortgage_transfer_choice), on the same seeds in every variant, from a seed offset no other study uses:

1. Candidates, each in one seat at a table of final meta agents, relative to the final agent in that seat on the
   same games: the agent's strongest known challenger, a hard three-house cap (max_level 3), three houses first
   (build_cap 3, the old "three-house cap" ablation, which still builds hotels), the housing lock switched off (or
   on, at 14 houses, for an agent without it) and the simple bot. A candidate that is the final agent itself (or
   repeats another) is left out and listed. At 4 players under official rules (the review's suggestion) and in the
   settings whose agents use the lock (official 2 players, championship 4 players). In house auctions each bot
   bids for one named house, the next it would build (the affordable square that adds the most rent per pound,
   within its building caps), up to (1 + its property-auction limit) x that house's price and within its cash
   buffer; a won house goes on that square and costs at most the bid (policies.HeuristicBot.house_bid). That
   bidding rule is one heuristic, not a searched policy.
2. Whether a variant changes a candidate's edge: its ratio under the variant ÷ its ratio under the engine's rules,
   with a bootstrap that resamples the same games (seeds) in both, so the pairing across variants is kept.
   Intervals are 95%, and also Bonferroni-adjusted for the number of such comparisons (a normal approximation on
   the log scale, from the same bootstrap). Each comparison is then read against a tolerance of ±3%, set before the
   run (a change that small can't reverse a verdict in these tables whose interval is more than 3% from 1):
   changed (the adjusted interval excludes 1 and reaches past the tolerance), a small change (it excludes 1 but stays
   within the tolerance), equivalent (it includes 1 and stays within the tolerance) or inconclusive. Each game's
   credits are kept (games/<setting>.npz), and where the previous run's are too (games/<setting>.previous.npz), the
   summary lists how each ratio moved, with a bootstrap that resamples the same seeds in both runs; where only the
   previous run's table exists, the interval treats the two runs as independent (wider than it should be).
3. How often the simplifications bind, between final agents: the share of games in which two or more players
   wanted more houses than the bank had, the houses auctioned per game under the official rule, the games in which
   two or more wanted more hotels than the bank had (the engine never auctions hotels, the official rules do), and
   the mortgaged deeds received per game (and lifted at once, given the choice).
4. Seat order with simple bots at 4 and 6 players.
5. The housing lock taken apart, for the official 4-player agent. It does two things: it defers hotels while houses
   are short, and when raising cash it mortgages everything else before selling a building (policies: lock and
   protect). Four arms (neither, each alone, both) on the same games, against four populations in the other seats:
   final agents (on the games of the earlier fresh-seed confirmation, and on fresh games), simple bots, an equal
   mixture per seat of the final agent, the simple bot and the strongest known challenger, and known challengers.
   "Both" against final agents on the confirmation's games is that confirmation (confirm.csv), reproduced.

Outputs, under <results>/tables/sensitivity/: candidates.csv (and candidates_previous.csv, the run it replaced),
games/<setting>.npz (and .previous.npz), housing.csv, seats.csv, lock_factorial.csv, confirm.csv, summary.md,
variants.json. candidates_pre_auction_fix.csv is the first review's run, before house auctions were fixed (kept for
the write-up's account of that fix).
"""
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace

from statistics import NormalDist

import numpy as np
import pandas as pd

from meta_common import MODES, TAB, ckpt_dir, rules_for
from run_config import scaled
from monopoly_meta.engine import Game, Rules
from monopoly_meta.meta import BALANCED, evaluate, paired_ratio, to_spec
from monopoly_meta.policies import make_bot
from monopoly_meta.tournament import run_games, win_rates

OUT = TAB / "sensitivity"
ENGINE = "engine rules"
VARIANTS = {ENGINE: {}, "build any time": {"build_any_time": True},
            "house auctions": {"house_auctions": True},
            "any time + auctions": {"build_any_time": True, "house_auctions": True},
            "mortgaged stations count": {"mortgaged_count_for_rent": True},
            "mortgage choice on transfer": {"mortgage_transfer_choice": True}}
BINDING = (ENGINE, "house auctions", "any time + auctions", "mortgage choice on transfer")  # counted in housing()
SETTINGS = [("standard", 4), ("standard", 2), ("championship", 4)]
GAMES = scaled(2000)          # paired games per candidate and variant (20,000 at MM_SCALE=10)
HOUSING_GAMES = scaled(500)   # games per setting for the housing counts
SEAT_GAMES = scaled(2000)
SEED = 7_777_000              # offset from each mode's seed for evaluate(): no other study uses these seeds
CONFIRM_SEED = 7_888_000      # fresh seeds for the confirmation (2026-10-31): the factorial's first schedule
CONFIRM_GAMES = scaled(4000)  # 40,000 at MM_SCALE=10
LOCK_SEED = 7_999_000         # fresh seeds for the factorial's other schedules
LOCK_GAMES = scaled(2000)     # 20,000 paired games per schedule at MM_SCALE=10
TOLERANCE = 0.03              # a variant ÷ engine-rules ratio within 1 ± this is a practically equivalent edge
BOOT = 2000
GAMES_DIR = OUT / "games"
LOCK_ARMS = {"neither": {"lock": 0, "protect": False}, "defer hotels only": {"protect": False},
             "protect buildings only": {"lock": 0, "protect": True}, "both (the housing lock)": {"protect": True}}


def candidates(mode: str, n: int) -> tuple[dict, list[str]]:
    """{name: genome}, the final agent first, and the names left out because they repeat an earlier genome."""
    meta = {k: v for k, v in json.loads((TAB / f"meta_agents_{mode}.json").read_text())[str(n)].items()
            if k != "name"}
    ck = json.loads((ckpt_dir(mode) / f"{n}p.json").read_text())
    lock = meta.get("lock", 0)
    wanted = {"final agent": meta, "strongest known challenger": ck["challenger"],
              "hard three-house cap": {**meta, "max_level": 3}, "three houses first": {**meta, "build_cap": 3},
              ("housing lock off" if lock else "housing lock on (14)"): {**meta, "lock": 0 if lock else 14},
              "simple bot": dict(BALANCED)}
    kept, dropped = {}, []
    for name, genome in wanted.items():
        g = {k: v for k, v in genome.items() if k != "name"}
        same = next((k for k, v in kept.items() if v == g), None)
        if same:
            dropped.append(f"{name} (the same genome as the {same})")
        else:
            kept[name] = g
    return kept, dropped


def joint_bootstrap(games: dict, boot: int = BOOT, seed: int = 0) -> tuple[dict, dict]:
    """Ratios of each candidate to the final agent (row 0) under each variant, and each variant's ratio ÷ the
    engine-rules ratio, with 95% intervals. Every variant played the same seeds, so a resample of seeds is applied
    to all of them at once (multinomial weights: the same as resampling game indices)."""
    names = list(games)
    x = np.concatenate([games[v] for v in names])            # (variants x candidates, games)
    k, g = games[names[0]].shape
    rng = np.random.default_rng(seed)
    draws = []
    for start in range(0, boot, 100):
        w = rng.multinomial(g, np.full(g, 1 / g), size=min(100, boot - start))
        draws.append(w @ x.T / g)                           # (resamples, variants x candidates) means
    means = np.concatenate(draws).reshape(boot, len(names), k)
    point = x.mean(axis=1).reshape(len(names), k)
    ratio = point / np.maximum(point[:, :1], 1e-12)
    r_boot = means / np.maximum(means[:, :, :1], 1e-12)
    q = lambda a: (np.quantile(a, 0.025, axis=0), np.quantile(a, 0.975, axis=0))  # noqa: E731
    lo, hi = q(r_boot)
    i_boot = r_boot / np.maximum(r_boot[:, :1, :], 1e-12)
    ilo, ihi = q(i_boot)
    inter = ratio / np.maximum(ratio[:1, :], 1e-12)
    log_se = np.log(np.maximum(i_boot, 1e-12)).std(axis=0, ddof=1)
    out_r = {v: (ratio[j], lo[j], hi[j]) for j, v in enumerate(names)}
    out_i = {v: (inter[j], ilo[j], ihi[j], log_se[j]) for j, v in enumerate(names)}
    return out_r, out_i


def compare(mode: str, n: int) -> tuple[list[dict], list[str]]:
    cands, dropped = candidates(mode, n)
    names, genomes = list(cands), list(cands.values())
    games, capped = {}, {}
    for variant, flags in VARIANTS.items():
        rules = replace(rules_for(mode, n), **flags)
        t = time.time()
        evaluate(genomes, [genomes[0]], n, GAMES, seed=MODES[mode]["seed"] + SEED + n, rules=rules,
                 fixed_opponents=True)
        games[variant], capped[variant] = np.asarray(evaluate.last_games, float), evaluate.last_capped_share
        print(f"  {mode} {n}p, {variant}: {time.time() - t:.0f}s", flush=True)
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    per_game = {f"{v}|{name}": games[v][i].astype(np.float32) for v in VARIANTS for i, name in enumerate(names)}
    np.savez_compressed(GAMES_DIR / f"{mode}_{n}p.new.npz", **per_game)
    ratios, inter = joint_bootstrap(games, seed=n)
    rows = []
    for variant in VARIANTS:
        (r, lo, hi), (ir, ilo, ihi, lse) = ratios[variant], inter[variant]
        for i, name in enumerate(names):
            rows.append({"mode": mode, "n_players": n, "variant": variant, "candidate": name, "ratio": r[i],
                         "ci_low": lo[i], "ci_high": hi[i], "vs_engine_rules": ir[i], "vs_engine_low": ilo[i],
                         "vs_engine_high": ihi[i], "vs_engine_log_se": lse[i],
                         "credit": float(games[variant][i].mean()),
                         "capped_share": float(capped[variant][i]), "games": GAMES})
    return rows, dropped


def _housing(args):
    genome, n, rules, seeds = args
    out = []
    for seed in seeds:
        g = Game([make_bot(to_spec(genome, "meta")) for _ in range(n)], rules=rules, seed=seed)
        g.track_housing = True
        r = g.play()
        out.append((g.contested_houses, g.house_auctions_held, r.capped, g.contested_hotels, g.mortgaged_received,
                    g.lifted_on_receipt))
    return out


def housing(mode: str, n: int) -> list[dict]:
    meta = candidates(mode, n)[0]["final agent"]
    rows = []
    workers = os.cpu_count() or 1
    for variant in BINDING:
        rules = replace(rules_for(mode, n), **VARIANTS[variant])
        base = 700_000_000 + MODES[mode]["seed"] * 1_000 + n * 100_000
        seeds = list(range(base, base + HOUSING_GAMES))
        with ProcessPoolExecutor(workers) as ex:
            res = np.array([r for part in ex.map(_housing, [(meta, n, rules, seeds[i::workers])
                                                            for i in range(workers)]) for r in part], float)
        contested, auctions, capped, hotels, received, lifted = res.T
        # contested_checks_per_game counts the checks that found contested demand: once or twice per turn, and
        # once per player per turn when building is allowed at any time, so it doesn't compare across variants
        rows.append({"mode": mode, "n_players": n, "variant": variant, "games": len(res),
                     "games_with_contested_houses": float((contested > 0).mean()),
                     "contested_checks_per_game": float(contested.mean()),
                     "houses_auctioned_per_game": float(auctions.mean()),
                     "games_with_contested_hotels": float((hotels > 0).mean()),
                     "mortgaged_received_per_game": float(received.mean()),
                     "lifted_at_once_per_game": float(lifted.mean()),
                     "capped_share": float(capped.mean())})
    return rows


def seats() -> list[dict]:
    rows = []
    for n in (4, 6):
        for variant, flags in VARIANTS.items():
            df = run_games(["balanced"] * n, SEAT_GAMES, seed0=90_000_000 + n * 1_000_000, rotate=False,
                           rules=Rules(**flags))
            wr = win_rates(df, by="seat")
            first, last = wr.iloc[0], wr.iloc[-1]
            rows.append({"n_players": n, "variant": variant, "games": SEAT_GAMES,
                         "first_relative": first.win_rate * n, "first_ci_low": first.ci_low * n,
                         "first_ci_high": first.ci_high * n, "last_relative": last.win_rate * n,
                         "capped_share": float(df.capped.mean())})
    return rows


def paired_diff(a: np.ndarray, b: np.ndarray, n_boot: int = BOOT, seed: int = 0) -> tuple[float, float, float]:
    """mean(a) - mean(b) for results on the same games, with a 95% bootstrap interval that resamples games."""
    d = np.asarray(a, float) - np.asarray(b, float)
    rng = np.random.default_rng(seed)
    boot = np.empty(n_boot)
    for start in range(0, n_boot, 100):
        m = min(100, n_boot - start)
        boot[start:start + m] = d[rng.integers(0, len(d), size=(m, len(d)))].mean(axis=1)
    return float(d.mean()), float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))


def lock_factorial() -> tuple[list[dict], list[dict]]:
    """The housing lock's two behaviours apart (LOCK_ARMS) for the official 4-player agent, each arm on the same games,
    against four populations in the other three seats. Returns the factorial's rows, and the confirmation of
    2026-10-31 (both ÷ neither on its games: the agent with the lock ÷ the agent as it is) reproduced."""
    cands, _ = candidates("standard", 4)
    meta = cands["final agent"]
    challenger = {k: v for k, v in json.loads((ckpt_dir("standard") / "4p.json").read_text())["challenger"].items()
                  if k != "name"}
    arms = {name: {**meta, "lock": meta.get("lock") or 14, **genes} for name, genes in LOCK_ARMS.items()}
    names, simple = list(arms), dict(BALANCED)
    first, fresh = MODES["standard"]["seed"] + CONFIRM_SEED + 4, MODES["standard"]["seed"] + LOCK_SEED + 4
    schedules = [("final agents", "the confirmation's games", [meta], True, CONFIRM_GAMES, first),
                 ("final agents", "fresh games", [meta], True, LOCK_GAMES, fresh),
                 ("simple bots", "fresh games", [simple], True, LOCK_GAMES, fresh + 1),
                 ("equal mixture per seat", "fresh games", [meta, simple, challenger], False, LOCK_GAMES, fresh + 2),
                 ("known challengers", "fresh games", [challenger], True, LOCK_GAMES, fresh + 3)]
    rows, conf = [], []
    both, protect = names.index("both (the housing lock)"), names.index("protect buildings only")
    for opponents, label, pool, fixed, games, seed in schedules:
        t = time.time()
        evaluate(list(arms.values()), pool, 4, games, seed=seed, rules=rules_for("standard", 4),
                 fixed_opponents=fixed)
        wins = np.asarray(evaluate.last_games, float) / 4  # official rules: outright wins
        print(f"  lock factorial, {opponents} ({label}): {time.time() - t:.0f}s", flush=True)
        base = {"opponents": opponents, "schedule": label, "games": games, "seed": seed}
        for i, name in enumerate(names):
            r, lo, hi = paired_ratio(wins[i], wins[0], seed=4)
            d, dlo, dhi = paired_diff(wins[i], wins[0], seed=4)
            rows.append({**base, "arm": name, "win_rate": float(wins[i].mean()), "ratio": r, "ci_low": lo,
                         "ci_high": hi, "gain_pp": 100 * d, "gain_low_pp": 100 * dlo, "gain_high_pp": 100 * dhi})
        d, dlo, dhi = paired_diff(wins[protect], wins[both], seed=5)
        r, lo, hi = paired_ratio(wins[protect], wins[both], seed=5)
        rows.append({**base, "arm": "protect only ÷ both", "win_rate": np.nan, "ratio": r, "ci_low": lo, "ci_high": hi,
                     "gain_pp": 100 * d, "gain_low_pp": 100 * dlo, "gain_high_pp": 100 * dhi})
        if label == "the confirmation's games":
            r, lo, hi = paired_ratio(wins[both], wins[0], seed=4)
            conf.append({"mode": "standard", "n_players": 4, "candidate": "housing lock on (14)", "ratio": r,
                         "ci_low": lo, "ci_high": hi, "games": games, "seed_offset": CONFIRM_SEED})
    return rows, conf


def adjust(cand: pd.DataFrame) -> pd.DataFrame:
    """Bonferroni-adjusted intervals for every variant ÷ engine-rules comparison (normal on the log scale), and each
    comparison's reading: changed (the adjusted interval excludes 1), equivalent (it lies within 1 ± TOLERANCE) or
    inconclusive."""
    cand = cand.copy()
    tests = (cand.variant != ENGINE) & (cand.candidate != "final agent")
    z = NormalDist().inv_cdf(1 - 0.025 / max(int(tests.sum()), 1))
    log_r = np.log(cand.vs_engine_rules)
    cand["vs_engine_adj_low"] = np.exp(log_r - z * cand.vs_engine_log_se)
    cand["vs_engine_adj_high"] = np.exp(log_r + z * cand.vs_engine_log_se)
    same = (cand.vs_engine_low == 1) & (cand.vs_engine_high == 1)
    changed = (cand.vs_engine_adj_low > 1) | (cand.vs_engine_adj_high < 1)
    within = (cand.vs_engine_adj_low >= 1 - TOLERANCE) & (cand.vs_engine_adj_high <= 1 + TOLERANCE)
    cand["reading"] = np.where(~tests, "", np.where(same, "the same games", np.where(
        changed, np.where(within, "small change", "changed"), np.where(within, "equivalent", "inconclusive"))))
    return cand


def load_games(suffix: str = "") -> dict:
    """{(mode, n): {"variant|candidate": per-game credits}}: this run's (suffix ".new"), the run it replaces ("") or
    the one before that (".previous")."""
    out = {}
    for mode, n in SETTINGS:
        f = GAMES_DIR / f"{mode}_{n}p{suffix}.npz"
        if f.exists():
            with np.load(f) as z:
                out[(mode, n)] = {k: z[k].astype(float) for k in z.files}
    return out


def paired_moves(before: dict, after: dict, boot: int = BOOT, seed: int = 0) -> dict:
    """{"variant|candidate": (change, low, high)}: how each ratio to the final agent moved between two runs whose games
    used the same seeds, with one bootstrap that resamples the seeds in both runs at once."""
    keys = sorted(k for k in after if k in before and len(before[k]) == len(after[k]))
    if not keys:
        return {}
    x = np.stack([after[k] for k in keys] + [before[k] for k in keys])
    g = x.shape[1]
    rng = np.random.default_rng(seed)
    means = np.concatenate([rng.multinomial(g, np.full(g, 1 / g), size=min(100, boot - s)) @ x.T / g
                            for s in range(0, boot, 100)])
    a, b = means[:, :len(keys)], means[:, len(keys):]
    out = {}
    for j, k in enumerate(keys):
        variant, name = k.split("|", 1)
        d = f"{variant}|final agent"
        if name == "final agent" or d not in keys:
            continue
        i = keys.index(d)
        ch = a[:, j] / np.maximum(a[:, i], 1e-12) - b[:, j] / np.maximum(b[:, i], 1e-12)
        point = after[k].mean() / max(after[d].mean(), 1e-12) - before[k].mean() / max(before[d].mean(), 1e-12)
        out[k] = (float(point), float(np.quantile(ch, 0.025)), float(np.quantile(ch, 0.975)))
    return out


def moved(cand: pd.DataFrame, previous: pd.DataFrame | None, before: dict | None = None,
          after: dict | None = None) -> pd.DataFrame | None:
    """How each ratio moved from the previous run on the same seeds. Where both runs kept their per-game credits the
    interval is paired (paired_moves); otherwise it treats the runs as independent, which overstates the
    uncertainty of a difference measured on the same seeds."""
    if previous is None:
        return None
    keys = ["mode", "n_players", "variant", "candidate"]
    m = cand[keys + ["ratio", "ci_low", "ci_high"]].merge(previous[keys + ["ratio", "ci_low", "ci_high"]], on=keys,
                                                          suffixes=("", "_before"))
    se = np.sqrt(((m.ci_high - m.ci_low) / 3.92) ** 2 + ((m.ci_high_before - m.ci_low_before) / 3.92) ** 2)
    m["change"] = m.ratio - m.ratio_before
    m["change_low"], m["change_high"] = m.change - 1.96 * se, m.change + 1.96 * se
    m["paired"] = False
    pairs = {s: paired_moves((before or {}).get(s, {}), (after or {}).get(s, {}), seed=s[1])
             for s in (after or {}) if s in (before or {})}
    for i, r in m.iterrows():
        hit = pairs.get((r["mode"], r.n_players), {}).get(f"{r.variant}|{r.candidate}")
        if hit:
            m.loc[i, ["change_low", "change_high", "paired"]] = hit[1], hit[2], True
    return m[m.candidate != "final agent"]


def verdict(lo: float, hi: float) -> str:
    return "better" if lo > 1 else "worse" if hi < 1 else "level"


def describe(g: pd.DataFrame) -> str:
    """One line per candidate: its edge under the engine's rules, and whether any variant changes it."""
    e = g[g.variant == ENGINE].iloc[0]
    head = f"{e.ratio:.3f} [{e.ci_low:.3f}, {e.ci_high:.3f}] under the engine's rules ({verdict(e.ci_low, e.ci_high)})"
    others = g[g.variant != ENGINE]
    flips = [r.variant for r in others.itertuples() if {verdict(e.ci_low, e.ci_high), verdict(r.ci_low, r.ci_high)}
             == {"better", "worse"}]
    parts = []
    for reading, label in (("changed", "changed (adjusted) by"),
                           ("small change", f"changed slightly (adjusted, within ±{TOLERANCE:.0%}) by"),
                           ("inconclusive", "inconclusive under"),
                           ("equivalent", f"equivalent within ±{TOLERANCE:.0%} under"),
                           ("the same games", "untouched (the same games) under")):
        d = others[others.reading == reading]
        if d.empty:
            continue
        if reading in ("changed", "small change"):
            parts.append(f"{label} " + "; ".join(f"{r.variant} × {r.vs_engine_rules:.3f} [{r.vs_engine_adj_low:.3f}, "
                                                 f"{r.vs_engine_adj_high:.3f}]" for r in d.itertuples()))
        else:
            parts.append(f"{label} {', '.join(d.variant)}")
    reverses = f"; the verdict reverses under {', '.join(flips)}" if flips else ""
    return f"{head}; " + "; ".join(parts) + reverses


def factorial_lines(lock: pd.DataFrame) -> list[str]:
    arms = [a for a in LOCK_ARMS if a != "neither"] + ["protect only ÷ both"]
    lines = ["## The housing lock, taken apart", "",
             "The official 4-player agent, with the housing lock's two behaviours switched on separately: deferring "
             "hotels while houses are short, and protecting buildings (when raising cash, mortgage everything else "
             "before selling one). Each arm ÷ the agent with neither, in the same seat on the same games, and the "
             "change in its outright win rate (official rules: a game stopped by the time limit is a loss for "
             "everyone). The last column compares the two strongest arms directly. 95% bootstrap intervals.", "",
             "| Other three seats | Games | " + " | ".join(arms) + " |", "|---" * (len(arms) + 2) + "|"]
    for (opp, sched), d in lock.groupby(["opponents", "schedule"], sort=False):
        cells = []
        for a in arms:
            r = d[d.arm == a].iloc[0]
            cells.append(f"{r.ratio:.3f} [{r.ci_low:.3f}, {r.ci_high:.3f}], {r.gain_pp:+.2f} pp "
                         f"[{r.gain_low_pp:+.2f}, {r.gain_high_pp:+.2f}]")
        lines.append(f"| {opp} ({sched}) | {int(d.games.iloc[0]):,} | " + " | ".join(cells) + " |")
    return lines + [""]


def summary(cand: pd.DataFrame, hous: pd.DataFrame, seat: pd.DataFrame, dropped: dict,
            conf: pd.DataFrame | None = None, change: pd.DataFrame | None = None,
            lock: pd.DataFrame | None = None) -> str:
    t = cand[(cand.variant != ENGINE) & (cand.candidate != "final agent")]
    tests = len(t)
    count = t.reading.value_counts()
    lines = ["# Rule sensitivity of the housing findings", "",
             f"Paired games per cell: {GAMES:,}. Ratio = the candidate's credit ÷ the final agent's in the same seat "
             "on the same games (95% bootstrap interval). \"Variant ÷ engine rules\" is that ratio under a variant "
             "divided by the ratio under the engine's own rules, from a bootstrap that resamples the same seeds in "
             "both: an interval that excludes 1 means the variant changes the candidate's edge. Variants: "
             + ", ".join(VARIANTS) + ".", "",
             f"There are {tests} variant ÷ engine-rules intervals below. At 95%, about {tests / 20:.0f} would exclude "
             "1 by chance even if no variant mattered, so a lone exclusion is weak evidence; a consistent pattern "
             "across settings or variants is not. With Bonferroni-adjusted intervals (marked **), "
             f"{count.get('changed', 0) + count.get('small change', 0)} of the {tests} still exclude 1: those edges "
             f"change ({count.get('small change', 0)} of them by less than {TOLERANCE:.0%} either way). Of the rest, "
             f"{count.get('equivalent', 0)} are equivalent within ±{TOLERANCE:.0%} (the adjusted interval lies inside "
             f"[{1 - TOLERANCE:.2f}, {1 + TOLERANCE:.2f}], a tolerance set before the run: no change big enough to "
             "reverse a verdict here is plausible), "
             f"{count.get('the same games', 0)} are untouched (the variant's rule never came into play) and "
             f"{count.get('inconclusive', 0)} are inconclusive (a change of a few percent is still possible).", ""]
    for (mode, n), d in cand.groupby(["mode", "n_players"], sort=False):
        lines += [f"## {mode}, {n} players", ""]
        if dropped.get((mode, n)):
            lines += ["Left out: " + "; ".join(dropped[(mode, n)]) + ".", ""]
        d = d[d.candidate != "final agent"]
        lines.append("| Candidate | " + " | ".join(VARIANTS) + " |")
        lines.append("|---" * (len(VARIANTS) + 1) + "|")
        for name, g in d.groupby("candidate", sort=False):
            cells = [f"{r.ratio:.3f} [{r.ci_low:.3f}, {r.ci_high:.3f}]" for r in g.itertuples()]
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
        lines += ["", "Variant ÷ engine rules:", "", "| Candidate | " + " | ".join(list(VARIANTS)[1:]) + " |",
                  "|---" * len(VARIANTS) + "|"]
        for name, g in d.groupby("candidate", sort=False):
            cells = ["1 (the same games)" if r.reading == "the same games" else
                     f"{r.vs_engine_rules:.3f} [{r.vs_engine_low:.3f}, {r.vs_engine_high:.3f}]"
                     + ("**" if r.reading in ("changed", "small change") else "*"
                        if r.vs_engine_low > 1 or r.vs_engine_high < 1 else "")
                     + (" ≈" if r.reading in ("equivalent", "small change") else "")
                     for r in g.itertuples() if r.variant != ENGINE]
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
        lines += ["", "(* the 95% interval excludes 1; ** the Bonferroni-adjusted one does too; ≈ the adjusted "
                  f"interval lies within ±{TOLERANCE:.0%}. \"The same games\": the variant's rule never came into "
                  "play, so every game went exactly as under the engine's rules.)", ""]
        for name, g in d.groupby("candidate", sort=False):
            lines.append(f"- {name}: {describe(g)}")
        lines.append("")
    if lock is not None and len(lock):
        lines += factorial_lines(lock)
    lines += ["## How often the simplifications bind", "",
              "Between final agents. A contested moment: two or more players want more houses (or hotels) than the "
              "bank has. The engine never auctions hotels; the official rules auction them too. Mortgaged deeds "
              "received: in a trade or from a bankrupt player, the moments the official choice to lift at once "
              "arises.", "",
              "| Setting | Variant | Games with contested houses | Houses auctioned per game | Games with contested "
              "hotels | Mortgaged deeds received per game | Lifted at once per game |", "|---|---|---|---|---|---|---|"]
    for _, r in hous.iterrows():
        lines.append(f"| {r['mode']} {r.n_players}p | {r.variant} | {r.games_with_contested_houses:.1%} | "
                     f"{r.houses_auctioned_per_game:.2f} | {r.games_with_contested_hotels:.1%} | "
                     f"{r.mortgaged_received_per_game:.2f} | {r.lifted_at_once_per_game:.2f} |")
    lines += ["", "## Seat order, simple bots", "", "| Players | Variant | First player | Last player |",
              "|---|---|---|---|"]
    for _, r in seat.iterrows():
        lines.append(f"| {r.n_players} | {r.variant} | {r.first_relative:.3f} "
                     f"[{r.first_ci_low:.3f}, {r.first_ci_high:.3f}] | {r.last_relative:.3f} |")
    if conf is not None and len(conf):
        r = conf.iloc[0]
        lines += ["", "## Confirmation on fresh seeds", "",
                  f"The official 4-player agent with the housing lock (at 14 houses) ÷ the agent as it is, on "
                  f"{int(r.games):,} paired games none of the comparisons above played (the confirmation of "
                  f"2026-10-31, replayed as the factorial's first schedule): {r.ratio:.3f} [{r.ci_low:.3f}, "
                  f"{r.ci_high:.3f}]."]
    if change is not None and len(change):
        exact = change.change.abs() < 1e-12
        lines += ["", "## Change from the previous run (same seeds)", "",
                  f"{int(exact.sum())} of the {len(change)} ratios the previous run also measured reproduce it "
                  "exactly" + (". The others:" if (~exact).any() else "."), ""]
        if (~exact).any():
            lines += ["| Setting | Variant | Candidate | Before | After | Change [95%] |", "|---|---|---|---|---|---|"]
            for r in change[~exact].itertuples():
                lines.append(f"| {r.mode} {r.n_players}p | {r.variant} | {r.candidate} | {r.ratio_before:.3f} | "
                             f"{r.ratio:.3f} | {r.change:+.3f} [{r.change_low:+.3f}, {r.change_high:+.3f}]"
                             + ("" if r.paired else " (runs as if independent)") + " |")
    return "\n".join(lines) + "\n"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t = time.time()
    # The previous complete run, the "before" of this one. This run writes candidates_partial.csv and
    # games/<setting>.new.npz as it goes, and replaces candidates.csv and games/<setting>.npz only at the end, file by
    # file, so an interrupted run leaves the previous run's tables as they were.
    previous = pd.read_csv(OUT / "candidates.csv") if (OUT / "candidates.csv").exists() else None
    cand, hous, dropped = [], [], {}
    for mode, n in SETTINGS:
        print(f"{mode} {n}p: candidates", flush=True)
        rows, dropped[(mode, n)] = compare(mode, n)
        cand += rows
        pd.DataFrame(cand).to_csv(OUT / "candidates_partial.csv", index=False)
        hous += housing(mode, n)
        pd.DataFrame(hous).to_csv(OUT / "housing.csv", index=False)
    cand = adjust(pd.DataFrame(cand))
    seat = pd.DataFrame(seats())
    seat.to_csv(OUT / "seats.csv", index=False)
    print("the housing lock, taken apart", flush=True)
    lock_rows, conf_rows = lock_factorial()
    lock, conf = pd.DataFrame(lock_rows), pd.DataFrame(conf_rows)
    lock.to_csv(OUT / "lock_factorial.csv", index=False)
    conf.to_csv(OUT / "confirm.csv", index=False)
    change = moved(cand, previous, load_games(""), load_games(".new"))
    # the new tables first, then the rotation: each step an atomic replace of one file
    cand.to_csv(OUT / "candidates.new.csv", index=False)
    if previous is not None:
        os.replace(OUT / "candidates.csv", OUT / "candidates_previous.csv")
    os.replace(OUT / "candidates.new.csv", OUT / "candidates.csv")
    for mode, n in SETTINGS:
        now, new = GAMES_DIR / f"{mode}_{n}p.npz", GAMES_DIR / f"{mode}_{n}p.new.npz"
        if now.exists():
            os.replace(now, GAMES_DIR / f"{mode}_{n}p.previous.npz")
        os.replace(new, now)
    (OUT / "candidates_partial.csv").unlink(missing_ok=True)
    (OUT / "summary.md").write_text(summary(cand, pd.DataFrame(hous), seat, dropped, conf, change, lock))
    (OUT / "variants.json").write_text(json.dumps({v: asdict(replace(Rules(), **f)) for v, f in VARIANTS.items()},
                                                  indent=1))
    print(f"done in {time.time() - t:.0f}s")
    print((OUT / "summary.md").read_text())


if __name__ == "__main__":
    main()
