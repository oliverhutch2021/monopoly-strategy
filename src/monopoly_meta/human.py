"""Playing against the bots yourself (`make play`): one seat asks a person instead of a policy.

A PlaySession runs a game in its own thread. Your seat is a HumanPolicy: whenever the engine wants a
decision from it (buy or pass, an auction bid, jail, the fine-or-Chance card, the Speed Die, building and
mortgages, trades, raising cash), it posts a question and waits for your answer. Meanwhile everything that
has happened so far can be read as a stream of events (the viewer's replay format, plus a "turn_end" with
the position after each turn), so the board shows the bots' moves as they happen.

Nothing about the rules or the bots changes: the engine asks your seat at exactly the points where it asks
a bot, and every action you take goes through the same checks a bot's does (can_build, trade_is_valid,
...). A trade you propose is put to the bot, which answers with its own accept_trade. The engine lets a
player build, mortgage and trade once per turn, after moving (manage), and you get the same.
"""
from __future__ import annotations

import queue
import threading
import traceback

from .engine import BANK, Rules
from .policies import Policy, default_liquidation, make_bot
from .replay import RecordingGame

MAX_PROPOSALS = 8  # trade proposals you may make in one turn (the bots make at most one)


class Abandoned(Exception):
    """The session was closed while the game waited for you."""


class LiveGame(RecordingGame):
    """A RecordingGame that also hands every event to `sink` as it happens, and a "turn_end" event with
    the position after each turn."""

    def __init__(self, *args, sink=None, **kw):
        super().__init__(*args, **kw)
        self.sink = sink

    def _emit(self, **event) -> None:
        super()._emit(**event)
        if self._ev is not None and self.sink is not None:
            self.sink(self._ev[-1])

    def take_turn(self) -> None:
        super().take_turn()
        t = self.turns[-1]
        if self.sink is not None:
            self.sink({"e": "turn_end", "turn": len(self.turns), "p": t["p"], "state": t["state"]})


class HumanPolicy(Policy):
    """Your seat: every decision is a question to you (PlaySession.ask)."""
    name = "you"

    def __init__(self, session: "PlaySession"):
        self.session = session

    def buy(self, g, p, sq) -> bool:
        return bool(self.session.ask("buy", sq=sq, price=g.ed.price[sq]))

    def max_bid(self, g, p, sq) -> int:
        a = self.session.ask("bid", sq=sq, price=g.ed.price[sq])
        return max(0, min(_int(a, 0), g.s.cash[p]))

    def jail_decision(self, g, p) -> str:
        s, ed = g.s, g.ed
        options = ["roll"] + (["pay"] if s.cash[p] >= ed.jail_fine else []) + (["card"] if s.goojf[p] else [])
        a = self.session.ask("jail", options=options, fine=ed.jail_fine, tries=s.jail_turns[p],
                             max_tries=ed.max_jail_turns)
        return a if a in options else "roll"

    def fine_or_chance(self, g, p) -> str:
        return "chance" if self.session.ask("fine_or_chance") == "chance" else "fine"

    def bus_choice(self, g, p, options) -> int:
        here = g.s.pos[p]
        a = self.session.ask("bus", options=[{"steps": st, "sq": (here + st) % g.n_sq} for st in options])
        a = _int(a, None)
        return a if a in options else max(options)

    def triple_destination(self, g, p) -> int:
        a = _int(self.session.ask("triple"), None)
        return a if a is not None and 0 <= a < g.n_sq else g.s.pos[p]

    def accept_trade(self, g, me, other, give, get, cash_in) -> bool:
        return bool(self.session.ask("trade_offer", by=other, give=list(give), get=list(get), money=cash_in))

    def raise_cash(self, g, p, target) -> None:
        self.session.act(g, p, "raise", target)

    def manage(self, g, p) -> None:
        self.session.act(g, p, "manage")


def _int(x, default):
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


