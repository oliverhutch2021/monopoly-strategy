"""Rule-by-rule unit tests using scripted dice."""
from monopoly_meta.engine import BANK, Game
from monopoly_meta.policies import Policy

from helpers import Bidder, Passive, ScriptedGame, set_deck


def game(dice, n=2, policies=None, **kw):
    return ScriptedGame(policies or [Passive() for _ in range(n)], dice, seed=1, **kw)


def give(g, p, *squares):
    for sq in squares:
        g.s.owner[sq] = p


# ------------------------------------------------------------------ movement & GO
def test_passing_go_collects_salary():
    g = game([(1, 2)])
    g.s.pos[0] = 38
    g.take_turn()
    assert g.s.pos[0] == 1 and g.s.cash[0] == 1700


def test_three_doubles_sends_to_jail_without_moving():
    g = game([(3, 3), (4, 4), (5, 5)])
    g.take_turn()
    assert g.s.in_jail[0] and g.s.pos[0] == 10 and g.s.cash[0] == 1500


def test_doubles_give_another_roll():
    g = game([(3, 3), (1, 3)])
    g.take_turn()
    assert g.s.pos[0] == 10 and not g.s.in_jail[0]  # 0 -> 6 -> 10 (just visiting)


def test_go_to_jail_square():
    g = game([(4, 5)])
    g.s.pos[0] = 21
    g.take_turn()
    assert g.s.in_jail[0] and g.s.pos[0] == 10


# ------------------------------------------------------------------ jail
def test_jail_double_exits_but_no_extra_roll():
    g = game([(2, 2)])
    g.send_to_jail(0)
    g.take_turn()  # would raise IndexError if a second roll were taken
    assert not g.s.in_jail[0] and g.s.pos[0] == 14


def test_jail_third_failure_pays_and_moves():
    g = game([(1, 2)])
    g.send_to_jail(0)
    g.s.jail_turns[0] = 2
    g.take_turn()
    assert not g.s.in_jail[0] and g.s.pos[0] == 13 and g.s.cash[0] == 1450


def test_jail_failed_roll_stays():
    g = game([(1, 2)])
    g.send_to_jail(0)
    g.take_turn()
    assert g.s.in_jail[0] and g.s.jail_turns[0] == 1 and g.s.pos[0] == 10


class Payer(Passive):
    def jail_decision(self, g, p):
        return "pay"


class CardUser(Passive):
    def jail_decision(self, g, p):
        return "card"


def test_jail_pay_then_normal_turn_with_doubles():
    g = game([(2, 2), (1, 2)], policies=[Payer(), Passive()])
    set_deck(g, "cc", ["Income tax refund"])
    g.send_to_jail(0)
    g.take_turn()
    assert not g.s.in_jail[0] and g.s.pos[0] == 17 and g.s.cash[0] == 1500 - 50 + 20


def test_get_out_of_jail_free_card_is_held_and_returned():
    g = game([(2, 5), (1, 2)], policies=[CardUser(), Passive()])
    set_deck(g, "chance", ["Get out of Jail free"])
    g.take_turn()  # 0 -> 7 (Chance) draws the card
    assert g.s.goojf[0] == ["chance"] and len(g.s.chance) == 15
    g.send_to_jail(0)
    g.s.current = 0
    g.take_turn()
    assert not g.s.in_jail[0] and g.s.goojf[0] == [] and len(g.s.chance) == 16
    assert g.s.cash[0] == 1500


# ------------------------------------------------------------------ rent
def test_double_rent_on_complete_unimproved_set():
    g = game([(1, 2)])
    give(g, 1, 1, 3)
    g.s.pos[0] = 38
    g.take_turn()
    assert g.s.cash[0] == 1500 + 200 - 4 and g.s.cash[1] == 1504


def test_house_rent():
    g = game([(1, 2)])
    give(g, 1, 1, 3)
    g.s.level[1] = g.s.level[3] = 1
    g.s.pos[0] = 38
    g.take_turn()
    assert g.s.cash[1] == 1510


def test_mortgaged_property_collects_no_rent():
    g = game([(2, 4)])
    give(g, 1, 6)
    g.s.mortgaged[6] = True
    g.take_turn()
    assert g.s.cash == [1500, 1500]


def test_station_rent_ignores_mortgaged_stations():
    g = game([(2, 3)])
    give(g, 1, 5, 15, 25)
    g.s.mortgaged[25] = True
    g.take_turn()
    assert g.s.cash[0] == 1450  # two live stations -> 50


