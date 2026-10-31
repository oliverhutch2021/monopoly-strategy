# Rule sensitivity of the housing findings

Paired games per cell: 20,000. Ratio = the candidate's credit ÷ the final agent's in the same seat on the same games (95% bootstrap interval). "Variant ÷ engine rules" is that ratio under a variant divided by the ratio under the engine's own rules, from a bootstrap that resamples the same seeds in both: an interval that excludes 1 means the variant changes the candidate's edge. Variants: engine rules, build any time, house auctions, any time + auctions, mortgaged stations count.

There are 52 variant ÷ engine-rules intervals below. At 95%, about 3 would exclude 1 by chance even if no variant mattered, so a lone exclusion is weak evidence; a consistent pattern across settings or variants is not. With Bonferroni-adjusted intervals, 11 of the 52 still exclude 1 (marked **).

## standard, 4 players

Left out: three houses first (the same genome as the final agent).

| Candidate | engine rules | build any time | house auctions | any time + auctions | mortgaged stations count |
|---|---|---|---|---|---|
| strongest known challenger | 1.263 [1.234, 1.292] | 1.240 [1.212, 1.269] | 1.262 [1.234, 1.292] | 1.239 [1.211, 1.268] | 1.257 [1.228, 1.287] |
| hard three-house cap | 0.794 [0.780, 0.809] | 0.774 [0.760, 0.787] | 0.795 [0.780, 0.809] | 0.775 [0.761, 0.788] | 0.792 [0.777, 0.806] |
| housing lock on (14) | 1.061 [1.052, 1.070] | 1.032 [1.025, 1.040] | 1.061 [1.052, 1.070] | 1.032 [1.025, 1.040] | 1.065 [1.056, 1.074] |
| simple bot | 0.610 [0.591, 0.630] | 0.576 [0.557, 0.596] | 0.608 [0.589, 0.628] | 0.576 [0.557, 0.596] | 0.608 [0.588, 0.628] |

Variant ÷ engine rules:

| Candidate | build any time | house auctions | any time + auctions | mortgaged stations count |
|---|---|---|---|---|
| strongest known challenger | 0.982 [0.960, 1.003] | 1.000 [0.997, 1.002] | 0.982 [0.959, 1.003] | 0.996 [0.990, 1.002] |
| hard three-house cap | 0.974 [0.955, 0.991]* | 1.000 [0.997, 1.003] | 0.975 [0.957, 0.993]* | 0.996 [0.991, 1.002] |
| housing lock on (14) | 0.973 [0.962, 0.984]** | 1.001 [0.998, 1.003] | 0.973 [0.962, 0.984]** | 1.004 [1.000, 1.008] |
| simple bot | 0.945 [0.917, 0.973]** | 0.997 [0.994, 1.000] | 0.945 [0.917, 0.973]** | 0.997 [0.990, 1.005] |

(* the 95% interval excludes 1; ** the Bonferroni-adjusted one does too. "The same games": the variant's rule never came into play, so every game went exactly as under the engine's rules.)

- strongest known challenger: 1.263 [1.234, 1.292] under the engine's rules (better); no variant changes it detectably (variant ÷ engine rules between 0.959 and 1.003)
- hard three-house cap: 0.794 [0.780, 0.809] under the engine's rules (worse); changed by build any time × 0.974 [0.955, 0.991]; any time + auctions × 0.975 [0.957, 0.993]
- housing lock on (14): 1.061 [1.052, 1.070] under the engine's rules (better); changed by build any time × 0.973 [0.962, 0.984]; any time + auctions × 0.973 [0.962, 0.984]
- simple bot: 0.610 [0.591, 0.630] under the engine's rules (worse); changed by build any time × 0.945 [0.917, 0.973]; any time + auctions × 0.945 [0.917, 0.973]

## standard, 2 players

Left out: three houses first (the same genome as the final agent).

