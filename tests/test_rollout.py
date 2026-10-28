import sys
from pathlib import Path

import numpy as np
import pandas as pd

from monopoly_meta.rollout import apply_trade, indifference_price, rollout, trade_price_curve
from monopoly_meta.tournament import run_games, wilson, win_rates

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scenarios import orange_squeeze  # noqa: E402


def test_wilson_interval():
    lo, hi = wilson(50, 100)
    assert lo < 0.5 < hi and abs((lo + hi) / 2 - 0.5) < 1e-9
    assert wilson(0, 10)[0] == 0.0


def test_run_games_is_reproducible_and_rotates_seats():
    a = run_games(["balanced", "aggressive", "cautious"], 30, seed0=5, workers=1)
    b = run_games(["balanced", "aggressive", "cautious"], 30, seed0=5, workers=1)
    pd.testing.assert_frame_equal(a, b)
    assert set(a.seat0) == {"balanced", "aggressive", "cautious"}
    wr = win_rates(a)
    assert np.isclose(wr.wins.sum(), len(a))


def test_common_random_numbers_identical_states_give_identical_outcomes():
    s = orange_squeeze()
    w1, nw1, c1 = rollout(s, ["balanced"] * 4, 40, seed0=3, workers=1)
    w2, nw2, c2 = rollout(s, ["balanced"] * 4, 40, seed0=3, workers=1)
    assert (w1 == w2).all() and np.allclose(nw1, nw2) and (c1 == c2).all()
    assert np.allclose(w1.sum(axis=1), 1.0)  # credit always sums to one per game


def test_apply_trade_validates():
    s = orange_squeeze()
    assert apply_trade(s, seller=1, buyer=0, squares=[19], price=300) is not None
    assert apply_trade(s, seller=1, buyer=0, squares=[16], price=300) is None  # not the seller's
    assert apply_trade(s, seller=1, buyer=0, squares=[19], price=5000) is None  # buyer can't pay


def test_free_set_helps_buyer_and_hurts_bystanders():
    s = orange_squeeze()
    c = trade_price_curve(s, ["balanced"] * 4, seller=1, buyer=0, squares=[19], prices=[0], n=150, workers=1)
    d = c.set_index("player").d_win
    assert d[0] > 0.3 and d[2] + d[3] < 0
    assert np.isclose(d.sum(), 0, atol=1e-9)  # win probabilities still sum to one


def test_indifference_price_interpolates():
    c = pd.DataFrame({"price": [0, 100, 200], "player": [1, 1, 1], "d_win": [-0.2, -0.1, 0.1]})
    assert np.isclose(indifference_price(c, 1), 150)
    assert indifference_price(c.assign(d_win=[0.1, 0.2, 0.3]), 1) is None


def test_scenario_scales_to_every_table_size():
    import pytest
    for n in range(2, 7):
        s = orange_squeeze(n)
        assert s.n_players == n and s.owner[19] == 1 and s.owner[16] == s.owner[18] == 0
        assert sum(o >= 0 for o in s.owner) == 4 * n
    with pytest.raises(ValueError):
        orange_squeeze(7)


def test_two_player_trades_are_zero_sum():
    c = trade_price_curve(orange_squeeze(2), ["balanced"] * 2, seller=1, buyer=0, squares=[19],
                          prices=[300], n=60, workers=1)
    d = c.set_index("player").d_win
    assert np.isclose(d[0], -d[1])
