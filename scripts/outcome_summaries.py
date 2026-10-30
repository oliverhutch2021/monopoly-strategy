"""Every outcome side by side in the stored tournament tables, from the counts already in them (no new games).

    MM_RESULTS=results/final python scripts/outcome_summaries.py

Adds to strategy_variants.csv, championship_strategy_variants.csv, seat_advantage.csv and
championship_seat_advantage.csv: outright_share (outright wins ÷ all games), limit_share (time-limit wins ÷ all
games) and, where missing, wins. win_rate stays the share of the decided games won outright (fair share 1/n), and
capped_share the share stopped by the limit. 03_tournament.py and 07_championship_basics.py write the same columns
when they run.
"""
import pandas as pd

from run_config import TABLES as TAB  # noqa: E402

FILES = ["strategy_variants.csv", "championship_strategy_variants.csv", "seat_advantage.csv",
         "championship_seat_advantage.csv"]


def outcomes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "wins" not in df:  # older championship tables kept the rate among decided games
        df.insert(df.columns.get_loc("decided"), "wins", (df.win_rate * df.decided).round().astype(int))
    df["outright_share"] = df.wins / df.games
    df["limit_share"] = df.limit_wins / df.games
    return df


def main():
    for name in FILES:
        path = TAB / name
        if not path.exists():
            print(f"skip {name}")
            continue
        df = outcomes(pd.read_csv(path))
        df.to_csv(path, index=False)
        print(f"{name}: outright share {df.outright_share.min():.4f}-{df.outright_share.max():.4f}, "
              f"time-limit share up to {df.limit_share.max():.4f}")


if __name__ == "__main__":
    main()
