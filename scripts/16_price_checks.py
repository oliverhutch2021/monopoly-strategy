"""Check narrow deals at prices someone could actually pay, on fresh seeds (from the 2026-10-31 review).

    MM_RESULTS=results/final python scripts/16_price_checks.py

A deal zone is read from curves played at a grid of prices (every £25-£200), and its ends are interpolated
between them. When no price actually played has both sides gaining (evidence "between sampled prices only",
rollout.deal_summary), the zone rests on interpolation alone. This plays each such sale again at whole-pound prices
inside its zone (all of them for up to three, else the lowest, middle and highest), on fresh seeds no other study
used, and asks whether both sides gain at that price, beyond the noise. A zone with no whole pound inside it is
listed as not payable.

Covers the property tables (simple bots, official and championship meta agents), which include Vine Street.

Outputs, under <results>/tables/: price_checks.csv (one row per sale and price), price_checks.md
"""
import importlib
import time

import numpy as np
import pandas as pd

from monopoly_meta import load_edition
from monopoly_meta.rollout import deal_summary, trade_price_curve
from scenarios import set_completion
from run_config import TABLES as TAB, scaled  # noqa: E402

N = scaled(2000)           # paired rollouts per price (20,000 at MM_SCALE=10)
SEED0 = 16_000_777         # fresh rollout seeds: the curves themselves used 777 onwards
MAX_PRICES = 3
LABEL = {"simple": "simple bots", "meta": "official meta agents", "championship": "championship meta agents"}


def narrow_deals() -> pd.DataFrame:
    """Every legal deal in the property tables that no sampled price supports, re-read from the stored curves."""
    rows = []
    for bots in ("simple", "meta", "championship"):
        cpath, spath = TAB / f"property_trade_curve_{bots}.csv", TAB / f"property_trade_summary_{bots}.csv"
        if not (cpath.exists() and spath.exists()):
            continue
        curve, summ = pd.read_csv(cpath), pd.read_csv(spath).set_index(["n_players", "square"])
        for (n, sq), g in curve.groupby(["n_players", "square"]):
            legal = bool(summ.loc[(n, sq), "legal"])
            z = deal_summary(g, seller=1, buyer=0, legal=legal)
            if z["evidence"] in ("between sampled prices only", "no whole-pound price"):
                rows.append({"bots": bots, "n_players": int(n), "square": int(sq), "deal_ranges": z["deal_ranges"],
                             "whole_pound_ranges": z["whole_pound_ranges"], "evidence": z["evidence"]})
    return pd.DataFrame(rows)


def test_prices(ranges: str) -> list[int]:
    """The whole-pound prices to play: all of them if there are up to three, else the lowest, middle and highest."""
    pounds = [p for part in str(ranges).split("; ") if "-" in part
              for p in range(int(part.split("-")[0]), int(part.split("-")[1]) + 1)]
    if len(pounds) <= MAX_PRICES:
        return pounds
    return [pounds[0], pounds[len(pounds) // 2], pounds[-1]]


def check(row, players_for) -> list[dict]:
    ed = load_edition()
    prices = test_prices(row.whole_pound_ranges) if isinstance(row.whole_pound_ranges, str) else []
    base = {"bots": row.bots, "n_players": row.n_players, "square": row.square, "name": ed.names[row.square],
            "deal_ranges": row.deal_ranges, "evidence": row.evidence}
    if not prices:
        return [{**base, "price": np.nan, "verdict": "no whole-pound price: not payable"}]
    bots, rules = players_for(row.bots, row.n_players)
    c = trade_price_curve(set_completion(ed.names[row.square], row.n_players), bots, seller=1, buyer=0,
                          squares=[row.square], prices=prices, n=N, seed0=SEED0, rules=rules, hypothetical=True)
    out = []
    for price in prices:
        b = c[(c.player == 0) & (c.price == price)].iloc[0]
        s = c[(c.player == 1) & (c.price == price)].iloc[0]
        both = b.d_win - 1.96 * b.d_win_se > 0 and s.d_win - 1.96 * s.d_win_se > 0
        either_loses = b.d_win + 1.96 * b.d_win_se < 0 or s.d_win + 1.96 * s.d_win_se < 0
        out.append({**base, "price": price, "buyer_change": b.d_win, "buyer_se": b.d_win_se,
                    "seller_change": s.d_win, "seller_se": s.d_win_se, "rollouts": N,
                    "unit": "points" if row.bots == "championship" else "pp",
                    "verdict": "both gain (95%)" if both else "one side loses (95%)" if either_loses
                    else "not established"})
    return out


def change(v: float, se: float, unit: str) -> str:
    """A change in credit, with its 95% half-width, as percentage points of win chance or championship points."""
    k, tag = (28, " pts") if unit == "points" else (100, " pp")
    return f"{k * v:+.2f} ± {1.96 * k * se:.2f}{tag}"


def summary(df: pd.DataFrame) -> str:
    if df.empty:
        return "# Narrow deals at whole-pound prices\n\nEvery deal in the property tables rests on a price played.\n"
    sales = df.groupby(["bots", "n_players", "square"], sort=False)
    good = sum((g.verdict == "both gain (95%)").any() for _, g in sales)
    lines = ["# Narrow deals at whole-pound prices", "",
             f"{sales.ngroups} deals in the property tables had no sampled price with both sides gaining. Each was "
             f"played again at whole-pound prices inside its zone, {N:,} paired rollouts per price on fresh seeds. "
             f"In {good} of them some price clearly benefits both sides (both changes above zero by 1.96 standard "
             "errors); the rest are not established as deals. Changes are in percentage points of win chance (pp), "
             "or expected finishing points (pts) under championship rules.", "",
             "| Opponents | Players | Property | Interpolated zone | Price | Buyer | Seller | Verdict |",
             "|---|---|---|---|---|---|---|---|"]
    for r in df.itertuples():
        if pd.isna(r.price):
            lines.append(f"| {LABEL[r.bots]} | {r.n_players} | {r.name} | £{r.deal_ranges} | — | — | — | {r.verdict} |")
        else:
            lines.append(f"| {LABEL[r.bots]} | {r.n_players} | {r.name} | £{r.deal_ranges} | £{int(r.price)} | "
                         f"{change(r.buyer_change, r.buyer_se, r.unit)} | "
                         f"{change(r.seller_change, r.seller_se, r.unit)} | {r.verdict} |")
    return "\n".join(lines) + "\n"


def main():
    t = time.time()
    players_for = importlib.import_module("10_property_trades").players_for
    rows = []
    for row in narrow_deals().itertuples():
        rows += check(row, players_for)
        print(f"{LABEL[row.bots]}, {row.n_players}p, square {row.square}: {time.time() - t:.0f}s", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "price_checks.csv", index=False)
    (TAB / "price_checks.md").write_text(summary(df))
    print((TAB / "price_checks.md").read_text())


if __name__ == "__main__":
    main()
