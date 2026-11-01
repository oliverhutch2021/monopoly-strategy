# Roadmap

The goal is a **game-state valuation engine**: for any position, how much every property,
trade, auction bid and building decision is worth, in win-probability and in pounds.

```
Phase 0  Rules engine + exact Markov chain + ROI + bots         <- done (v0.1)
Phase 1  Rollout evaluator + trade price curves                 <- done; 2-6 players (v0.2)
Phase 5a Meta agents by evolutionary self-play, 2-6 players     <- done (v0.2)
Phase 5c Unconventional strategies: new moves + MAP-Elites      <- done (v0.4, hardened in v0.5, deep run)
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
  finds re-measured on fresh games; a league of them, with the Nash mixture of the league's payoff table. That
  table scores each pair of strategies at tables of one kind, so the mixture is of a surrogate game, not of
  Monopoly at a mixed table.
- Result (`results/v04/tables/unconventional/summary.md`): every v0.3 meta agent can be beaten, by
  1.2-1.9x; the housing lock is in 66 of the 85 finds that beat it, auction sniping in 56. The search started
  from each move switched on, so these counts say what survived, not what was discovered; switching each move
  off (v0.5) is the better measure. Many finds are
  counter-strategies: a table made only of one stalls or hands its neglected colour groups to whoever joins,
  so homogeneous-table leagues overstate how easily they are invaded.
- v0.5, hardening (`src/monopoly_meta/harden.py`, `scripts/14_harden.py`): best-response iteration (a small
  PSRO) from each v0.3 agent, new moves allowed, at mixed tables with every known exploit in the opponent
  pool; each round's agent is the one the pool exploits least, and a quick MAP-Elites search against it adds
  fresh exploits to the pool. Then v0.4's two searches are repeated against the new agents with the same
  budgets and seeds, for a like-for-like before and after. Also: which new moves do the work in v0.4's finds
  (one switched off at a time).
- Result (`results/v05/tables/hardened/summary.md`): hardening made six of the ten agents harder to exploit,
  most clearly at 2 and 4 players (the official 2-player agent from 1.91x to 1.15x). It went in circles at 3
  and 6 players under official rules and 5 and 6 under championship rules, so those keep their v0.3 agents.
  Borrowing to build and the housing lock carry the new moves' edge; most of the others are passengers.
- The deep run (`make deep`, `results/final`) re-measured every study at 10x the samples with the final agents.
  The exploits hold (within about 0.05 of v0.5's numbers), and single changes find the last cheap gains: bidding
  25% more beats six of the ten agents by 3-13%. At 5 players both agents lose to simple bots because they offer
  meta-agent prices for set pieces. Against meta agents, sellers of a set-completing colour-group piece other
  than a brown should ask £70-£171 more than against simple bots (4 players, official rules).
- Next: a fix for the four cycling settings would train against a weighted mixture of the strongest opponents
  (PSRO proper) rather than a uniform pool.

## Methodology review (October 2026)

An independent review of commit 59cab72 scored the methodology 72/100. Every finding was checked against the
code and the stored results, and all of them held. What changed, and the principle behind each change:

- **Every number says what it measures**: the outcome (outright win, time-limit win, finishing points), the
  policy, the change and the horizon. Championship credit is labelled as points ÷ 28; win-rate tables count
  outright wins and time-limit leaders apart; "three-house cap" is renamed "three houses first", which is what
  it does; trade summaries name their utility.
- **Summaries read the whole curve**: a deal is every price at which both sides gain, not the first zero
  crossing. Curves that aren't monotone are flagged (a bot that does better after paying more is misusing its
  cash, which is a finding about the bot), and a whole-curve bootstrap gives intervals for the deal's ends.
- **The action layer uses the game's rules**: a trade the rules forbid (heads-up under championship rules) is
  reported as not allowed instead of priced.
- **Simplifications are rule variants**: building at any time, house auctions and counting mortgaged stations
  are engine switches, and `scripts/15_rule_sensitivity.py` re-tests the housing findings under each.
- **Results know their inputs**: checkpoints are keyed by everything that produced them, and every run records
  its package versions.
- **The README is checked against the tables**: `scripts/claims.py` recomputes the deep-run findings' numbers (a test
  runs it).

`make review` ran the parts that needed new games on the PC (2 hours): the trade studies at equal own-turn
horizons and with bootstrap intervals, the tournaments with outright and time-limit wins apart, and the rule
sensitivity. No README number moved at its precision. Finding 3 changed: at equal horizons the gap between net
worth and win chance doesn't grow with table size. The housing findings hold under every official building rule
(finding 18), which also found a gain the official 4-player agent misses: the housing lock (+6%).

A second review (82/100, of 970c390) found two defects in that new work, both confirmed before fixing:

- **Own-turn horizons drifted.** "Net worth after k own turns" was taken after k rounds of the starting table,
  so after a bankruptcy a player had had more turns than k (24 instead of 20 in the review's example), and the
  trade and keep arms could differ. Each player's net worth is now taken at their own k-th turn
  (`rollout.play_recording`), with a bankrupt player at 0 and a game that ends first at its end, in both arms.
- **House auctions could charge more than a bid.** The bid was sized on the cheapest group but the house could go
  on a dearer one, at a price above the bid. A bid now names its house (the next the bot would build that it can
  afford), its limit covers that house's price, and the winner never pays more than its limit.

And it asked for more, done with them: every outcome side by side in the tournament tables (outright wins among
finished games and among all games, time-limit wins, the cap share); checkpoint keys that include hashes of the code,
the edition data and the scenario state as built, not just its name; Bonferroni-adjusted intervals beside the 52
rule comparisons; and a fresh-seed confirmation of the housing-lock gain. `make review2` re-ran findings 3 and 18 on
the same games and seeds (78 minutes). Counting each player's own turns raised finding 3's gaps by 1–4 points and
left its conclusion as it was. With the auction fix, the house-auction results moved by 0.006 at most, and the 39
results without house auctions reproduced exactly. On fresh seeds the housing-lock gain is 4.9% [4.3%, 5.5%]. After
a Bonferroni adjustment, 11 of the 52 rule comparisons still show a change, all of them with building at any time.

A third, deeper review (85/100, of 6e8a9f4) reproduced the corrected results and asked what each one means. Its
points, each checked against the code before changing anything:

- **Which decision a trade price prices.** A sale was compared with keeping the deed for good, which measures the
  deed's own value to each side. Whether to accept an offer today depends on what happens otherwise, and the bots
  often trade the deed later anyway (simple bots offer twice face value, £400 for Vine Street). Every Vine Street
  curve is now played against both baselines, and records what the keep arm's later trades were
  (`rollout.trade_price_curve(freeze=...)`). Narrow deals read between sampled prices are replayed at whole-pound
  prices on fresh games (`scripts/16_price_checks.py`), and the set-completing sale is priced in 100 positions from
  real games, not one hand-built position (`scripts/17_game_positions.py`).
- **One setting, two decisions.** The housing lock defers hotels while houses are short *and*, when raising cash,
  mortgages everything else before selling a building. These are now separate settings (`lock` and `protect`), and
  a four-arm comparison against four opponent populations says which one carries the gain.
- **Points are not wins.** Championship trade values are expected finishing points ÷ 28; the dashboard now shows
  them as points. The 5- and 6-survivor points are an assumption that decides most games at those sizes, so those
  conclusions are re-scored under two other schedules (`scripts/18_scoring_sensitivity.py`).
- **Smaller fixes:** everyone else's change in a trade is measured game by game (a paired standard error); the
  dashboard draws one band per deal range and the uncertainty of the end it shows; the official choice to lift a
  received mortgage at once is a rule variant; hotel shortages are counted; "no detected change" now needs an
  interval inside a tolerance set in advance (±3%) before it is called equivalent; before/after comparisons keep each
  game's outcome so they can be paired; and search checkpoints refuse to resume on other inputs or code
  (`provenance.fingerprint`).

`make review3` ran the parts that needed new games on the PC (2 hours 11 minutes). Everything re-run on the same
seeds reproduced exactly: the Vine Street curves against keeping the deed for good, and all 65 earlier rule
comparisons. What the new work found:

- **The decision differs from the deed.** Carrying on as normal, the bots sell Vine Street to the player who needs
  it within a few player-turns at their own offer (£400 for simple bots, £200–£800 for the meta agents), so the deal
  zone for accepting an offer today shrinks to a few pounds at that price. In 100 positions from real games, paying
  three or four times face value instead of the going twice loses for the buyer in every position.
- **Narrow zones mostly don't survive.** Of 21 zones read between the prices played, 4 hold at whole-pound prices
  on fresh games; the 2-player £304–£306 band against the official agent doesn't.
- **The housing lock's gain is a cash-raising rule.** Protecting buildings alone gains 6–7% against every opponent
  population tested; holding back hotels alone helps nowhere. This reproduces the review's figures exactly on its
  games.
- **The remaining rule simplifications hardly matter.** Lifting a received mortgage at once moves the agents' edges
  by 2% at most (the simple bot's by 5%); hotels are contested in at most 0.1% of games.
- **Championship conclusions don't rest on the assumed points.** Under two other schedules for five and six
  survivors, accepting trades costs the agents more, and no price compensates a seller of Vine Street.

The review's three highest-return next steps are now part of the plan below: make the decision being priced explicit
in every valuation (Phase 4), separate bundled decisions before attributing a strategy's gain and then search over
them (Phase 5), and build a game-level holdout before training a value model (Phases 2 and 3).

## Phase 2: data pipeline
- Snapshot the state every *k* turns in self-play games. Label each snapshot with the
  eventual winner, finishing position and the turns remaining, keeping outright wins,
  time-limit wins and finishing points as separate targets: a game stopped by the time limit
  is its own outcome class, and championship finishing points get their own target.
- **A game-level holdout, built first.** Sample snapshots across game phase, property
  scarcity, cash, developed sets, players remaining and opponent policies, and keep every
  snapshot of a source game on the same side of every split.
- **Positions from real games.** The trade findings rest on one hand-built position per
  table size, and each extra player there also adds properties and cash. Sample positions
  from held-out games instead, stratified by cash, property ownership, development, game
  phase and players remaining; price trades under several opponent populations, with
  realistic continuation trading rather than a frozen property; and report the
  distribution of values and of recommendation errors, not only average effects.
- **Cover unusual states.** Inject random trades, auctions and cash shocks, so the model
  sees positions the bots wouldn't normally produce (sets completed early, cash-starved
  monopolies).
- Store the data as Parquet partitioned by bot mix and rule set, and query it with DuckDB.
- Generate it in parallel and make every run reproducible from a seed. Add schema and
  invariant tests.
- Speed: profile the engine first, and port only the hot spots profiling finds to Numba or
  Rust, if more than ~10M positions are needed.

## Phase 3: value model
- **Symmetric features from the mover's point of view**:
  - cash, net worth and position for "me" and for each opponent;
  - sets owned and their build level;
  - expected rent faced and charged per opponent turn (from the Markov landing rates);
  - Jail status, Get Out of Jail Free cards held, houses left in the bank, unowned
    properties, turn number.
- Win probabilities that add up: score every player, then normalise to sum to 1 (softmax
  or multiclass).
- **Monotonicity as a hypothesis, not an assumption** (own cash ↑ ⇒ P(win) ↑; opponents'
  cash ↑ ⇒ P(win) ↓). Test it on rollouts first: the brown trade curves show bots that do
  better after paying more, so a constraint would hide a real flaw in the policy. Constrain
  only where it holds for the policy being valued.
- **Legal information only**: the model sees what a player could know (the cards drawn so
  far, not the order of the deck).
- **Validation**:
  - split train and test **by game**, so correlated snapshots from one game never leak
    across;
  - reliability curves and the Brier score;
  - a held-out **valuation benchmark** of positions whose indifference prices have also
    been computed by rollouts (like `scripts/04_trade_curve.py`), comparing the model's £
    values against the rollout £ values;
  - **decision regret**: how much win chance (or finishing points) the model's choices (buy,
    bid, build, trade) give up against the rollout's best choice, with the benchmark's
    continuations on seeds of their own, which matters more than calibration or price error
    alone.
- SHAP explains every valuation: "why is Vine Street worth £900 to you right now?"

## Phase 4: instant valuations
- **Name the decision being priced.** Every valuation says what it is compared with: the
  deed kept for good (its own value to each side) or play carrying on as normal, later trades
  included (whether to accept an offer now). Recommendations to accept or decline use the
  second; both sides' outcomes and the later deals the baseline makes are shown.
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
- Train and test against mixtures of the strongest known opponents (the known
  challengers included), weighted by how much they exploit the agent, and report
  exploitability as a lower bound with the search budget that found it. Repeat each search
  with new seeds to measure how much its result varies, and confirm every selected
  candidate on fresh seeds.
- Retrain under the official building rules: the rule-sensitivity study (finding 18)
  tested the existing agents under them, which is not the same as the best play there.
  House-auction bidding is one heuristic today; search over it like any other setting.
- **Separate decisions before attributing a gain.** The housing lock bundled hotel timing
  with the order buildings are sold in; they are now separate settings (`lock`, `protect`).
  Search over them separately, validate the selected policies against fresh mixtures of
  opponents, and report absolute and relative gains with the outcome scored. Do the same for
  any other setting that changes more than one action.
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
