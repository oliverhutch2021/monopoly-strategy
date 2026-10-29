# Roadmap

The goal is a **game-state valuation engine**: for any position, how much every property,
trade, auction bid and building decision is worth, in win-probability and in pounds.

```
Phase 0  Rules engine + exact Markov chain + ROI + bots         <- done (v0.1)
Phase 1  Rollout evaluator + trade price curves                 <- done; 2-6 players (v0.2)
Phase 5a Meta agents by evolutionary self-play, 2-6 players     <- done (v0.2)
Phase 5c Unconventional strategies: new moves + MAP-Elites      <- done (v0.4, hardened in v0.5)
Phase 2  Data pipeline: millions of simulated positions         -> Parquet / DuckDB
Phase 3  Learned value function  P(win | state)                 -> LightGBM + SHAP, calibrated vs rollouts
Phase 4  Instant valuations: trades, auctions, builds, cash     -> indifference prices in £
Phase 5b Value-driven agents (self-play with the learned model) -> beyond the heuristic bot family
Phase 6  Showcase: web dashboard, consulting deck, notebooks + report
```

## Phase 5c: unconventional strategies (v0.4)
- Eight optional tactics for the heuristic bot, all off by default so v0.3's games are unchanged:
  auction sniping, the housing lock, borrowing to build, jail by the numbers, dodging with the Speed
  Die, card counting, taxing the leader and playing the clock (`HeuristicBot` in
  `src/monopoly_meta/policies.py`; `src/monopoly_meta/unconventional.py`).
- A controlled comparison: v0.3's exploitability search with and without the new moves, with the same
  budget and on the same games (`scripts/12_exploitability.py`, `scripts/13_unconventional.py`).
- MAP-Elites over eight behaviour descriptors, so strong strategies of every style survive; the best
  finds re-measured on fresh games; a league of them with its Nash mixture.
- Result (`results/v04/tables/unconventional/summary.md`): every v0.3 meta agent can be beaten, by
  1.2-1.9x; the housing lock is in 66 of the 85 finds that beat it, auction sniping in 56. Many finds are
  counter-strategies: a table made only of one stalls or hands its neglected colour groups to whoever joins,
  so homogeneous-table leagues overstate how easily they are invaded.
- v0.5, hardening (`src/monopoly_meta/harden.py`, `scripts/14_harden.py`): best-response iteration (a small
  PSRO) from each v0.3 agent, new moves allowed, at mixed tables with every known exploit in the opponent
  pool; each round's agent is the one the pool exploits least, and a quick MAP-Elites search against it adds
  fresh exploits to the pool. Then v0.4's two searches are repeated against the new agents with the same
  budgets and seeds, for a like-for-like before and after. Also: which new moves do the work in v0.4's finds
  (one switched off at a time).

## Phase 2: data pipeline
- Snapshot the state every *k* turns in self-play games. Label each snapshot with the
  eventual winner, finishing position and the turns remaining.
- **Cover unusual states.** Inject random trades, auctions and cash shocks, so the model
  sees positions the bots wouldn't normally produce (sets completed early, cash-starved
  monopolies).
- Store the data as Parquet partitioned by bot mix and rule set, and query it with DuckDB.
- Generate it in parallel and make every run reproducible from a seed. Add schema and
  invariant tests.
- Speed: profile the engine, and port the hot loop to Numba or Rust if more than ~10M
  positions are needed.

## Phase 3: value model
- **Symmetric features from the mover's point of view**:
  - cash, net worth and position for "me" and for each opponent;
  - sets owned and their build level;
  - expected rent faced and charged per opponent turn (from the Markov landing rates);
  - Jail status, Get Out of Jail Free cards held, houses left in the bank, unowned
    properties, turn number.
- Win probabilities that add up: score every player, then normalise to sum to 1 (softmax
  or multiclass).
- **Monotone constraints** (own cash ↑ ⇒ P(win) ↑; opponents' cash ↑ ⇒ P(win) ↓) so
  that price curves are smooth and indifference prices exist.
- **Validation**:
  - split train and test **by game**, so correlated snapshots from one game never leak
    across;
  - reliability curves and the Brier score;
  - a held-out **valuation benchmark** of positions whose indifference prices have also
    been computed by rollouts (like `scripts/04_trade_curve.py`), comparing the model's £
    values against the rollout £ values.
- SHAP explains every valuation: "why is Vine Street worth £900 to you right now?"

## Phase 4: instant valuations
- **The marginal value of cash**, dP(win)/d£, which turns any Δwin% into pounds.
- **Indifference price** of any property, for any player, in any state, compared with the
  same property in a fresh game. Break it into standalone rent, set-completion premium,
  blocking value and liquidity cost.
- **Auctions**: simulate an ascending auction using each player's model-based limit. A
  player's limit is the win% if they win the property minus the win% if the likely
  rival wins it. Account for budget constraints and test price-driving tactics.
- **Building**: Δwin% per £ for each possible build compared with holding cash. When to
  build, where, and whether to hoard houses.
- **Card counting**: compare a model that sees the remaining deck order with one that
  only sees public information, and measure the value of a good memory.

## Phase 5: agents
- **Done in v0.2**: evolutionary self-play over the heuristic bot's ~20 parameters, at
  every table size, with exploitability checks and single-change ablations
  (`src/monopoly_meta/meta.py`, `scripts/05_meta_agents.py`).
- Next: a bot that buys, bids, builds and trades by maximising the value model. This
  removes the limit of the heuristic bot family.
- Expert iteration: play → retrain on the new games → repeat, until the valuations stop
  moving.
- Report win rates against the hand-written bots, with confidence intervals.

## Phase 6: showcase
- **Dashboard** (GitHub Pages):
  - a board heatmap;
  - a "what's it worth?" trade calculator, where you set up a position and get price
    curves and the deal zone;
  - auction and build advisors.
- **Consulting deck**: "Monopoly as capital allocation", covering ROI, liquidity, negotiation
  and risk.
- **Notebooks + report**: methods, validation and limitations.
