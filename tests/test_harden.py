"""v0.5's hardening: the extra sparring pool, exposure tables, ablations and the resumable rounds."""
import pytest

from monopoly_meta import harden as hd
from monopoly_meta.harden import Budget, ablations, exposure, harden
from monopoly_meta.meta import BALANCED, evolve, tournament_rules
from monopoly_meta.unconventional import TACTICS, tactics_on, with_tactics

META = dict(BALANCED, reserve=220.0, bid_frac=1.1)
TINY = Budget(generations=1, pop_size=2, games=4, select_games=4, top=2, exposure_games=4, oracle_evals=16,
              oracle_games=4, oracle_cells=4, oracle_batch=8, oracle_keep=2, check_games=4, max_new=1)


def test_evolve_without_sparring_is_unchanged():
    kw = dict(generations=2, pop_size=2, games=4, seed=3, workers=1, rules=tournament_rules(2), log=lambda *a: None)
    a, b, c = evolve(2, **kw), evolve(2, sparring=None, **kw), evolve(2, sparring=[], **kw)
    assert a.best == b.best == c.best and a.history == b.history == c.history
    d = evolve(2, sparring=[dict(META, reserve=0.0, build_reserve=0.0)] * 3, **kw)
    assert d.history != a.history  # the sparring partners really are at the tables


def test_exposure_of_the_agent_to_itself_is_exactly_one():
    rows = exposure(META, {"itself": META, "simple bot": BALANCED}, 3, tournament_rules(3), games=30, seed=5,
                    workers=1)
    assert [r["name"] for r in rows] == ["itself", "simple bot"]
    assert rows[0]["ratio"] == pytest.approx(1.0) and rows[0]["ci_low"] == pytest.approx(1.0)
    assert 0 <= rows[1]["meta_capped"] <= 1 and rows[1]["tactics"] == "no new moves"


def test_ablations_switch_one_move_off_at_a_time():
    g = with_tactics({**META, "snipe": 0.5, "lock": 8})
    out = ablations(g)
    assert list(out) == ["without auction sniping", "without housing lock", "without any new move"]
    assert tactics_on(out["without auction sniping"]) == ["lock"]
    assert tactics_on(out["without housing lock"]) == ["snipe"]
    assert tactics_on(out["without any new move"]) == [] and out["without any new move"]["reserve"] == 220.0
    assert list(ablations(with_tactics({**META, "lock": 8}))) == ["without housing lock"]
    assert ablations(META) == {}


def test_budget_for_slow_tables():
    b = Budget().for_speed(0.16)
    assert (b.generations, b.oracle_evals) == (5, 8 * b.oracle_batch)
    b = Budget().for_speed(1.4)
    assert (b.generations, b.oracle_evals) == (12, 1120)
    assert Budget().for_speed(1.0) == Budget()


def test_least_exploited_passes_over_stalling_agents():
    cands = [{"worst": 1.0, "self_capped": 0.5, "fitness": 2.0}, {"worst": 1.3, "self_capped": 0.0, "fitness": 1.0},
             {"worst": 1.2, "self_capped": 0.1, "fitness": 0.5}]
    assert hd._least_exploited(cands) == 2
    assert hd._least_exploited([dict(c, self_capped=0.9) for c in cands]) == 0  # all stall: fall back to all


def test_hardening_resumes_exactly(tmp_path, monkeypatch):
    pool = {"meta": META, "simple bot": BALANCED, "hoarder": dict(META, reserve=600.0, w_red=0.0)}
    args = dict(seed=9, budget=TINY, rounds=2, threshold=0.0, workers=1, log=lambda *a: None)
    rules = tournament_rules(2)
    whole = harden(META, pool, 2, rules, ckpt=tmp_path / "a.json", **args)
    assert len(whole["rounds"]) == 2 and len(whole["final"]) == 3  # start + two rounds
    # one fresh exploit joins after each round (threshold 0 lets any in), the last round's too, so that every
    # round's agent meets the exploits found against it in the final comparison
    assert len(whole["pool"]) == 5
    assert {x["agent"] for x in whole["final"]} == {"start", "round 1", "round 2"}
    # stop the same run during round 2's oracle, then resume it: same answer
    real, calls = hd.search, []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return real(*a, **k)

    monkeypatch.setattr(hd, "search", flaky)
    with pytest.raises(KeyboardInterrupt):
        harden(META, pool, 2, rules, ckpt=tmp_path / "b.json", **args)
    monkeypatch.setattr(hd, "search", real)
    resumed = harden(META, pool, 2, rules, ckpt=tmp_path / "b.json", **args)
    assert resumed["meta"] == whole["meta"] and resumed["selected_round"] == whole["selected_round"]
    assert [r["exploitability"] for r in resumed["rounds"]] == [r["exploitability"] for r in whole["rounds"]]
    # a finished run just reports
    again = harden(META, pool, 2, rules, ckpt=tmp_path / "a.json", **args)
    assert again["meta"] == whole["meta"]
    with pytest.raises(SystemExit):
        harden(META, pool, 2, rules, ckpt=tmp_path / "a.json", **{**args, "seed": 10})


def test_every_tactic_has_a_name_in_labels():
    g = with_tactics({**META, **{k: hi for k, (off, lo, hi) in TACTICS.items()}})
    assert len(hd.label(g).split(", ")) == len(TACTICS)
