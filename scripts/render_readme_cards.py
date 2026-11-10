"""Render the animated SVG cards for the profile README.

Reads data/contributions.json (written by fetch_data.py) and writes cards/*.svg.
STATIC=1 renders every card at its final frame (handy for screenshots).
"""
import base64, datetime as dt, io, json, math, os, re, string
from collections import OrderedDict
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "fonts"
OUT = Path(os.environ.get("CARDS_OUT", ROOT / "cards"))
STATIC = os.environ.get("STATIC") == "1"
GRAPH_START_MONTH = 2  # contribution graph starts on Feb 1 of the current year

# ── palette ───────────────────────────────────────────────────────────────
PAPER = "#F4F0E6"
PAPER2 = "#EBE5D6"
INK = "#16140F"
MUTED = "#6E685C"
BLUE = "#2B59FF"
RED = "#EF4136"
YELLOW = "#F6B62B"
GRAPH = ["#C7D3FF", "#8DA6FF", "#557BFF", "#2B59FF"]
EMPTY_OP = ".07"
BORDER_OP = ".1"

THEMES = {
    "light": dict(PAPER="#F4F0E6", PAPER2="#EBE5D6", INK="#16140F", MUTED="#6E685C",
                  BLUE="#2B59FF", RED="#EF4136", YELLOW="#F6B62B",
                  GRAPH=["#C7D3FF", "#8DA6FF", "#557BFF", "#2B59FF"], EMPTY_OP=".07", BORDER_OP=".1",
                  TILES={"blue": ("#2B59FF", "#F7F4EC", "#F7F4EC"), "red": ("#EF4136", "#F7F4EC", "#F7F4EC"),
                         "yellow": ("#F6B62B", "#16140F", "#16140F")}, SHINE_OP=".28", TILE_BORDER=False, DARK=False),
    # GitHub-dark friendly: card sits one step above #0d1117, warm off-white ink, brighter accents
    "dark": dict(PAPER="#12171F", PAPER2="#1B222C", INK="#EDE8DC", MUTED="#8D96A3",
                 BLUE="#5B82FF", RED="#F25A4F", YELLOW="#F7C04A",
                 GRAPH=["#1D2C5E", "#2B48A8", "#4167F0", "#7B9BFF"], EMPTY_OP=".07", BORDER_OP=".12",
                 # dimmed: the light-mode colours, deepened so they don't glare on #0d1117
                 TILES={"blue": ("#2341B0", "#D9E0F7", "#FFFFFF"), "red": ("#A8352C", "#F2DAD7", "#FFFFFF"),
                        "yellow": ("#B88A26", "#1A160D", "#1A160D")}, SHINE_OP=".12", TILE_BORDER=False, DARK=True),
}

SERIF, SANS, SANS_MED, MONO = "Instrument Serif", "Geist", "GeistMed", "Geist Mono"
GLYPHS = string.printable + "→↗↑●·—’•"


# ── fonts: subset + embed as base64 woff2 ─────────────────────────────────
_face_cache = {}


def font_face(family):
    if family in _face_cache:
        return _face_cache[family]
    src, wght = {
        SERIF: ("InstrumentSerif-Regular.ttf", None),
        SANS: ("Geist.ttf", 400),
        SANS_MED: ("Geist.ttf", 560),
        MONO: ("GeistMono.ttf", 450),
    }[family]
    f = TTFont(FONTS / src)
    if wght and "fvar" in f:
        f = instancer.instantiateVariableFont(f, {"wght": wght})
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga"]
    opts.name_IDs = ["*"]
    sub = subset.Subsetter(opts)
    sub.populate(text=GLYPHS)
    sub.subset(f)
    buf = io.BytesIO()
    f.flavor = "woff2"
    f.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    css = f"@font-face{{font-family:'{family}';src:url(data:font/woff2;base64,{b64}) format('woff2')}}"
    _face_cache[family] = css
    return css


