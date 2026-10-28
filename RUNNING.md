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
search, same games, but without the new moves.

## Later steps

Claude adds each one here when it's ready: the unconventional-strategy search (v0.4), engine checks
(Phase A), studies at scale (Phase B), position data (Phase C), model training (Phase D), and the agent
league (Phase F).

## If something goes wrong

- `make status` shows which steps are done; logs are in `.sync/logs/`.
- A step failed: paste the last 20 lines of its log into the chat.
- "uncommitted changes": a tracked file was edited. `git stash` puts the edit aside, or ask Claude.
- "detected dubious ownership": run `git config --global --add safe.directory /mnt/h/monopoly-strategy`.
- Ubuntu can't see `H:`: check `ls /mnt/h`. If H: is a network drive, tell Claude.
