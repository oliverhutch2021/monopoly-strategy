"""Property economics from the exact Markov landing rates.

Everything is expressed per *opponent turn* (how much one opponent's turn is expected to
pay you) and per *round* (all opponents take one turn each), so results scale with the
number of players.
"""
from __future__ import annotations

import pandas as pd

from .markov import MarkovResult

LEVEL_NAMES = ["site", "set", "1 house", "2 houses", "3 houses", "4 houses", "hotel"]


def property_table(m: MarkovResult) -> pd.DataFrame:
    """One row per ownable square with landing rate and expected rent per opponent turn."""
    ed = m.edition
    rows = []
    for sq in ed.ownable:
        t = ed.types[sq]
        v = m.visits_per_turn[sq]
        row = {
            "square": sq, "name": ed.names[sq], "group": ed.group_names[ed.group_of[sq]],
            "type": t, "price": ed.price[sq], "landings_per_turn": v,
            "landing_share_pct": 100 * m.landing_share[sq],
        }
        if t == "street":
            r = ed.rent[sq]
            rents = [r[0], 2 * r[0], *r[1:]]
            for name, rent in zip(LEVEL_NAMES, rents):
                row[f"rent_{name}"] = rent
                row[f"ev_{name}"] = v * rent
        rows.append(row)
    return pd.DataFrame(rows)


def group_table(m: MarkovResult, n_players: int = 4) -> pd.DataFrame:
    """Per colour group and development level: cost, income, payback and marginal return.

    * ``invest``          total spent to reach this level (all squares in the group)
    * ``ev_per_opp_turn`` expected rent from one opponent turn
    * ``payback_rounds``  invest / income per round with (n_players - 1) opponents
    * ``marginal_roi``    extra income per round per extra pound vs the previous level
    """
    ed = m.edition
    opp = n_players - 1
    rows = []
    for gi, gname in enumerate(ed.group_names):
        sqs = ed.group_squares[gi]
        t = ed.types[sqs[0]]
        base_cost = sum(ed.price[sq] for sq in sqs)
        levels = []
        if t == "street":
            hc = ed.house_cost[gi]
            for li, name in enumerate(LEVEL_NAMES[1:]):  # from "set" upwards
                if li == 0:
                    ev = sum(m.visits_per_turn[sq] * 2 * ed.rent[sq][0] for sq in sqs)
                else:
                    ev = sum(m.visits_per_turn[sq] * ed.rent[sq][li] for sq in sqs)
                levels.append((name, base_cost + li * hc * len(sqs), ev))
        elif t == "station":
            for k in range(1, len(sqs) + 1):
                # owning k stations: average over which k you own is ~ the mean landing rate
                mean_v = sum(m.visits_per_turn[sq] for sq in sqs) / len(sqs)
                ev = k * mean_v * ed.station_rent[k - 1]
                levels.append((f"{k} owned", k * ed.price[sqs[0]], ev))
        else:  # utilities
            for k in range(1, len(sqs) + 1):
                mean_u = sum(m.utility_dice_per_turn[sq] for sq in sqs) / len(sqs)
                ev = k * mean_u * ed.utility_multiplier[k - 1]
                levels.append((f"{k} owned", k * ed.price[sqs[0]], ev))
        prev_cost = prev_ev = None
        for name, invest, ev in levels:
            income_round = ev * opp
            marginal = None
            if prev_cost is not None and invest > prev_cost:
                marginal = (ev - prev_ev) * opp / (invest - prev_cost)
            rows.append({
                "group": gname, "level": name, "invest": invest,
                "ev_per_opp_turn": ev, "income_per_round": income_round,
                "payback_rounds": invest / income_round if income_round else float("inf"),
                "marginal_roi_per_round": marginal,
            })
            prev_cost, prev_ev = invest, ev
    return pd.DataFrame(rows)