BASE_CSS = f"""
.serif{{font-family:'{SERIF}',Georgia,serif}}
.sans{{font-family:'{SANS}',system-ui,sans-serif}}
.med{{font-family:'{SANS_MED}','{SANS}',system-ui,sans-serif}}
.mono{{font-family:'{MONO}',ui-monospace,monospace}}
@keyframes rise{{from{{opacity:0;transform:translateY(34px)}}to{{opacity:1;transform:none}}}}
@keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes pop{{0%{{opacity:0;transform:scale(0)}}70%{{opacity:1;transform:scale(1.25)}}100%{{opacity:1;transform:scale(1)}}}}
@keyframes grow{{from{{transform:scaleY(0)}}to{{transform:scaleY(1)}}}}
@keyframes pulse{{0%{{opacity:.55;transform:scale(1)}}100%{{opacity:0;transform:scale(3.2)}}}}
@keyframes nudge{{0%,100%{{transform:translate(0,0)}}50%{{transform:translate(4px,-4px)}}}}
.rise{{animation:rise .9s cubic-bezier(.2,.8,.2,1) both}}
.fade{{animation:fade .6s ease-out both}}
.pop{{transform-box:fill-box;transform-origin:center;animation:pop .45s cubic-bezier(.3,1.4,.5,1) both}}
.grow{{transform-box:fill-box;transform-origin:bottom;animation:grow .9s cubic-bezier(.2,.8,.2,1) both}}
.pulse{{transform-box:fill-box;transform-origin:center;animation:pulse 2s ease-out infinite}}
.nudge{{animation:nudge 1.6s ease-in-out infinite}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
"""


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg(w, h, body, fonts, css="", title="", bg=None, radius=18, border=True):
    bg = bg or PAPER
    faces = "".join(font_face(f) for f in fonts)
    static = "*{animation:none!important}" if STATIC else ""
    stroke = f' stroke="{INK}" stroke-opacity="{BORDER_OP}"' if border else ""
    doc = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">