| Candidate | engine rules | build any time | house auctions | any time + auctions | mortgaged stations count |
|---|---|---|---|---|---|
| strongest known challenger | 1.171 [1.153, 1.191] | 1.193 [1.175, 1.213] | 1.172 [1.154, 1.192] | 1.193 [1.175, 1.212] | 1.176 [1.157, 1.196] |
| hard three-house cap | 0.942 [0.936, 0.949] | 0.945 [0.938, 0.951] | 0.943 [0.936, 0.949] | 0.945 [0.938, 0.951] | 0.942 [0.935, 0.949] |
| housing lock off | 0.962 [0.958, 0.966] | 0.964 [0.960, 0.968] | 0.962 [0.958, 0.966] | 0.964 [0.960, 0.968] | 0.962 [0.958, 0.966] |
| simple bot | 0.411 [0.399, 0.422] | 0.444 [0.433, 0.457] | 0.411 [0.399, 0.423] | 0.444 [0.432, 0.457] | 0.411 [0.400, 0.423] |

Variant ÷ engine rules:

| Candidate | build any time | house auctions | any time + auctions | mortgaged stations count |
|---|---|---|---|---|
| strongest known challenger | 1.019 [1.008, 1.029]** | 1.001 [1.000, 1.001]* | 1.018 [1.008, 1.029]** | 1.004 [1.001, 1.006]* |
| hard three-house cap | 1.002 [0.996, 1.010] | 1.000 [1.000, 1.001] | 1.002 [0.996, 1.010] | 1.000 [0.998, 1.001] |
| housing lock off | 1.002 [0.998, 1.006] | 1.000 [1.000, 1.001] | 1.002 [0.998, 1.006] | 1.000 [0.999, 1.002] |
| simple bot | 1.082 [1.065, 1.101]** | 1.000 [0.999, 1.001] | 1.082 [1.065, 1.101]** | 1.001 [0.996, 1.007] |

(* the 95% interval excludes 1; ** the Bonferroni-adjusted one does too. "The same games": the variant's rule never came into play, so every game went exactly as under the engine's rules.)

- strongest known challenger: 1.171 [1.153, 1.191] under the engine's rules (better); changed by build any time × 1.019 [1.008, 1.029]; house auctions × 1.001 [1.000, 1.001]; any time + auctions × 1.018 [1.008, 1.029]; mortgaged stations count × 1.004 [1.001, 1.006]
- hard three-house cap: 0.942 [0.936, 0.949] under the engine's rules (worse); no variant changes it detectably (variant ÷ engine rules between 0.996 and 1.010)
- housing lock off: 0.962 [0.958, 0.966] under the engine's rules (worse); no variant changes it detectably (variant ÷ engine rules between 0.998 and 1.006)
- simple bot: 0.411 [0.399, 0.422] under the engine's rules (worse); changed by build any time × 1.082 [1.065, 1.101]; any time + auctions × 1.082 [1.065, 1.101]

## championship, 4 players

| Candidate | engine rules | build any time | house auctions | any time + auctions | mortgaged stations count |
|---|---|---|---|---|---|
| strongest known challenger | 1.326 [1.291, 1.363] | 1.265 [1.231, 1.300] | 1.318 [1.283, 1.356] | 1.257 [1.224, 1.292] | 1.324 [1.288, 1.360] |
| hard three-house cap | 0.870 [0.855, 0.885] | 0.864 [0.848, 0.880] | 0.878 [0.861, 0.893] | 0.869 [0.853, 0.885] | 0.873 [0.858, 0.888] |
| three houses first | 0.992 [0.985, 0.999] | 0.994 [0.989, 1.000] | 0.996 [0.988, 1.005] | 0.992 [0.986, 0.999] | 0.994 [0.987, 1.001] |
| housing lock off | 0.911 [0.897, 0.927] | 0.927 [0.912, 0.942] | 0.904 [0.890, 0.920] | 0.922 [0.908, 0.936] | 0.911 [0.897, 0.926] |
| simple bot | 0.460 [0.441, 0.480] | 0.626 [0.602, 0.650] | 0.459 [0.440, 0.479] | 0.622 [0.598, 0.646] | 0.468 [0.449, 0.488] |

