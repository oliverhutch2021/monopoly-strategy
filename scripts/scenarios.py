"""Hand-built mid-game positions used in the write-up and the tests."""
import random

from monopoly_meta import load_edition
from monopoly_meta.engine import GameState

# Player 0 and Player 1 are the same at every player count; each extra player ("bystander")
# adds four scattered properties, chosen so that nobody else is close to a set.
CORE = {
    0: (["Bow Street", "Marlborough Street", "Kings Cross Station", "Whitechapel Road"], 1200, 5),
    1: (["Vine Street", "Pall Mall", "Electric Company", "Euston Road"], 800, 24),
}
BYSTANDERS = [
    (["Strand", "Fleet Street", "Leicester Square", "Marylebone Station"], 900, 31),
    (["Coventry Street", "Regent Street", "Park Lane", "Old Kent Road"], 850, 12),
    (["The Angel Islington", "Northumberland Avenue", "Fenchurch St Station", "Oxford Street"], 875, 20),
    (["Pentonville Road", "Whitehall", "Liverpool Street Station", "Bond Street"], 875, 36),
]


def orange_squeeze(n_players: int = 4) -> GameState:
    """Ten rounds in. Player 0 holds two oranges; Player 1 holds the third (Vine Street).

    Works for 2-6 players: players 2+ are bystanders with four unrelated properties each.
    """
    if not 2 <= n_players <= 6:
        raise ValueError("orange_squeeze supports 2-6 players")
    ed = load_edition()
    s = GameState.new(ed, n_players, random.Random(2026))
    seats = [CORE[0], CORE[1], *BYSTANDERS[: n_players - 2]]
    for p, (names, cash, pos) in enumerate(seats):
        for name in names:
            s.owner[ed.names.index(name)] = p
        s.cash[p] = cash
        s.pos[p] = pos
    s.current = 2 % n_players  # the player after the seller moves next
    s.turn = 10 * n_players
    s.passed_go = [True] * n_players  # ten rounds in, everyone has been round the board
    return s


# Spare properties for topping up a hand, in order. Taken only when the player holds nothing
# else in that group, so nobody but the buyer ends up close to a set.
SPARES = ["Trafalgar Square", "Piccadilly", "Water Works", "Mayfair", "Old Kent Road", "Whitechapel Road",
          "Kings Cross Station", "Marylebone Station", "Pall Mall", "Electric Company", "Euston Road",
          "Strand", "Leicester Square", "Regent Street", "Park Lane", "The Angel Islington",
          "Northumberland Avenue", "Fenchurch St Station", "Oxford Street", "Pentonville Road",
          "Whitehall", "Liverpool Street Station", "Bond Street", "Fleet Street", "Coventry Street",
          "Bow Street", "Marlborough Street", "Vine Street"]


def set_completion(target: str, n_players: int = 4) -> GameState:
    """The orange squeeze, generalised: Player 1 owns `target`; Player 0 owns the rest of its group.

    Same cash, positions and turn as `orange_squeeze`. Players keep their usual properties
    except any in the target's group, which are taken away; everyone is then topped up to four
    properties from SPARES, never taking a second piece of a group or the piece that would
    leave another player one short of a set.
    For Vine Street this reproduces `orange_squeeze` exactly.
    """
    if not 2 <= n_players <= 6:
        raise ValueError("set_completion supports 2-6 players")
    ed = load_edition()
    t = ed.names.index(target)
    if not ed.is_ownable(t):
        raise ValueError(f"{target} can't be owned")
    group = [sq for sq in range(len(ed.names)) if ed.is_ownable(sq) and ed.group_of[sq] == ed.group_of[t]]
    seats = [CORE[0], CORE[1], *BYSTANDERS[: n_players - 2]]
    usual = {0: ["Kings Cross Station", "Whitechapel Road"], 1: ["Pall Mall", "Electric Company", "Euston Road"]}
    hands = [[ed.names.index(x) for x in usual.get(p, names)] for p, (names, _, _) in enumerate(seats)]
    hands = [[sq for sq in h if sq not in group] for h in hands]
    hands[0] = [sq for sq in group if sq != t] + hands[0]
    hands[1] = [t] + hands[1]
    owned = {sq for h in hands for sq in h}
    for p, h in enumerate(hands):
        for name in SPARES:
            if len(h) >= 4:
                break
            sq = ed.names.index(name)
            same = [x for hand in hands for x in hand if ed.group_of[x] == ed.group_of[sq]]
            if sq in owned or sq in group or any(x in h for x in same) or len(same) >= 2:
                continue  # never a second piece of a group, nor the last piece someone needs
            h.append(sq)
            owned.add(sq)
    s = GameState.new(ed, n_players, random.Random(2026))
    for p, (h, (_, cash, pos)) in enumerate(zip(hands, seats)):
        for sq in h:
            s.owner[sq] = p
        s.cash[p] = cash
        s.pos[p] = pos
    s.current = 2 % n_players
    s.turn = 10 * n_players
    s.passed_go = [True] * n_players
    return s
