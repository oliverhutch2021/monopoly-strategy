"""Championship mode: Speed Die faces and tournament rule tweaks, with scripted dice."""
import pytest

from monopoly_meta.engine import BANK, BUS, MR_MONOPOLY, Rules

from helpers import Buyer, Passive, ScriptedGame


def game(dice, speed=(), policies=None, n=2, passed_go=True, **rules):
    g = ScriptedGame(policies or [Passive() for _ in range(n)], dice, speed=speed, seed=1,
                     rules=Rules(speed_die=True, **rules))
    g.s.passed_go = [passed_go] * len(g.policies)
    return g


def test_speed_die_unused_before_first_lap():
    g = game([(1, 2)], speed=[], passed_go=False)  # speed_roll would raise if called
    g.take_turn()
    assert g.s.pos[0] == 3


def test_passing_go_switches_the_speed_die_on():
    g = game([(1, 2)], passed_go=False)
    g.s.pos[0] = 38
    g.take_turn()
    assert g.s.passed_go[0] and g.s.cash[0] == 1700


def test_number_face_adds_to_the_dice():
    g = game([(1, 2)], speed=[3])
    g.take_turn()
    assert g.s.pos[0] == 6


class BusPicker(Passive):
    def __init__(self, pick):
        self.pick, self.seen = pick, None

    def bus_choice(self, g, p, options):
        self.seen = options
        return self.pick


def test_bus_lets_you_choose_one_die_or_both_and_counts_zero_for_utilities():
    bot = BusPicker(2)
    g = game([(2, 5)], speed=[BUS], policies=[bot, Passive()])
    g.s.pos[0] = 10
    g.s.owner[12] = 1
    g.take_turn()
    assert bot.seen == [2, 5, 7] and g.s.pos[0] == 12
    assert g.s.cash[0] == 1500 - 4 * 7  # utility rent uses the number dice only


def test_mr_monopoly_moves_on_to_the_next_unowned_property():
    g = game([(1, 2)], speed=[MR_MONOPOLY], policies=[Buyer(), Passive()])
    g.take_turn()
    assert g.s.owner[3] == 0 and g.s.owner[5] == 0 and g.s.pos[0] == 5


def test_mr_monopoly_with_nothing_unowned_goes_to_the_next_rent():
    g = game([(1, 2)], speed=[MR_MONOPOLY])
    for sq in g.ed.ownable:
        g.s.owner[sq] = 1
    g.s.mortgaged[3] = g.s.mortgaged[5] = True
    g.take_turn()
    assert g.s.pos[0] == 6 and g.s.cash[0] == 1500 - 12  # skips mortgaged squares; Angel at set rent


def test_mr_monopoly_stays_put_if_no_rent_is_possible():
    g = game([(1, 2)], speed=[MR_MONOPOLY])
    for sq in g.ed.ownable:
        g.s.owner[sq] = 1
        g.s.mortgaged[sq] = True
    g.take_turn()
    assert g.s.pos[0] == 3


class Teleporter(Passive):
    def triple_destination(self, g, p):
        return 39


def test_triple_moves_anywhere_and_ends_the_turn():
    g = game([(2, 2)], speed=[2], policies=[Teleporter(), Passive()])
    g.take_turn()  # a second roll would raise: triples give no extra throw
    assert g.s.pos[0] == 39


def test_triple_after_two_doubles_is_a_third_double():
    g = game([(1, 1), (3, 3), (2, 2)], speed=[3, 2, 2])
    g.s.pos[0] = 10
    g.take_turn()
    assert g.s.in_jail[0] and g.s.pos[0] == 10


def test_jail_rolls_ignore_the_speed_die():
    g = game([(1, 2)], speed=[])
    g.send_to_jail(0)
    g.take_turn()
    assert g.s.in_jail[0] and g.s.jail_turns[0] == 1


def test_no_bid_auction_goes_to_richest_player_for_a_pound():
    g = game([(2, 4)], passed_go=False, no_bid_to_richest=True)
    g.s.cash[1] = 2000
    g.take_turn()
    assert g.s.owner[6] == 1 and g.s.cash[1] == 1999


def test_no_trades_when_two_players_are_left():
    g = game([], n=3, no_trades_heads_up=True)
    g.s.owner[16] = 0
    assert g.trade_is_valid(0, 1, (16,), (), -100)
    g.s.alive[2] = False
    assert not g.trade_is_valid(0, 1, (16,), (), -100)


@pytest.mark.parametrize("n", [2, 4, 6])
def test_default_bots_play_full_championship_games(n):
    from monopoly_meta.engine import Game, championship_rules
    from monopoly_meta.policies import make_bot
    for seed in range(5):
        r = Game([make_bot("balanced") for _ in range(n)], seed=seed, rules=championship_rules(n)).play()
        assert 0 <= r.winner < n
        assert sum(r.credit(p) for p in range(n)) > 0 or r.capped
    assert BANK == -1
