"""Shared settings for the meta-agent scripts (05, 05b, 06): modes, paths, rules."""
import argparse
import json
from pathlib import Path

import pandas as pd

from monopoly_meta.engine import championship_rules
from monopoly_meta.meta import BALANCED, tournament_rules

from run_config import ROOT, TABLES as TAB, scaled  # noqa: E402,F401
PLAYER_COUNTS = [2, 3, 4, 5, 6]
EVAL_GAMES = scaled(4000)

MODES = {
    # official rules; a game stopped after 150 rounds is a loss for everyone
    "standard": {"rules": tournament_rules, "seed": 0},
    # championship rules: Speed Die, tournament tweaks, finishing-position points
    "championship": {"rules": championship_rules, "seed": 5000},
}


def parse(description):
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--mode", choices=list(MODES), default="standard")
    ap.add_argument("players", nargs="*", type=int, default=PLAYER_COUNTS)
    return ap.parse_args()


def ckpt_dir(mode: str) -> Path:
    d = TAB / f"meta_{mode}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def rules_for(mode: str, n: int):
    return MODES[mode]["rules"](n)


def ablations(meta: dict) -> dict:
    m = meta
    return {
        "no trading at all": {**m, "trades": False, "accept_trades": False},
        "accept trades": {**m, "accept_trades": True},
        "always leave jail": {**m, "jail": "short"},
        "always stay in jail": {**m, "jail": "long"},
        "three houses first": {**m, "build_cap": 3},  # a priority, not a cap: hotels follow once all sets have 3
        "never build hotels": {**m, "max_level": 4},
        "flip 'take a Chance'": {**m, "take_chance": not m["take_chance"]},
        "keep £200 more cash": {**m, "reserve": m["reserve"] + 200, "build_reserve": m["build_reserve"] + 200},
        "keep no cash buffer": {**m, "reserve": 0.0, "build_reserve": 0.0},
        "bid 25% more": {**m, "bid_frac": m["bid_frac"] * 1.25},
        "bid 25% less": {**m, "bid_frac": m["bid_frac"] * 0.75},
        "simple baseline bot": dict(BALANCED),
    }


def aggregate(mode: str) -> None:
    """Combine the per-table-size checkpoints of a mode into the published tables."""
    d = ckpt_dir(mode)
    parts = [json.loads(p.read_text()) for p in sorted(d.glob("[0-9]p.json"))]
    parts = [x for x in parts if x.get("refined")]
    if not parts:
        return
    (TAB / f"meta_agents_{mode}.json").write_text(
        json.dumps({str(x["n_players"]): x["meta"] for x in parts}, indent=2))
    for key, name in [("history", "evolution"), ("validation", "validation"), ("ablations", "ablations"),
                      ("refinement", "refinement")]:
        rows = [r for x in parts for r in x.get(key, [])]
        if rows:
            pd.DataFrame(rows).assign(mode=mode).to_csv(TAB / f"meta_{name}_{mode}.csv", index=False)
