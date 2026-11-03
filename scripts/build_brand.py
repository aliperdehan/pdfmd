#!/usr/bin/env python3
"""Build the pdfmd logo files from one source of geometry.

    python3 scripts/build_brand.py            # SVGs into docs/brand/
    python3 scripts/build_brand.py --render   # also the macOS icon and PNGs into gui/Resources/

The mark is three tilted sheets on a tile; the front sheet carries a `#`
heading, a bar and text lines.  Below 48 px the front sheet shows the `#`
alone (`SMALL_BELOW`).  The wordmark pairs an italic `pdf` (STIX Two, the
default math font) with a bold monospace `md` (JetBrains Mono, the default
code font): the same pairing as `$\\mathit{pdf}$`md``.

All lettering is outlined from the fonts (both under the SIL Open Font
License), so the SVGs do not depend on any installed font.  Font files are
looked up in the usual folders; set PDFMD_BRAND_FONTS to a folder to add one.

Needs fontTools; `--render` also needs rsvg-convert and, for the .icns,
macOS's iconutil.  Nothing here is imported by pdfmd itself.
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "brand"
RES = ROOT / "gui" / "Resources"

# colours: the pdfmd Edit palette (light values)
NAVY, TEAL, ROSE, CREAM = "#22304A", "#3F7F86", "#A05A72", "#F4F1EA"
BLUE, GREY = "#3B5F99", "#C4BFB3"
BLUE_ON_DARK = "#8AA9D6"

# sheet geometry on the 256 x 256 tile (the "V2" proportions)
SX, SY, SW, SH, SR = 68, 38, 120, 168, 11
TILT = (-16, -6, 6)           # back, middle, front, about the tile's centre
TILE_R = 58
MONO_TILT = (-22, -9, 6)      # the one-colour mark is fanned wider
MONO_GAP = 7

SMALL_BELOW = 48              # px: below this the front sheet shows the # only
# macOS draws the tile at 824 of 1024 px with a margin round it
ICON_CANVAS, ICON_TILE = 1024, 824

FONT_DIRS = [Path.home() / "Library" / "Fonts", Path("/System/Library/Fonts/Supplemental"),
             Path("/Library/Fonts"), Path.home() / ".fonts", Path("/usr/share/fonts/truetype"),
             Path("/usr/share/fonts")]
if os.environ.get("PDFMD_BRAND_FONTS"):
    FONT_DIRS.insert(0, Path(os.environ["PDFMD_BRAND_FONTS"]))
_fonts: dict[str, TTFont] = {}


def font(name: str) -> TTFont:
    if name not in _fonts:
        for d in FONT_DIRS:
            hit = next(d.rglob(glob.escape(name)), None) if d.is_dir() else None
            if hit:
                _fonts[name] = TTFont(str(hit))
                break
        else:
            sys.exit(f"font file {name} not found (set PDFMD_BRAND_FONTS to its folder)")
    return _fonts[name]


ITALIC = "STIXTwoText-Italic.ttf"
MONO_BOLD = "JetBrainsMono-Bold.ttf"
MONO_REG = "JetBrainsMono[wght].ttf"      # default instance = Regular


def glyph_path(fname: str, ch: str, size: float, x: float, y: float):
    """(svg path data, advance, bbox) of one character set at baseline (x, y)."""
    f = font(fname)
    gs = f.getGlyphSet()
    name = f.getBestCmap()[ord(ch)]
    upem = f["head"].unitsPerEm
    k = size / upem
    pen = SVGPathPen(gs)
    gs[name].draw(TransformPen(pen, (k, 0, 0, -k, x, y)))
    bp = BoundsPen(gs)
    gs[name].draw(bp)
    b = bp.bounds
    box = None if b is None else (x + b[0] * k, y - b[3] * k, x + b[2] * k, y - b[1] * k)
    return pen.getCommands(), gs[name].width * k, box


def text_path(fname: str, s: str, size: float, x: float, y: float, track: float = 0.0):
    """One path for a string, outlined; returns (d, end x)."""
    ds = []
    for ch in s:
        d, adv, _ = glyph_path(fname, ch, size, x, y)
        ds.append(d)
        x += adv + track
    return " ".join(ds), x - track


def hash_path(size: float, cx: float, cy: float):
    """The # of the mark, outlined and centred on (cx, cy)."""
    _, _, b = glyph_path(MONO_BOLD, "#", size, 0, 0)
    d, _, _ = glyph_path(MONO_BOLD, "#", size, cx - (b[0] + b[2]) / 2, cy - (b[1] + b[3]) / 2)
    return d


