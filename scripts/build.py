#!/usr/bin/env python3
"""Builds the profile cards in assets/.

The cards reuse the portfolio's palette and fonts. Each SVG embeds only the
glyphs it uses, so it renders the same wherever GitHub shows it.

    pip install fonttools brotli
    python3 scripts/build.py --fonts ../portfolio/fonts
"""
import argparse
import base64
import io
import math
import pathlib
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"

NIGHT, DUSK, TWILIGHT, ABYSS = "#070A14", "#0B1222", "#0A1828", "#02121A"
SNOW, MIST, DIM = "#ECEFF6", "#9AA3B8", "#5D6680"
ALPEN, GLACIER = "#F4AE8A", "#84D9E6"
RIDGE_FAR, RIDGE_MID = "#20284A", "#121A33"
SKY = ("#0D1430", "#2A2442", "#6E4B58")
SEA = ("#0F4C5C", "#08303D", "#03161D")
EASE = "cubic-bezier(.22,1,.36,1)"


def mix(a, b, t):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ca, cb))


# ---------- fonts ----------

class Face:
    """One font at one weight: measures text and embeds a subset of itself."""

    def __init__(self, path, family, wght=None):
        font = TTFont(path)
        if "fvar" in font:
            axes = {a.axisTag: a.defaultValue for a in font["fvar"].axes}
            if wght is not None:
                axes["wght"] = wght
            font = instancer.instantiateVariableFont(font, axes)
        buf = io.BytesIO()
        font.flavor = None
        font.save(buf)
        self.data = buf.getvalue()
        self.family = family
        self.upm = font["head"].unitsPerEm
        self.cmap = font.getBestCmap()
        self.adv = {g: m[0] for g, m in font["hmtx"].metrics.items()}
        self.used = set()

    def width(self, s, size, ls=0.0):
        """Advance width in px; ls is letter-spacing in em, as in CSS."""
        units = 0
        for ch in s:
            if ord(ch) not in self.cmap:
                raise KeyError(f"{self.family} has no glyph for {ch!r}")
            units += self.adv[self.cmap[ord(ch)]]
        return units * size / self.upm + ls * size * len(s)

    def css(self):
        if not self.used:
            return ""
        font = TTFont(io.BytesIO(self.data))
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = ["*"]
        sub = subset.Subsetter(opts)
        sub.populate(text="".join(sorted(self.used)))
        sub.subset(font)
        buf = io.BytesIO()
        font.flavor = "woff2"
        font.save(buf)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f'@font-face{{font-family:"{self.family}";src:url(data:font/woff2;base64,{b64}) format("woff2")}}'


