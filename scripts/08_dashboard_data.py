"""Collect the published results into tidy CSVs for the interactive dashboard.

Outputs (results/dashboard/*.csv), one file per dashboard dataset:
  squares, set_economics, strategies, seats, game_length, trade_curves, deal_zones,
  meta_agents, meta_checks, meta_ablations, hardening

Tables the pipeline hasn't written yet (e.g. championship mode while it runs) are skipped.
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from meta_common import ablations  # noqa: E402

from monopoly_meta import load_edition  # noqa: E402

from run_config import DASHBOARD as OUT, TABLES as TAB  # noqa: E402
OUT.mkdir(parents=True, exist_ok=True)
RULES = {"standard": "Official rules", "championship": "Championship rules"}
VARIANT = {
    "aggressive": "Aggressive (no cash buffer, bids 120%)", "cautious": "Cautious (£400 buffer, bids 80%)",
    "three_house": "Three houses first (then hotels)", "hoarder": "Never builds hotels",
    "jail_short": "Always leaves jail",
    "jail_long": "Always stays in jail", "take_chance": "Takes the Chance card",
    "no_trade": "Never proposes trades", "hard_bargain": "Hard bargainer (asks 3×, offers 1.5×)",
    "random": "Random decisions",
}
PARAM = {  # genome key: (label, unit)
    "reserve": ("Cash kept after buying", "£"), "build_reserve": ("Cash kept after building", "£"),
    "bid_frac": ("Auction limit", "× face value"), "set_bonus": ("Bid premium to complete a set", "×"),
    "block_bonus": ("Bid premium to block a set", "×"), "offer_mult": ("Cash offered for a set piece", "× face value"),
    "ask_mult": ("Cash asked for a set piece", "× face value"), "build_cap": ("Builds evenly up to", ""),
    "max_level": ("Highest building", ""), "jail": ("In jail", ""),
    "take_chance": ("Takes a Chance instead of the £10 fine", ""),
    "trades": ("Proposes trades", ""), "accept_trades": ("Accepts trades", ""),
}
LEVEL = {3: "3 houses", 4: "4 houses", 5: "a hotel"}
JAIL = {"short": "leaves at once", "long": "stays and rolls for doubles", "adaptive": "leaves early, stays late"}
RENAMED = {"three-house cap": "three houses first"}  # build_cap 3 is a priority, not a cap (hotels follow)
ABLATION = {
    "meta agent (placebo)": "Unchanged meta agent", "no trading at all": "No trading at all",
    "accept trades": "Accepts trades", "always leave jail": "Always leave jail at once",
    "always stay in jail": "Always stay in jail", "three-house cap": "Three houses first (then hotels)",
    "three houses first": "Three houses first (then hotels)",
    "never build hotels": "Never build hotels", "flip 'take a Chance'": "Flip the take-a-Chance choice",
    "keep £200 more cash": "Keep £200 more cash", "keep no cash buffer": "Keep no cash buffer",
    "bid 25% more": "Bid 25% more at auctions", "bid 25% less": "Bid 25% less at auctions",
    "simple baseline bot": "Play as the simple bot",
}
GROUP_NAME = {"brown": "brown", "light_blue": "light blue", "pink": "pink", "orange": "orange", "red": "red",
              "yellow": "yellow", "green": "green", "dark_blue": "dark blue", "stations": "stations",
              "utilities": "utilities"}


def save(df: pd.DataFrame, name: str) -> None:
    """Write a dashboard table, floats rounded to 4 decimals so the files stay readable."""
    df.round(4).to_csv(OUT / name, index=False)


def read(name: str, **assign) -> pd.DataFrame | None:
    """A results table, or None while the pipeline hasn't written it yet."""
    path = TAB / name
    if not path.exists():
        print(f"  (missing {name}: skipped)")
        return None
    return pd.read_csv(path).assign(**assign)


def squares():
    lp = pd.read_csv(TAB / "landing_probabilities.csv")
    pe = pd.read_csv(TAB / "property_economics.csv")
    df = lp[["square", "name", "type", "group"]].copy()
    df["group"] = df["group"].fillna("")
    df["landings_per_100_turns"] = 100 * lp.landings_per_turn_long
    df["landings_per_100_turns_short_jail"] = 100 * lp.landings_per_turn_short
    df["landing_share_pct"] = lp.landing_share_pct_long
    keep = ["square", "price", "rent_site", "rent_set", "rent_1 house", "rent_2 houses", "rent_3 houses",
            "rent_4 houses", "rent_hotel"]
    df = df.merge(pe[keep].rename(columns=lambda c: c.replace(" ", "_")), on="square", how="left")
    save(df, "squares.csv")


