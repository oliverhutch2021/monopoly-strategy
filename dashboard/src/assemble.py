"""Assemble dashboard/index.html: the v0.3 page (src/v03_index.html) with the themed header, board and
property card swapped in, and the shared helpers pointed at the theme's colours.

    python dashboard/src/assemble.py
"""
import re
from pathlib import Path

SRC = Path(__file__).parent
OUT = SRC.parent / "index.html"
page = (SRC / "v03_index.html").read_text()


def swap(old: str, new: str, count: int = 1) -> None:
    global page
    n = page.count(old)
    if n != count:
        raise SystemExit(f"expected {count} match(es), found {n}: {old[:80]!r}")
    page = page.replace(old, new)


# 1. the theme and the 3D board replace the inline styles
head_end = page.index("</style>\n") + len("</style>\n")
page = ('<meta name="dash-one-writer">\n<link rel="stylesheet" href="theme.css">\n<script src="board3d.js"></script>\n'
        + page[head_end:])

# 2. header and the first page
start = page.index('<div class="mm">')
ov = page.index('id="overview"')
end = page.index("  </section>\n", ov) + len("  </section>\n")
page = page[:start] + (SRC / "head_overview.html").read_text() + page[end:]

# 3. kickers over the other cards, in the game's language
KICKERS = {
    "How fast each set pays for itself": "Payback", "Which building is the best buy": "Houses and hotels",
    "What is a property worth to the player it completes a set for?": "Trading floor",
    "Deal zones for every property": "Deal zones", "Vine Street in depth: who plays on, and who buys": "Vine Street",
    "Which tweaks to the simple bot win?": "Strategy tweaks", "Does going first matter?": "Seat order",
    "How long games last": "Game length", "How strong are the meta agents?": "Champions' table",
    "Why can a meta agent lose to simple bots?": "Diagnosis", "Deviating from the meta": "Off the meta",
    "The meta agent's settings": "The meta agent", "Hardening rounds": "Hardening",
}
for h2, kicker in KICKERS.items():
    swap(f"<h2>{h2}</h2>", f'<span class="mm-kicker">{kicker}</span>\n        <h2>{h2}</h2>')

# 4. the footer, inside the page wrapper
FOOT = """  <footer class="mm-foot">
    <span>Monopoly Meta is an independent, unofficial analysis made for learning and research. It isn't affiliated with or endorsed by Hasbro. MONOPOLY is a trademark of Hasbro; board names, prices and rents are used only to model the game. The board, cards, icons and colours on this page are the project's own designs.</span>
  </footer>
</div>

<script>
// ---------------------------------------------------------------- shared helpers"""
swap("</div>\n\n<script>\n// ---------------------------------------------------------------- shared helpers", FOOT)

# 5. helpers: the board colours and heat ramps come from the theme; a board mode parameter
swap("""  const BOARD = { brown: '#8b5a3c', light_blue: '#8fc9e8', pink: '#d0479b', orange: '#ec8a2c', red: '#d93a2b',
    yellow: '#f1d22a', green: '#2f9e4f', dark_blue: '#28509e', stations: '#5f5e5a', utilities: '#9a9993' };""",
     """  const BOARD = { brown: 'var(--mm-brown)', light_blue: 'var(--mm-light-blue)', pink: 'var(--mm-pink)', orange: 'var(--mm-orange)',
    red: 'var(--mm-red)', yellow: 'var(--mm-yellow)', green: 'var(--mm-green)', dark_blue: 'var(--mm-dark-blue)',
    stations: 'var(--mm-station)', utilities: 'var(--mm-utility)' };""")
swap("view: p.view ?? '3d', property: +(p.property ?? 19),", "view: p.view ?? '3d', bmode: p.bmode ?? 'towers', property: +(p.property ?? 19),")
swap("""  // the heat ramp used by both board views: panel colour to the first series colour
  const heat = (el, lo, hi) => {
    const a = rgb(el, 'var(--color-panel)', 'rgb(244, 244, 244)'), b = rgb(el, (dash.colors && dash.colors[0]) || '#2a78d6', 'rgb(42, 120, 214)');""",
     """  // the heat ramp of the flat board: board paper to a theme colour
  const heat = (el, lo, hi, to = 'var(--mm-orange)') => {
    const a = rgb(el, 'var(--mm-board-paper)', 'rgb(239, 230, 204)'), b = rgb(el, to, 'rgb(236, 138, 44)');""")
