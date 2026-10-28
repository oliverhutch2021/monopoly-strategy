"""Board data for the dashboard's 3D board and property cards.

    python scripts/11_board_data.py

Outputs (results/dashboard/)
  moves.csv   where one throw of the dice takes you from each square, and where your turn ends
              (doubles rolled again, three doubles to jail), from the exact Markov chain. Cards are
              drawn at random, as in the chain; "In jail" is square 10 reached by being sent there.
  deeds.csv   each ownable square's mortgage value, the cost to lift the mortgage, house cost,
              taxes, station rents and utility multipliers, straight from the edition data.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from monopoly_meta.edition import load_edition
from monopoly_meta.markov import _jail_state, _state, build_chain

OUT = Path(__file__).resolve().parents[1] / "results" / "dashboard"


def moves() -> pd.DataFrame:
    ed = load_edition()
    m = build_chain(ed, jail_strategy="long")
    P, n_sq, jail = m.P, ed.n_squares, ed.jail_square
    jail_states = [_jail_state(n) for n in (1, 2, 3)]

    def to_squares(x: np.ndarray) -> np.ndarray:
        """Collapse roll-states to squares; any jail state counts as square 10, in jail."""
        sq = np.zeros(n_sq)
        for pos in range(n_sq):
            sq[pos] += x[[_state(pos, d) for d in range(3)]].sum()
        sq[jail] += x[jail_states].sum()
        return sq

    rows = []
    for start in range(n_sq):
        if start == ed.go_to_jail_square:
            continue  # nobody starts a turn on Go To Jail
        x = P[_state(start, 0)]
        roll = to_squares(x)
        # the whole turn: keep rolling while the last throw was a double (states with d >= 1)
        end = np.zeros(len(x))
        stop = [_state(p, 0) for p in range(n_sq)] + jail_states
        end[stop] += x[stop]
        cont = x.copy()
        cont[stop] = 0
        for _ in range(3):
            if cont.sum() < 1e-15:
                break
            nxt = cont @ P
            end[stop] += nxt[stop]
            cont = nxt.copy()
            cont[stop] = 0
        turn = to_squares(end)
        in_jail_roll = x[jail_states].sum()
        in_jail_turn = end[jail_states].sum()
        for dest in range(n_sq):
            if roll[dest] < 1e-12 and turn[dest] < 1e-12:
                continue
            rows.append({"from_square": start, "to_square": dest,
                         "p_roll": round(float(roll[dest]), 6), "p_turn": round(float(turn[dest]), 6),
                         "p_roll_jailed": round(float(in_jail_roll), 6) if dest == jail else 0.0,
                         "p_turn_jailed": round(float(in_jail_turn), 6) if dest == jail else 0.0})
    df = pd.DataFrame(rows)
    assert np.allclose(df.groupby("from_square").p_roll.sum(), 1, atol=1e-5)
    assert np.allclose(df.groupby("from_square").p_turn.sum(), 1, atol=1e-5)
    return df


def deeds() -> pd.DataFrame:
    ed = load_edition()
    rows = []
    for sq in range(ed.n_squares):
        g = ed.group_of[sq]
        row = {"square": sq, "name": ed.names[sq], "type": ed.types[sq],
               "group": ed.group_names[g] if g >= 0 else "", "tax": ed.tax[sq] or None}
        if ed.is_ownable(sq):
            row.update({"price": ed.price[sq], "mortgage_value": ed.mortgage_value(sq),
                        "unmortgage_cost": ed.unmortgage_cost(sq),
                        "house_cost": ed.house_cost[g] or None})
        if ed.types[sq] == "station":
            row.update({f"rent_{k}_stations": r for k, r in enumerate(ed.station_rent, 1)})
        if ed.types[sq] == "utility":
            row.update({f"dice_x_{k}_utilities": r for k, r in enumerate(ed.utility_multiplier, 1)})
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    mv = moves()
    mv.to_csv(OUT / "moves.csv", index=False)
    dd = deeds()
    dd.to_csv(OUT / "deeds.csv", index=False)
    top = mv[mv.from_square == 0].nlargest(3, "p_roll")[["to_square", "p_roll"]]
    print(f"moves.csv: {len(mv)} rows; from GO the likeliest squares are {top.values.tolist()}")
    print(f"deeds.csv: {len(dd)} rows")


if __name__ == "__main__":
    main()
