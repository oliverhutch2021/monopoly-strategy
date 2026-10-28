"""Full-rules Monopoly game engine (classic UK rules by default).

Design goals
------------
* **Correct**: the rules implemented, and every simplification, are listed in RULES.md.
* **Reproducible**: dice, card decks and bot randomness use separate seeded RNGs. Each
  player has their own dice stream and every turn consumes a fixed block of three throws,
  so the dice for "player p's k-th turn" are the same in two games built from the same
  seed however the games diverge (common random numbers). This is what lets the rollout
  evaluator compare "with trade" vs "without trade" precisely.
* **Restartable**: a game can start from any ``GameState`` (used for rollouts from a
  mid-game position).
* **Fast enough**: plain lists and integer codes, no per-turn object allocation.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

from .edition import Edition, load_edition

BANK = -1
HOTEL = 5
DICE_PER_TURN = 6  # at most three throws per turn (three doubles, or pay out of jail then two doubles)
SPEED_PER_TURN = 3  # one Speed Die face per throw
# Speed Die faces (championship rules): 1, 2, 3, Bus, Mr Monopoly, Mr Monopoly
BUS, MR_MONOPOLY = 4, 5
SPEED_FACES = (1, 2, 3, BUS, MR_MONOPOLY, MR_MONOPOLY)

# Championship tournament points by finishing position, indexed by how many players are
# still in when time runs out (Hasbro 2009 championship rules). Rows for 5 and 6 survivors
# are not published; they extend the published pattern and are an assumption.
CHAMPIONSHIP_POINTS = {
    1: [28],
    2: [25, 14],
    3: [22, 12, 6],
    4: [19, 10, 5, 3],
    5: [16, 8, 4, 2, 1],      # extrapolated
    6: [13, 6, 3, 2, 1, 0],   # extrapolated
}

# Behaviour counters kept per player when Game(track_stats=True). "Per turn" fields are summed at the
# end of each of the player's own turns, so dividing by "turns" gives an average over the game.
STAT_FIELDS = (
    "turns",        # own turns completed while still in the game
    "cash",         # cash held (per turn)
    "bought",       # properties bought at the printed price
    "auction_won",  # properties won at auction (including bankruptcy auctions)
    "trades",       # trades completed, on either side
    "levels",       # building levels owned, a hotel counting 5 (per turn)
    "hotels",       # squares with a hotel (per turn)
    "built",        # squares with any building (per turn)
    "jail",         # own turns that started in jail
    "mortgaged",    # mortgaged properties owned (per turn)
)
(ST_TURNS, ST_CASH, ST_BOUGHT, ST_AUCTION, ST_TRADES, ST_LEVELS, ST_HOTELS, ST_BUILT, ST_JAIL,
 ST_MORTGAGED) = range(len(STAT_FIELDS))

# integer square-type codes (faster than string comparison in the hot loop)
T_GO, T_STREET, T_STATION, T_UTILITY, T_CHANCE, T_CC, T_TAX, T_JAIL, T_FREE, T_GOTOJAIL = range(10)
_TYPE_CODE = {
    "go": T_GO, "street": T_STREET, "station": T_STATION, "utility": T_UTILITY,
    "chance": T_CHANCE, "community_chest": T_CC, "tax": T_TAX, "jail": T_JAIL,
    "free_parking": T_FREE, "go_to_jail": T_GOTOJAIL,
}


@dataclass
class Rules:
    auctions: bool = True               # official rule: declined property is auctioned
    free_parking_jackpot: bool = False  # house rule: taxes and fines go to the centre
    card_draw: str = "deck"             # "deck" = fixed cyclic order (official), "random" = with replacement
    max_turns: int = 4000               # cap on total player-turns; capped games are flagged
    min_bid: int = 1
    # how a game stopped by max_turns is scored (GameResult.credit):
    #   "networth" richest survivor wins | "draw" shared by survivors | "loss" nobody wins |
    #   "championship" finishing-position points (CHAMPIONSHIP_POINTS)
    stalemate: str = "networth"
    # championship tournament rules (Hasbro 2009)
    speed_die: bool = False             # Speed Die once a player has passed GO
    no_bid_to_richest: bool = False     # an auction with no bids gives the property to the richest player for £1
    no_trades_heads_up: bool = False    # no trades once only two players are left


def championship_rules(n_players: int, rounds: int = 150) -> "Rules":
    """Championship tournament mode: Speed Die, tournament tweaks and finishing-position scoring."""
    return Rules(max_turns=rounds * n_players, stalemate="championship", speed_die=True,
                 no_bid_to_richest=True, no_trades_heads_up=True)


@dataclass
class GameState:
    """Everything needed to resume a game. Copying it is cheap (lists of ints)."""
    n_players: int
    cash: list[int]
    pos: list[int]
    alive: list[bool]
    in_jail: list[bool]
    jail_turns: list[int]
    goojf: list[list[str]]      # per player: which deck(s) the held GOOJF cards came from
    owner: list[int]            # per square: player index or BANK
    level: list[int]            # per square: 0-4 houses, 5 = hotel
    mortgaged: list[bool]
    bank_houses: int
    bank_hotels: int
    chance: deque               # card indices, top of deck on the left
    cc: deque
    current: int = 0
    turn: int = 0
    pot: int = 0
    elimination_order: list[int] = field(default_factory=list)
    passed_go: list[bool] = field(default_factory=list)  # Speed Die is used only after this

    @classmethod
    def new(cls, ed: Edition, n_players: int, deck_rng: random.Random) -> "GameState":
        n = ed.n_squares
        chance = list(range(len(ed.chance)))
        cc = list(range(len(ed.community_chest)))
        deck_rng.shuffle(chance)
        deck_rng.shuffle(cc)
        return cls(
            n_players=n_players,
            cash=[ed.start_cash] * n_players,
            pos=[0] * n_players,
            alive=[True] * n_players,
            in_jail=[False] * n_players,
            jail_turns=[0] * n_players,
            goojf=[[] for _ in range(n_players)],
            owner=[BANK] * n,
            level=[0] * n,
            mortgaged=[False] * n,
            bank_houses=ed.bank_houses,
            bank_hotels=ed.bank_hotels,
            chance=deque(chance),
            cc=deque(cc),
            passed_go=[False] * n_players,
        )

    def copy(self) -> "GameState":
        return GameState(
            n_players=self.n_players,
            cash=self.cash[:], pos=self.pos[:], alive=self.alive[:],
            in_jail=self.in_jail[:], jail_turns=self.jail_turns[:],
            goojf=[g[:] for g in self.goojf],
            owner=self.owner[:], level=self.level[:], mortgaged=self.mortgaged[:],
            bank_houses=self.bank_houses, bank_hotels=self.bank_hotels,
            chance=deque(self.chance), cc=deque(self.cc),
            current=self.current, turn=self.turn, pot=self.pot,
            elimination_order=self.elimination_order[:],
            passed_go=(self.passed_go or [True] * self.n_players)[:],
        )


@dataclass
class GameResult:
    winner: int
    capped: bool
    turns: int
    net_worth: list[int]
    elimination_order: list[int]
    stalemate: str = "networth"

    def credit(self, p: int) -> float:
        """Win credit for player p: 1 for an outright win (any scoring rule).

        A game stopped by the turn limit is scored by `stalemate` (see Rules): the richest
        survivor wins ("networth"), survivors share it ("draw"), nobody wins ("loss"), or
        survivors get championship finishing points ÷ 28 ("championship").
        """
        if not self.capped:
            return float(self.winner == p)
        alive = [q for q in range(len(self.net_worth)) if q not in self.elimination_order]
        if p not in alive:
            return 0.0
        if self.stalemate == "draw":
            return 1.0 / len(alive)
        if self.stalemate == "loss":
            return 0.0
        if self.stalemate == "championship":
            ranked = sorted(alive, key=lambda q: (-self.net_worth[q], q))
            return CHAMPIONSHIP_POINTS[len(alive)][ranked.index(p)] / 28
        return float(self.winner == p)


class Game:
    def __init__(self, policies, edition: Edition | None = None, rules: Rules | None = None,
                 seed: int | None = None, state: GameState | None = None,
                 track_landings: bool = False, reshuffle_decks: bool = False,
                 frozen_squares=(), track_stats: bool = False):
        self.ed = ed = edition or load_edition()
        self.rules = rules or Rules()
        self.policies = list(policies)
        base = random.Random(seed)
        self.deck_rng = random.Random(base.getrandbits(64))    # card shuffles
        self.policy_rng = random.Random(base.getrandbits(64))  # bots' own randomness
        self.dice_rngs = [random.Random(base.getrandbits(64)) for _ in self.policies]
        self.speed_rngs = [random.Random(base.getrandbits(64)) for _ in self.policies]
        self._turn_dice = []  # this turn's block of throws
        self._turn_speed = []
        if state is None:
            self.s = GameState.new(ed, len(self.policies), self.deck_rng)
        else:
            self.s = state.copy()
            if not self.s.passed_go:
                self.s.passed_go = [True] * self.s.n_players
            if reshuffle_decks:  # forget the deck order (a player who has not tracked cards)
                self._reshuffle(self.s.chance)
                self._reshuffle(self.s.cc)
        assert len(self.policies) == self.s.n_players

        self.types = [_TYPE_CODE[t] for t in ed.types]
        self.n_sq = ed.n_squares
        self.landings = [0] * self.n_sq if track_landings else None
        self.last_dice = 7
        self.done = sum(self.s.alive) <= 1
        self.capped = False
        self.uneven_events = 0  # hotel broken during a house shortage (see RULES.md)
        # squares that may not be traded (used to define "keep it" baselines in rollouts)
        self.frozen = frozenset(frozen_squares)
        # cards drawn from each deck since this Game started: public information, so a player with a
        # perfect memory knows the order of everything drawn so far (policies.next_card_values)
        self.draws = {"chance": 0, "cc": 0}
        # optional per-player behaviour counters (STAT_FIELDS), for describing playing styles
        self.stats = [[0] * len(STAT_FIELDS) for _ in self.policies] if track_stats else None

    # ------------------------------------------------------------------ main loop
    def play(self) -> GameResult:
        while not self.done:
            self.take_turn()
        return self.result()

    def take_turn(self) -> None:
        s = self.s
        p = s.current
        r = self.dice_rngs[p].random
        self._turn_dice = [int(r() * 6) + 1 for _ in range(DICE_PER_TURN)]
        self._die_idx = 0
        if self.rules.speed_die:  # separate stream, so standard-rules games are unchanged
            r = self.speed_rngs[p].random
            self._turn_speed = [SPEED_FACES[int(r() * 6)] for _ in range(SPEED_PER_TURN)]
            self._speed_idx = 0
        if self.stats is not None and s.in_jail[p]:
            self.stats[p][ST_JAIL] += 1
        if s.in_jail[p]:
            self._jail_turn(p)
        else:
            self._roll_and_move(p)
        if s.alive[p] and not self.done:
            self.policies[p].manage(self, p)
        if self.stats is not None and s.alive[p]:
            self._record_turn(p)
        self._end_turn()

    def _record_turn(self, p: int) -> None:
        s, st = self.s, self.stats[p]
        st[ST_TURNS] += 1
        st[ST_CASH] += s.cash[p]
        for sq in self.ed.ownable:
            if s.owner[sq] == p:
                lv = s.level[sq]
                if lv:
                    st[ST_LEVELS] += lv
                    st[ST_BUILT] += 1
                    st[ST_HOTELS] += lv == HOTEL
                elif s.mortgaged[sq]:
                    st[ST_MORTGAGED] += 1

    def roll(self) -> tuple[int, int]:
        i = self._die_idx
        self._die_idx = i + 2
        return self._turn_dice[i], self._turn_dice[i + 1]

    def speed_roll(self) -> int:
        i = self._speed_idx
        self._speed_idx = i + 1
        return self._turn_speed[i]

    def _roll_and_move(self, p: int) -> None:
        s = self.s
        doubles = 0
        while True:
            d1, d2 = self.roll()
            speed = self.speed_roll() if self.rules.speed_die and s.passed_go[p] else 0
            if d1 == d2:
                doubles += 1
                if doubles == 3:  # only the number dice count (a triple here is a third double)
                    self.send_to_jail(p)
                    return
            if speed == 0:
                self.move(p, d1 + d2)
            elif speed <= 3 and d1 == d2 == speed:  # triple: go anywhere, then the turn ends
                dest = self.policies[p].triple_destination(self, p)
                self.move_to(p, dest, dice=d1 + d2 + speed)
                return
            elif speed <= 3:
                self.move(p, d1 + d2 + speed)
            elif speed == BUS:  # move by one number die or both; the Bus counts as 0 for utilities
                options = sorted({d1, d2, d1 + d2})
                steps = self.policies[p].bus_choice(self, p, options)
                self.move(p, steps if steps in options else d1 + d2, dice=d1 + d2)
            else:  # Mr Monopoly: normal move, then on to the next unowned (or rent-paying) property
                self.move(p, d1 + d2)
                if not (self.done or not s.alive[p] or s.in_jail[p]):
                    self.mr_monopoly(p, dice=d1 + d2)
            if self.done or not s.alive[p] or s.in_jail[p] or d1 != d2:
                return

    def mr_monopoly(self, p: int, dice: int) -> None:
        """Advance to the next unowned property (buy or auction it). If none is left, advance to
        the next property where rent is owed; if there is none, stay put."""
        s, ed = self.s, self.ed
        ahead = [(s.pos[p] + k) % self.n_sq for k in range(1, self.n_sq + 1)]
        target = next((sq for sq in ahead if ed.is_ownable(sq) and s.owner[sq] == BANK), None)
        if target is None:
            target = next((sq for sq in ahead if ed.is_ownable(sq) and s.owner[sq] not in (BANK, p)
                           and not s.mortgaged[sq]), None)
        if target is not None:
            self.move_to(p, target, dice=dice)

    def _jail_turn(self, p: int) -> None:
        s, ed = self.s, self.ed
        choice = self.policies[p].jail_decision(self, p)
        if choice == "card" and s.goojf[p]:
            self.use_goojf(p)
            self._roll_and_move(p)
            return
        if choice == "pay" and s.cash[p] >= ed.jail_fine:
            self._pay_bank(p, ed.jail_fine)
            s.in_jail[p] = False
            s.jail_turns[p] = 0
            self._roll_and_move(p)
            return
        d1, d2 = self.roll()
        if d1 == d2:  # out on a double: move, but no extra roll
            s.in_jail[p] = False
            s.jail_turns[p] = 0
            self.move(p, d1 + d2)
            return
        s.jail_turns[p] += 1
        if s.jail_turns[p] >= ed.max_jail_turns:  # third failure: must pay and move
            if not self.charge(p, ed.jail_fine):
                return
            s.in_jail[p] = False
            s.jail_turns[p] = 0
            self.move(p, d1 + d2)

    def _end_turn(self) -> None:
        s = self.s
        s.turn += 1
        if sum(s.alive) <= 1:
            self.done = True
            return
        q = s.current
        for _ in range(s.n_players):
            q = (q + 1) % s.n_players
            if s.alive[q]:
                break
        s.current = q
        if s.turn >= self.rules.max_turns:
            self.done = True
            self.capped = True

    # ------------------------------------------------------------------ movement & squares
    def move(self, p: int, steps: int, dice: int | None = None) -> None:
        s = self.s
        new = s.pos[p] + steps
        if new >= self.n_sq:
            new -= self.n_sq
            s.cash[p] += self.ed.go_salary
            s.passed_go[p] = True
        s.pos[p] = new
        self.last_dice = steps if dice is None else dice
        self.land(p, new)

    def move_to(self, p: int, dest: int, dice: int | None = None) -> None:
        """Move forward to `dest` (a full lap if dest is the current square)."""
        steps = (dest - self.s.pos[p]) % self.n_sq or self.n_sq
        self.move(p, steps, dice=dice)

    def land(self, p: int, sq: int) -> None:
        s = self.s
        if self.landings is not None:
            self.landings[sq] += 1
        t = self.types[sq]
        if t == T_STREET or t == T_STATION or t == T_UTILITY:
            o = s.owner[sq]
            if o == BANK:
                self.offer(p, sq)
            elif o != p and not s.mortgaged[sq]:
                self.charge(p, self.rent_due(sq), o)
        elif t == T_CHANCE:
            self.draw(p, "chance")
        elif t == T_CC:
            self.draw(p, "cc")
        elif t == T_TAX:
            self.charge(p, self.ed.tax[sq])
        elif t == T_GOTOJAIL:
            self.send_to_jail(p)
        elif t == T_FREE and self.rules.free_parking_jackpot:
            s.cash[p] += s.pot
            s.pot = 0

    def send_to_jail(self, p: int) -> None:
        s = self.s
        s.pos[p] = self.ed.jail_square
        s.in_jail[p] = True
        s.jail_turns[p] = 0

    # ------------------------------------------------------------------ rent
    def owns_group(self, p: int, g: int) -> bool:
        owner = self.s.owner
        return all(owner[sq] == p for sq in self.ed.group_squares[g])

    def rent_due(self, sq: int, dice: int | None = None) -> int:
        s, ed = self.s, self.ed
        o = s.owner[sq]
        t = self.types[sq]
        if t == T_STREET:
            lvl = s.level[sq]
            if lvl:
                return ed.rent[sq][lvl]
            base = ed.rent[sq][0]
            return base * 2 if self.owns_group(o, ed.group_of[sq]) else base
        sqs = ed.group_squares[ed.group_of[sq]]
        k = sum(1 for x in sqs if s.owner[x] == o and not s.mortgaged[x])
        if t == T_STATION:
            return ed.station_rent[k - 1]
        return ed.utility_multiplier[k - 1] * (dice if dice is not None else self.last_dice)

    # ------------------------------------------------------------------ buying & auctions
    def offer(self, p: int, sq: int) -> None:
        s = self.s
        price = self.ed.price[sq]
        if s.cash[p] >= price and self.policies[p].buy(self, p, sq):
            s.cash[p] -= price
            s.owner[sq] = p
            if self.stats is not None:
                self.stats[p][ST_BOUGHT] += 1
        elif self.rules.auctions:
            self.auction(sq)

    def auction(self, sq: int) -> tuple[int, int] | None:
        """Ascending auction, resolved from each player's private maximum bid.

        With £1 increments an English auction ends at (second-highest max + 1),
        capped at the winner's max. Ties go to the earliest bidder in turn order.
        """
        s = self.s
        best, best_bid, second = None, 0, 0
        for i in range(s.n_players):
            q = (s.current + i) % s.n_players
            if not s.alive[q]:
                continue
            b = min(int(self.policies[q].max_bid(self, q, sq)), s.cash[q])
            if b > best_bid:
                second, best_bid, best = best_bid, b, q
            elif b > second:
                second = b
        if best is None or best_bid < self.rules.min_bid:
            if not self.rules.no_bid_to_richest:
                return None
            # championship rule: with no bids the richest player gets it for the minimum bid
            alive = [q for q in range(s.n_players) if s.alive[q] and s.cash[q] >= self.rules.min_bid]
            if not alive:
                return None
            best = max(alive, key=lambda q: s.cash[q])
            s.cash[best] -= self.rules.min_bid
            s.owner[sq] = best
            if self.stats is not None:
                self.stats[best][ST_AUCTION] += 1
            return best, self.rules.min_bid
        price = max(self.rules.min_bid, min(best_bid, second + 1))
        s.cash[best] -= price
        s.owner[sq] = best
        if self.stats is not None:
            self.stats[best][ST_AUCTION] += 1
        return best, price

    # ------------------------------------------------------------------ cards
    def _reshuffle(self, dq: deque) -> None:
        cards = list(dq)
        self.deck_rng.shuffle(cards)
        dq.clear()
        dq.extend(cards)

    def draw(self, p: int, deck: str) -> None:
        s, ed = self.s, self.ed
        dq = s.chance if deck == "chance" else s.cc
        cards = ed.chance if deck == "chance" else ed.community_chest
        self.draws[deck] += 1
        if self.rules.card_draw == "random":
            # true sampling with replacement: the deck never changes (a drawn
            # Get-out-of-Jail-free card is handed out as a copy). Matches the Markov model.
            idx = dq[int(self.deck_rng.random() * len(dq))]
        else:
            idx = dq.popleft()
            if cards[idx].action != "goojf":
                dq.append(idx)  # back to the bottom of the pile
        self.apply_card(p, cards[idx], deck)

    def apply_card(self, p: int, card, deck: str) -> None:
        s = self.s
        a = card.action
        if a == "advance":
            if card.to <= s.pos[p]:  # passes (or lands on) GO
                s.cash[p] += self.ed.go_salary
                s.passed_go[p] = True
            s.pos[p] = card.to
            self.land(p, card.to)
        elif a == "back":
            to = (s.pos[p] - card.n) % self.n_sq
            s.pos[p] = to
            self.land(p, to)
        elif a == "back_to":
            s.pos[p] = card.to
            self.land(p, card.to)
        elif a == "jail":
            self.send_to_jail(p)
        elif a == "pay":
            self.charge(p, card.amount)
        elif a == "collect":
            s.cash[p] += card.amount
        elif a == "repairs":
            houses, hotels = self.count_buildings(p)
            self.charge(p, houses * card.house + hotels * card.hotel)
        elif a == "goojf":
            s.goojf[p].append(deck)
        elif a == "birthday":
            for q in range(s.n_players):
                if not s.alive[p] or self.done:
                    break  # the drawer went bankrupt mid-collection
                if q != p and s.alive[q]:
                    self.charge(q, card.amount, p)
        elif a == "fine_or_chance":
            if self.policies[p].fine_or_chance(self, p) == "chance":
                self.draw(p, "chance")
            else:
                self.charge(p, card.amount)
        else:  # pragma: no cover
            raise ValueError(f"unknown card action {a}")

    def use_goojf(self, p: int) -> None:
        s = self.s
        self._return_goojf(s.goojf[p].pop())
        s.in_jail[p] = False
        s.jail_turns[p] = 0

    def _return_goojf(self, deck: str) -> None:
        """Put a used/forfeited Get-out-of-Jail-free card back at the bottom of its deck."""
        if self.rules.card_draw == "random":
            return  # the card was a copy; the deck never lost it
        s = self.s
        dq = s.chance if deck == "chance" else s.cc
        cards = self.ed.chance if deck == "chance" else self.ed.community_chest
        dq.append(next(i for i, c in enumerate(cards) if c.action == "goojf"))

    # ------------------------------------------------------------------ money
    def _pay_bank(self, p: int, amount: int, to_pot: bool = True) -> None:
        self.s.cash[p] -= amount
        if to_pot and self.rules.free_parking_jackpot:
            self.s.pot += amount

    def charge(self, p: int, amount: int, creditor: int | None = None, to_pot: bool = True) -> bool:
        """Make player p pay `amount` to `creditor` (None = bank). Returns False if p went bankrupt."""
        if amount <= 0:
            return True
        s = self.s
        if creditor is not None and not s.alive[creditor]:
            creditor = None  # a bankrupt creditor's claims lapse to the bank
        if s.cash[p] < amount:
            self.policies[p].raise_cash(self, p, amount)
        if s.cash[p] >= amount:
            if creditor is None:
                self._pay_bank(p, amount, to_pot)
            else:
                s.cash[p] -= amount
                s.cash[creditor] += amount
            return True
        self.bankrupt(p, creditor)
        return False

    def bankrupt(self, p: int, creditor: int | None) -> None:
        s, ed = self.s, self.ed
        # any buildings left are sold to the bank at half price first
        for sq in ed.ownable:
            if s.owner[sq] == p and s.level[sq]:
                self._sell_levels(sq, s.level[sq])
        props = [sq for sq in ed.ownable if s.owner[sq] == p]
        s.alive[p] = False
        s.elimination_order.append(p)
        if creditor is not None and s.alive[creditor]:
            s.cash[creditor] += s.cash[p]
            s.cash[p] = 0
            fee = 0
            for sq in props:
                s.owner[sq] = creditor
                if s.mortgaged[sq]:
                    fee += ed.unmortgage_cost(sq) - ed.mortgage_value(sq)
            s.goojf[creditor].extend(s.goojf[p])
            s.goojf[p] = []
            if sum(s.alive) <= 1:
                self.done = True
                return
            if fee:
                self.charge(creditor, fee, to_pot=False)  # 10% interest on inherited mortgages
        else:
            s.cash[p] = 0
            while s.goojf[p]:
                self._return_goojf(s.goojf[p].pop())
            for sq in props:
                s.owner[sq] = BANK
                s.mortgaged[sq] = False
            if sum(s.alive) <= 1:
                self.done = True
                return
            if self.rules.auctions:
                for sq in props:
                    self.auction(sq)
        if sum(s.alive) <= 1:
            self.done = True

    # ------------------------------------------------------------------ building & mortgages
    def count_buildings(self, p: int) -> tuple[int, int]:
        s = self.s
        houses = hotels = 0
        for sq in self.ed.ownable:
            if s.owner[sq] == p:
                lv = s.level[sq]
                if lv == HOTEL:
                    hotels += 1
                else:
                    houses += lv
        return houses, hotels

    def group_has_buildings(self, g: int) -> bool:
        lv = self.s.level
        return any(lv[sq] for sq in self.ed.group_squares[g])

    def can_build(self, p: int, sq: int) -> bool:
        s, ed = self.s, self.ed
        if self.types[sq] != T_STREET or s.owner[sq] != p:
            return False
        g = ed.group_of[sq]
        sqs = ed.group_squares[g]
        lv = s.level[sq]
        if lv >= HOTEL or s.cash[p] < ed.house_cost[g]:
            return False
        if not self.owns_group(p, g) or any(s.mortgaged[x] for x in sqs):
            return False
        if lv != min(s.level[x] for x in sqs):  # even-build rule
            return False
        if lv == 4:
            return s.bank_hotels > 0
        return s.bank_houses > 0

    def build(self, p: int, sq: int) -> bool:
        if not self.can_build(p, sq):
            return False
        s, ed = self.s, self.ed
        s.cash[p] -= ed.house_cost[ed.group_of[sq]]
        if s.level[sq] == 4:
            s.bank_hotels -= 1
            s.bank_houses += 4
        else:
            s.bank_houses -= 1
        s.level[sq] += 1
        return True

    def can_sell_building(self, p: int, sq: int) -> bool:
        s = self.s
        if s.owner[sq] != p or s.level[sq] == 0:
            return False
        sqs = self.ed.group_squares[self.ed.group_of[sq]]
        return s.level[sq] == max(s.level[x] for x in sqs)  # even-sell rule

    def sell_building(self, p: int, sq: int) -> bool:
        if not self.can_sell_building(p, sq):
            return False
        self._sell_levels(sq, 1)
        return True

    def _sell_levels(self, sq: int, n: int) -> None:
        """Sell n building levels on sq back to the bank at half cost."""
        s, ed = self.s, self.ed
        p = s.owner[sq]
        hc = ed.house_cost[ed.group_of[sq]]
        start = s.level[sq]
        target = start - n
        if start == HOTEL:
            # breaking a hotel needs houses from the bank to replace it
            s.bank_hotels += 1
            want = target
            if s.bank_houses < want:
                target = s.bank_houses  # shortage: sell further down than requested
                self.uneven_events += 1
            s.bank_houses -= target
        else:
            s.bank_houses += n
        s.level[sq] = target
        s.cash[p] += (start - target) * hc // 2

    def can_mortgage(self, p: int, sq: int) -> bool:
        s = self.s
        if s.owner[sq] != p or s.mortgaged[sq]:
            return False
        return not self.group_has_buildings(self.ed.group_of[sq])

    def mortgage(self, p: int, sq: int) -> bool:
        if not self.can_mortgage(p, sq):
            return False
        self.s.mortgaged[sq] = True
        self.s.cash[p] += self.ed.mortgage_value(sq)
        return True

    def unmortgage(self, p: int, sq: int) -> bool:
        s = self.s
        cost = self.ed.unmortgage_cost(sq)
        if s.owner[sq] != p or not s.mortgaged[sq] or s.cash[p] < cost:
            return False
        s.cash[p] -= cost
        s.mortgaged[sq] = False
        return True

    # ------------------------------------------------------------------ trading
    def trade_is_valid(self, a: int, b: int, a_gives=(), b_gives=(), cash_a_to_b: int = 0) -> bool:
        s, ed = self.s, self.ed
        if a == b or not (s.alive[a] and s.alive[b]):
            return False
        if self.rules.no_trades_heads_up and sum(s.alive) <= 2:
            return False
        if any(s.owner[sq] != a for sq in a_gives) or any(s.owner[sq] != b for sq in b_gives):
            return False
        if self.frozen and any(sq in self.frozen for sq in (*a_gives, *b_gives)):
            return False
        # classic rule: buildings in a colour group must be sold before any of it is traded
        for sq in (*a_gives, *b_gives):
            if self.group_has_buildings(ed.group_of[sq]):
                return False
        fee_a = sum(self._transfer_fee(sq) for sq in b_gives)  # a receives b's properties
        fee_b = sum(self._transfer_fee(sq) for sq in a_gives)
        return (s.cash[a] - cash_a_to_b >= fee_a) and (s.cash[b] + cash_a_to_b >= fee_b)

    def _transfer_fee(self, sq: int) -> int:
        if not self.s.mortgaged[sq]:
            return 0
        return self.ed.unmortgage_cost(sq) - self.ed.mortgage_value(sq)  # 10% interest

    def execute_trade(self, a: int, b: int, a_gives=(), b_gives=(), cash_a_to_b: int = 0) -> bool:
        """Swap properties and cash between players a and b (mortgages travel with a 10% fee)."""
        if not self.trade_is_valid(a, b, a_gives, b_gives, cash_a_to_b):
            return False
        s = self.s
        if self.stats is not None:
            self.stats[a][ST_TRADES] += 1
            self.stats[b][ST_TRADES] += 1
        s.cash[a] -= cash_a_to_b
        s.cash[b] += cash_a_to_b
        for sq in a_gives:
            s.owner[sq] = b
            s.cash[b] -= self._transfer_fee(sq)
        for sq in b_gives:
            s.owner[sq] = a
            s.cash[a] -= self._transfer_fee(sq)
        return True

    # ------------------------------------------------------------------ valuation helpers
    def net_worth(self, p: int) -> int:
        s, ed = self.s, self.ed
        if not s.alive[p]:
            return 0
        total = s.cash[p]
        for sq in ed.ownable:
            if s.owner[sq] == p:
                total += ed.mortgage_value(sq) if s.mortgaged[sq] else ed.price[sq]
                if s.level[sq]:
                    total += s.level[sq] * ed.house_cost[ed.group_of[sq]]
        return total

    def result(self) -> GameResult:
        s = self.s
        nw = [self.net_worth(p) for p in range(s.n_players)]
        alive = [p for p in range(s.n_players) if s.alive[p]]
        if len(alive) == 1:
            winner = alive[0]
        elif alive:  # capped: richest surviving player
            winner = max(alive, key=lambda q: nw[q])
        else:  # everyone went bankrupt in one chain of payments: last one out wins
            winner = s.elimination_order[-1]
        return GameResult(winner=winner, capped=self.capped, turns=s.turn,
                          net_worth=nw, elimination_order=s.elimination_order[:],
                          stalemate=self.rules.stalemate)


def play_game(policies, seed=None, rules=None, edition=None, **kw) -> GameResult:
    return Game(policies, edition=edition, rules=rules, seed=seed, **kw).play()
