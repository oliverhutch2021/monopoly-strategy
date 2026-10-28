"""Render every results figure from the CSVs in results/tables (run the numbered scripts first)."""
import json

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from meta_common import ablations

matplotlib.use("Agg")

from run_config import FIGURES as FIG, TABLES as TAB  # noqa: E402
FIG.mkdir(parents=True, exist_ok=True)

# reference palette (light mode) from the dataviz method
SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlecolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 13, "axes.titleweight": "semibold", "axes.titlelocation": "left",
    "legend.frameon": False,
})

SHORT = {
    "The Angel Islington": "Angel Islington", "Northumberland Avenue": "Northumberland Ave",
    "Kings Cross Station": "King's Cross Stn", "Marylebone Station": "Marylebone Stn",
    "Fenchurch St Station": "Fenchurch St Stn", "Liverpool Street Station": "Liverpool St Stn",
    "Jail / Just Visiting": "Just Visiting", "Community Chest": "Comm. Chest",
}
GROUP_LABEL = {"brown": "Brown", "light_blue": "Light blue", "pink": "Pink", "orange": "Orange",
               "red": "Red", "yellow": "Yellow", "green": "Green", "dark_blue": "Dark blue"}


VARIANT_LABEL = {
    "aggressive": "aggressive (no cash buffer)", "cautious": "cautious (£400 buffer)",
    "three_house": "three-house cap", "hoarder": "never builds hotels", "jail_short": "always leaves jail",
    "jail_long": "always stays in jail", "take_chance": "takes the Chance card",
    "no_trade": "never proposes trades", "hard_bargain": "hard bargainer (asks 3×, offers 1.5×)",
}


def title(ax, main, sub):
    ax.set_title(main, pad=26)
    ax.text(0, 1.02, sub, transform=ax.transAxes, color=INK2, fontsize=9.5, va="bottom")


def save(fig, name):
    fig.savefig(FIG / name, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


def fig_landing():
    lp = pd.read_csv(TAB / "landing_probabilities.csv")
    y = 100 * lp.landings_per_turn_long
    ownable = lp.type.isin(["street", "station", "utility"])
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.bar(lp.square[ownable], y[ownable], width=0.62, color=S1, label="Property you can buy", zorder=3)
    ax.bar(lp.square[~ownable], y[~ownable], width=0.62, color=AXIS, label="Other square", zorder=3)
    ax.set_xticks(lp.square)
    ax.set_xticklabels([SHORT.get(n, n) for n in lp.name], rotation=90, fontsize=7.5, color=INK2)
    ax.set_ylabel("Landings per 100 turns")
    ax.grid(axis="x", visible=False)
    ax.set_xlim(-0.8, 39.8)
    ax.set_ylim(0, y.max() * 1.16)
    top = lp[ownable].assign(v=y[ownable]).nlargest(3, "v")
    for _, r in top.iterrows():
        ax.annotate(f"{r.v:.2f}", (r.square, r.v), xytext=(0, 3), textcoords="offset points",
                    ha="center", fontsize=8, color=INK)
    ax.legend(loc="upper left", fontsize=8.5, ncol=2, bbox_to_anchor=(0, 1.0))
    title(ax, "Trafalgar Square is the most-landed property on the UK board",
          "Expected landings per 100 turns from the exact Markov chain (long-stay jail strategy). "
          "Jail itself: 11.0% of turns.")
    save(fig, "landing_probabilities.png")


def fig_payback():
    gt = pd.read_csv(TAB / "group_economics_4p.csv")
    gt = gt[gt.group.isin(GROUP_LABEL)]
    piv = gt.pivot(index="group", columns="level", values="payback_rounds")
    piv = piv.sort_values("hotel", ascending=False)
    ypos = np.arange(len(piv))
    h = 0.34
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.barh(ypos + h / 2, piv["3 houses"], height=h, color=S1, label="3 houses", zorder=3)
    ax.barh(ypos - h / 2, piv["hotel"], height=h, color=S2, label="Hotel", zorder=3)
    for i, (a, b) in enumerate(zip(piv["3 houses"], piv["hotel"])):
        ax.text(a + 0.15, i + h / 2, f"{a:.1f}", va="center", fontsize=8, color=INK2)
        ax.text(b + 0.15, i - h / 2, f"{b:.1f}", va="center", fontsize=8, color=INK2)
    ax.set_yticks(ypos)
    ax.set_yticklabels([GROUP_LABEL[g] for g in piv.index], color=INK)
    ax.set_xlabel("Rounds to pay back the whole set + buildings (4 players)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", fontsize=9)
    title(ax, "Orange pays for itself fastest, at any table size",
          "Investment ÷ rent per round from 3 opponents. Other sizes: multiply by 3/(n−1); the ranking never changes")
    save(fig, "payback_by_group.png")


def fig_marginal():
    gt = pd.read_csv(TAB / "group_economics_4p.csv")
    gt = gt[gt.group.isin(GROUP_LABEL) & (gt.level != "set")]
    order = list(GROUP_LABEL)
    levels = ["1 house", "2 houses", "3 houses", "4 houses", "hotel"]
    m = gt.pivot(index="group", columns="level", values="marginal_roi_per_round").loc[order, levels] * 100
    fig, ax = plt.subplots(figsize=(7.5, 4.9))
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("seq", SEQ)
    im = ax.imshow(m.values, cmap=cmap, aspect="auto", vmin=0, vmax=m.values.max())
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.values[i, j]
            ax.text(j, i, f"{v:.0f}%", ha="center", va="center", fontsize=8.5,
                    color="#ffffff" if v > 0.55 * m.values.max() else INK)
    ax.set_xticks(range(len(levels)))
    ax.set_xticklabels(["1st house", "2nd", "3rd", "4th", "Hotel"], color=INK)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([GROUP_LABEL[g] for g in order], color=INK)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=MUTED, labelsize=8)
    title(ax, "The third house is the best money you can spend",
          "Extra rent per round (3 opponents) per £ spent on that building level")
    save(fig, "marginal_return_heatmap.png")


