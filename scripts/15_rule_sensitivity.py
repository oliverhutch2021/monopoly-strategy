"""Do the housing findings survive the rules the engine simplifies? (from the methodology review, 2026-10-30)

    MM_RESULTS=results/final python scripts/15_rule_sensitivity.py

The engine lets players build only after their own move, and the last houses go to whoever builds first. The
official rules let anyone build at any time, and auction the houses when two or more players want more than the
bank has. The engine also leaves mortgaged stations and utilities out of the count that sets their rent. This
replays the comparisons the housing findings rest on under each variant (engine.Rules: build_any_time,
house_auctions, both, mortgaged_count_for_rent), on the same seeds in every variant, from a seed offset no other
study uses:

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
   the log scale, from the same bootstrap). Where an earlier run's candidates.csv exists, the summary lists how
   each ratio moved (with an interval that treats the two runs as independent, which overstates the uncertainty
   of a difference measured on the same seeds).
3. How often the simplification binds: the share of games, between final agents, in which two or more players
   wanted more houses than the bank had, and the houses auctioned per game under the official rule.
4. Seat order with simple bots at 4 and 6 players.
5. A fresh-seed confirmation of the one change the comparisons found worth adopting: the official 4-player agent
   with the housing lock, on games none of the above played.

Outputs, under <results>/tables/sensitivity/: candidates.csv (and candidates_before.csv, the run it replaced),
housing.csv, seats.csv, confirm.csv, summary.md, variants.json
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
            "mortgaged stations count": {"mortgaged_count_for_rent": True}}
SETTINGS = [("standard", 4), ("standard", 2), ("championship", 4)]
GAMES = scaled(2000)          # paired games per candidate and variant (20,000 at MM_SCALE=10)
HOUSING_GAMES = scaled(500)   # games per setting for the housing counts
SEAT_GAMES = scaled(2000)
SEED = 7_777_000              # offset from each mode's seed for evaluate(): no other study uses these seeds
CONFIRM_SEED = 7_888_000      # fresh seeds for the confirmation
CONFIRM_GAMES = scaled(4000)  # 40,000 at MM_SCALE=10
BOOT = 2000


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
        out.append((g.contested_houses, g.house_auctions_held, r.capped))
    return out


def housing(mode: str, n: int) -> list[dict]:
    meta = candidates(mode, n)[0]["final agent"]
    rows = []
    workers = os.cpu_count() or 1
    for variant in (ENGINE, "house auctions", "any time + auctions"):
        rules = replace(rules_for(mode, n), **VARIANTS[variant])
        base = 700_000_000 + MODES[mode]["seed"] * 1_000 + n * 100_000
        seeds = list(range(base, base + HOUSING_GAMES))
        with ProcessPoolExecutor(workers) as ex:
            res = [r for part in ex.map(_housing, [(meta, n, rules, seeds[i::workers]) for i in range(workers)])
                   for r in part]
        contested = np.array([c for c, _, _ in res])
        auctions = np.array([a for _, a, _ in res])
        # contested_checks_per_game counts the checks that found contested demand: once or twice per turn, and
        # once per player per turn when building is allowed at any time, so it doesn't compare across variants
        rows.append({"mode": mode, "n_players": n, "variant": variant, "games": len(res),
                     "games_with_contested_houses": float((contested > 0).mean()),
                     "contested_checks_per_game": float(contested.mean()),
                     "houses_auctioned_per_game": float(auctions.mean()),
                     "capped_share": float(np.mean([c for _, _, c in res]))})
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


def confirm() -> list[dict]:
    """The official 4-player agent with and without the housing lock (at 14 houses), on fresh seeds."""
    cands, _ = candidates("standard", 4)
    genomes = [cands["final agent"], cands["housing lock on (14)"]]
    evaluate(genomes, [genomes[0]], 4, CONFIRM_GAMES, seed=MODES["standard"]["seed"] + CONFIRM_SEED + 4,
             rules=rules_for("standard", 4), fixed_opponents=True)
    games = evaluate.last_games
    ratio, lo, hi = paired_ratio(games[1], games[0], seed=4)
    return [{"mode": "standard", "n_players": 4, "candidate": "housing lock on (14)", "ratio": ratio, "ci_low": lo,
             "ci_high": hi, "games": CONFIRM_GAMES, "seed_offset": CONFIRM_SEED}]


def adjust(cand: pd.DataFrame) -> pd.DataFrame:
    """Bonferroni-adjusted intervals for every variant ÷ engine-rules comparison (normal on the log scale)."""
    cand = cand.copy()
    tests = (cand.variant != ENGINE) & (cand.candidate != "final agent")
    z = NormalDist().inv_cdf(1 - 0.025 / max(int(tests.sum()), 1))
    log_r = np.log(cand.vs_engine_rules)
    cand["vs_engine_adj_low"] = np.exp(log_r - z * cand.vs_engine_log_se)
    cand["vs_engine_adj_high"] = np.exp(log_r + z * cand.vs_engine_log_se)
    return cand


def moved(cand: pd.DataFrame, previous: pd.DataFrame | None) -> pd.DataFrame | None:
    """How each ratio moved from an earlier run on the same seeds; the interval treats the runs as independent."""
    if previous is None:
        return None
    keys = ["mode", "n_players", "variant", "candidate"]
    m = cand[keys + ["ratio", "ci_low", "ci_high"]].merge(previous[keys + ["ratio", "ci_low", "ci_high"]], on=keys,
                                                          suffixes=("", "_before"))
    se = np.sqrt(((m.ci_high - m.ci_low) / 3.92) ** 2 + ((m.ci_high_before - m.ci_low_before) / 3.92) ** 2)
    m["change"] = m.ratio - m.ratio_before
    m["change_low"], m["change_high"] = m.change - 1.96 * se, m.change + 1.96 * se
    return m[m.candidate != "final agent"]


def verdict(lo: float, hi: float) -> str:
    return "better" if lo > 1 else "worse" if hi < 1 else "level"


def describe(g: pd.DataFrame) -> str:
    """One line per candidate: its edge under the engine's rules, and whether any variant changes it."""
    e = g[g.variant == ENGINE].iloc[0]
    head = f"{e.ratio:.3f} [{e.ci_low:.3f}, {e.ci_high:.3f}] under the engine's rules ({verdict(e.ci_low, e.ci_high)})"
    others = g[g.variant != ENGINE]
    changed = others[(others.vs_engine_low > 1) | (others.vs_engine_high < 1)]
    flips = [r.variant for r in others.itertuples() if {verdict(e.ci_low, e.ci_high), verdict(r.ci_low, r.ci_high)}
             == {"better", "worse"}]
    if changed.empty:
        return (f"{head}; no variant changes it detectably (variant ÷ engine rules between "
                f"{others.vs_engine_low.min():.3f} and {others.vs_engine_high.max():.3f})")
    parts = [f"{r.variant} × {r.vs_engine_rules:.3f} [{r.vs_engine_low:.3f}, {r.vs_engine_high:.3f}]"
             for r in changed.itertuples()]
    reverses = f"; the verdict reverses under {', '.join(flips)}" if flips else ""
    return f"{head}; changed by " + "; ".join(parts) + reverses


