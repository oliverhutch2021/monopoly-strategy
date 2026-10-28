"""Test helpers: a game with scripted dice and a deterministic deck order."""
from collections import deque

from monopoly_meta.engine import Game
from monopoly_meta.policies import Policy


class ScriptedGame(Game):
    """Game whose dice come from a fixed list of (d1, d2) pairs (and Speed Die faces, if given)."""

    def __init__(self, policies, dice, speed=(), **kw):
        super().__init__(policies, **kw)
        self._dice = deque(dice)
        self._speed = deque(speed)

    def roll(self):
        return self._dice.popleft()

    def speed_roll(self):
        return self._speed.popleft()


class Passive(Policy):
    """Never buys, never bids, always rolls in jail: lets tests control everything."""
    name = "passive"

    def buy(self, g, p, sq):
        return False


class Buyer(Policy):
    name = "buyer"

    def buy(self, g, p, sq):
        return True


class Bidder(Policy):
    def __init__(self, bid):
        self.bid = bid

    def buy(self, g, p, sq):
        return False

    def max_bid(self, g, p, sq):
        return self.bid


def set_deck(game, deck, card_texts):
    """Put the named cards on top of a deck in the given order."""
    cards = game.ed.chance if deck == "chance" else game.ed.community_chest
    dq = game.s.chance if deck == "chance" else game.s.cc
    order = [next(i for i, c in enumerate(cards) if c.text.startswith(t)) for t in card_texts]
    rest = [i for i in dq if i not in order]
    dq.clear()
    dq.extend(order + rest)
