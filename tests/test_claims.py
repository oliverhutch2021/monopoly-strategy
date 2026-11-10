"""The numbers on the front page, in the full findings and on the rules page match the result tables they come from
(scripts/claims.py).

When a re-run moves a number, test_pages_match_tables fails and names the claim, until the page is updated."""
import importlib
import re
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
        f"  {claims.where(item)}, {item[1]}: {item[2]}" for item in missing)
    assert sum(map(claims.on_front_page, items)) >= 12 and sum(map(claims.on_rules_page, items)) >= 14
    # the front page says how many figures are checked: that number is checked too
    quoted = int(re.search(r"recomputes over (\d+) of the figures", claims.README.read_text()).group(1))
    assert len(items) > quoted >= 190


def test_a_changed_number_is_caught(items):
    findings = claims.FINDINGS.read_text()
    wrong = findings.replace("£594–£1,144", "£594–£1,145", 1)
    names = {what for _, what, _, _ in claims.check_pages(items, findings=wrong)}
    assert "deal zone, 4 players" in names
    wrong = findings.replace("costs 10–11% of", "costs 10–12% of")
    assert {what for _, what, _, _ in claims.check_pages(items, findings=wrong)} == {"cash"}
    front = claims.README.read_text().replace("(3.48 and 2.36 landings", "(3.47 and 2.36 landings")
    assert {c[0] for c in claims.check_pages(items, front=front)} == {"L1"}


def test_the_rules_page_and_the_search_findings_are_checked_too(items):
    """RULES.md once quoted a 20% stall rate for an agent that had been replaced (it is 0.2%), and findings 8-12 had
    three rounding slips: both are now under the check."""
    rules = claims.RULES_PAGE.read_text()
    assert "stalls in 0.2%" in claims.flatten(rules)
    stale = rules.replace("0.1–0.6% of games between the final agents stall", "under 0.5% of games stall")
    assert {c[1] for c in claims.check_pages(items, rules=stale)} == {"stalls, final agents"}
    findings = claims.FINDINGS.read_text()
    slip = findings.replace("| 4 | 1.71× | 1.64× |", "| 4 | 1.71× | 1.65× |")
    assert {c[1] for c in claims.check_pages(items, findings=slip)} == {"best find, 4 players"}
    # a claim is looked for on its own page only
    assert all(claims.where(c) == "rules page" for c in items if c[0] == "R")
    assert claims.chance(0.0035) == "0.35%" and claims.chance(0.0873) == "8.7%" and claims.chance(0.36465) == "36%"


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