def sheet(fill: str, rot: float, inner: str = "") -> str:
    return (f'<g transform="rotate({rot} 128 128)"><rect x="{SX}" y="{SY}" width="{SW}" height="{SH}" '
            f'rx="{SR}" fill="{fill}"/>{inner}</g>')


def front_full() -> str:
    """# + heading bar + three text lines (scaled from the 104 x 146 original)."""
    s = SW / 104
    X = lambda v: SX + (v - 76) * s
    Y = lambda v: SY + (v - 50) * s
    h, _, _ = glyph_path(MONO_BOLD, "#", 52 * s, X(90), Y(116))
    bits = [f'<path d="{h}" fill="{BLUE}"/>',
            f'<rect x="{X(128):.2f}" y="{Y(94):.2f}" width="{38*s:.2f}" height="{8*s:.2f}" rx="{4*s:.2f}" fill="{BLUE}"/>']
    for yy, ww in ((134, 76), (150, 76), (166, 46)):
        bits.append(f'<rect x="{X(90):.2f}" y="{Y(yy):.2f}" width="{ww*s:.2f}" height="{6*s:.2f}" '
                    f'rx="{3*s:.2f}" fill="{GREY}"/>')
    return "".join(bits)


def front_small() -> str:
    return f'<path d="{hash_path(112, SX + SW / 2, SY + SH / 2)}" fill="{BLUE}"/>'


def tile_body(small: bool) -> str:
    return (f'<rect width="256" height="256" rx="{TILE_R}" fill="{NAVY}"/>' + sheet(TEAL, TILT[0]) + sheet(ROSE, TILT[1])
            + sheet(CREAM, TILT[2], front_small() if small else front_full()))


def svg(body: str, w: float, h: float, vb: str | None = None, title: str = "") -> str:
    t = f"<title>{title}</title>" if title else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb or f"0 0 {w} {h}"}" width="{w:g}" height="{h:g}">'
            f"{t}{body}</svg>\n")


def mono_body(ink: str, tile: str = "") -> str:
    """Three sheets in one colour with gaps between them and the # cut out."""
    def ms(rot, gap, inner=""):
        g = (f'<rect x="{SX}" y="{SY}" width="{SW}" height="{SH}" rx="{SR}" fill="#000" stroke="#000" '
             f'stroke-width="{gap}"/>') if gap else ""
        return (f'<g transform="rotate({rot} 128 128)">{g}<rect x="{SX}" y="{SY}" width="{SW}" height="{SH}" '
                f'rx="{SR}" fill="#fff"/>{inner}</g>')
    cut = f'<path d="{hash_path(112, SX + SW / 2, SY + SH / 2)}" fill="#000"/>'
    mask = ('<mask id="m" maskUnits="userSpaceOnUse" x="0" y="0" width="256" height="256">'
            '<rect width="256" height="256" fill="#000"/>' + ms(MONO_TILT[0], 0) + ms(MONO_TILT[1], MONO_GAP)
            + ms(MONO_TILT[2], MONO_GAP, cut) + "</mask>")
    return f'{tile}<defs>{mask}</defs><rect width="256" height="256" fill="{ink}" mask="url(#m)"/>'


def wordmark(ink: str, md: str) -> str:
    """The mark (128 px) and `pdf` + `md` beside it; returns a complete SVG."""
    d1, x = text_path(ITALIC, "pdf", 84, 150, 88)
    d2, x2 = text_path(MONO_BOLD, "md", 76, x + 4, 88, track=-3)
    icon = f'<g transform="scale(.5)">{tile_body(False)}</g>'
    return svg(icon + f'<path d="{d1}" fill="{ink}"/><path d="{d2}" fill="{md}"/>', x2 + 10, 128,
               title="pdfmd")


