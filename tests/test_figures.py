"""The charts' title-deed card: the board's mint around a cream card, a band in the chart's colour, the fonts."""
import importlib
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_title_deed_card():
    mf = importlib.import_module("make_figures")
    chart = Image.new("RGB", (900, 500), mf.CARD)
    img = mf.card(chart, mf.GROUP["orange"], "Vine Street", "What is Vine Street worth, and to whom? " * 3,
                  "A subtitle\nover two lines")
    colour = lambda xy: "#%02x%02x%02x" % img.getpixel(xy)  # noqa: E731
    assert colour((1, 1)) == mf.BOARD  # the board around the card
    px = mf.DPI / 72
    corner = round(9 * px) + max(2, round(1.1 * px)) + round(4 * px)  # edge + border + inset: the band's corner
    assert colour((corner + 6, corner + 6)) == mf.GROUP["orange"]
    assert colour((corner, img.height - corner)) == mf.CARD
    assert img.width >= chart.width and img.height > chart.height + 200  # a long title wraps onto more lines
    for face in ("Oswald-500.ttf", "Oswald-700.ttf"):
        assert mf._font(10, face).getname()[0].startswith("Oswald")
