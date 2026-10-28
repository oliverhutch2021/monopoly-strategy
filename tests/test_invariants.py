"""Property-based checks: play many full games and assert invariants after every turn."""
import pytest

from monopoly_meta.engine import BANK, HOTEL, Game, Rules
from monopoly_meta.policies import make_bot

KINDS = ["balanced", "aggressive", "cautious", "three_house", "random"]


def check_invariants(g):
    s, ed = g.s, g.ed
    for p in range(s.n_players):
        if s.alive[p]:
            assert s.cash[p] >= 0, f"negative cash for {p}"
        else:
            assert all(s.owner[sq] != p for sq in ed.ownable)
    houses = sum(lv for lv in s.level if 0 < lv < HOTEL)
    hotels = sum(lv == HOTEL for lv in s.level)
    assert s.bank_houses + houses == ed.bank_houses
    assert s.bank_hotels + hotels == ed.bank_hotels
    assert s.bank_houses >= 0 and s.bank_hotels >= 0
    for sq in range(ed.n_squares):
        if s.level[sq]:
            assert ed.types[sq] == "street"
            g_idx = ed.group_of[sq]
            assert g.owns_group(s.owner[sq], g_idx)
            assert not any(s.mortgaged[x] for x in ed.group_squares[g_idx])
        if s.mortgaged[sq]:
            assert s.owner[sq] != BANK
    if g.uneven_events == 0:  # even-build rule (can only break during a hotel/house shortage)
        for gi in ed.street_groups:
            lv = [s.level[x] for x in ed.group_squares[gi]]
            assert max(lv) - min(lv) <= 1
    held = sum(len(x) for x in s.goojf)
    if g.rules.card_draw == "deck":
        assert len(s.chance) + len(s.cc) + held == len(ed.chance) + len(ed.community_chest)
    else:
        assert len(s.chance) + len(s.cc) == len(ed.chance) + len(ed.community_chest)


@pytest.mark.parametrize("rules", [
    Rules(),
    Rules(free_parking_jackpot=True),
    Rules(card_draw="random"),
    Rules(auctions=False, max_turns=1500),
    Rules(speed_die=True, no_bid_to_richest=True, no_trades_heads_up=True, stalemate="championship",
          max_turns=1500),
])
def test_invariants_hold_through_full_games(rules):
    for seed in range(40):
        kinds = [KINDS[(seed + i) % len(KINDS)] for i in range(2 + seed % 5)]
        g = Game([make_bot(k) for k in kinds], seed=seed, rules=rules)
        while not g.done:
            g.take_turn()
            check_invariants(g)
        r = g.result()
        assert 0 <= r.winner < len(kinds)
        assert r.capped or sum(g.s.alive) == 1


def test_same_seed_same_game():
    a = Game([make_bot("balanced"), make_bot("aggressive")], seed=42).play()
    b = Game([make_bot("balanced"), make_bot("aggressive")], seed=42).play()
    assert a == b
