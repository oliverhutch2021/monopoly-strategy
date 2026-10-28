"""Regression tests for defects found in code review."""
from monopoly_meta.engine import Game, Rules
from monopoly_meta.policies import HeuristicBot, make_bot

from helpers import Passive, ScriptedGame, set_deck


def test_birthday_stops_when_drawer_goes_bankrupt():
    # p1 cannot pay and goes bankrupt to p0; p0 then cannot pay the 10% interest on the
    # inherited mortgages and goes bankrupt to the bank. p2 must not pay a dead player.
    g = ScriptedGame([Passive(), Passive(), Passive()], dice=[(1, 1)], rules=Rules(auctions=False))
    s = g.s
    s.cash = [0, 5, 5]
    for sq in (37, 39):
        s.owner[sq] = 1
        s.mortgaged[sq] = True
    set_deck(g, "cc", ["It is your birthday"])
    g.take_turn()
    assert not s.alive[0] and not s.alive[1] and s.alive[2]
    assert s.cash[0] == 0 and s.cash[2] == 5
    assert g.done and g.result().winner == 2


def test_result_never_crashes_when_everyone_is_out():
    g = Game([Passive(), Passive()], seed=1)
    g.s.alive = [False, False]
    g.s.elimination_order = [1, 0]
    assert g.result().winner == 0


def test_three_house_bot_respects_its_cap():
    bot = HeuristicBot(build_cap=3, build_reserve=0, trades=False)
    g = Game([bot, Passive()], seed=1)
    s = g.s
    for sq in (1, 3, 16, 18, 19):
        s.owner[sq] = 0
    s.level[1] = s.level[3] = 3
    s.bank_houses -= 6
    s.cash[0] = 60  # can afford one more brown house but no orange house
    bot.manage(g, 0)
    assert s.level[1] == 3 and s.level[3] == 3


def test_capped_game_hands_turn_to_next_player():
    g = Game([Passive(), Passive()], seed=1, rules=Rules(max_turns=1))
    g.take_turn()
    assert g.done and g.capped and g.s.current == 1


def test_mortgage_interest_does_not_feed_free_parking_pot():
    g = Game([Passive(), Passive()], seed=1, rules=Rules(free_parking_jackpot=True))
    g.s.owner[39] = 0
    g.s.mortgaged[39] = True
    assert g.execute_trade(0, 1, (39,), (), -100)
    assert g.s.pot == 0


class Recorder(Passive):
    def __init__(self, jail="roll"):
        self.jail = jail

    def jail_decision(self, g, p):
        return self.jail


def _first_throws(game, player, turns):
    seen = []
    orig = game.roll

    def roll():
        d = orig()
        if game.s.current == player and len(seen) < turns:
            seen.append(d)
        return d
    game.roll = roll
    while len(seen) < turns and not game.done:
        before = len(seen)
        game.take_turn()
        if len(seen) > before:
            seen[before + 1:] = []  # keep only the first throw of each of p's turns
    return seen


def test_dice_stay_aligned_when_another_player_rolls_differently():
    # Arm A: player 0 is jailed and rolls for doubles (1 throw per turn).
    # Arm B: player 0 pays out and takes normal turns (1-3 throws per turn).
    a = Game([Recorder("roll"), make_bot("balanced")], seed=9)
    b = Game([Recorder("pay"), make_bot("balanced")], seed=9)
    a.send_to_jail(0)
    b.send_to_jail(0)
    assert _first_throws(a, 1, 5) == _first_throws(b, 1, 5)
