"""Regression guard: the engine and pipelines must reproduce the stored v0.3 digests exactly.

If this fails after a change that should not alter behaviour (a refactor, a move, a rename), the
change altered at least one game. Run `python tests/golden.py` for the list of cases that moved.
"""
from golden import check


def test_v03_digests_unchanged():
    changed = check()
    assert not changed, f"{len(changed)} regression digest(s) changed, e.g. {changed[:5]}"