def fig_seat():
    sa = pd.read_csv(TAB / "seat_advantage.csv")
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for (label, pick, color, dx) in [("First player", "first", S1, -0.08), ("Last player", "last", S2, 0.08)]:
        xs, ys, lo, hi = [], [], [], []
        for n, d in sa.groupby("n_players"):
            r = d.iloc[0] if pick == "first" else d.iloc[-1]
            xs.append(n + dx)
            ys.append(100 * (r.win_rate - r.fair_share))
            lo.append(100 * (r.win_rate - r.ci_low))
            hi.append(100 * (r.ci_high - r.win_rate))
        ax.errorbar(xs, ys, yerr=[lo, hi], fmt="o", color=color, ms=7, capsize=0, elinewidth=1.6,
                    label=label, zorder=3, markeredgecolor=SURFACE, markeredgewidth=1.5)
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_xticks(range(2, 7))
    ax.set_xlabel("Number of players")
    ax.set_ylabel("Win rate minus fair share (pp)")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", fontsize=9)
    title(ax, "Going first is a real edge once there are 3+ players",
          "Identical 'balanced' bots, fixed seats; 95% Wilson intervals")
    save(fig, "seat_advantage.png")


def fig_strategies(mode="standard"):
    """Win rate relative to fair share, for every variant at every player count (diverging heatmap)."""
    champ = mode == "championship"
    sv = pd.read_csv(TAB / ("championship_strategy_variants.csv" if champ else "strategy_variants.csv"))
    sv = sv[sv.variant != "random"]
    order = (sv.groupby("variant").relative.mean().sort_values(ascending=False).index.tolist())
    counts = sorted(sv.n_players.unique())
    m = sv.pivot(index="variant", columns="n_players", values="relative").loc[order, counts]
    lo = sv.pivot(index="variant", columns="n_players", values="rel_low").loc[order, counts]
    hi = sv.pivot(index="variant", columns="n_players", values="rel_high").loc[order, counts]
    logm = np.log2(m.values)
    lim = np.abs(logm).max()
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
        "div", ["#b8302f", "#e34948", "#f4b4b3", "#f0efec", "#9ec5f4", "#3987e5", "#184f95"])
    fig, ax = plt.subplots(figsize=(8, 5.6))
    ax.imshow(logm, cmap=cmap, vmin=-lim, vmax=lim, aspect="auto")
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.values[i, j]
            sig = lo.values[i, j] > 1 or hi.values[i, j] < 1
            ax.text(j, i, f"{v:.2f}×" + ("" if sig else "*"), ha="center", va="center", fontsize=9,
                    color="#ffffff" if abs(logm[i, j]) > 0.6 * lim else INK)
    ax.set_xticks(range(len(counts)))
    ax.set_xticklabels([f"{n} players" for n in counts], color=INK)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([VARIANT_LABEL.get(v, v) for v in order], color=INK)
    ax.tick_params(length=0)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    question = " under championship rules?" if champ else ", at every table size?"
    title(ax, "Which tweaks to the baseline bot win" + question,
          f"Win rate ÷ fair share vs (n−1) baseline bots; {'6,000' if champ else '10,000'} games per cell; "
          "* = not significant at 95%")
    save(fig, "strategy_variants_championship.png" if champ else "strategy_variants.png")


