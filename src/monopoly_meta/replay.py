"""Record a game move by move, for the live board viewer (scripts/watch.py).

``RecordingGame`` plays exactly the same game as ``Game`` (same code, seeds and decisions); it only
writes down what happens: dice, moves, cards, purchases, auctions, payments, building, mortgages,
trades, jail and bankruptcies, plus the full position at the end of every turn. Every event carries
the players' cash at the moment it was written, so a viewer can show money changing hands as it
replays.
"""
from __future__ import annotations

import random

from .engine import Game, GameState, Rules
from .policies import make_bot


def win_chances(lineup: list, rules: Rules, state: GameState, n: int, seed: int | None = None) -> dict:
    """Each player's chance of winning from `state`, estimated by playing it out n times.

    The card decks are reshuffled in every playout, because nobody at the table knows their order.
    A game stopped by the time limit counts for the richest survivor when the scoring ranks the
    survivors ("championship", "networth"), and as "no winner" when it does not ("loss", "draw").
    """
    rng = random.Random(seed)
    wins = [0] * state.n_players
    none = 0
    for _ in range(n):
        g = Game([make_bot(spec) for spec in lineup], state=state, rules=rules, seed=rng.getrandbits(62),
                 reshuffle_decks=True)
        r = g.play()
        if r.capped and rules.stalemate in ("loss", "draw"):
            none += 1
        else:
            wins[r.winner] += 1
    return {"p": [w / n for w in wins], "none": none / n, "n": n}


class RecordingGame(Game):
    """A Game that keeps a turn-by-turn log in ``self.turns``."""

    def __init__(self, *args, keep_states: bool = False, **kw):
        super().__init__(*args, **kw)
        self.turns: list[dict] = []
        self._ev: list[dict] | None = None
        self._auctioned = False
        # full positions (GameState copies): states[0] before the first turn, states[t] after turn t,
        # for estimating each player's chances from any point of the game
        self.states = [self.s.copy()] if keep_states else None

    # ------------------------------------------------------------------ log helpers
    def _emit(self, **event) -> None:
        if self._ev is not None:
            event["cash"] = self.s.cash[:]
            self._ev.append(event)

    def snapshot(self) -> dict:
        s, ed = self.s, self.ed
        own = ed.ownable
        return {
            "turn": s.turn, "current": s.current,
            "cash": s.cash[:], "pos": s.pos[:], "alive": s.alive[:], "jail": s.in_jail[:],
            "goojf": [len(x) for x in s.goojf],
            "owner": [s.owner[sq] for sq in own], "level": [s.level[sq] for sq in own],
            "mortgaged": [s.mortgaged[sq] for sq in own],
            "bank_houses": s.bank_houses, "bank_hotels": s.bank_hotels,
            "worth": [self.net_worth(p) for p in range(s.n_players)],
        }

    def record(self) -> dict:
        """Play the game to the end and return the log (see scripts/watch.py for the format)."""
        start = self.snapshot()
        while not self.done:
            self.take_turn()
        r = self.result()
        return {
            "start": start, "turns": self.turns,
            "result": {"winner": r.winner, "capped": r.capped, "turns": r.turns, "net_worth": r.net_worth,
                       "elimination_order": r.elimination_order,
                       "credit": [r.credit(p) for p in range(self.s.n_players)]},
        }

    # ------------------------------------------------------------------ the turn
    def take_turn(self) -> None:
        p = self.s.current
        self._ev = []
        super().take_turn()
        self.turns.append({"p": p, "events": self._ev, "state": self.snapshot()})
        self._ev = None
        if self.states is not None:
            self.states.append(self.s.copy())

    def roll(self):
        d = super().roll()
        self._emit(e="roll", p=self.s.current, d=list(d))
        return d

    def speed_roll(self):
        v = super().speed_roll()
        self._emit(e="speed", p=self.s.current, v=v)
        return v

    # ------------------------------------------------------------------ movement
    def move(self, p, steps, dice=None):
        frm = self.s.pos[p]
        self._emit(e="move", p=p, frm=frm, to=(frm + steps) % self.n_sq, steps=steps,
                   go=frm + steps >= self.n_sq)
        super().move(p, steps, dice)

    def send_to_jail(self, p):
        self._emit(e="jail", p=p)
        super().send_to_jail(p)

    def use_goojf(self, p):
        self._emit(e="goojf", p=p)
        super().use_goojf(p)

    def apply_card(self, p, card, deck):
        pos = self.s.pos[p]
        self._emit(e="card", p=p, deck=deck, text=card.text, action=card.action)
        if card.action == "advance":
            self._emit(e="jump", p=p, to=card.to, fwd=True, go=card.to <= pos)
        elif card.action == "back":
            self._emit(e="jump", p=p, to=(pos - card.n) % self.n_sq, fwd=False, go=False)
        elif card.action == "back_to":
            self._emit(e="jump", p=p, to=card.to, fwd=False, go=False)
        super().apply_card(p, card, deck)

    # ------------------------------------------------------------------ buying and paying
    def offer(self, p, sq):
        self._auctioned = False
        super().offer(p, sq)
        if not self._auctioned and self.s.owner[sq] == p:
            self._emit(e="buy", p=p, sq=sq, price=self.ed.price[sq])

    def auction(self, sq):
        self._auctioned = True
        r = super().auction(sq)
        self._emit(e="auction", sq=sq, winner=None if r is None else r[0], price=None if r is None else r[1])
        return r

    def charge(self, p, amount, creditor=None, to_pot=True):
        to_player = amount > 0 and creditor is not None and self.s.alive[creditor]
        ok = super().charge(p, amount, creditor, to_pot)
        if ok and to_player:
            self._emit(e="pay", p=p, to=creditor, amount=amount)
        return ok

    def _pay_bank(self, p, amount, to_pot=True):
        super()._pay_bank(p, amount, to_pot)
        self._emit(e="pay", p=p, to=-1, amount=amount)

    def bankrupt(self, p, creditor):
        self._emit(e="bankrupt", p=p, to=-1 if creditor is None else creditor)
        super().bankrupt(p, creditor)

    # ------------------------------------------------------------------ building, mortgages, trades
    def build(self, p, sq):
        ok = super().build(p, sq)
        if ok:
            self._emit(e="build", p=p, sq=sq, level=self.s.level[sq])
        return ok

    def sell_building(self, p, sq):
        ok = super().sell_building(p, sq)
        if ok:
            self._emit(e="sell", p=p, sq=sq, level=self.s.level[sq])
        return ok

    def mortgage(self, p, sq):
        ok = super().mortgage(p, sq)
        if ok:
            self._emit(e="mortgage", p=p, sq=sq)
        return ok

    def unmortgage(self, p, sq):
        ok = super().unmortgage(p, sq)
        if ok:
            self._emit(e="unmortgage", p=p, sq=sq)
        return ok

    def execute_trade(self, a, b, a_gives=(), b_gives=(), cash_a_to_b=0):
        ok = super().execute_trade(a, b, a_gives, b_gives, cash_a_to_b)
        if ok:
            self._emit(e="trade", a=a, b=b, a_gives=list(a_gives), b_gives=list(b_gives), money=cash_a_to_b)
        return ok
