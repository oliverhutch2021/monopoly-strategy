"""Cut the playing pieces out of Oliver's artwork sheet for the live viewer.

    python scripts/cut_pieces.py

Reads watch/pieces/sheet.png (eight pieces on a transparent background, in two rows of four) and
writes one PNG per piece, at half size, plus watch/pieces/pieces.json with each piece's name, size
and the colour of its glow. Pieces are found as connected regions of the sheet and taken in reading
order; faint specks of background are dropped and each piece's body is made fully opaque.
"""
import colorsys
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parents[1] / "watch" / "pieces"
NAMES = ["Top hat", "Racing car", "Scottie dog", "Boot", "Thimble", "Iron", "Battleship", "Wheelbarrow"]
SCALE = 0.5


def main() -> None:
    a = np.array(Image.open(HERE / "sheet.png").convert("RGBA"))
    lab, n = ndimage.label(a[..., 3] > 24, structure=np.ones((3, 3)))
    sizes = ndimage.sum(np.ones(lab.shape), lab, range(1, n + 1))
    comps = [i + 1 for i, s in enumerate(sizes) if s > 2000]
    if len(comps) != len(NAMES):
        raise SystemExit(f"expected {len(NAMES)} pieces on the sheet, found {len(comps)}")
    tops = {c: np.where(lab == c) for c in comps}
    mid_row = a.shape[0] / 2
    comps.sort(key=lambda c: (tops[c][0].mean() > mid_row, tops[c][1].min()))  # reading order
    meta = []
    for comp, name in zip(comps, NAMES):
        slug = name.lower().replace(" ", "-")
        keep = ndimage.binary_dilation(lab == comp, iterations=8)  # the piece and the soft tail of its glow
        ys, xs = np.where(keep)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        piece = a[y0:y1, x0:x1].copy()
        alpha = piece[..., 3].astype(int)
        alpha[~keep[y0:y1, x0:x1]] = 0
        alpha[alpha >= 200] = 255
        alpha[alpha < 6] = 0
        piece[..., 3] = alpha
        piece[alpha == 0, :3] = 0
        im = Image.fromarray(piece, "RGBA")
        size = (round(im.size[0] * SCALE), round(im.size[1] * SCALE))
        im = im.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")  # premultiplied: no dark fringes
        im.save(HERE / f"{slug}.png", optimize=True)
        rgb = piece[..., :3].reshape(-1, 3)[::5] / 255
        hsv = np.array([colorsys.rgb_to_hsv(*c) for c in rgb])
        sel = (hsv[:, 1] > 0.6) & (hsv[:, 2] > 0.5) & (alpha.reshape(-1)[::5] > 120)
        glow = np.median(rgb[sel], axis=0) if sel.any() else np.array([.5, .5, .5])
        meta.append({"slug": slug, "name": name, "w": im.size[0], "h": im.size[1],
                     "glow": "#" + "".join(f"{round(v * 255):02x}" for v in glow)})
        print(f"{name}: {im.size[0]}x{im.size[1]}, glow {meta[-1]['glow']}")
    (HERE / "pieces.json").write_text(json.dumps(meta, indent=1) + "\n")


if __name__ == "__main__":
    main()
