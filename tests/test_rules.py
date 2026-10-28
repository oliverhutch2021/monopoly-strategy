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
