from monopoly_meta import load_edition


def test_board_shape():
    ed = load_edition("uk_classic")
    assert ed.n_squares == 40
    assert len(ed.ownable) == 28
    assert sum(t == "street" for t in ed.types) == 22
    assert sum(t == "station" for t in ed.types) == 4
    assert sum(t == "utility" for t in ed.types) == 2
    assert len(ed.chance) == 16 and len(ed.community_chest) == 16


def test_known_totals_and_landmarks():
    ed = load_edition()
    assert sum(ed.price[sq] for sq in ed.ownable) == 5690
    assert ed.names[24] == "Trafalgar Square" and ed.price[24] == 240
    assert ed.names[39] == "Mayfair" and ed.rent[39] == [50, 200, 600, 1400, 1700, 2000]
    assert ed.tax[4] == 200 and ed.tax[38] == 100


def test_group_house_costs():
    ed = load_edition()
    hc = dict(zip(ed.group_names, ed.house_cost))
    assert hc["brown"] == hc["light_blue"] == 50
    assert hc["pink"] == hc["orange"] == 100
    assert hc["red"] == hc["yellow"] == 150
    assert hc["green"] == hc["dark_blue"] == 200


def test_mortgage_values():
    ed = load_edition()
    assert ed.mortgage_value(1) == 30 and ed.unmortgage_cost(1) == 33
    assert ed.mortgage_value(39) == 200 and ed.unmortgage_cost(39) == 220
    assert ed.unmortgage_cost(12) == 83  # 75 + 7.50 rounded up


def test_rent_tables_increase():
    ed = load_edition()
    for sq in ed.ownable:
        if ed.types[sq] == "street":
            r = ed.rent[sq]
            assert len(r) == 6 and all(a < b for a, b in zip(r, r[1:]))


def test_card_actions_are_known():
    ed = load_edition()
    known = {"advance", "back", "back_to", "jail", "pay", "collect", "repairs",
             "goojf", "birthday", "fine_or_chance"}
    for c in ed.chance + ed.community_chest:
        assert c.action in known
    assert sum(c.action == "goojf" for c in ed.chance) == 1
    assert sum(c.action == "goojf" for c in ed.community_chest) == 1