<title>{esc(title)}</title>
<style>{faces}{BASE_CSS}{css}{static}</style>
<defs><clipPath id="card"><rect width="{w}" height="{h}" rx="{radius}"/></clipPath></defs>
<g clip-path="url(#card)">
<rect width="{w}" height="{h}" rx="{radius}" fill="{bg}"/>
{body}
</g>
<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="{radius}" fill="none"{stroke}/>
</svg>"""
    if STATIC:
        doc = re.sub(r"<(set|animate|animateTransform)\b[^>]*/>", "", doc)
    return doc


def d(sec):
    return f"animation-delay:{sec:.3f}s"


def text_w(s, size, kind="sans"):
    """Rough advance width for layout (monospace exact, proportional approximate)."""
    if kind == "mono":
        return len(s) * size * 0.6
    return sum(size * (0.3 if c in " .,'il|" else 0.62 if c.isupper() else 0.53) for c in s)


def wrap(s, size, max_w):
    lines, cur = [], ""
    for word in s.split():
        trial = (cur + " " + word).strip()
        if text_w(trial, size) > max_w and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


# ── data ──────────────────────────────────────────────────────────────────
DATA = json.loads((ROOT / "data" / "contributions.json").read_text())
DAYS = [(dt.date.fromisoformat(x["date"]), x["count"]) for x in DATA["days"]]
TOTAL = sum(c for _, c in DAYS)


def streaks():
    longest = cur = 0
    for _, c in DAYS:
        cur = cur + 1 if c else 0
        longest = max(longest, cur)
    current = 0
    days = DAYS[:]
    if days and days[-1][1] == 0:  # today not counted yet doesn't break the streak
        days = days[:-1]
    for _, c in reversed(days):
        if not c:
            break
        current += 1
    return current, longest


# ── 1. hero ───────────────────────────────────────────────────────────────
def ascii_monogram(cols, rows, text="RG"):
    W, H = cols * 10, rows * 16
    img = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(img)
    size = int(H * 1.05)
    font = ImageFont.truetype(str(FONTS / "InstrumentSerif-Regular.ttf"), size)
    while True:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        if r - l <= W * 0.9 and b - t <= H * 0.8:
            break
        size -= 4
        font = ImageFont.truetype(str(FONTS / "InstrumentSerif-Regular.ttf"), size)
    draw.text(((W - (r - l)) / 2 - l, (H - (b - t)) / 2 - t), text, font=font, fill=255)
    img = img.filter(ImageFilter.MaxFilter(11)).filter(ImageFilter.GaussianBlur(2.5))
    ramp = " .:-=+*#%@"
    grid = []
    for ry in range(rows):
        row = []
        for cx in range(cols):
            box = img.crop((cx * 10, ry * 16, cx * 10 + 10, ry * 16 + 16))
            v = ImageStat.Stat(box).mean[0] / 255
            shade = 0.72 + 0.28 * (1 - (cx / cols + ry / rows) / 2)  # light from top-left
            v *= shade
            if v < 0.06:
                row.append(("b", "." if (cx + ry * 2) % 4 == 0 else " "))
            else:
                row.append(("i", ramp[min(len(ramp) - 1, max(1, int(v * len(ramp))))]))
        grid.append(row)
    return grid


def ascii_portrait(data):
    """Brightness grid -> characters, tones equalised over the subject so the face keeps contrast.
    Light theme: dark = dense ink. Dark theme: bright = dense."""
    ramp = " .:-=+*#%@"
    vals = sorted(v for row in data["grid"] for v in row if v >= 0)
    rank = {}
    for i, v in enumerate(vals):
        rank.setdefault(v, []).append(i)
    pct = {v: (sum(ix) / len(ix)) / max(1, len(vals) - 1) for v, ix in rank.items()}
    grid = [row[:] for row in data["grid"]]
    # mirror the right-hand ending on the left: find the head's centre column, drop everything further
    # left than the right edge is on the right, and dither-fade the last few columns so it tapers off
    ncol = len(grid[0])
    head = [c for row in grid[: len(grid) // 3] for c, v in enumerate(row) if v >= 0]
    centre = sum(head) / len(head)
    left = max(0, int(2 * centre - (ncol - 1)))
    fade = 16
    for r, row in enumerate(grid):
        for c in range(min(ncol, left + fade)):
            keep = (c - left) / fade
            if c < left or ((r * 7 + c * 13) % 17) / 17 > keep:
                row[c] = -1
    rows = []
    for row in grid:
        out = []
        for v in row:
            if v < 0:
                out.append(("b", " "))
                continue
            t = 0.55 * pct[v] + 0.45 * v / 99  # half equalised, half raw: keeps contrast without flattening the face
            dens = 0.06 + 0.94 * t if DARK else 0.05 + 0.92 * (1 - t) ** 0.55
            # tone carried twice: glyph density and opacity (o3..o10) -> near-continuous shading
            out.append((f"o{max(3, round(dens * 10))}", ramp[min(len(ramp) - 1, int(dens * len(ramp)))]))
        rows.append(out)
    return rows


def hero():
    W, H = 880, 360
    parts = []
    # status line with pulsing dot
    parts.append(f'<g class="fade" style="{d(0.1)}">'
                 f'<circle cx="50" cy="62" r="4.5" fill="{BLUE}" class="pulse"/>'
                 f'<circle cx="50" cy="62" r="4.5" fill="{BLUE}"/>'
                 f'<text x="64" y="66.5" class="mono" font-size="12" letter-spacing="1.6" fill="{MUTED}">'
                 f'E&amp;I ENGINEERING · SGSITS INDORE · CLASS OF 2027</text></g>')
    # name, rising line by line, shine on the surname
    parts.append(f"""<defs><linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="260" y2="0" gradientTransform="translate(-300 0)">
