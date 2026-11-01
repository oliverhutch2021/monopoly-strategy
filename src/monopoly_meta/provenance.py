"""What a result was computed from: digests of the code and of a run's inputs, so a checkpoint is reused only for
the run that made it (the 2026-10-31 review: resumes checked their budget and seed, not their rules, opponents or
code)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent


def code_digest() -> str:
    """A digest of every module of this package and its edition data."""
    h = hashlib.sha256()
    for f in sorted(PACKAGE.rglob("*.py")) + sorted((PACKAGE / "data").glob("*.json")):
        h.update(f.relative_to(PACKAGE).as_posix().encode())
        h.update(f.read_bytes().replace(b"\r\n", b"\n"))  # the same digest whatever a checkout's line endings
    return h.hexdigest()[:16]


def fingerprint(**inputs) -> str:
    """A digest of a run's inputs (anything JSON can write, e.g. dataclasses as dicts) and of the code."""
    blob = json.dumps(inputs, sort_keys=True, default=str) + code_digest()
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def check_resume(state: dict, fp: str, ckpt, log=print) -> None:
    """Refuse to resume a checkpoint made from other inputs or code. One from before fingerprints is resumed with a
    note, so finished historical runs stay readable."""
    if "fingerprint" not in state:
        log(f"  note: {ckpt} has no fingerprint (made before 2026-11); resuming it as it is")
        return
    if state["fingerprint"] != fp:
        raise SystemExit(f"{ckpt} was made from other inputs or code (fingerprint {state['fingerprint']}, now {fp}): "
                         "delete it to start again")
