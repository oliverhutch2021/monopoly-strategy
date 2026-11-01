"""Write the dashboard's store documents (dataset docs + page) as JSON for one ArtifactData batch.

blobs.json maps each dataset id to its uploaded CSV asset; versions.json holds the store versions last written."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
blobs = json.loads((HERE / "blobs.json").read_text())
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
BY = "Claude, from the monopoly-meta simulation results"
D = {
    "squares": ("Board squares and landing odds",
                "Every square of the classic UK board with its price, rent at each development level and expected "
                "landings per 100 turns from the exact 123-state Markov chain (staying in jail to roll for doubles, "
                "and leaving at once). Exported by scripts/08_dashboard_data.py."),
    "set_economics": ("Set payback and building returns",
                      "For each set, station and utility group at 2 to 6 players: cost of each development level, "
                      "expected rent per round from every opponent, rounds to pay back, and extra rent per round "
                      "per £100 spent on each building level. Computed from the Markov chain."),
    "strategies": ("Strategy tweaks vs simple bots",
                   "One tweaked bot against copies of the simple bot at 2 to 6 players, seats rotated: outright wins "
                   "as a share of the games that finish, relative to a fair share, with 95% Wilson intervals; beside "
                   "it the share of all games won outright, the share stopped by the time limit and the share won "
                   "on it (100,000 games per cell under official rules, 60,000 under championship rules)."),
    "seats": ("Win rate by seat",
              "Identical simple bots in fixed seats at 2 to 6 players: outright wins per seat as a share of the "
              "games that finish, with 95% intervals and relative to a fair share, and beside it the share of all "
              "games won outright and the share in which the seat was richest when the time limit hit (100,000 "
              "games per table size under official rules, 60,000 under championship rules)."),
    "game_length": ("Game length by rule set",
                    "Median and 90th-percentile rounds per game with simple bots, by rule set and table size, and "
                    "the share of games stopped by the time limit."),
    "trade_curves": ("Vine Street price curves",
                     "The change for the buyer, the seller and everyone else when Vine Street is sold at each price, "
                     "from 20,000 paired rollouts per price, against two baselines: the seller keeping it for good "
                     "(the deed's own value) and trading carrying on as normal (whether to accept the offer today). "
                     "change and change_se are in the row's unit: percentage points of win chance (pp), or expected "
                     "championship points (points) under championship rules; outright_pp is the change in outright "
                     "wins; d_networth the change in net worth 40 player-turns later. Everyone else's standard error "
                     "is paired, from their summed outcome game by game."),
    "deal_zones": ("Vine Street deal zones",
                   "Seller's break-even price and buyer's maximum for the Vine Street sale, judged by the rules' "
                   "score (win chance, or championship points) and by net worth, for each opponent type, baseline "
                   "and table size: every price range where both sides gain, whether the rules allow the trade, "
                   "and, with trading carrying on, how often the buyer got Vine Street later anyway and at what "
                   "median price."),
    "meta_agents": ("Meta agent settings",
                    "The settings of the final meta agents (v0.3's, or v0.5's hardened ones) for each rule set and "
                    "table size."),
    "meta_checks": ("Meta agent strength checks",
                    "Paired checks of each final meta agent: against simple bots, a simple bot at a table of meta "
                    "agents, and the strongest known challenger, with 95% bootstrap intervals over 40,000 games. "
                    "Under championship rules the credit is finishing points ÷ 28."),
    "meta_ablations": ("Deviations from the meta",
                       "One player changes one setting of the final meta agent and plays against meta agents, on the "
                       "same 40,000 games as an unchanged meta agent: credit relative to it, with 95% intervals; "
                       "no_effect marks a change that never altered a decision."),
    "property_trades": ("Every property's price curves",
                        "The change for buyer, seller and everyone else, against the seller keeping it for good, when "
                        "each of the 28 properties is sold to the player it completes a set for, at 2 to 6 players: "
                        "10,000 paired rollouts per price (5,000 under championship rules, 20,000 for Vine Street). "
                        "change is in percentage points of win chance (unit pp) or expected championship points "
                        "(unit points). From scripts/10_property_trades.py."),
    "property_zones": ("Every property's deal zone",
                       "For each property, opponent type and table size: the seller's break-even price and the "
                       "buyer's maximum, by win chance and by net worth, with rough standard errors; every price "
                       "range where both sides gain, whether the rules allow the trade, and notes where a curve "
                       "isn't monotone or never crosses zero. evidence says whether a zone rests on a price actually "
                       "played; price_check what replaying a narrow zone at whole-pound prices on fresh games found "
                       "(scripts/16_price_checks.py)."),
    "meta_vs_simple": ("Meta agent vs simple bots",
                       "The official-rules final meta agent at a table of simple bots, alone and with one group of "
                       "its settings copied from the simple bot: wins relative to a simple bot in the same seat, "
                       "30,000 paired games each, 95% bootstrap intervals. From scripts/09_meta_vs_simple.py."),
    "moves": ("Where one throw takes you",
              "For every starting square: the chance of ending on each square after one throw of the dice (p_roll) "
              "and at the end of the turn, doubles rolled again (p_turn), cards and Go to Jail included, from the "
              "exact 123-state Markov chain with cards drawn at random. Exported by scripts/11_board_data.py."),
    "deeds": ("Property card details",
              "Each square's type and group, taxes, and for properties the mortgage value, the cost to lift the "
              "mortgage, the house cost, station rents and utility dice multipliers, from the classic UK edition "
              "data. Exported by scripts/11_board_data.py."),
    "hardening": ("Meta hardening rounds",
                  "Each best-response round: the challenger's win credit over the meta agent's own at the same "
                  "table, and which round's agent was kept."),
}
writes = [{"op": "set", "collection": "dash", "doc_id": "meta", "data": {"title": "Monopoly Meta"}}]
if "--params" in sys.argv:
    writes.append({"op": "set", "collection": "dash", "doc_id": "params",
                   "data": {"players": 4, "rules": "Official rules", "opponents": "Simple bots",
                            "deal": "Completes the buyer's set", "price": 650, "square": 24, "view": "3d",
                            "property": 19, "popp": "Simple bots", "pprice": 600, "bmode": "towers",
                            "baseline": "Kept for good"}})
versions = json.loads((HERE / "versions.json").read_text()) if (HERE / "versions.json").exists() else {}
only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None
for ds, (title, desc) in D.items():
    if ds not in blobs or (only is not None and ds not in only):
        continue
    w = {"op": "set", "collection": "datasets", "doc_id": ds,
         "data": {"title": title, "description": desc,
                  "source": {"kind": "file", "url": blobs[ds], "name": f"{ds}.csv"},
                  "updated": {"at": now, "by": BY}, "fixed": True}}
    if f"datasets/{ds}" in versions:
        w["if_version"] = versions[f"datasets/{ds}"]
    writes.append(w)
FILES = sys.argv[sys.argv.index("--files") + 1].split(",") if "--files" in sys.argv else \
    ["index.html", "theme.css", "board3d.js"]
for name in FILES:  # the page and the files it links to
    (HERE / f"{name}.json").write_text(json.dumps({"text": (HERE / name).read_text()}))
    w = {"op": "set", "collection": "files", "doc_id": name, "file_path": str(HERE / f"{name}.json")}
    if f"files/{name}" in versions:
        w["if_version"] = versions[f"files/{name}"]
    writes.append(w)
for x in writes:
    if x["collection"] == "dash" and f"dash/{x['doc_id']}" in versions:
        x["if_version"] = versions[f"dash/{x['doc_id']}"]
(HERE / "writes.json").write_text(json.dumps(writes, indent=1, ensure_ascii=False))
print(len(writes), "writes;", (HERE / "index.html").stat().st_size // 1024, "KB page")
