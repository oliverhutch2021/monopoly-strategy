"""Bot strategies (policies).

A policy answers the engine's decision points:

* ``buy``            - buy an unowned property you landed on (else it is auctioned)
* ``max_bid``        - private maximum in an auction
* ``jail_decision``  - "card", "pay" or "roll"
* ``fine_or_chance`` - the classic UK "Pay a £10 fine or take a Chance" card
* ``manage``         - end-of-turn building / unmortgaging
* ``raise_cash``     - what to sell or mortgage when short of cash
* ``accept_trade``   - respond to another player's trade proposal

The hand-written bots here are deliberately simple and parameterised: they are the
opponents the meta is measured against, and the starting population for the
evolutionary / value-model agents on the roadmap.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .engine import BANK, HOTEL, T_CC, T_CHANCE, T_GOTOJAIL, T_STATION, T_STREET, T_TAX, T_UTILITY

DICE_2D6 = tuple((d, (6 - abs(d - 7)) / 36) for d in range(2, 13))  # (total, probability)


class Policy:
    name = "base"

    def buy(self, g, p, sq) -> bool:
        return True

    def max_bid(self, g, p, sq) -> int:
        return 0

    def jail_decision(self, g, p) -> str:
        return "roll"

    def fine_or_chance(self, g, p) -> str:
        return "fine"

    def manage(self, g, p) -> None:
        pass

    def manage_buildings(self, g, p) -> None:
        """Building and unmortgaging only, no trades: what a player may also do between other players' turns when
        Rules.build_any_time is on."""
        pass

    def house_bid(self, g, p) -> tuple[int, int, int | None]:
        """When houses are auctioned (Rules.house_auctions): (houses wanted right now, the most it would pay for
        the next one, the square that house is for). The limit must cover that square's house price, and a won
        house goes on that square, so a bid never pays for a dearer house than the one it was made for."""
        return 0, 0, None

    def raise_cash(self, g, p, target) -> None:
        default_liquidation(g, p, target)

    def lift_on_transfer(self, g, p, sq) -> bool:
        """Under Rules.mortgage_transfer_choice: lift a mortgaged property just received at once (its value + 10%)
        rather than pay the 10% now and keep it mortgaged."""
        return False

    def hotels_wanted(self, g, p) -> int:
        """How many hotels it would build right now if the bank had them (for counting hotel shortages)."""
        return 0

    def accept_trade(self, g, me, other, give, get, cash_in) -> bool:
        return False

    # Speed Die decisions (championship mode)
    def bus_choice(self, g, p, options) -> int:
        """Bus: move by one number die or both. Default: the best-looking destination."""
        n = g.n_sq
        return max(options, key=lambda st: destination_score(g, p, (g.s.pos[p] + st) % n, self))

    def triple_destination(self, g, p) -> int:
        """Triple: move to any square. Default: the best-looking square on the board."""
        return max(range(g.n_sq), key=lambda sq: destination_score(g, p, sq, self))

    def __repr__(self) -> str:
        return self.name


# ---------------------------------------------------------------------- shared helpers
def completes_set(g, p, sq) -> bool:
    """Would owning sq give p the whole colour group?"""
    ed, owner = g.ed, g.s.owner
    return all(owner[x] == p or x == sq for x in ed.group_squares[ed.group_of[sq]])


def blocks_opponent(g, p, sq) -> bool:
    """Is sq the last piece another single player needs for a set?"""
    ed, owner = g.ed, g.s.owner
    others = [owner[x] for x in ed.group_squares[ed.group_of[sq]] if x != sq]
    return bool(others) and others[0] not in (BANK, p) and all(o == others[0] for o in others)


def missing_piece(g, p, gi):
    """If p owns all but one square of street group gi, return that square, else None."""
    owner = g.s.owner
    missing = [sq for sq in g.ed.group_squares[gi] if owner[sq] != p]
    return missing[0] if len(missing) == 1 else None


def gives_set(g, p, get, give=()) -> bool:
    """Would receiving `get` (and giving away `give`) complete a street set for p?"""
    ed, owner = g.ed, g.s.owner
    for sq in get:
        if g.types[sq] != T_STREET:
            continue
        sqs = ed.group_squares[ed.group_of[sq]]
        if all((owner[x] == p and x not in give) or x in get for x in sqs):
            return True
    return False


def destination_score(g, p, sq, policy=None) -> float:
    """Rough value of landing on sq, used for Speed Die choices (Bus, triples).

    Unowned properties we can afford are good (very good if they complete our set or block a
    rival's), opponents' properties cost their rent, taxes cost their amount, and Go To Jail is
    bad early but a safe haven late in the game.
    """
    s, ed = g.s, g.ed
    t = ed.types[sq]
    if ed.is_ownable(sq):
        o = s.owner[sq]
        if o == BANK:
            if s.cash[p] < ed.price[sq]:
                return 0.2
            w = policy._weight(g, sq) if hasattr(policy, "_weight") else 1.0
            if completes_set(g, p, sq):
                return 5.0
            return 1.0 * w + (1.0 if blocks_opponent(g, p, sq) else 0.0)
        if o == p or s.mortgaged[sq]:
            return 0.1
        return -g.rent_due(sq, dice=7) / 100
    if t == "tax":
        return -ed.tax[sq] / 100
    if t == "go_to_jail":
        return 0.3 if unowned_count(g) <= 6 and opponents_built(g, p) else -0.5
    if t == "go":
        return 0.5
    return 0.1  # free parking, just visiting, chance / community chest


def default_liquidation(g, p, target, houses_last: bool = False) -> None:
    """Raise cash up to `target` doing the least damage first.

    1. mortgage properties that are not part of a complete street set (cheapest first)
    2. sell buildings, choosing the sale that loses least rent per pound raised
    3. mortgage what is left (cheapest first)

    houses_last mortgages everything it can before selling any building, so the buildings (and the rent
    they earn) stay up and the houses stay off the bank's shelf (HeuristicBot.protect).
    """
    s, ed = g.s, g.ed
    mine = [sq for sq in ed.ownable if s.owner[sq] == p]

    def in_set(sq):
        return g.types[sq] == T_STREET and g.owns_group(p, ed.group_of[sq])

    for sq in sorted((x for x in mine if not in_set(x)), key=lambda x: ed.price[x]):
        if s.cash[p] >= target:
            return
        g.mortgage(p, sq)

    if houses_last:
        for sq in sorted(mine, key=lambda x: ed.price[x]):
            if s.cash[p] >= target:
                return
            g.mortgage(p, sq)

    while s.cash[p] < target:
        best, best_score = None, None
        for sq in mine:
            if s.level[sq] and g.can_sell_building(p, sq):
                lv = s.level[sq]
                hc = ed.house_cost[ed.group_of[sq]]
                score = (ed.rent[sq][lv] - ed.rent[sq][lv - 1]) / (hc / 2)
                if best_score is None or score < best_score:
                    best, best_score = sq, score
        if best is None:
            break
        g.sell_building(p, best)

    for sq in sorted(mine, key=lambda x: ed.price[x]):
        if s.cash[p] >= target:
            return
        g.mortgage(p, sq)


def opponents_built(g, p) -> int:
    s = g.s
    return sum(s.level[sq] for sq in g.ed.ownable
               if s.owner[sq] not in (BANK, p) and s.level[sq])


def unowned_count(g) -> int:
    s = g.s
    return sum(1 for sq in g.ed.ownable if s.owner[sq] == BANK)


# ---------------------------------------------------------------------- helpers for the v0.4 moves
def landing_cost(g, p, sq, dice: int = 7) -> int:
    """What landing on sq would cost p right now: a rival's rent or a tax (cards and buying ignored)."""
    s = g.s
    t = g.types[sq]
    if t == T_STREET or t == T_STATION or t == T_UTILITY:
        o = s.owner[sq]
        if o != BANK and o != p and not s.mortgaged[sq]:
            return g.rent_due(sq, dice=dice)
        return 0
    return g.ed.tax[sq] if t == T_TAX else 0


def expected_exposure(g, p, frm: int) -> float:
    """Expected cost to p of one ordinary roll of two dice from square `frm`."""
    n = g.n_sq
    return sum(pr * landing_cost(g, p, (frm + d) % n, d) for d, pr in DICE_2D6)


def leader(g) -> int:
    """The player still in the game with the highest net worth (ties: lowest seat)."""
    s = g.s
    return max((q for q in range(s.n_players) if s.alive[q]), key=lambda q: (g.net_worth(q), -q))


def jail_value(g, p) -> float:
    """Rough cash value to p of being sent to jail now: a lost fine early, a safe haven late."""
    if unowned_count(g) > 6:
        return -g.ed.jail_fine
    return expected_exposure(g, p, g.ed.jail_square)


def square_value(g, p, sq: int) -> float:
    """Rough cash value to p of landing on sq (unowned property counts as neutral)."""
    if g.types[sq] == T_GOTOJAIL:
        return jail_value(g, p)
    return -landing_cost(g, p, sq)


def card_value(g, p, card) -> float:
    """Rough cash value to p of drawing `card` now."""
    s, ed = g.s, g.ed
    a = card.action
    if a == "collect":
        return card.amount
    if a in ("pay", "fine_or_chance"):
        return -card.amount
    if a == "birthday":
        return card.amount * (sum(s.alive) - 1)
    if a == "repairs":
        houses, hotels = g.count_buildings(p)
        return -(houses * card.house + hotels * card.hotel)
    if a == "goojf":
        return ed.jail_fine
    if a == "jail":
        return jail_value(g, p)
    if a == "advance":
        return (ed.go_salary if card.to <= s.pos[p] else 0) + square_value(g, p, card.to)
    if a == "back":
        return square_value(g, p, (s.pos[p] - card.n) % g.n_sq)
    if a == "back_to":
        return square_value(g, p, card.to)
    return 0.0


def next_card_values(g, p, deck: str) -> list[float]:
    """Values to p of the cards that could come next from `deck`, for a player who remembers every draw.

    Under the official rules a used card goes to the bottom, so everything drawn since the game began
    sits at the bottom in the order it was drawn, and the cards never drawn sit on top in an unknown
    order. A held Get Out of Jail Free card is out of the deck. So the next card is one of the
    never-drawn cards (all equally likely; which ones they are is known by elimination), or, once every
    card has been seen, exactly known. Only public information is used: how many cards have been drawn
    (Game.draws), who holds a Get Out of Jail Free card, and which cards those draws showed. With the
    'random' house rule (drawing with replacement) nothing can be remembered and every card is possible.
    """
    s, ed = g.s, g.ed
    dq = s.chance if deck == "chance" else s.cc
    cards = ed.chance if deck == "chance" else ed.community_chest
    if g.rules.card_draw != "deck":
        return [card_value(g, p, cards[i]) for i in dq]
    held = sum(h.count(deck) for h in s.goojf)
    seen = max(0, min(len(dq), min(g.draws[deck], len(cards)) - held))
    unseen = len(dq) - seen
    if unseen:
        return [card_value(g, p, cards[dq[i]]) for i in range(unseen)]  # the set, not its order
    return [card_value(g, p, cards[dq[0]])]


def can_build_ignoring_cash(g, p, sq) -> bool:
    """Engine.can_build without the 'can afford it' check (used to plan raising the money)."""
    s, ed = g.s, g.ed
    if g.types[sq] != T_STREET or s.owner[sq] != p:
        return False
    gi = ed.group_of[sq]
    sqs = ed.group_squares[gi]
    lv = s.level[sq]
    if lv >= HOTEL or not g.owns_group(p, gi) or any(s.mortgaged[x] for x in sqs):
        return False
    if lv != min(s.level[x] for x in sqs):
        return False
    return s.bank_hotels > 0 if lv == 4 else s.bank_houses > 0


def set_rival(g, p, sq) -> int:
    """The player who owns the rest of sq's colour group (call only when blocks_opponent is true)."""
    ed = g.ed
    return g.s.owner[next(x for x in ed.group_squares[ed.group_of[sq]] if x != sq)]


def fine_amount(ed) -> int:
    """The fine on the "Pay a £10 fine or take a Chance" card."""
    return next((c.amount for c in (*ed.chance, *ed.community_chest) if c.action == "fine_or_chance"), 10)


# ---------------------------------------------------------------------- heuristic bot
@dataclass
class HeuristicBot(Policy):
    """A configurable rule-based player.

    reserve        cash kept back after buying a property
    build_reserve  cash kept back after building
    group_weight   per-group multiplier on buying (0 = never buy that group)
    bid_frac       auction limit as a fraction of face value
    set_bonus      auction multiplier when the property completes our set
    block_bonus    auction multiplier when it stops an opponent completing theirs
    build_cap      stop building at this level until every set reaches it (3 = "three-house rule")
    max_level      never build beyond this level (4 = hold houses, never hotels: housing-shortage play)
    jail           "short" (leave asap), "long" (roll for doubles), "adaptive"
    take_chance    answer to "Pay a £10 fine or take a Chance"
    trades         propose set-completing trades (swaps first, then cash offers)
    accept_trades  consider other players' proposals at all
    offer_mult     cash offer for a set-completing piece, as a multiple of face value
    ask_mult       cash demanded before handing an opponent their set, as a multiple of face value

    Tactics (v0.4). Each is off at its default, and then the bot plays exactly as before:
    snipe          pass on a property at its printed price when every rival has less than snipe x the
                   price in cash, so it goes to auction, where nobody can bid it up to the price (0 = off)
    lock           housing lock: while the bank has at most this many houses and a rival owns a set that
                   still needs houses, stop at four houses instead of building hotels (0 = off)
    protect        when raising cash, mortgage everything else before selling a building, at any house
                   supply. None (the default) follows lock, as before the two were separated: a bot with
                   the housing lock also protects its buildings. An external review (2026-10-31) found
                   that this, not the hotel deferral, carried the lock's gain for the official 4-player
                   agent; scripts/15_rule_sensitivity.py measures each part.
    leverage       mortgage up to this share of our properties outside sets to build our sets to three
                   houses (0 = off)
    jail_exposure  stay in jail while one roll from there would cost at least this much on average, and
                   otherwise leave at once (0 = off: the jail setting decides)
    dodge          in Speed Die choices, also avoid squares from which the next roll is dangerous: the
                   expected cost of that roll times dodge counts against a square (0 = off)
    count_cards    remember every card drawn: "Pay a £10 fine or take a Chance" and Speed Die choices
                   use the cards that can actually come next
    leader_tax     ask this many times more before handing the richest player a set, and bid this many
                   times more to stop them completing one (1 = off)
    endgame_rounds in the last this-many rounds before the time limit, stay in jail and keep
                   endgame_reserve as the cash reserve for buying and building (0 = off)
    """
    name: str = "heuristic"
    reserve: int = 150
    build_reserve: int = 150
    group_weight: dict = field(default_factory=dict)
    bid_frac: float = 1.0
    set_bonus: float = 2.0
    block_bonus: float = 1.3
    build_cap: int = 5
    max_level: int = 5
    jail: str = "adaptive"
    take_chance: bool = False
    trades: bool = True
    accept_trades: bool = True
    offer_mult: float = 2.0
    ask_mult: float = 2.0
    # tactics (v0.4), all off by default
    snipe: float = 0.0
    lock: int = 0
    protect: bool | None = None
    leverage: float = 0.0
    jail_exposure: float = 0.0
    dodge: float = 0.0
    count_cards: bool = False
    leader_tax: float = 1.0
    endgame_rounds: int = 0
    endgame_reserve: float = 0.0

    def _weight(self, g, sq) -> float:
        return self.group_weight.get(g.ed.group_names[g.ed.group_of[sq]], 1.0)

    def _endgame(self, g) -> bool:
        """Within endgame_rounds rounds of the time limit?"""
        s = g.s
        return g.rules.max_turns - s.turn <= self.endgame_rounds * sum(s.alive)

    def buy(self, g, p, sq) -> bool:
        cash, price = g.s.cash[p], g.ed.price[sq]
        if completes_set(g, p, sq):
            return cash >= price
        w = self._weight(g, sq)
        if w <= 0:
            return False
        if self.snipe and g.rules.auctions and self._snipe(g, p, price):
            return False
        reserve = self.endgame_reserve if self.endgame_rounds and self._endgame(g) else self.reserve
        return cash - price >= reserve / w

    def _snipe(self, g, p, price) -> bool:
        """Every rival is too poor to bid the property up to its printed price."""
        s = g.s
        richest = max((s.cash[q] for q in range(s.n_players) if q != p and s.alive[q]), default=0)
        return richest < self.snipe * price

    def max_bid(self, g, p, sq) -> int:
        price, cash = g.ed.price[sq], g.s.cash[p]
        if completes_set(g, p, sq):
            return int(min(cash, price * self.bid_frac * self.set_bonus))
        val = price * self.bid_frac * self._weight(g, sq)
        if blocks_opponent(g, p, sq):
            val *= self.block_bonus
            if self.leader_tax != 1.0 and set_rival(g, p, sq) == leader(g):
                val *= self.leader_tax
        reserve = self.endgame_reserve if self.endgame_rounds and self._endgame(g) else self.reserve
        return int(max(0, min(val, cash - reserve)))

    def jail_decision(self, g, p) -> str:
        if self.endgame_rounds and self._endgame(g):
            return "roll"  # sit tight: a player in jail lands nowhere, so pays no rent
        if self.jail_exposure:
            if expected_exposure(g, p, g.ed.jail_square) >= self.jail_exposure:
                return "roll"
            return "card" if g.s.goojf[p] else "pay"
        if self.jail == "long":
            return "roll"
        if self.jail == "adaptive" and unowned_count(g) <= 6 and opponents_built(g, p) > 0:
            return "roll"  # late game: jail is a safe place to sit
        return "card" if g.s.goojf[p] else "pay"

    def fine_or_chance(self, g, p) -> str:
        if self.count_cards:
            vals = next_card_values(g, p, "chance")
            return "chance" if vals and sum(vals) / len(vals) > -fine_amount(g.ed) else "fine"
        return "chance" if self.take_chance else "fine"

    def bus_choice(self, g, p, options) -> int:
        if not (self.dodge or self.count_cards):
            return super().bus_choice(g, p, options)
        n = g.n_sq
        return max(options, key=lambda st: self._destination(g, p, (g.s.pos[p] + st) % n))

    def triple_destination(self, g, p) -> int:
        if not (self.dodge or self.count_cards):
            return super().triple_destination(g, p)
        return max(range(g.n_sq), key=lambda sq: self._destination(g, p, sq))

    def _destination(self, g, p, sq) -> float:
        """destination_score, with the cards that can come next (count_cards) and the danger of the
        roll after (dodge)."""
        score = destination_score(g, p, sq, self)
        t = g.types[sq]
        if self.count_cards and (t == T_CHANCE or t == T_CC):
            vals = next_card_values(g, p, "chance" if t == T_CHANCE else "cc")
            if vals:
                score += sum(vals) / len(vals) / 100 - 0.1  # in place of the flat 0.1 for a card square
        if self.dodge:
            score -= self.dodge * expected_exposure(g, p, sq) / 100
        return score

    def raise_cash(self, g, p, target) -> None:
        protect = bool(self.lock) if self.protect is None else bool(self.protect)
        default_liquidation(g, p, target, houses_last=protect)

    def _below_cap(self, g, p) -> bool:
        """Does p own a buildable set with a property still below build_cap?"""
        s, ed = g.s, g.ed
        for gi in ed.street_groups:
            sqs = ed.group_squares[gi]
            if g.owns_group(p, gi) and not any(s.mortgaged[x] for x in sqs) \
                    and min(s.level[x] for x in sqs) < self.build_cap:
                return True
        return False

    def accept_trade(self, g, me, other, give, get, cash_in) -> bool:
        if not self.accept_trades:
            return False
        ed = g.ed
        face_give = sum(ed.price[sq] for sq in give)
        face_get = sum(ed.price[sq] for sq in get)
        i_get_set = gives_set(g, me, get, give)
        they_get_set = gives_set(g, other, give, get)
        if i_get_set:  # happy to pay up to face difference for a set of my own
            return g.s.cash[me] + cash_in >= self.build_reserve // 2 and cash_in >= face_give - face_get - 50
        if they_get_set:
            ask = self.ask_mult
            if self.leader_tax != 1.0 and other == leader(g):
                ask *= self.leader_tax
            return cash_in + face_get >= ask * face_give
        return cash_in + face_get >= 1.2 * face_give

    def _try_trade(self, g, p) -> None:
        s, ed = g.s, g.ed
        for gi in ed.street_groups:
            sq_a = missing_piece(g, p, gi)
            if sq_a is None or g.group_has_buildings(gi):
                continue
            q = s.owner[sq_a]
            if q in (BANK, p):
                continue
            # (a) mutual set-completing swap, balanced at face value
            for gj in ed.street_groups:
                if gj == gi or g.group_has_buildings(gj):
                    continue
                sq_b = missing_piece(g, q, gj)
                if sq_b is None or s.owner[sq_b] != p:
                    continue
                cash = ed.price[sq_a] - ed.price[sq_b]  # p pays q the difference
                if g.trade_is_valid(p, q, (sq_b,), (sq_a,), cash) and \
                        g.policies[q].accept_trade(g, q, p, (sq_a,), (sq_b,), cash):
                    g.execute_trade(p, q, (sq_b,), (sq_a,), cash)
                    return
            # (b) cash offer for the missing piece
            offer = int(ed.price[sq_a] * self.offer_mult)
            if s.cash[p] - offer >= self.build_reserve and g.trade_is_valid(p, q, (), (sq_a,), offer) and \
                    g.policies[q].accept_trade(g, q, p, (sq_a,), (), offer):
                g.execute_trade(p, q, (), (sq_a,), offer)
                return

    def manage(self, g, p) -> None:
        if self.trades:
            self._try_trade(g, p)
            g.housing_check()  # a set this trade completed competes for scarce houses too (no-op by default)
        self.manage_buildings(g, p)

    def _build_reserve(self, g) -> float:
        return self.endgame_reserve if self.endgame_rounds and self._endgame(g) else self.build_reserve

    def lift_on_transfer(self, g, p, sq) -> bool:
        """It lifts a mortgage whenever its cash stays above its building reserve (as manage_buildings would this
        turn), so given the choice it lifts at once and saves the second 10%."""
        return g.s.cash[p] - g.ed.unmortgage_cost(sq) >= self._build_reserve(g)

    def hotels_wanted(self, g, p) -> int:
        """Squares at four houses it would turn into hotels now: its caps allow hotels, the housing lock isn't
        holding, the whole set is at four houses, and it can afford them above its reserve."""
        s, ed = g.s, g.ed
        if min(self.max_level, HOTEL) < HOTEL or self._below_cap(g, p) and self.build_cap < HOTEL:
            return 0
        if self.lock and self._locking(g, p):
            return 0
        budget, wanted = s.cash[p] - self._build_reserve(g), 0
        for gi in ed.street_groups:
            sqs = ed.group_squares[gi]
            if g.owns_group(p, gi) and not any(s.mortgaged[x] for x in sqs) and all(s.level[x] >= 4 for x in sqs):
                k = min(sum(s.level[x] == 4 for x in sqs), max(0, int(budget // ed.house_cost[gi])))
                wanted += k
                budget -= k * ed.house_cost[gi]
        return wanted

    def _house_cap(self, g, p) -> int:
        """The level it is building houses up to right now, as manage_buildings does: build_cap while one of its
        sets is below it, then max_level; at most 4 (a hotel isn't a house)."""
        top = min(self.max_level, HOTEL)
        cap = self.build_cap if self.build_cap < top and self._below_cap(g, p) else top
        return min(cap, 4)

    def house_bid(self, g, p) -> tuple[int, int, int | None]:
        """How many houses it would build now if the bank had them all (up to its current cap, within its cash
        and reserve); where the next one would go (the affordable square that adds the most rent per pound, as when
        building); and the most it pays for that house at auction: its price times (1 + bid_frac), its auction
        appetite for property applied to houses, within its cash and reserve. The limit is never below the price of
        the house it is for."""
        s, ed = g.s, g.ed
        budget = s.cash[p] - self._build_reserve(g)
        target = self._house_cap(g, p)
        wanted, left = 0, budget
        for gi in ed.street_groups:
            sqs = ed.group_squares[gi]
            if not g.owns_group(p, gi) or any(s.mortgaged[x] for x in sqs):
                continue
            hc = ed.house_cost[gi]
            k = min(sum(max(0, target - s.level[x]) for x in sqs), max(0, int(left // hc)))
            if k > 0:
                wanted += k
                left -= k * hc
        sq = self._next_house(g, p, budget) if wanted else None
        if sq is None:
            return 0, 0, None
        cost = ed.house_cost[ed.group_of[sq]]
        return wanted, int(min(cost * (1 + self.bid_frac), budget)), sq

    def _next_house(self, g, p, budget: float) -> int | None:
        """The square its next house goes on: the most rent per pound among the squares below its current cap that
        it may build on and can afford, as when building."""
        s, ed = g.s, g.ed
        cap = self._house_cap(g, p)
        options = [sq for gi in ed.street_groups for sq in ed.group_squares[gi]
                   if s.level[sq] < cap and ed.house_cost[gi] <= budget and g.can_build(p, sq)]
        if not options:
            return None
        return max(options, key=lambda sq: (ed.rent[sq][s.level[sq] + 1] - ed.rent[sq][s.level[sq]])
                   / ed.house_cost[ed.group_of[sq]])

    def manage_buildings(self, g, p) -> None:
        s, ed = g.s, g.ed
        build_reserve = self._build_reserve(g)
        # 1. unmortgage pieces of complete sets (needed before we can build), then the rest
        mortgaged = [sq for sq in ed.ownable if s.owner[sq] == p and s.mortgaged[sq]]
        if mortgaged:
            def key(sq):
                in_set = g.types[sq] == T_STREET and g.owns_group(p, ed.group_of[sq])
                return (not in_set, -ed.price[sq])
            for sq in sorted(mortgaged, key=key):
                if s.cash[p] - ed.unmortgage_cost(sq) >= build_reserve:
                    g.unmortgage(p, sq)
        # 2. build, best marginal rent per pound first, respecting the build cap
        top = min(self.max_level, HOTEL)
        for cap in sorted({min(self.build_cap, top), top}):
            if cap > self.build_cap and self._below_cap(g, p):
                break  # keep the cash for sets still under the cap
            while True:
                best, best_score = None, -1.0
                for gi in ed.street_groups:
                    hc = ed.house_cost[gi]
                    if s.cash[p] - hc < build_reserve:
                        continue
                    for sq in ed.group_squares[gi]:
                        lv = s.level[sq]
                        if lv < cap and g.can_build(p, sq):
                            if lv == 4 and self.lock and self._locking(g, p):
                                continue  # hold the four houses: the rival can't have them
                            score = (ed.rent[sq][lv + 1] - ed.rent[sq][lv]) / hc
                            if score > best_score:
                                best, best_score = sq, score
                if best is None:
                    break
                g.build(p, best)
        # 3. borrow against lone properties to bring our sets up to three houses
        if self.leverage:
            self._leverage(g, p, build_reserve)

    def _locking(self, g, p) -> bool:
        """Housing lock: the bank is short of houses and a rival still needs houses for a set."""
        s, ed = g.s, g.ed
        if s.bank_houses > self.lock:
            return False
        for gi in ed.street_groups:
            sqs = ed.group_squares[gi]
            q = s.owner[sqs[0]]
            if q == BANK or q == p or not s.alive[q]:
                continue
            if all(s.owner[x] == q for x in sqs) and not any(s.mortgaged[x] for x in sqs) \
                    and min(s.level[x] for x in sqs) < 4:
                return True
        return False

    def _leverage(self, g, p, build_reserve) -> None:
        """Mortgage lone properties (cheapest first, up to `leverage` of what they would raise) to
        build our sets up to three houses, the level where rents jump."""
        s, ed = g.s, g.ed
        target = min(3, self.build_cap, self.max_level)
        lone = sorted((sq for sq in ed.ownable if s.owner[sq] == p and not s.mortgaged[sq]
                       and not (g.types[sq] == T_STREET and g.owns_group(p, ed.group_of[sq]))),
                      key=lambda x: (ed.mortgage_value(x), x))
        budget = self.leverage * sum(ed.mortgage_value(x) for x in lone)
        raised = 0
        while True:
            best, best_score = None, -1.0
            for gi in ed.street_groups:
                hc = ed.house_cost[gi]
                for sq in ed.group_squares[gi]:
                    lv = s.level[sq]
                    if lv < target and can_build_ignoring_cash(g, p, sq):
                        score = (ed.rent[sq][lv + 1] - ed.rent[sq][lv]) / hc
                        if score > best_score:
                            best, best_score = sq, score
            if best is None:
                return
            hc = ed.house_cost[ed.group_of[best]]
            while s.cash[p] - hc < build_reserve and lone and raised + ed.mortgage_value(lone[0]) <= budget:
                sq = lone.pop(0)
                if g.mortgage(p, sq):
                    raised += ed.mortgage_value(sq)
            if s.cash[p] - hc < build_reserve or not g.build(p, best):
                return


# ---------------------------------------------------------------------- baselines
class RandomBot(Policy):
    """Coin-flip decisions: the 'no skill' baseline for luck-vs-skill analysis."""
    name = "random"

    def buy(self, g, p, sq) -> bool:
        return g.policy_rng.random() < 0.5

    def max_bid(self, g, p, sq) -> int:
        return int(g.policy_rng.random() * g.ed.price[sq])

    def jail_decision(self, g, p) -> str:
        return g.policy_rng.choice(["card", "pay", "roll"])

    def fine_or_chance(self, g, p) -> str:
        return g.policy_rng.choice(["fine", "chance"])

    def accept_trade(self, g, me, other, give, get, cash_in) -> bool:
        return g.policy_rng.random() < 0.5

    def manage(self, g, p) -> None:
        ed = g.ed
        if g.policy_rng.random() < 0.5:
            options = [sq for sq in ed.ownable if g.can_build(p, sq)]
            if options:
                g.build(p, g.policy_rng.choice(options))


class NeverBuyBot(Policy):
    """Never buys or bids. A floor for 'how much does owning anything matter?'."""
    name = "never_buy"

    def buy(self, g, p, sq) -> bool:
        return False

    def jail_decision(self, g, p) -> str:
        return "roll"


def bot_label(spec) -> str:
    """Display name for a bot spec (a preset name or a dict of HeuristicBot parameters)."""
    return spec if isinstance(spec, str) else spec.get("name", "custom")


def make_bot(kind, **kw) -> Policy:
    """Build a bot from a preset name, or from a dict of HeuristicBot parameters."""
    if isinstance(kind, dict):
        params = {**kind, **kw}
        params["group_weight"] = dict(params.get("group_weight", {}))
        return HeuristicBot(**params)
    presets = {
        "balanced": dict(name="balanced", reserve=150, build_reserve=150),
        "aggressive": dict(name="aggressive", reserve=0, build_reserve=0, bid_frac=1.2),
        "cautious": dict(name="cautious", reserve=400, build_reserve=400, bid_frac=0.8),
        "three_house": dict(name="three_house", reserve=150, build_reserve=150, build_cap=3),
        "hoarder": dict(name="hoarder", max_level=4),
        "jail_short": dict(name="jail_short", jail="short"),
        "jail_long": dict(name="jail_long", jail="long"),
        "take_chance": dict(name="take_chance", take_chance=True),
        "no_trade": dict(name="no_trade", trades=False),
        "hard_bargain": dict(name="hard_bargain", ask_mult=3.0, offer_mult=1.5),
    }
    if kind == "random":
        return RandomBot()
    if kind == "never_buy":
        return NeverBuyBot()
    params = {**presets[kind], **kw}
    return HeuristicBot(**params)