def fig_deal_zone():
    """Seller's break-even and buyer's maximum for Vine Street, by player count and by who plays on."""
    rows = [("simple bots", TAB / "trade_curve_summary.csv", S3)]
    for mode, col in (("standard", "#6250d6"), ("championship", "#e87ba4")):
        rows.append((f"meta, {mode}", TAB / f"meta_trade_summary_{mode}.csv", col))
    rows = [(lab, pd.read_csv(f).query("buyer == 0") if "buyer" in pd.read_csv(f) else pd.read_csv(f), col)
            for lab, f, col in rows if f.exists()]
    offsets = np.linspace(-0.27, 0.27, len(rows)) if len(rows) > 1 else [0.0]
    fig, ax = plt.subplots(figsize=(10.5, 6.8))
    seen = set()
    for (lab, s, col), dy in zip(rows, offsets):
        for _, r in s.sort_values("n_players").iterrows():
            y = r.n_players + dy
            lo, hi = r.seller_min_price_win, r.buyer_max_price_win
            cens = bool(r.get("buyer_max_censored", False))
            if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
                key = f"Deal zone ({lab})"
                ax.plot([lo, hi], [y, y], color=col, lw=6, alpha=0.55, solid_capstyle="round", zorder=2,
                        label=key if key not in seen else None)
                seen.add(key)
                txt = f"£{lo:,.0f} – £{hi:,.0f}" + ("+" if cens else "")
            elif np.isfinite(lo) and np.isfinite(hi):
                txt = f"none (both break even at £{lo:,.0f})"
            elif np.isfinite(hi):
                txt = "none (seller loses at every price)"
            else:
                txt = "none"
            for v, c, name in [(lo, S2, "Seller's break-even"), (hi, S1, "Buyer's maximum")]:
                if np.isfinite(v):
                    ax.plot(v, y, "o", color=c, ms=7, markeredgecolor=SURFACE, markeredgewidth=1.6, zorder=3,
                            label=name if name not in seen else None)
                    seen.add(name)
            ax.text(1265, y, txt, fontsize=7.5, color=INK2, va="center")
            ax.text(390, y, lab, fontsize=7, color=MUTED, va="center", ha="right")
    counts = sorted(rows[0][1].n_players)
    ax.set_yticks(counts)
    ax.set_yticklabels([f"{n} players" for n in counts], color=INK)
    ax.set_ylim(max(counts) + 0.6, min(counts) - 0.6)
    ax.set_xlim(250, 1750)
    ax.set_xticks(range(400, 1201, 200))
    ax.set_xlabel("Price for Vine Street (£)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.1), ncol=3, fontsize=8)
    title(ax, "Is there a price that suits both sides?",
          "Orange-squeeze position; 2,000 paired rollouts per price; '+' = buyer would pay all £1,200 they have")
    save(fig, "deal_zone_by_players.png")


def fig_house_rules():
    hr = pd.read_csv(TAB / "house_rules.csv")
    fig, ax = plt.subplots(figsize=(8, 4.4))
    names = {"official": ("Official rules", S1), "free_parking_jackpot": ("Free Parking jackpot", S2),
             "no_auctions": ("No auctions", S3)}
    for key, (lab, col) in names.items():
        d = hr[hr.rules == key].sort_values("n_players")
        ax.plot(d.n_players, d.median_rounds, "-o", color=col, lw=2, ms=7, label=lab,
                markeredgecolor=SURFACE, markeredgewidth=1.5)
    champ = TAB / "championship_seat_advantage.csv"
    if champ.exists():
        d = pd.read_csv(champ).groupby("n_players").median_rounds.first()
        ax.plot(d.index, d.values, "-o", color="#6250d6", lw=2, ms=7, label="Championship rules (Speed Die)",
                markeredgecolor=SURFACE, markeredgewidth=1.5)
    ax.set_xticks(sorted(hr.n_players.unique()))
    ax.set_xlabel("Number of players")
    ax.set_ylabel("Median game length (rounds)")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper right", fontsize=9)
    title(ax, "More players, shorter games (in rounds)", "Identical baseline bots; 6,000 games per point")
    ax.set_ylim(bottom=0)
    save(fig, "game_length_by_players.png")


def fig_trade(n_players=4):
    c = pd.read_csv(TAB / "trade_curve_orange_squeeze.csv")
    s = pd.read_csv(TAB / "trade_curve_summary.csv")
    c, s = c[c.n_players == n_players], s[s.n_players == n_players]
    c0 = c[c.buyer == 0]
    seller = c0[c0.player == 1].sort_values("price")
    buyer = c0[c0.player == 0].sort_values("price")
    by = c0[c0.player >= 2].groupby("price").agg(d_win=("d_win", "sum")).reset_index()
    fig, ax = plt.subplots(figsize=(9, 4.9))
    lo = s[s.buyer == 0].seller_min_price_win.iloc[0]
    hi = s[s.buyer == 0].buyer_max_price_win.iloc[0]
    if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
        ax.axvspan(lo, hi, color=S3, alpha=0.10, lw=0, zorder=1)
        ax.text((lo + hi) / 2, 88, f"deal zone: £{lo:,.0f} – £{hi:,.0f}", ha="center", va="top",
                color=INK2, fontsize=9)
    for d, col, lab in [(buyer, S1, "Buyer (owns the other two oranges)"), (seller, S2, "Seller (owns Vine Street)")]:
        ax.fill_between(d.price, 100 * (d.d_win - 1.96 * d.d_win_se), 100 * (d.d_win + 1.96 * d.d_win_se),
                        color=col, alpha=0.12, lw=0, zorder=2)
        ax.plot(d.price, 100 * d.d_win, color=col, lw=2, label=lab, zorder=3)
    ax.plot(by.price, 100 * by.d_win, color=MUTED, lw=2, ls="-",
            label=f"The {n_players - 2} other players (combined)", zorder=3)
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_xlabel("Price paid for Vine Street (£)")
    ax.set_ylabel("Change in win probability (pp)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, fontsize=8.5)
    ax.grid(axis="x", visible=False)
    title(ax, f"What is Vine Street worth, and to whom? ({n_players} players)",
          "Orange-squeeze position, 2,000 paired rollouts per price (common random numbers); bands = 95% CI")
    save(fig, "trade_curve_vine_street.png")

    fig, ax = plt.subplots(figsize=(8, 4.4))
    for b, col, lab in [(0, S1, "Sell to the player who completes orange"), (2, S3, "Sell to a player who doesn't")]:
        d = c[(c.buyer == b) & (c.player == 1)].sort_values("price")
        d = d[d.price <= 600]
        ax.fill_between(d.price, 100 * (d.d_win - 1.96 * d.d_win_se), 100 * (d.d_win + 1.96 * d.d_win_se),
                        color=col, alpha=0.12, lw=0)
        ax.plot(d.price, 100 * d.d_win, color=col, lw=2, label=lab)
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_xlabel("Price (£)")
    ax.set_ylabel("Seller's change in win probability (pp)")
    ax.legend(loc="upper left", fontsize=8.5)
    ax.grid(axis="x", visible=False)
    title(ax, "Who you sell to matters as much as the price",
          f"Seller = owner of Vine Street; {n_players} players, same position and rollouts as above")
    save(fig, "trade_curve_who_you_sell_to.png")


def _diverging_heatmap(m, lo, hi, ax):
    logm = np.log2(m.values)
    lim = max(np.abs(logm).max(), 0.05)
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
        "div", ["#b8302f", "#e34948", "#f4b4b3", "#f0efec", "#9ec5f4", "#3987e5", "#184f95"])
    ax.imshow(logm, cmap=cmap, vmin=-lim, vmax=lim, aspect="auto")
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.values[i, j]
            sig = lo.values[i, j] > 1 or hi.values[i, j] < 1
            ax.text(j, i, f"{v:.2f}×" + ("" if sig else "*"), ha="center", va="center", fontsize=9,
                    color="#ffffff" if abs(logm[i, j]) > 0.6 * lim else INK)
    ax.set_xticks(range(m.shape[1]))
    ax.set_xticklabels([f"{n} players" for n in m.columns], color=INK)
    ax.set_yticks(range(m.shape[0]))
    ax.set_yticklabels(m.index, color=INK)
    ax.tick_params(length=0)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)


