"""The set-completing sale in positions that real games reach, not one hand-built position (2026-10-31 review).

    MM_RESULTS=results/final python scripts/17_game_positions.py

Findings 4, 16 and 17 price sales in one hand-built position per table size. Here, games between four simple bots
are screened, each with its own seed, for the first moment (at a turn boundary, all four players in) at which one
player holds two of the oranges and another holds the third, all unmortgaged, and the first can pay the highest
price tested. That position is taken once per game, before any valuation, so selection can't favour a result. The
sale of the missing orange is then played out at 2, 3 and 4 times its printed price (2x is the bots' own usual
offer: £360 for Bow Street or Marlborough Street, £400 for Vine Street), against keeping it, both ways
(rollout.trade_price_curve):
  kept for good           the deed never trades again in either arm: its own value to each side
  later trades allowed    everyone carries on as normal: the decision to accept the offer today
Reported per position, and across positions with intervals that resample whole positions.

Outputs, under <results>/tables/: game_positions.csv, game_positions.md
"""
import time

import numpy as np
import pandas as pd

from monopoly_meta import load_edition
from monopoly_meta.engine import Game
from monopoly_meta.policies import make_bot
from monopoly_meta.rollout import trade_price_curve
from run_config import TABLES as TAB, scaled  # noqa: E402

ORANGES = (16, 18, 19)
MULTIPLES = (2, 3, 4)      # prices, as multiples of the missing orange's printed price
POSITIONS = 100            # positions (one per qualifying game)
ROLLOUTS = scaled(200)     # paired rollouts per price and arm (2,000 at MM_SCALE=10)
SCREEN_SEED = 17_000_000   # the screened games: seeds from here on, one game each
ROLLOUT_SEED = 17_500_000  # rollout seeds for position j: from ROLLOUT_SEED + 10,000 j
BOOT = 20_000


def qualifying(g: Game) -> tuple[int, int, int] | None:
    """(buyer, seller, missing orange) if the position qualifies, else None."""
    s = g.s
    if sum(s.alive) < 4:
        return None
    for missing in ORANGES:
        rest = [s.owner[sq] for sq in ORANGES if sq != missing]
        seller = s.owner[missing]
        top = max(MULTIPLES) * g.ed.price[missing]  # the highest price tested
        if rest[0] == rest[1] and rest[0] >= 0 and seller >= 0 and seller != rest[0] \
                and not any(s.mortgaged[sq] for sq in ORANGES) and s.cash[rest[0]] >= top:
            return rest[0], seller, missing
    return None


def screen(limit: int = 20_000) -> list[dict]:
    """The first qualifying position of each screened game, until POSITIONS are found."""
    found, seed = [], SCREEN_SEED
    while len(found) < POSITIONS and seed < SCREEN_SEED + limit:
        g = Game([make_bot("balanced") for _ in range(4)], seed=seed)
        while not g.done:
            hit = qualifying(g)
            if hit:
                buyer, seller, missing = hit
                found.append({"game_seed": seed, "turn": g.s.turn, "buyer": buyer, "seller": seller,
                              "square": missing, "buyer_cash": g.s.cash[buyer], "seller_cash": g.s.cash[seller],
                              "bank_held": sum(g.s.owner[sq] < 0 for sq in g.ed.ownable), "state": g.s.copy()})
                break
            g.take_turn()
        seed += 1
    return found


