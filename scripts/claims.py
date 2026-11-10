"""Check the numbers on the front page (README.md), in the full findings (FINDINGS.md) and on the rules page
(RULES.md) against the result tables they come from.

    python scripts/claims.py              # every claim, with OK or MISSING; exits 1 if any is missing
    python scripts/claims.py --quiet      # only the missing ones

Each claim recomputes a number, or a row of a table, from the result tables and writes it the way the page does.
It passes when that text is on its page (line breaks and repeated spaces ignored): the front page's plain-English
summary (claims "L1"-"L8"), the rules page (claims "R") or the full findings (the rest). So when a re-run moves a
number, the claim fails until the prose is updated, and an edit that mistypes a number fails too.

Covered: the front page; the rules page's measured effects; findings 1-7 (simple bots), 8-12 (v0.4's searches and
v0.5's hardening, from results/v04 and results/v05), 13-14 (the final meta agents), 16-17 (trades under meta play)
and 18 (rule sensitivity). Everything else comes from results/final/tables, the deep run and its re-runs.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"      # the front page: the plain-English summary
FINDINGS = ROOT / "FINDINGS.md"  # the full findings
RULES_PAGE = ROOT / "RULES.md"   # the rules, and what each simplification was measured to change
TABLES = ROOT / "results" / "final" / "tables"
V03 = ROOT / "results" / "tables"                             # the first meta agents
V04 = ROOT / "results" / "v04" / "tables" / "unconventional"  # the searches against them
V05 = ROOT / "results" / "v05" / "tables" / "hardened"        # the hardening
DASH = "–"  # the pages' range dash


# ---------------------------------------------------------------- formatting, as the pages write numbers
def money(x: float, censored: bool = False) -> str:
    if not np.isfinite(x):
        return "£?"
    return f"£{int(np.floor(x + 0.5)):,}" + ("+" if censored else "")


def times(x: float, d: int = 2) -> str:
    return f"{x:.{d}f}×"


def pct(x: float, d: int = 0) -> str:
    return f"{100 * x:.{d}f}%"


def chance(x: float) -> str:
    """A win chance as finding 4's table writes it: a whole percent from 10%, one decimal below, two below 1%."""
    p = 100 * x
    return f"{p:.0f}%" if p >= 9.95 else f"{p:.1f}%" if p >= 0.995 else f"{p:.2f}%"


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


def listing(items, last: str = "and") -> str:
    """'a', 'a and b', 'a, b and c'."""
    items = [str(x) for x in items]
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {last} {items[-1]}" if items else "none"


def sizes(ns) -> str:
    """Table sizes: '4–6' when three or more are consecutive, else '3 and 5'."""
    ns = sorted(int(n) for n in ns)
    if len(ns) > 2 and ns == list(range(ns[0], ns[-1] + 1)):
        return f"{ns[0]}{DASH}{ns[-1]}"
    return listing(ns)


def more_than(share: float) -> str:
    """'more than 99.9%' for a share above 99.9% but below all of them; 'all' for exactly 1."""
    if not np.isfinite(share):
        return "more than ?%"
    if share >= 1:
        return "all"
    tenths = int(np.ceil(round(share * 1000, 6))) - 1  # the largest tenth of a percent strictly below the share
    return f"more than {tenths / 10:.1f}%"


# What rollout.later_deals() leaves out when the buyer never got the square. NaN prints as 'nan', so a claim that
# needs one of these fails on its own instead of stopping every claim with a KeyError.
NO_LATER_DEALS = {"games": 0, "traded_later": 0.0, "to_buyer": 0.0, "median_wait": np.nan, "median_price": np.nan,
                  "price_mode": np.nan, "price_mode_share": np.nan, "swap_share": np.nan}


def row(*cells: str | None) -> tuple[str, str]:
    """A table row whose cells start with these texts (None = any cell): (readable text, regex)."""
    parts = [r"[^|\n]*" if c is None else re.escape(c) + r"[^|\n]*" for c in cells]
    return "| " + " | ".join("…" if c is None else c + "…" for c in cells) + " |", r"\| " + r"\| ".join(parts) + r"\|"


# ---------------------------------------------------------------- claims
Claim = tuple[str, str, str, str | None]  # finding, what, the text expected, a regex for it (None: the text itself)
FRACTION = {2: "half", 3: "third", 4: "quarter", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth",
            10: "tenth"}


