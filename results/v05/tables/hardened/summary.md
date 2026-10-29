# Hardened meta agents (v0.5)

Ratios are a strategy's win credit at a table of meta agents, divided by the meta agent's own credit in that seat on the same games (above 1 beats the meta agent), with 95% intervals. *Before* is v0.4's measurement against the v0.3 agents; *after* repeats it against the v0.5 agents.

## Official rules

| Players | Hardening rounds | v0.4's exploits, worst: before -> after | Challenger search: before -> after | MAP-Elites: before -> after | New agent at a table of old | Old agent at a table of new | New agent's moves |
|---|---|---|---|---|---|---|---|
| 2 | 3 (kept round 3) | 1.907 -> 0.906 [0.885, 0.928] (v0.4 find 1) | 1.617 -> 1.150 [1.138, 1.164] | 1.877 -> 1.113 [1.086, 1.140] | 1.932 [1.884, 1.983] | 0.425 [0.408, 0.441] | auction sniping, housing lock, borrowing to build, card counting, playing the clock |
| 3 | 4 (kept round 4) | 1.488 -> 1.167 [1.128, 1.208] (v0.4 find 2) | 1.254 -> 1.452 [1.429, 1.473] | 1.481 -> 1.583 [1.534, 1.636] | 1.299 [1.263, 1.340] | 1.137 [1.098, 1.178] | auction sniping, housing lock, borrowing to build, taxing the leader |
| 4 | 4 (kept round 1) | 1.687 -> 1.285 [1.242, 1.329] (v0.4 find 2) | 1.296 -> 1.048 [1.032, 1.067] | 1.710 -> 1.108 [1.071, 1.149] | 1.225 [1.190, 1.262] | 0.876 [0.848, 0.905] | borrowing to build, card counting |
| 5 | 3 (kept round 3) | 1.505 -> 0.503 [0.476, 0.532] (v0.4 new-moves challenger) | 1.132 -> 1.120 [1.105, 1.137] | 1.438 -> 1.144 [1.103, 1.190] | 0.923 [0.889, 0.957] | 0.460 [0.435, 0.485] | dodging |
| 6 | 4 (kept round 2) | 1.517 -> 5.081 [4.869, 5.315] (v0.4 find 2) | 1.363 -> 5.202 [5.088, 5.321] | 1.520 -> 5.258 [5.034, 5.502] | 0.739 [0.703, 0.776] | 5.165 [4.953, 5.398] | housing lock, jail by the numbers |

## Championship rules

| Players | Hardening rounds | v0.4's exploits, worst: before -> after | Challenger search: before -> after | MAP-Elites: before -> after | New agent at a table of old | Old agent at a table of new | New agent's moves |
|---|---|---|---|---|---|---|---|
| 2 | 3 (kept round 3) | 1.577 -> 0.877 [0.855, 0.901] (v0.4 league: best jail by the numbers) | 1.482 -> 1.021 [1.010, 1.031] | 1.583 -> 1.040 [1.016, 1.065] | 1.563 [1.534, 1.591] | 0.393 [0.376, 0.408] | auction sniping, housing lock, borrowing to build, dodging |
| 3 | 4 (kept round 4) | 1.899 -> 1.230 [1.192, 1.268] (v0.4 new-moves challenger) | 1.690 -> 1.449 [1.426, 1.471] | 1.886 -> 1.530 [1.483, 1.583] | 1.721 [1.667, 1.776] | 1.104 [1.067, 1.141] | housing lock, borrowing to build, dodging, card counting |
| 4 | 4 (kept round 4) | 1.660 -> 0.944 [0.906, 0.984] (v0.4 find 3) | 1.296 -> 1.139 [1.116, 1.163] | 1.645 -> 1.307 [1.258, 1.357] | 0.975 [0.932, 1.018] | 0.505 [0.477, 0.534] | housing lock, borrowing to build, dodging |
| 5 | 1 (kept round 1) | 1.436 -> 0.691 [0.654, 0.731] (v0.4 find 3) | 1.206 -> 1.555 [1.525, 1.585] | 1.395 -> 1.220 [1.170, 1.275] | 0.850 [0.822, 0.878] | 0.724 [0.689, 0.759] | borrowing to build |
| 6 | 4 (kept round 3) | 1.265 -> 0.516 [0.486, 0.550] (v0.4 new-moves challenger) | 1.250 -> 1.509 [1.481, 1.540] | 1.213 -> 1.751 [1.678, 1.821] | 1.106 [1.081, 1.131] | 0.504 [0.474, 0.536] | auction sniping, housing lock |

## Which new moves do the work (v0.4's finds, one move switched off at a time)

| Move | Strategies using it | Switching it off costs 0.05 or more | Average change |
|---|---|---|---|
| auction sniping | 28 | 5 | -0.026 |
| housing lock | 30 | 13 | -0.057 |
| borrowing to build | 25 | 13 | -0.107 |
| jail by the numbers | 6 | 0 | -0.001 |
| dodging | 16 | 1 | -0.011 |
| card counting | 23 | 6 | -0.026 |
| taxing the leader | 10 | 0 | -0.003 |
| playing the clock | 13 | 0 | +0.000 |
