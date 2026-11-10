# Monopoly Meta

**What's the best way to play Monopoly? This project has computers play millions of games of classic UK Monopoly,
at every table size from 2 to 6 players, to find out.**

![How often each square is landed on](results/final/figures/landing_probabilities.png)

## The idea

Monopoly looks like a game of luck, but every choice in it (buy or pass, how much to bid, when to build, whether to
trade, whether to pay your way out of jail) changes your chance of winning. Make one choice differently, play
thousands of games each way with the same dice, and you can measure what that choice is worth. The project
does this in three steps:

1. **Exact odds.** Where the dice send you, worked out mathematically: how often every square gets landed on.
2. **A full game simulator.** The official rules (auctions, mortgages, the 32 houses and 12 hotels in the box, jail,
   bankruptcy), apart from a few [listed simplifications](RULES.md), with computer players of different styles, fast
   enough to play millions of games.
3. **Computer players that learn.** Players evolved by playing each other at every table size, then searches for
   strategies that beat *them*, then another round of learning against those.

## What it found

1. **Trafalgar Square is the most-visited property, Park Lane the least** (3.48 and 2.36 landings per 100 turns).
2. **The orange set is the best investment.** With hotels it pays for itself fastest: in about 7 rounds of play at
   4 players. On every set but the browns, the third house earns the most rent for its price.
3. **The last piece of a set is worth far more than its price.** In one test position at 4 players, a player who owns two
   of the oranges wins 6% of the time without the third, and 90% if given it. Compared with never getting it, it's
   worth up to £1,144 to them: almost six times the £200 printed on the card. But the computer players usually sell
   it to them within a couple of turns for £400, so paying much more than that going rate is a loss.
4. **Trading is most of the game.** Under the standard rules with 3 or more players, a strong player that refuses
   every trade wins far less often: a fifth as often at 4 players. With 2 players, trading barely matters.
5. **Going first helps, and more so at a big table.** With six identical computer players, the first player wins
   20% more often than an equal share, and the last player 19% less.
6. **Keep little cash at a big table, and a cushion at a small one.** For the strongest players found (standard
   rules), keeping £200 more in hand costs 10–19% of their wins. With 4 to 6 players they keep almost nothing
   (£0–£19 after buying); with 2 or 3 they keep £223–£462, and giving that cushion up costs them 11%.
7. **No strategy found is unbeatable.** Every one of the ten strongest players can be beaten by a counter-strategy:
   the best ones the searches found score 3% to 51% more against them, and those are lower limits. The best way to
   play depends on who you're playing against.

## How we know it's right

- **Same dice, two choices.** Trades and single-setting changes are tested by playing both options on identical dice
  rolls, so much of the luck cancels out. The full findings give each number's margin of error.
- **Checked against itself.** The exact odds match 10 million simulated turns to within 0.5% when cards are drawn at
  random (the real, fixed-order decks shift a few squares by up to 1.8%). Over 190 automated tests check the rules,
  and that the money, houses and cards always add up after every turn.
- **Numbers re-checked automatically.** A script recomputes over 190 of the figures quoted here, in the full findings
  and on the rules page, straight from the result tables, so a stale or mistyped number fails the tests.

These are results for computer players of one design, under these rules: a strong guide to good play, not proof of
perfect play.

## Read more

- **[The full findings](FINDINGS.md)**: all 18 results, with tables, charts and margins of error.
- [Rules](RULES.md): exactly which rules the simulator plays, and what it simplifies.
- [Roadmap](ROADMAP.md): what comes next, and what earlier corrections changed.
- [Running it](RUNNING.md): the jobs behind every result, as they were run on a 16-thread PC.

```bash
pip install -e ".[dev]"
pytest
python scripts/watch.py --play     # play the computer players yourself, in your browser
```

---

An independent, unofficial analysis for learning and research. Not affiliated with or endorsed by Hasbro. MONOPOLY
is a trademark of Hasbro; board names, prices and card texts are used only to model the game. Code: [MIT](LICENSE);
the Oswald font in the charts: SIL Open Font Licence 1.1.
