"""The v0.4 tactic genes: each is off by default, and each changes the decision it is meant to change."""
import random

import pytest

from helpers import set_deck
from monopoly_meta.engine import Game, Rules, championship_rules
from monopoly_meta.meta import BALANCED, to_spec, tournament_rules
from monopoly_meta.policies import HeuristicBot, expected_exposure, make_bot

OFF = dict(snipe=0.0, lock=0, leverage=0.0, jail_exposure=0.0, dodge=0.0, count_cards=False, leader_tax=1.0,
           endgame_rounds=0, endgame_reserve=0.0)
ALL_ON = dict(snipe=0.6, lock=10, leverage=0.8, jail_exposure=60.0, dodge=1.5, count_cards=True, leader_tax=2.0,
              endgame_rounds=10, endgame_reserve=300.0)


def game(bots, rules=None, seed=1):
    g = Game(bots, seed=seed, rules=rules or Rules())
    s = g.s
    s.owner = [-1] * len(s.owner)  # nobody owns anything yet; tests hand out property themselves
    return g


def sq(g, name):
    return g.ed.names.index(name)


def give(g, p, *names, level=0):
    for name in names:
        i = sq(g, name)
        g.s.owner[i] = p
        g.s.level[i] = level


@pytest.mark.parametrize("rules", [tournament_rules(4), championship_rules(4)], ids=["official", "championship"])
def test_tactics_off_play_exactly_as_before(rules):
    spec = to_spec(BALANCED, "b")
    for seed in range(6):
        plain = Game([make_bot(spec) for _ in range(4)], seed=seed, rules=rules).play()
        off = Game([make_bot({**spec, **OFF}) for _ in range(4)], seed=seed, rules=rules).play()
        assert plain == off


@pytest.mark.parametrize("rules", [tournament_rules(4), championship_rules(4)], ids=["official", "championship"])
def test_every_tactic_at_once_plays_valid_games(rules):
    rng = random.Random(3)
    for seed in range(12):
        bots = [make_bot({**to_spec(BALANCED, f"b{k}"), **(ALL_ON if rng.random() < 0.5 else {})}) for k in range(4)]
        r = Game(bots, seed=seed, rules=rules).play()
        assert 0 <= r.winner < 4 and r.turns > 0


def test_snipe_sends_a_property_to_auction_when_rivals_are_poor():
    bot = HeuristicBot(snipe=0.6)
    g = game([bot, HeuristicBot(), HeuristicBot()])
    mayfair = sq(g, "Mayfair")  # £400
    g.s.cash = [1500, 200, 150]
    assert not bot.buy(g, 0, mayfair)  # nobody can bid £240: an auction is cheaper
    assert HeuristicBot().buy(g, 0, mayfair)
    g.s.cash = [1500, 900, 150]
    assert bot.buy(g, 0, mayfair)  # one rival could bid it up, so buy at the printed price
    g.rules = Rules(auctions=False)
    g.s.cash = [1500, 200, 150]
    assert bot.buy(g, 0, mayfair)  # no auctions, nothing to snipe


def test_housing_lock_holds_four_houses_while_a_rival_needs_them():
    def hotels_built(bot, bank_houses):
        g = game([bot, HeuristicBot()])
        give(g, 0, "Bow Street", "Marlborough Street", "Vine Street", level=4)
        give(g, 1, "Strand", "Fleet Street", "Trafalgar Square")  # a rival set with no houses yet
        g.s.cash = [3000, 1500]
        g.s.bank_houses = bank_houses
        bot.manage(g, 0)
        return sum(g.s.level[sq(g, x)] == 5 for x in ("Bow Street", "Marlborough Street", "Vine Street"))

    assert hotels_built(HeuristicBot(), 4) == 3
    assert hotels_built(HeuristicBot(lock=8), 4) == 0  # bank short of houses: hold them
    assert hotels_built(HeuristicBot(lock=8), 20) == 3  # plenty in the bank: no point holding


def test_housing_lock_mortgages_before_selling_houses():
    def after_raising(bot):
        g = game([bot, HeuristicBot()])
        give(g, 0, "Bow Street", "Marlborough Street", "Vine Street", level=2)  # built set
        give(g, 0, "Old Kent Road", "Whitechapel Road")  # unbuilt set
        g.s.cash = [0, 1500]
        bot.raise_cash(g, 0, 60)
        houses = sum(g.s.level[sq(g, x)] for x in ("Bow Street", "Marlborough Street", "Vine Street"))
        browns = sum(g.s.mortgaged[sq(g, x)] for x in ("Old Kent Road", "Whitechapel Road"))
        return houses, browns

    assert after_raising(HeuristicBot()) == (4, 0)  # sells two houses (£50 each)
    assert after_raising(HeuristicBot(lock=8)) == (6, 2)  # keeps the houses, mortgages the browns


def test_leverage_mortgages_lone_properties_to_build_to_three_houses():
    def levels(bot):
        g = game([bot, HeuristicBot()])
        blues = ("The Angel Islington", "Euston Road", "Pentonville Road")  # houses cost £50
        give(g, 0, *blues)
        give(g, 0, "Mayfair", "Kings Cross Station")  # lone properties worth £300 mortgaged
        g.s.cash = [200, 1500]
        bot.manage(g, 0)
        return sorted(g.s.level[sq(g, x)] for x in blues), g.s.mortgaged[sq(g, "Mayfair")]

    assert levels(HeuristicBot()) == ([0, 0, 1], False)  # £200 less the £150 reserve: one house
    lv, mortgaged = levels(HeuristicBot(leverage=1.0))
    assert lv == [2, 2, 3] and mortgaged  # £300 raised: six more houses, still keeping the £150 reserve