class Claims:
    """Collects the claims, recomputed from the tables."""

    def __init__(self, tables: Path = TABLES):
        self.tab = tables
        self.items: list[Claim] = []
        self._cache: dict[str, object] = {}

    def read(self, name: str) -> pd.DataFrame:
        if name not in self._cache:
            self._cache[name] = pd.read_csv(self.tab / name)
        return self._cache[name].copy()

    def json(self, name: str) -> dict:
        if name not in self._cache:
            self._cache[name] = json.loads((self.tab / name).read_text())
        return self._cache[name]

    def frame(self, path: Path) -> pd.DataFrame:
        """A table from an earlier version's results (results/tables, results/v04, results/v05)."""
        if str(path) not in self._cache:
            self._cache[str(path)] = pd.read_csv(path)
        return self._cache[str(path)].copy()

    def reserves(self, mode: str) -> dict[int, tuple[float, float]]:
        """Each final agent's cash held back when buying and when building."""
        agents = self.json(f"meta_agents_{mode}.json")
        return {int(n): (g["reserve"], g["build_reserve"]) for n, g in agents.items()}

    def later(self, name: str) -> dict[str, dict]:
        """later_deals_<name>.json with every key in every entry (NaN where the buyer never got the square). A table
        size the file leaves out counts as no deals."""
        raw = self.json(f"later_deals_{name}.json")
        keys = set(raw) | {f"{n}p" for n in range(2, 7)} | {f"{n}p_buyer0" for n in range(2, 7)}
        return {k: {**NO_LATER_DEALS, **raw.get(k, {})} for k in keys}

    def text(self, finding: str, what: str, text: str) -> None:
        self.items.append((finding, what, text, None))

    def regex(self, finding: str, what: str, row_: tuple[str, str]) -> None:
        self.items.append((finding, what, *row_))

    # the front page: its seven findings in plain words, and how it says they were checked
    def landing(self) -> None:
        lp = self.read("landing_probabilities.csv").set_index("name")
        props = lp[lp.type.isin(["street", "station", "utility"])].landings_per_turn_long * 100
        top, low = props.idxmax(), props.idxmin()
        self.text("L1", "most and least visited", f"**{top} is the most-visited property, {low} the least** "
                  f"({props[top]:.2f} and {props[low]:.2f} landings per 100 turns)")
        ge = self.read("group_economics_4p.csv")
        streets = ge[~ge.group.isin(["stations", "utilities"])]
        hotel = streets[streets.level == "hotel"].set_index("group").payback_rounds
        best = hotel.idxmin()
        self.text("L2", "best investment", f"**The {best.replace('_', ' ')} set is the best investment.** With hotels "
                  f"it pays for itself fastest: in about {hotel[best]:.0f} rounds of play at 4 players")
        top_level = streets.dropna(subset=["marginal_roi_per_round"]).groupby("group").apply(
            lambda d: d.loc[d.marginal_roi_per_round.idxmax(), "level"], include_groups=False)
        others = sorted(g for g, lv in top_level.items() if lv != "3 houses")
        if others == ["brown"]:
            self.text("L2", "third house", "On every set but the browns, the third house earns the most rent for its "
                      "price")
        else:
            self.text("L2", "third house", f"the third house is best on every set except {', '.join(others)}")
        s = self.read("trade_curve_summary.csv")
        r = s[(s.buyer == 0) & (s.n_players == 4)].iloc[0]
        ratio = r.buyer_max_price_win / 200  # Vine Street's printed price
        size = (f"almost {words(int(np.ceil(ratio)))}" if np.ceil(ratio) - ratio < 0.5 else
                f"over {words(int(ratio))}")
        self.text("L3", "the last piece of a set", f"wins {pct(r.p_win_base_buyer)} of the time without the third, "
                  f"and {pct(r.p_win_buyer_if_free)} if given it. Compared with never getting it, it's worth up to "
                  f"{money(r.buyer_max_price_win, bool(r.buyer_max_censored))} to them: {size} times the £200")
        later = self.later("simple")["4p_buyer0"]
        live = self.read("trade_curve_summary_live.csv")
        live = live[(live.buyer == 0) & (live.n_players == 4)].iloc[0]
        soon = "within a couple of turns" if later["median_wait"] <= 2 else f"within {later['median_wait']:.0f} turns"
        going = (f"usually sell it to them {soon} for {money(later['median_price'])}, so paying much more than that "
                 "going rate is a loss")
        if (later["to_buyer"] < 0.5 or not np.isfinite(later["median_price"])
                or live.buyer_max_price_win > later["median_price"] * 1.1):
            going = "the going rate doesn't hold"  # the text would no longer be true, so the claim fails
        self.text("L3", "the going rate", going)
        a = self.read("meta_ablations_standard.csv").set_index(["name", "n_players"]).relative
        nt = a["no trading at all"]
        frac = FRACTION.get(int(np.floor(1 / nt[4] + 0.5)), f"{nt[4]:.2f}x")
        heads_up = ("With 2 players, trading barely matters" if abs(nt[2] - 1) < 0.05 else
                    f"With 2 players, refusing trades costs {pct(1 - nt[2])}")
        self.text("L4", "trading", f"a {frac} as often at 4 players. {heads_up}")
        sa = self.read("seat_advantage.csv")
        six = sa[sa.n_players == 6].set_index("seat")
        first, last = six.win_rate[0] / six.fair_share[0], six.win_rate[5] / six.fair_share[5]
        self.text("L5", "seat order", f"the first player wins {pct(first - 1)} more often than an equal share, and the "
                  f"last player {pct(1 - last)} less")
        cash = 1 - a["keep £200 more cash"]
        self.text("L6", "cash", f"keeping £200 more in hand costs {span(cash.min(), cash.max())} of their wins")
        keep = {n: buying for n, (buying, _) in self.reserves("standard").items()}
        big, small = [keep[n] for n in (4, 5, 6)], [keep[n] for n in (2, 3)]
        bare = 1 - a["keep no cash buffer"]
        self.text("L6", "the cushion", f"With 4 to 6 players they keep almost nothing ({span(min(big), max(big), '£')} "
                  f"after buying); with 2 or 3 they keep {span(min(small), max(small), '£')}, and giving that cushion "
                  f"up costs them {span(bare[[2, 3]].min(), bare[[2, 3]].max())}")
        v = pd.concat([self.read(f"meta_validation_{m}.csv") for m in ("standard", "championship")])
        best_c = v[v.name == "best challenger vs meta agents"].relative
        self.text("L7", "no strategy unbeatable", f"score {pct(best_c.min() - 1)} to {pct(best_c.max() - 1)} more "
                  "against them")
        mv = self.read("markov_validation.csv")
        off = (mv.simulated / mv.markov - 1).abs().groupby(mv.card_draw).max()
        within = "0.5%" if off["random"] < 0.005 else pct(off["random"], 1)
        self.text("L8", "the exact odds against simulation", f"to within {within} when cards are drawn at random")
        self.text("L8", "the real decks", f"by up to {pct(off['deck'], 1)}")
        self.text("0", "the exact odds against simulation", f"matches to within **{within}**")  # "How it works"
        self.text("0", "the real decks", f"by up to {pct(off['deck'], 1)} while someone is holding")

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
        self.text("1", "paying to leave jail", f"{top} rises to {100 * lp.landings_per_turn_short[top]:.2f}, the "
                  f"typical property gets about **{pct(gain[props.index].median())} more** traffic")
        self.text("1", "leaving jail quickly", f"a roll away from Jail, about **{pct(both)} more**")

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
            cells = [str(n), money(r.seller_min_price_win), money(r.buyer_max_price_win, bool(r.buyer_max_censored)),
                     zone(r), f"{chance(r.p_win_base_seller)} / {chance(r.p_win_base_buyer)}",
                     pct(r.p_win_buyer_if_free)]
            self.regex("4", f"deal zone, {n} players", row(*cells))
        poor = need.p_win_base_buyer[need.buyer_max_censored.astype(bool)]  # where the buyer gains at every price
        self.text("4", "what paying everything beats", f"the buyer wins about {span(poor.min(), poor.max())} of games "
                  "without the deed")
        other = s[s.buyer != 0]
        lo, hi = other.seller_min_price_win.min(), other.seller_min_price_win.max()
        self.text("4", "selling to a bystander", f"(break-even {span(lo, hi, '£')})")
        for k in (5, 10, 20):  # net worth after k of each player's own turns
            col = f"buyer_max_price_networth_own{k}"
            if col not in need:  # tables from before the own-turn fix (d_networth_r<k>: k rounds of the start)
                col = f"buyer_max_price_networth_r{k}"
            gap = 1 - need[col] / need.buyer_max_price_win
            cells = [("≥" if need.buyer_max_censored[n] else "") + pct(gap[n]) for n in range(2, 7)]
            self.regex("3", f"net worth gap after {k} own turns", row(f"{k} own turns", *cells))
        half = (need.deal_low_ci_high - need.deal_low_ci_low) / 2, (need.deal_high_ci_high - need.deal_high_ci_low) / 2
        ends = pd.concat([h[[3, 4]] for h in half])
        self.text("4", "bootstrap intervals", f"95% intervals of ±{span(ends.min(), ends.max(), '£')} for the 3- and "
                  f"4-player prices, and ±{money(half[0][5])} and ±{money(half[0][6])} for the 5- and 6-player "
                  "break-evens")
        self.vine_live()
        self.positions()

    def vine_live(self) -> None:
        """Finding 4's sale against carrying on as normal (later trades allowed), and what the keep arm did."""
        later = self.later("simple")
        need = {n: later[f"{n}p_buyer0"] for n in range(2, 7)}
        games = sum(d["games"] for d in need.values())
        per = {d["games"] for d in need.values()}
        per = f"{next(iter(per)):,} per table size" if len(per) == 1 else "different numbers per table size"
        missed = int(round(sum(d["games"] * (1 - d["to_buyer"]) for d in need.values())))
        waits = np.array([d["median_wait"] for d in need.values()], float)
        prices = {d["median_price"] for d in need.values()} | {d["price_mode"] for d in need.values()}
        share = np.min([d["price_mode_share"] for d in need.values()])
        price = next(iter(prices)) if len(prices) == 1 else np.nan  # several prices: '£?', and the claim fails
        from monopoly_meta import load_edition
        from monopoly_meta.policies import make_bot
        face = load_edition().price[19]  # Vine Street
        usual = "their usual offer" if price == face * make_bot("balanced").offer_mult else "not their usual offer"
        multiple = "twice face value" if price == 2 * face else f"{price / face:g}× face value"
        lost = "all but one" if missed == 1 else "every one" if missed == 0 else f"all but {missed}"
        self.text("4", "later trades", f"in {lost} of the {games:,} games played on ({per}), after a median of "
                  f"{waits.min():.0f}{DASH}{waits.max():.0f} player-turns, and for {money(price)} ({usual}, "
                  f"{multiple}) in {more_than(share)} of them")
        live = self.read("trade_curve_summary_live.csv")
        z = live[live.buyer == 0].set_index("n_players")
        deal = z[z.deal_zone_exists.astype(bool)]
        none = [n for n in z.index if not z.deal_zone_exists[n]]
        if len(deal) and none:
            top = deal.loc[deal.buyer_max_price_win.idxmax()]
            sliver = (f"{money(deal.seller_min_price_win.min())}{DASH}"
                      f"{money(top.buyer_max_price_win, bool(top.buyer_max_censored))}")
            where = (f"none at {listing(none, 'or')} players, and at {sizes(deal.index)} players only a sliver just "
                     f"above that price ({sliver})")
        else:
            where = "a deal at every table size" if len(deal) else "no deal at any table size"
        self.text("4", "live deal zone", where)
        share = deal.deal_share_of_resamples
        unsure = (deal.evidence == "between sampled prices only").all()
        self.text("4", "live deal zone, evidence", ("The sliver lies between two prices played" if unsure else
                  "The sliver holds at a price played") + (f", shows up in {span(share.min(), share.max())} of "
                                                           "bootstrap resamples" if len(deal) else ""))
        by = live[live.buyer == 2].set_index("n_players")
        by = by[by.legal.astype(bool) & by.deal_zone_exists.astype(bool)]
        clear = by[by.evidence == "confident at a sampled price"]
        rest = by[by.evidence == "at a sampled price"]
        if len(clear) + len(rest) != len(by):  # a zone that is only between prices: the text would be wrong
            self.text("4", "live bystander", "a bystander deal that lies between the prices played")
        self.text("4", "live bystander, clear", f"is a clear deal at {sizes(clear.index)} players "
                  f"({listing(zone(r) for _, r in clear.iterrows())})" if len(clear) else "a clear deal nowhere")
        self.text("4", "live bystander, within the noise", f"At {listing(rest.index)} players both sides gain at a "
                  f"price played ({listing(zone(r) for _, r in rest.iterrows())}), but not by more than their margins "
                  "of error" if len(rest) else "clear at every table size")

    def positions(self) -> None:
        """The set-completing sale in 100 positions from real games (scripts/17_game_positions.py)."""
        g = self.read("game_positions.csv")
        mean = g.groupby(["baseline", "multiple"])[["buyer_change", "seller_change"]].mean() * 100
        kept, live = mean.loc["kept for good"], mean.loc["later trades allowed"]
        both = g.assign(both=(g.buyer_change > 0) & (g.seller_change > 0)).groupby(["baseline", "multiple"]).both.sum()
        loses = g.assign(l=g.buyer_change < 0).groupby(["baseline", "multiple"]).l.sum()
        n = g.position.nunique()
        if "screened" in g:  # saved by scripts/17_game_positions.py since the third review
            screened = int(g.screened.iloc[0])
        else:  # older tables: rebuilt from the script's first seed
            import importlib.util
            spec = importlib.util.spec_from_file_location("game_positions", ROOT / "scripts" / "17_game_positions.py")
            script = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(script)
            screened = int(g.game_seed.max() - script.SCREEN_SEED + 1)
        self.text("4", "positions screened", f"out of {screened:,} screened games between simple bots")
        cash = g.drop_duplicates("position").buyer_cash
        self.text("4", "positions, buyers' cash", f"the median buyer in these positions holds {money(cash.median())}")
        gains = "gains" if (kept.buyer_change[[2, 3, 4]] > 0).all() else "doesn't always gain"
        self.text("4", "positions, kept for good", f"the buyer {gains} on average at 2, 3 and 4 times face value "
                  f"({kept.buyer_change[2]:+.1f}, {kept.buyer_change[3]:+.1f} and {kept.buyer_change[4]:+.1f} points "
                  f"of win chance), and both sides gain in {both['kept for good', 2]}, {both['kept for good', 3]} and "
                  f"{both['kept for good', 4]} of the {n} positions")
        first = g[(g.baseline == "later trades allowed") & (g.multiple == 2)]
        twice = "twice" if first.keep_later_multiple.median() == 2 else "other than twice"
        # "changes nothing": the 95% interval of the mean across positions straddles zero
        half = 1.96 * 100 * first.buyer_change.std() / np.sqrt(len(first))
        nothing = ("changes nothing on average" if abs(live.buyer_change[2]) <= half else
                   "changes the buyer's chances on average")
        k3, k4 = loses["later trades allowed", 3], loses["later trades allowed", 4]
        lose = ("loses in every one of the" if k3 == k4 == n else
                f"loses in {k3} and {k4} of the" if k3 != k4 else f"loses in {k3} of the")
        if not (live.buyer_change[3] < 0 and live.buyer_change[4] < 0):
            lose = "doesn't lose on average, though " + lose
        worse = f"({live.buyer_change[3]:.1f} and {live.buyer_change[4]:.1f} points)".replace("-", "−")
        later = pct(first.keep_later_to_buyer.mean())
        self.text("4", "positions, carrying on", f"the buyer got it later in {later} of "
                  f"games, for a median of {twice} face value, so a sale at that price {nothing} "
                  f"({live.buyer_change[2]:+.1f} points), and at 3 or 4 times face value the buyer {lose} {n} "
                  f"positions {worse}")

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
        both = pd.concat([self.read(f) for f in ("strategy_variants.csv", "championship_strategy_variants.csv")])
        moved = (both.game_relative - both.relative).abs().max()
        c2 = self.read("championship_strategy_variants.csv")
        c2 = c2[c2.n_players == 2].capped_share
        self.text("5", "time-limit games", f"Under championship rules {span(c2.min(), c2.max())} of 2-player games hit "
                  "the time limit")
        self.text("5", "outright vs time-limit", "moves no number in this finding by more than "
                  f"{np.ceil(moved * 100) / 100:.2f}")
        if "outright_share" in c2.index.names or "outright_share" in self.read("championship_strategy_variants.csv"):
            ch = self.read("championship_strategy_variants.csv")
            two = ch[ch.n_players == 2].assign(all_games=lambda d: d.outright_share * 2)
            drop = (two.relative - two.all_games)
            worst = two.loc[drop.idxmax()]
            self.text("5", "outright over all games", f"the 2-player championship rates fall by up to "
                      f"{np.ceil(drop.max() * 100) / 100:.2f}: {worst.variant} play, which stalls most "
                      f"({pct(worst.capped_share)} of its games), goes from {times(worst.relative)} to "
                      f"{times(worst.all_games)}")

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

    # 8-12. the searches against the first agents (v0.4) and the hardening (v0.5), from their own results folders
    def searches(self) -> None:
        s = self.frame(V04 / "summary.csv").set_index(["mode", "n_players"])
        best = s.best_find
        self.text("8", "the best finds", f"the best finds score {best.min():.1f} to {best.max():.1f} times what the "
                  "agent scores")
        for n in range(2, 7):
            self.regex("8", f"best find, {n} players", row(str(n), times(best["standard", n]),
                                                           times(best["championship", n])))
        arms = {}
        for (mode, n) in s.index:
            if f"v04/{mode}_{n}p" not in self._cache:
                self._cache[f"v04/{mode}_{n}p"] = json.loads((V04 / f"{mode}_{n}p.json").read_text())
            arms[mode, n] = self._cache[f"v04/{mode}_{n}p"]["tactics_arm"]
        bigger = [k for k, a in arms.items() if a["tvc_ci_low"] > 1]
        smaller = [k for k, a in arms.items() if a["tvc_ci_high"] < 1]
        ratio = s.tactics_vs_control
        self.text("8", "with and without the new moves", f"a bigger exploit in {words(len(bigger))} of the "
                  f"{words(len(arms))} settings (most at {ratio.idxmax()[1]} players under "
                  f"{'championship' if ratio.idxmax()[0] == 'championship' else 'official'} rules: "
                  f"{ratio.max():.2f} times the search without them), about the same in "
                  f"{words(len(arms) - len(bigger) - len(smaller))}, and a smaller one at "
                  f"{listing(n for _, n in smaller)} players under "
                  f"{'official' if {m for m, _ in smaller} == {'standard'} else 'some'} rules "
                  f"({listing(sorted({f'{ratio[k]:.2f}' for k in smaller}))} times)")
        tried = s.strategies_tried
        few = tried["championship"][[5, 6]]
        rest = tried.drop([("championship", 5), ("championship", 6)])
        self.text("8", "search budgets", f"MAP-Elites tried {rest.min():,} to {rest.max():,} strategies per setting, "
                  f"but only {few[5]:,} and {few[6]:,} at 5 and 6 players under championship rules")
        old = self.frame(V03 / "meta_validation_standard.csv")
        old = old[(old.name == "meta agent at a table of meta agents") & (old.n_players == 2)].iloc[0]
        self.text("8", "the first 2-player agent", f"ran {pct(old.capped_share)} of its own games to the time limit, a "
                  f"loss for both players, so it scored {old.relative:.2f} of a fair share")

        ab = pd.concat([self.frame(V05 / f"ablations_{m}.csv") for m in ("standard", "championship")])
        bare = ab[(ab.n_players == 4) & (ab.tactics == "no new moves") & ab.name.str.startswith("v0.4 find")].ratio
        self.text("9", "finds without the new moves", f"with every new move off ({bare.min():.2f}{DASH}"
                  f"{times(bare.max())})")

        def joins(mode):  # one meta agent at a table of each of the three best finds
            league = pd.read_csv(V04 / f"league_{mode}_5p.csv", index_col=0)
            cells = league.loc["meta agent", [c for c in league.columns if c.startswith("find")]]
            return f"{cells.min():.1f}{DASH}{cells.max():.1f} times"
        self.text("10", "a meta agent among finds", f"scores {joins('standard')} what the find scores in that seat "
                  f"under official rules, and {joins('championship')} under championship rules")

        h = self.frame(V05 / "summary.csv").set_index(["mode", "n_players"])

        def cell(mode, n):
            r = h.loc[(mode, n)]
            after = f"**{times(r.worst_v05)}**" if r.kept == "v0.5" else times(r.worst_v05)
            return [f"{times(r.worst_v03)} → {after}", r.kept]
        for n in range(2, 7):
            self.regex("11", f"hardening, {n} players", row(str(n), *cell("standard", n), *cell("championship", n)))
        kept = h[h.kept == "v0.5"]
        self.text("11", "agents improved", f"improved {words(len(kept))} of the {words(len(h))} agents")
        two = h.xs(2, level="n_players")
        self.text("11", "new against old, 2 players", f"scores {times(two.new_in_old['standard'])} (official) and "
                  f"{times(two.new_in_old['championship'])} (championship); one v0.3 agent at a table of v0.5 agents "
                  f"scores only {times(two.old_in_new['standard'])} and {times(two.old_in_new['championship'])}")
        self.text("11", "still beatable", f"the {words(len(kept))} new agents' worst measured exploits are still "
                  f"{kept.worst_v05.min():.2f}{DASH}{times(kept.worst_v05.max())}")
        worse = h[h.kept == "v0.3"]
        six, one = worse.loc[("standard", 6)], worse[worse.rounds == 1]
        self.text("12", "6 players, official", f"the rounds made things much worse ({times(six.worst_v05)})")
        where = [f"{n} players under {'official' if m == 'standard' else 'championship'} rules" for m, n in one.index]
        self.text("12", "one round only", f"At {listing(where)} only one round ran, and the full searches then beat "
                  f"its agent by more than the old one ({times(one.worst_v05.iloc[0])} against "
                  f"{times(one.worst_v03.iloc[0])})" if len(one) == 1 else "every setting ran several rounds")
        four = h.loc[("standard", 4)]
        self.text("13", "official 4 players, which challenger", f"({times(four.known_worst_after)} on 10,000 games in "
                  f"v0.5's checks), not the fresh searches' best ({times(max(four.arm_after, four.find_after))})")

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
        sc = self.read("scoring_sensitivity.csv").groupby("n_players").first()
        self.text("13", "decided by assumed points", f"On {int(sc.games[5]):,} fresh games, "
                  f"{pct(sc.decided_by_assumed_rows[5])} and {pct(sc.decided_by_assumed_rows[6])} end there with five "
                  "or six players still in")

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
        nt_c = c["no trading at all"]
        trade = [n for n in range(2, 7) if abs(nt_c[n] - 1) > 1e-9]  # where the championship agents trade at all
        self.text("14", "no trading, championship", f"only the {listing(trade)}-player agents trade with each other "
                  f"({listing(times(nt_c[n]) for n in trade)} without it)" if trade else "no championship agent trades")
        cash = cost(s["keep £200 more cash"])
        self.text("14", "cash", f"Keeping £200 more costs {span(cash[[2, 3, 4]].min(), cash[[2, 3, 4]].max())} of "
                  f"wins at 2{DASH}4 players, {pct(cash[5])} at 5 and {pct(cash[6])} at 6")
        keep = {m: self.reserves(m) for m in a}
        bare, big = cost(s["keep no cash buffer"]), [keep["standard"][n][0] for n in (4, 5, 6)]
        each = (f"each loses {pct(bare[2])} of its wins" if pct(bare[2]) == pct(bare[3]) else
                f"they lose {pct(bare[2])} and {pct(bare[3])} of their wins")
        little = "under 1%" if bare[[4, 5, 6]].max() < 0.01 else f"up to {pct(bare[[4, 5, 6]].max())}"
        self.text("14", "the cushion", f"the 2- and 3-player agents hold back {money(keep['standard'][2][0])} and "
                  f"{money(keep['standard'][3][0])} when buying, and without that cushion {each}, while the 4{DASH}6 "
                  f"player agents hold back {span(min(big), max(big), '£')} and lose {little} without it")
        bare_c = cost(c["keep no cash buffer"])
        self.text("14", "the cushion, championship", f"the {bare_c.idxmax()}-player agent's cushion matters most "
                  f"({pct(bare_c.max())} of its credit)")
        for mode, agent in (("standard", "v0.5 | v0.3 | v0.5 | v0.5 | v0.3"),
                            ("championship", "v0.5 | v0.5 | v0.5 | v0.3 | v0.3")):
            cells = [f"{money(keep[mode][n][0])} / {money(keep[mode][n][1])}" for n in range(2, 7)]
            self.text("14", f"cash held back, {mode}", f"| Agent | {agent} | | Cash held back when buying† / when "
                      f"building | {' | '.join(cells)} |")
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
        sc = self.read("scoring_sensitivity.csv").set_index(["n_players", "schedule"]).ratio
        other = lambda n: sc[n].drop("extrapolated")  # noqa: E731
        holds = all(other(n).max() < sc[n, "extrapolated"] for n in (5, 6))
        self.text("14", "embargo, other schedules", ("accepting trades costs more, not less" if holds else
                  "accepting trades doesn't always cost more") + f" ({times(other(5).min())}"
                  f"{DASH}{times(other(5).max())} at 5 players and {times(other(6).min())}{DASH}"
                  f"{times(other(6).max())} at 6, against {times(sc[5, 'extrapolated'])} and "
                  f"{times(sc[6, 'extrapolated'])} under the engine's points".replace(f"×{DASH}", DASH))

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
        half = pd.concat([(d.deal_low_ci_high - d.deal_low_ci_low)[ns] / 2 for d, ns in
                          ((m["standard"], [3, 4, 5]), (m["championship"], [3, 4]))])
        six = (m["standard"].deal_low_ci_high - m["standard"].deal_low_ci_low)[6] / 2
        self.text("16", "bootstrap intervals", f"break-evens are ±{span(half.min(), half.max(), '£')} at 3{DASH}5 "
                  f"players and ±{money(six)} at 6")
        c = self.read("meta_trade_curve_standard.csv")
        c = c[(c.n_players == 2) & (c.player == 0)]
        near = c[(c.price >= m2.deal_low_ci_low) & (c.price <= m2.deal_high_ci_high + 50)]
        self.text("16", "fewer stalled games", f"rarer ({pct(c.capped_share_base.iloc[0], 2)} of games to about "
                  f"{pct(near.capped_share_trade.mean(), 1)})")
        self.text("16", "2-player band", f"The band shows up in {pct(m2.deal_share_of_resamples, 1)} of bootstrap "
                  f"resamples, though where it sits is less sure ({money(m2.deal_low_ci_low)}{DASH}"
                  f"{money(m2.deal_high_ci_high)})")
        pc = self.read("price_checks.csv")
        vine = pc[(pc.bots == "meta") & (pc.n_players == 2) & (pc.square == 19)]
        shown = "neither price clearly benefits both sides" if (vine.verdict != "both gain (95%)").all() else \
            "some price benefits both sides"
        self.text("16", "2-player band replayed", "replayed at " + " and ".join(money(x) for x in vine.price)
                  + f" on {int(vine.rollouts.iloc[0]):,} fresh games each, {shown}")
        later = self.later("standard")
        big = [3, 4, 5, 6]
        offers = [money(later[f"{n}p"]["median_price"]) for n in big]
        waits = np.array([later[f"{n}p"]["median_wait"] for n in big], float)
        self.text("16", "later deals, meta", f"at their own offer: {offers[0]} at 3 players, {offers[1]} at 4, "
                  f"{offers[2]} at 5 and {offers[3]} at 6, within a median of {waits.min():.0f}{DASH}"
                  f"{waits.max():.0f} player-turns")
        two = later["2p"]
        sw = two["swap_share"]
        swaps = ("always in a swap" if sw == 1 else "never in a swap" if sw == 0 else
                 f"in a swap {pct(sw)} of the time" if np.isfinite(sw) else "with no deals to the buyer")
        self.text("16", "later deals, 2 players", f"At 2 players it changes hands later in {pct(two['to_buyer'])} of "
                  f"games, {swaps}, after a median of {two['median_wait']:.0f} player-turns")
        live = self.read("meta_trade_summary_standard_live.csv").set_index("n_players")
        none = [n for n in live.index if live.evidence[n] == "no whole-pound price"]
        self.text("16", "live zones, meta", f"({zone(live.loc[4])} at 4 players, {zone(live.loc[6])} at 6), and at "
                  + " and ".join(map(str, none)) + " players to no whole pound at all")
        slivers = live.loc[[4, 6]]
        share = slivers.deal_share_of_resamples
        self.text("16", "live zones, evidence", ("each lies between two prices played" if
                  (slivers.evidence == "between sampled prices only").all() else "one holds at a price played")
                  + f", shows up in {span(share.min(), share.max())} of bootstrap resamples")
        agents = self.json("meta_agents_standard.json")
        own = all(abs(later[f"{n}p"]["median_price"] - 200 * agents[str(n)]["offer_mult"]) < 1 for n in big)
        self.text("16", "the going rate is a setting", "Each price is that agent's offer setting times the £200 face "
                  "value" if own else "The prices are not the agents' offer settings")
        lc = self.later("championship")["4p"]
        clive = self.read("meta_trade_summary_championship_live.csv").set_index("n_players")
        how = "between prices played" if clive.evidence[4] == "between sampled prices only" else "at a price played"
        self.text("16", "championship, carrying on", f"the 4-player agents trade it later for "
                  f"{money(lc['median_price'])} and the zone shrinks to {zone(clive.loc[4])} ({how}, in "
                  f"{pct(clive.deal_share_of_resamples[4])} of resamples")
        tr = self.read("scoring_trades.csv")
        loss = -tr.seller_points
        self.text("16", "championship scoring", f"the seller loses {loss.min():.1f}{DASH}{loss.max():.1f} points per "
                  "game, even at " + money(tr.price.max()) if (tr.seller_points < 0).all() else "the seller gains")

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
        pc = self.read("price_checks.csv")
        deals = pc.groupby(["bots", "n_players", "square"])
        good = sum((g.verdict == "both gain (95%)").any() for _, g in deals)
        unpaid = [g for _, g in deals if g.price.isna().all()]
        names = " and ".join(sorted({g.name.iloc[0] for g in unpaid}))
        up, down, without = [], [], []  # how far inside each quoted zone its confident range starts and ends
        for b, kind in (("simple", "simple-bot"), ("meta", "official"), ("championship", "championship")):
            for sq, label in self.LABELS.items():
                r = p4[b].loc[sq]
                if not (r.legal and r.deal_zone_exists):
                    continue
                if not isinstance(r.confident_deal_ranges, str):
                    without.append(f"{label.split(' (')[0]}'s {kind} zone")
                    continue
                ends = [float(x) for piece in r.confident_deal_ranges.split(";") for x in piece.split("-")]
                up.append(ends[0] - r.seller_min_price_win)
                if not r.buyer_max_censored:
                    down.append(r.buyer_max_price_win - ends[-1])
        self.text("17", "confident ranges", f"starts {span(min(up), max(up), '£')} higher and ends "
                  f"{span(min(down), max(down), '£')} lower than the zones in this table, and {listing(without)} has "
                  "no such range")
        self.text("17", "narrow zones", f"There are {deals.ngroups} such deals across all the tables")
        self.text("17", "narrow zones replayed", f"{good} hold up")
        self.text("17", "narrow zones not established", f"{deals.ngroups - good - len(unpaid)} aren't established at "
                  f"any price tried, and {len(unpaid)} ({names}")
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

    # 18. the housing findings under the official building rules
    SENSITIVITY = [("standard", 4, "strongest known challenger", "Official, 4 players", "strongest known challenger"),
                   ("standard", 4, "hard three-house cap", "Official, 4 players", "hard three-house cap"),
                   ("standard", 4, "housing lock on (14)", "Official, 4 players", "housing lock added"),
                   ("standard", 2, "strongest known challenger", "Official, 2 players", "strongest known challenger"),
                   ("standard", 2, "housing lock off", "Official, 2 players", "housing lock removed"),
                   ("championship", 4, "strongest known challenger", "Championship, 4 players",
                    "strongest known challenger"),
                   ("championship", 4, "housing lock off", "Championship, 4 players", "housing lock removed"),
                   ("championship", 4, "simple bot", "Championship, 4 players", "simple bot")]

    def sensitivity(self) -> None:
        c = self.read("sensitivity/candidates.csv")
        variants = ["engine rules", "build any time", "house auctions", "mortgaged stations count",
                    "mortgage choice on transfer"]
        for mode, n, cand, setting, label in self.SENSITIVITY:
            r = c[(c["mode"] == mode) & (c.n_players == n) & (c.candidate == cand)].set_index("variant").ratio
            self.regex("18", f"{setting}, {label}", row(setting, label, *(times(r[v]) for v in variants)))
        rest = c[c.candidate != "final agent"]
        change = (rest.vs_engine_rules - 1).abs()
        engine = rest[rest.variant == "engine rules"].set_index(["mode", "n_players", "candidate"])
        flips = 0
        for r in rest[rest.variant != "engine rules"].itertuples():
            e = engine.loc[(r.mode, r.n_players, r.candidate)]
            flips += (e.ci_low > 1 and r.ci_high < 1) or (e.ci_high < 1 and r.ci_low > 1)
        self.text("18", "no verdict reverses", "No verdict reverses." if flips == 0 else
                  f"{flips} verdicts reverse")  # the second text isn't in the README, so the claim fails
        h = self.read("sensitivity/housing.csv").set_index(["mode", "n_players", "variant"])
        ch, st = h.loc[("championship", 4, "house auctions")], h.loc[("standard", 4, "engine rules")]
        auctions = change[rest.variant == "house auctions"].max()
        self.text("18", "house auctions", f"houses than the bank has in {pct(ch.games_with_contested_houses)} of "
                  f"championship 4-player games ({ch.houses_auctioned_per_game:.1f} houses auctioned per game) and "
                  f"{pct(st.games_with_contested_houses)} of official 4-player games, yet no candidate's edge moves by "
                  f"more than {pct(np.ceil(auctions * 100) / 100)}")
        two = h.loc[("standard", 2, "engine rules")]
        self.text("R", "house auctions", f"houses are contested in {pct(st.games_with_contested_houses)} of official "
                  f"4-player games, {pct(two.games_with_contested_houses)} of 2-player games and "
                  f"{pct(ch.games_with_contested_houses)} of championship 4-player games "
                  f"({ch.houses_auctioned_per_game:.1f} houses auctioned per game)")
        self.text("R", "house auctions, edges", "house auctions change no edge by more than "
                  f"{pct(np.ceil(auctions * 100) / 100)}")
        any_time = change[(rest.variant == "build any time") & (rest.candidate != "simple bot")].max()
        self.text("18", "building at any time", f"Building at any time moves those edges by "
                  f"{pct(np.ceil(any_time * 100) / 100)} at most")
        simple = c[(c["mode"] == "championship") & (c.n_players == 4) & (c.candidate == "simple bot")]
        simple = simple.set_index("variant").ratio
        self.text("18", "simple bot, building at any time", f"it rises from {times(simple['engine rules'])} to "
                  f"{times(simple['build any time'])}")
        self.text("R", "building at any time", f"Moves the tested agents' edges by "
                  f"{pct(np.ceil(any_time * 100) / 100)} at most; helps the simple bot more "
                  f"({times(simple['engine rules'])} to {times(simple['build any time'])} against the championship "
                  "4-player agents)")
        stations = change[rest.variant == "mortgaged stations count"].max()
        self.text("18", "mortgaged stations", f"Counting mortgaged stations moves nothing by more than "
                  f"{pct(np.ceil(stations * 100) / 100)}")
        self.text("R", "mortgaged stations", f"Moves no tested result by more than "
                  f"{pct(np.ceil(stations * 100) / 100)}.")
        self.text("R", "mortgaged stations, in the rules list", "The choice moves no tested result by more than "
                  f"{pct(np.ceil(stations * 100) / 100)}")
        lock = c[(c["mode"] == "standard") & (c.n_players == 4) & (c.candidate == "housing lock on (14)")]
        lock = lock.set_index("variant").ratio
        conf = self.read("sensitivity/confirm.csv").iloc[0]
        self.text("18", "the housing lock at 4 players", f"wins it {pct(conf.ratio - 1)} more on {int(conf.games):,} "
                  f"fresh games ({conf.ratio:.3f}× [{conf.ci_low:.3f}, {conf.ci_high:.3f}]; "
                  f"{pct(lock['engine rules'] - 1)} on the comparison's own games), and "
                  f"{pct(lock['build any time'] - 1)} more when building at any time")
        self.text("18", "comparisons", f"With {int(((rest.variant != 'engine rules')).sum())} such comparisons")
        tests = rest[rest.variant != "engine rules"]
        adj = tests[(tests.vs_engine_adj_low > 1) | (tests.vs_engine_adj_high < 1)]
        under_any_time = adj.variant.isin(["build any time", "any time + auctions"])
        lifts = adj[adj.variant == "mortgage choice on transfer"]
        others = adj[~under_any_time & (adj.variant != "mortgage choice on transfer")]
        which = (f" (the {lifts.candidate.iloc[0]}'s {pct(1 - lifts.vs_engine_rules.iloc[0])})" if len(lifts) == 1
                 else "")
        where = (f"{int(under_any_time.sum())} of them with building at any time and {words(len(lifts))} with lifting "
                 f"a received mortgage at once{which}" if others.empty else "some with other rules")
        self.text("18", "Bonferroni", f"After a Bonferroni adjustment {len(adj)} still show a change, {where}")
        # "build any time" and "any time + auctions" are nearly the same test, so one result can be counted twice
        twice = adj[under_any_time].groupby(["mode", "n_players", "candidate"]).size()
        self.text("18", "Bonferroni, repeats", f"The {int(under_any_time.sum())} are really {len(twice)} results: "
                  f"{int((twice > 1).sum())} of them appear twice")
        readings = tests.reading.value_counts()
        self.text("18", "equivalence", f"Read against a tolerance of ±3%, "
                  f"{readings.get('equivalent', 0)} of the {len(tests)} are equivalent (no change that large is "
                  f"plausible) and {readings.get('inconclusive', 0)} are inconclusive")
        changed = (tests.vs_engine_adj_low > 1) | (tests.vs_engine_adj_high < 1)

        def equivalent(tol):  # as scripts/15_rule_sensitivity.py reads a comparison, at another tolerance
            return int((~changed & (tests.vs_engine_adj_low >= 1 - tol) & (tests.vs_engine_adj_high <= 1 + tol)).sum())
        first = int((tests.variant != "mortgage choice on transfer").sum())  # the comparisons of the first two runs
        self.text("18", "the tolerance", f"chosen after the first {first} comparisons had been seen, so it isn't a "
                  f"threshold fixed in advance; at ±2% and ±4% the equivalent count is {equivalent(0.02)} and "
                  f"{equivalent(0.04)}" if equivalent(0.03) == readings.get("equivalent", 0) else
                  "the tolerance is not ±3%")
        lift = rest[rest.variant == "mortgage choice on transfer"]
        agents = (lift[lift.candidate != "simple bot"].vs_engine_rules - 1).abs().max()
        sb = c[(c["mode"] == "standard") & (c.n_players == 4) & (c.candidate == "simple bot")].set_index("variant")
        self.text("18", "mortgage choice", f"Lifting a received mortgage at once moves the agents' edges by "
                  f"{pct(np.ceil(agents * 100) / 100)} at most,** and lowers the simple bot's by "
                  f"{pct(1 - sb.vs_engine_rules['mortgage choice on transfer'])} against the official 4-player agents "
                  f"({times(sb.ratio['engine rules'])} to {times(sb.ratio['mortgage choice on transfer'])})")
        hv = h.reset_index()
        four = hv[(hv.n_players == 4) & (hv.variant == "engine rules")].mortgaged_received_per_game
        choice = hv[(hv.n_players == 4) & (hv.variant == "mortgage choice on transfer")]
        lifted = choice.lifted_at_once_per_game / choice.mortgaged_received_per_game
        self.text("18", "mortgage choice, how often", f"{four.min():.0f}{DASH}{four.max():.0f} mortgaged properties "
                  f"change hands in a 4-player game between the final agents")
        self.text("18", "mortgage choice, lifted", f"the agents lift {pct(lifted.min())}{DASH}{pct(lifted.max())} of "
                  "them at once".replace(f"%{DASH}", DASH))
        self.text("R", "mortgage choice", f"{four.min():.0f}{DASH}{four.max():.0f} times in a 4-player game between "
                  "the final meta agents, about nine in ten from bankrupt players, and they lift "
                  f"{pct(lifted.min())}{DASH}{pct(lifted.max())} at once. Moves the tested agents' edges by "
                  f"{pct(np.ceil(agents * 100) / 100)} at most; lowers the simple bot's by "
                  f"{pct(1 - sb.vs_engine_rules['mortgage choice on transfer'])}".replace(f"%{DASH}", DASH))
        hot = h.games_with_contested_hotels
        worst = hot.idxmax()
        self.text("18", "hotels", f"wanted more hotels than the bank had in at most {pct(hot.max(), 1)} of games "
                  f"({worst[0].replace('standard', 'official')} rules, {worst[1]} players)")
        self.text("R", "hotels", f"in at most {pct(hot.max(), 1)} of games "
                  f"({worst[0].replace('standard', 'official')} rules, {worst[1]} players)")
        prev = self.read("sensitivity/candidates_previous.csv")
        keys = ["mode", "n_players", "variant", "candidate"]
        again = c.merge(prev[keys + ["ratio"]], on=keys, suffixes=("", "_previous"))
        again = again[again.candidate != "final agent"]
        same = int(((again.ratio - again.ratio_previous).abs() < 1e-12).sum())
        self.text("18", "the third re-run", f"reproduced {'all ' + str(same) if same == len(again) else str(same)} of "
                  "the earlier results exactly")
        self.lock_factorial()
        before = self.read("sensitivity/candidates_pre_auction_fix.csv")  # the first review's run, kept as it was
        both = rest.merge(before[keys + ["ratio"]], on=keys, suffixes=("", "_before"))
        auction = both.variant.isin(["house auctions", "any time + auctions"])
        shift = (both.ratio - both.ratio_before)[auction].abs().max()
        exact = int(((both.ratio - both.ratio_before).abs() < 1e-12)[~auction].sum())
        self.text("18", "the auction fix", f"the house-auction results moved by {np.ceil(shift * 1000) / 1000:.3f} at "
                  f"most, and the other {exact} results reproduced exactly")
        seats = self.read("sensitivity/seats.csv")
        base = seats[seats.variant == "engine rules"].set_index("n_players").first_relative
        moved = (seats.first_relative - seats.n_players.map(base)).abs().max()
        self.text("18", "seat order", f"the first player's edge with simple bots moves by about {moved:.2f} at most")

    LOCK_ROWS = [("final agents", "the confirmation's games", "Final agents (the games above)"),
                 ("final agents", "fresh games", "Final agents (fresh games)"),
                 ("simple bots", "fresh games", "Simple bots"),
                 ("equal mixture per seat", "fresh games", "An equal mixture per seat"),
                 ("known challengers", "fresh games", "Known challengers")]

    def lock_factorial(self) -> None:
        """The housing lock taken apart (scripts/15_rule_sensitivity.py, lock_factorial.csv)."""
        f = self.read("sensitivity/lock_factorial.csv").set_index(["opponents", "schedule", "arm"])
        arms = ["defer hotels only", "protect buildings only", "both (the housing lock)"]
        for opp, sched, label in self.LOCK_ROWS:
            games = int(f.loc[(opp, sched, arms[0]), "games"])
            self.regex("18", f"lock factorial, {label}", row(label, f"{games:,}",
                                                             *(times(f.loc[(opp, sched, a), "ratio"]) for a in arms)))
        arm = lambda a: f.xs(a, level="arm")  # noqa: E731
        protect, defer, both = arm("protect buildings only"), arm("defer hotels only"), arm(arms[2])
        gain = span(protect.ratio.min() - 1, protect.ratio.max() - 1)
        everywhere = "against every population" if (protect.ci_low > 1).all() else "against some populations"
        nowhere = "helps nowhere" if not (defer.ci_low > 1).any() else "helps somewhere"
        self.text("18", "protecting buildings", f"Protecting buildings gains {gain} {everywhere} "
                  f"({protect.gain_pp.min():.1f}{DASH}{protect.gain_pp.max():.1f} points of win rate), while holding "
                  f"back hotels alone {nowhere} ({times(defer.ratio.min())}{DASH}{times(defer.ratio.max())})"
                  .replace(f"×{DASH}", DASH))
        contrast = arm("protect only ÷ both")
        clear = contrast[contrast.gain_low_pp > 0]
        tie = contrast[(contrast.gain_low_pp <= 0) & (contrast.gain_high_pp >= 0)]
        ahead = contrast[contrast.gain_high_pp < 0]  # both arms together beat protecting alone
        tied = " and against the " + " and ".join(o for o, _ in tie.index) + " they tie" if len(tie) else ""
        won = " and against the " + " and ".join(o for o, _ in ahead.index) + " they win more" if len(ahead) else ""
        by = (f"by {clear.gain_pp.min():.1f}{DASH}{clear.gain_pp.max():.1f} points," if len(clear) else
              "nowhere clearly,")
        self.text("18", "both vs protecting", f"together they win slightly less than protecting alone ({by}{tied}"
                  f"{won})")
        half = pd.concat([(d.ci_high - d.ci_low) / 2 for d in (protect, defer, both)])
        self.text("18", "lock factorial intervals", f"95% intervals ±{np.floor(half.min() * 1000) / 1000:.3f}{DASH}"
                  f"{np.ceil(half.max() * 1000) / 1000:.3f}")

    # the rules page: how often games reach a turn limit
    def limits(self) -> None:
        sa = self.read("seat_advantage.csv").groupby("n_players")
        capped = (sa.limit_wins.sum() / sa.games.first() * 100_000).round().astype(int)
        self.text("R", "the 4,000-turn cap, simple bots", f"({capped.max()} in 100,000 at most, at any table size)")
        sv = self.read("strategy_variants.csv")
        worst = sv.loc[sv.capped_share.idxmax()]
        name = {"hard_bargain": "hard-bargainer"}.get(worst.variant, worst.variant)
        self.text("R", "the 4,000-turn cap, rare traders", f"up to {pct(worst.capped_share, 1)} for the {name} at "
                  f"{worst.n_players} players")
        p90 = self.read("house_rules.csv").query("rules == 'official'").set_index("n_players").p90_rounds
        whole = lambda x: int(np.floor(x + 0.5))  # noqa: E731
        self.text("R", "90th-percentile length", f"({whole(p90[2])} rounds at 2 players, {whole(p90[4])} at 4, "
                  f"{whole(p90[6])} at 6)")

        def stalled(table):  # the share of games between copies of one meta agent that reach the limit
            return table[table.name == "meta agent at a table of meta agents"].set_index("n_players").capped_share
        official = stalled(self.read("meta_validation_standard.csv"))
        self.text("R", "stalls, final agents", f"{100 * official.min():.1f}{DASH}{100 * official.max():.1f}% of games "
                  "between the final agents stall, at any table size")
        old = stalled(self.frame(V03 / "meta_validation_standard.csv"))
        self.text("R", "stalls, 2 players", f"(v0.3) still ran {pct(old[2])} of its games to the limit")
        self.text("R", "stalls, 2 players, hardened", f"(v0.5) stalls in {pct(official[2], 1)}")
        champ = stalled(self.read("meta_validation_championship.csv"))
        self.text("R", "championship games at the limit", f"{pct(champ[5])} and {pct(champ[6])} of games between the "
                  "5- and 6-player agents end at the limit")

    def all(self) -> list[Claim]:
        for step in (self.landing, self.landings, self.payback, self.vine_simple, self.strategies, self.seats,
                     self.lengths, self.searches, self.validation, self.ablations, self.vine_meta, self.properties,
                     self.sensitivity, self.limits):
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


