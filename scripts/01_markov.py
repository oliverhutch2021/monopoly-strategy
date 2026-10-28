"""Exact landing probabilities (Markov chain) and their validation against the simulator.

Outputs
  results/tables/landing_probabilities.csv   per square, short- and long-stay jail strategies
  results/tables/markov_validation.csv       Markov vs simulation (random-draw and fixed-deck cards)
"""
from pathlib import Path

import numpy as np
import pandas as pd

from monopoly_meta.engine import Game, Rules
from monopoly_meta.markov import build_chain
from monopoly_meta.policies import Policy

OUT = Path(__file__).resolve().parents[1] / "results" / "tables"
OUT.mkdir(parents=True, exist_ok=True)
SIM_TURNS = 10_000_000
SEEDS = {("long", "random"): 101, ("long", "deck"): 102, ("short", "random"): 103, ("short", "deck"): 104}


class Walker(Policy):
    """Never buys. `use_card`: spend a Get-out-of-Jail-free card as soon as jailed (else hoard it)."""

    def __init__(self, jail, use_card):
        self.jail, self.use_card = jail, use_card

    def buy(self, g, p, sq):
        return False

    def jail_decision(self, g, p):
        if self.use_card and g.s.goojf[p]:
            return "card"
        return self.jail


def simulate(jail, card_draw, seed, turns=SIM_TURNS, batches=50):
    """Landings per turn, with a batch-means standard error (landings are serially correlated).

    Short-stay walkers use a Get-out-of-Jail-free card immediately (cards cycle back into the
    deck); long-stay walkers hoard them, so under real fixed decks the decks shrink to 15 cards.
    """
    use_card = jail == "pay"
    g = Game([Walker(jail, use_card), Walker(jail, use_card)], seed=seed, track_landings=True,
             rules=Rules(auctions=False, card_draw=card_draw, max_turns=turns))
    per_batch = []
    prev = np.zeros(40)
    for b in range(1, batches + 1):
        g.rules.max_turns = turns * b // batches
        g.done = False
        g.play()
        cur = np.array(g.landings, dtype=float)
        per_batch.append((cur - prev) / (turns / batches))
        prev = cur
    per_batch = np.array(per_batch)
    return per_batch.mean(0), per_batch.std(0, ddof=1) / np.sqrt(batches)


def main():
    chains = {s: build_chain(jail_strategy=s) for s in ("short", "long")}
    ed = chains["long"].edition
    rows = []
    for sq in range(40):
        row = {"square": sq, "name": ed.names[sq], "type": ed.types[sq],
               "group": ed.group_names[ed.group_of[sq]] if ed.group_of[sq] >= 0 else ""}
        for s, m in chains.items():
            row[f"landings_per_turn_{s}"] = m.visits_per_turn[sq]
            row[f"landing_share_pct_{s}"] = 100 * m.landing_share[sq]
        rows.append(row)
    lp = pd.DataFrame(rows)
    lp.attrs["jail_turn_share"] = {s: m.jail_turn_share for s, m in chains.items()}
    lp.to_csv(OUT / "landing_probabilities.csv", index=False)
    for s, m in chains.items():
        print(f"{s:>5} jail: {100 * m.jail_turn_share:.2f}% of turns start in jail, "
              f"{m.rolls_per_turn:.3f} rolls per turn")

    val = []
    for s, jail in (("long", "roll"), ("short", "pay")):
        for mode in ("random", "deck"):
            sim, se = simulate(jail, mode, seed=SEEDS[(s, mode)])
            exact = chains[s].visits_per_turn
            z = (sim - exact) / np.where(se > 0, se, np.nan)
            for sq in range(40):
                val.append({"jail_strategy": s, "card_draw": mode, "square": sq, "name": ed.names[sq],
                            "markov": exact[sq], "simulated": sim[sq], "se": se[sq], "z": z[sq]})
            zz = z[np.isfinite(z)]
            print(f"{s:>5} / {mode:>6}: max |z| = {np.abs(zz).max():.2f}, "
                  f"chi2 = {np.sum(zz ** 2):.1f} on {len(zz)} squares, "
                  f"max abs diff = {np.nanmax(np.abs(sim - exact)):.5f}")
    pd.DataFrame(val).to_csv(OUT / "markov_validation.csv", index=False)


if __name__ == "__main__":
    main()