def value(pos: dict, j: int) -> list[dict]:
    rows = []
    face = int(load_edition().price[pos["square"]])
    prices = [m * face for m in MULTIPLES]
    for freeze, label in ((True, "kept for good"), (False, "later trades allowed")):
        c = trade_price_curve(pos["state"], ["balanced"] * 4, seller=pos["seller"], buyer=pos["buyer"],
                              squares=[pos["square"]], prices=prices, n=ROLLOUTS, seed0=ROLLOUT_SEED + 10_000 * j,
                              freeze=freeze)
        later = c.attrs.get("later_deals", {})
        for m, price in zip(MULTIPLES, prices):
            b = c[(c.player == pos["buyer"]) & (c.price == price)].iloc[0]
            s = c[(c.player == pos["seller"]) & (c.price == price)].iloc[0]
            rows.append({**{k: v for k, v in pos.items() if k != "state"}, "position": j, "baseline": label,
                         "multiple": m, "price": price, "buyer_change": b.d_win, "buyer_se": b.d_win_se,
                         "seller_change": s.d_win, "seller_se": s.d_win_se,
                         "keep_later_to_buyer": later.get("to_buyer", np.nan),
                         "keep_later_multiple": later.get("median_price", np.nan) / face,
                         "keep_later_swap_share": later.get("swap_share", np.nan)})
    return rows


def across(df: pd.DataFrame, col: str, seed: int = 0) -> tuple[float, float, float]:
    """Mean over positions with a 95% interval that resamples whole positions."""
    x = df[col].to_numpy(float)
    rng = np.random.default_rng(seed)
    means = x[rng.integers(0, len(x), size=(BOOT, len(x)))].mean(axis=1)
    return float(x.mean()), float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def summary(df: pd.DataFrame, screened: int) -> str:
    n = df.position.nunique()
    lines = ["# The set-completing sale in positions from real games", "",
             f"{n} positions, the first qualifying moment of each of {screened:,} screened games between four simple "
             f"bots. Turns {df.turn.min()}-{df.turn.max()}; buyers held £{df.buyer_cash.min():,}-"
             f"£{df.buyer_cash.max():,}; the bank held {df.bank_held.min()}-{df.bank_held.max()} unowned deeds. "
             f"{ROLLOUTS:,} paired rollouts per price and arm. Prices are multiples of the missing orange's printed "
             "price (£180 for Bow Street and Marlborough Street, £200 for Vine Street). Changes in win chance in "
             "percentage points; intervals resample whole positions.", "",
             "| Baseline | Price | Buyer: mean change | Seller: mean change | Both gain | Buyer loses |",
             "|---|---|---|---|---|---|"]
    for (label, m), d in df.groupby(["baseline", "multiple"], sort=False):
        b, s = across(d, "buyer_change"), across(d, "seller_change", seed=1)
        both = int(((d.buyer_change > 0) & (d.seller_change > 0)).sum())
        lines.append(f"| {label} | {m}× face | {100 * b[0]:+.1f} [{100 * b[1]:+.1f}, {100 * b[2]:+.1f}] | "
                     f"{100 * s[0]:+.1f} [{100 * s[1]:+.1f}, {100 * s[2]:+.1f}] | {both} / {len(d)} | "
                     f"{int((d.buyer_change < 0).sum())} / {len(d)} |")
    live = df[(df.baseline == "later trades allowed") & (df.multiple == MULTIPLES[0])]
    lines += ["", f"Carrying on as normal, the buyer got the missing orange by a later trade in "
              f"{100 * live.keep_later_to_buyer.mean():.0f}% of the keep games on average; across positions the "
              f"median cash paid was {live.keep_later_multiple.median():.1f}× face value, and "
              f"{100 * live.keep_later_swap_share.mean():.0f}% of those deals were swaps (property given in "
              "exchange, so the cash is only part of the price). \"Both gain\" and \"buyer loses\" count positions "
              "by their point estimates."]
    return "\n".join(lines) + "\n"


def main():
    t = time.time()
    positions = screen()
    screened = positions[-1]["game_seed"] - SCREEN_SEED + 1 if positions else 0
    print(f"{len(positions)} positions from {screened} games ({time.time() - t:.0f}s)", flush=True)
    rows = []
    for j, pos in enumerate(positions):
        rows += value(pos, j)
        if j % 10 == 9:
            print(f"  {j + 1} positions valued ({time.time() - t:.0f}s)", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "game_positions.csv", index=False)
    (TAB / "game_positions.md").write_text(summary(df, screened))
    print((TAB / "game_positions.md").read_text())


if __name__ == "__main__":
    main()