def social() -> str:
    """1280 x 640 social preview: the mark, the wordmark (large) and one line."""
    d1, x = text_path(ITALIC, "pdf", 190, 480, 360)
    d2, x2 = text_path(MONO_BOLD, "md", 172, x + 8, 360, track=-6)
    tag, _ = text_path(MONO_REG, "One command from Markdown to a good-looking PDF.", 24, 484, 436)
    body = (f'<rect width="1280" height="640" fill="{NAVY}"/><g transform="translate(110 150) scale(1.4)">'
            f'{tile_body(False)}</g>'
            f'<path d="{d1}" fill="{CREAM}"/><path d="{d2}" fill="{BLUE_ON_DARK}"/>'
            f'<path d="{tag}" fill="#AEB6C6"/>')
    return svg(body, 1280, 640, title="pdfmd")


def icon_canvas(small: bool) -> str:
    """The 1024 px macOS icon: the tile at 824 px, centred, transparent margin."""
    k = ICON_TILE / 256
    m = (ICON_CANVAS - ICON_TILE) / 2
    return svg(f'<g transform="translate({m} {m}) scale({k})">{tile_body(small)}</g>', 1024, 1024)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print("wrote", path.relative_to(ROOT))


def build_svgs() -> None:
    write(OUT / "mark.svg", svg(tile_body(False), 256, 256, title="pdfmd"))
    write(OUT / "mark-small.svg", svg(tile_body(True), 256, 256, title="pdfmd"))
    write(OUT / "mark-mono.svg", svg(mono_body(NAVY), 256, 256, title="pdfmd"))
    write(OUT / "mark-mono-light.svg", svg(mono_body(CREAM), 256, 256, title="pdfmd"))
    write(OUT / "mark-menubar.svg", svg(mono_body(NAVY), 184, 204, vb="36 26 184 204", title="pdfmd"))
    write(OUT / "wordmark.svg", wordmark(NAVY, BLUE))
    write(OUT / "wordmark-dark.svg", wordmark(CREAM, BLUE_ON_DARK))
    write(OUT / "social-preview.svg", social())


def rsvg(src: Path, dst: Path, px: int) -> None:
    subprocess.run(["rsvg-convert", "-w", str(px), "-h", str(px), str(src), "-o", str(dst)], check=True)


def render() -> None:
    if not shutil.which("rsvg-convert"):
        sys.exit("--render needs rsvg-convert (brew install librsvg)")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        full, small = td / "full.svg", td / "small.svg"
        full.write_text(icon_canvas(False)), small.write_text(icon_canvas(True))
        iconset = td / "pdfmd.iconset"
        iconset.mkdir()
        for pt in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                px = pt * scale
                rsvg(small if px < SMALL_BELOW else full, iconset / f"icon_{pt}x{pt}{'@2x' if scale == 2 else ''}.png", px)
        RES.mkdir(parents=True, exist_ok=True)
        if shutil.which("iconutil"):
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(RES / "pdfmd.icns")], check=True)
            print("wrote", (RES / "pdfmd.icns").relative_to(ROOT))
        else:
            print("iconutil not found: .icns skipped")
        # menu-bar template image: black on transparent, 18 pt high (and 36 px for retina), cropped tight
        for px, name in ((18, "pdfmd-menubarTemplate.png"), (36, "pdfmd-menubarTemplate@2x.png")):
            subprocess.run(["rsvg-convert", "-h", str(px), str(OUT / "mark-menubar.svg"), "-o", str(RES / name)], check=True)
            print("wrote", (RES / name).relative_to(ROOT))
        subprocess.run(["rsvg-convert", "-w", "1280", "-h", "640", str(OUT / "social-preview.svg"),
                        "-o", str(OUT / "social-preview.png")], check=True)
        print("wrote", (OUT / "social-preview.png").relative_to(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--render", action="store_true", help="also the .icns, the menu-bar PNGs and the social PNG")
    a = ap.parse_args()
    build_svgs()
    if a.render:
        render()


if __name__ == "__main__":
    main()