def set_economics():
    df = pd.concat([pd.read_csv(TAB / f"group_economics_{n}p.csv").assign(n_players=n) for n in range(2, 7)])
    df["marginal_return_pct"] = 100 * df.marginal_roi_per_round
    save(df.drop(columns=["marginal_roi_per_round"]), "set_economics.csv")


def strategies():
    a = read("strategy_variants.csv", rules=RULES["standard"])
    b = read("championship_strategy_variants.csv", rules=RULES["championship"])
    df = pd.concat([a, b])
    # outright wins among finished games (relative), and among all games, with the share stopped by the limit
    extra = [c for c in ("outright_share", "limit_share") if c in df]
    df = df[["rules", "n_players", "variant", "relative", "rel_low", "rel_high", "capped_share"] + extra]
    if "outright_share" in df:
        df["outright_all_relative"] = df.outright_share * df.n_players
    df["strategy"] = df.variant.map(VARIANT)
    save(df.drop(columns="variant"), "strategies.csv")


def seats():
    a = read("seat_advantage.csv", rules=RULES["standard"])
    b = read("championship_seat_advantage.csv", rules=RULES["championship"])
    df = pd.concat([a, b])
    df["seat"] = df.seat + 1
    df["relative"] = df.win_rate / df.fair_share
    cols = ["rules", "n_players", "seat", "win_rate", "ci_low", "ci_high", "fair_share", "relative"]
    cols += [c for c in ("outright_share", "limit_share") if c in df]
    save(df[cols], "seats.csv")


def game_length():
    hr = pd.read_csv(TAB / "house_rules.csv")
    names = {"official": "Official rules", "free_parking_jackpot": "Free Parking jackpot",
             "no_auctions": "No auctions"}
    hr["rules"] = hr.rules.map(names)
    cols = ["rules", "n_players", "median_rounds", "p90_rounds", "capped_share"]
    parts = [hr[cols]]
    cs = read("championship_seat_advantage.csv", rules=RULES["championship"])
    if cs is not None:
        parts.append(cs.groupby("n_players").first().reset_index()[cols])
    save(pd.concat(parts), "game_length.csv")


def trades():
    """The Vine Street curves and deal zones, against both baselines: the deed kept for good (its own value to each
    side) and later trades allowed (the decision to accept an offer today, when the bots would otherwise trade on).
    Championship rollouts score finishing points ÷ 28, shown as expected points, not win chance."""
    curves, zones = [], []
    files = {"Simple bots": ("trade_curve_orange_squeeze{}.csv", "trade_curve_summary{}.csv",
                             "later_deals_simple.json"),
             "Meta agents, official rules": ("meta_trade_curve_standard{}.csv", "meta_trade_summary_standard{}.csv",
                                             "later_deals_standard.json"),
             "Meta agents, championship rules": ("meta_trade_curve_championship{}.csv",
                                                 "meta_trade_summary_championship{}.csv",
                                                 "later_deals_championship.json")}
    for label, (curve_f, summary_f, later_f) in files.items():
        unit = "points" if "championship" in label else "pp"
        later = json.loads((TAB / later_f).read_text()) if (TAB / later_f).exists() else {}
        for baseline, suffix in (("Kept for good", ""), ("Later trades allowed", "_live")):
            c, s = read(curve_f.format(suffix)), read(summary_f.format(suffix))
            if c is None or s is None:
                continue
            c, s = (d if "buyer" in d else d.assign(buyer=0) for d in (c, s))
            for (n, buyer), d in c.groupby(["n_players", "buyer"]):
                kind = "Completes the buyer's set" if buyer == 0 else "Buyer doesn't need it"
                for r in roles(d, ["n_players"], buyer=buyer, scale=SCALE[unit]):
                    curves.append({"opponents": label, "deal": kind, "baseline": baseline, "unit": unit, **r})
            for _, r in s.iterrows():
                kind = "Completes the buyer's set" if r.buyer == 0 else "Buyer doesn't need it"
                # what the keep arm did when trading carried on: did the buyer get the deed later anyway, and for what
                k = later.get(f"{r.n_players}p_buyer{r.buyer}", later.get(f"{r.n_players}p", {})) if suffix else {}
                zones.append({"opponents": label, "deal": kind, "baseline": baseline, "unit": unit,
                              "n_players": r.n_players,
                              "seller_break_even": r.seller_min_price_win, "buyer_maximum": r.buyer_max_price_win,
                              "buyer_maximum_is_all_cash": bool(r.buyer_max_censored),
                              "deal_zone": bool(r.deal_zone_exists), "deal_ranges": r.get("deal_ranges", ""),
                              "evidence": r.get("evidence", ""), "allowed": bool(r.get("legal", True)),
                              "note": zone_note(r),
                              "seller_break_even_networth": r.seller_min_price_networth,
                              "buyer_maximum_networth": r.buyer_max_price_networth,
                              "buyer_win_pct_without": 100 * r.p_win_base_buyer,
                              "buyer_win_pct_if_free": 100 * r.p_win_buyer_if_free,
                              "later_to_buyer_pct": 100 * k["to_buyer"] if "to_buyer" in k else None,
                              "later_median_price": k.get("median_price")})
    save(pd.DataFrame(curves), "trade_curves.csv")
    z = pd.DataFrame(zones)
    z.insert(0, "key", z.opponents + " | " + z.deal + " | " + z.baseline + " | " + z.n_players.astype(str)
             + " players")
    save(z, "deal_zones.csv")