def summary(cand: pd.DataFrame, hous: pd.DataFrame, seat: pd.DataFrame, dropped: dict,
            conf: pd.DataFrame | None = None, change: pd.DataFrame | None = None) -> str:
    tests = int(((cand.variant != ENGINE) & (cand.candidate != "final agent")).sum())
    t = cand[(cand.variant != ENGINE) & (cand.candidate != "final agent")]
    adjusted = int(((t.vs_engine_adj_low > 1) | (t.vs_engine_adj_high < 1)).sum())
    lines = ["# Rule sensitivity of the housing findings", "",
             f"Paired games per cell: {GAMES:,}. Ratio = the candidate's credit ÷ the final agent's in the same seat "
             "on the same games (95% bootstrap interval). \"Variant ÷ engine rules\" is that ratio under a variant "
             "divided by the ratio under the engine's own rules, from a bootstrap that resamples the same seeds in "
             "both: an interval that excludes 1 means the variant changes the candidate's edge. Variants: "
             + ", ".join(VARIANTS) + ".", "",
             f"There are {tests} variant ÷ engine-rules intervals below. At 95%, about {tests / 20:.0f} would exclude "
             "1 by chance even if no variant mattered, so a lone exclusion is weak evidence; a consistent pattern "
             f"across settings or variants is not. With Bonferroni-adjusted intervals, {adjusted} of the {tests} "
             "still exclude 1 (marked **).", ""]
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
            cells = ["1 (the same games)" if r.vs_engine_low == r.vs_engine_high == 1 else
                     f"{r.vs_engine_rules:.3f} [{r.vs_engine_low:.3f}, {r.vs_engine_high:.3f}]"
                     + ("**" if r.vs_engine_adj_low > 1 or r.vs_engine_adj_high < 1 else
                        "*" if r.vs_engine_low > 1 or r.vs_engine_high < 1 else "")
                     for r in g.itertuples() if r.variant != ENGINE]
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
        lines += ["", "(* the 95% interval excludes 1; ** the Bonferroni-adjusted one does too. \"The same "
                  "games\": the variant's rule never came into play, so every game went exactly as under the "
                  "engine's rules.)", ""]
        for name, g in d.groupby("candidate", sort=False):
            lines.append(f"- {name}: {describe(g)}")
        lines.append("")
    lines += ["## How often the simplification binds", "",
              "Between final agents. A contested moment: two or more players want more houses than the bank has.", "",
              "| Setting | Variant | Games with a contested moment | Houses auctioned per game |", "|---|---|---|---|"]
    for _, r in hous.iterrows():
        lines.append(f"| {r['mode']} {r.n_players}p | {r.variant} | {r.games_with_contested_houses:.1%} | "
                     f"{r.houses_auctioned_per_game:.2f} |")
    lines += ["", "## Seat order, simple bots", "", "| Players | Variant | First player | Last player |",
              "|---|---|---|---|"]
    for _, r in seat.iterrows():
        lines.append(f"| {r.n_players} | {r.variant} | {r.first_relative:.3f} "
                     f"[{r.first_ci_low:.3f}, {r.first_ci_high:.3f}] | {r.last_relative:.3f} |")
    if conf is not None and len(conf):
        r = conf.iloc[0]
        lines += ["", "## Confirmation on fresh seeds", "",
                  f"The official 4-player agent with the housing lock (at 14 houses) ÷ the agent as it is, on "
                  f"{int(r.games):,} paired games no other comparison played: {r.ratio:.3f} [{r.ci_low:.3f}, "
                  f"{r.ci_high:.3f}]."]
    if change is not None and len(change):
        same = change[change.variant.isin([ENGINE, "build any time", "mortgaged stations count"])]
        unchanged = int((same.change.abs() < 1e-12).sum())
        lines += ["", "## Change from the previous run (same seeds)", "",
                  f"Variants without house auctions reproduce the previous run exactly in {unchanged} of {len(same)} "
                  "cells. With house auctions (after the auction fix):", "",
                  "| Setting | Variant | Candidate | Before | After | Change [95%, runs as if independent] |",
                  "|---|---|---|---|---|---|"]
        for r in change[change.variant.isin(["house auctions", "any time + auctions"])].itertuples():
            lines.append(f"| {r.mode} {r.n_players}p | {r.variant} | {r.candidate} | {r.ratio_before:.3f} | "
                         f"{r.ratio:.3f} | {r.change:+.3f} [{r.change_low:+.3f}, {r.change_high:+.3f}] |")
    return "\n".join(lines) + "\n"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    t = time.time()
    # the run this one replaces (kept once, so an interrupted run still compares with the real "before")
    before = OUT / "candidates_before.csv"
    if not before.exists() and (OUT / "candidates.csv").exists():
        (OUT / "candidates.csv").replace(before)
    previous = pd.read_csv(before) if before.exists() else None
    cand, hous, dropped = [], [], {}
    for mode, n in SETTINGS:
        print(f"{mode} {n}p: candidates", flush=True)
        rows, dropped[(mode, n)] = compare(mode, n)
        cand += rows
        pd.DataFrame(cand).to_csv(OUT / "candidates.csv", index=False)
        hous += housing(mode, n)
        pd.DataFrame(hous).to_csv(OUT / "housing.csv", index=False)
    cand = adjust(pd.DataFrame(cand))
    cand.to_csv(OUT / "candidates.csv", index=False)
    seat = pd.DataFrame(seats())
    seat.to_csv(OUT / "seats.csv", index=False)
    print("confirmation on fresh seeds", flush=True)
    conf = pd.DataFrame(confirm())
    conf.to_csv(OUT / "confirm.csv", index=False)
    (OUT / "summary.md").write_text(summary(cand, pd.DataFrame(hous), seat, dropped, conf, moved(cand, previous)))
    (OUT / "variants.json").write_text(json.dumps({v: asdict(replace(Rules(), **f)) for v, f in VARIANTS.items()},
                                                  indent=1))
    print(f"done in {time.time() - t:.0f}s")
    print((OUT / "summary.md").read_text())


if __name__ == "__main__":
    main()
