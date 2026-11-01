"""How much the assumed 5- and 6-survivor championship points matter (from the 2026-10-31 review).

    MM_RESULTS=results/final python scripts/18_scoring_sensitivity.py

The championship rules sheet gives finishing points for up to four players still in at the time limit. The engine
extends its pattern to five and six survivors (16/8/4/2/1 and 13/6/3/2/1/0), which is an assumption, and at 5 and 6
players most games between the championship agents end at the limit with five or six still in, so the assumed rows
decide most scores. This re-scores the two conclusions that rest on them under two other schedules
(engine.POINTS_ALTERNATIVES):
  extend_four   the 4-survivor scores with 1 and 0 added below (19/10/5/3/1 and 19/10/5/3/1/0): more for the leader
  rank_linear   an even fall from the 4-survivor leader's 19 to 0 (19/14/10/5/0 and 19/15/11/8/4/0): more for the
                middle places
The bots never read the schedule, so the games are the same under all three and only their scores differ.

1. The trade embargo (finding 14): the final agent with trades accepted ÷ the agent as it is, in the same seat on the
   same games (fresh seeds), at 5 and 6 players. And how often the assumed rows decide a game: the share of the
   agent's games that end at the limit with five or six still in.
2. The Vine Street sale (finding 16): the seller's and the buyer's change in expected championship points at £400,
   £800 and £1,200, against keeping it for good, on the same rollouts under each schedule.

The agents were trained under the extrapolated schedule; this tests their conclusions under the others, not the
best play there.

Outputs, under <results>/tables/: scoring_sensitivity.csv, scoring_trades.csv, scoring_sensitivity.md
"""
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace

import numpy as np
import pandas as pd

from meta_common import TAB, ablations, rules_for
from run_config import scaled
from scenarios import orange_squeeze
from monopoly_meta.engine import POINTS_ALTERNATIVES, Game, championship_points
from monopoly_meta.meta import paired_ratio, to_spec
from monopoly_meta.policies import make_bot
from monopoly_meta.rollout import trade_price_curve

SCHEDULES = ("extrapolated",) + tuple(POINTS_ALTERNATIVES)
SIZES = (5, 6)
GAMES = scaled(2000)        # paired games per size (20,000 at MM_SCALE=10)
SEED = 18_000_000           # fresh game seeds: no other study uses them
ROLLOUTS = scaled(500)      # paired rollouts per price (5,000 at MM_SCALE=10)
ROLLOUT_SEED = 18_500_000
PRICES = (400, 800, 1200)
VINE = 19


def _play(args):
    """Each game once, scored under every schedule: (candidate, game, capped, survivors, credit per schedule)."""
    tasks, rules = args
    out = []
    for ci, gi, seat, lineup, seed in tasks:
        r = Game([make_bot(s) for s in lineup], seed=seed, rules=rules).play()
        survivors = len(lineup) - len(r.elimination_order)
        out.append((ci, gi, r.capped, survivors, *[replace(r, points_schedule=s).credit(seat) for s in SCHEDULES]))
    return out


def embargo(n: int, meta: dict, workers: int | None = None) -> tuple[list[dict], dict]:
    """The agent as it is and with trades accepted, on the same games (the seat rotates, as in meta.evaluate)."""
    cands = {"final agent": meta, "accept trades": ablations(meta)["accept trades"]}
    specs = [to_spec(g, "candidate") for g in cands.values()]
    opp = to_spec(meta, "meta")
    tasks = []
    for ci, spec in enumerate(specs):
        for gi in range(GAMES):
            seat = gi % n
            lineup = [opp] * (n - 1)
            lineup.insert(seat, spec)
            tasks.append((ci, gi, seat, lineup, SEED * 1_000_003 + n * 100_000 + gi))
    workers = workers or os.cpu_count() or 1
    chunks = [(tasks[i::workers], rules_for("championship", n)) for i in range(workers)]
    with ProcessPoolExecutor(workers) as ex:
        res = [x for part in ex.map(_play, chunks) for x in part]
    credit = np.zeros((len(cands), len(SCHEDULES), GAMES))
    capped, survivors = np.zeros((len(cands), GAMES)), np.zeros((len(cands), GAMES))
    for ci, gi, cap, alive, *c in res:
        credit[ci, :, gi], capped[ci, gi], survivors[ci, gi] = c, cap, alive
    rows = []
    for k, s in enumerate(SCHEDULES):
        r, lo, hi = paired_ratio(credit[1, k], credit[0, k], seed=n)
        rows.append({"n_players": n, "schedule": s, "points": "/".join(map(str, points(s, n))), "games": GAMES,
                     "agent_points": 28 * float(credit[0, k].mean()),
                     "accepting_points": 28 * float(credit[1, k].mean()),
                     "ratio": r, "ci_low": lo, "ci_high": hi})
    use = {"n_players": n, "games": GAMES, "capped_share": float(capped[0].mean()),
           "decided_by_assumed_rows": float(((capped[0] > 0) & (survivors[0] >= 5)).mean())}
    return rows, use


