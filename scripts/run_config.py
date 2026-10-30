"""Where a run's results go and how large its samples are, so deeper runs reuse the v0.3 scripts as they are.

    MM_RESULTS=results/v04 MM_SCALE=10 python scripts/03_tournament.py

MM_RESULTS  the results folder, relative to the repo (default "results"); tables/, dashboard/ and
            figures/ go under it. Scripts read their inputs (meta agents, earlier tables) from the same
            folder, so a deeper run starts from a copy of the tables it builds on (scripts/deep_prepare.py).
MM_SCALE    a multiplier on every measurement sample (games per cell, rollouts per price, paired
            evaluation games). Search budgets (evolution) are not scaled. The default, 1, reproduces v0.3.

Seeds don't change with the scale, so a deeper run's first games are v0.3's games: the samples nest.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / os.environ.get("MM_RESULTS", "results")
TABLES = RESULTS / "tables"
DASHBOARD = RESULTS / "dashboard"
FIGURES = RESULTS / "figures"
SCALE = float(os.environ.get("MM_SCALE", "1"))


def scaled(n: int) -> int:
    """A sample size multiplied by MM_SCALE (at least 1)."""
    return max(1, round(n * SCALE))


def _key(path: Path) -> Path:
    return path.with_name(path.name + ".key.json")


def fresh(path: Path, inputs: dict) -> bool:
    """Does `path` hold a result computed from exactly `inputs`? A checkpoint counts only with a matching key file
    beside it (written by `stamp`), so a change of agents, rules, seeds or sample size recomputes it instead of
    silently reusing it."""
    want = json.dumps(inputs, sort_keys=True, default=str)
    return path.exists() and _key(path).exists() and _key(path).read_text() == want


def stamp(path: Path, inputs: dict) -> None:
    """Record the inputs a checkpoint was computed from (see `fresh`)."""
    _key(path).write_text(json.dumps(inputs, sort_keys=True, default=str))
