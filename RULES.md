# Rules implemented

The engine plays the **classic UK (London) edition** with the official rules. Board and card
data live in `src/monopoly_meta/data/uk_classic.json`, with the source of each list recorded in
the file. Every simplification is listed below, so a reader can judge each result against it.

## Board, money and cards

| Item | Value | Source |
|---|---|---|
| Starting cash | £1,500 | Waddingtons rules; Wikipedia |
| Passing or landing on GO | +£200 | rules |
| Income Tax / Super Tax | £200 / £100 (flat) | Wikipedia (UK board) |
| Prices and rents | UK set marked ©1972; Piccadilly site rent is **£22** (later editions use £24) | jdawiseman.com, Wikibooks |
| House costs | £50 brown/light blue, £100 pink/orange, £150 red/yellow, £200 green/dark blue | title deeds |
| Chance / Community Chest | 16 cards each, classic London text (incl. "Drunk in charge", "Pay a £10 fine or take a Chance") | Jumbloid (2008), cross-checked |

Card decks are shuffled once. Drawn cards go to the **bottom** of the pile, so each deck runs
through a fixed order. A held Get Out of Jail Free card leaves the deck until it is used.
The engine also has a `card_draw="random"` mode, which draws with replacement. It is used
only to validate the Markov chain.

## Rules implemented

- **Doubles**: roll again; a third double in one turn sends you straight to Jail without moving.
- **Jail**: on each turn in Jail you can use a Get Out of Jail Free card, pay £50 and then take
  a normal turn, or roll for a double. A double moves you out but gives no extra roll. After
  the third failed roll you must pay £50 and move by that roll. Players in Jail still
  collect rent.
- **Buying and auctions**: an unowned property you land on is bought at face value or
  auctioned to **all** players, including the one who declined it. The auction is resolved
  from each bidder's private maximum. The winner pays the second-highest maximum plus £1,
  capped at their own maximum. This is the outcome of an English auction with £1
  increments. Ties go to the earliest bidder in turn order.
- **Rent**:
  - Unimproved streets pay double rent when the whole colour set has one owner.
  - Mortgaged properties collect no rent.
  - Stations pay £25, £50, £100 or £200 by the number owned. By default **a mortgaged
    station doesn't count** towards that number. That is the engine's reading: the rules
    sheet doesn't settle it, and some players count every station owned.
    `Rules(mortgaged_count_for_rent=True)` plays it that way. The choice moves no tested
    result by more than 2% (README, finding 18).
  - Utilities pay 4× the dice roll for one owned, or 10× for both, with the same choice
    about a mortgaged one.
  - A street's double rent for a whole set applies even if another street in the set is
    mortgaged.
- **Building**:
  - You need the whole colour set, with no property in it mortgaged.
  - Houses must be built evenly across the set, and sold back evenly.
  - A hotel replaces four houses, which go back to the bank.
  - The bank holds **32 houses and 12 hotels**. If none are left, nobody can build.
  - Buildings sell back to the bank for half their cost.
- **Mortgages**: a property mortgages for half its price and costs half its price + 10% to
  lift. You can't mortgage while the colour set has buildings.
- **Trades**: properties and cash can change hands. Every building in a colour set must be
  sold before any of its streets can be traded. Whoever receives a mortgaged property pays
  the 10% interest straight away.
- **Bankruptcy**: buildings are sold to the bank first.
  - Owing a player: your cash, properties and Get Out of Jail Free cards go to that player,
    and they pay 10% on any mortgages they inherit.
  - Owing the bank: your properties are unmortgaged and auctioned to the remaining players.
  - The last player left wins.
- **Free Parking**: nothing happens (official rule). A `free_parking_jackpot` switch adds the
  common house rule, where taxes and fines (card fines, repairs, the jail fine) go into a pot
  for whoever lands there. Mortgage interest goes to the bank, not the pot.

## Simplifications (and how each is tested)

Three of the simplifications below could bend the findings: two decide who gets houses,
which several findings rest on, and one sets station and utility rent. Each has an engine
switch that plays the official rule instead. `scripts/15_rule_sensitivity.py` (run by
`make review`) replayed the housing comparisons under every switch, on games no search had
seen, and counted how often each simplification binds. No verdict reverses under any of
them, and house auctions change no edge by more than 1% (README, finding 18; details in
`results/final/tables/sensitivity/summary.md`). The meta agents were still trained under
the engine's rules.

