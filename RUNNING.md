# Running the jobs on your PC

Heavy jobs run on your PC (WSL2 Ubuntu), one command each. Claude writes and tests the code, then
says **Your turn** in the chat when a run is ready. This file holds the exact steps.

## How it works

- The repo lives in `H:\monopoly-strategy`; in Ubuntu that's `/mnt/h/monopoly-strategy`.
- New code from Claude arrives as `.sync/claude.bundle`. `make sync` applies it, and every job runs it first.
- Every job can be stopped with Ctrl+C and resumed by running the same command again. Jobs run at low
  priority, so the PC stays usable, just slower.
- When a job finishes it commits its results, then writes `.sync/DONE-<job>.txt` and
  `.sync/from-pc.bundle`. Tell Claude in the chat; it reads both straight from the folder.
- For long runs, stop the PC from sleeping: Settings > System > Power > Screen and sleep > "Never" while
  plugged in.

## Step 1: one-time setup (about 30 minutes)

1. If WSL isn't installed yet: open **PowerShell as administrator** and run

   ```
   wsl --install -d Ubuntu-24.04
   ```

   Restart the PC, open **Ubuntu** from the Start menu, and choose a Linux user name and password.
2. In Ubuntu:

   ```
   cd /mnt/h/monopoly-strategy
   git -c core.autocrlf=true pull --ff-only .sync/claude.bundle main
   bash bootstrap.sh
   ```

   The `-c core.autocrlf=true` is only needed this first time, while the files still have Windows line
   endings; `bootstrap.sh` converts them. It also installs `make`, `uv` and Python 3.12, and asks for your
   Ubuntu password once.
3. It ends with a check table. If any line says FAIL, paste the table into the chat.

## Step 2: finish v0.3 (about 1 hour)

```
make v03
```

It runs the eight remaining v0.3 commands in order, using all 16 threads:

1. harden and validate the 6-player championship agent;
2. the championship trade curve;
3. championship seat advantage and strategy tweaks;
4. paired re-validation of the official-rules agents at 2-5 players;
5. meta agent vs simple bots under championship rules;
6. every-property trade curves against meta agents;
7. dashboard data;
8. figures.

When it prints "All done", tell Claude in the chat.

## Step 3: exploitability test (2-3 hours)

```
make sync && make exploit
```

For each table size under official and championship rules, it trains challengers against the meta
agents from three starting points with a much bigger search than hardening used, then measures the best
one against the meta agent on 40,000 paired games. It writes to `results/v04`; the v0.3 results stay as
they are. This is also the comparison run for the unconventional-strategy search that comes next: same
search, same games, but without the new moves. Step 4 runs it too, so you can skip straight there.

## Step 4: unconventional strategies (about 6 hours)

```
make sync && make v04
```

Can moves people rarely make beat the meta agents? The bots now have eight optional tactics: forcing an
auction when every rival is short of cash, hoarding houses so rivals can't build, mortgaging lone
properties to build, staying in jail by the numbers, dodging dangerous squares with the Speed Die,
counting cards, charging the leader more, and playing the clock near the time limit. For each table size
(4 players first, so a stopped run has the most-played sizes) under both rule sets it:

1. runs Step 3's test, old moves only: the control arm (skipped wherever Step 3 already ran);
2. runs the same test with the new moves allowed, and plays both challengers on the same 40,000 games;
3. runs a MAP-Elites search, which keeps the best strategy for each style of play rather than one winner;
4. re-measures the strongest finds on fresh games, and plays them all against each other in a league.

It writes to `results/v04`. Championship games at 5 and 6 players often run to the time limit, so those
two sizes take about half the time. Leave it overnight; `make watch` shows the games it's trying.

## Step 5: harden the meta agents (about 7 hours)

```
make sync && make v05
```

Step 4 found that every meta agent can be beaten by 1.2-1.9x, mostly with the new moves. This step makes
new meta agents that know those moves and are hard to exploit with them. It reads what Step 4 found from
`results/v04` and writes to `results/v05`. First, for every table size under both rule sets (4 players
first), it:

1. switches the new moves off one at a time in Step 4's strongest finds, to see which ones do the work;
2. hardens the meta agent in up to four rounds. Each round evolves agents at mixed tables (each other,
   plus everything Step 4 found that beat the old agent), keeps the one those exploits beat by the least,
   then runs a quick MAP-Elites search against it. Any new exploit joins the opponents for the next round;
3. checks the new agent on fresh games: Step 4's exploits against it and against the old agent, and the new
   and old agents at each other's tables.

Then, for every size again, it repeats Step 4's two searches against the new agents, with Step 4's
budgets and seeds, so the before and after numbers compare like for like. The new agents are saved in
`results/v05/tables/meta_agents_<mode>.json`; `results/v05/tables/hardened/summary.md` sums it all up.
If you stop it, `make v05` carries on where it was.

## Watching a run

Open a second Ubuntu window while a job runs and type:

```
cd /mnt/h/monopoly-strategy
make watch
```

Your browser opens a board that replays real games from the running job, move by move, next to the job's
progress: games simulated, games per second, which step it's on and its latest output. Every few seconds the
job saves one of the games it's about to play (who is playing, the seed and the rules), and the viewer
replays that exact game with the same code. With no job running it shows demo games between the meta agents.

- **It can't affect the job.** The viewer is a separate program at the lowest priority. Closing the tab or
  pressing Ctrl+C in its window stops only the viewer. The job's side is one small file write every few
  seconds, and it doesn't touch the random numbers: results are identical with or without it
  (`tests/test_replay.py` checks this). To switch even that off, start the job with `WATCH=0`, e.g.
  `make exploit WATCH=0`.
- **CPU.** Replaying a game takes a few hundredths of a second. The win-chance chart is the only part with
  a real cost: each estimate plays the position out 64 times, about 0.1-0.2 s of one thread, at most
  twice a second. The toolbar has a switch for it and a Pause button; add `?odds=off` or `?speed=5`
  to the address to start that way.
- **Going back.** Click or drag on the Projected winner chart to rewind the board to any turn; ← and → step
  one turn at a time and Space pauses. The numbered turning points under the chart are the biggest swings in
  the win chances, each with the turn that caused it: click one to watch that turn again. While you look
  back at a paused game the viewer fills in the gaps in the chart (the same cost as above), then stops.
- **The board** is your classic-colour board kit (`watch/board`: Go to Jail's padlock, Free Parking's blue P).
  Owners' tabs, houses and hotels, mortgages and the pieces are drawn over it where the kit's `manifest.json`
  puts them, and the jail's bars go over anyone inside. Add `?board=drawn` to the address for the earlier board.
- If the page doesn't open, go to http://localhost:8765 yourself. If Windows can't reach it, try
  `make watch HOST=0.0.0.0`.

## Later steps

Claude adds each one here when it's ready: engine checks (Phase A), studies at scale (Phase B), position
data (Phase C), model training (Phase D), and the agent league (Phase F).

## If something goes wrong

- `make status` shows which steps are done; logs are in `.sync/logs/`.
- A step failed: paste the last 20 lines of its log into the chat.
- "uncommitted changes": a tracked file was edited. `git stash` puts the edit aside, or ask Claude.
- "detected dubious ownership": run `git config --global --add safe.directory /mnt/h/monopoly-strategy`.
- Ubuntu can't see `H:`: check `ls /mnt/h`. If H: is a network drive, tell Claude.
