"""Check the README's numbers against the result tables they come from.

    python scripts/claims.py              # every claim, with OK or MISSING; exits 1 if any is missing
    python scripts/claims.py --quiet      # only the missing ones

Each claim recomputes a number, or a row of a table, from results/final/tables and writes it the way the README
does. It passes when that text is in the README (line breaks and repeated spaces ignored). So when a re-run moves a
number, the claim fails until the prose is updated, and a README edit that mistypes a number fails too.

Covered: findings 1-7 (simple bots), 13-14 (the final meta agents) and 16-17 (trades under meta play), the ones
the deep run measured and the methodology review checked. Findings 8-12 quote v0.4 and v0.5's summaries, which link
to their own tables.
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
TABLES = ROOT / "results" / "final" / "tables"
DASH = "–"  # the README's range dash


# ---------------------------------------------------------------- formatting, as the README writes numbers
def money(x: float, censored: bool = False) -> str:
    if not np.isfinite(x):
        return "£?"
    return f"£{int(np.floor(x + 0.5)):,}" + ("+" if censored else "")


def times(x: float, d: int = 2) -> str:
    return f"{x:.{d}f}×"


def pct(x: float, d: int = 0) -> str:
    return f"{100 * x:.{d}f}%"


def span(lo: float, hi: float, unit: str = "%") -> str:
    """'10–11%' (or '£70–£171' with unit='£'); a single number when both ends round the same."""
    if unit == "£":
        a, b = money(lo), money(hi)
    else:
        a, b = f"{100 * lo:.0f}", f"{100 * hi:.0f}"
    return (a if a == b else f"{a}{DASH}{b}") + ("%" if unit == "%" else "")


def rounds(x: float) -> str:
    """Medians of rounds: '56.5' for a half, else a whole number."""
    return f"{x:g}" if (2 * x).is_integer() else str(int(np.floor(x + 0.5)))


def zone(r) -> str:
    """The start of a deal-zone cell: '£662–£890', '£746–£1,200+', 'none' or 'not allowed'."""
    if not r.legal:
        return "not allowed"
    if not r.deal_zone_exists:
        return "none"
    return f"{money(r.seller_min_price_win)}{DASH}{money(r.buyer_max_price_win, bool(r.buyer_max_censored))}"


def row(*cells: str | None) -> tuple[str, str]:
    """A README table row whose cells start with these texts (None = any cell): (readable text, regex)."""
    parts = [r"[^|\n]*" if c is None else re.escape(c) + r"[^|\n]*" for c in cells]
    return "| " + " | ".join("…" if c is None else c + "…" for c in cells) + " |", r"\| " + r"\| ".join(parts) + r"\|"


# ---------------------------------------------------------------- claims
Claim = tuple[str, str, str, str | None]  # finding, what, the text expected, a regex for it (None: the text itself)


class Claims:
    """Collects the claims, recomputed from the tables."""

    def __init__(self, tables: Path = TABLES):
        self.tab = tables
        self.items: list[Claim] = []

    def read(self, name: str) -> pd.DataFrame:
        return pd.read_csv(self.tab / name)

    def text(self, finding: str, what: str, text: str) -> None:
        self.items.append((finding, what, text, None))

    def regex(self, finding: str, what: str, row_: tuple[str, str]) -> None:
        self.items.append((finding, what, *row_))

    # 1. landing rates (per 100 turns, rolling for doubles in jail; "short" = leaving jail at once)
    def landings(self) -> None:
        lp = self.read("landing_probabilities.csv").set_index("name")
        per100 = lp.landings_per_turn_long * 100
        props = lp[lp.type.isin(["street", "station", "utility"])]
        top = props.landings_per_turn_long.idxmax()
        low = props.landings_per_turn_long.idxmin()
        self.text("1", "most-landed property", f"{top} is the most-landed property, at **{per100[top]:.2f} landings")
        self.text("1", "least-landed property", f"{low} is the least-landed property ({per100[low]:.2f})")
        self.text("1", "Marlborough and Marylebone", f"Marlborough Street and Marylebone Station "
                  f"({per100['Marlborough Street']:.2f} each)")
        self.text("1", "Vine Street", f"then Vine Street ({per100['Vine Street']:.2f})")
        gain = lp.landings_per_turn_short / lp.landings_per_turn_long - 1
        both = (gain["Marylebone Station"] + gain["Vine Street"]) / 2
        self.text("1", "leaving jail quickly", f"about **{pct(both)} more** traffic")

    # 2. payback with hotels, orange and green
    def payback(self) -> None:
        for n in range(2, 7):
            ge = self.read(f"group_economics_{n}p.csv").set_index(["group", "level"]).payback_rounds
            o, g = ge["orange", "hotel"], ge["green", "hotel"]
            cells = (f"{o:.1f} rounds", f"{g:.1f} rounds") if n == 2 else (f"{o:.1f}", f"{g:.1f}")
            self.regex("2", f"payback, {n} players", row(str(n), *cells))

    # 3 and 4. Vine Street with simple bots
    def vine_simple(self) -> None:
        s = self.read("trade_curve_summary.csv")
        need = s[s.buyer == 0].set_index("n_players")
        for n, r in need.iterrows():
            cells = [str(n), money(r.seller_min_price_win), money(r.buyer_max_price_win, bool(r.buyer_max_censored))]
            if n in (3, 4):
                cells.append(zone(r))
            self.regex("4", f"deal zone, {n} players", row(*cells))
        other = s[s.buyer != 0]
        lo, hi = other.seller_min_price_win.min(), other.seller_min_price_win.max()
        self.text("4", "selling to a bystander", f"(break-even {span(lo, hi, '£')})")
        gap = 1 - need.buyer_max_price_networth / need.buyer_max_price_win
        self.text("3", "net worth gap", f"The gap is **{pct(gap[2])} at 2 players, {pct(gap[3])} at 3 and "
                  f"{pct(gap[4])} at 4**, and at least {span(gap[[5, 6]].min(), gap[[5, 6]].max())} at 5{DASH}6 "
                  "players")

    # 5. strategy tweaks against simple bots
    def strategies(self) -> None:
        sv = self.read("strategy_variants.csv").set_index(["variant", "n_players"]).relative
        self.text("5", "aggressive", f"{times(sv['aggressive', 2])} its fair share at 2 players, rising to "
                  f"**{times(sv['aggressive', 6])}** at 6")
        self.text("5", "never trading, 2 players", f"the *best* tweak at 2 players ({times(sv['no_trade', 2])},")
        self.text("5", "never trading, 6 players", f"among the worst at 6 (**{times(sv['no_trade', 6])}**)")
        self.text("5", "cautious", f"{times(sv['cautious', 2])} at 2 players, falling to "
                  f"{times(sv['cautious', 6])} at 6")
        self.text("5", "random", f"about even at 2 players ({times(sv['random', 2])}) but "
                  f"**{times(sv['random', 6], 3)}** at 6")
        cv = self.read("championship_strategy_variants.csv").set_index(["variant", "n_players"]).relative
        self.text("5", "championship aggressive", f"({times(cv['aggressive', 6])} at 6 players)")
        self.text("5", "championship never trading", f"({times(cv['no_trade', 6])} at 6)")

    # 6. seat order
    def seats(self) -> None:
        def rel(df, n, seat):
            r = df[(df.n_players == n) & (df.seat == seat)].iloc[0]
            return r.win_rate / r.fair_share
        sa = self.read("seat_advantage.csv")
        self.text("6", "first player", f"the first player wins {times(rel(sa, 2, 0))} their fair share at 2 players "
                  f"(not significant), {times(rel(sa, 4, 0))} at 4 and **{times(rel(sa, 6, 0))}** at 6")
        self.text("6", "last player", f"The last player wins only {times(rel(sa, 6, 5))} at 6")
        ca = self.read("championship_seat_advantage.csv")
        self.text("6", "championship first player", f"it's {times(rel(ca, 4, 0))} and {times(rel(ca, 6, 0))} for "
                  "the first player at 4 and 6")

    # 7. game length
    def lengths(self) -> None:
        gl = self.read("game_lengths.csv").groupby("n_players")
        med, turns = gl.rounds.median(), gl.turns.median()
        self.text("7", "median rounds", f"The median game lasts {rounds(med[2])} rounds with 2 players and "
                  f"{rounds(med[6])} with 6")
        self.text("7", "median turns", f"{turns[2]:.0f} turns in all at 2 players and {turns[6]:.0f} at 6")
        hr = self.read("house_rules.csv").set_index(["rules", "n_players"]).median_rounds
        self.text("7", "Free Parking jackpot", f"({rounds(hr['free_parking_jackpot', 2])} rounds instead of "
                  f"{rounds(hr['official', 2])})")
        ca = self.read("championship_seat_advantage.csv").groupby("n_players").median_rounds.first()
        self.text("7", "championship length", f"the median is {rounds(ca[2])} rounds at 2 players and "
                  f"{rounds(ca[6])} at 6")

    # 13. the final agents re-measured
    def validation(self) -> None:
        v = {m: self.read(f"meta_validation_{m}.csv").set_index(["name", "n_players"]) for m in
             ("standard", "championship")}
        cols = ["best challenger vs meta agents", "meta agent vs baseline bots", "baseline bot vs meta agents"]
        for n in range(2, 7):
            cells = [f"{times(v['standard'].relative[c, n])} / {times(v['championship'].relative[c, n])}"
                     for c in cols]
            self.regex("13", f"final agents, {n} players", row(str(n), None, *cells))
        capped = v["championship"].capped_share
        self.text("13", "championship stalls", f"{pct(capped['meta agent at a table of meta agents', 5])} and "
                  f"{pct(capped['meta agent at a table of meta agents', 6])} of the games between meta agents run "
                  "to the time limit")

    # 14. single changes to the final agents
    def ablations(self) -> None:
        a = {m: self.read(f"meta_ablations_{m}.csv").set_index(["name", "n_players"]).relative
             for m in ("standard", "championship")}
        s, c = a["standard"], a["championship"]
        cost = lambda r: 1 - r  # noqa: E731
        nt = s["no trading at all"]
        self.text("14", "no trading", f"an agent that never trades keeps {times(nt[3])} its share at 3 players, "
                  f"{times(nt[4])} at 4, {times(nt[5])} at 5 and {times(nt[6])} at 6. At 2 players it hardly matters "
                  f"({times(nt[2])})")
        cash = cost(s["keep £200 more cash"])
        self.text("14", "cash", f"Keeping £200 more costs {span(cash[[2, 3, 4]].min(), cash[[2, 3, 4]].max())} of "
                  f"wins at 2{DASH}4 players, {pct(cash[5])} at 5 and {pct(cash[6])} at 6")
        hot = cost(s["never build hotels"])
        self.text("14", "hotels", f"Stopping at four houses costs {pct(hot[2])} at 2 players and "
                  f"{span(hot[[4, 5, 6]].min(), hot[[4, 5, 6]].max())} at 4{DASH}6")
        hot_c = cost(c["never build hotels"])
        self.text("14", "hotels, championship", f"Under championship rules it costs "
                  f"{span(hot_c[[3, 4, 5, 6]].min(), hot_c[[3, 4, 5, 6]].max())} at 3{DASH}6 players")
        more = s["bid 25% more"] - 1
        self.text("14", "bidding more", f"Bidding 25% more beats the official agents at 3, 5 and 6 players by "
                  f"{span(more[[3, 5, 6]].min(), more[[3, 5, 6]].max())}")
        more_c = c["bid 25% more"] - 1
        self.text("14", "bidding more, championship", f"the championship agents at 3, 4 and 5 players by "
                  f"{pct(more_c[3])}, {pct(more_c[4])} and {pct(more_c[5])}")
        self.text("14", "bidding less, championship 3p", f"also gains {pct(c['bid 25% less', 3] - 1)} by bidding "
                  "25% less")
        self.text("14", "bidding more, official 2p", f"bidding more is a mistake ({times(s['bid 25% more', 2])})")
        jail = pd.concat([cost(x[k]) for x in (s, c) for k in ("always leave jail", "always stay in jail")])
        self.text("14", "jail", f"Always leaving or always staying in jail costs {pct(jail.max())} at most")
        self.text("14", "jail, official 2p", f"staying is {pct(s['always stay in jail', 2] - 1)} better for the "
                  "official 2-player agent")
        flip = pd.concat([x["flip 'take a Chance'"] for x in (s, c)])
        self.text("14", "Chance card", f"changes results by {pct((flip - 1).abs().max(), 1)} at most")
        acc = c["accept trades"]
        self.text("14", "embargo", f"cost them {pct(1 - acc[5])} and {pct(1 - acc[6])} of their credit "
                  f"({times(acc[5])} and {times(acc[6])})")

    # 16. Vine Street under meta play
    def vine_meta(self) -> None:
        simple = self.read("trade_curve_summary.csv")
        simple = simple[simple.buyer == 0].set_index("n_players")
        m = {k: self.read(f"meta_trade_summary_{k}.csv").set_index("n_players") for k in ("standard", "championship")}
        for n in range(2, 7):
            self.regex("16", f"Vine Street, {n} players",
                       row(str(n), zone(simple.loc[n]), zone(m["standard"].loc[n]), zone(m["championship"].loc[n])))
        s2, m2 = simple.loc[2], m["standard"].loc[2]
        self.text("16", "2 players, buyer if free", f"from {pct(m2.p_win_base_buyer)} to "
                  f"{pct(m2.p_win_buyer_if_free)} against the 2-player agent, and from {pct(s2.p_win_base_buyer)} to "
                  f"{pct(s2.p_win_buyer_if_free)} with simple bots")
        big = [4, 5, 6]
        meta_lo = m["standard"].seller_min_price_win[big]
        simple_lo = simple.seller_min_price_win[big]
        self.text("16", "sellers ask more", f"(break-even {span(meta_lo.min(), meta_lo.max(), '£')}, against "
                  f"{span(simple_lo.min(), simple_lo.max(), '£')})")
        ch = m["championship"].seller_min_price_win[[3, 4]]
        self.text("16", "championship break-even", f"at 3{DASH}4 players ({span(ch.min(), ch.max(), '£')})")

    # 17. every property, 4 players
    LABELS = {1: "Old Kent Road (brown)", 6: "The Angel Islington (light blue)", 11: "Pall Mall (pink)",
              19: "Vine Street (orange)", 21: "Strand (red)", 26: "Leicester Square (yellow)",
              31: "Regent Street (green)", 37: "Park Lane (dark blue)", 5: "King's Cross (stations)"}
    COLOURS = ("light_blue", "pink", "orange", "red", "yellow", "green", "dark_blue")

    def properties(self) -> None:
        p = {b: self.read(f"property_trade_summary_{b}.csv") for b in ("simple", "meta", "championship")}
        p4 = {b: d[d.n_players == 4].set_index("square") for b, d in p.items()}
        for sq, label in self.LABELS.items():
            self.regex("17", label, row(label, *(zone(p4[b].loc[sq]) for b in ("simple", "meta", "championship"))))
        from monopoly_meta import load_edition
        ed = load_edition()
        colour = [sq for sq in p4["simple"].index
                  if ed.group_of[sq] >= 0 and ed.group_names[ed.group_of[sq]] in self.COLOURS]
        s, m = p4["simple"].loc[colour], p4["meta"].loc[colour]
        ask = m.seller_min_price_win - s.seller_min_price_win
        pay = (m.buyer_max_price_win - s.buyer_max_price_win)[~m.buyer_max_censored.astype(bool)]
        self.text("17", "sellers ask more", f"should ask {span(ask.min(), ask.max(), '£')} more than")
        self.text("17", "buyers pay more", f"buyers will pay {span(pay.min(), pay.max(), '£')} more")
        self.brown()
        self.first_crossing(p)

    def brown(self) -> None:
        """The non-monotone brown curves: the buyer's win share given the piece free, at the dip and at the peak."""
        def buyer(bots):
            c = self.read(f"property_trade_curve_{bots}.csv")
            c = c[(c.n_players == 4) & (c.square == 1) & (c.player == 0)].sort_values("price")
            return c.set_index("price").p_win_trade
        m, s = buyer("meta"), buyer("simple")
        self.text("17", "brown, meta", f"the buyer wins {pct(m.iloc[0])} of games when given Old Kent Road free but "
                  f"{pct(m.max())} after paying {money(m.idxmax())}")
        peak = s.idxmax()
        dip = s[s.index < peak].iloc[1:].idxmin()
        self.text("17", "brown, simple", f"with simple bots it is {pct(s.iloc[0])} free, {pct(s[dip])} at "
                  f"{money(dip)} and {pct(s[peak])} at {money(peak)}")

    def first_crossing(self, summaries: dict) -> None:
        """How many deals the old summary (each curve's first zero crossing) missed, and how many forbidden
        sales it listed."""
        missed = listed = 0
        for b, summ in summaries.items():
            curve = self.read(f"property_trade_curve_{b}.csv")
            for (n, sq), c in curve.groupby(["n_players", "square"]):
                r = summ[(summ.n_players == n) & (summ.square == sq)].iloc[0]
                old = first_crossing_deal(c, seller=1, buyer=0)
                missed += bool(r.legal and r.deal_zone_exists and not old)
                listed += bool(not r.legal and old)
        self.text("17", "deals the first crossing missed", f"That missed {missed} deals")
        self.text("17", "forbidden sales listed", f"They also listed {words(listed)} 2-player championship sales")

    def all(self) -> list[Claim]:
        for step in (self.landings, self.payback, self.vine_simple, self.strategies, self.seats, self.lengths,
                     self.validation, self.ablations, self.vine_meta, self.properties):
            step()
        return self.items