class Doc:
    """An SVG card: collects markup, tracks glyphs, writes a self-contained file."""

    def __init__(self, fonts_dir, w, h, title):
        self.w, self.h, self.title = w, h, title
        self.faces = {
            "display": Face(fonts_dir / "big-shoulders-display.woff2", "RM Display", 800),
            "body": Face(fonts_dir / "instrument-sans.woff2", "RM Sans", 500),
            "mono": Face(fonts_dir / "ibm-plex-mono-400.woff2", "RM Mono"),
            "script": Face(fonts_dir / "pinyon-script.woff2", "RM Script"),
        }
        self.fallback = {
            "display": '"Arial Narrow",sans-serif',
            "body": "system-ui,sans-serif",
            "mono": "ui-monospace,Menlo,monospace",
            "script": "cursive",
        }
        self.defs, self.body, self.styles = [], [], []

    def measure(self, s, face, size, ls=0.0):
        return self.faces[face].width(s, size, ls)

    def text(self, x, y, s, face, size, fill, ls=0.0, anchor="start", attrs=""):
        f = self.faces[face]
        f.width(s, size, ls)  # validates glyphs
        f.used |= set(s)
        spacing = f' letter-spacing="{ls * size:.2f}"' if ls else ""
        anchor_attr = f' text-anchor="{anchor}"' if anchor != "start" else ""
        return (f'<text x="{x:.1f}" y="{y:.1f}" class="{face}" font-size="{size}" fill="{fill}"'
                f'{spacing}{anchor_attr} {attrs}>{escape(s)}</text>')

    def add(self, *parts):
        self.body.extend(parts)

    def write(self, name):
        fonts = "".join(f.css() for f in self.faces.values())
        families = "".join(
            f'.{k}{{font-family:"{f.family}",{self.fallback[k]}}}' for k, f in self.faces.items() if f.used)
        motion = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" '
            f'height="{self.h}" role="img" aria-labelledby="title"><title id="title">{escape(self.title)}</title>'
            f'<style>{fonts}{families}{"".join(self.styles)}{motion}</style>'
            f'<defs><clipPath id="card"><rect width="{self.w}" height="{self.h}" rx="20"/></clipPath>'
            f'{"".join(self.defs)}</defs>'
            f'<g clip-path="url(#card)">{"".join(self.body)}</g>'
            f'<rect x=".5" y=".5" width="{self.w - 1}" height="{self.h - 1}" rx="19.5" fill="none" '
            f'stroke="{SNOW}" stroke-opacity=".12"/></svg>'
        )
        OUT.mkdir(exist_ok=True)
        (OUT / name).write_text(svg)
        print(f"{name}: {len(svg) / 1024:.1f} KB")


# ---------- terrain (ported from the portfolio hero) ----------

def rng(seed):
    state = [seed & 0xFFFFFFFF]

    def imul(a, b):
        return (a * b) & 0xFFFFFFFF

    def r():
        state[0] = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        s = state[0]
        t = imul(s ^ (s >> 15), 1 | s)
        t = ((t + imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return r


def ridge(seed, w, top, bottom, rough=0.55, peak=None, x0=0.0, n=129):
    r = rng(seed)
    ys = [0.0] * n
    ys[0], ys[-1] = r(), r()
    step, amp = n - 1, 1.0
    while step > 1:
        half = step // 2
        for i in range(half, n, step):
            ys[i] = (ys[i - half] + ys[i + half]) / 2 + (r() - 0.5) * amp
        step //= 2
        amp *= rough
    lo, hi = min(ys), max(ys)
    pts = []
    for i, v in enumerate(ys):
        x = i / (n - 1)
        k = (v - lo) / ((hi - lo) or 1)
        if peak:
            tri = max(0.0, 1 - abs(x - peak[0]) / peak[1])
            k = max(k * peak[2], tri * tri * (3 - 2 * tri) + (k - 0.5) * 0.1 * tri)
        pts.append((x0 + x * w, bottom - k * (bottom - top)))
    return pts


def line(pts):
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)


def area(pts, floor):
    return f"M{pts[0][0]:.1f} {floor} L" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + f" L{pts[-1][0]:.1f} {floor}Z"


def smooth(pts):
    """Catmull-Rom through pts, as cubic Béziers."""
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}"
    return d


def stars(doc, count, seed, w, h, twinkle=True, avoid=()):
    """Scatter stars over the top h px, keeping clear of the (x0, y0, x1, y1) boxes in avoid."""
    r = rng(seed)
    out = []
    for i in range(count):
        x, y = r() * w, r() ** 1.4 * h
        if any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in avoid):
            continue
        rad = 0.5 + r() * 1.1
        op = 0.25 + r() * 0.65
        cls = ""
        if twinkle and i % 3 == 0:
            cls = f' class="tw" style="animation-delay:{r() * 6:.2f}s;animation-duration:{3 + r() * 4:.2f}s"'
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad:.2f}" fill="{SNOW}" fill-opacity="{op:.2f}"{cls}/>')
    doc.styles.append("@keyframes tw{0%,100%{opacity:1}50%{opacity:.2}}.tw{animation:tw 4s ease-in-out infinite}")
    return "".join(out)