def test_utility_rent_uses_dice():
    g = game([(2, 3)])
    give(g, 1, 12)
    g.s.pos[0] = 7
    g.take_turn()
    assert g.s.cash[0] == 1500 - 4 * 5
    g2 = game([(2, 3)])
    give(g2, 1, 12, 28)
    g2.s.pos[0] = 7
    g2.take_turn()
    assert g2.s.cash[0] == 1500 - 10 * 5


# ------------------------------------------------------------------ building
def test_even_build_and_mortgage_block():
    g = game([])
    give(g, 0, 16, 18, 19)
    assert g.can_build(0, 16)
    assert g.build(0, 16)
    assert not g.can_build(0, 16) and g.can_build(0, 18)
    g.s.level[16] = 0
    g.s.mortgaged[19] = True
    assert not g.can_build(0, 16)


def test_must_own_full_set_to_build():
    g = game([])
    give(g, 0, 16, 18)
    assert not g.can_build(0, 16)


def test_house_shortage_and_hotels():
    g = game([])
    give(g, 0, 16, 18, 19)
    g.s.bank_houses = 0
    assert not g.can_build(0, 16)
    g.s.level[16] = g.s.level[18] = g.s.level[19] = 4
    assert g.build(0, 16)
    assert g.s.level[16] == 5 and g.s.bank_houses == 4 and g.s.bank_hotels == 11


def test_selling_buildings_half_price_even_sell():
    g = game([])
    give(g, 0, 16, 18, 19)
    g.s.level[16], g.s.level[18], g.s.level[19] = 2, 2, 1
    g.s.bank_houses -= 5
    assert not g.can_sell_building(0, 19)
    assert g.sell_building(0, 16)
    assert g.s.cash[0] == 1550 and g.s.bank_houses == 28


def test_cannot_mortgage_with_buildings_in_group():
    g = game([])
    give(g, 0, 16, 18, 19)
    g.s.level[19] = 1
    assert not g.can_mortgage(0, 16)
    g.s.level[19] = 0
    assert g.mortgage(0, 16) and g.s.cash[0] == 1590
    assert g.unmortgage(0, 16) and g.s.cash[0] == 1590 - 99


# ------------------------------------------------------------------ auctions
def test_auction_second_price_plus_one():
    g = game([(2, 4)], policies=[Bidder(100), Bidder(250), Bidder(180)])
    g.take_turn()
    assert g.s.owner[6] == 1 and g.s.cash[1] == 1500 - 181


def test_auction_no_bids_stays_with_bank():
    g = game([(2, 4)])
    g.take_turn()
    assert g.s.owner[6] == BANK


# ------------------------------------------------------------------ cards
def test_go_back_three_onto_community_chest_chains():
    g = game([(2, 3)])
    set_deck(g, "chance", ["Go back three spaces"])
    set_deck(g, "cc", ["Bank error"])
    g.s.pos[0] = 31
    g.take_turn()
    assert g.s.pos[0] == 33 and g.s.cash[0] == 1700


def test_advance_card_collects_go_when_passing():
    g = game([(2, 3)])
    set_deck(g, "chance", ["Advance to Pall Mall"])
    g.s.pos[0] = 17  # -> 22 Chance -> Pall Mall (11), passing GO
    g.take_turn()
    assert g.s.cash[0] == 1700 and g.s.pos[0] == 11


def test_birthday_collects_from_each_player():
    g = game([(2, 3)], n=3)
    set_deck(g, "cc", ["It is your birthday"])
    g.s.pos[0] = 12
    g.take_turn()
    assert g.s.cash == [1520, 1490, 1490]


def test_repairs_charge_per_house_and_hotel():
    g = game([(2, 3)])
    set_deck(g, "chance", ["Make general repairs"])
    give(g, 0, 16, 18, 19, 21, 23, 24)
    for sq in (16, 18, 19):
        g.s.level[sq] = 2
    for sq in (21, 23, 24):
        g.s.level[sq] = 5
    g.s.pos[0] = 17
    g.take_turn()
    assert g.s.cash[0] == 1500 - (6 * 25 + 3 * 100)


def test_fine_or_chance_pays_fine_by_default():
    g = game([(2, 3)])
    set_deck(g, "cc", ["Pay a £10 fine"])
    g.s.pos[0] = 12
    g.take_turn()
    assert g.s.cash[0] == 1490


def test_fixed_deck_returns_card_to_bottom():
    g = game([(2, 5)])
    set_deck(g, "chance", ["Bank pays you dividend"])
    top = g.s.chance[0]
    g.take_turn()
    assert g.s.chance[-1] == top and len(g.s.chance) == 16


