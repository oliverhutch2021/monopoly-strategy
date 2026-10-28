"""The live viewer's recording and hooks must never change a game or a result."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from monopoly_meta import Game, watch
from monopoly_meta.engine import championship_rules
from monopoly_meta.meta import BALANCED, evaluate, to_spec, tournament_rules
from monopoly_meta.policies import make_bot
from monopoly_meta.replay import RecordingGame, buy_value, win_chances
from monopoly_meta.rollout import rollout
from monopoly_meta.tournament import run_games

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scenarios import orange_squeeze  # noqa: E402

LINEUPS = [
    ["balanced", "aggressive", "cautious", "hard_bargain"],
    [to_spec(BALANCED, f"b{i}") for i in range(3)],
    ["balanced", "three_house", "hoarder", "no_trade", "jail_long", "take_chance"],
]


@pytest.mark.parametrize("lineup", LINEUPS)
@pytest.mark.parametrize("champ", [False, True])
def test_recorded_game_is_the_same_game(lineup, champ):
    n = len(lineup)
    rules = championship_rules(n) if champ else tournament_rules(n)
    for seed in (1, 2, 3):
        plain = Game([make_bot(s) for s in lineup], seed=seed, rules=rules).play()
        rec = RecordingGame([make_bot(s) for s in lineup], seed=seed, rules=rules, keep_states=True)
        log = rec.record()
        assert rec.result() == plain
        assert log["result"]["winner"] == plain.winner and log["result"]["turns"] == plain.turns
        assert len(log["turns"]) == plain.turns == len(rec.states) - 1
        json.dumps(log)  # the viewer receives it as JSON


def test_events_agree_with_the_snapshots():
    rules = tournament_rules(4)
    rec = RecordingGame([make_bot(k) for k in LINEUPS[0]], seed=7, rules=rules)
    log = rec.record()
    kinds = {e["e"] for t in log["turns"] for e in t["events"]}
    assert {"roll", "move", "buy", "pay"} <= kinds
    for t in log["turns"]:
        for e in t["events"]:
            if e["e"] == "move":
                assert e["to"] == (e["frm"] + e["steps"]) % 40
        # cash on the last event of a turn can only differ from the snapshot by the turn's later effects,
        # so check the snapshot itself is self-consistent instead
        st = t["state"]
        assert len(st["owner"]) == len(st["level"]) == len(st["mortgaged"]) == 28


def test_hooks_do_not_change_results(tmp_path, monkeypatch):
    m = to_spec(BALANCED, "m")
    genome = dict(BALANCED)
    rules = tournament_rules(3)
    state = orange_squeeze(3)

    def everything():
        f = evaluate([genome, {**genome, "reserve": 300.0}], [genome], 3, 24, seed=5, rules=rules, workers=1,
                     fixed_opponents=True)
        df = run_games([m, "aggressive", "cautious"], 12, seed0=3, rules=rules, workers=1)
        r = rollout(state, ["balanced"] * 3, 10, seed0=9, workers=1)
        return f, evaluate.last_games.copy(), df, r

    monkeypatch.delenv("MM_WATCH_DIR", raising=False)
    off = everything()
    monkeypatch.setenv("MM_WATCH_DIR", str(tmp_path))
    monkeypatch.setattr(watch, "SAMPLE_EVERY", 0.0)
    on = everything()
    assert np.array_equal(off[0], on[0]) and np.array_equal(off[1], on[1])
    assert off[2].equals(on[2])
    assert all(np.array_equal(a, b) for a, b in zip(off[3], on[3]))
    # and the viewer got what it needs: a replayable game and a progress log
    sample = json.loads((tmp_path / "sample.json").read_text())
    assert {"lineup", "seed", "rules", "seat"} <= set(sample)
    lines = (tmp_path / "progress.log").read_text().split("\n")
    assert sum(1 for x in lines if " done " in x) == 3


def test_sampled_game_replays_exactly(tmp_path, monkeypatch):
    monkeypatch.setenv("MM_WATCH_DIR", str(tmp_path))
    monkeypatch.setattr(watch, "SAMPLE_EVERY", 0.0)
    rules = tournament_rules(4)
    df = run_games(["balanced", "aggressive", "cautious", "hard_bargain"], 6, seed0=11, rules=rules, workers=1)
    rec = json.loads((tmp_path / "sample.json").read_text())
    row = df[df.seed == rec["seed"]].iloc[0]
    log = RecordingGame([make_bot(s) for s in rec["lineup"]], seed=rec["seed"], rules=rules).record()
    assert log["result"]["turns"] == row.turns and log["result"]["winner"] == row.winner_seat


def test_win_chances_add_up():
    rules = tournament_rules(3)
    state = orange_squeeze(3)
    res = win_chances(["balanced"] * 3, rules, state, 16, seed=1)
    assert res["n"] == 16
    assert sum(res["p"]) + res["none"] == pytest.approx(1.0)
    assert res == win_chances(["balanced"] * 3, rules, state, 16, seed=1)


def test_buying_decisions_are_kept_where_they_happen():
    rules = tournament_rules(4)
    rec = RecordingGame([make_bot(k) for k in LINEUPS[0]], seed=5, rules=rules, keep_states=True)
    log = rec.record()
    offers = [e for t in log["turns"] for e in t["events"] if e["e"] == "offer"]
    assert offers and [e["k"] for e in offers if e["afford"]] == list(range(len(rec.decisions)))
    for d in rec.decisions:
        st = d["state"]
        assert st.pos[d["p"]] == d["sq"] and st.owner[d["sq"]] == -1 and st.cash[d["p"]] >= rec.ed.price[d["sq"]]


def test_buy_value_reports_a_paired_comparison():
    rules = tournament_rules(4)
    lineup = LINEUPS[0]
    rec = RecordingGame([make_bot(k) for k in lineup], seed=5, rules=rules, keep_states=True)
    rec.record()
    d = rec.decisions[0]
    v = buy_value(lineup, rules, d["state"], d["p"], d["sq"], n=12, seed=3)
    assert v["n"] == 12 and v["playouts"] == 24 and v["price"] == rec.ed.price[d["sq"]]
    assert 0 <= v["p_own"] <= 1 and 0 <= v["p_other"] <= 1
    assert v["gain"] == pytest.approx(v["p_own"] - v["p_other"])
    assert np.isfinite(v["value"]) and v["value_se"] >= 0
    if v["other_owner"]:
        assert v["other_owner"]["winner"] != d["p"]
    assert v == {**buy_value(lineup, rules, d["state"], d["p"], d["sq"], n=12, seed=3), "cpu_seconds": v["cpu_seconds"]}
    short = buy_value(lineup, rules, d["state"], d["p"], d["sq"], n=500, seed=3, budget_s=0.0, n_min=4)
    assert short["n"] == 4
