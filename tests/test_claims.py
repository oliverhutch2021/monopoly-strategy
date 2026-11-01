"""The front page's and the full findings' numbers match the result tables they come from (scripts/claims.py).

When a re-run moves a number, test_pages_match_tables fails and names the claim, until the page is updated."""
import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
claims = importlib.import_module("claims")


@pytest.fixture(scope="module")
def items():
    return claims.Claims().all()


def test_pages_match_tables(items):
    missing = claims.check_pages(items)
    assert not missing, "Claims that no longer match the tables (python scripts/claims.py):\n" + "\n".join(
        f"  finding {f}, {what}: {text}" for f, what, text, _ in missing)
    assert len(items) >= 70 and sum(map(claims.on_front_page, items)) >= 7


def test_a_changed_number_is_caught(items):
    findings = claims.FINDINGS.read_text()
    wrong = findings.replace("£594–£1,144", "£594–£1,145", 1)
    names = {what for _, what, _, _ in claims.check_pages(items, findings=wrong)}
    assert "deal zone, 4 players" in names
    wrong = findings.replace("costs 10–11% of", "costs 10–12% of")
    assert {what for _, what, _, _ in claims.check_pages(items, findings=wrong)} == {"cash"}
    front = claims.README.read_text().replace("(3.48 and 2.36 landings", "(3.47 and 2.36 landings")
    assert {c[0] for c in claims.check_pages(items, front=front)} == {"L1"}


def test_line_breaks_and_formatting():
    text = "Keeping £200 more costs 10–11% of wins\n  at 2–4 players"
    assert claims.check(text, [("14", "cash", "costs 10–11% of wins at 2–4 players", None)]) == []
    assert claims.money(1144.37) == "£1,144" and claims.money(1200, censored=True) == "£1,200+"
    assert claims.money(660.5) == "£661"  # half up, not to even
    assert claims.span(0.101, 0.114) == "10–11%" and claims.span(0.03, 0.031) == "3%"
    assert claims.rounds(56.5) == "56.5" and claims.rounds(35.33) == "35" and claims.rounds(63.0) == "63"


def test_first_crossing_misses_a_second_zone():
    """The old summary stopped at the buyer's first crossing, so a buyer who gains again at higher prices (the
    brown curves) had no deal; the new one finds it."""
    prices = [0, 100, 200, 300, 400, 500]
    buyer = [0.05, -0.02, 0.04, 0.06, 0.01, -0.03]
    seller = [-0.10, -0.06, -0.01, 0.02, 0.05, 0.08]
    curve = pd.DataFrame([{"price": x, "player": p, "d_win": d, "d_win_se": 0.005, "p_win_base": 0.3,
                           "p_win_trade": 0.3 + d, "d_networth": d, "d_networth_se": 1.0}
                          for p, ys in ((0, buyer), (1, seller)) for x, d in zip(prices, ys)])
    assert not claims.first_crossing_deal(curve, seller=1, buyer=0)
    from monopoly_meta.rollout import deal_summary
    s = deal_summary(curve, seller=1, buyer=0)
    assert s["deal_zone_exists"] and not s["monotone"]