def check(text: str, items: list[Claim]) -> list[Claim]:
    """The claims not found in this text."""
    flat = flatten(text)
    return [c for c in items if not (re.search(c[3], flat) if c[3] else flatten(c[2]) in flat)]


def on_front_page(item: Claim) -> bool:
    return item[0].startswith("L")


def on_rules_page(item: Claim) -> bool:
    return item[0] == "R"


def where(item: Claim) -> str:
    """The page a claim is checked on, as the report names it."""
    if on_front_page(item):
        return "front page"
    if on_rules_page(item):
        return "rules page"
    return "how it works" if item[0] == "0" else f"finding {item[0]:>2}"


def check_pages(items: list[Claim], front: str | None = None, findings: str | None = None,
                rules: str | None = None) -> list[Claim]:
    """The claims missing from their page: the front page's ("L…") from README.md, the rules page's ("R") from
    RULES.md, the rest from FINDINGS.md."""
    front = README.read_text() if front is None else front
    findings = FINDINGS.read_text() if findings is None else findings
    rules = RULES_PAGE.read_text() if rules is None else rules
    return (check(front, [c for c in items if on_front_page(c)])
            + check(rules, [c for c in items if on_rules_page(c)])
            + check(findings, [c for c in items if not on_front_page(c) and not on_rules_page(c)]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quiet", action="store_true", help="print only the claims missing from their page")
    ap.add_argument("--tables", type=Path, default=TABLES)
    ap.add_argument("--report", type=Path, help="also write the output to this file")
    ap.add_argument("--no-fail", action="store_true", help="exit 0 even if claims are missing (after a re-run, "
                    "before the pages are updated)")
    args = ap.parse_args(argv)
    try:
        items = Claims(args.tables).all()
    except Exception as e:  # e.g. a table a partial re-run hasn't written yet
        msg = f"Could not recompute the claims: {type(e).__name__}: {e}"
        print(msg)
        if args.report:
            (args.report if args.report.is_absolute() else ROOT / args.report).write_text(msg + "\n")
        return 0 if args.no_fail else 1
    missing = check_pages(items)
    lines = []
    for item in items:
        bad = any(item is m for m in missing)
        if bad or not args.quiet:
            lines.append(f"{'MISSING' if bad else 'ok':7} {where(item)}, {item[1]}: {item[2]}")
    lines.append(f"{len(items) - len(missing)} of {len(items)} claims match the tables "
                 f"({sum(map(on_front_page, items))} on the front page, {sum(map(on_rules_page, items))} on the rules "
                 "page, the rest in the full findings)")
    print("\n".join(lines))
    if args.report:
        path = args.report if args.report.is_absolute() else ROOT / args.report
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")
    return 1 if missing and not args.no_fail else 0


if __name__ == "__main__":
    sys.exit(main())
