"""One-off: turn a photo into data/portrait.json (per-cell brightness, -1 = background).

Usage: python scripts/make_portrait.py photo.jpg
Only the coarse brightness grid is committed, never the photo itself.
"""
import json, sys
from pathlib import Path
from PIL import Image, ImageFilter, ImageOps, ImageStat

import os
COLS, ROWS = int(os.environ.get("COLS", 190)), int(os.environ.get("ROWS", 104))  #         # grid size (cells are ~0.6 wide : 1 tall)
CELL_W, CELL_H = int(os.environ.get("CELL_W", 4)), int(os.environ.get("CELL_H", 7))  #       # sample resolution per cell
ROOT = Path(__file__).resolve().parent.parent

im = Image.open(sys.argv[1]).convert("RGB")
inset = int(os.environ.get("INSET", 0))  # trim any frame/border baked into the photo
if inset:
    im = im.crop((inset, inset, im.size[0] - inset, im.size[1] - inset))
W, H = im.size
# crop to head + shoulders, keep the grid's aspect
target = (COLS * 0.6) / ROWS
ch = int(H * 0.66)
cw = int(ch * target)
x0 = max(0, (W - cw) // 2)
im = im.crop((x0, 0, x0 + cw, ch)).resize((COLS * CELL_W, ROWS * CELL_H), Image.LANCZOS)

# background = maroon backdrop: red over green, blue at/above green, not bright
px = im.load()
bgmask = Image.new("L", im.size, 0)
bm = bgmask.load()
for y in range(im.size[1]):
    for x in range(im.size[0]):
        r, g, b = px[x, y]
        if r - g >= 12 and b >= g + 1 and r < 120:
            bm[x, y] = 255
# keep only background connected to the image border, then smooth it
bgmask = bgmask.filter(ImageFilter.MedianFilter(7))
from PIL import ImageDraw
seedmask = bgmask.copy()
for sx, sy in [(1, 1), (im.size[0] - 2, 1), (1, im.size[1] // 2), (im.size[0] - 2, im.size[1] // 2)]:
    if seedmask.getpixel((sx, sy)) == 255:
        ImageDraw.floodfill(seedmask, (sx, sy), 128)
bg = seedmask.point(lambda v: 255 if v == 128 else 0).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))

# subject luminance with local contrast boost
gray = ImageOps.grayscale(im)
subject_only = Image.composite(Image.new("L", im.size, 128), gray, bg)
eq = ImageOps.autocontrast(subject_only, cutoff=1)
eq = eq.point(lambda v: int(255 * (v / 255) ** 1.5))  # pull skin highlights down so features read
sharp = eq.filter(ImageFilter.UnsharpMask(radius=4, percent=180, threshold=2))

grid = []
for ry in range(ROWS):
    row = []
    for cx in range(COLS):
        box = (cx * CELL_W, ry * CELL_H, cx * CELL_W + CELL_W, ry * CELL_H + CELL_H)
        if ImageStat.Stat(bg.crop(box)).mean[0] > 140:
            row.append(-1)
        else:
            row.append(round(ImageStat.Stat(sharp.crop(box)).mean[0] / 255 * 99))
    grid.append(row)
(ROOT / "data" / os.environ.get("OUT", "portrait.json")).write_text(json.dumps({"cols": COLS, "rows": ROWS, "grid": grid}, separators=(",", ":")))
# debug preview
dbg = Image.new("L", (COLS, ROWS))
dbg.putdata([255 if v < 0 else int(v * 2.55) for r in grid for v in r])
dbg.resize((COLS * 4, ROWS * 6), Image.NEAREST).save(sys.argv[2] if len(sys.argv) > 2 else "/dev/null", "PNG")
print("ok", COLS, ROWS)
