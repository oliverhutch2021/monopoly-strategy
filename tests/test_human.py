"""Playing against the bots yourself: the human seat asks questions, the game streams its events, and every
action goes through the engine's own checks."""
import threading
import time

import pytest

from monopoly_meta.engine import BANK, championship_rules
from monopoly_meta.human import MAX_PROPOSALS, PlaySession
from monopoly_meta.meta import BALANCED, to_spec, tournament_rules

BOT = to_spec(dict(BALANCED, reserve=150.0), "bot")


def scripted(session: PlaySession, asked: list, timeout: float = 60.0) -> None:
    """A simple player answering from a thread: buys what leaves £200, bids half price, builds where it can."""
    seen, built = 0, 0
    t0 = time.time()
    while not session.over and time.time() - t0 < timeout:
        r = session.poll(seen, wait=0.2)
        seen = r["next"]
        q = r["question"]
        if q is None:
            continue
        asked.append(q["kind"])
        k = q["kind"]
        if k == "buy":
            a = q["cash"] - q["price"] >= 200
        elif k == "bid":
            a = q["price"] // 2
        elif k == "jail":
            a = "roll"
        elif k == "fine_or_chance":
            a = "fine"
        elif k == "bus":
            a = q["options"][0]["steps"]
        elif k == "triple":
            a = 39
        elif k == "trade_offer":
            a = False
        elif k == "raise":
            a = {"act": "auto"}
        else:  # manage: build where allowed (a few per turn), then end the turn
            can = [x for x in q["assets"] if x["build"]]
            if can and built < 3:
                a, built = {"act": "build", "sq": can[0]["sq"]}, built + 1
            else:
                a, built = {"act": "done"}, 0
        session.answer(q["id"], a)


@pytest.mark.parametrize("rules,n", [(tournament_rules(3), 3), (championship_rules(4), 4)])
def test_a_whole_game_against_the_bots(rules, n):
    s = PlaySession([BOT] * n, seat=1, rules=rules, seed=11)
    asked = []
    scripted(s, asked)
    assert s.over and s.error is None and s.result is not None
    assert {"buy", "manage"} <= set(asked)
    ends = [e for e in s.events if e["e"] == "turn_end"]
    assert ends and ends[-1]["turn"] == len(ends) == len(s.g.turns)
    assert all("cash" in e for e in s.events if e["e"] != "turn_end")
    assert s.g.states is not None and len(s.g.states) == len(ends) + 1  # for the coach's win chances


def test_same_seed_same_answers_same_game():
    def events():
        s = PlaySession([BOT] * 3, seat=0, rules=tournament_rules(3), seed=5)
        scripted(s, [])
        return [(e["e"], e.get("p"), e.get("sq"), e.get("to")) for e in s.events]
    assert events() == events()


def test_answers_must_match_the_question():
    s = PlaySession([BOT] * 2, seat=0, rules=tournament_rules(2), seed=3)
    r = s.poll(0, wait=5)
    while r["question"] is None and not r["over"]:
        r = s.poll(r["next"], wait=5)
    q = r["question"]
    assert q is not None and q["at"] <= r["next"]
    assert not s.answer(q["id"] + 1, True)  # not the question being asked
    s.close()
    s.thread.join(timeout=5)
    assert not s.thread.is_alive() and s.over and s.error is None


def own(g, p, squares):
    for sq in squares:
        g.s.owner[sq] = p


def test_your_trade_offers_go_to_the_bot():
    s = PlaySession([BOT] * 3, seat=0, rules=tournament_rules(3), seed=1, start=False)
    g = s.g
    ed = g.ed
    browns = ed.group_squares[ed.group_names.index("brown")]
    own(g, 0, browns[:1])
    own(g, 1, browns[1:])
    g._ev = []  # as during a turn, so the proposal is logged
    assert s.propose(g, 0, {"to": 1, "give": [], "get": browns[1:], "cash": 1}) == "declined"
    assert g.s.owner[browns[1]] == 1
    assert s.propose(g, 0, {"to": 1, "give": [], "get": browns[1:], "cash": 900}) == "accepted"
    assert g.s.owner[browns[1]] == 0 and g.s.cash[0] == ed.start_cash - 900
    kinds = [e["e"] for e in g._ev]
    assert kinds == ["proposal", "proposal", "trade"] and g._ev[1]["accepted"]
    assert "doesn't make sense" in s.propose(g, 0, {"to": 0, "give": [1]})
    assert "at least one property" in s.propose(g, 0, {"to": 2, "cash": 50})
    assert "isn't possible" in s.propose(g, 0, {"to": 2, "get": [39]})  # nobody owns Mayfair yet
    assert g.s.owner[39] == BANK


def test_manage_checks_every_action():
    s = PlaySession([BOT] * 2, seat=0, rules=tournament_rules(2), seed=2, start=False)
    g = s.g
    ed = g.ed
    browns = ed.group_squares[ed.group_names.index("brown")]
    own(g, 0, browns)
    answers = iter([{"act": "build", "sq": browns[0]}, {"act": "build", "sq": browns[0]},  # even-build rule
                    {"act": "build", "sq": browns[1]}, {"act": "mortgage", "sq": browns[0]},
                    {"act": "trade", "to": 1, "get": [5], "cash": 10}, {"act": "done"}])
    seen = []
    s.ask = lambda kind, **info: (seen.append((kind, info["note"], info["assets"], info["trading"])), next(answers))[1]
    s.act(g, 0, "manage")
    assert [lv for lv in (g.s.level[sq] for sq in browns)] == [1, 1]
    assert seen[2][1] == "That isn't allowed right now."  # the second house on the same square first
    assert seen[4][1] == "That isn't allowed right now."  # can't mortgage with houses in the group
    assert seen[5][1].startswith("That offer isn't possible")
    first = {x["sq"]: x for x in seen[0][2]}
    assert first[browns[0]]["build"] and not first[browns[0]]["sell"] and first[browns[0]]["mortgage"]
    assert seen[0][3]["players"] == [1]


def test_raising_cash_stops_when_you_have_enough():
    s = PlaySession([BOT] * 2, seat=0, rules=tournament_rules(2), seed=2, start=False)
    g = s.g
    own(g, 0, [1, 3, 5])
    g.s.cash[0] = 10
    asked = []
    s.ask = lambda kind, **info: (asked.append(info["target"]), {"act": "mortgage", "sq": [5, 1, 3][len(asked) - 1]})[1]
    s.act(g, 0, "raise", 100)
    assert asked == [100] and g.s.cash[0] == 10 + g.ed.mortgage_value(5) and g.s.mortgaged[5]


def test_proposals_per_turn_are_limited():
    s = PlaySession([BOT] * 2, seat=0, rules=tournament_rules(2), seed=4, start=False)
    g = s.g
    n = {"asked": 0}

    def ask(kind, **info):
        n["asked"] += 1
        return {"act": "done"} if n["asked"] > MAX_PROPOSALS + 2 else {"act": "trade", "to": 1, "get": [1]}
    s.ask = ask
    notes = []
    real = s.propose
    s.propose = lambda *a: notes.append(1) or real(*a)
    s.act(g, 0, "manage")
    assert len(notes) == MAX_PROPOSALS


def test_closing_ends_a_waiting_game_quickly():
    s = PlaySession([BOT] * 4, seat=2, rules=championship_rules(4), seed=8)
    t0 = time.time()
    while s.question is None and time.time() - t0 < 10:
        time.sleep(0.01)
    assert s.question is not None
    threading.Timer(0.05, s.close).start()
    s.thread.join(timeout=5)
    assert not s.thread.is_alive() and s.over and s.result is None and s.error is None
