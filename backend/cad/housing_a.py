"""Housing - A CAD drawing (RES format).

An annular ring (OD = stack dia, ID = PCD + 2) with two radial cuts at 180°,
each cut (width = squib width + 2) running only from the ID to the OD. Two
sectional views:
  * SECTION A-A (horizontal cut): the two ring walls, each a 3-layer laminate
    (top+middle hatch one way, bottom the opposite way) -> Silicon / Mica /
    Silicon making up the total thickness.
  * SECTION B-B (vertical cut, through the cuts): the two ring segments, hatched.
A small assembly BOM table sits just above the footer.
Total thickness = Mica Ring thk + 2 x Silicon Bonded Mica Ring thk.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, FOOT_TOP, BORDER_L, BORDER_R, THICK, MED,
                        THIN, C_LINE, C_HID, _n, line, rect, circle, text, arrow,
                        _header, _footer)
from .lid import _leader

DIA_TOL_OUT = "+0.0/-0.2"
DIA_TOL_IN = "+0.2/-0.0"


@dataclass
class HousingAParams:
    outer_dia: float                # = stack diameter
    inner_dia: float                # = PCD + 2
    mica_thk: float = 0.15          # Mica Ring thickness
    silicon_thk: float = 1.0        # Silicon Bonded Mica Ring thickness
    squib_width: float = 5.0
    num_cuts: int = 2
    dia_tol_out: str = DIA_TOL_OUT
    dia_tol_in: str = DIA_TOL_IN
    bom_rows: Optional[list] = None  # [(sno, name, qty, ref_drg_no), ...]
    component_name: str = "HOUSING - A"
    material: str = "ASSY"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    quantity: str = "01"
    date: str = ""
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class HousingAGeom:
    outer_dia: float
    inner_dia: float
    thickness: float
    cut_width: float
    num_cuts: int
    mica_thk: float
    silicon_thk: float
    dia_tol_out: str
    dia_tol_in: str
    warnings: list = field(default_factory=list)


def compute_housing_a(p: HousingAParams) -> HousingAGeom:
    w: list[str] = []
    outer = round(p.outer_dia, 2)
    inner = round(p.inner_dia, 2)
    if inner >= outer:      # PCD+2 bigger than the stack-sized OD -> not a valid ring
        inner = round(outer * 0.68, 2)
        w.append(f"Inner dia (PCD+2) exceeded the outer dia; using calculated Ø{inner}.")
    thickness = round(p.mica_thk + 2 * p.silicon_thk, 2)
    cut_w = round(p.squib_width + 2.0, 2)
    return HousingAGeom(outer_dia=outer, inner_dia=inner, thickness=thickness,
                        cut_width=cut_w, num_cuts=max(int(p.num_cuts or 2), 1),
                        mica_thk=p.mica_thk, silicon_thk=p.silicon_thk,
                        dia_tol_out=p.dia_tol_out or DIA_TOL_OUT,
                        dia_tol_in=p.dia_tol_in or DIA_TOL_IN, warnings=w)


def _defs() -> str:
    # two cross-hatch meshes: hA = diagonal X, hB = upright grid (the "opposite")
    # single-line patterns (these render reliably in svglib); hA = 45°, hB = -45°
    return ('<defs>'
            '<pattern id="hA" width="1.4" height="1.4" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">'
            '<line x1="0" y1="0" x2="0" y2="1.4" stroke="#111" stroke-width="0.14"/></pattern>'
            '<pattern id="hB" width="1.4" height="1.4" patternTransform="rotate(-45)" patternUnits="userSpaceOnUse">'
            '<line x1="0" y1="0" x2="0" y2="1.4" stroke="#111" stroke-width="0.14"/></pattern>'
            '</defs>')


def _hatch_lines(x0, y0, w, h, sign=1, step=1.5):
    """Explicit diagonal hatch segments in the rect (renders in browser AND svglib).
    sign=+1 -> 45°, sign=-1 -> -45°."""
    x1, y1 = x0 + w, y0 + h
    out = []
    if sign > 0:                          # lines y = x + c
        c = y0 - x1
        while c <= y1 - x0:
            pts = []
            yy = x0 + c
            if y0 <= yy <= y1: pts.append((x0, yy))
            yy = x1 + c
            if y0 <= yy <= y1: pts.append((x1, yy))
            xx = y0 - c
            if x0 < xx < x1: pts.append((xx, y0))
            xx = y1 - c
            if x0 < xx < x1: pts.append((xx, y1))
            if len(pts) >= 2:
                out.append(line(pts[0][0], pts[0][1], pts[1][0], pts[1][1], THIN))
            c += step
    else:                                 # lines y = -x + c
        c = y0 + x0
        while c <= y1 + x1:
            pts = []
            yy = c - x0
            if y0 <= yy <= y1: pts.append((x0, yy))
            yy = c - x1
            if y0 <= yy <= y1: pts.append((x1, yy))
            xx = c - y0
            if x0 < xx < x1: pts.append((xx, y0))
            xx = c - y1
            if x0 < xx < x1: pts.append((xx, y1))
            if len(pts) >= 2:
                out.append(line(pts[0][0], pts[0][1], pts[1][0], pts[1][1], THIN))
            c += step
    return out


def _balloon(x, y, n) -> str:
    return circle(x, y, 2.4, THIN) + text(x, y + 0.9, str(n), 2.4, weight="bold")


def _hbar(x, y, xa, xb, gaps):
    """Horizontal line xa..xb with gaps (list of (g0,g1)) removed."""
    xa, xb = min(xa, xb), max(xa, xb)
    segs = [(xa, xb)]
    for g0, g1 in gaps:
        g0, g1 = min(g0, g1), max(g0, g1)
        out = []
        for s0, s1 in segs:
            if g1 <= s0 or g0 >= s1:
                out.append((s0, s1)); continue
            if g0 > s0:
                out.append((s0, g0))
            if g1 < s1:
                out.append((g1, s1))
        segs = out
    return "".join(line(s0, y, s1, y, THICK) for s0, s1 in segs)


# Wall = 3 layers (top two forward-hatch = comp 2, bottom reverse-hatch = comp 1)
# Middle bore span = 2 layers (cross-hatch = comp 3)
_WALL_LAYERS = [(0.33, "fwd"), (0.33, "fwd"), (0.34, "rev")]
_MID_LAYERS = [(0.5, "cross"), (0.5, "cross")]


def _hatch_region(x0, y0, w, h, kind):
    """Rect + hatch. kind: 'fwd' (+45°), 'rev' (-45°), 'cross' (both)."""
    out = [rect(x0, y0, w, h, THICK)]
    if kind in ("fwd", "cross"):
        out += _hatch_lines(x0, y0, w, h, 1)
    if kind in ("rev", "cross"):
        out += _hatch_lines(x0, y0, w, h, -1)
    return out


def _vstack(x0, x1, yTop, tp, layers):
    """Layers stacked top->bottom (Section A-A)."""
    out = []
    yy = yTop
    for frac, kind in layers:
        h = tp * frac
        out += _hatch_region(x0, yy, x1 - x0, h, kind)
        yy += h
    return out


def _hstack(y0, y1, xLeft, tp, layers):
    """Layers stacked left->right (Section B-B = A-A rotated 90°)."""
    out = []
    xx = xLeft
    for frac, kind in layers:
        w = tp * frac
        out += _hatch_region(xx, y0, w, y1 - y0, kind)
        xx += w
    return out


def _views(g: HousingAGeom, p: HousingAParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = ax0 + (ax1 - ax0) * 0.34
    sv = min((ax1 - ax0 - 96) / g.outer_dia, (ay1 - ay0 - 150) / g.outer_dia)
    r = g.outer_dia * sv / 2
    r = max(20.0, min(r, 40.0))
    ri = g.inner_dia / g.outer_dia * r
    cw = g.cut_width * sv
    cut_angles = [90 + i * (360 / g.num_cuts) for i in range(g.num_cuts)]

    # ---------------- TOP VIEW ----------------
    cy1 = ay0 + 6 + r
    # continuous OUTER and INNER walls (the cuts are closed at both ends by these)
    s.append(circle(cx, cy1, r, THICK))
    s.append(circle(cx, cy1, ri, THICK))
    # cuts: two radial side walls each, running from the inner wall to the outer wall
    for a in cut_angles:
        ar = math.radians(a)
        rx, ry = math.cos(ar), -math.sin(ar)       # radial unit
        px, py = -math.sin(ar), -math.cos(ar)      # perpendicular unit
        ro = math.sqrt(max(r * r - (cw / 2) ** 2, 1.0))
        rin = math.sqrt(max(ri * ri - (cw / 2) ** 2, 1.0))
        for sgn in (-1, 1):
            xi = cx + rin * rx + sgn * (cw / 2) * px
            yi = cy1 + rin * ry + sgn * (cw / 2) * py
            xo = cx + ro * rx + sgn * (cw / 2) * px
            yo = cy1 + ro * ry + sgn * (cw / 2) * py
            s.append(line(xi, yi, xo, yo, THICK))
    # centre lines
    s.append(line(cx - r - 8, cy1, cx + r + 8, cy1, THIN, dash=C_LINE))
    s.append(line(cx, cy1 - r - 10, cx, cy1 + r + 10, THIN, dash=C_LINE))
    # dia leaders (OD, ID) with tolerance
    ao = math.radians(35)
    s.append(_leader(cx + r * math.cos(ao), cy1 - r * math.sin(ao), cx + r + 20, cy1 - r * 0.55,
                     f"Ø{_n(g.outer_dia)} {g.dia_tol_out}"))
    ai = math.radians(-20)
    s.append(_leader(cx + ri * math.cos(ai), cy1 - ri * math.sin(ai), cx + r + 20, cy1 - r * 0.05,
                     f"Ø{_n(g.inner_dia)} {g.dia_tol_in}"))
    # A-A markers (horizontal, left & right — arrows up)
    for sx, d in ((cx - r - 8, -1), (cx + r + 8, 1)):
        s.append(arrow(sx, cy1 - 2, 0, -1))
        s.append(line(sx, cy1 - 2, sx, cy1 + 4, THIN))
        s.append(text(sx + d * 3, cy1 + 3, "A", 2.8, weight="bold"))
    # B-B markers (vertical, top & bottom — arrows toward centre)
    for sy, d in ((cy1 - r - 10, -1), (cy1 + r + 10, 1)):
        s.append(arrow(cx - 2, sy, -1, 0))
        s.append(line(cx - 2, sy, cx + 4, sy, THIN))
        s.append(text(cx + 3, sy + d * 3 + 1, "B", 2.8, weight="bold"))
    # cut width dimension (bottom cut) — small dim: arrows OUTSIDE pointing inward
    yb = cy1 + (ri + r) / 2 + 3
    ydl = yb + 3
    s.append(line(cx - cw / 2, cy1 + ri, cx - cw / 2, ydl, THIN))
    s.append(line(cx + cw / 2, cy1 + ri, cx + cw / 2, ydl, THIN))
    s.append(line(cx - cw / 2 - 4, ydl, cx + cw / 2 + 4, ydl, THIN))
    s.append(arrow(cx - cw / 2, ydl, 1, 0)); s.append(arrow(cx + cw / 2, ydl, -1, 0))
    s.append(text(cx, ydl + 4.5, f"{_n(g.cut_width)}", 3.5))

    # ---------------- SECTION A-A (horizontal, below) ----------------
    tsc = 22.0 / g.thickness                      # thickness scaled tall
    tp = g.thickness * tsc
    wf = 1.3                                       # widen the section (width only)
    rW, riW = r * wf, ri * wf
    sec_cy = cy1 + r + 34                          # extra gap so ③ clears the cut-width value
    yTop = sec_cy - tp / 2
    xL0, xL1 = cx - rW, cx - riW                   # left wall  (outer->inner)
    xR0, xR1 = cx + riW, cx + rW                   # right wall (inner->outer)
    # walls: 3 layers (top two 'fwd' = comp 2, bottom 'rev' = comp 1)
    s += _vstack(xL0, xL1, yTop, tp, _WALL_LAYERS)
    s += _vstack(xR0, xR1, yTop, tp, _WALL_LAYERS)
    # middle (inner dia -> inner dia): 2 layers, cross-hatch = comp 3
    s += _vstack(xL1, xR0, yTop, tp, _MID_LAYERS)

    # balloons: ② top two wall layers, ① bottom wall layer, ③ middle
    y_top2 = yTop + tp * 0.33                      # centre of the top two layers
    y_bot = yTop + tp * 0.83                       # centre of the bottom layer
    s.append(line(xR1, y_top2, xR1 + 5.6, y_top2, THIN)); s.append(_balloon(xR1 + 8, y_top2, 2))
    s.append(line(xL0, y_bot, xL0 - 5.6, y_bot, THIN)); s.append(_balloon(xL0 - 8, y_bot, 1))
    # ③ middle — offset left of the (centred) cut-width value so they don't overlap
    m3x = xL1 + (xR0 - xL1) * 0.28
    s.append(line(m3x, yTop, m3x, yTop - 7, THIN))
    s.append(_balloon(m3x, yTop - 10, 3))
    # thickness dim (right) — arrows exactly at the two faces (no overshoot)
    xtd = xR1 + 20
    s.append(line(xR1, yTop, xtd + 3, yTop, THIN)); s.append(line(xR1, yTop + tp, xtd + 3, yTop + tp, THIN))
    s.append(line(xtd, yTop, xtd, yTop + tp, THIN))
    s.append(arrow(xtd, yTop, 0, -1)); s.append(arrow(xtd, yTop + tp, 0, 1))
    s.append(text(xtd + 2.5, sec_cy + 1, f"{_n(g.thickness)}", 3.5, anchor="start"))
    s.append(text(xtd + 2.5, yTop - 1, "(STD)", 3.0, anchor="start"))
    s.append(text(cx, yTop + tp + 8, "SECTION  A-A", 2.6, weight="bold"))

    # ---------------- SECTION B-B (A-A rotated 90° to the left) ----------------
    bx = ax1 - 20
    by_c = cy1
    bw = tp                                       # width (x) = thickness
    x0 = bx - bw / 2
    yT0, yT1 = by_c - r, by_c - ri                # top wall  (outer->inner)
    yB0, yB1 = by_c + ri, by_c + r                # bottom wall(inner->outer)
    s += _hstack(yT0, yT1, x0, tp, _WALL_LAYERS)
    s += _hstack(yB0, yB1, x0, tp, _WALL_LAYERS)
    # middle (inner dia -> inner dia): 2 layers, cross-hatch = comp 3
    s += _hstack(by_c - ri, by_c + ri, x0, tp, _MID_LAYERS)
    # balloon ① at the bottom (as in the reference)
    s.append(line(x0, by_c + r - 3, x0 - 5.6, by_c + r - 3, THIN))
    s.append(_balloon(x0 - 8, by_c + r - 3, 1))
    s.append(text(bx + bw / 2 + 10, by_c, "SECTION B-B", 2.6, weight="bold", rot=90))

    # ---------------- assembly BOM table (above footer) ----------------
    s += _bom_table(g, p)
    return s


def _arc(cx, cy, R, a0, a1, wd=THICK):
    steps = max(3, int(abs(a1 - a0) / 5))
    pts = [(cx + R * math.cos(math.radians(a0 + (a1 - a0) * k / steps)),
            cy - R * math.sin(math.radians(a0 + (a1 - a0) * k / steps))) for k in range(steps + 1)]
    return ('<polyline points="' + " ".join(f"{_n(x)},{_n(y)}" for x, y in pts) +
            f'" fill="none" stroke="#111" stroke-width="{wd}"/>')


def _bom_table(g: HousingAGeom, p: HousingAParams) -> list[str]:
    s: list[str] = []
    rows = p.bom_rows or [
        (1, "MICA RING", "01", ""),
        (2, "SILICON BONDED MICA RING (HOUSING - A)", "02", ""),
        (3, "FIBERFRAX DISC", "02", ""),
    ]
    cols = [("S.No", 12), ("COMPONENT NAME", 96), ("QTY/NoS", 24), ("REF. DRG. NO", 40)]
    tw = sum(w for _, w in cols)
    x0 = BORDER_R - tw
    rh = 5.0
    y0 = FOOT_TOP - (len(rows) + 1) * rh - 1.5
    # outer + header
    s.append(rect(x0, y0, tw, (len(rows) + 1) * rh, MED))
    cxs = [x0]
    for _, w in cols:
        cxs.append(cxs[-1] + w)
    for i, (name, w) in enumerate(cols):
        s.append(line(cxs[i], y0, cxs[i], y0 + (len(rows) + 1) * rh, THIN))
        s.append(text((cxs[i] + cxs[i + 1]) / 2, y0 + rh - 1.6, name, 1.7, weight="bold"))
    for r_i, row in enumerate(rows):
        ry = y0 + (r_i + 1) * rh
        s.append(line(x0, ry, x0 + tw, ry, THIN))
        vals = [str(row[0]), row[1], row[2], row[3] or ""]
        for c_i, v in enumerate(vals):
            anc = "middle" if c_i != 1 else "start"
            xx = (cxs[c_i] + cxs[c_i + 1]) / 2 if c_i != 1 else cxs[c_i] + 1.5
            s.append(text(xx, ry + rh - 1.7, v, 1.6, anchor=anc))
    return s


def render_housing_a_svg(g: HousingAGeom, p: HousingAParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>', _defs()]
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
