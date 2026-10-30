"""Deal summaries for every stored trade curve, read without assuming a curve's shape (rollout.deal_summary).

    MM_RESULTS=results/final python scripts/trade_summaries.py

Rewrites, from the curves already in <results>/tables (no new games are played):
  trade_curve_summary.csv               Vine Street with simple bots (04_trade_curve.py)
  meta_trade_summary_<mode>.csv         Vine Street with meta agents (06_meta_trade_curve.py)
  property_trade_summary_<bots>.csv     every property (10_property_trades.py)
Each row says whether the rules allow the trade at all (legal: no trades heads-up under championship rules)
and what the credit measures (utility). 04, 06 and 10 call the same functions when they finish.
"""
import pandas as pd

from monopoly_meta import load_edition
from monopoly_meta.engine import Rules, championship_rules
from monopoly_meta.meta import tournament_rules
from monopoly_meta.rollout import deal_summary, trade_allowed, utility_name
from scenarios import orange_squeeze, set_completion

from run_config import TABLES as TAB  # noqa: E402

VINE = 19
RULES = {"simple": lambda n: Rules(), "standard": tournament_rules, "meta": tournament_rules,
         "championship": championship_rules}


def summarise(curve: pd.DataFrame, by: list[str], rules_of, state_of, squares_of, buyer_of, extra=None,
              boot: dict | None = None) -> pd.DataFrame:
    """One deal summary per group of `curve` (grouped by `by`), with its legality and utility.
    `boot` maps a group key to the whole-curve bootstrap of its deal (trade_price_curve attrs), when there is one."""
    rows = []
    for key, c in curve.groupby(by):
        k = dict(zip(by, key if isinstance(key, tuple) else (key,)))
        rules = rules_of(int(k["n_players"]))
        buyer = buyer_of(k)
        legal = trade_allowed(state_of(k), 1, buyer, squares_of(k), rules)
        row = {**k, **(extra(k) if extra else {}), **deal_summary(c, seller=1, buyer=buyer, legal=legal),
               "utility": utility_name(rules)}
        if legal:  # a forbidden trade has no deal to resample
            row.update((boot or {}).get(tuple(k.values()), {}))
        rows.append(row)
    return pd.DataFrame(rows)


def vine_simple(curve: pd.DataFrame, boot: dict | None = None) -> pd.DataFrame:
    return summarise(curve, ["n_players", "buyer"], RULES["simple"], lambda k: orange_squeeze(int(k["n_players"])),
                     lambda k: [VINE], lambda k: int(k["buyer"]), boot=boot)


def vine_meta(curve: pd.DataFrame, mode: str, boot: dict | None = None) -> pd.DataFrame:
    return summarise(curve, ["n_players"], RULES[mode], lambda k: orange_squeeze(int(k["n_players"])),
                     lambda k: [VINE], lambda k: 0, boot=boot)


def properties(curve: pd.DataFrame, bots: str) -> pd.DataFrame:
    ed = load_edition()
    return summarise(curve, ["n_players", "square"], RULES[bots],
                     lambda k: set_completion(ed.names[int(k["square"])], int(k["n_players"])),
                     lambda k: [int(k["square"])], lambda k: 0, extra=lambda k: {"name": ed.names[int(k["square"])]})


def main():
    jobs = [("trade_curve_orange_squeeze.csv", "trade_curve_summary.csv", vine_simple)]
    jobs += [(f"meta_trade_curve_{m}.csv", f"meta_trade_summary_{m}.csv", lambda c, m=m: vine_meta(c, m))
             for m in ("standard", "championship")]
    jobs += [(f"property_trade_curve_{b}.csv", f"property_trade_summary_{b}.csv", lambda c, b=b: properties(c, b))
             for b in ("simple", "meta", "championship")]
    for source, target, fn in jobs:
        if not (TAB / source).exists():
            print(f"skip {target}: no {source}")
            continue
        old = pd.read_csv(TAB / target) if (TAB / target).exists() else None
        new = fn(pd.read_csv(TAB / source))
        keep = [c for c in (old.columns if old is not None else []) if c.startswith("deal_low_ci")
                or c.startswith("deal_high_ci") or c in ("deal_share_of_resamples", "resamples")]
        if keep:  # bootstrap columns come from the run that played the games; carry them over
            new = new.merge(old[[c for c in old.columns if c in ("n_players", "buyer", "square")] + keep], how="left")
            new.loc[~new.legal.astype(bool), keep] = None  # a forbidden trade has no deal to resample
        new.to_csv(TAB / target, index=False)
        changed = "" if old is None else _changes(old, new)
        print(f"{target}: {len(new)} rows, {int(new.deal_zone_exists.sum())} with a deal{changed}")


def _changes(old: pd.DataFrame, new: pd.DataFrame) -> str:
    keys = [c for c in ("n_players", "buyer", "square") if c in new.columns]
    m = old[keys + ["deal_zone_exists"]].merge(new[keys + ["deal_zone_exists", "legal"]], on=keys,
                                               suffixes=("_old", ""))
    gained = int((~m.deal_zone_exists_old & m.deal_zone_exists).sum())
    lost = int((m.deal_zone_exists_old & ~m.deal_zone_exists).sum())
    illegal = int((~m.legal).sum())
    return f" ({gained} deals found that the old summary missed, {lost} removed, {illegal} not allowed by the rules)"


if __name__ == "__main__":
    main()
