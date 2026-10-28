"""Hooks that let the live viewer (scripts/watch.py) follow a running job.

When MM_WATCH_DIR is set (the job runner sets it for every step), the batch runners note how many
games they start and finish, and ``evaluate``/``run_games`` save one of the games they are about to
play every few seconds: who is playing, the seed and the rules. That is enough for the viewer to
replay the very same game move by move (the engine is deterministic given the seed and the players).

Nothing here changes any result. The sample is picked with its own random generator, which never
touches the games' random numbers, and the files are only read by the viewer. With MM_WATCH_DIR
unset every hook returns immediately.
"""
from __future__ import annotations

import json
import os
import random
import time
from dataclasses import asdict

SAMPLE_EVERY = 3.0  # seconds between saved games
_pick = random.Random()  # seeded by the OS, independent of every game
_last = 0.0

# Optional labels a script can set before a batch, e.g.
#   watch.context.update(candidate="Challenger", opponents="Meta agent", about="exploitability test")
context: dict = {}


def folder() -> str | None:
    return os.environ.get("MM_WATCH_DIR") or None


def _append(line: str) -> None:
    d = folder()
    if not d:
        return
    try:
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "progress.log"), "a") as f:
            f.write(line + "\n")
    except OSError:
        pass  # the viewer is a nicety: never let it stop a run


def started(n_games: int) -> float:
    """Note that a batch of n_games is starting; returns the start time for finished()."""
    t = time.time()
    if folder():
        _append(f"{t:.2f} start {n_games} {os.environ.get('MM_STEP', '')}")
    return t


def finished(n_games: int, t0: float) -> None:
    if folder():
        _append(f"{time.time():.2f} done {n_games} {time.time() - t0:.2f}")


def sample(tasks, rules, describe) -> None:
    """Save one of `tasks` for the viewer, at most every SAMPLE_EVERY seconds.

    describe(task) -> {"lineup": [bot specs], "seed": int, "seat": candidate's seat or None}.
    """
    global _last
    d = folder()
    if not d or not tasks:
        return
    now = time.time()
    if now - _last < SAMPLE_EVERY:
        return
    _last = now
    rec = {"time": now, "step": os.environ.get("MM_STEP", ""), "rules": asdict(rules),
           "context": dict(context), **describe(_pick.choice(tasks))}
    try:
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, f".sample-{os.getpid()}.tmp")
        with open(tmp, "w") as f:
            json.dump(rec, f)
        os.replace(tmp, os.path.join(d, "sample.json"))
    except (OSError, TypeError, ValueError):
        pass