| Simplification | Effect, and the switch that removes it |
|---|---|
| Building, unmortgaging and trading happen once per turn, at the end of the player's own turn (the rules allow building at any time). | `Rules(build_any_time=True)`: after each turn, every other player in turn order may also build and unmortgage (trades stay on a player's own turn). Games run 2–3 times slower. Moves the tested agents' edges by 5% at most; helps the simple bot more (0.46× to 0.63× against the championship 4-player agents). |
| During a housing shortage, the remaining houses go to whoever builds first. There's no auction for the last houses. | `Rules(house_auctions=True)`: whenever two or more players want more houses than the bank has, the houses are auctioned one at a time. The highest limit wins and pays the second-highest + £1 (at least the house's price); ties go to the earliest in turn order. `Game.contested_houses` counts those moments (also without the switch, with `Game.track_housing`), and `Game.house_auctions_held` the houses sold. Between the final meta agents, houses are contested in 5% of official 4-player games, 1% of 2-player games and 43% of championship 4-player games (2.3 houses auctioned per game). |
| A mortgaged station or utility doesn't count towards the rent of the others (see Rent above). | `Rules(mortgaged_count_for_rent=True)`. Moves no tested result by more than 2%. |
| Players buy only with cash on hand. They don't mortgage to fund a purchase. | Slightly fewer purchases by cash-poor players. |
| If a hotel must be broken up and the bank lacks 4 houses, it is sold further down. The other streets in the set aren't forced down with it. | Very rare; counted in `Game.uneven_events` (which counts only this, not housing shortages in general). |
| Rent is always collected (in the real game the owner must ask for it before the next roll). | Treats every player as attentive. |
| If the card-drawer goes bankrupt while collecting birthday money, collection stops; money owed to a bankrupt player goes to the bank. | Edge case; keeps the books consistent. |
| A game stops after `max_turns` (default 4,000 player-turns). The richest player is then recorded as the winner, and the `capped` flag is set. | Under the official rules almost no game reaches it (1 in 10,000 at 4 players, none at other sizes). Bots that rarely trade hit it more often: up to 3.5% for the hard-bargainer at 6 players. |

## Time limit in meta-agent games

The self-play games that train and test the meta agents stop after **150 full rounds**
(`meta.tournament_rules`). That is well above the 90th-percentile game length at every
table size (93 rounds at 2 players, 66 at 4, 55 at 6), so it only stops stalled games.

How a stopped game is scored decides what self-play learns, so three rules were tried:

| A game stopped by the time limit counts as… | What 5–6 player self-play learned |
|---|---|
| a win for the richest player | refuse every trade and coast to the limit on net worth (77% of 5-player games stalled; `archive_networth_cap/stall_check.csv`) |
| a draw shared by the players still in it | a trade embargo: nobody accepts any trade, about 80% of games stall (`archive_draw_scoring/`) |
| **a loss for everyone (used)** | stalling earns nothing, so agents trade to win; under 0.5% of games stall at 3–6 players |

At 2 players about 20% of games between meta agents still reach the limit: two cautious
players can lock each other out of every set.

## Championship mode (`engine.championship_rules`)

A second rule set follows the official **Monopoly Championship rules** (Hasbro, 2009, with
the championship FAQ). The championship meta agents and every "Championship rules" result
use it.

- **Speed Die.** Once a player has passed GO for the first time, they roll a third die with
  faces 1, 2, 3, Bus, Mr Monopoly, Mr Monopoly.
  - **1–3**: added to the two number dice.
  - **Bus**: move by either number die or by both; the bot picks the best landing square.
  - **Mr Monopoly**: make the normal move and act on that square, then advance to the next
    unowned property and buy or auction it. If none are left, advance to the next property
    on which you owe rent, and pay it.
  - **Triples** (both number dice equal the Speed Die): move to any square, collecting £200
    if you pass GO; the turn then ends. The bot picks the square with the best value for it.
  - Only the number dice count for doubles; a third double still sends you to Jail.
    Utility rent uses the number dice (plus a 1–3 Speed Die face).
- **Auctions** start at £1. If nobody bids, the richest player gets the property for £1
  (championship FAQ).
- **No trades heads-up**: once only two players are left, no more trades (championship FAQ, for
  preliminary games).
- **Time limit and scoring.** Games stop after 150 rounds. Players are then ranked by net
  worth and score finishing points: 28 for an outright win; with 2 players left 25 and 14;
  with 3 left 22, 12 and 6; with 4 left 19, 10, 5 and 3. The rules sheet stops at 4
  survivors, so 5 and 6 survivors use an extrapolated 16/8/4/2/1 and 13/6/3/2/1/0.
  Agents maximise points ÷ 28, and championship results report that credit, which is not a
  win probability: with two survivors the credits sum to 39/28. Win-rate tables count
  outright wins and time-limit leaders separately (`limit_wins`).
- Not modelled: the real-time clock (official heats run for a fixed number of minutes, not
  rounds), the 60-second limit on trade talks, and rent that is lost when the owner forgets
  to ask for it.

All other results use the plain official rules with the 4,000-turn safety cap described
above.

## Known edition differences

Some later UK printings (2008 onwards) changed several cards and amounts, and Piccadilly's
site rent. To model one, add `data/<edition>.json` and pass `load_edition("<edition>")`.
