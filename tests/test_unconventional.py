"""The v0.4 search: genomes with tactics, behaviour descriptors, the MAP-Elites archive and the league."""
import json
import random

import numpy as np
import pytest

from monopoly_meta.engine import STAT_FIELDS, ST_AUCTION, ST_BOUGHT, ST_CASH, ST_TURNS
from monopoly_meta.meta import BALANCED, evolve, to_spec, tournament_rules
from monopoly_meta.policies import make_bot
from monopoly_meta.unconventional import (TACTICS, Arena, describe, draw_tactic, fit_cells, insert, kmeans, league,
                                          nash_mixture, pick_finalists, random_genome_ext, search, seed_genomes,
                                          tactics_on, validate, vary, with_tactics)

META = dict(BALANCED, reserve=220.0, bid_frac=1.1)


def in_range(g):
    for k, (off, lo, hi) in TACTICS.items():
        v = g[k]
        assert v == off or (lo <= v <= hi), (k, v)


def test_genomes_with_tactics_are_valid_bots():
    rng = random.Random(1)
    pool = [random_genome_ext(rng) for _ in range(20)] + seed_genomes(META)
    for _ in range(200):
        child = vary(rng.choice(pool), rng, rng.choice(pool) if rng.random() < 0.5 else None)
        in_range(child)
        json.dumps(child)
        make_bot(to_spec(child, "x"))  # every gene is a HeuristicBot field
        pool.append(child)
    assert any(tactics_on(g) for g in pool) and any(not tactics_on(g) for g in pool)
    assert tactics_on(with_tactics(META)) == []
    assert all(len(tactics_on(g)) == 1 for g in seed_genomes(META)[1:9])
    assert draw_tactic("count_cards", rng) is True and isinstance(draw_tactic("lock", rng), int)


def test_descriptors_are_in_the_unit_cube():
    st = [0] * len(STAT_FIELDS)
    st[ST_TURNS], st[ST_CASH], st[ST_BOUGHT], st[ST_AUCTION] = 100, 100 * 1250, 10, 10
    d = describe(st, games=2, n_players=4)
    assert d[0] == pytest.approx(0.5) and d[2] == pytest.approx(0.5)
    assert d[1] == pytest.approx(10 / 7 / 2)
    assert all(0 <= x <= 1 for x in describe([10 ** 6] * len(STAT_FIELDS), 1, 2))
    assert describe([0] * len(STAT_FIELDS), 0, 3) == [0.0] * 8


def test_kmeans_and_cells_are_deterministic():
    pts = np.random.default_rng(0).random((60, 3))
    a, b = kmeans(pts, 5, seed=4), kmeans(pts, 5, seed=4)
    assert a.shape == (5, 3) and np.array_equal(a, b)
    cells = fit_cells(pts.tolist(), 7, seed=2)
    assert len(cells) == 7 and cells == fit_cells(pts.tolist(), 7, seed=2)


def test_insert_keeps_the_better_strategy_per_region():
    state = {"n_players": 2, "centroids": [[0.0] * 8, [1.0] * 8], "elites": {}, "meta_credit": 0.5, "evals": 0}
    st = [0] * len(STAT_FIELDS)
    res = {"credit": 0.4, "capped": 0.0, "stats": st, "games": [0] * 10}
    assert insert(state, {"a": 1}, res) and state["elites"]["0"]["fitness"] == pytest.approx(0.8)
    assert not insert(state, {"a": 2}, {**res, "credit": 0.3})
    assert insert(state, {"a": 3}, {**res, "credit": 0.6}) and state["elites"]["0"]["genome"] == {"a": 3}


def test_arena_plays_every_candidate_on_the_same_games():
    rules = tournament_rules(3)
    with Arena(META, 3, rules, games=9, seed=5, workers=1) as arena:
        a, b = arena.play([with_tactics(META), with_tactics(META)])
    assert np.array_equal(a["games"], b["games"]) and a["stats"] == b["stats"]
    assert a["stats"][ST_TURNS] > 0


def tiny(tmp_path=None, evals=20):
    return search(META, 2, tournament_rules(2), seed=3, games=6, cells=5, init=12, batch=4, evals=evals, workers=1,
                  ckpt=tmp_path, log=lambda *a, **k: None)


def test_search_is_deterministic_and_resumes_exactly(tmp_path):
    straight = tiny()
    assert straight["evals"] == 20 and 0 < len(straight["elites"]) <= 5
    assert straight == tiny()
    ck = tmp_path / "s.json"
    tiny(ck, evals=16)
    resumed = tiny(ck, evals=20)
    assert resumed["elites"] == straight["elites"] and resumed["history"] == straight["history"]


def test_a_checkpoint_from_other_inputs_is_refused(tmp_path):
    ck = tmp_path / "s.json"
    tiny(ck, evals=8)
    with pytest.raises(SystemExit, match="other inputs or code"):
        search(META, 2, tournament_rules(2), seed=4, games=6, cells=5, init=12, batch=4, evals=12, workers=1,
               ckpt=ck, log=lambda *a, **k: None)
    state = json.loads(ck.read_text())
    del state["fingerprint"]  # made before fingerprints: resumed, with a note
    ck.write_text(json.dumps(state))
    notes = []
    search(META, 2, tournament_rules(2), seed=3, games=6, cells=5, init=12, batch=4, evals=12, workers=1,
           ckpt=ck, log=notes.append)
    assert any("no fingerprint" in n for n in notes)


def test_finalists_validation_and_league():
    state = tiny()
    fins = pick_finalists(state, top=2)
    assert fins and len({json.dumps(e["genome"], sort_keys=True) for e in fins}) == len(fins)
    rows = validate([{"genome": with_tactics(META), "fitness": 1.0, "tactics": []}], META, 2, tournament_rules(2),
                    seed=1, games=10, workers=1)
    assert rows[0]["ratio"] == pytest.approx(1.0)  # the meta agent against itself, on the same games
    m = league({"meta": with_tactics(META), "simple": with_tactics(BALANCED)}, 2, tournament_rules(2), seed=2,
               games=8, workers=1, log=lambda *a: None)
    assert m.shape == (2, 2) and np.allclose(np.diag(m), 1.0)


def test_nash_mixture_picks_the_strategy_nobody_invades():
    m = np.array([[1.0, 0.8, 0.7], [1.3, 1.0, 0.9], [1.4, 1.2, 1.0]])  # the third invades everyone
    mix = nash_mixture(m, iters=3000)
    assert mix.sum() == pytest.approx(1.0) and mix.argmax() == 2 and mix[2] > 0.95
    rps = np.array([[1, 2, .5], [.5, 1, 2], [2, .5, 1]])  # a cycle: rock, paper, scissors
    assert np.allclose(nash_mixture(rps, iters=30000), 1 / 3, atol=0.03)


def test_evolve_with_the_new_variation():
    res = evolve(2, generations=2, pop_size=4, games=6, seed=1, init=[with_tactics(META)], opponents=[META],
                 rules=tournament_rules(2), workers=1, mutator=vary, sampler=random_genome_ext, log=lambda *a: None)
    in_range(res.best)
