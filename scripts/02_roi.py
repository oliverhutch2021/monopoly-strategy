"""Property economics: rent per opponent turn, payback and marginal return per house.

Outputs
  results/tables/property_economics.csv   per property (long-stay jail landing rates)
  results/tables/group_economics_{n}p.csv per colour group and level, for 2-6 players
"""

from monopoly_meta.markov import build_chain
from monopoly_meta.roi import group_table, property_table

from run_config import TABLES as OUT  # noqa: E402
OUT.mkdir(parents=True, exist_ok=True)


def main():
    m = build_chain(jail_strategy="long")
    props = property_table(m)
    props.to_csv(OUT / "property_economics.csv", index=False)
    for n in range(2, 7):
        group_table(m, n_players=n).to_csv(OUT / f"group_economics_{n}p.csv", index=False)

    gt = group_table(m, n_players=4)
    streets = gt[~gt.group.isin(["stations", "utilities"])]
    hotel = streets[streets.level == "hotel"].sort_values("payback_rounds")
    print("Hotel payback (rounds, 4 players):")
    print(hotel[["group", "invest", "income_per_round", "payback_rounds"]].round(2).to_string(index=False))
    best_house = streets.dropna(subset=["marginal_roi_per_round"]).loc[
        lambda d: d.groupby("group").marginal_roi_per_round.idxmax()]
    print("\nHouse level with the best marginal return, per group:")
    print(best_house[["group", "level", "marginal_roi_per_round"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
