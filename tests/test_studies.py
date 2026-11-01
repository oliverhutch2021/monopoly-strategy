"""The analysis helpers of the review studies (scripts 15-18)."""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from monopoly_meta.engine import Game
from monopoly_meta.policies import make_bot

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sens = importlib.import_module("15_rule_sensitivity")
checks = importlib.import_module("16_price_checks")
positions = importlib.import_module("17_game_positions")
scoring = importlib.import_module("18_scoring_sensitivity")
ENGINE = sens.ENGINE


def test_a_rerun_that_reproduces_moves_nothing_and_a_real_change_is_detected():
    rng = np.random.default_rng(0)
    base = rng.integers(0, 2, 4000).astype(float)
    cand = rng.integers(0, 2, 4000).astype(float)
    before = {"engine rules|final agent": base, "engine rules|challenger": cand}
    same = sens.paired_moves(before, dict(before))
    assert same == {"engine rules|challenger": (0.0, 0.0, 0.0)}
    better = cand.copy()
    better[np.flatnonzero(better == 0)[:400]] = 1  # the candidate now wins 400 more of the same games
    point, lo, hi = sens.paired_moves(before, {**before, "engine rules|challenger": better})["engine rules|challenger"]
    assert point > 0 and 0 < lo < point < hi
    assert sens.paired_moves(before, {"engine rules|final agent": base[:10]}) == {}  # different games: not paired


def test_each_rule_comparison_reads_changed_equivalent_inconclusive_or_untouched():
    rows = [("final agent", "build any time", 1.0, 0.0, 1.0, 1.0),     # the denominator: not a test
            ("a", ENGINE, 1.0, 0.0, 1.0, 1.0),                          # the engine's own rules: not a test
            ("a", "build any time", 1.10, 0.01, 1.08, 1.12),            # clearly changed
            ("a", "house auctions", 1.0, 0.001, 0.998, 1.002),          # tight around 1: equivalent
            ("a", "any time + auctions", 1.01, 0.02, 0.97, 1.05),       # wide: inconclusive
            ("a", "mortgaged stations count", 1.0, 0.0, 1.0, 1.0),      # the rule never came into play
            ("b", "build any time", 1.012, 0.002, 1.008, 1.016)]        # a real change, but within the tolerance
    cand = pd.DataFrame(rows, columns=["candidate", "variant", "vs_engine_rules", "vs_engine_log_se", "vs_engine_low",
                                       "vs_engine_high"])
    read = sens.adjust(cand).reading.tolist()
    assert read == ["", "", "changed", "equivalent", "inconclusive", "the same games", "small change"]


def test_whole_pound_prices_to_check():
    assert checks.test_prices("305-305") == [305]
    assert checks.test_prices("100-101; 200-200") == [100, 101, 200]
    assert checks.test_prices("300-310") == [300, 305, 310]


def test_a_game_position_qualifies_only_with_two_oranges_against_one():
    g = Game([make_bot("balanced") for _ in range(4)], seed=1)
    s = g.s
    s.owner[16], s.owner[18], s.owner[19] = 0, 0, 2
    s.cash[0] = 900
    assert positions.qualifying(g) == (0, 2, 19)
    s.mortgaged[18] = True
    assert positions.qualifying(g) is None  # a mortgaged orange
    s.mortgaged[18] = False
    s.cash[0] = 700
    assert positions.qualifying(g) is None  # the buyer couldn't pay the highest price tested
    s.cash[0], s.owner[19] = 900, -1
    assert positions.qualifying(g) is None  # nobody to buy the third from


def test_the_points_schedules_compared():
    assert scoring.SCHEDULES == ("extrapolated", "extend_four", "rank_linear")
    assert scoring.points("extrapolated", 6) == [13, 6, 3, 2, 1, 0]
    assert scoring.points("rank_linear", 5) == [19, 14, 10, 5, 0]