def test_jail_exposure_stays_in_while_a_roll_is_dangerous():
    bot = HeuristicBot(jail_exposure=100.0, jail="short")
    g = game([bot, HeuristicBot()])
    g.s.cash = [1000, 1000]
    assert bot.jail_decision(g, 0) == "pay"  # nothing to fear: leave
    give(g, 1, "Bow Street", "Marlborough Street", "Vine Street", level=5)  # orange hotels, 6-9 squares away
    give(g, 1, "Pall Mall", "Whitehall", "Northumberland Avenue", level=5)
    assert expected_exposure(g, 0, g.ed.jail_square) >= 100
    assert bot.jail_decision(g, 0) == "roll"
    assert HeuristicBot(jail="short").jail_decision(g, 0) == "pay"  # without the tactic: the jail setting


def test_dodge_avoids_squares_with_a_dangerous_next_roll():
    rules = championship_rules(2)
    bot = HeuristicBot(dodge=1.0)
    g = game([bot, HeuristicBot()], rules=rules)
    give(g, 0, "Strand", "Fleet Street")  # our own squares: nothing to pay there
    give(g, 1, "Leicester Square", "Coventry Street", "Piccadilly", level=5)  # yellows, 3-8 squares on
    g.s.cash = [1000, 1000]
    g.s.pos[0] = 20
    options = [1, 2, 3]  # Strand, Chance, Fleet Street: the plain score can't tell them apart
    assert HeuristicBot().bus_choice(g, 0, options) == 1
    assert bot.bus_choice(g, 0, options) == 3  # Fleet Street: the yellows are hardest to reach from there


def test_count_cards_knows_what_the_next_chance_card_is():
    bot = HeuristicBot(count_cards=True)
    g = game([bot, HeuristicBot()])
    g.draws["chance"] = len(g.ed.chance)  # every card has been seen once: the order is known
    set_deck(g, "chance", ["Advance to GO"])
    assert bot.fine_or_chance(g, 0) == "chance"
    set_deck(g, "chance", ["Go to Jail"])
    g.s.owner[sq(g, "Mayfair")] = -1
    assert bot.fine_or_chance(g, 0) == "fine"
    assert HeuristicBot().fine_or_chance(g, 0) == "fine"  # without the tactic: take_chance decides


def test_leader_tax_asks_more_from_the_richest_player():
    me = HeuristicBot(leader_tax=2.0, ask_mult=2.0)
    g = game([me, HeuristicBot(), HeuristicBot()])
    give(g, 0, "Mayfair")
    give(g, 1, "Park Lane")
    mayfair = sq(g, "Mayfair")
    g.s.cash = [500, 3000, 500]  # player 1 leads
    assert not me.accept_trade(g, 0, 1, (mayfair,), (), 900)  # 2 x 2 x £400 asked of the leader
    assert HeuristicBot(ask_mult=2.0).accept_trade(g, 0, 1, (mayfair,), (), 900)
    g.s.cash = [3000, 500, 500]  # now we lead: the usual price
    assert me.accept_trade(g, 0, 1, (mayfair,), (), 900)


def test_endgame_sits_in_jail_and_keeps_its_reserve():
    rules = Rules(max_turns=200, stalemate="championship")
    bot = HeuristicBot(endgame_rounds=5, endgame_reserve=2000.0, jail="short")
    g = game([bot, HeuristicBot()], rules=rules)
    g.s.cash = [1500, 1500]
    mayfair = sq(g, "Mayfair")
    g.s.turn = 20
    assert bot.jail_decision(g, 0) == "pay" and bot.buy(g, 0, mayfair)
    g.s.turn = 195  # 2.5 own turns left each
    assert bot.jail_decision(g, 0) == "roll" and not bot.buy(g, 0, mayfair)


def test_protecting_buildings_is_separate_from_the_housing_lock():
    """The 2026-10-31 review: the lock setting also changed the order of raising cash. The two are now separate
    settings; an agent that only sets lock keeps both, as before."""
    from helpers import Passive, ScriptedGame

    def after_raising(**kw):
        g = ScriptedGame([Passive(), Passive()], [(4, 5)], seed=1)
        bot = make_bot({"name": "x", **kw})
        for sq in (1, 3, 6, 8, 9):  # the browns with a house each, and the light blues with none
            g.s.owner[sq] = 0
        g.s.level[1] = g.s.level[3] = 1
        g.s.bank_houses -= 2
        g.s.cash[0] = 0
        bot.raise_cash(g, 0, 100)
        return g.s.level[1] + g.s.level[3], sum(g.s.mortgaged[x] for x in (6, 8, 9))

    assert after_raising()[0] < 2                     # by default it sells the browns' houses first
    assert after_raising(protect=True) == (2, 2)      # protecting: mortgages two light blues, keeps both houses
    assert after_raising(lock=14) == after_raising(lock=14, protect=True)  # lock alone keeps both, as before
    assert after_raising(lock=14, protect=False) == after_raising()
