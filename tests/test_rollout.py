import sys
from pathlib import Path

import numpy as np
import pandas as pd

from monopoly_meta.rollout import apply_trade, deal_summary, indifference_price, rollout, trade_price_curve
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


# ---------------------------------------------------------------------- deal summaries (methodology review, 2026-10-30)
def _curve(prices, buyer, seller, se=0.001):
    rows = []
    for x, b, s in zip(prices, buyer, seller):
        for p, d in ((0, b), (1, s)):
            rows.append({"price": x, "player": p, "d_win": d, "d_win_se": se, "d_networth": d * 1000,
                         "d_networth_se": se, "p_win_base": 0.3, "p_win_trade": 0.3 + d})
    return pd.DataFrame(rows)


def test_gain_ranges_finds_every_range():
    from monopoly_meta.rollout import gain_ranges, intersect
    x = [0, 100, 200, 300, 400]
    assert gain_ranges(x, [-1, 1, 1, -1, 1]) == [(50.0, 250.0), (350.0, 400.0)]
    assert gain_ranges(x, [1, 1, 1, 1, 1]) == [(0.0, 400.0)]
    assert gain_ranges(x, [-1, -1, 0, -1, -1]) == []
    assert intersect([(0, 100), (200, 300)], [(50, 250)]) == [(50, 100), (200, 250)]
    assert intersect([(0, 100)], [(100, 200)]) == []  # touching at one price is no range


def test_deal_summary_handles_a_curve_that_is_not_monotone():
    """The four-player brown case: the buyer loses if given the property, gains at £200-£650, loses above."""
    from monopoly_meta.rollout import deal_summary
    prices = [0, 100, 200, 300, 400, 500, 600, 700, 800]
    buyer = [-0.05, -0.07, 0.0, 0.12, 0.10, 0.065, 0.026, -0.01, -0.05]
    seller = [-0.08, -0.06, -0.044, -0.03, -0.005, 0.023, 0.06, 0.1, 0.15]
    z = deal_summary(_curve(prices, buyer, seller), seller=1, buyer=0)
    assert z["deal_zone_exists"] and z["deal_pieces"] == 1
    assert 410 < z["seller_min_price_win"] < 420 and 670 < z["buyer_max_price_win"] < 680
    assert not z["monotone"] and z["buyer_reversals"] >= 1 and z["seller_reversals"] == 0
    assert z["confident_deal_ranges"]  # both well above zero at £500 and £600


def test_deal_summary_when_the_seller_gains_at_every_price():
    from monopoly_meta.rollout import deal_summary
    prices = [0, 100, 200, 300]
    z = deal_summary(_curve(prices, [0.3, 0.2, 0.1, -0.1], [0.01, 0.02, 0.05, 0.1]), seller=1, buyer=0)
    assert z["deal_zone_exists"] and z["seller_gains_free"] and z["seller_min_price_win"] == 0.0
    assert 240 < z["buyer_max_price_win"] < 260


def test_deal_summary_disconnected_ranges_and_illegal_trades():
    from monopoly_meta.rollout import deal_summary
    prices = [0, 100, 200, 300, 400]
    c = _curve(prices, [0.2, 0.1, -0.1, 0.1, 0.05], [0.1, 0.1, 0.1, 0.1, 0.1])
    z = deal_summary(c, seller=1, buyer=0)
    assert z["deal_pieces"] == 2 and z["deal_ranges"] == "0-150; 250-400" and z["buyer_max_censored"]
    z = deal_summary(c, seller=1, buyer=0, legal=False)
    assert not z["deal_zone_exists"] and z["deal_ranges"] == "" and not z["legal"]


def test_championship_trades_heads_up_are_illegal():
    from monopoly_meta.engine import championship_rules
    from monopoly_meta.rollout import trade_allowed
    s2 = orange_squeeze(2)
    assert trade_allowed(s2, 1, 0, [19])  # the official rules allow it
    assert not trade_allowed(s2, 1, 0, [19], championship_rules(2))  # no trades heads-up
    assert apply_trade(s2, 1, 0, [19], 300, championship_rules(2)) is None
    assert trade_allowed(orange_squeeze(3), 1, 0, [19], championship_rules(3))
    c = trade_price_curve(s2, ["balanced"] * 2, seller=1, buyer=0, squares=[19], prices=[300], n=8, workers=1,
                          rules=championship_rules(2))
    assert c.empty and c.attrs["legal"] is False
    h = trade_price_curve(s2, ["balanced"] * 2, seller=1, buyer=0, squares=[19], prices=[300], n=8, workers=1,
                          rules=championship_rules(2), hypothetical=True)
    assert not h.empty and h.attrs["legal"] is False


def test_extra_networth_marks_and_bootstrap_leave_the_curve_unchanged():
    s = orange_squeeze()
    kw = dict(seller=1, buyer=0, squares=[19], prices=[0, 600, 1200], n=24, workers=1, seed0=5)
    plain = trade_price_curve(s, ["balanced"] * 4, **kw)
    more = trade_price_curve(s, ["balanced"] * 4, networth_rounds=(5, 10), boot=40, **kw)
    pd.testing.assert_frame_equal(plain, more[plain.columns])  # pausing to look changes no game
    assert {"d_networth_r5", "d_networth_r10_se"} <= set(more.columns)
    b = more.attrs["deal_bootstrap"]
    assert b["resamples"] == 40 and 0 <= b["deal_share_of_resamples"] <= 1
    summary = deal_summary(more, seller=1, buyer=0)  # net worth after 5 and 10 of each player's own turns too
    assert {"buyer_max_price_networth_r5", "seller_min_price_networth_r10"} <= set(summary)


def test_games_stopped_by_the_limit_are_not_outright_wins():
    """Review finding: time-limit leaders were counted as outright winners."""
    from monopoly_meta.engine import championship_rules
    df = run_games(["aggressive", "balanced"], 12, seed0=3, rules=championship_rules(2, rounds=3), workers=1)
    assert df.capped.all()  # three rounds: every game hits the limit
    wr = win_rates(df)
    assert (wr.wins == 0).all() and wr.limit_wins.sum() == 12 and np.isclose(wr.game_win_rate.sum(), 1.0)
    seats = win_rates(df, by="seat")
    assert seats.wins.sum() == 0 and seats.limit_wins.sum() == 12


def test_outright_win_rates_are_shares_of_decided_games():
    """Review finding: outright wins compared with 1/n look unfair whenever some games stop at the limit. As a
    share of the decided games, identical seats average exactly 1/n."""
    from monopoly_meta.engine import championship_rules
    df = run_games(["balanced"] * 3, 60, seed0=11, rules=championship_rules(3, rounds=40), workers=1, rotate=False)
    assert 0 < df.capped.sum() < len(df)  # some games stop at the limit, some don't
    seats = win_rates(df, by="seat")
    assert np.isclose(seats.win_rate.sum(), 1.0) and (seats.decided == len(df) - df.capped.sum()).all()
    assert np.isclose(seats.game_win_rate.sum(), 1.0)