class PlaySession:
    """One game between you (seat `seat`) and bots (`lineup`, bot specs; lineup[seat] is ignored)."""

    def __init__(self, lineup: list, seat: int, rules: Rules, seed: int, start: bool = True):
        self.seat, self.lineup, self.rules, self.seed = seat, lineup, rules, seed
        self.events: list[dict] = []
        self.question: dict | None = None
        self.qid = 0
        self.over = False
        self.result: dict | None = None
        self.error: str | None = None
        self.closed = False
        self.cond = threading.Condition()
        self._answers: queue.Queue = queue.Queue()
        policies = [HumanPolicy(self) if i == seat else make_bot(spec) for i, spec in enumerate(lineup)]
        self.g = LiveGame(policies, seed=seed, rules=rules, keep_states=True, sink=self._sink)
        self.start_state = self.g.snapshot()
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"play-{seed}")
        if start:
            self.start()

    # ------------------------------------------------------------------ the game thread
    def start(self) -> None:
        self.start_state = self.g.snapshot()
        self.thread.start()

    def _run(self) -> None:
        g = self.g
        try:
            while not g.done:
                g.take_turn()
            r = g.result()
            self.result = {"winner": r.winner, "capped": r.capped, "turns": r.turns, "net_worth": r.net_worth,
                           "elimination_order": r.elimination_order,
                           "credit": [r.credit(p) for p in range(g.s.n_players)]}
        except Abandoned:
            pass
        except Exception:  # report it to the page rather than dying quietly
            self.error = traceback.format_exc(limit=6)
        finally:
            with self.cond:
                self.over = True
                self.question = None
                self.cond.notify_all()

    def _sink(self, ev: dict) -> None:
        with self.cond:
            self.events.append(ev)
            self.cond.notify_all()

    def ask(self, kind: str, **info):
        """Post a question and wait for its answer (called from the game thread)."""
        with self.cond:
            if self.closed:
                raise Abandoned
            self.qid += 1
            qid = self.qid
            s = self.g.s
            self.question = {"id": qid, "kind": kind, "at": len(self.events), "cash": s.cash[self.seat],
                             "state": self.g.snapshot(), **info}
            self.cond.notify_all()
        while True:
            try:
                got, value = self._answers.get(timeout=0.5)
            except queue.Empty:
                if self.closed:
                    raise Abandoned
                continue
            if self.closed:
                raise Abandoned
            if got == qid:
                break
        with self.cond:
            self.question = None
        return value

    # ------------------------------------------------------------------ building, mortgages and trades
    def act(self, g, p: int, mode: str, target: int = 0) -> None:
        """Your manage phase ("manage") or raising cash you owe ("raise"): one action per answer, each
        checked by the engine, until you say you're done (or, raising cash, until you have enough)."""
        note, proposals = "", 0
        while True:
            if mode == "raise" and g.s.cash[p] >= target:
                return
            a = self.ask(mode, target=target, note=note, assets=self.assets(g, p, mode),
                         trading=self.trading(g, p) if mode == "manage" else None,
                         proposals_left=MAX_PROPOSALS - proposals)
            a = a if isinstance(a, dict) else {}
            act, sq = a.get("act"), _int(a.get("sq"), -1)
            note = ""
            if act == "done":
                return
            if act == "auto" and mode == "raise":
                default_liquidation(g, p, target)
                return
            if act == "trade" and mode == "manage":
                if proposals >= MAX_PROPOSALS:
                    note = "That's enough offers for one turn."
                    continue
                proposals += 1
                note = self.propose(g, p, a)
                continue
            ok = False
            if 0 <= sq < g.n_sq:
                if act == "build" and mode == "manage":
                    ok = g.build(p, sq)
                elif act == "sell":
                    ok = g.sell_building(p, sq)
                elif act == "mortgage":
                    ok = g.mortgage(p, sq)
                elif act == "unmortgage" and mode == "manage":
                    ok = g.unmortgage(p, sq)
            if not ok:
                note = "That isn't allowed right now."

    def assets(self, g, p: int, mode: str) -> list[dict]:
        """Your properties and what you may do with each, as the engine sees it."""
        s, ed = g.s, g.ed
        out = []
        for sq in ed.ownable:
            if s.owner[sq] != p:
                continue
            gi = ed.group_of[sq]
            out.append({
                "sq": sq, "level": s.level[sq], "mortgaged": s.mortgaged[sq],
                "house_cost": ed.house_cost[gi] if gi >= 0 else 0,
                "mortgage_value": ed.mortgage_value(sq), "unmortgage_cost": ed.unmortgage_cost(sq),
                "build": mode == "manage" and g.can_build(p, sq),
                "sell": g.can_sell_building(p, sq),
                "mortgage": g.can_mortgage(p, sq),
                "unmortgage": mode == "manage" and s.mortgaged[sq] and s.cash[p] >= ed.unmortgage_cost(sq),
            })
        return out

    def trading(self, g, p: int) -> dict:
        """Who you can trade with and which properties may change hands (no buildings in their colour group)."""
        s, ed = g.s, g.ed
        if g.rules.no_trades_heads_up and sum(s.alive) <= 2:
            return {"closed": "No trades once only two players are left (championship rules)."}
        tradable = [sq for sq in ed.ownable if s.owner[sq] != BANK and not g.group_has_buildings(ed.group_of[sq])]
        return {"players": [q for q in range(s.n_players) if q != p and s.alive[q]], "tradable": tradable}

    def propose(self, g, p: int, a: dict) -> str:
        """Put your offer to the bot; it answers with its own accept_trade."""
        q = _int(a.get("to"), -1)
        give = sorted({_int(x, -1) for x in a.get("give") or []})
        get = sorted({_int(x, -1) for x in a.get("get") or []})
        cash = _int(a.get("cash"), 0)  # what you pay them (negative: they pay you)
        s = g.s
        if not (0 <= q < s.n_players) or q == p or any(not 0 <= x < g.n_sq for x in (*give, *get)):
            return "That offer doesn't make sense."
        if not (give or get):
            return "Put at least one property in the offer."
        if not g.trade_is_valid(p, q, tuple(give), tuple(get), cash):
            if g.rules.no_trades_heads_up and sum(s.alive) <= 2:
                return "No trades once only two players are left."
            if any(g.group_has_buildings(g.ed.group_of[x]) for x in (*give, *get)):
                return "Sell the buildings in a colour group before trading any of it."
            return "That offer isn't possible: check who owns what, and the cash."
        yes = bool(g.policies[q].accept_trade(g, q, p, tuple(get), tuple(give), cash))
        g._emit(e="proposal", a=p, b=q, a_gives=give, b_gives=get, money=cash, accepted=yes)
        if yes:
            g.execute_trade(p, q, tuple(give), tuple(get), cash)
        return "accepted" if yes else "declined"

    # ------------------------------------------------------------------ the page's side
    def poll(self, since: int, wait: float = 1.0) -> dict:
        """Events after `since`, the question waiting for you (if any) and whether the game is over. Waits
        up to `wait` seconds for something new."""
        with self.cond:
            if len(self.events) <= since and self.question is None and not self.over:
                self.cond.wait(timeout=wait)
            return {"events": self.events[since:], "next": len(self.events), "question": self.question,
                    "over": self.over, "result": self.result, "error": self.error}

    def answer(self, qid: int, value) -> bool:
        with self.cond:
            current = self.question["id"] if self.question else None
        if current != qid:
            return False
        self._answers.put((qid, value))
        return True

    def close(self) -> None:
        """Stop the game (a new one is starting): the game thread ends at its next question."""
        with self.cond:
            self.closed = True
            self.cond.notify_all()
        self._answers.put((None, None))