def eyebrow(doc, x, y, label, accent=ALPEN):
    return (f'<line x1="{x}" y1="{y - 5}" x2="{x + 28}" y2="{y - 5}" stroke="{accent}" stroke-width="1.5"/>'
            + doc.text(x + 42, y, label, "mono", 15, MIST, ls=0.18))


def script(doc, x, y, s, size, fill=ALPEN):
    return doc.text(x, y, s, "script", size, fill, attrs=f'transform="rotate(-4 {x} {y})" filter="url(#glow)"')


def glow_filter(doc):
    doc.defs.append(
        '<filter id="glow" x="-20%" y="-60%" width="140%" height="220%">'
        '<feGaussianBlur in="SourceGraphic" stdDeviation="9" result="b"/>'
        '<feComponentTransfer in="b" result="g"><feFuncA type="linear" slope=".55"/></feComponentTransfer>'
        '<feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')


def wrap(doc, s, face, size, max_w):
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if cur and doc.measure(trial, face, size) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur]


# ---------- cards ----------

def hero(fonts):
    W, H = 1200, 440
    d = Doc(fonts, W, H, "Rishab Mishra, fullstack engineer. Clean code and thin air.")
    glow_filter(d)
    d.defs.append(
        f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{NIGHT}"/><stop offset=".38" stop-color="{SKY[0]}"/>'
        f'<stop offset=".7" stop-color="{SKY[1]}"/><stop offset=".95" stop-color="{SKY[2]}"/></linearGradient>'
        f'<radialGradient id="alpenglow" cx=".66" cy=".86" r=".55">'
        f'<stop offset="0" stop-color="{ALPEN}" stop-opacity=".34"/><stop offset="1" stop-color="{ALPEN}" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="farFill" gradientUnits="userSpaceOnUse" x1="0" y1="120" x2="0" y2="300">'
        f'<stop offset="0" stop-color="#34395F"/><stop offset="1" stop-color="{RIDGE_FAR}"/></linearGradient>'
        f'<linearGradient id="meteor" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{SNOW}" stop-opacity="0"/><stop offset="1" stop-color="{SNOW}"/></linearGradient>')
    d.styles.append(
        f"@keyframes meteor{{0%{{opacity:0;transform:translate(0,0)}}2%{{opacity:1}}"
        f"9%{{opacity:0;transform:translate(-300px,150px)}}100%{{opacity:0;transform:translate(-300px,150px)}}}}"
        f".meteor{{opacity:0;animation:meteor 11s linear 3s infinite}}")

    far = ridge(7, W, 120, 330, 0.52, peak=(0.68, 0.2, 0.55))
    mid = ridge(23, W, 292, 388, 0.5)
    near = ridge(4, W, 372, 432, 0.48)
    sx, sy = min(far, key=lambda p: p[1])

    d.add(
        f'<rect width="{W}" height="{H}" fill="url(#sky)"/>',
        f'<rect width="{W}" height="{H}" fill="url(#alpenglow)"/>',
        stars(d, 140, 31, W, 300, avoid=[(50, 70, 820, 290)]),
        f'<line class="meteor" x1="1010" y1="40" x2="1110" y2="40" stroke="url(#meteor)" stroke-width="1.4" '
        f'transform="rotate(-27 1110 40)"/>',
        f'<g><path d="{area(far, H)}" fill="url(#farFill)"/>'
        f'<path d="{line(far)}" fill="none" stroke="{ALPEN}" stroke-opacity=".6" stroke-width="1.3"/>'
        f'<line x1="{sx:.1f}" y1="{sy - 1:.1f}" x2="{sx:.1f}" y2="{sy - 50:.1f}" stroke="{SNOW}" stroke-width="1.4"/>'
        f'<path d="M{sx:.1f} {sy - 50:.1f} l22 7 l-22 7z" fill="{ALPEN}"/>'
        + d.text(sx - 12, sy - 38, "KANG YATSE II", "mono", 14, SNOW, ls=0.14, anchor="end")
        + d.text(sx - 12, sy - 19, "6,250 M", "mono", 12, MIST, ls=0.14, anchor="end")
        + "</g>",
        f'<path d="{area(mid, H)}" fill="{RIDGE_MID}"/>',
        f'<path d="{area(near, H)}" fill="{NIGHT}"/>',
    )

    x = 72
    d.add(
        eyebrow(d, x, 100, "FULLSTACK ENGINEER"),
        d.text(x - 4, 206, "RISHAB MISHRA", "display", 112, SNOW, ls=0.005),
        script(d, x + 150, 274, "clean code & thin air", 54),
        d.text(x, 412, "SKYDIVER  ·  FREEDIVER  ·  MOUNTAINEER", "mono", 15, MIST, ls=0.2),
    )
    d.write("hero.svg")