def zone_note(r) -> str:
    """Why a deal zone needs care: the rules forbid the trade, or a curve that is not monotone."""
    if not bool(r.get("legal", True)):
        return "not allowed: no trades heads-up under championship rules (a hypothetical intervention)"
    if not bool(r.get("monotone", True)):
        return "not monotone: a bot here does better after paying more, a flaw of its policy rather than value"
    return ""


def roles(c: pd.DataFrame, keys: list[str], buyer: int = 0, seller: int = 1, scale: float = 100) -> list[dict]:
    """Per-player curve rows -> one row per role (buyer, seller, everyone else) and price. `scale` turns a change in
    credit into the unit shown: 100 for percentage points of win chance, 28 for championship points. Everyone
    else comes from the curve's own row for the bystanders summed game by game (player -1), whose standard error is
    paired; older curves without it sum the players and their errors as if independent."""
    out = []
    for vals, g in c.groupby(keys + ["price"]):
        base = dict(zip(keys + ["price"], vals))
        combined = g[g.player == -1]
        others = combined if not combined.empty else g[~g.player.isin([seller, buyer, -1])]
        for role, sub in [("Buyer", g[g.player == buyer]), ("Seller", g[g.player == seller]),
                          ("Everyone else", others)]:
            if not sub.empty:
                row = {**base, "role": role, "change": scale * sub.d_win.sum(),
                       "change_se": scale * (sub.d_win_se ** 2).sum() ** 0.5, "d_networth": sub.d_networth.sum()}
                if "d_outright" in sub and sub.d_outright.notna().all():
                    row["outright_pp"] = 100 * sub.d_outright.sum()
                out.append(row)
    return out


def crossing_se(curve: pd.DataFrame, player: int, at: float | None = None) -> float | None:
    """Rough standard error, in pounds, of where a player's change in win chance crosses zero: the noise in the
    change (its standard error) divided by how steeply it falls with price there. Cheap sets have flat curves, so
    their break-even prices are much less certain. `at` picks the crossing nearest the price shown (a curve that
    isn't monotone crosses more than once, and the shown end may not be the first crossing)."""
    c = curve[curve.player == player].sort_values("price")
    x, y, se = c.price.to_numpy(float), c.d_win.to_numpy(float), c.d_win_se.to_numpy(float)
    found = []
    for i in range(len(x) - 1):
        if y[i] == 0 or (y[i] > 0) != (y[i + 1] > 0):
            slope = abs(y[i + 1] - y[i]) / (x[i + 1] - x[i])
            where = x[i] if y[i] == 0 else x[i] + (x[i + 1] - x[i]) * y[i] / (y[i] - y[i + 1])
            found.append((where, float(min(600.0, (se[i] + se[i + 1]) / 2 / slope)) if slope > 0 else 600.0))
    if not found:
        return None
    if at is None or pd.isna(at):
        return found[0][1]
    return min(found, key=lambda f: abs(f[0] - at))[1]


MODE_OF = {"meta": "standard", "championship": "championship"}
# championship rollouts score finishing points ÷ 28, not wins: shown as expected points, other rules as win chance
UNIT = {"simple": "pp", "meta": "pp", "championship": "points"}
SCALE = {"pp": 100, "points": 28}