def words(k: int) -> str:
    small = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
    return small[k] if k < len(small) else str(k)


def first_crossing_deal(curve: pd.DataFrame, seller: int, buyer: int) -> bool:
    """The summary used before the methodology review: the seller's first zero crossing, the buyer's first (or the
    highest price, if the buyer still gains there), and a deal if the second is above the first."""
    def first(player):
        c = curve[curve.player == player].sort_values("price")
        x, y = c.price.to_numpy(float), c.d_win.to_numpy(float)
        for i in range(len(x) - 1):
            if y[i] == 0:
                return x[i]
            if np.sign(y[i]) != np.sign(y[i + 1]):
                return x[i] + (x[i + 1] - x[i]) * (0 - y[i]) / (y[i + 1] - y[i])
        return x[-1] if player == buyer and y[-1] > 0 else None
    lo, hi = first(seller), first(buyer)
    return lo is not None and hi is not None and hi > lo


def flatten(text: str) -> str:
    """Line breaks and runs of spaces become one space, as a reader sees wrapped prose."""
    return re.sub(r"\s+", " ", text)


def check(readme: str, items: list[Claim]) -> list[Claim]:
    """The claims not found in the README."""
    flat = flatten(readme)
    return [c for c in items if not (re.search(c[3], flat) if c[3] else flatten(c[2]) in flat)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quiet", action="store_true", help="print only the claims missing from the README")
    ap.add_argument("--tables", type=Path, default=TABLES)
    ap.add_argument("--report", type=Path, help="also write the output to this file")
    ap.add_argument("--no-fail", action="store_true", help="exit 0 even if claims are missing (after a re-run, "
                    "before the README is updated)")
    args = ap.parse_args(argv)
    try:
        items = Claims(args.tables).all()
    except Exception as e:  # e.g. a table a partial re-run hasn't written yet
        msg = f"Could not recompute the README claims: {type(e).__name__}: {e}"
        print(msg)
        if args.report:
            (args.report if args.report.is_absolute() else ROOT / args.report).write_text(msg + "\n")
        return 0 if args.no_fail else 1
    missing = check(README.read_text(), items)
    lines = []
    for item in items:
        bad = any(item is m for m in missing)
        if bad or not args.quiet:
            lines.append(f"{'MISSING' if bad else 'ok':7} finding {item[0]:>2}, {item[1]}: {item[2]}")
    lines.append(f"{len(items) - len(missing)} of {len(items)} README claims match the tables")
    print("\n".join(lines))
    if args.report:
        path = args.report if args.report.is_absolute() else ROOT / args.report
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")
    return 1 if missing and not args.no_fail else 0


if __name__ == "__main__":
    sys.exit(main())
