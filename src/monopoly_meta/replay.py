"""Record a game move by move, for the live board viewer (scripts/watch.py).

``RecordingGame`` plays exactly the same game as ``Game`` (same code, seeds and decisions); it only
writes down what happens: dice, moves, cards, purchases, auctions, payments, building, mortgages,
trades, jail and bankruptcies, plus the full position at the end of every turn. Every event carries
the players' cash at the moment it was written, so a viewer can show money changing hands as it
replays.
"""
from __future__ import annotations

import random
import time

import numpy as np

from .engine import Game, GameState, Rules
from .policies import make_bot


def _won(r, p: int, rules: Rules) -> float:
    """1 if p won the game: outright, or (when the scoring ranks survivors) on net worth at the time limit."""
    if r.capped and rules.stalemate in ("loss", "draw"):
        return 0.0
    return float(r.winner == p)


def _auction_among_others(g: Game, sq: int, p: int):
    """Auction sq as the engine does (Game.auction), but without player p bidding; with no bids it stays
    with the bank. Returns (winner, price) or None."""
    s = g.s
    best, best_bid, second = None, 0, 0
    for i in range(s.n_players):
        q = (s.current + i) % s.n_players
        if q == p or not s.alive[q]:
            continue
        b = min(int(g.policies[q].max_bid(g, q, sq)), s.cash[q])
        if b > best_bid:
            second, best_bid, best = best_bid, b, q
        elif b > second:
            second = b
    if best is None or best_bid < g.rules.min_bid:
        return None
    price = max(g.rules.min_bid, min(best_bid, second + 1))
    s.cash[best] -= price
    s.owner[sq] = best
    return best, price


def _resolve(lineup: list, rules: Rules, state: GameState, p: int, sq: int, how: str):
    """The position at the end of p's turn after p's decision on unowned sq:
      "buy"    p pays the printed price;
      "pass"   p declines and it is auctioned with everyone bidding, p included (the real alternative);
      "other"  p does not get it: auctioned among the other players (stays with the bank if no one bids).
    The rest of the turn is p's end-of-turn management; an extra roll after doubles is not replayed (a
    small approximation). Returns (state, result if that ended the game else None, (winner, price) of
    any auction).
    """
    g = Game([make_bot(spec) for spec in lineup], state=state, rules=rules, seed=0)
    s = g.s
    sold = None
    if how == "buy":
        s.cash[p] -= g.ed.price[sq]
        s.owner[sq] = p
    elif how == "pass":
        sold = g.auction(sq) if rules.auctions else None
    else:
        sold = _auction_among_others(g, sq, p) if rules.auctions else None
    if not g.done and s.alive[p]:
        g.policies[p].manage(g, p)
    if not g.done:
        g._end_turn()
    return g.s, (g.result() if g.done else None), sold