def price_check(checks: pd.DataFrame | None, bots: str, n: int, sq: int) -> str:
    """What replaying a narrow deal at whole-pound prices on fresh games found (scripts/16_price_checks.py)."""
    if checks is None:
        return ""
    c = checks[(checks.bots == bots) & (checks.n_players == n) & (checks.square == sq)]
    if c.empty:
        return ""
    pounds = lambda d: ", ".join(f"£{int(x)}" for x in d.price.dropna())  # noqa: E731
    good = c[c.verdict == "both gain (95%)"]
    if len(good):
        return f"replayed on fresh games: both clearly gain at {pounds(good)}"
    if c.price.isna().all():
        return "no whole-pound price inside the zone, so no payable deal"
    return f"replayed on fresh games at {pounds(c)}: no price where both clearly gain"


def property_trades():
    """Every property sold to the player it completes a set for (scripts/10_property_trades.py)."""
    ed = load_edition()
    curves, zones = [], []
    checks = read("price_checks.csv")
    for bots, label in [("simple", "Simple bots"), ("meta", "Meta agents, official rules"),
                        ("championship", "Meta agents, championship rules")]:
        d = TAB / "property_trades" / bots
        parts = [pd.read_csv(f) for f in sorted(d.glob("*p_*.csv"))] if d.exists() else []
        if not parts:
            print(f"  (no property trades for {bots} yet: skipped)")
            continue
        vine = (pd.read_csv(TAB / "trade_curve_orange_squeeze.csv").query("buyer == 0").drop(columns="buyer")
                if bots == "simple" else read(f"meta_trade_curve_{MODE_OF[bots]}.csv"))
        sizes = {int(x.n_players.iloc[0]) for x in parts}
        if vine is not None:
            parts.append(vine[vine.n_players.isin(sizes)].assign(square=19))
        c = pd.concat(parts)
        unit = UNIT[bots]
        for r in roles(c, ["n_players", "square"], scale=SCALE[unit]):
            curves.append({"opponents": label, "unit": unit, **r})
        summary = read(f"property_trade_summary_{bots}.csv")
        if summary is None:
            continue
        for (n, sq), g in c.groupby(["n_players", "square"]):
            hit = summary[(summary.n_players == n) & (summary.square == sq)]
            if hit.empty:
                continue
            z = hit.iloc[0]
            seller_note = ("gains even giving it away" if z.seller_gains_free else
                           "loses at every price tested" if pd.isna(z.seller_min_price_win) else "")
            buyer_note = "loses at every price, even free" if pd.isna(z.buyer_max_price_win) else ""
            zones.append({"opponents": label, "unit": unit, "n_players": n, "square": sq, "name": ed.names[sq],
                          "group": ed.group_names[ed.group_of[sq]], "price": ed.price[sq],
                          "seller_break_even": z["seller_min_price_win"], "buyer_maximum": z["buyer_max_price_win"],
                          "seller_break_even_se": crossing_se(g, 1, z["seller_min_price_win"]),
                          "buyer_maximum_se": crossing_se(g, 0, z["buyer_max_price_win"]),
                          "buyer_maximum_is_all_cash": bool(z["buyer_max_censored"]),
                          "deal_zone": bool(z["deal_zone_exists"]), "deal_ranges": z["deal_ranges"],
                          "confident_deal_ranges": z["confident_deal_ranges"], "allowed": bool(z["legal"]),
                          "evidence": z.get("evidence", ""), "price_check": price_check(checks, bots, n, sq),
                          "note": zone_note(z),
                          "seller_break_even_networth": z["seller_min_price_networth"],
                          "buyer_maximum_networth": z["buyer_max_price_networth"],
                          "buyer_win_pct_without": 100 * z["p_win_base_buyer"],
                          "buyer_win_pct_if_free": 100 * z["p_win_buyer_if_free"],
                          "seller_win_pct_without": 100 * z["p_win_base_seller"],
                          "seller_note": seller_note, "buyer_note": buyer_note})
    if not zones:
        return
    cv = pd.DataFrame(curves)
    cv.insert(2, "name", cv.square.map(lambda q: ed.names[int(q)]))
    save(cv, "property_trades.csv")
    z = pd.DataFrame(zones)
    z.insert(0, "key", z.opponents + " | " + z.n_players.astype(str) + " players | " + z.name)
    save(z, "property_zones.csv")