MODE_TITLE = {"standard": "official rules", "championship": "championship rules (Speed Die)"}


def no_op_ablations(mode):
    """(n_players, name) of one-change ablations that leave that meta agent unchanged."""
    metas = json.loads((TAB / f"meta_agents_{mode}.json").read_text())
    out = set()
    for n, g in metas.items():
        genome = {k: v for k, v in g.items() if k != "name"}
        out |= {(int(n), name) for name, variant in ablations(genome).items() if variant == genome}
    return out


def fig_meta_ablations(mode):
    ab = pd.read_csv(TAB / f"meta_ablations_{mode}.csv")
    skip = no_op_ablations(mode)
    ab = ab[[(int(n), name) not in skip and name != "meta agent (placebo)" for n, name in zip(ab.n_players, ab.name)]]
    order = ab.groupby("name").relative.mean().sort_values(ascending=False).index.tolist()
    piv = {k: ab.pivot(index="name", columns="n_players", values=k).loc[order]
           for k in ("relative", "rel_low", "rel_high")}
    fig, ax = plt.subplots(figsize=(8.5, 6.2))
    _diverging_heatmap(piv["relative"], piv["rel_low"], piv["rel_high"], ax)
    title(ax, f"Deviating from the meta, {MODE_TITLE[mode]}",
          "One deviating player vs (n−1) meta agents, relative to a meta agent at the same table; "
          "4,000 games per cell; * = not significant")
    save(fig, f"meta_ablations_{mode}.png")


