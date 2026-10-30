"""Render every results figure from the CSVs in results/tables (run the numbered scripts first).

Each chart is a title deed on the board: a cream card with an ink border on the board's mint, a band in the colour
of the property group the chart is about (the board's ink when it's about the whole game), the title in Oswald
capitals (scripts/fonts, SIL Open Font Licence) and the plot below. The colours are the board kit's (watch/board):
houses green, hotels red, every property in its own colour. The data colours were checked for contrast on the card
and for colour-blind readers; where the board's green sits close to its red, orange or pink for them, the chart
also tells the two apart by marker shape, position or a label.
"""
import json
from io import BytesIO
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.transforms import ScaledTranslation, blended_transform_factory
from meta_common import ablations
from PIL import Image, ImageDraw, ImageFont

matplotlib.use("Agg")

from run_config import FIGURES as FIG, TABLES as TAB, scaled  # noqa: E402
FIG.mkdir(parents=True, exist_ok=True)
ROLLOUTS = scaled(2000)  # paired rollouts per price in 04_trade_curve.py and 06_meta_trade_curve.py
DPI = 180
FONTS = Path(__file__).resolve().parent / "fonts"


def games(df) -> str:
    """The sample size of a results table, from its games column ("10,000")."""
    return f"{int(df.games.max()):,}"


# ---------------------------------------------------------------- the board's colours (watch/board)
BOARD, CARD, INK = "#d6e9d4", "#fff9ee", "#203c44"     # mint field, title-deed cream, the board's ink
INK2, MUTED = "#4a5f63", "#6f7c7b"                      # secondary and muted text on the card
GRID, AXIS, NEUTRAL = "#ece4d2", "#cfc6b0", "#d8d1bf"   # hairlines, axis rules, the squares nobody can own
GROUP = {"brown": "#8a5a3b", "light_blue": "#8cc9e8", "pink": "#c9468f", "orange": "#ec8a2c", "red": "#d53a2c",
         "yellow": "#edcb2c", "green": "#22955a", "dark_blue": "#2c58a8", "stations": "#3b3833",
         "utilities": "#9a9488"}
# data colours: the board's own, orange one step darker so that it holds 3:1 on the card
BLUE, RED, GREEN, ORANGE, PINK = "#2c58a8", "#d53a2c", "#22955a", "#d9731c", "#c9468f"
HOUSE, HOTEL = GREEN, RED
# value scales: houses green for amounts; Trafalgar red to Mayfair blue through cream for worse/better
SEQ = ["#f0f6ef", "#d3eadb", "#a9d6b8", "#78bf92", "#4aa36f", "#22955a", "#1a7446", "#11502f"]
DIV = ["#9e2a1f", "#cf4a3b", "#e88f82", "#f5d2cb", "#efe9dc", "#d0dbef", "#8ea8dc", "#4a72bd", "#24498f"]

plt.rcParams.update({
    "figure.facecolor": CARD, "axes.facecolor": CARD, "savefig.facecolor": CARD,
    "font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": AXIS, "ytick.color": AXIS,
    "xtick.labelcolor": INK2, "ytick.labelcolor": INK2, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    "legend.labelcolor": INK, "lines.solid_capstyle": "round",
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
    "three_house": "three houses first", "hoarder": "never builds hotels", "jail_short": "always leaves jail",
    "jail_long": "always stays in jail", "take_chance": "takes the Chance card",
    "no_trade": "never proposes trades", "hard_bargain": "hard bargainer (asks 3×, offers 1.5×)",
}
MODE_TITLE = {"standard": "official rules", "championship": "championship rules"}


# ---------------------------------------------------------------- the title-deed card
def _font(pt: float, face: str = "Oswald-700.ttf") -> ImageFont.FreeTypeFont:
    path = font_manager.findfont("DejaVu Sans") if face == "DejaVu" else str(FONTS / face)
    return ImageFont.truetype(path, round(pt * DPI / 72))


def _width(draw, text: str, font, tracking: float = 0) -> float:
    return draw.textlength(text, font=font) + tracking * max(len(text) - 1, 0)


def _wrap(draw, text: str, font, width: float, tracking: float = 0) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and _width(draw, trial, font, tracking) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line] if line else lines