# ------------------------------------------------------------------ bankruptcy & trades
def test_bankrupt_to_player_transfers_assets_and_mortgage_fee():
    g = game([(1, 1)], n=3)
    give(g, 1, 37, 39)
    g.s.level[37] = g.s.level[39] = 5
    give(g, 0, 1)
    g.s.mortgaged[1] = True
    g.s.cash[0] = 10
    g.s.pos[0] = 37
    g.take_turn()
    assert not g.s.alive[0] and g.s.owner[1] == 1
    assert g.s.cash[1] == 1500 + 10 - 3


def test_bankrupt_to_bank_auctions_property():
    g = game([(1, 3)], policies=[Bidder(0), Bidder(120), Bidder(60)])
    give(g, 0, 6)
    g.s.cash[0] = 50
    g.take_turn()
    assert not g.s.alive[0]
    assert g.s.owner[6] == 1 and not g.s.mortgaged[6] and g.s.cash[1] == 1500 - 61


def test_last_player_standing_wins():
    g = game([(1, 1)], n=2)
    give(g, 1, 37, 39)
    g.s.level[37] = g.s.level[39] = 5
    g.s.cash[0] = 10
    g.s.pos[0] = 37
    g.take_turn()
    assert g.done and g.result().winner == 1


def test_trade_rules():
    g = game([])
    give(g, 0, 16)
    give(g, 1, 18, 19)
    g.s.mortgaged[16] = True
    assert g.execute_trade(0, 1, (16,), (), -100)  # 0 sells mortgaged Bow St for 100
    assert g.s.owner[16] == 1 and g.s.cash[0] == 1600 and g.s.cash[1] == 1500 - 100 - 9
    g.s.level[19] = 1
    assert not g.trade_is_valid(1, 0, (18,), (), 0)  # buildings in the group


class Always(Policy):
    def buy(self, g, p, sq):
        return True


def test_game_state_copy_is_independent():
    g = Game([Always(), Always()], seed=3)
    for _ in range(20):
        g.take_turn()
    snap = g.s.copy()
    g.take_turn()
    g.s.cash[0] += 1
    assert snap.cash[0] != g.s.cash[0] or snap.turn != g.s.turn


# ------------------------------------------------------------------ rule variants (methodology review, 2026-10-30)
def test_mortgaged_stations_count_only_in_the_variant():
    from monopoly_meta.engine import Rules
    for count_all, rent in ((False, 100), (True, 200)):
        g = game([(2, 3)], rules=Rules(mortgaged_count_for_rent=count_all))
        give(g, 1, 5, 15, 25, 35)
        g.s.mortgaged[15] = True
        g.take_turn()  # GO + 5 = King's Cross
        assert g.s.pos[0] == 5 and g.s.cash[0] == 1500 - rent


def test_building_between_turns_only_in_the_variant():
    from monopoly_meta.engine import Rules
    from monopoly_meta.policies import make_bot
    for any_time in (False, True):
        g = game([(4, 5)], policies=[Passive(), make_bot("balanced")], rules=Rules(build_any_time=any_time))
        give(g, 1, 1, 3)  # the browns
        g.take_turn()  # player 0 moves; player 1 may build only if building between turns is allowed
        built = g.s.level[1] + g.s.level[3]
        assert (built > 0) == any_time


def test_scarce_houses_are_auctioned_in_the_variant():
    from monopoly_meta.engine import Rules
    from monopoly_meta.policies import make_bot
    for auctions in (False, True):
        g = game([(4, 5)], n=3, policies=[Passive(), make_bot("balanced"), make_bot("balanced")],
                 rules=Rules(house_auctions=auctions))
        g.track_housing = True
        give(g, 1, 1, 3)
        give(g, 2, 6, 8, 9)
        g.s.bank_houses = 2
        g.take_turn()  # before player 0's management the two players both want more houses than the bank has
        assert g.contested_houses >= 1
        if auctions:
            assert g.house_auctions_held == 2 and g.s.bank_houses == 0
            assert g.s.level[1] + g.s.level[3] == 2 and g.s.cash[1] == 1500 - 2 * 100  # £50 houses at £100
        else:
            assert g.house_auctions_held == 0 and g.s.bank_houses == 2