<stop offset="0" stop-color="{INK}"/><stop offset=".42" stop-color="{INK}"/><stop offset=".5" stop-color="{BLUE}"/>
<stop offset=".58" stop-color="{INK}"/><stop offset="1" stop-color="{INK}"/>
<animateTransform attributeName="gradientTransform" type="translate" values="-300 0;-300 0;520 0" keyTimes="0;.6;1" dur="5s" begin="1.4s" repeatCount="indefinite"/>
</linearGradient></defs>""")
    parts.append(f'<text x="40" y="172" class="serif rise" font-size="112" letter-spacing="-2" fill="{INK}" style="{d(0.2)}">Rajvir</text>')
    parts.append(f'<text x="40" y="264" class="serif rise" font-size="112" letter-spacing="-2" style="{d(0.42)}">'
                 f'<tspan fill="url(#shine)">Gautam</tspan><tspan fill="{BLUE}">.</tspan></text>')
    parts.append(f'<text x="44" y="312" class="sans rise" font-size="17" fill="{MUTED}" style="{d(0.7)}">'
                 f'Final-year engineer building full-stack web &amp; Android apps.</text>')
    # ASCII portrait (data/portrait.json) or RG monogram fallback, printed row by row
    portrait = ROOT / "data" / os.environ.get("PORTRAIT", "portrait.json")
    if portrait.exists():
        grid = ascii_portrait(json.loads(portrait.read_text()))
        fs = round(343 / len(grid), 2)  # same on-card height whatever the grid resolution
        x0, y0 = W + 1 - len(grid[0]) * fs * 0.6, H - len(grid) * fs + 3  # bleed off right + bottom edges
        step = 0.018
    else:
        grid, fs, x0, y0 = ascii_monogram(70, 44), 6.2, 578, 46
        step = 0.03
    rows_svg = []
    for ry, row in enumerate(grid):
        runs, prev = [], None
        for kind, ch in row:
            if kind != prev:
                runs.append([kind, ""])
                prev = kind
            runs[-1][1] += ch
        spans = "".join(f'<tspan class="{k}">{esc(s)}</tspan>' for k, s in runs)
        rows_svg.append(f'<text x="{x0}" y="{y0 + ry * fs:.1f}" class="fade" style="{d(0.5 + ry * step)}" xml:space="preserve">{spans}</text>')
    parts.append(f'<g class="mono" font-size="{fs}">{"".join(rows_svg)}</g>')
    css = f".b{{fill:{MUTED};fill-opacity:.35}} .i{{fill:{INK}}}" + "".join(
        f" .o{n}{{fill:{INK};fill-opacity:{n / 10}}}" for n in range(3, 11))
    return svg(W, H, "\n".join(parts), [SERIF, SANS, MONO], css, "Rajvir Gautam — final-year engineer at SGSITS Indore")


# ── 2. contribution graph ─────────────────────────────────────────────────
def level(c, qs):
    if c == 0:
        return 0
    return 1 + sum(c > q for q in qs)


def graph():
    """Contribution graph from GRAPH_START_MONTH of the current year → today."""
    year = DAYS[-1][0].year
    start = dt.date(year, GRAPH_START_MONTH, 1)
    days = [(day, c) for day, c in DAYS if day >= start]
    total = sum(c for _, c in days)
    W, x0, x1, y0 = 880, 44, 836, 92
    offset = (days[0][0].weekday() + 1) % 7  # Sunday-first rows
    cols = math.ceil((len(days) + offset) / 7)
    step = min(22.0, (x1 - x0) / cols)
    cell = round(step * 0.8, 1)
    H = int(y0 + 7 * step + 52)
    nz = sorted(c for _, c in days if c)
    qs = [nz[int(len(nz) * p)] for p in (0.25, 0.5, 0.75)] if nz else [1, 2, 3]
    colors = [INK] + GRAPH
    parts = [f'<text x="40" y="54" class="serif rise" font-size="30" fill="{INK}">{total:,} contributions'
             f'<tspan fill="{MUTED}"> since {start:%B}</tspan></text>',
             f'<text x="836" y="52" text-anchor="end" class="mono fade" font-size="11" letter-spacing="1.4" fill="{MUTED}">'
             + f'{days[0][0]:%b %Y} → {days[-1][0]:%b %Y}'.upper() + "</text>"]
    cells = []
    for i, (day, c) in enumerate(days):
        col, row = divmod(i + offset, 7)
        x, y = x0 + col * step, y0 + row * step
        lv = level(c, qs)
        op = f' fill-opacity="{EMPTY_OP}"' if lv == 0 else ""
        cells.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell}" height="{cell}" rx="3.5" fill="{colors[lv]}"{op} '
                     f'class="pop" style="{d(0.3 + col * 0.025 + row * 0.012)}"><title>{c} on {day:%b %d}</title></rect>')
        if day.day == 1:
            parts.append(f'<text x="{x0 + (col + (1 if row else 0)) * step:.1f}" y="{y0 - 12}" class="mono fade" font-size="10.5" '
                         f'fill="{MUTED}" style="{d(0.3)}">{day:%b}</text>')
    parts.extend(cells)
    lx = 836 - 5 * 15 - 36
    parts.append(f'<text x="{lx - 8}" y="{H - 18}" text-anchor="end" class="mono" font-size="10" fill="{MUTED}">less</text>')
    for k, col in enumerate(colors):
        op = f' fill-opacity="{EMPTY_OP}"' if k == 0 else ""
        parts.append(f'<rect x="{lx + k * 15}" y="{H - 28}" width="11" height="11" rx="3" fill="{col}"{op}/>')
    parts.append(f'<text x="{lx + 5 * 15 + 4}" y="{H - 18}" class="mono" font-size="10" fill="{MUTED}">more</text>')
    return svg(W, H, "\n".join(parts), [SERIF, MONO], title=f"{total} contributions since {start:%B %Y}")


# ── 3. monthly activity ───────────────────────────────────────────────────
def activity():
    W, H = 880, 320
    months = OrderedDict()
    for day, c in DAYS:
        months.setdefault((day.year, day.month), 0)
        months[(day.year, day.month)] += c
    months = list(months.items())[-12:]
    best_i = max(range(len(months)), key=lambda i: months[i][1])
    mx = max(v for _, v in months) or 1
    cur, longest = streaks()
    active = sum(1 for _, c in DAYS if c)
    busy_day, busy_c = max(DAYS, key=lambda x: x[1])

    parts = [f'<text x="40" y="58" class="serif rise" font-size="30" fill="{INK}">Monthly activity</text>']
    stats = [(f"{cur}", "day current streak"), (f"{longest}", "day longest streak"),
             (f"{active}", "active days this year"), (f"{busy_c}", f"on {busy_day:%b %d}, busiest day")]
    for k, (num, label) in enumerate(stats):
        y = 118 + k * 52
        parts.append(f'<g class="rise" style="{d(0.25 + k * 0.1)}">'
                     f'<text x="40" y="{y}" class="serif" font-size="34" fill="{INK}">{num}</text>'
                     f'<text x="112" y="{y - 2}" class="sans" font-size="13.5" fill="{MUTED}">{esc(label)}</text></g>')
    parts.append(f'<line x1="292" y1="84" x2="292" y2="286" stroke="{INK}" stroke-opacity=".1"/>')
    bx0, bx1, base, top = 320, 840, 270, 92
    slot = (bx1 - bx0) / len(months)
    bw = slot * 0.58
    for i, ((y, m), v) in enumerate(months):
        h = max(3, (base - top) * v / mx)
        x = bx0 + i * slot + (slot - bw) / 2
        best = i == best_i
        fill = BLUE if best else INK
        op = "" if best else ' fill-opacity=".14"'
        parts.append(f'<rect x="{x:.1f}" y="{base - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="5" fill="{fill}"{op} '
                     f'class="grow" style="{d(0.4 + i * 0.07)}"><title>{v} in {dt.date(y, m, 1):%B %Y}</title></rect>')
        parts.append(f'<text x="{x + bw / 2:.1f}" y="{base + 20}" text-anchor="middle" class="mono" font-size="10.5" '
                     f'fill="{BLUE if best else MUTED}">{dt.date(y, m, 1):%b}</text>')
        if best:
            parts.append(f'<g class="pop" style="{d(0.4 + len(months) * 0.07 + 0.5)}">'
                         f'<text x="{x + bw / 2:.1f}" y="{base - h - 12:.1f}" text-anchor="middle" class="serif" font-size="24" fill="{BLUE}">{v}</text></g>')
    parts.append(f'<line x1="{bx0}" y1="{base + .5}" x2="{bx1}" y2="{base + .5}" stroke="{INK}" stroke-opacity=".18"/>')
    return svg(W, H, "\n".join(parts), [SERIF, SANS, MONO], title="Monthly contribution activity")


# ── 4. tiles ──────────────────────────────────────────────────────────────
def count_up(x, y, target, fmt, begin, size, fill, frames=18, step=0.055):
    out = []
    for i in range(frames):
        t = i / (frames - 1)
        val = round(target * (1 - (1 - t) ** 3))
        label = esc(fmt(val))
        if STATIC and i < frames - 1:
            continue
        if i < frames - 1:
            out.append(f'<text x="{x}" y="{y}" class="serif" font-size="{size}" fill="{fill}" opacity="0">{label}'
                       f'<set attributeName="opacity" to="1" begin="{begin + i * step:.3f}s" dur="{step:.3f}s"/></text>')
        else:
            out.append(f'<text x="{x}" y="{y}" class="serif" font-size="{size}" fill="{fill}">{label}'
                       f'<set attributeName="opacity" to="0" begin="0s" dur="{begin + i * step:.3f}s"/></text>')
    return "".join(out)


def tile(idx, word, key, target, fmt, caption, delay):
    bg, fg, accent = TILES[key]
    W, H = 286, 300
    css = f"""@keyframes swing{{0%{{opacity:0;transform:translateY(90px) rotate(7deg)}}65%{{opacity:1;transform:translateY(-8px) rotate(-1.5deg)}}100%{{opacity:1;transform:none}}}}
