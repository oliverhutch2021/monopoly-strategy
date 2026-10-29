# Unconventional strategies (v0.4)

Ratios are win credit against a table of meta agents, divided by the meta agent's own credit on the same games (above 1 beats the meta agent), with 95% intervals.

## Official rules

| Players | Control arm | Tactics arm | Tactics / control | Best find (re-measured) | Its tactics |
|---|---|---|---|---|---|
| 2 | 1.472 | 1.617 [1.598, 1.636] | 1.098 [1.089, 1.108] | 1.877 [1.833, 1.923] | auction sniping, housing lock, borrowing to build, card counting, playing the clock |
| 3 | 1.182 | 1.254 [1.236, 1.272] | 1.061 [1.047, 1.075] | 1.481 [1.440, 1.523] | auction sniping, borrowing to build, card counting, taxing the leader |
| 4 | 1.354 | 1.296 [1.277, 1.317] | 0.957 [0.942, 0.971] | 1.710 [1.652, 1.776] | housing lock |
| 5 | 1.113 | 1.132 [1.117, 1.146] | 1.017 [0.999, 1.034] | 1.438 [1.383, 1.498] | auction sniping, housing lock, dodging, card counting |
| 6 | 1.416 | 1.363 [1.338, 1.387] | 0.962 [0.950, 0.974] | 1.520 [1.462, 1.579] | auction sniping, housing lock |

- **2 players.** 6,000 strategies tried, 106 kinds of play kept. League mixture: find 2 100%. Can invade a table of meta agents: find 1 1.95x; find 2 1.92x; find 3 1.82x; best jail by the numbers 1.69x; best taxing the leader 1.79x.
- **3 players.** 7,000 strategies tried, 104 kinds of play kept. League mixture: best playing the clock 100%. Can invade a table of meta agents: find 1 1.59x; find 2 1.60x; find 3 1.57x; best housing lock 1.53x; best jail by the numbers 1.30x; best dodging 1.44x; best playing the clock 1.44x.
- **4 players.** 5,000 strategies tried, 105 kinds of play kept. League mixture: meta agent 100%. Can invade a table of meta agents: find 1 1.88x; find 2 1.83x; find 3 1.79x; best jail by the numbers 1.82x; best dodging 1.68x; best taxing the leader 1.55x.
- **5 players.** 4,000 strategies tried, 91 kinds of play kept. League mixture: meta agent 100%. Can invade a table of meta agents: find 1 1.49x; find 2 1.41x; find 3 1.32x; best playing the clock 1.31x.
- **6 players.** 3,600 strategies tried, 99 kinds of play kept. League mixture: meta agent 100%. Can invade a table of meta agents: find 1 1.50x; find 2 1.60x; find 3 1.49x.

## Championship rules

| Players | Control arm | Tactics arm | Tactics / control | Best find (re-measured) | Its tactics |
|---|---|---|---|---|---|
| 2 | 1.057 | 1.482 [1.469, 1.495] | 1.402 [1.391, 1.414] | 1.583 [1.555, 1.613] | auction sniping, housing lock, borrowing to build, card counting |
| 3 | 1.687 | 1.690 [1.664, 1.717] | 1.002 [0.991, 1.013] | 1.886 [1.834, 1.938] | auction sniping, housing lock, borrowing to build, dodging, card counting, taxing the leader |
| 4 | 1.215 | 1.296 [1.274, 1.319] | 1.067 [1.049, 1.084] | 1.645 [1.589, 1.708] | auction sniping, housing lock, borrowing to build, dodging, card counting |
| 5 | 1.108 | 1.206 [1.194, 1.218] | 1.088 [1.080, 1.096] | 1.395 [1.351, 1.441] | no tactics |
| 6 | 1.178 | 1.250 [1.236, 1.264] | 1.061 [1.051, 1.072] | 1.213 [1.187, 1.241] | auction sniping, card counting |

- **2 players.** 5,400 strategies tried, 93 kinds of play kept. League mixture: best jail by the numbers 46%; find 1 38%; find 2 15%. Can invade a table of meta agents: find 1 1.54x; find 2 1.49x; find 3 1.50x; best jail by the numbers 1.52x; best playing the clock 1.48x.
- **3 players.** 6,000 strategies tried, 110 kinds of play kept. League mixture: find 2 100%. Can invade a table of meta agents: find 1 2.00x; find 2 1.97x; find 3 1.94x; best jail by the numbers 1.96x.
- **4 players.** 5,000 strategies tried, 93 kinds of play kept. League mixture: meta agent 44%; find 3 30%; best jail by the numbers 26%. Can invade a table of meta agents: find 1 1.63x; find 2 1.54x; find 3 1.53x; best jail by the numbers 1.59x; best taxing the leader 1.14x.
- **5 players.** 1,100 strategies tried, 62 kinds of play kept. League mixture: simple bot 100%. Can invade a table of meta agents: find 1 1.46x; find 2 1.38x; find 3 1.34x; best jail by the numbers 1.33x.
- **6 players.** 800 strategies tried, 54 kinds of play kept. League mixture: meta agent 46%; find 1 39%; simple bot 16%. Can invade a table of meta agents: find 1 1.25x; find 2 1.14x; best taxing the leader 1.05x.

## Tactics among finds that beat the meta agent (interval above 1)

- housing lock: 66 of 85
- auction sniping: 56 of 85
- card counting: 52 of 85
- borrowing to build: 48 of 85
- dodging: 35 of 85
- playing the clock: 32 of 85
- taxing the leader: 25 of 85
- jail by the numbers: 17 of 85