def test_auctioned_houses_respect_the_bots_own_caps():
    """Review finding: a bot capped at three houses (max_level 3), or building three houses everywhere first
    (build_cap 3), must not bid for or place a house past that cap."""
    from monopoly_meta.policies import make_bot
    capped = make_bot({"name": "capped", "max_level": 3})
    first = make_bot({"name": "three first", "build_cap": 3})
    g = game([(4, 5)], n=3, policies=[Passive(), capped, first])
    give(g, 1, 6, 8, 9)  # light blues, at three houses: the capped bot wants nothing more
    for sq in (6, 8, 9):
        g.s.level[sq] = 3
    assert capped.house_bid(g, 1) == (0, 0, None)
    give(g, 2, 1, 3, 11, 13, 14)  # browns at three houses, pinks at one: houses go to the pinks first
    for sq, lv in ((1, 3), (3, 3), (11, 1), (13, 1), (14, 1)):
        g.s.level[sq] = lv
    want, limit, sq = first.house_bid(g, 2)
    assert want == 6 and sq in (11, 13, 14) and limit >= 100  # a pink house costs £100


def _auction_game(cash1=1500, cash2=1500, bank=2):
    """Player 1 owns the browns (£50 houses) and the dark blues (£200 houses), player 2 the light blues (£50), and
    the bank has fewer houses than they want: the review's case of bidders whose groups have different prices."""
    from monopoly_meta.engine import Rules
    from monopoly_meta.policies import make_bot
    g = game([(4, 5)], n=3, policies=[Passive(), make_bot("balanced"), make_bot("balanced")],
             rules=Rules(house_auctions=True))
    give(g, 1, 1, 3, 37, 39)
    give(g, 2, 6, 8, 9)
    g.s.cash[1], g.s.cash[2] = cash1, cash2
    g.s.bank_houses = bank
    g.house_auction_log = []
    return g


def test_house_auctions_never_charge_more_than_the_bid():
    """Review finding: the limit came from the cheapest group but the house could go on a dearer one, at a price
    above the limit. Now each bid names its square, and the price never exceeds the bid."""
    for cash1 in (1500, 400, 300, 230):  # a £150 reserve: rich enough for a dark-blue house, or only a brown one
        g = _auction_game(cash1=cash1)
        houses_before = g.s.bank_houses + sum(g.s.level[sq] for sq in g.ed.ownable if g.s.level[sq] < 5)
        money_before = sum(g.s.cash)
        g.take_turn()
        assert g.house_auction_log, cash1
        for buyer, sq, price, limit in g.house_auction_log:
            cost = g.ed.house_cost[g.ed.group_of[sq]]
            assert cost <= price <= limit, (cash1, buyer, sq, price, limit)
            assert g.s.owner[sq] == buyer and g.s.level[sq] >= 1
        assert min(g.s.cash) >= 0
        # every house is either in the bank or on the board, and the bank got exactly what was paid
        assert g.s.bank_houses + sum(g.s.level[sq] for sq in g.ed.ownable if g.s.level[sq] < 5) == houses_before
        spent = sum(price for _, _, price, _ in g.house_auction_log)
        assert money_before - sum(g.s.cash) >= spent  # auctions, plus anything built after them


def test_a_bid_is_for_the_house_it_names():
    from monopoly_meta.policies import make_bot
    g = _auction_game(cash1=1500)
    want, limit, sq = g.policies[1].house_bid(g, 1)
    assert sq in (1, 3, 37, 39) and limit >= g.ed.house_cost[g.ed.group_of[sq]]
    g.s.cash[1] = 300  # £150 above its reserve: no dark-blue house (£200), so the bid is for a brown one
    want, limit, sq = g.policies[1].house_bid(g, 1)
    assert sq in (1, 3) and 50 <= limit <= 150
    assert make_bot("balanced").house_bid(g, 0) == (0, 0, None)  # owns no set


# ------------------------------------------------------------------ 2026-10-31 review
def test_receiving_a_mortgaged_property_can_be_lifted_at_once_for_ten_percent():
    """Official rule: lift it at once for its mortgage + 10%, or pay the 10% now and keep it mortgaged. Without the
    choice the engine charged the 10% on receipt, so a bot that then lifted it paid 20%."""
    from monopoly_meta.engine import Rules
    from monopoly_meta.policies import make_bot
    for choice in (False, True):
        g = game([(4, 5)], policies=[make_bot("balanced"), make_bot("balanced")],
                 rules=Rules(mortgage_transfer_choice=choice))
        give(g, 1, 19)
        g.s.mortgaged[19] = True  # Vine Street: mortgage £100, lifting costs £110
        g.trade_log = []
        assert g.execute_trade(1, 0, (19,), (), 0)
        if choice:
            assert not g.s.mortgaged[19] and g.s.cash[0] == 1500 - 110
        else:
            assert g.s.mortgaged[19] and g.s.cash[0] == 1500 - 10
        assert g.trade_log == [(g.s.turn, 1, 0, (19,), (), 0)]


