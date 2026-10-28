import random

import numpy as np

from monopoly_meta import Game
from monopoly_meta.meta import (BALANCED, CONTINUOUS, DISCRETE, evaluate, evolve, mutate,
                                random_genome, to_spec)
from monopoly_meta.policies import make_bot


def test_balanced_genome_plays_exactly_like_the_preset():
    a = Game([make_bot(to_spec(BALANCED, "b")) for _ in range(3)], seed=4).play()
    b = Game([make_bot("balanced") for _ in range(3)], seed=4).play()
    assert a == b


def test_mutation_stays_in_bounds():
    rng = random.Random(0)
    g = random_genome(rng)
    for _ in range(200):
        g = mutate(g, rng, sigma=0.5, p_discrete=0.5)
        for k, (lo, hi) in CONTINUOUS.items():
            assert lo <= g[k] <= hi
        for k, options in DISCRETE.items():
            assert g[k] in options


def test_evaluation_uses_common_random_numbers():
    f = evaluate([BALANCED, BALANCED], [BALANCED], 3, 30, seed=1, workers=1, fixed_opponents=True)
    assert f[0] == f[1]


def test_evolution_runs_and_keeps_population_size():
    res = evolve(2, generations=2, pop_size=3, games=12, seed=0, workers=1, log=lambda *_: None)
    assert len(res.population) == 3 and len(res.history) == 2
    assert np.isfinite(res.best_fitness)


def test_refine_stops_when_challenger_is_weak():
    from monopoly_meta.meta import refine
    meta, ch, log = refine(BALANCED, BALANCED, 2, rounds=2, threshold=2.0, eval_games=20, seed=1,
                           workers=1, log=lambda *_: None)
    assert meta == BALANCED and len(log) == 1


def test_capped_games_count_as_draws_between_survivors():
    from monopoly_meta.engine import GameResult
    from monopoly_meta.meta import game_credit
    r = GameResult(winner=1, capped=True, turns=900, net_worth=[0, 900, 500], elimination_order=[0],
                   stalemate="draw")
    assert game_credit(r, 1, 3) == 0.5 and game_credit(r, 2, 3) == 0.5 and game_credit(r, 0, 3) == 0.0
    r = GameResult(winner=2, capped=False, turns=300, net_worth=[0, 0, 900], elimination_order=[0, 1],
                   stalemate="draw")
    assert game_credit(r, 2, 3) == 1.0 and game_credit(r, 1, 3) == 0.0


def test_stalemate_scoring_modes():
    from monopoly_meta.engine import GameResult
    kw = dict(winner=1, capped=True, turns=900, net_worth=[0, 900, 500, 700], elimination_order=[0])
    assert GameResult(**kw, stalemate="networth").credit(1) == 1.0
    assert GameResult(**kw, stalemate="loss").credit(1) == 0.0
    champ = GameResult(**kw, stalemate="championship")
    # three survivors ranked by net worth: 22, 12, 6 points out of 28
    assert champ.credit(1) == 22 / 28 and champ.credit(3) == 12 / 28 and champ.credit(2) == 6 / 28
    assert champ.credit(0) == 0.0
    outright = GameResult(winner=2, capped=False, turns=300, net_worth=[0, 0, 900, 0],
                          elimination_order=[0, 1, 3], stalemate="championship")
    assert outright.credit(2) == 1.0
