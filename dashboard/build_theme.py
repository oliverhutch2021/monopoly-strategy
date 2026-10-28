"""Build dashboard/theme.css from theme.src.css, embedding the Oswald font (SIL Open Font Licence 1.1).

    python dashboard/build_theme.py <dir with oswald-latin-500-normal.woff2 and oswald-latin-700-normal.woff2>

The dashboard can't load web fonts, so the two weights it uses are embedded as data URLs.
Oswald: Copyright 2016 The Oswald Project Authors (https://github.com/googlefonts/OswaldFont).
"""
import base64
import sys
from pathlib import Path

HERE = Path(__file__).parent
fonts = Path(sys.argv[1])
css = (HERE / "theme.src.css").read_text()
for w in (500, 700):
    data = base64.b64encode((fonts / f"oswald-latin-{w}-normal.woff2").read_bytes()).decode()
    css = css.replace(f"__OSWALD_{w}__", data)
(HERE / "theme.css").write_text(css)
print(f"theme.css: {len(css) / 1024:.0f} KB")