def meta_vs_simple():
    """The meta agent at a table of simple bots, with one settings group copied back (09_meta_vs_simple.py)."""
    d = read("meta_vs_simple_standard.csv", rules=RULES["standard"])
    if d is None:
        return
    d["candidate"] = d.candidate.map(lambda c: c[0].upper() + c[1:])
    d["significant"] = (d.rel_low > 1) | (d.rel_high < 1)
    d.insert(0, "key", d.rules + " | " + d.n_players.astype(str) + " players | " + d.candidate)
    save(d[["key", "rules", "n_players", "candidate", "relative", "rel_low", "rel_high", "significant", "games"]],
         "meta_vs_simple.csv")


def shown(key: str, v):
    """A genome value as the settings table shows it."""
    if key == "jail":
        return JAIL.get(v, v)
    if key in ("build_cap", "max_level"):
        return LEVEL.get(int(v), v)
    if isinstance(v, bool):
        return "yes" if v else "no"
    return round(v, 4) if isinstance(v, float) else v


def meta():
    agents, checks, abl, hard = [], [], [], []
    for mode, label in RULES.items():
        if not (TAB / f"meta_refinement_{mode}.csv").exists():
            print(f"  (no hardened {mode} meta agents yet: skipped)")
            continue
        metas = json.loads((TAB / f"meta_agents_{mode}.json").read_text())
        no_ops = set()  # one-change ablations that leave the meta agent as it is
        for n, g in metas.items():
            for key, (name, unit) in PARAM.items():
                agents.append({"rules": label, "n_players": int(n), "setting": name, "unit": unit,
                               "value": shown(key, g[key])})
            for k, v in g.items():
                if k.startswith("w_"):
                    agents.append({"rules": label, "n_players": int(n),
                                   "setting": f"Buying weight, {GROUP_NAME.get(k[2:], k[2:])}", "unit": "×",
                                   "value": round(v, 4)})
            genome = {k: v for k, v in g.items() if k != "name"}
            for name, variant in ablations(genome).items():
                if variant == genome:
                    no_ops.add((int(n), name))
        v = pd.read_csv(TAB / f"meta_validation_{mode}.csv").assign(rules=label)
        checks.append(v[["rules", "n_players", "name", "relative", "rel_low", "rel_high", "capped_share"]])
        a = pd.read_csv(TAB / f"meta_ablations_{mode}.csv").assign(rules=label)
        a["name"] = a.name.replace(RENAMED)  # tables from before the rename use the old name
        a = a[[(int(n), name) not in no_ops for n, name in zip(a.n_players, a.name)]]
        a["significant"] = (a.rel_low > 1) | (a.rel_high < 1)
        # the same result in every game: the change never altered a decision (e.g. a take-a-Chance flip for an agent
        # whose card counting makes that choice)
        same = (a.rel_low == 1) & (a.rel_high == 1)
        a["no_effect"] = a.no_effect.astype("boolean").fillna(same).astype(bool) if "no_effect" in a else same
        abl.append(a[["rules", "n_players", "name", "relative", "rel_low", "rel_high", "significant", "no_effect",
                      "capped_share"]])
        h = pd.read_csv(TAB / f"meta_refinement_{mode}.csv").assign(rules=label)
        # the agent kept: the one marked by least-exploitable selection, else the last one tested
        kept = h["selected"].fillna(False).astype(bool) if "selected" in h else pd.Series(False, index=h.index)
        for _, g in h.groupby("n_players"):
            if not kept[g.index].any():
                kept[g["round"].idxmax()] = True
        h["kept"] = kept.map({True: "kept", False: ""})
        hard.append(h)
    ag = pd.DataFrame(agents)
    ag.insert(0, "key", ag.rules + " | " + ag.n_players.astype(str) + " players | " + ag.setting)
    save(ag, "meta_agents.csv")
    save(pd.concat(checks).rename(columns={"name": "check"}), "meta_checks.csv")
    ab = pd.concat(abl).rename(columns={"name": "change"})
    ab["change"] = ab.change.map(lambda c: ABLATION.get(c, c))
    save(ab, "meta_ablations.csv")
    h = pd.concat(hard)
    h.insert(0, "key", h.rules + " | " + h.n_players.astype(str) + " players | round " + h["round"].astype(str))
    save(h[["key", "rules", "n_players", "round", "challenger_vs_meta", "meta_self_credit", "kept"]], "hardening.csv")


if __name__ == "__main__":
    for f in (squares, set_economics, strategies, seats, game_length, trades, property_trades, meta, meta_vs_simple):
        f()
        print("ok", f.__name__)
    for p in sorted(OUT.glob("*.csv")):
        print(f"{p.name:22s} {p.stat().st_size / 1024:7.1f} KB")
