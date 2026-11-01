"""Stored regression hashes for the v0.3 Python engine and pipelines.

Every case plays seeded games (or runs a pipeline function) and reduces everything it produced to
one SHA-256 digest: each game hashes its full state after every turn, then its result. The digests
live in tests/golden/v03.json, together with copies of the bot genomes they use, so later changes
to results/ never move them.

    python tests/golden.py            # recompute and compare (same check as the pytest test)
    python tests/golden.py --write    # store new digests: only on purpose, e.g. a new RNG in Phase A

A refactor that keeps every digest identical has not changed a single game.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "v03.json"
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from monopoly_meta.engine import Game, Rules, championship_rules  # noqa: E402
from monopoly_meta.markov import build_chain  # noqa: E402
from monopoly_meta.meta import BALANCED, evaluate, to_spec, tournament_rules  # noqa: E402
from monopoly_meta.policies import make_bot  # noqa: E402
from monopoly_meta.rollout import rollout, trade_price_curve  # noqa: E402
from monopoly_meta.tournament import run_games  # noqa: E402

PLAYERS = [2, 3, 4, 5, 6]
V03_CURVE = ["price", "player", "p_win_base", "p_win_trade", "d_win", "d_win_se", "d_networth", "d_networth_se",
             "capped_share_base", "capped_share_trade"]
MIX = ["balanced", "aggressive", "cautious", "three_house", "hoarder", "jail_short", "jail_long",
       "take_chance", "no_trade", "hard_bargain", "random"]
GAME_SETS = {  # name: (rules factory, lineup kind, seeds per table size)
    "official-mix": (lambda n: Rules(), "mix", 6),
    "official-meta": (tournament_rules, "meta_standard", 4),
    "championship-meta": (championship_rules, "meta_championship", 4),
    "championship-mix": (championship_rules, "mix", 4),
    "jackpot-mix": (lambda n: Rules(free_parking_jackpot=True), "mix", 2),
    "no-auctions-mix": (lambda n: Rules(auctions=False), "mix", 2),
    "random-cards-mix": (lambda n: Rules(card_draw="random"), "mix", 2),
}


def _dump(x) -> bytes:
    return json.dumps(x, separators=(",", ":"), sort_keys=True).encode()


def _r(xs, nd=10):
    return [round(float(x), nd) for x in xs]


def state_tuple(s) -> list:
    return [s.cash, s.pos, s.alive, s.in_jail, s.jail_turns, s.goojf, s.owner, s.level, s.mortgaged,
            s.bank_houses, s.bank_hotels, list(s.chance), list(s.cc), s.current, s.turn, s.pot,
            s.elimination_order, s.passed_go]


def lineup(kind: str, n: int, seed: int, genomes: dict) -> list:
    if kind == "mix":
        return [MIX[(seed * 7 + i * 3) % len(MIX)] for i in range(n)]
    return [to_spec(genomes[kind][str(n)], "meta")] * n


def game_digest(rules, specs, seed: int) -> tuple[str, int]:
    """Play one game turn by turn, hashing the whole state after every turn, then the result."""
    g = Game([make_bot(k) for k in specs], rules=rules, seed=seed)
    h = hashlib.sha256()
    while not g.done:
        g.take_turn()
        h.update(_dump(state_tuple(g.s)))
    r = g.result()
    h.update(_dump([r.winner, r.capped, r.turns, r.net_worth, r.elimination_order, r.stalemate,
                    g.uneven_events, _r([r.credit(p) for p in range(g.s.n_players)])]))
    return h.hexdigest(), r.turns


def pipeline_digests(genomes: dict) -> dict:
    """Small, fast versions of the v0.3 pipelines: Markov chain, tournaments, rollouts, meta evaluation."""
    from scenarios import orange_squeeze

    out = {}
    for jail in ("long", "short"):
        m = build_chain(jail_strategy=jail)
        out[f"markov-{jail}"] = hashlib.sha256(_dump(_r(m.visits_per_turn, 12) + _r(m.pi, 12))).hexdigest()
    df = run_games(["balanced", "aggressive", "cautious", "random"], 24, seed0=5, workers=1)
    out["run_games"] = hashlib.sha256(_dump(df.astype(str).values.tolist())).hexdigest()
    state = orange_squeeze(4)
    credit, worth, capped = rollout(state, ["balanced"] * 4, 24, seed0=3, workers=1)
    out["rollout"] = hashlib.sha256(_dump([_r(credit.ravel()), _r(worth.ravel()), capped.tolist()])).hexdigest()
    curve = trade_price_curve(state, ["balanced"] * 4, seller=1, buyer=0, squares=[19], prices=[0, 400, 800],
                              n=16, seed0=777, workers=1)
    # v0.3's rows and columns, in v0.3's order: what was added since (outright wins, the bystanders summed game by
    # game) doesn't move the digest, and a changed value still does
    curve = curve[curve.player >= 0][V03_CURVE]
    out["trade_price_curve"] = hashlib.sha256(_dump(curve.round(10).astype(str).values.tolist())).hexdigest()
    meta = genomes["meta_standard"]["4"]
    evaluate([meta, BALANCED], [meta], 4, 24, seed=11, rules=tournament_rules(4), workers=1, fixed_opponents=True)
    out["evaluate"] = hashlib.sha256(_dump([_r(evaluate.last_games.ravel()),
                                            _r(evaluate.last_capped_share)])).hexdigest()
    return out


def compute(genomes: dict) -> dict:
    digests = {}
    for name, (rules_for, kind, seeds) in GAME_SETS.items():
        for n in PLAYERS:
            for seed in range(seeds):
                d, _ = game_digest(rules_for(n), lineup(kind, n, seed, genomes), seed)
                digests[f"{name}/{n}p/seed{seed}"] = d
    digests.update({f"pipeline/{k}": v for k, v in pipeline_digests(genomes).items()})
    return digests


def frozen_genomes() -> dict:
    """The meta genomes used above, copied from results/ when the digests are first written."""
    tab = ROOT / "results" / "tables"
    std = json.loads((tab / "meta_agents_standard.json").read_text())
    champ = json.loads((tab / "meta_agents_championship.json").read_text())
    if "6" not in champ:  # v0.3 starter: 6-player championship agent is still the first-pass one
        champ["6"] = json.loads((tab / "meta_championship" / "6p.json").read_text())["meta"]
    strip = lambda d: {n: {k: v for k, v in g.items() if k != "name"} for n, g in d.items()}  # noqa: E731
    return {"meta_standard": strip(std), "meta_championship": strip(champ)}


def load() -> dict:
    return json.loads(GOLDEN.read_text())


def check() -> list[str]:
    """Names of the cases whose digest no longer matches (empty list = identical behaviour)."""
    stored = load()
    now = compute(stored["genomes"])
    return [k for k in stored["digests"] if now.get(k) != stored["digests"][k]] + \
           [k for k in now if k not in stored["digests"]]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="store new digests (deliberate engine changes only)")
    args = ap.parse_args()
    if args.write:
        genomes = frozen_genomes()
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps({"version": "v0.3", "python": sys.version.split()[0],
                                      "genomes": genomes, "digests": compute(genomes)}, indent=1) + "\n")
        print(f"wrote {GOLDEN.relative_to(ROOT)}")
        return
    bad = check()
    if bad:
        print(f"{len(bad)} case(s) changed, e.g. {', '.join(bad[:5])}")
        sys.exit(1)
    print(f"all {len(load()['digests'])} regression digests match")


if __name__ == "__main__":
    main()