def _centred(draw, cx: float, y: float, text: str, font, fill: str, tracking: float = 0) -> None:
    x = cx - _width(draw, text, font, tracking) / 2
    if not tracking:
        draw.text((x, y), text, font=font, fill=fill)
        return
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking


def deed(fig, band: str, kicker: str, title: str, sub: str) -> None:
    """Title a chart like a title deed: a band in `band` with the kicker over the title, the subtitle below it."""
    fig._deed = (band, kicker, title, sub)


def card(chart: Image.Image, band: str, kicker: str, title: str, sub: str) -> Image.Image:
    """The rendered chart on a title-deed card, laid on the board's mint."""
    px = DPI / 72
    edge, border, inset, pad = round(9 * px), max(2, round(1.1 * px)), round(4 * px), round(11 * px)
    fk, ft, fs = _font(8, "Oswald-500.ttf"), _font(17), _font(9, "DejaVu")
    tk, tt = 0.16 * 8 * px, 0.02 * 17 * px  # letter-spacing of the kicker and the title, in pixels
    d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    inner = max(chart.width, round(6.4 * DPI))
    text_w = inner - 2 * (inset + pad)
    titles = _wrap(d, title.upper(), ft, text_w, tt)
    subs = [line for part in sub.split("\n") for line in _wrap(d, part, fs, text_w)]
    kh, th, sh = round(8 * px * 1.5), round(17 * px * 1.22), round(9 * px * 1.45)
    band_h = round(0.75 * pad) + kh + len(titles) * th + round(0.8 * pad)
    w = inner + 2 * border
    sub_top = border + inset + band_h + round(0.8 * pad)
    chart_top = sub_top + len(subs) * sh + round(0.5 * pad)
    h = chart_top + chart.height + pad + border
    img = Image.new("RGB", (w + 2 * edge, h + 2 * edge), BOARD)
    d = ImageDraw.Draw(img)
    d.rectangle([edge, edge, edge + w - 1, edge + h - 1], fill=CARD, outline=INK, width=border)
    x0, y0 = edge + border + inset, edge + border + inset
    d.rectangle([x0, y0, edge + w - 1 - border - inset, y0 + band_h], fill=band, outline=INK, width=max(1, border // 2))
    cx = edge + w / 2
    y = y0 + round(0.75 * pad)
    _centred(d, cx, y, kicker.upper(), fk, "#ffffff", tk)
    y += kh
    for line in titles:
        _centred(d, cx, y, line, ft, "#ffffff", tt)
        y += th
    y = edge + sub_top
    for line in subs:
        _centred(d, cx, y, line, fs, INK2)
        y += sh
    img.paste(chart, (round(cx - chart.width / 2), edge + chart_top))
    return img


def save(fig, name):
    buf = BytesIO()
    fig.savefig(buf, dpi=DPI, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    buf.seek(0)
    card(Image.open(buf).convert("RGB"), *fig._deed).save(FIG / name, optimize=True)
    print("wrote", name)


def group_ticks(ax, groups) -> None:
    """Colour groups as y tick labels, each with a square in its board colour beside the axis."""
    ax.set_yticks(range(len(groups)))
    ax.set_yticklabels([GROUP_LABEL[g] for g in groups], color=INK)
    ax.tick_params(axis="y", length=0, pad=17)
    shift = ScaledTranslation(-8.5 / 72, 0, ax.figure.dpi_scale_trans)  # the squares sit 8.5 pt left of the axis
    tr = blended_transform_factory(ax.transAxes, ax.transData) + shift
    for i, g in enumerate(groups):
        ax.plot([0], [i], marker="s", ms=8, color=GROUP[g], transform=tr, clip_on=False, zorder=5)


def plain(ax, rows: int | None = None, cols: int | None = None) -> None:
    """A table-like chart: no grid, spines or tick marks; cells parted by the card's colour, like board squares."""
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    for x in np.arange(0.5, (cols or 0) - 1, 1):
        ax.axvline(x, color=CARD, lw=2.5)
    for y in np.arange(0.5, (rows or 0) - 1, 1):
        ax.axhline(y, color=CARD, lw=2.5)


def key(color: str, marker: str, label: str) -> Line2D:
    """A legend entry for a dot series (an errorbar's own entry carries a stray whisker)."""
    return Line2D([], [], ls="", marker=marker, ms=7, color=color, markeredgecolor=CARD, markeredgewidth=1.5,
                  label=label)


# ---------------------------------------------------------------- the charts
def fig_landing():
    lp = pd.read_csv(TAB / "landing_probabilities.csv")
    y = 100 * lp.landings_per_turn_long
    colour = [GROUP.get(g, NEUTRAL) if isinstance(g, str) else NEUTRAL for g in lp.group]
    ownable = lp.type.isin(["street", "station", "utility"])
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.bar(lp.square, y, width=0.66, color=colour, zorder=3)
    ax.set_xticks(lp.square)
    ax.set_xticklabels([SHORT.get(n, n) for n in lp.name], rotation=90, fontsize=7.5)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Landings per 100 turns")
    ax.grid(axis="x", visible=False)
    ax.set_xlim(-0.8, 39.8)
    ax.set_ylim(0, y.max() * 1.16)
    top = lp[ownable].assign(v=y[ownable]).nlargest(3, "v")
    for _, r in top.iterrows():
        ax.annotate(f"{r.v:.2f}", (r.square, r.v), xytext=(0, 3), textcoords="offset points",
                    ha="center", fontsize=8, color=INK)
    deed(fig, GROUP["red"], "Landing odds", "Trafalgar Square is the most-landed property",
         "Expected landings per 100 turns from the exact Markov chain (staying in jail to roll for doubles), each "
         "property in its colour on the board; grey squares can't be bought. Jail itself: 11.0% of turns.")
    save(fig, "landing_probabilities.png")


def fig_payback():
    gt = pd.read_csv(TAB / "group_economics_4p.csv")
    gt = gt[gt.group.isin(GROUP_LABEL)]
    piv = gt.pivot(index="group", columns="level", values="payback_rounds").sort_values("hotel", ascending=False)
    ypos, h = np.arange(len(piv)), 0.34
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.barh(ypos + h / 2, piv["3 houses"], height=h, color=HOUSE, label="3 houses", zorder=3)
    ax.barh(ypos - h / 2, piv["hotel"], height=h, color=HOTEL, label="Hotel", zorder=3)
    for i, (a, b) in enumerate(zip(piv["3 houses"], piv["hotel"])):
        ax.text(a + 0.15, i + h / 2, f"{a:.1f}", va="center", fontsize=8, color=INK2)
        ax.text(b + 0.15, i - h / 2, f"{b:.1f}", va="center", fontsize=8, color=INK2)
    group_ticks(ax, list(piv.index))
    ax.set_xlabel("Rounds to pay back the whole set + buildings (4 players)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", fontsize=9)
    deed(fig, GROUP["orange"], "Payback", "Orange pays for itself fastest, at any table size",
         "Investment ÷ rent per round from 3 opponents, houses green and hotels red as on the board. "
         "Other sizes: multiply by 3/(n−1); the ranking never changes.")
    save(fig, "payback_by_group.png")


def fig_marginal():
    gt = pd.read_csv(TAB / "group_economics_4p.csv")
    gt = gt[gt.group.isin(GROUP_LABEL) & (gt.level != "set")]
    order = list(GROUP_LABEL)
    levels = ["1 house", "2 houses", "3 houses", "4 houses", "hotel"]
    m = gt.pivot(index="group", columns="level", values="marginal_roi_per_round").loc[order, levels] * 100
    fig, ax = plt.subplots(figsize=(7.5, 4.9))
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("houses", SEQ)
    im = ax.imshow(m.values, cmap=cmap, aspect="auto", vmin=0, vmax=m.values.max())
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.values[i, j]
            ax.text(j, i, f"{v:.0f}%", ha="center", va="center", fontsize=8.5,
                    color="#ffffff" if v > 0.6 * m.values.max() else INK)
    ax.set_xticks(range(len(levels)))
    ax.set_xticklabels(["1st house", "2nd", "3rd", "4th", "Hotel"], color=INK)
    plain(ax, *m.shape)
    group_ticks(ax, order)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=AXIS, labelcolor=MUTED, labelsize=8)
    deed(fig, GROUP["green"], "Houses and hotels", "The third house is the best money you can spend",
         "Extra rent per round (3 opponents) per £ spent on that building level")
    save(fig, "marginal_return_heatmap.png")


def fig_seat():
    sa = pd.read_csv(TAB / "seat_advantage.csv")
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for label, pick, color, marker, dx in [("First player", "first", BLUE, "o", -0.08),
                                           ("Last player", "last", RED, "s", 0.08)]:
        xs, ys, lo, hi = [], [], [], []
        for n, d in sa.groupby("n_players"):
            r = d.iloc[0] if pick == "first" else d.iloc[-1]
            xs.append(n + dx)
            ys.append(100 * (r.win_rate - r.fair_share))
            lo.append(100 * (r.win_rate - r.ci_low))
            hi.append(100 * (r.ci_high - r.win_rate))
        ax.errorbar(xs, ys, yerr=[lo, hi], fmt=marker, color=color, ms=7, capsize=0, elinewidth=1.6,
                    label=label, zorder=3, markeredgecolor=CARD, markeredgewidth=1.5)
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_xticks(range(2, 7))
    ax.set_xlabel("Number of players")
    ax.set_ylabel("Win rate minus fair share (pp)")
    ax.grid(axis="x", visible=False)
    ax.legend(handles=[key(BLUE, "o", "First player"), key(RED, "s", "Last player")], loc="upper left", fontsize=9)
    deed(fig, INK, "Seat order", "Going first is a real edge once there are 3+ players",
         f"Identical simple bots in fixed seats, {int(sa.games.max()):,} games per table size; outright wins, "
         "95% Wilson intervals")
    save(fig, "seat_advantage.png")


def _diverging_heatmap(m, lo, hi, ax):
    """Ratios on a log scale, red below 1 and blue above, full colour at 0.5x and 2x (the numbers carry the rest);
    empty cells (NaN) are left blank with a dash."""
    logm = np.ma.masked_invalid(np.log2(m.values.astype(float)))
    lim = 1.0
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("worse-better", DIV)
    cmap.set_bad(CARD)
    ax.imshow(logm, cmap=cmap, vmin=-lim, vmax=lim, aspect="auto")
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.values[i, j]
            if not np.isfinite(v):
                ax.text(j, i, "—", ha="center", va="center", fontsize=9, color=MUTED)
                continue
            sig = lo.values[i, j] > 1 or hi.values[i, j] < 1
            ax.text(j, i, f"{v:.2f}×" + ("" if sig else "*"), ha="center", va="center", fontsize=9,
                    color="#ffffff" if abs(logm[i, j]) > 0.7 * lim else INK)
    ax.set_xticks(range(m.shape[1]))
    ax.set_xticklabels([f"{n} players" for n in m.columns], color=INK)
    ax.set_yticks(range(m.shape[0]))
    ax.set_yticklabels(m.index, color=INK)
    plain(ax, *m.shape)


def fig_strategies(mode="standard"):
    """Win rate relative to fair share, for every variant at every player count (diverging heatmap)."""
    champ = mode == "championship"
    sv = pd.read_csv(TAB / ("championship_strategy_variants.csv" if champ else "strategy_variants.csv"))
    sv = sv[sv.variant != "random"]
    order = (sv.groupby("variant").relative.mean().sort_values(ascending=False).index.tolist())
    counts = sorted(sv.n_players.unique())
    piv = {k: sv.pivot(index="variant", columns="n_players", values=k).loc[order, counts]
           for k in ("relative", "rel_low", "rel_high")}
    piv["relative"].index = [VARIANT_LABEL.get(v, v) for v in order]
    fig, ax = plt.subplots(figsize=(8, 5.6))
    _diverging_heatmap(piv["relative"], piv["rel_low"], piv["rel_high"], ax)
    deed(fig, INK, f"Strategy tweaks · {MODE_TITLE[mode]}", "Which tweaks to the simple bot win?",
         f"One tweaked bot against simple bots: outright wins ÷ fair share, {games(sv)} games per cell.\n"
         "Red loses (darkest at 0.5× or less), blue wins; * = not significant at 95%")
    save(fig, "strategy_variants_championship.png" if champ else "strategy_variants.png")


def fig_deal_zone():
    """Seller's break-even and buyer's maximum for Vine Street, by player count and by who plays on."""
    rows = [("simple bots", TAB / "trade_curve_summary.csv", GREEN)]
    for mode, col in (("standard", BLUE), ("championship", PINK)):
        rows.append((f"meta agents, {MODE_TITLE[mode]}", TAB / f"meta_trade_summary_{mode}.csv", col))
    rows = [(lab, pd.read_csv(f).query("buyer == 0") if "buyer" in pd.read_csv(f) else pd.read_csv(f), col)
            for lab, f, col in rows if f.exists()]
    offsets = np.linspace(-0.27, 0.27, len(rows)) if len(rows) > 1 else [0.0]
    fig, ax = plt.subplots(figsize=(11, 6.8))
    for (lab, s, col), dy in zip(rows, offsets):
        for _, r in s.sort_values("n_players").iterrows():
            y = r.n_players + dy
            lo, hi = r.seller_min_price_win, r.buyer_max_price_win
            cens = bool(r.get("buyer_max_censored", False))
            if not bool(r.get("legal", True)):
                ax.text(1265, y, f"{lab}: not allowed (no trades heads-up)", fontsize=7.5, color=MUTED, va="center")
                continue
            if bool(r.get("deal_zone_exists", hi > lo)) and np.isfinite(lo) and np.isfinite(hi):
                ax.plot([lo, hi], [y, y], color=col, lw=6, alpha=0.35, solid_capstyle="round", zorder=2)
                txt = f"£{lo:,.0f} – £{hi:,.0f}" + ("+" if cens else "")
            elif np.isfinite(lo) and np.isfinite(hi):
                txt = f"none (both break even at £{lo:,.0f})"
            elif np.isfinite(hi):
                txt = "none (seller loses at every price)"
            else:
                txt = "none"
            if np.isfinite(lo):
                ax.plot(lo, y, "o", ms=7.5, markerfacecolor=CARD, markeredgecolor=col, markeredgewidth=2, zorder=3)
            if np.isfinite(hi):
                ax.plot(hi, y, "o", ms=7.5, color=col, markeredgecolor=CARD, markeredgewidth=1.4, zorder=4)
            ax.text(1265, y, f"{lab}: {txt}", fontsize=7.5, color=INK2, va="center")
    counts = sorted(rows[0][1].n_players)
    ax.set_yticks(counts)
    ax.set_yticklabels([f"{n} players" for n in counts], color=INK)
    ax.tick_params(axis="y", length=0)
    ax.set_ylim(max(counts) + 0.6, min(counts) - 0.6)
    ax.set_xlim(0, 1900)
    ax.set_xticks(range(0, 1201, 200))
    ax.set_xlabel("Price for Vine Street (£)")
    ax.grid(axis="y", visible=False)
    handles = [Line2D([], [], color=col, lw=6, alpha=0.35, label=f"Deal zone, {lab}") for lab, _, col in rows]
    handles += [Line2D([], [], ls="", marker="o", ms=7.5, markerfacecolor=CARD, markeredgecolor=INK2,
                       markeredgewidth=2, label="Seller's break-even"),
                Line2D([], [], ls="", marker="o", ms=7.5, color=INK2, label="Buyer's maximum")]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.45, -0.1), ncol=3, fontsize=8)
    deed(fig, GROUP["orange"], "Vine Street", "Is there a price that suits both sides?",
         f"Orange-squeeze position; {ROLLOUTS:,} paired rollouts per price; "
         "'+' = the buyer would pay all £1,200 they have")
    save(fig, "deal_zone_by_players.png")