Variant ÷ engine rules:

| Candidate | build any time | house auctions | any time + auctions | mortgaged stations count |
|---|---|---|---|---|
| strongest known challenger | 0.954 [0.926, 0.981]* | 0.994 [0.979, 1.009] | 0.948 [0.920, 0.975]** | 0.998 [0.990, 1.006] |
| hard three-house cap | 0.992 [0.971, 1.016] | 1.008 [0.995, 1.021] | 0.998 [0.976, 1.022] | 1.004 [0.996, 1.011] |
| three houses first | 1.003 [0.994, 1.012] | 1.005 [0.997, 1.013] | 1.001 [0.991, 1.010] | 1.002 [0.999, 1.006] |
| housing lock off | 1.018 [0.995, 1.040] | 0.993 [0.981, 1.005] | 1.012 [0.990, 1.034] | 1.000 [0.993, 1.008] |
| simple bot | 1.361 [1.304, 1.417]** | 0.997 [0.983, 1.011] | 1.352 [1.297, 1.408]** | 1.018 [1.004, 1.031]* |

(* the 95% interval excludes 1; ** the Bonferroni-adjusted one does too. "The same games": the variant's rule never came into play, so every game went exactly as under the engine's rules.)

- strongest known challenger: 1.326 [1.291, 1.363] under the engine's rules (better); changed by build any time × 0.954 [0.926, 0.981]; any time + auctions × 0.948 [0.920, 0.975]
- hard three-house cap: 0.870 [0.855, 0.885] under the engine's rules (worse); no variant changes it detectably (variant ÷ engine rules between 0.971 and 1.022)
- three houses first: 0.992 [0.985, 0.999] under the engine's rules (worse); no variant changes it detectably (variant ÷ engine rules between 0.991 and 1.013)
- housing lock off: 0.911 [0.897, 0.927] under the engine's rules (worse); no variant changes it detectably (variant ÷ engine rules between 0.981 and 1.040)
- simple bot: 0.460 [0.441, 0.480] under the engine's rules (worse); changed by build any time × 1.361 [1.304, 1.417]; any time + auctions × 1.352 [1.297, 1.408]; mortgaged stations count × 1.018 [1.004, 1.031]

## How often the simplification binds

Between final agents. A contested moment: two or more players want more houses than the bank has.

| Setting | Variant | Games with a contested moment | Houses auctioned per game |
|---|---|---|---|
| standard 4p | engine rules | 5.0% | 0.00 |
| standard 4p | house auctions | 5.0% | 0.15 |
| standard 4p | any time + auctions | 1.0% | 0.02 |
| standard 2p | engine rules | 1.1% | 0.00 |
| standard 2p | house auctions | 1.1% | 0.03 |
| standard 2p | any time + auctions | 0.3% | 0.01 |
| championship 4p | engine rules | 42.8% | 0.00 |
| championship 4p | house auctions | 42.8% | 2.29 |
| championship 4p | any time + auctions | 24.7% | 0.98 |

## Seat order, simple bots

| Players | Variant | First player | Last player |
|---|---|---|---|
| 4 | engine rules | 1.064 [1.040, 1.089] | 0.891 |
| 4 | build any time | 1.084 [1.060, 1.109] | 0.874 |
| 4 | house auctions | 1.065 [1.041, 1.090] | 0.890 |
| 4 | any time + auctions | 1.085 [1.060, 1.109] | 0.874 |
| 4 | mortgaged stations count | 1.066 [1.042, 1.091] | 0.890 |
| 6 | engine rules | 1.177 [1.144, 1.210] | 0.833 |
| 6 | build any time | 1.171 [1.139, 1.205] | 0.837 |
| 6 | house auctions | 1.178 [1.146, 1.212] | 0.831 |
| 6 | any time + auctions | 1.171 [1.138, 1.204] | 0.837 |
| 6 | mortgaged stations count | 1.177 [1.144, 1.210] | 0.834 |

