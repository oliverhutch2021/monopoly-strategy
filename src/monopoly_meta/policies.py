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

from .engine import BANK, HOTEL, T_STREET


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

    def raise_cash(self, g, p, target) -> None:
        default_liquidation(g, p, target)

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


def default_liquidation(g, p, target) -> None:
    """Raise cash up to `target` doing the least damage first.

    1. mortgage properties that are not part of a complete street set (cheapest first)
    2. sell buildings, choosing the sale that loses least rent per pound raised
    3. mortgage what is left (cheapest first)
    """
    s, ed = g.s, g.ed
    mine = [sq for sq in ed.ownable if s.owner[sq] == p]

    def in_set(sq):
        return g.types[sq] == T_STREET and g.owns_group(p, ed.group_of[sq])

    for sq in sorted((x for x in mine if not in_set(x)), key=lambda x: ed.price[x]):
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

    def _weight(self, g, sq) -> float:
        return self.group_weight.get(g.ed.group_names[g.ed.group_of[sq]], 1.0)

    def buy(self, g, p, sq) -> bool:
        cash, price = g.s.cash[p], g.ed.price[sq]
        if completes_set(g, p, sq):
            return cash >= price
        w = self._weight(g, sq)
        if w <= 0:
            return False
        return cash - price >= self.reserve / w

    def max_bid(self, g, p, sq) -> int:
        price, cash = g.ed.price[sq], g.s.cash[p]
        if completes_set(g, p, sq):
            return int(min(cash, price * self.bid_frac * self.set_bonus))
        val = price * self.bid_frac * self._weight(g, sq)
        if blocks_opponent(g, p, sq):
            val *= self.block_bonus
        return int(max(0, min(val, cash - self.reserve)))

    def jail_decision(self, g, p) -> str:
        if self.jail == "long":
            return "roll"
        if self.jail == "adaptive" and unowned_count(g) <= 6 and opponents_built(g, p) > 0:
            return "roll"  # late game: jail is a safe place to sit
        return "card" if g.s.goojf[p] else "pay"

    def fine_or_chance(self, g, p) -> str:
        return "chance" if self.take_chance else "fine"

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
            return cash_in + face_get >= self.ask_mult * face_give
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
        s, ed = g.s, g.ed
        if self.trades:
            self._try_trade(g, p)
        # 1. unmortgage pieces of complete sets (needed before we can build), then the rest
        mortgaged = [sq for sq in ed.ownable if s.owner[sq] == p and s.mortgaged[sq]]
        if mortgaged:
            def key(sq):
                in_set = g.types[sq] == T_STREET and g.owns_group(p, ed.group_of[sq])
                return (not in_set, -ed.price[sq])
            for sq in sorted(mortgaged, key=key):
                if s.cash[p] - ed.unmortgage_cost(sq) >= self.build_reserve:
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
                    if s.cash[p] - hc < self.build_reserve:
                        continue
                    for sq in ed.group_squares[gi]:
                        lv = s.level[sq]
                        if lv < cap and g.can_build(p, sq):
                            score = (ed.rent[sq][lv + 1] - ed.rent[sq][lv]) / hc
                            if score > best_score:
                                best, best_score = sq, score
                if best is None:
                    break
                g.build(p, best)


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