def points(schedule: str, survivors: int) -> list[int]:
    return championship_points(survivors, schedule)


def sale(n: int, meta: dict) -> list[dict]:
    """The Vine Street sale at PRICES, against keeping it for good, under each schedule (the same rollouts)."""
    rows = []
    for s in SCHEDULES:
        t = time.time()
        rules = replace(rules_for("championship", n), points_schedule=s)
        c = trade_price_curve(orange_squeeze(n), [to_spec(meta, "meta")] * n, seller=1, buyer=0, squares=[VINE],
                              prices=PRICES, n=ROLLOUTS, seed0=ROLLOUT_SEED + n * 100_000, rules=rules)
        for price in PRICES:
            b = c[(c.player == 0) & (c.price == price)].iloc[0]
            v = c[(c.player == 1) & (c.price == price)].iloc[0]
            rows.append({"n_players": n, "schedule": s, "price": price, "rollouts": ROLLOUTS,
                         "buyer_points": 28 * b.d_win, "buyer_se": 28 * b.d_win_se,
                         "seller_points": 28 * v.d_win, "seller_se": 28 * v.d_win_se,
                         "seller_outright_pp": 100 * v.d_outright, "buyer_outright_pp": 100 * b.d_outright})
        print(f"  {n}p sale, {s}: {time.time() - t:.0f}s", flush=True)
    return rows


def summary(emb: pd.DataFrame, use: pd.DataFrame, trades: pd.DataFrame) -> str:
    lines = ["# Championship scoring: how much the assumed 5- and 6-survivor points matter", "",
             "The rules sheet stops at four survivors. Three schedules for five and six (finishing points, first "
             "place first):", "", "| Schedule | 5 survivors | 6 survivors |", "|---|---|---|"]
    for s in SCHEDULES:
        lines.append(f"| {s} | {'/'.join(map(str, points(s, 5)))} | {'/'.join(map(str, points(s, 6)))} |")
    lines += ["", "## How often the assumed rows decide a game", "",
              "Between the final championship agents, on the trade-embargo games below.", "",
              "| Players | Games | Stopped by the time limit | Stopped with 5 or more still in |", "|---|---|---|---|"]
    for r in use.itertuples():
        lines.append(f"| {r.n_players} | {r.games:,} | {r.capped_share:.1%} | {r.decided_by_assumed_rows:.1%} |")
    lines += ["", "## The trade embargo under each schedule", "",
              f"The final agent with trades accepted ÷ the agent as it is, in the same seat on the same {GAMES:,} "
              "games (fresh seeds; the seat rotates). Credit is finishing points ÷ 28; the points columns are "
              "expected points per game. A ratio below 1 means accepting trades costs the agent, so the embargo "
              "holds against that change.", "",
              "| Players | Schedule | Agent's points | Accepting trades | Ratio [95%] |", "|---|---|---|---|---|"]
    for r in emb.itertuples():
        lines.append(f"| {r.n_players} | {r.schedule} | {r.agent_points:.2f} | {r.accepting_points:.2f} | "
                     f"{r.ratio:.3f} [{r.ci_low:.3f}, {r.ci_high:.3f}] |")
    lines += ["", "## The Vine Street sale under each schedule", "",
              f"Change in expected championship points per game against keeping it for good ({ROLLOUTS:,} paired "
              "rollouts per price; ± is 1.96 standard errors), and the seller's change in outright wins.", "",
              "| Players | Schedule | Price | Buyer (points) | Seller (points) | Seller, outright wins (pp) |",
              "|---|---|---|---|---|---|"]
    for r in trades.itertuples():
        lines.append(f"| {r.n_players} | {r.schedule} | £{r.price:,} | {r.buyer_points:+.2f} ± "
                     f"{1.96 * r.buyer_se:.2f} | {r.seller_points:+.2f} ± {1.96 * r.seller_se:.2f} | "
                     f"{r.seller_outright_pp:+.2f} |")
    return "\n".join(lines) + "\n"


def main():
    t = time.time()
    agents = json.loads((TAB / "meta_agents_championship.json").read_text())
    emb, use, trades = [], [], []
    for n in SIZES:
        meta = {k: v for k, v in agents[str(n)].items() if k != "name"}
        rows, u = embargo(n, meta)
        emb += rows
        use.append(u)
        print(f"{n}p embargo: {time.time() - t:.0f}s", flush=True)
        trades += sale(n, meta)
    emb, use, trades = pd.DataFrame(emb), pd.DataFrame(use), pd.DataFrame(trades)
    emb.merge(use, on=["n_players", "games"]).to_csv(TAB / "scoring_sensitivity.csv", index=False)
    trades.to_csv(TAB / "scoring_trades.csv", index=False)
    (TAB / "scoring_sensitivity.md").write_text(summary(emb, use, trades))
    print(f"done in {time.time() - t:.0f}s")
    print((TAB / "scoring_sensitivity.md").read_text())


if __name__ == "__main__":
    main()
