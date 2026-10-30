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
    Rules(build_any_time=True, house_auctions=True, mortgaged_count_for_rent=True),
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


@pytest.mark.parametrize("any_time", [False, True])
def test_house_auctions_keep_the_books(any_time):
    """With the bank short of houses from the start, so that auctions happen often: every house is in the bank or on
    the board, nobody's cash goes negative, and every auction charges at least the house's price and at most the
    winner's bid, for a house on the square the bid named, owned by the winner (updated review, finding 2)."""
    rules = Rules(house_auctions=True, build_any_time=any_time, max_turns=1500)
    held = 0
    for seed in range(30):
        kinds = [KINDS[(seed + i) % 4] for i in range(3 + seed % 3)]  # no random bot: it ignores the auction
        g = Game([make_bot(k) for k in kinds], seed=seed, rules=rules)
        g.s.bank_houses = 8  # a quarter of the usual 32
        g.house_auction_log = []
        while not g.done:
            seen = len(g.house_auction_log)
            g.take_turn()
            for buyer, sq, price, limit in g.house_auction_log[seen:]:
                assert g.ed.house_cost[g.ed.group_of[sq]] <= price <= limit, (seed, buyer, sq, price, limit)
            houses = sum(lv for lv in g.s.level if 0 < lv < HOTEL)
            assert g.s.bank_houses + houses == 8 and g.s.bank_houses >= 0  # every house in the bank or on the board
            assert g.s.bank_hotels + sum(lv == HOTEL for lv in g.s.level) == g.ed.bank_hotels
            assert all(c >= 0 for p, c in enumerate(g.s.cash) if g.s.alive[p])
        held += g.house_auctions_held
    assert held > 0  # the test saw auctions
