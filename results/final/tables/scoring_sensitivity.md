# Championship scoring: how much the assumed 5- and 6-survivor points matter

The rules sheet stops at four survivors. Three schedules for five and six (finishing points, first place first):

| Schedule | 5 survivors | 6 survivors |
|---|---|---|
| extrapolated | 16/8/4/2/1 | 13/6/3/2/1/0 |
| extend_four | 19/10/5/3/1 | 19/10/5/3/1/0 |
| rank_linear | 19/14/10/5/0 | 19/15/11/8/4/0 |

## How often the assumed rows decide a game

Between the final championship agents, on the trade-embargo games below.

| Players | Games | Stopped by the time limit | Stopped with 5 or more still in |
|---|---|---|---|
| 5 | 20,000 | 75.4% | 69.5% |
| 6 | 20,000 | 81.2% | 78.5% |

## The trade embargo under each schedule

The final agent with trades accepted ÷ the agent as it is, in the same seat on the same 20,000 games (fresh seeds; the seat rotates). Credit is finishing points ÷ 28; the points columns are expected points per game. A ratio below 1 means accepting trades costs the agent, so the embargo holds against that change.

| Players | Schedule | Agent's points | Accepting trades | Ratio [95%] |
|---|---|---|---|---|
| 5 | extrapolated | 6.17 | 4.92 | 0.797 [0.778, 0.816] |
| 5 | extend_four | 7.14 | 5.15 | 0.721 [0.703, 0.737] |
| 5 | rank_linear | 8.53 | 5.51 | 0.646 [0.631, 0.660] |
| 6 | extrapolated | 4.32 | 3.02 | 0.699 [0.680, 0.719] |
| 6 | extend_four | 5.97 | 3.47 | 0.582 [0.566, 0.597] |
| 6 | rank_linear | 8.38 | 4.38 | 0.523 [0.511, 0.534] |

## The Vine Street sale under each schedule

Change in expected championship points per game against keeping it for good (5,000 paired rollouts per price; ± is 1.96 standard errors), and the seller's change in outright wins.

| Players | Schedule | Price | Buyer (points) | Seller (points) | Seller, outright wins (pp) |
|---|---|---|---|---|---|
| 5 | extrapolated | £400 | +22.13 ± 0.23 | -3.20 ± 0.13 | +0.02 |
| 5 | extrapolated | £800 | +19.51 ± 0.29 | -3.18 ± 0.13 | +0.10 |
| 5 | extrapolated | £1,200 | +17.58 ± 0.31 | -3.11 ± 0.13 | +0.34 |
| 5 | extend_four | £400 | +21.37 ± 0.24 | -3.94 ± 0.15 | +0.02 |
| 5 | extend_four | £800 | +18.75 ± 0.29 | -3.91 ± 0.15 | +0.10 |
| 5 | extend_four | £1,200 | +16.82 ± 0.31 | -3.84 ± 0.16 | +0.34 |
| 5 | rank_linear | £400 | +20.14 ± 0.25 | -4.97 ± 0.18 | +0.02 |
| 5 | rank_linear | £800 | +17.52 ± 0.29 | -4.95 ± 0.18 | +0.10 |
| 5 | rank_linear | £1,200 | +15.59 ± 0.30 | -4.88 ± 0.18 | +0.34 |
| 6 | extrapolated | £400 | +21.93 ± 0.28 | -2.18 ± 0.11 | +0.02 |
| 6 | extrapolated | £800 | +19.30 ± 0.32 | -2.17 ± 0.11 | +0.04 |
| 6 | extrapolated | £1,200 | +17.27 ± 0.34 | -2.14 ± 0.11 | +0.14 |
| 6 | extend_four | £400 | +21.15 ± 0.28 | -3.24 ± 0.16 | +0.02 |
| 6 | extend_four | £800 | +18.53 ± 0.32 | -3.24 ± 0.16 | +0.04 |
| 6 | extend_four | £1,200 | +16.50 ± 0.34 | -3.21 ± 0.17 | +0.14 |
| 6 | rank_linear | £400 | +19.17 ± 0.28 | -4.77 ± 0.18 | +0.02 |
| 6 | rank_linear | £800 | +16.55 ± 0.30 | -4.77 ± 0.18 | +0.04 |
| 6 | rank_linear | £1,200 | +14.52 ± 0.31 | -4.74 ± 0.18 | +0.14 |
