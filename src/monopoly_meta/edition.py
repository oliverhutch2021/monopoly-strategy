"""Load a board edition (squares, prices, rents, cards) from a JSON config.

Everything edition-specific lives in ``data/<edition>.json`` so the engine,
Markov model and analyses can be re-run on another board (e.g. a US edition)
without code changes.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

OWNABLE_TYPES = {"street", "station", "utility"}


@dataclass(frozen=True)
class Card:
    text: str
    action: str
    to: int | None = None
    n: int | None = None
    amount: int | None = None
    house: int | None = None
    hotel: int | None = None


@dataclass
class Edition:
    name: str
    raw: dict
    names: list[str]
    types: list[str]
    price: list[int]
    rent: list[list[int]]          # street rent table [site, 1h, 2h, 3h, 4h, hotel]
    group_of: list[int]            # group index per square (-1 if not ownable)
    group_names: list[str]
    group_squares: list[list[int]]
    house_cost: list[int]          # per group (0 for stations / utilities)
    tax: list[int]                 # tax amount per square (0 otherwise)
    chance: list[Card]
    community_chest: list[Card]
    station_rent: list[int]
    utility_multiplier: list[int]
    start_cash: int
    go_salary: int
    jail_fine: int
    jail_square: int
    go_to_jail_square: int
    max_jail_turns: int
    bank_houses: int
    bank_hotels: int
    mortgage_interest: float
    ownable: list[int] = field(default_factory=list)
    street_groups: list[int] = field(default_factory=list)

    @property
    def n_squares(self) -> int:
        return len(self.names)

    def is_ownable(self, sq: int) -> bool:
        return self.types[sq] in OWNABLE_TYPES

    def mortgage_value(self, sq: int) -> int:
        return self.price[sq] // 2

    def unmortgage_cost(self, sq: int) -> int:
        # mortgage value plus interest, rounded up to whole pounds
        mv = self.mortgage_value(sq)
        return mv + math.ceil(round(mv * self.mortgage_interest, 6))

    def group_by_name(self, name: str) -> int:
        return self.group_names.index(name)


def _card(d: dict) -> Card:
    return Card(
        text=d["text"], action=d["action"], to=d.get("to"), n=d.get("n"),
        amount=d.get("amount"), house=d.get("house"), hotel=d.get("hotel"),
    )


@lru_cache(maxsize=None)
def load_edition(name: str = "uk_classic") -> Edition:
    path = DATA_DIR / f"{name}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    squares = raw["squares"]
    n = len(squares)
    assert [s["i"] for s in squares] == list(range(n)), "squares must be in board order"

    group_names = list(raw["groups"].keys())
    group_squares = [raw["groups"][g]["squares"] for g in group_names]
    house_cost = [raw["groups"][g]["house_cost"] or 0 for g in group_names]

    group_of = [-1] * n
    for gi, sqs in enumerate(group_squares):
        for sq in sqs:
            group_of[sq] = gi

    ed = Edition(
        name=raw["edition"],
        raw=raw,
        names=[s["name"] for s in squares],
        types=[s["type"] for s in squares],
        price=[s.get("price", 0) for s in squares],
        rent=[s.get("rent", []) for s in squares],
        group_of=group_of,
        group_names=group_names,
        group_squares=group_squares,
        house_cost=house_cost,
        tax=[s.get("amount", 0) if s["type"] == "tax" else 0 for s in squares],
        chance=[_card(c) for c in raw["chance"]],
        community_chest=[_card(c) for c in raw["community_chest"]],
        station_rent=raw["station_rent"],
        utility_multiplier=raw["utility_multiplier"],
        start_cash=raw["start_cash"],
        go_salary=raw["go_salary"],
        jail_fine=raw["jail_fine"],
        jail_square=raw["jail_square"],
        go_to_jail_square=raw["go_to_jail_square"],
        max_jail_turns=raw["max_jail_turns"],
        bank_houses=raw["bank_houses"],
        bank_hotels=raw["bank_hotels"],
        mortgage_interest=raw["mortgage_interest"],
    )
    ed.ownable = [i for i in range(n) if ed.is_ownable(i)]
    ed.street_groups = [gi for gi, sqs in enumerate(group_squares)
                        if ed.types[sqs[0]] == "street"]
    return ed