.swing{{transform-box:view-box;transform-origin:50% 100%;animation:swing 1.1s cubic-bezier(.2,.8,.2,1) both}}
@keyframes ring{{0%{{opacity:.5;transform:scale(.2)}}100%{{opacity:0;transform:scale(1)}}}}
.ring{{opacity:0;transform-box:fill-box;transform-origin:center;animation:ring 3s ease-out infinite}}"""
    parts = [f'<g class="swing" style="{d(delay)}">',
             f'<rect width="{W}" height="{H}" fill="{bg}"/>',
             f'<circle cx="{W}" cy="0" r="150" fill="none" stroke="{accent}" stroke-width="1.5" class="ring" style="{d(delay + 0.8)}"/>',
             f'<circle cx="{W}" cy="0" r="150" fill="none" stroke="{accent}" stroke-width="1.5" class="ring" style="{d(delay + 2.3)}"/>',
             f'<text x="26" y="44" class="mono" font-size="12" letter-spacing="2" fill="{fg}" fill-opacity=".75">{idx} / {word}</text>',
             count_up(22, 162, target, fmt, delay + 0.6, 84, accent)]
    for k, line in enumerate(wrap(caption, 15, W - 56)):
        parts.append(f'<text x="26" y="{206 + k * 21}" class="sans" font-size="15" fill="{fg}" fill-opacity=".85">{esc(line)}</text>')
    parts.append(f'<g class="nudge"><text x="{W - 26}" y="{H - 24}" text-anchor="end" class="sans" font-size="26" fill="{accent}">↗</text></g>')
    # sweeping shine
    parts.append(f"""<defs><linearGradient id="sh" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity="{SHINE_OP}"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>