STACK = [
    ("CLIENT-SIDE", ["React", "Next.js", "TypeScript", "JavaScript", "Redux", "Tailwind CSS", "Emotion", "Sass"]),
    ("SERVER-SIDE", ["Node.js", "NestJS", "Java", "Spring", "PostgreSQL", "Kafka", "GraphQL", "REST", "Microservices"]),
    ("DELIVERY & OPS", ["Docker", "Kubernetes", "AWS", "CI/CD", "Jest", "Testing Library", "Datadog", "Splunk", "Swagger"]),
]


def card_header(d, eyebrow_label, title, tagline, blurb, accent=ALPEN):
    """Eyebrow, display title and script tagline on the left; a short blurb on the right."""
    x = 72
    parts = [
        eyebrow(d, x, 88, eyebrow_label, accent),
        d.text(x - 3, 168, title, "display", 78, SNOW, ls=0.005),
        script(d, x + 70, 214, tagline, 44, accent),
    ]
    bx, bw = 744, d.w - 72 - 744
    for i, ln in enumerate(wrap(d, blurb, "body", 19, bw)):
        parts.append(d.text(bx, 112 + i * 30, ln, "body", 19, MIST))
    return "".join(parts)


def stack(fonts):
    W = 1200
    d = Doc(fonts, W, 10, "Stack. " + ". ".join(f"{k.title()}: {', '.join(v)}" for k, v in STACK) + ".")
    glow_filter(d)
    gap, x0, top = 44, 72, 280
    colw = (W - 2 * x0 - 2 * gap) / 3
    accents = [ALPEN, mix(ALPEN, GLACIER, 0.5), GLACIER]
    chip_h, chip_gap, pad, size = 40, 10, 17, 18

    cols, bottom = [], 0
    for i, (label, items) in enumerate(STACK):
        cx = x0 + i * (colw + gap)
        a = accents[i]
        parts = [
            d.text(cx, top, f"0{i + 1}", "mono", 14, a, ls=0.16),
            d.text(cx + 34, top, label, "mono", 14, SNOW, ls=0.16),
            f'<line x1="{cx}" y1="{top + 18}" x2="{cx + colw:.1f}" y2="{top + 18}" stroke="{SNOW}" stroke-opacity=".12"/>',
            f'<line x1="{cx}" y1="{top + 18}" x2="{cx + 44}" y2="{top + 18}" stroke="{a}" stroke-width="1.5"/>',
        ]
        x, y = cx, top + 42
        for item in items:
            w = d.measure(item, "body", size) + 2 * pad
            if x + w > cx + colw + 0.5:
                x, y = cx, y + chip_h + chip_gap
            parts.append(
                f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{chip_h}" rx="{chip_h / 2}" fill="{SNOW}" '
                f'fill-opacity=".035" stroke="{SNOW}" stroke-opacity=".16"/>'
                + d.text(x + pad, y + 26, item, "body", size, SNOW))
            x += w + chip_gap
        bottom = max(bottom, y + chip_h)
        cols.append("".join(parts))

    H = int(bottom + 64)
    d.h = H
    d.defs.append(
        f'<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{DUSK}"/><stop offset="1" stop-color="{TWILIGHT}"/></linearGradient>'
        f'<radialGradient id="warm" cx=".05" cy="0" r=".6"><stop offset="0" stop-color="{ALPEN}" stop-opacity=".12"/>'
        f'<stop offset="1" stop-color="{ALPEN}" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="cool" cx="1" cy="1" r=".6"><stop offset="0" stop-color="{GLACIER}" stop-opacity=".1"/>'
        f'<stop offset="1" stop-color="{GLACIER}" stop-opacity="0"/></radialGradient>')
    d.add(
        f'<rect width="{W}" height="{H}" fill="url(#bg)"/>',
        f'<rect width="{W}" height="{H}" fill="url(#warm)"/><rect width="{W}" height="{H}" fill="url(#cool)"/>',
        stars(d, 60, 9, W, 250, twinkle=False, avoid=[(50, 50, 700, 240), (730, 80, 1150, 240)]),
        card_header(d, "STACK", "TOOLS I REACH FOR", "tools of the trade",
                    "From the schema to the last pixel. Interfaces that feel simple, "
                    "services that stay quiet in production, and the tooling that ships them."),
        *cols,
    )
    d.write("stack.svg")