def fig_meta_validation(mode):
    v = pd.read_csv(TAB / f"meta_validation_{mode}.csv")
    series = [("meta agent vs baseline bots", S1, "Meta agent vs simple bots", "relative"),
              ("baseline bot vs meta agents", S2, "Simple bot at a table of meta agents", "relative"),
              ("best challenger vs meta agents", S3, "Best challenger trained against the meta", "relative")]
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    for k, (name, col, lab, key) in enumerate(series):
        d = v[v.name == name].sort_values("n_players")
        x = d.n_players + (k - 1) * 0.12
        ax.errorbar(x, d[key], yerr=[d[key] - d.rel_low, d.rel_high - d[key]], fmt="o",
                    color=col, ms=7, elinewidth=1.6, capsize=0, label=lab, zorder=3,
                    markeredgecolor=SURFACE, markeredgewidth=1.5)
    ax.axhline(1, color=AXIS, lw=1)
    ax.set_xticks(range(2, 7))
    ax.set_xlabel("Number of players")
    ax.set_ylabel("Win credit, relative")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3, fontsize=8.5)
    title(ax, f"How strong are the meta agents? ({MODE_TITLE[mode]})",
          "1.0 = level with the player it replaces, on the same 4,000 games; 95% bootstrap CIs")
    save(fig, f"meta_validation_{mode}.png")


if __name__ == "__main__":
    jobs = [fig_landing, fig_payback, fig_marginal, fig_seat, fig_strategies, fig_deal_zone,
            fig_house_rules, fig_trade]
    jobs += [lambda: fig_strategies("championship")]
    for mode in ("standard", "championship"):
        jobs += [lambda m=mode: fig_meta_ablations(m), lambda m=mode: fig_meta_validation(m)]
    for f in jobs:
        try:
            f()
        except (FileNotFoundError, KeyError) as e:
            print("skip", getattr(f, "__name__", "meta figure"), repr(e))
