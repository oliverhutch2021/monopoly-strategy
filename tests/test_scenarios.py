"""The hand-built positions behind the trade valuations (scripts/scenarios.py)."""
import sys
from pathlib import Path

import pytest

from monopoly_meta import load_edition
from monopoly_meta.rollout import trade_price_curve

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scenarios import orange_squeeze, set_completion  # noqa: E402

ED = load_edition()
OWNABLE = [sq for sq in range(len(ED.names)) if ED.is_ownable(sq)]


@pytest.mark.parametrize("n", [2, 3, 4, 5, 6])
def test_vine_street_reproduces_the_orange_squeeze(n):
    a, b = orange_squeeze(n), set_completion("Vine Street", n)
    assert (a.owner, a.cash, a.pos, a.current, a.turn) == (b.owner, b.cash, b.pos, b.current, b.turn)


@pytest.mark.parametrize("n", [2, 4, 6])
def test_every_property_gets_a_clean_set_completion_position(n):
    for t in OWNABLE:
        s = set_completion(ED.names[t], n)
        group = [sq for sq in OWNABLE if ED.group_of[sq] == ED.group_of[t]]
        assert s.owner[t] == 1, ED.names[t]
        assert all(s.owner[sq] == 0 for sq in group if sq != t), ED.names[t]
        hands = [[sq for sq in OWNABLE if s.owner[sq] == p] for p in range(n)]
        assert len(hands[1]) == 4 and all(len(h) >= 4 for h in hands), (ED.names[t], hands)
        # nobody starts with a complete set: the sale is the only way to one
        for gi in {ED.group_of[sq] for sq in OWNABLE}:
            members = [sq for sq in OWNABLE if ED.group_of[sq] == gi]
            assert len({s.owner[sq] for sq in members}) > 1 or s.owner[members[0]] < 0, (ED.names[t], gi)


def test_set_completion_rejects_squares_that_cannot_be_owned():
    with pytest.raises(ValueError):
        set_completion("Free Parking", 4)
    with pytest.raises(ValueError):
        set_completion("Vine Street", 7)


def test_a_two_player_sale_is_zero_sum():
    """With two players one side's gain is the other's loss, at every price."""
    s = set_completion("Bow Street", 2)
    c = trade_price_curve(s, ["balanced", "balanced"], seller=1, buyer=0, squares=[ED.names.index("Bow Street")],
                          prices=[0, 400], n=40, seed0=3, workers=1)
    for _, g in c.groupby("price"):
        assert abs(g.d_win.sum()) < 1e-9