def fig_house_rules():
    hr = pd.read_csv(TAB / "house_rules.csv")
    fig, ax = plt.subplots(figsize=(8, 4.4))
    names = {"official": ("Official rules", BLUE, "o"), "free_parking_jackpot": ("Free Parking jackpot", GREEN, "s"),
             "no_auctions": ("No auctions", ORANGE, "^")}
    for key, (lab, col, marker) in names.items():
        d = hr[hr.rules == key].sort_values("n_players")
        ax.plot(d.n_players, d.median_rounds, "-" + marker, color=col, lw=2, ms=7, label=lab,
                markeredgecolor=CARD, markeredgewidth=1.5)
    champ = TAB / "championship_seat_advantage.csv"
    if champ.exists():
        d = pd.read_csv(champ).groupby("n_players").median_rounds.first()
        ax.plot(d.index, d.values, "-D", color=PINK, lw=2, ms=6.5, label="Championship rules (Speed Die)",
                markeredgecolor=CARD, markeredgewidth=1.5)
    ax.set_xticks(sorted(hr.n_players.unique()))
    ax.set_xlabel("Number of players")
    ax.set_ylabel("Median game length (rounds)")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_ylim(bottom=0)
    deed(fig, INK, "Game length", "More players, shorter games (in rounds)",
         f"Identical simple bots; {games(hr)} games per point")
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
        ax.axvspan(lo, hi, color=GROUP["orange"], alpha=0.12, lw=0, zorder=1)
        ax.text((lo + hi) / 2, 88, f"deal zone: £{lo:,.0f} – £{hi:,.0f}", ha="center", va="top",
                color=INK2, fontsize=9)
    for d, col, lab in [(buyer, BLUE, "Buyer (owns the other two oranges)"),
                        (seller, RED, "Seller (owns Vine Street)")]:
        ax.fill_between(d.price, 100 * (d.d_win - 1.96 * d.d_win_se), 100 * (d.d_win + 1.96 * d.d_win_se),
                        color=col, alpha=0.12, lw=0, zorder=2)
        ax.plot(d.price, 100 * d.d_win, color=col, lw=2, label=lab, zorder=3)
    ax.plot(by.price, 100 * by.d_win, color=MUTED, lw=2, label=f"The {n_players - 2} other players (combined)",
            zorder=3)
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_xlabel("Price paid for Vine Street (£)")
    ax.set_ylabel("Change in win probability (pp)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, fontsize=8.5)
    ax.grid(axis="x", visible=False)
    deed(fig, GROUP["orange"], f"Vine Street · {n_players} players", "What is Vine Street worth, and to whom?",
         f"Orange-squeeze position, {ROLLOUTS:,} paired rollouts per price (common random numbers); "
         "bands = 95% CI")
    save(fig, "trade_curve_vine_street.png")

    fig, ax = plt.subplots(figsize=(8, 4.4))
    for b, col, lab in [(0, ORANGE, "Sell to the player who completes orange"),
                        (2, BLUE, "Sell to a player who doesn't")]:
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
    deed(fig, GROUP["orange"], f"Vine Street · {n_players} players", "Who you sell to matters as much as the price",
         f"Seller = owner of Vine Street; {n_players} players, same position and rollouts as above")
    save(fig, "trade_curve_who_you_sell_to.png")


def no_op_ablations(mode):
    """(n_players, name) of one-change ablations that leave that meta agent unchanged."""
    metas = json.loads((TAB / f"meta_agents_{mode}.json").read_text())
    out = set()
    for n, g in metas.items():
        genome = {k: v for k, v in g.items() if k != "name"}
        out |= {(int(n), name) for name, variant in ablations(genome).items() if variant == genome}
    return out


RENAMED = {"three-house cap": "three houses first"}  # build_cap 3 is a priority, not a cap (it still builds hotels)


def fig_meta_ablations(mode):
    ab = pd.read_csv(TAB / f"meta_ablations_{mode}.csv")
    ab["name"] = ab.name.replace(RENAMED)
    skip = no_op_ablations(mode)
    ab = ab[[(int(n), name) not in skip and name != "meta agent (placebo)" for n, name in zip(ab.n_players, ab.name)]]
    # no effect at all: the same result in every game, so the change never altered a decision (e.g. a take-a-Chance
    # flip for an agent whose card counting makes that choice); shown like a change the agent already plays
    same = (ab.rel_low == 1) & (ab.rel_high == 1)
    if "no_effect" in ab:  # rows from a partial re-run may lack it: fall back to the identical-results test there
        same = ab.no_effect.astype("boolean").fillna(same).astype(bool)
    ab.loc[same, ["relative", "rel_low", "rel_high"]] = np.nan
    order = ab.groupby("name").relative.mean().sort_values(ascending=False).index.tolist()
    piv = {k: ab.pivot(index="name", columns="n_players", values=k).loc[order]
           for k in ("relative", "rel_low", "rel_high")}
    fig, ax = plt.subplots(figsize=(8.5, 6.2))
    _diverging_heatmap(piv["relative"], piv["rel_low"], piv["rel_high"], ax)
    deed(fig, GROUP["dark_blue"], f"Off the meta · {MODE_TITLE[mode]}", "Deviating from the meta",
         f"One setting changed in one meta agent, against unchanged agents; {games(ab)} games per cell"
         + ("; credit = championship points.\n" if mode == "championship" else ".\n")
         + "Red loses (darkest at 0.5× or less), blue wins; * = not significant; — = no effect: the agent already "
         "plays this way, or the change never altered a decision")
    save(fig, f"meta_ablations_{mode}.png")


def fig_meta_validation(mode):
    v = pd.read_csv(TAB / f"meta_validation_{mode}.csv")
    series = [("meta agent vs baseline bots", BLUE, "o", "Meta agent at a table of simple bots"),
              ("baseline bot vs meta agents", RED, "s", "Simple bot at a table of meta agents"),
              ("best challenger vs meta agents", GREEN, "D", "Best challenger at a table of meta agents")]
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    for k, (name, col, marker, lab) in enumerate(series):
        d = v[v.name == name].sort_values("n_players")
        x = d.n_players + (k - 1) * 0.12
        ax.errorbar(x, d.relative, yerr=[d.relative - d.rel_low, d.rel_high - d.relative], fmt=marker,
                    color=col, ms=7 if marker != "D" else 6.5, elinewidth=1.6, capsize=0, label=lab, zorder=3,
                    markeredgecolor=CARD, markeredgewidth=1.5)
    ax.axhline(1, color=AXIS, lw=1)
    ax.set_xticks(range(2, 7))
    ax.set_xlabel("Number of players")
    ax.set_ylabel("Win credit, relative" if mode == "standard" else "Points credit, relative")
    ax.grid(axis="x", visible=False)
    ax.legend(handles=[key(col, marker, lab) for _, col, marker, lab in series], loc="upper center",
              bbox_to_anchor=(0.5, -0.16), ncol=3, fontsize=8.5)
    deed(fig, GROUP["dark_blue"], f"Champions' table · {MODE_TITLE[mode]}", "How strong are the meta agents?",
         f"1.0 = level with the player it replaces, on the same {games(v)} games; 95% bootstrap intervals"
         + ("; credit = championship points ÷ 28, not a win probability" if mode == "championship" else ""))
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