<rect x="-160" y="-60" width="110" height="{H + 120}" fill="url(#sh)" transform="rotate(18)">
<animate attributeName="x" values="-260;-260;{W + 120}" keyTimes="0;.7;1" dur="5.5s" begin="{delay + 1.5}s" repeatCount="indefinite"/></rect>""")
    parts.append("</g>")
    return svg(W, H, "\n".join(parts), [SERIF, SANS, MONO], css, f"{word}: {fmt(target)}", bg=bg, border=TILE_BORDER)


# ── 5. toolbox ────────────────────────────────────────────────────────────
STACK = [
    ("LANG", ["JavaScript", "TypeScript", "Kotlin", "C++", "Python"]),
    ("WEB", ["React", "Node.js", "Express", "MongoDB", "Tailwind"]),
    ("TOOLS", ["Git", "Android Studio", "Vercel", "Cloudinary", "Postman"]),
]


def toolbox():
    W, H = 880, 230
    parts = [f'<text x="40" y="58" class="serif rise" font-size="30" fill="{INK}">Toolbox</text>',
             f'<text x="836" y="56" text-anchor="end" class="mono fade" font-size="11" letter-spacing="1.4" fill="{MUTED}">WHAT I REACH FOR</text>']
    accents = [BLUE, RED, YELLOW]
    n = 0
    for r, (label, items) in enumerate(STACK):
        y = 96 + r * 44
        parts.append(f'<text x="40" y="{y + 19}" class="mono fade" font-size="11" letter-spacing="1.6" fill="{MUTED}" style="{d(0.2 + r * 0.1)}">{label}</text>')
        x = 120
        for item in items:
            w = text_w(item, 13.5, "mono") + 40
            parts.append(f'<g class="rise" style="{d(0.3 + n * 0.05)}">'
                         f'<rect x="{x}" y="{y}" width="{w:.0f}" height="30" rx="15" fill="{PAPER2}" stroke="{INK}" stroke-opacity=".08"/>'
                         f'<circle cx="{x + 15}" cy="{y + 15}" r="3.5" fill="{accents[r]}"/>'
                         f'<text x="{x + 26}" y="{y + 19.5}" class="mono" font-size="13.5" fill="{INK}">{esc(item)}</text></g>')
            x += w + 10
            n += 1
    return svg(W, H, "\n".join(parts), [SERIF, MONO], title="Toolbox")


# ── 6. repo cards ─────────────────────────────────────────────────────────
REPOS = [
    ("GS-Marketplace", "Campus Marketplace", "A student-only P2P marketplace to buy, sell and rent on campus. Full MERN stack.", "JavaScript", "#F1E05A", "BLUE"),
    ("Crypto-Futures-Tracker", "CryptoStatus", "Turns your Android status bar into a live crypto ticker, updating every second from Binance.", "Kotlin", "#A97BFF", "RED"),
    ("Credex", "RightSize", "Audit your startup's AI spend across 8 vendors (Cursor, Copilot, ChatGPT, Claude...) in one view.", "TypeScript", "#3178C6", "YELLOW"),
    ("Careerflow", "Careerflow", "An AI-powered job application tracker with a Kanban board for every stage of the hunt.", "TypeScript", "#3178C6", "BLUE"),
]


def repo_card(i, slug, name, desc, lang, lang_color, accent):
    accent = globals()[accent]
    W, H = 432, 196
    delay = 0.2 + (i % 2) * 0.15
    parts = [f'<rect width="{W}" height="5" fill="{accent}" class="fade" style="{d(delay)}"/>',
             f'<g class="rise" style="{d(delay)}">',
             f'<text x="28" y="58" class="serif" font-size="32" fill="{INK}">{esc(name)}</text>',
             f'<text x="29" y="82" class="mono" font-size="11" fill="{MUTED}">RajvirGautam/{esc(slug)}</text>']
    for k, line in enumerate(wrap(desc, 14.5, W - 60)[:3]):
        parts.append(f'<text x="28" y="{116 + k * 20}" class="sans" font-size="14.5" fill="{INK}" fill-opacity=".8">{esc(line)}</text>')
    parts.append(f'<circle cx="34" cy="{H - 27}" r="5" fill="{lang_color}"/>'
                 f'<text x="46" y="{H - 23}" class="mono" font-size="11.5" fill="{MUTED}">{lang}</text></g>')
    parts.append(f'<g class="nudge"><text x="{W - 26}" y="54" text-anchor="end" class="sans" font-size="22" fill="{INK}">↗</text></g>')
    return svg(W, H, "\n".join(parts), [SERIF, SANS, MONO], title=f"{name} — {desc}")


# ── main ──────────────────────────────────────────────────────────────────
def main():
    for theme, palette in THEMES.items():
        globals().update(palette)
        render(OUT if theme == "light" else OUT / "dark")


def render(out):
    out.mkdir(parents=True, exist_ok=True)
    cards = {
        "hero.svg": hero(),
        "graph.svg": graph(),
        "activity.svg": activity(),
        "build.svg": tile("01", "BUILD", "blue", DATA["public_repos"], str,
                          "public repositories: web apps, Android widgets and everything in between", 0.2),
        "lead.svg": tile("02", "LEAD", "red", 3000, lambda v: f"{v:,}+",
                         "participants at AAROHAN 2025, SGSITS's first techfest. Main student coordinator.", 0.35),
        "ship.svg": tile("03", "SHIP", "yellow", TOTAL, lambda v: f"{v:,}",
                         "contributions pushed to GitHub in the last 12 months", 0.5),
        "toolbox.svg": toolbox(),
    }
    for i, r in enumerate(REPOS):
        cards[f"repo-{r[0].lower()}.svg"] = repo_card(i, *r)
    for name, content in cards.items():
        (out / name).write_text(content)
        print(f"{out.name}/{name:28s} {len(content) / 1024:6.1f} KB")


if __name__ == "__main__":
    main()