## Confirmation on fresh seeds

The official 4-player agent with the housing lock (at 14 houses) ÷ the agent as it is, on 40,000 paired games no other comparison played: 1.049 [1.043, 1.055].

## Change from the previous run (same seeds)

Variants without house auctions reproduce the previous run exactly in 39 of 39 cells. With house auctions (after the auction fix):

| Setting | Variant | Candidate | Before | After | Change [95%, runs as if independent] |
|---|---|---|---|---|---|
| standard 4p | house auctions | strongest known challenger | 1.262 | 1.262 | +0.000 [-0.041, +0.041] |
| standard 4p | house auctions | hard three-house cap | 0.794 | 0.795 | +0.000 [-0.020, +0.020] |
| standard 4p | house auctions | housing lock on (14) | 1.061 | 1.061 | +0.001 [-0.012, +0.014] |
| standard 4p | house auctions | simple bot | 0.609 | 0.608 | -0.001 [-0.029, +0.027] |
| standard 4p | any time + auctions | strongest known challenger | 1.240 | 1.239 | -0.000 [-0.040, +0.040] |
| standard 4p | any time + auctions | hard three-house cap | 0.774 | 0.775 | +0.000 [-0.019, +0.019] |
| standard 4p | any time + auctions | housing lock on (14) | 1.032 | 1.032 | +0.000 [-0.011, +0.011] |
| standard 4p | any time + auctions | simple bot | 0.576 | 0.576 | +0.000 [-0.027, +0.027] |
| standard 2p | house auctions | strongest known challenger | 1.172 | 1.172 | +0.000 [-0.027, +0.027] |
| standard 2p | house auctions | hard three-house cap | 0.943 | 0.943 | +0.000 [-0.010, +0.010] |
| standard 2p | house auctions | housing lock off | 0.962 | 0.962 | +0.000 [-0.005, +0.006] |
| standard 2p | house auctions | simple bot | 0.411 | 0.411 | -0.000 [-0.016, +0.016] |
| standard 2p | any time + auctions | strongest known challenger | 1.193 | 1.193 | +0.000 [-0.026, +0.027] |
| standard 2p | any time + auctions | hard three-house cap | 0.945 | 0.945 | +0.000 [-0.009, +0.010] |
| standard 2p | any time + auctions | housing lock off | 0.964 | 0.964 | -0.000 [-0.005, +0.005] |
| standard 2p | any time + auctions | simple bot | 0.444 | 0.444 | +0.000 [-0.017, +0.017] |
| championship 4p | house auctions | strongest known challenger | 1.323 | 1.318 | -0.005 [-0.057, +0.047] |
| championship 4p | house auctions | hard three-house cap | 0.877 | 0.878 | +0.000 [-0.022, +0.023] |
| championship 4p | house auctions | three houses first | 0.999 | 0.996 | -0.003 [-0.014, +0.009] |
| championship 4p | house auctions | housing lock off | 0.903 | 0.904 | +0.001 [-0.020, +0.021] |
| championship 4p | house auctions | simple bot | 0.457 | 0.459 | +0.001 [-0.026, +0.029] |
| championship 4p | any time + auctions | strongest known challenger | 1.262 | 1.257 | -0.005 [-0.053, +0.043] |
| championship 4p | any time + auctions | hard three-house cap | 0.870 | 0.869 | -0.001 [-0.023, +0.022] |
| championship 4p | any time + auctions | three houses first | 0.992 | 0.992 | +0.000 [-0.008, +0.009] |
| championship 4p | any time + auctions | housing lock off | 0.923 | 0.922 | -0.001 [-0.022, +0.019] |
| championship 4p | any time + auctions | simple bot | 0.624 | 0.622 | -0.001 [-0.035, +0.033] |