swap("""  const setColors = () => {
    (dash.colors || []).forEach((c, i) => root.style.setProperty(`--mm-c${i}`, c));
    root.style.setProperty('--mm-muted', 'var(--cds-chart-muted)');
  };
  setColors();""", """  const setColors = () => {};  // series colours come from the theme (theme.css)""")
swap("""    document.querySelectorAll('[data-rotate]').forEach((b) => { if (b.hidden !== (view !== '3d')) b.hidden = view !== '3d'; });""",
     """    document.querySelectorAll('[data-rotate]').forEach((b) => { if (b.hidden !== (view !== '3d')) b.hidden = view !== '3d'; });
    const { bmode, square } = mm.P();
    document.querySelectorAll('[data-bmode]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.bmode === bmode)));
    document.querySelectorAll('[data-bnote]').forEach((p) => { if (p.hidden !== (p.dataset.bnote !== bmode)) p.hidden = p.dataset.bnote !== bmode; });
    document.querySelectorAll('[data-roll]').forEach((b) => { if (b.hidden !== (bmode !== 'roll')) b.hidden = bmode !== 'roll'; });
    // the property card shows the parts that fit the chosen square, in its colour
    const sq = mm.ok('squares') ? mm.rows('squares').find((r) => +r.square === square) : null;
    const type = sq ? sq.type : 'street', own = ['street', 'station', 'utility'].includes(type);
    const showOnly = (sel, on) => document.querySelectorAll(sel).forEach((e) => { if (e.hidden === on) e.hidden = !on; });
    showOnly('.mm-deed-street', type === 'street'); showOnly('.mm-deed-station', type === 'station');
    showOnly('.mm-deed-utility', type === 'utility'); showOnly('.mm-deed-tax', type === 'tax');
    showOnly('.mm-deed-own', own); showOnly('.mm-deed-other', !own); showOnly('.mm-deed-zone', own);
    const band = sq && mm.BOARD[sq.group] ? mm.BOARD[sq.group] : 'var(--mm-board-ink)';
    document.querySelectorAll('.mm-deed-band').forEach((e) => {
      e.style.setProperty('--band', band);
      e.classList.toggle('mm-light', !!sq && ['light_blue', 'yellow'].includes(sq.group));
    });""")
swap("""  document.querySelectorAll('[data-view]').forEach((b) => b.addEventListener('click', () => dash.setParams({ view: b.dataset.view })));""",
     """  document.querySelectorAll('[data-view]').forEach((b) => b.addEventListener('click', () => dash.setParams({ view: b.dataset.view })));
  document.querySelectorAll('[data-bmode]').forEach((b) => b.addEventListener('click', () => dash.setParams({ bmode: b.dataset.bmode })));""")

# 6. the board script block is replaced whole
b0 = page.index("<script>\n// ---------------------------------------------------------------- board (3D and flat), square details, ranking")
b1 = page.index("</script>\n", b0) + len("</script>\n")
page = page[:b0] + (SRC / "board_script.html").read_text() + page[b1:]

# 7. chart colours that read the dashboard's series palette now read the theme
page = page.replace("(dash.colors && dash.colors[0]) || '#2a78d6'", "'var(--mm-cash)'")
page = page.replace("rgb(el, 'var(--cds-chart-status-critical)', 'rgb(208, 59, 59)')", "rgb(el, 'var(--mm-brick)', 'rgb(196, 69, 47)')")
page = re.sub(r"'var\(--color-panel\)'", "'var(--mm-card)'", page)
page = page.replace("rgb(el, 'var(--mm-card)', 'rgb(244, 244, 244)')", "rgb(el, 'var(--mm-card)', 'rgb(248, 242, 228)')")

OUT.write_text(page)
print(f"index.html: {len(page) / 1024:.0f} KB")
