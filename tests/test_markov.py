import numpy as np
import pytest

from monopoly_meta.engine import Game, Rules
from monopoly_meta.markov import build_chain
from monopoly_meta.policies import Policy
from monopoly_meta.roi import group_table, property_table


class Walker(Policy):
    """Never buys: the token just walks the board, as in the Markov model."""

    def __init__(self, jail="roll"):
        self.jail = jail

    def buy(self, g, p, sq):
        return False

    def jail_decision(self, g, p):
        return self.jail


@pytest.mark.parametrize("strategy", ["long", "short"])
def test_chain_is_stochastic_and_normalised(strategy):
    m = build_chain(jail_strategy=strategy)
    assert np.allclose(m.P.sum(axis=1), 1)
    assert np.isclose(m.pi.sum(), 1) and (m.pi >= 0).all()
    assert np.allclose(m.pi @ m.P, m.pi, atol=1e-12)


def test_long_jail_strategy_spends_more_turns_in_jail():
    assert build_chain(jail_strategy="long").jail_turn_share > build_chain(jail_strategy="short").jail_turn_share


def test_go_to_jail_is_never_a_final_position():
    m = build_chain()
    # nobody ends a move on Go To Jail: every state for square 30 has zero mass
    assert np.allclose(m.pi[[30 * 3 + d for d in range(3)]], 0)


@pytest.mark.parametrize("strategy,jail", [("long", "roll"), ("short", "pay")])
def test_markov_matches_simulation(strategy, jail):
    m = build_chain(jail_strategy=strategy)
    g = Game([Walker(jail), Walker(jail)], seed=11, track_landings=True,
             rules=Rules(auctions=False, card_draw="random", max_turns=300_000))
    g.play()
    sim = np.array(g.landings) / g.s.turn
    assert np.abs(sim - m.visits_per_turn).max() < 0.0025


def test_trafalgar_is_most_landed_property():
    m = build_chain()
    props = property_table(m)
    assert props.loc[props.landings_per_turn.idxmax(), "name"] == "Trafalgar Square"


def test_group_table_shapes_and_sanity():
    m = build_chain()
    gt = group_table(m, n_players=4)
    assert set(gt.group) == set(m.edition.group_names)
    orange = gt[(gt.group == "orange")].set_index("level")
    # rent rises with development, payback is finite
    assert orange.ev_per_opp_turn.is_monotonic_increasing
    assert np.isfinite(orange.payback_rounds).all()