def altitude(fonts):
    W, H = 1200, 676
    d = Doc(fonts, W, H, "Altitude and depth. Mountaineering: Kang Yatse II, 6,250 m, Ladakh. "
                        "Skydiving: B licence, exits around 4,000 m. Travel: 5 countries and counting. "
                        "Freediving: one breath, Apnea Total Advanced.")
    glow_filter(d)
    gx0, gx1, gtop, gbot = 150, 1128, 250, 492
    sea_y, peak_y = 404, 292
    scale = (sea_y - peak_y) / 6250
    colw = (gx1 - gx0) / 4
    centers = [gx0 + colw * (i + 0.5) for i in range(4)]
    accents = [mix(ALPEN, GLACIER, t) for t in (0, 1 / 3, 2 / 3, 1)]
    coast = 0.71

    # Terrain: a summit over the first column, foothills, plains, then the coast drops to the seabed.
    raw = ridge(5, gx1 - gx0, 0, 1, 0.5, peak=(0.125, 0.19, 0.22), x0=gx0)
    pts = []
    for x, k in raw:
        k = 1 - k  # ridge() returns y in [0,1] with 0 at the top
        xf = (x - gx0) / (gx1 - gx0)
        flat = min(1.0, max(0.0, (xf - 0.28) / 0.16))
        k *= 1 - 0.55 * flat * flat * (3 - 2 * flat)
        land = sea_y - 8 - k * (sea_y - 8 - peak_y)
        c = min(1.0, max(0.0, (xf - coast) / 0.07))
        c = c * c * (3 - 2 * c)
        floor = 474 + 3 * math.sin(xf * 61) + 2 * math.sin(xf * 23 + 1)
        pts.append((x, land * (1 - c) + floor * c))

    def ground(x):
        return min(pts, key=lambda p: abs(p[0] - x))[1]

    marks = [
        (centers[0], min(pts, key=lambda p: p[1])[1]),
        (centers[1], sea_y - 4000 * scale),
        (centers[2], ground(centers[2])),
        (centers[3], 458),
    ]
    marks[0] = min(pts, key=lambda p: p[1])
    sx, sy = marks[0]

    d.defs.append(
        f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{NIGHT}"/><stop offset=".5" stop-color="{DUSK}"/>'
        f'<stop offset="1" stop-color="{ABYSS}"/></linearGradient>'
        f'<radialGradient id="horizon"><stop offset="0" stop-color="{ALPEN}" stop-opacity=".12"/>'
        f'<stop offset="1" stop-color="{ALPEN}" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="water" gradientUnits="userSpaceOnUse" x1="0" y1="{sea_y}" x2="0" y2="{gbot}">'
        f'<stop offset="0" stop-color="{SEA[0]}"/><stop offset=".55" stop-color="{SEA[1]}"/>'
        f'<stop offset="1" stop-color="{SEA[2]}"/></linearGradient>'
        f'<linearGradient id="land" gradientUnits="userSpaceOnUse" x1="0" y1="{peak_y}" x2="0" y2="{gbot}">'
        f'<stop offset="0" stop-color="#232B4D"/><stop offset=".5" stop-color="{RIDGE_MID}"/>'
        f'<stop offset="1" stop-color="{NIGHT}"/></linearGradient>'
        f'<linearGradient id="span" gradientUnits="userSpaceOnUse" x1="{gx0}" y1="0" x2="{gx1}" y2="0">'
        f'<stop offset="0" stop-color="{ALPEN}"/><stop offset="1" stop-color="{GLACIER}"/></linearGradient>'
        f'<linearGradient id="edges" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        f'<stop offset=".06" stop-color="#fff"/><stop offset=".94" stop-color="#fff"/>'
        f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<mask id="graph" maskUnits="userSpaceOnUse" x="{gx0}" y="{gtop - 60}" width="{gx1 - gx0}" height="{gbot - gtop + 60}">'
        f'<rect x="{gx0}" y="{gtop - 60}" width="{gx1 - gx0}" height="{gbot - gtop + 60}" fill="url(#edges)"/></mask>'
        f'<linearGradient id="floor" x1="0" y1="0" x2="0" y2="1"><stop offset=".7" stop-color="#fff"/>'
        f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<mask id="sink" maskUnits="userSpaceOnUse" x="{gx0}" y="{gtop - 60}" width="{gx1 - gx0}" height="{gbot - gtop + 60}">'
        f'<rect x="{gx0}" y="{gtop - 60}" width="{gx1 - gx0}" height="{gbot - gtop + 60}" fill="url(#floor)"/></mask>')
    d.styles.append(
        "@keyframes march{to{stroke-dashoffset:-40}}.march{animation:march 2.4s linear infinite}"
        "@keyframes halo{0%,100%{opacity:.5;transform:scale(1)}50%{opacity:.12;transform:scale(1.5)}}"
        ".halo{transform-box:fill-box;transform-origin:center;animation:halo 3.2s ease-in-out infinite}"
        "@keyframes bubble{0%{opacity:0;transform:translateY(0)}20%{opacity:.9}100%{opacity:0;transform:translateY(-46px)}}"
        ".bubble{opacity:0;animation:bubble 3.6s ease-out infinite}"
        "@keyframes swell{0%,100%{transform:translateX(0)}50%{transform:translateX(-14px)}}"
        ".swell{animation:swell 7s ease-in-out infinite}")

    parts = [
        f'<rect width="{W}" height="{H}" fill="url(#bg)"/>',
        stars(d, 90, 13, W, 250, avoid=[(50, 50, 700, 240), (730, 80, 1150, 240)]),
        card_header(d, "OFF THE CLOCK", "ALTITUDE & DEPTH", "a life measured in metres",
                    "Up, off, across and under. Each one rewards what good engineering does: "
                    "preparation, calm under pressure and respect for the margins."),
        f'<ellipse cx="{(gx0 + gx1) / 2}" cy="{sea_y}" rx="{(gx1 - gx0) / 2}" ry="120" fill="url(#horizon)"/>',
    ]

    # Axis: altitude guides and labels.
    for alt, label in ((6250, "6,250 M"), (4000, "4,000 M"), (0, "0 M")):
        y = sea_y - alt * scale
        parts.append(f'<line x1="{gx0}" y1="{y:.1f}" x2="{gx1}" y2="{y:.1f}" stroke="{SNOW}" '
                     f'stroke-opacity="{.22 if alt == 0 else .1}" stroke-dasharray="2 6"/>')
        parts.append(d.text(gx0 - 16, y + 4, label, "mono", 13, DIM, ls=0.06, anchor="end"))
    for i in range(1, 4):
        x = gx0 + colw * i
        parts.append(f'<line x1="{x:.1f}" y1="{gtop}" x2="{x:.1f}" y2="{H - 56}" stroke="{SNOW}" stroke-opacity=".07"/>')

    # Sea, then land over it, then the ridge line.
    cx0 = next(x for x, y in pts if (x - gx0) / (gx1 - gx0) > coast - 0.1 and y >= sea_y)
    parts += [
        f'<g mask="url(#graph)"><g mask="url(#sink)">',
        f'<rect x="{cx0:.1f}" y="{sea_y}" width="{gx1 - cx0:.1f}" height="{gbot - sea_y}" fill="url(#water)"/>',
        f'<path class="swell" d="M{cx0:.1f} {sea_y + 9} q 18 -5 36 0' + " t 36 0" * 9 + '" '
        f'fill="none" stroke="{GLACIER}" stroke-opacity=".22"/>',
        f'<path d="{area(pts, gbot)}" fill="url(#land)"/>',
        f'<path d="{line(pts)}" fill="none" stroke="url(#span)" stroke-opacity=".7" stroke-width="1.3"/>',
        f'<line x1="{cx0:.1f}" y1="{sea_y}" x2="{gx1}" y2="{sea_y}" stroke="{GLACIER}" stroke-opacity=".6" stroke-width="1.2"/>',
        "</g></g>",
    ]

    # The descent: one dashed line through all four, summit to seabed.
    parts.append(f'<path class="march" d="{smooth(marks)}" fill="none" stroke="url(#span)" stroke-width="1.6" '
                 f'stroke-dasharray="4 6" stroke-linecap="round"/>')

    # Summit flag.
    parts.append(
        f'<line x1="{sx:.1f}" y1="{sy - 1:.1f}" x2="{sx:.1f}" y2="{sy - 40:.1f}" stroke="{SNOW}" stroke-width="1.3"/>'
        f'<path d="M{sx:.1f} {sy - 40:.1f} l18 6 l-18 6z" fill="{accents[0]}"/>'
        + d.text(sx - 10, sy - 28, "KANG YATSE II", "mono", 13, SNOW, ls=0.12, anchor="end"))

    # Canopy over the jumper.
    jx, jy = marks[1]
    a = accents[1]
    parts.append(
        f'<path d="M{jx - 26:.1f} {jy - 30:.1f} Q{jx:.1f} {jy - 50:.1f} {jx + 26:.1f} {jy - 30:.1f} '
        f'Q{jx:.1f} {jy - 40:.1f} {jx - 26:.1f} {jy - 30:.1f}Z" fill="{a}"/>'
        f'<path d="M{jx - 25:.1f} {jy - 30:.1f} L{jx:.1f} {jy - 6:.1f} L{jx + 25:.1f} {jy - 30:.1f} '
        f'M{jx - 9:.1f} {jy - 36:.1f} L{jx:.1f} {jy - 6:.1f} L{jx + 9:.1f} {jy - 36:.1f}" fill="none" '
        f'stroke="{SNOW}" stroke-opacity=".5" stroke-width=".8"/>'
        + d.text(jx + 34, jy - 34, "EXIT", "mono", 11, DIM, ls=0.16))

    # Map pin on the plains.
    px, py = marks[2]
    a = accents[2]
    parts.append(
        f'<path d="M{px:.1f} {py - 10:.1f} C{px - 4:.1f} {py - 18:.1f} {px - 11:.1f} {py - 22:.1f} {px - 11:.1f} {py - 31:.1f} '
        f'A11 11 0 1 1 {px + 11:.1f} {py - 31:.1f} C{px + 11:.1f} {py - 22:.1f} {px + 4:.1f} {py - 18:.1f} {px:.1f} {py - 10:.1f}Z" '
        f'fill="{a}"/><circle cx="{px:.1f}" cy="{py - 31:.1f}" r="4" fill="{DUSK}"/>')

    # Buoy, dive line and bubbles.
    fx, fy = marks[3]
    a = accents[3]
    parts.append(
        f'<line x1="{fx:.1f}" y1="{sea_y:.1f}" x2="{fx:.1f}" y2="{fy + 10:.1f}" stroke="{SNOW}" stroke-opacity=".45"/>'
        f'<circle cx="{fx:.1f}" cy="{sea_y - 2:.1f}" r="7" fill="{DUSK}" stroke="{a}" stroke-width="1.5"/>'
        + "".join(
            f'<circle class="bubble" style="animation-delay:{delay}s" cx="{fx + dx:.1f}" cy="{fy - 12:.1f}" r="{rad}" '
            f'fill="none" stroke="{SNOW}" stroke-opacity=".7"/>'
            for dx, rad, delay in ((6, 2.2, 0), (10, 1.5, 1.2), (4, 1.8, 2.4))))

    for (mx, my), a in zip(marks, accents):
        parts.append(f'<circle class="halo" cx="{mx:.1f}" cy="{my:.1f}" r="10" fill="{a}" fill-opacity=".35"/>'
                     f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="4.5" fill="{a}"/>'
                     f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="4.5" fill="none" stroke="{NIGHT}" stroke-width="1.5"/>')

    # Legend under each column.
    legend = [
        ("MOUNTAINEERING", "6,250 M", "Kang Yatse II, Ladakh"),
        ("SKYDIVING", "4,000 M", "B licence, exit altitude"),
        ("TRAVEL", "± 0 M", "5 countries and counting"),
        ("FREEDIVING", "1 BREATH", "Apnea Total Advanced"),
    ]
    for i, ((kind, figure, note), a) in enumerate(zip(legend, accents)):
        x = gx0 + colw * i + 22
        parts += [
            d.text(x, 540, kind, "mono", 14, a, ls=0.18),
            d.text(x - 2, 592, figure, "display", 50, SNOW, ls=0.01),
            d.text(x, 624, note, "mono", 14, MIST, ls=0.02),
        ]

    d.add(*parts)
    d.write("altitude.svg")


def button(fonts, name, label, accent):
    W, H = 220, 56
    d = Doc(fonts, W, H, label.title())
    tw = d.measure(label, "mono", 14, 0.2)
    x = (W - tw - 22) / 2
    ax, ay = x + tw + 12, H / 2
    d.add(
        f'<rect width="{W}" height="{H}" fill="{DUSK}"/>',
        d.text(x, 33, label, "mono", 14, SNOW, ls=0.2),
        f'<path d="M{ax:.1f} {ay + 5:.1f} L{ax + 10:.1f} {ay - 5:.1f} M{ax + 2:.1f} {ay - 5:.1f} L{ax + 10:.1f} {ay - 5:.1f} '
        f'L{ax + 10:.1f} {ay + 3:.1f}" fill="none" stroke="{accent}" stroke-width="1.6" stroke-linecap="round" '
        f'stroke-linejoin="round"/>',
    )
    d.write(name)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fonts", type=pathlib.Path, default=ROOT.parent / "portfolio" / "fonts")
    fonts = p.parse_args().fonts
    hero(fonts)
    stack(fonts)
    altitude(fonts)
    button(fonts, "btn-website.svg", "WEBSITE", ALPEN)
    button(fonts, "btn-linkedin.svg", "LINKEDIN", mix(ALPEN, GLACIER, 0.5))
    button(fonts, "btn-email.svg", "EMAIL", GLACIER)


if __name__ == "__main__":
    main()