def buy_value(lineup: list, rules: Rules, state: GameState, p: int, sq: int, n: int = 200,
              seed: int | None = None, horizon_rounds: int = 10, budget_s: float | None = None,
              n_min: int = 16) -> dict:
    """What property sq is worth to player p right now, as p stands on it deciding whether to buy.

    Plays the rest of the game out n times from two positions, with the same dice and reshuffled decks
    in both (paired): p owns it, having paid the printed price; or p does not get it, so it goes to
    whichever other player wins the auction (or stays with the bank). Reports
      * p's chance of winning either way, and the difference: what owning it adds to p's chance of
        winning (a game stopped by the time limit is scored as the rules score it);
      * p's net worth `horizon_rounds` rounds later either way. Buying swaps cash for a property counted
        at its price, so the difference is what owning it earns over that time (rent collected, rent not
        paid to the other owner); price + difference is its money value to p over that horizon.
    Both come with standard errors from the paired playouts. Also reports, without playouts, what would
    really happen if p declined (the auction with p bidding too). The rest of the game is played by the
    same players, so these are values when these players play on the way they do.

    budget_s caps the CPU time: playouts stop once it is spent (after at least n_min pairs), so long
    games get fewer playouts and wider error bars rather than taking longer.
    """
    price = Game([make_bot(spec) for spec in lineup], state=state, rules=rules, seed=0).ed.price[sq]
    rng = random.Random(seed)
    seeds = [rng.getrandbits(62) for _ in range(n)]
    horizon = horizon_rounds * sum(state.alive)
    sold, start = {}, {}
    for how in ("buy", "other"):
        st, done, sold[how] = _resolve(lineup, rules, state, p, sq, how)
        start[how] = (st, done)

    def playout(how, sd):
        st, done = start[how]
        if done is not None:
            return _won(done, p, rules), done.net_worth[p]
        g = Game([make_bot(spec) for spec in lineup], state=st, rules=rules, seed=sd, reshuffle_decks=True)
        stop = g.s.turn + horizon
        while not g.done and g.s.turn < stop:
            g.take_turn()
        worth = g.net_worth(p)
        return _won(g.play(), p, rules), worth

    t0 = time.process_time()
    pairs = []
    for sd in seeds:  # both branches on the same seed, so every finished pair is a fair comparison
        pairs.append((playout("buy", sd), playout("other", sd)))
        if budget_s is not None and len(pairs) >= n_min and time.process_time() - t0 > budget_s:
            break
    a = np.array(pairs)  # pairs x branch x (win, worth)
    sold["pass"] = _resolve(lineup, rules, state, p, sq, "pass")[2]
    d_win = a[:, 0, 0] - a[:, 1, 0]
    d_worth = a[:, 0, 1] - a[:, 1, 1]
    n = len(pairs)

    def se(x):
        return float(x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else None

    def auction(a):
        return None if a is None else {"winner": a[0], "price": a[1]}

    return {
        "sq": sq, "player": p, "price": price, "n": n, "playouts": 2 * n, "horizon_rounds": horizon_rounds,
        "p_own": float(a[:, 0, 0].mean()), "p_other": float(a[:, 1, 0].mean()),
        "cpu_seconds": round(time.process_time() - t0, 3),
        "gain": float(d_win.mean()), "gain_se": se(d_win),
        "value": float(price + d_worth.mean()), "value_se": se(d_worth),
        "other_owner": auction(sold["other"]), "if_passed": auction(sold["pass"]),
    }


def win_chances(lineup: list, rules: Rules, state: GameState, n: int, seed: int | None = None,
                budget_s: float | None = None, n_min: int = 16) -> dict:
    """Each player's chance of winning from `state`, estimated by playing it out n times.

    The card decks are reshuffled in every playout, because nobody at the table knows their order.
    budget_s caps the CPU time (after at least n_min playouts).
    A game stopped by the time limit counts for the richest survivor when the scoring ranks the
    survivors ("championship", "networth"), and as "no winner" when it does not ("loss", "draw").
    """
    rng = random.Random(seed)
    wins = [0] * state.n_players
    none = done = 0
    t0 = time.process_time()
    for _ in range(n):
        g = Game([make_bot(spec) for spec in lineup], state=state, rules=rules, seed=rng.getrandbits(62),
                 reshuffle_decks=True)
        r = g.play()
        if r.capped and rules.stalemate in ("loss", "draw"):
            none += 1
        else:
            wins[r.winner] += 1
        done += 1
        if budget_s is not None and done >= n_min and time.process_time() - t0 > budget_s:
            break
    return {"p": [w / done for w in wins], "none": none / done, "n": done}


class RecordingGame(Game):
    """A Game that keeps a turn-by-turn log in ``self.turns``."""

    def __init__(self, *args, keep_states: bool = False, **kw):
        super().__init__(*args, **kw)
        self.turns: list[dict] = []
        self._ev: list[dict] | None = None
        self._auctioned = False
        # full positions (GameState copies): states[0] before the first turn, states[t] after turn t,
        # for estimating each player's chances from any point of the game; and the position at every
        # buying decision, for valuing the property there (buy_value)
        self.states = [self.s.copy()] if keep_states else None
        self.decisions: list[dict] | None = [] if keep_states else None

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
        """p landed on unowned sq. If p can afford it, p decides (then "buy", or an "auction" if p
        declines); a recording that keeps states also keeps this position, so the property can be
        valued for p exactly as p stood deciding (buy_value)."""
        price = self.ed.price[sq]
        afford = self.s.cash[p] >= price
        k = None
        if afford and self.decisions is not None:
            k = len(self.decisions)
            self.decisions.append({"p": p, "sq": sq, "turn": len(self.turns), "state": self.s.copy()})
        self._emit(e="offer", p=p, sq=sq, price=price, afford=afford, k=k)
        self._auctioned = False
        super().offer(p, sq)
        if not self._auctioned and self.s.owner[sq] == p:
            self._emit(e="buy", p=p, sq=sq, price=price)

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