def test_lifting_at_once_never_leaves_the_fees_on_other_deeds_unpaid():
    """Two mortgaged deeds received together: the first is lifted only if the 10% on the second can still be paid."""
    from monopoly_meta.engine import Rules
    from monopoly_meta.policies import make_bot
    g = game([(4, 5)], policies=[make_bot("aggressive"), make_bot("balanced")],
             rules=Rules(mortgage_transfer_choice=True))
    give(g, 1, 16, 18)  # Bow Street and Marlborough Street: mortgages £90 each, lifting costs £99, the fee £9
    g.s.mortgaged[16] = g.s.mortgaged[18] = True
    g.s.cash[0] = 100  # lifting Bow Street (£99) would leave £1, short of Marlborough Street's £9
    assert g.execute_trade(1, 0, (16, 18), (), 0)
    assert g.s.cash[0] == 100 - 9 - 9 and g.s.mortgaged[16] and g.s.mortgaged[18]
    assert (g.mortgaged_received, g.lifted_on_receipt) == (2, 0)
    g = game([(4, 5)], policies=[make_bot("aggressive"), make_bot("balanced")],
             rules=Rules(mortgage_transfer_choice=True))
    give(g, 1, 16, 18)
    g.s.mortgaged[16] = g.s.mortgaged[18] = True
    g.s.cash[0] = 120  # enough to lift one and still pay the other's fee
    assert g.execute_trade(1, 0, (16, 18), (), 0)
    assert g.s.cash[0] == 120 - 99 - 9 and not g.s.mortgaged[16] and g.s.mortgaged[18]
    assert (g.mortgaged_received, g.lifted_on_receipt) == (2, 1)


def test_the_bankruptcy_that_ends_the_game_counts_no_mortgaged_deeds():
    """The winner inherits the loser's deeds as the game ends: no choice arises, so none is counted (or lifted)."""
    from monopoly_meta.engine import Rules
    from monopoly_meta.policies import make_bot
    g = game([(4, 5)], policies=[make_bot("balanced"), make_bot("balanced")],
             rules=Rules(mortgage_transfer_choice=True))
    give(g, 1, 19)
    g.s.mortgaged[19] = True
    g.bankrupt(1, 0)
    assert g.done and g.mortgaged_received == 0 and g.lifted_on_receipt == 0 and g.s.mortgaged[19]
    g = game([(4, 5)], policies=[make_bot("balanced") for _ in range(3)], rules=Rules(mortgage_transfer_choice=True))
    give(g, 1, 19)
    g.s.mortgaged[19] = True
    g.bankrupt(1, 0)  # two players left: the game goes on, so the choice arises
    assert not g.done and g.mortgaged_received == 1 and g.lifted_on_receipt == 1 and not g.s.mortgaged[19]


def test_alternative_points_schedules_for_five_and_six_survivors():
    from monopoly_meta.engine import GameResult, championship_points
    assert championship_points(5) == [16, 8, 4, 2, 1] and championship_points(4, "extend_four") == [19, 10, 5, 3]
    assert championship_points(5, "extend_four") == [19, 10, 5, 3, 1]
    assert championship_points(6, "rank_linear") == [19, 15, 11, 8, 4, 0]
    r = GameResult(winner=0, capped=True, turns=750, net_worth=[500, 400, 300, 200, 100], elimination_order=[],
                   stalemate="championship", points_schedule="extend_four")
    assert r.credit(0) == 19 / 28 and r.credit(4) == 1 / 28


def test_contested_hotels_are_counted():
    """Hotels in short supply aren't auctioned here; how often two players want more hotels than the bank has is
    counted (track_housing), to show how much that simplification matters."""
    from monopoly_meta.policies import make_bot
    g = game([(4, 5)], n=3, policies=[Passive(), make_bot("balanced"), make_bot("balanced")])
    give(g, 1, 1, 3)
    give(g, 2, 6, 8, 9)
    for sq in (1, 3, 6, 8, 9):
        g.s.level[sq] = 4
    g.s.bank_houses = 32 - 20
    g.s.bank_hotels = 1
    g.track_housing = True
    g.housing_check()
    assert g.contested_hotels == 1
