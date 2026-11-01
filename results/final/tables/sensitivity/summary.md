# Rule sensitivity of the housing findings

Paired games per cell: 20,000. Ratio = the candidate's credit ÷ the final agent's in the same seat on the same games (95% bootstrap interval). "Variant ÷ engine rules" is that ratio under a variant divided by the ratio under the engine's own rules, from a bootstrap that resamples the same seeds in both: an interval that excludes 1 means the variant changes the candidate's edge. Variants: engine rules, build any time, house auctions, any time + auctions, mortgaged stations count, mortgage choice on transfer.

There are 65 variant ÷ engine-rules intervals below. At 95%, about 3 would exclude 1 by chance even if no variant mattered, so a lone exclusion is weak evidence; a consistent pattern across settings or variants is not. With Bonferroni-adjusted intervals (marked **), 12 of the 65 still exclude 1: those edges change (0 of them by less than 3% either way). Of the rest, 35 are equivalent within ±3% (the adjusted interval lies inside [0.97, 1.03], a tolerance set before the run: no change big enough to reverse a verdict here is plausible), 0 are untouched (the variant's rule never came into play) and 18 are inconclusive (a change of a few percent is still possible).

## standard, 4 players

Left out: three houses first (the same genome as the final agent).

| Candidate | engine rules | build any time | house auctions | any time + auctions | mortgaged stations count | mortgage choice on transfer |
|---|---|---|---|---|---|---|
| strongest known challenger | 1.263 [1.234, 1.292] | 1.240 [1.212, 1.269] | 1.262 [1.234, 1.292] | 1.239 [1.211, 1.268] | 1.257 [1.228, 1.287] | 1.246 [1.219, 1.274] |
| hard three-house cap | 0.794 [0.780, 0.809] | 0.774 [0.760, 0.787] | 0.795 [0.780, 0.809] | 0.775 [0.761, 0.788] | 0.792 [0.777, 0.806] | 0.779 [0.765, 0.793] |
| housing lock on (14) | 1.061 [1.052, 1.070] | 1.032 [1.025, 1.040] | 1.061 [1.052, 1.070] | 1.032 [1.025, 1.040] | 1.065 [1.056, 1.074] | 1.048 [1.039, 1.056] |
| simple bot | 0.610 [0.591, 0.630] | 0.576 [0.557, 0.596] | 0.608 [0.589, 0.628] | 0.576 [0.557, 0.596] | 0.608 [0.588, 0.628] | 0.577 [0.558, 0.597] |

Variant ÷ engine rules:

| Candidate | build any time | house auctions | any time + auctions | mortgaged stations count | mortgage choice on transfer |
|---|---|---|---|---|---|
| strongest known challenger | 0.982 [0.960, 1.003] | 1.000 [0.997, 1.002] ≈ | 0.982 [0.959, 1.003] | 0.996 [0.990, 1.002] ≈ | 0.987 [0.974, 1.000]* |
| hard three-house cap | 0.974 [0.955, 0.991]* | 1.000 [0.997, 1.003] ≈ | 0.975 [0.957, 0.993]* | 0.996 [0.991, 1.002] ≈ | 0.981 [0.968, 0.993]* |
| housing lock on (14) | 0.973 [0.962, 0.984]** | 1.001 [0.998, 1.003] ≈ | 0.973 [0.962, 0.984]** | 1.004 [1.000, 1.008] ≈ | 0.987 [0.979, 0.996]* ≈ |
| simple bot | 0.945 [0.917, 0.973]** | 0.997 [0.994, 1.000] ≈ | 0.945 [0.917, 0.973]** | 0.997 [0.990, 1.005] ≈ | 0.946 [0.929, 0.964]** |

(* the 95% interval excludes 1; ** the Bonferroni-adjusted one does too; ≈ the adjusted interval lies within ±3%. "The same games": the variant's rule never came into play, so every game went exactly as under the engine's rules.)

- strongest known challenger: 1.263 [1.234, 1.292] under the engine's rules (better); inconclusive under build any time, any time + auctions, mortgage choice on transfer; equivalent within ±3% under house auctions, mortgaged stations count
- hard three-house cap: 0.794 [0.780, 0.809] under the engine's rules (worse); inconclusive under build any time, any time + auctions, mortgage choice on transfer; equivalent within ±3% under house auctions, mortgaged stations count
- housing lock on (14): 1.061 [1.052, 1.070] under the engine's rules (better); changed (adjusted) by build any time × 0.973 [0.955, 0.992]; any time + auctions × 0.973 [0.955, 0.992]; equivalent within ±3% under house auctions, mortgaged stations count, mortgage choice on transfer
- simple bot: 0.610 [0.591, 0.630] under the engine's rules (worse); changed (adjusted) by build any time × 0.945 [0.898, 0.995]; any time + auctions × 0.945 [0.898, 0.995]; mortgage choice on transfer × 0.946 [0.918, 0.975]; equivalent within ±3% under house auctions, mortgaged stations count

## standard, 2 players

Left out: three houses first (the same genome as the final agent).

| Candidate | engine rules | build any time | house auctions | any time + auctions | mortgaged stations count | mortgage choice on transfer |
|---|---|---|---|---|---|---|
| strongest known challenger | 1.171 [1.153, 1.191] | 1.193 [1.175, 1.213] | 1.172 [1.154, 1.192] | 1.193 [1.175, 1.212] | 1.176 [1.157, 1.196] | 1.172 [1.153, 1.191] |
| hard three-house cap | 0.942 [0.936, 0.949] | 0.945 [0.938, 0.951] | 0.943 [0.936, 0.949] | 0.945 [0.938, 0.951] | 0.942 [0.935, 0.949] | 0.943 [0.936, 0.949] |
| housing lock off | 0.962 [0.958, 0.966] | 0.964 [0.960, 0.968] | 0.962 [0.958, 0.966] | 0.964 [0.960, 0.968] | 0.962 [0.958, 0.966] | 0.962 [0.958, 0.966] |
| simple bot | 0.411 [0.399, 0.422] | 0.444 [0.433, 0.457] | 0.411 [0.399, 0.423] | 0.444 [0.432, 0.457] | 0.411 [0.400, 0.423] | 0.411 [0.400, 0.423] |

Variant ÷ engine rules:

| Candidate | build any time | house auctions | any time + auctions | mortgaged stations count | mortgage choice on transfer |
|---|---|---|---|---|---|
| strongest known challenger | 1.019 [1.008, 1.029]** | 1.001 [1.000, 1.001]* ≈ | 1.018 [1.008, 1.029]** | 1.004 [1.001, 1.006]* ≈ | 1.000 [0.998, 1.002] ≈ |
| hard three-house cap | 1.002 [0.996, 1.010] ≈ | 1.000 [1.000, 1.001] ≈ | 1.002 [0.996, 1.010] ≈ | 1.000 [0.998, 1.001] ≈ | 1.000 [0.999, 1.001] ≈ |
| housing lock off | 1.002 [0.998, 1.006] ≈ | 1.000 [1.000, 1.001] ≈ | 1.002 [0.998, 1.006] ≈ | 1.000 [0.999, 1.002] ≈ | 1.000 [0.999, 1.001] ≈ |
| simple bot | 1.082 [1.065, 1.101]** | 1.000 [0.999, 1.001] ≈ | 1.082 [1.065, 1.101]** | 1.001 [0.996, 1.007] ≈ | 1.000 [0.998, 1.003] ≈ |

(* the 95% interval excludes 1; ** the Bonferroni-adjusted one does too; ≈ the adjusted interval lies within ±3%. "The same games": the variant's rule never came into play, so every game went exactly as under the engine's rules.)

- strongest known challenger: 1.171 [1.153, 1.191] under the engine's rules (better); changed (adjusted) by build any time × 1.019 [1.000, 1.037]; any time + auctions × 1.018 [1.000, 1.037]; equivalent within ±3% under house auctions, mortgaged stations count, mortgage choice on transfer
- hard three-house cap: 0.942 [0.936, 0.949] under the engine's rules (worse); equivalent within ±3% under build any time, house auctions, any time + auctions, mortgaged stations count, mortgage choice on transfer
- housing lock off: 0.962 [0.958, 0.966] under the engine's rules (worse); equivalent within ±3% under build any time, house auctions, any time + auctions, mortgaged stations count, mortgage choice on transfer
- simple bot: 0.411 [0.399, 0.422] under the engine's rules (worse); changed (adjusted) by build any time × 1.082 [1.051, 1.114]; any time + auctions × 1.082 [1.051, 1.114]; equivalent within ±3% under house auctions, mortgaged stations count, mortgage choice on transfer

## championship, 4 players

| Candidate | engine rules | build any time | house auctions | any time + auctions | mortgaged stations count | mortgage choice on transfer |
|---|---|---|---|---|---|---|
| strongest known challenger | 1.326 [1.291, 1.363] | 1.265 [1.231, 1.300] | 1.318 [1.283, 1.356] | 1.257 [1.224, 1.292] | 1.324 [1.288, 1.360] | 1.314 [1.279, 1.351] |
| hard three-house cap | 0.870 [0.855, 0.885] | 0.864 [0.848, 0.880] | 0.878 [0.861, 0.893] | 0.869 [0.853, 0.885] | 0.873 [0.858, 0.888] | 0.879 [0.863, 0.893] |
| three houses first | 0.992 [0.985, 0.999] | 0.994 [0.989, 1.000] | 0.996 [0.988, 1.005] | 0.992 [0.986, 0.999] | 0.994 [0.987, 1.001] | 0.994 [0.987, 1.000] |
| housing lock off | 0.911 [0.897, 0.927] | 0.927 [0.912, 0.942] | 0.904 [0.890, 0.920] | 0.922 [0.908, 0.936] | 0.911 [0.897, 0.926] | 0.914 [0.899, 0.929] |
| simple bot | 0.460 [0.441, 0.480] | 0.626 [0.602, 0.650] | 0.459 [0.440, 0.479] | 0.622 [0.598, 0.646] | 0.468 [0.449, 0.488] | 0.463 [0.444, 0.483] |

Variant ÷ engine rules:

| Candidate | build any time | house auctions | any time + auctions | mortgaged stations count | mortgage choice on transfer |
|---|---|---|---|---|---|
| strongest known challenger | 0.954 [0.926, 0.981]* | 0.994 [0.979, 1.009] | 0.948 [0.920, 0.975]** | 0.998 [0.990, 1.006] ≈ | 0.991 [0.973, 1.009] |
| hard three-house cap | 0.992 [0.971, 1.016] | 1.008 [0.995, 1.021] | 0.998 [0.976, 1.022] | 1.004 [0.996, 1.011] ≈ | 1.009 [0.993, 1.026] |
| three houses first | 1.003 [0.994, 1.012] ≈ | 1.005 [0.997, 1.013] ≈ | 1.001 [0.991, 1.010] ≈ | 1.002 [0.999, 1.006] ≈ | 1.002 [0.993, 1.010] ≈ |
| housing lock off | 1.018 [0.995, 1.040] | 0.993 [0.981, 1.005] ≈ | 1.012 [0.990, 1.034] | 1.000 [0.993, 1.008] ≈ | 1.003 [0.987, 1.020] |
| simple bot | 1.361 [1.304, 1.417]** | 0.997 [0.983, 1.011] ≈ | 1.352 [1.297, 1.408]** | 1.018 [1.004, 1.031]* | 1.006 [0.982, 1.031] |

(* the 95% interval excludes 1; ** the Bonferroni-adjusted one does too; ≈ the adjusted interval lies within ±3%. "The same games": the variant's rule never came into play, so every game went exactly as under the engine's rules.)

- strongest known challenger: 1.326 [1.291, 1.363] under the engine's rules (better); changed (adjusted) by any time + auctions × 0.948 [0.901, 0.997]; inconclusive under build any time, house auctions, mortgage choice on transfer; equivalent within ±3% under mortgaged stations count
- hard three-house cap: 0.870 [0.855, 0.885] under the engine's rules (worse); inconclusive under build any time, house auctions, any time + auctions, mortgage choice on transfer; equivalent within ±3% under mortgaged stations count
- three houses first: 0.992 [0.985, 0.999] under the engine's rules (worse); equivalent within ±3% under build any time, house auctions, any time + auctions, mortgaged stations count, mortgage choice on transfer
- housing lock off: 0.911 [0.897, 0.927] under the engine's rules (worse); inconclusive under build any time, any time + auctions, mortgage choice on transfer; equivalent within ±3% under house auctions, mortgaged stations count
- simple bot: 0.460 [0.441, 0.480] under the engine's rules (worse); changed (adjusted) by build any time × 1.361 [1.267, 1.461]; any time + auctions × 1.352 [1.260, 1.452]; inconclusive under mortgaged stations count, mortgage choice on transfer; equivalent within ±3% under house auctions

## The housing lock, taken apart

The official 4-player agent, with the housing lock's two behaviours switched on separately: deferring hotels while houses are short, and protecting buildings (when raising cash, mortgage everything else before selling one). Each arm ÷ the agent with neither, in the same seat on the same games, and the change in its outright win rate (official rules: a game stopped by the time limit is a loss for everyone). The last column compares the two strongest arms directly. 95% bootstrap intervals.

| Other three seats | Games | defer hotels only | protect buildings only | both (the housing lock) | protect only ÷ both |
|---|---|---|---|---|---|
| final agents (the confirmation's games) | 40,000 | 0.990 [0.986, 0.994], -0.25 pp [-0.34, -0.15] | 1.062 [1.056, 1.067], +1.55 pp [+1.42, +1.68] | 1.049 [1.043, 1.055], +1.23 pp [+1.08, +1.38] | 1.012 [1.009, 1.016], +0.32 pp [+0.23, +0.42] |
| final agents (fresh games) | 20,000 | 0.989 [0.983, 0.995], -0.27 pp [-0.42, -0.11] | 1.071 [1.063, 1.079], +1.79 pp [+1.60, +1.98] | 1.061 [1.051, 1.070], +1.53 pp [+1.31, +1.75] | 1.010 [1.005, 1.015], +0.26 pp [+0.12, +0.39] |
| simple bots (fresh games) | 20,000 | 0.992 [0.987, 0.996], -0.22 pp [-0.34, -0.10] | 1.056 [1.049, 1.063], +1.49 pp [+1.30, +1.67] | 1.048 [1.040, 1.056], +1.29 pp [+1.07, +1.49] | 1.007 [1.003, 1.012], +0.21 pp [+0.08, +0.33] |
| equal mixture per seat (fresh games) | 20,000 | 0.994 [0.989, 0.999], -0.16 pp [-0.29, -0.03] | 1.071 [1.063, 1.078], +1.89 pp [+1.70, +2.08] | 1.063 [1.054, 1.071], +1.68 pp [+1.45, +1.90] | 1.008 [1.003, 1.012], +0.21 pp [+0.09, +0.34] |
| known challengers (fresh games) | 20,000 | 1.000 [0.998, 1.002], -0.01 pp [-0.12, +0.10] | 1.060 [1.055, 1.065], +3.19 pp [+2.94, +3.45] | 1.060 [1.054, 1.065], +3.17 pp [+2.90, +3.44] | 1.000 [0.999, 1.002], +0.03 pp [-0.08, +0.12] |

## How often the simplifications bind

Between final agents. A contested moment: two or more players want more houses (or hotels) than the bank has. The engine never auctions hotels; the official rules auction them too. Mortgaged deeds received: in a trade or from a bankrupt player, the moments the official choice to lift at once arises.

| Setting | Variant | Games with contested houses | Houses auctioned per game | Games with contested hotels | Mortgaged deeds received per game | Lifted at once per game |
|---|---|---|---|---|---|---|
| standard 4p | engine rules | 5.0% | 0.00 | 0.0% | 14.12 | 0.00 |
| standard 4p | house auctions | 5.0% | 0.15 | 0.0% | 14.13 | 0.00 |
| standard 4p | any time + auctions | 1.0% | 0.02 | 0.0% | 13.66 | 0.00 |
| standard 4p | mortgage choice on transfer | 5.2% | 0.00 | 0.0% | 13.98 | 10.73 |
| standard 2p | engine rules | 1.1% | 0.00 | 0.0% | 0.24 | 0.00 |
| standard 2p | house auctions | 1.1% | 0.03 | 0.0% | 0.24 | 0.00 |
| standard 2p | any time + auctions | 0.3% | 0.01 | 0.0% | 0.20 | 0.00 |
| standard 2p | mortgage choice on transfer | 1.1% | 0.00 | 0.0% | 0.24 | 0.23 |
| championship 4p | engine rules | 42.8% | 0.00 | 0.1% | 14.69 | 0.00 |
| championship 4p | house auctions | 42.8% | 2.29 | 0.0% | 14.67 | 0.00 |
| championship 4p | any time + auctions | 24.7% | 0.98 | 0.0% | 14.50 | 0.00 |
| championship 4p | mortgage choice on transfer | 45.5% | 0.00 | 0.0% | 14.63 | 11.84 |

## Seat order, simple bots

| Players | Variant | First player | Last player |
|---|---|---|---|
| 4 | engine rules | 1.064 [1.040, 1.089] | 0.891 |
| 4 | build any time | 1.084 [1.060, 1.109] | 0.874 |
| 4 | house auctions | 1.065 [1.041, 1.090] | 0.890 |
| 4 | any time + auctions | 1.085 [1.060, 1.109] | 0.874 |
| 4 | mortgaged stations count | 1.066 [1.042, 1.091] | 0.890 |
| 4 | mortgage choice on transfer | 1.072 [1.048, 1.097] | 0.888 |
| 6 | engine rules | 1.177 [1.144, 1.210] | 0.833 |
| 6 | build any time | 1.171 [1.139, 1.205] | 0.837 |
| 6 | house auctions | 1.178 [1.146, 1.212] | 0.831 |
| 6 | any time + auctions | 1.171 [1.138, 1.204] | 0.837 |
| 6 | mortgaged stations count | 1.177 [1.144, 1.210] | 0.834 |
| 6 | mortgage choice on transfer | 1.180 [1.147, 1.213] | 0.829 |

## Confirmation on fresh seeds

The official 4-player agent with the housing lock (at 14 houses) ÷ the agent as it is, on 40,000 paired games none of the comparisons above played (the confirmation of 2026-10-31, replayed as the factorial's first schedule): 1.049 [1.043, 1.055].

## Change from the previous run (same seeds)

65 of the 65 ratios the previous run also measured reproduce it exactly.

