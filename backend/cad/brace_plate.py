"""Brace Plate CAD drawing (RES format).

Three views:
  * TOP VIEW  : outer circle (Brace Plate Dia = cathode dia) + inner dashed circle
    (outer - 2 x 6 mm radial clearance). At each tie-wire position (360/N apart) a
    radial construction line runs to the outer circle, and the brace plate is shown
    as two short parallel lines that TOUCH the inner dia. One position carries the
    DETAIL-A bubble and the horizontal D-D cutting plane. Dimensioned: outer dia
    (Ø + tol), inner dia (Ø), the TYP angle between cuts.
  * SECTION D-D : the brace-plate cross-section (hatched) with the centre bump,
    R-rounded top corners. Dimensioned: plate thickness, bump height, total height.
  * DETAIL - A : the enlarged bump inside a scalloped cloud, toleranced dims — total
    length, bump width (horizontal) and total height, bump height (vertical) +
    clearance note.

Formulas (all data-driven from the battery + Tie Wire drawing):
  outer         = cathode diameter
  inner         = cathode diameter - 2 x radial_clearance (6 mm)
  angle         = 360 / number of tie wires
  plate width   = tie-wire width x 3 (small battery) / x 2 (large battery)
  plate thick   = 0.5 (small) / 1.0 (large)
  bump width    = tie-wire width + 2
  bump height   = tie-wire thickness x 4
  total height  = 2 x plate thickness + bump height
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, THICK, MED, THIN, C_LINE, C_HID, _n, line,
                        rect, circle, text, arrow, _header, _footer, _arc)
from .lid import _leader


@dataclass
class BracePlateParams:
    cathode_dia: float                       # outer = Brace Plate Dia
    radial_clearance: float = 6.0            # inner = cathode - 2 x this
    num_tie_wires: int = 3
    tie_wire_width: float = 3.0
    tie_wire_thickness: float = 0.3
    is_small: bool = True                    # small vs large battery
    plate_thickness: Optional[float] = None  # else 0.5 small / 1.0 large
    plate_width: Optional[float] = None      # BPw; else Ww x 3 / x 2
    bump_width: Optional[float] = None       # else Ww + 2
    bump_height: Optional[float] = None      # else Wt x 4
    bump_radius: float = 3.0                 # R on the bump top corners
    clearance_per_side: float = 0.30
    dia_tol: str = "+0.0/-0.2"
    len_tol: str = "±0.5"
    bw_tol: str = "±0.5"
    h_tol: str = "±0.25"
    bh_tol: str = "±0.2"
    component_name: str = "BRACE PLATE"
    material: str = "SS 304"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    quantity: str = "03"
    date: str = ""
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class BracePlateGeom:
    outer_dia: float
    inner_dia: float
    num_tie_wires: int
    angle: float
    plate_width: float
    plate_thickness: float
    bump_width: float
    bump_height: float
    total_height: float
    bump_radius: float
    tie_wire_thickness: float
    warnings: list = field(default_factory=list)


def compute_brace_plate(p: BracePlateParams) -> BracePlateGeom:
    w: list[str] = []
    outer = round(p.cathode_dia, 2)
    inner = round(p.cathode_dia - 2 * p.radial_clearance, 2)
    if inner <= 0:
        inner = round(outer * 0.6, 2)
        w.append("Inner circle <= 0 after clearance; assumed 0.6 x outer.")
    n = max(int(p.num_tie_wires or 3), 1)
    Ww, Wt = p.tie_wire_width, p.tie_wire_thickness
    t = p.plate_thickness if p.plate_thickness else (0.5 if p.is_small else 1.0)
    bpw = p.plate_width if p.plate_width else round(Ww * (3 if p.is_small else 2), 2)
    bw = p.bump_width if p.bump_width else round(Ww + 2.0, 2)
    bh = p.bump_height if p.bump_height else round(Wt * 4.0, 2)
    H = round(2 * t + bh, 2)
    return BracePlateGeom(outer_dia=outer, inner_dia=inner, num_tie_wires=n,
                          angle=round(360.0 / n, 2), plate_width=round(bpw, 2),
                          plate_thickness=round(t, 2), bump_width=round(bw, 2),
                          bump_height=round(bh, 2), total_height=H,
                          bump_radius=p.bump_radius, tie_wire_thickness=round(Wt, 3), warnings=w)


def _poly(pts, w=THICK, color="#111", dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<polyline points="{" ".join(f"{_n(x)},{_n(y)}" for x, y in pts)}" '
            f'fill="none" stroke="{color}" stroke-width="{w}"{d}/>')


def _solid_bump(cx, base, halfW, halfBW, tpx, bumprise, rpx):
    """Brace-plate cross-section: a flat plate (thickness tpx) with a formed bump
    (R-rounded top corners) rising bumprise above the plate top. Drawn as OUTER and
    INNER walls in solid lines (no hatching inside the bump).
    base = plate bottom surface y. Returns (svg_list, y-levels dict)."""
    yPlateTop = base - tpx
    yTop = base - tpx - bumprise
    r = max(min(rpx, halfBW * 0.55, bumprise * 0.5), 0.6)

    # OUTER surface (top): plate top -> bump wall -> rounded top -> wall -> plate top
    outer = [(cx - halfW, yPlateTop), (cx - halfBW, yPlateTop), (cx - halfBW, yTop + r)]
    outer += _arc(cx - halfBW + r, yTop + r, r, 180, 270, n=5)
    outer += [(cx + halfBW - r, yTop)]
    outer += _arc(cx + halfBW - r, yTop + r, r, 270, 360, n=5)
    outer += [(cx + halfBW, yTop + r), (cx + halfBW, yPlateTop), (cx + halfW, yPlateTop)]

    # INNER walls (bottom surface): inset by the sheet thickness
    hbi = max(halfBW - tpx, halfBW * 0.35)
    yti = yTop + tpx
    ri = max(min(r, hbi * 0.5), 0.5)
    inner = [(cx - halfW, base), (cx - hbi, base), (cx - hbi, yti + ri)]
    inner += _arc(cx - hbi + ri, yti + ri, ri, 180, 270, n=5)
    inner += [(cx + hbi - ri, yti)]
    inner += _arc(cx + hbi - ri, yti + ri, ri, 270, 360, n=5)
    inner += [(cx + hbi, yti + ri), (cx + hbi, base), (cx + halfW, base)]

    s = [_poly(outer, THICK), _poly(inner, THICK),
         line(cx - halfW, yPlateTop, cx - halfW, base, THICK),   # end caps
         line(cx + halfW, yPlateTop, cx + halfW, base, THICK)]
    y = dict(base=base, yPlateTop=yPlateTop, yTop=yTop, yTopInner=yti, r=r, hbi=hbi)
    return s, y


def _cloud(cx, cy, R, bumps=11):
    """Scalloped 'cloud' detail boundary."""
    amp = R * 0.16
    steps = bumps * 6
    pts = []
    for i in range(steps + 1):
        th = 2 * math.pi * i / steps
        rr = R + amp * (0.5 - 0.5 * math.cos(bumps * th))
        pts.append((cx + rr * math.cos(th), cy + rr * math.sin(th)))
    return _poly(pts, THIN)


def _dim_v_small(x, y1, y2, label, size=3.5, side="left"):
    s = [line(x, y1, x, y2, THIN), arrow(x, y1, 0, -1), arrow(x, y2, 0, 1)]
    tx = x - 1.2 if side == "left" else x + 1.2
    anc = "end" if side == "left" else "start"
    s.append(text(tx, (y1 + y2) / 2 + 0.7, label, size, anchor=anc))
    return s


def _dim_h_small(y, x1, x2, label, size=3.5, above=True):
    s = [line(x1, y, x2, y, THIN), arrow(x1, y, -1, 0), arrow(x2, y, 1, 0)]
    s.append(text((x1 + x2) / 2, y - 1.1 if above else y + 2.6, label, size))
    return s


# --------------------------------------------------------------------------- #
def _top_view(g: BracePlateGeom, p: BracePlateParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx, cy = ax0 + 78, ay0 + 54
    rO = 46.0
    sc = rO / (g.outer_dia / 2)
    rI = g.inner_dia / 2 * sc

    # centre lines + circles
    s.append(line(cx - rO - 8, cy, cx + rO + 8, cy, THIN, dash=C_LINE))
    s.append(line(cx, cy - rO - 8, cx, cy + rO + 8, THIN, dash=C_LINE))
    s.append(circle(cx, cy, rO, THICK))
    s.append(circle(cx, cy, rI, MED, dash=C_HID))

    n = g.num_tie_wires
    step = 360.0 / n
    a0 = -90.0
    detail_i = 1 % n                          # a lower position carries the detail
    Lp = g.plate_width * sc                   # tangential length = Brace Plate Dia
    Dp = g.bump_width * sc                     # radial depth = Bump Width
    for i in range(n):
        a = math.radians(a0 + i * step)
        ru = (math.cos(a), math.sin(a))
        tu = (-math.sin(a), math.cos(a))
        # radial tie-wire axis: centre -> inner dia
        s.append(line(cx, cy, cx + rI * ru[0], cy + rI * ru[1], THIN))
        # brace plate = rectangle: two parallel lines (Brace Plate Dia long); one
        # touches the inner circle, the rectangle (Bump Width deep) is toward centre.
        mx, my = cx + rI * ru[0], cy + rI * ru[1]           # tangent point on inner dia
        A = (mx + Lp / 2 * tu[0], my + Lp / 2 * tu[1])
        B = (mx - Lp / 2 * tu[0], my - Lp / 2 * tu[1])
        C = (B[0] - Dp * ru[0], B[1] - Dp * ru[1])
        D = (A[0] - Dp * ru[0], A[1] - Dp * ru[1])
        s.append(line(A[0], A[1], B[0], B[1], THICK))       # outer line (on inner dia)
        s.append(line(D[0], D[1], C[0], C[1], THICK))       # inner line (toward centre)
        s.append(line(A[0], A[1], D[0], D[1], THICK))       # end cap
        s.append(line(B[0], B[1], C[0], C[1], THICK))       # end cap

    # DETAIL-A bubble on the detailed plate
    ad = math.radians(a0 + detail_i * step)
    dr = rI - Dp * 0.5
    dcx = cx + dr * math.cos(ad)
    dcy = cy + dr * math.sin(ad)
    br = max(Lp / 2, Dp / 2) + 3
    s.append(circle(dcx, dcy, br, THIN, dash="2,1.2"))
    s.append(_leader(dcx + br * 0.7, dcy + br * 0.7, dcx + br + 12, dcy + br * 0.7 + 6, "DETAIL- A"))

    # D-D cutting plane — HORIZONTAL through the centre (D arrows left & right)
    yD = cy
    for sgn in (-1, 1):
        ex = cx + sgn * (rO + 7)
        bx = cx + sgn * (rO + 1)
        s.append(line(bx, yD, ex, yD, THIN))
        s.append(arrow(bx, yD, -sgn, 0))
        s.append(text(ex + sgn * 3, yD + 1, "D", 2.6, weight="bold"))

    # outer dia leader (Ø + tolerance, tolerance stacked clear of the value)
    ao = math.radians(-52)
    tx, ty = cx + rO + 12, cy - rO * 0.74
    s.append(_leader(cx + rO * math.cos(ao), cy + rO * math.sin(ao), tx, ty, f"Ø{_n(g.outer_dia)}"))
    tv = p.dia_tol.replace(" ", "").split("/")
    s.append(text(tx + 9, ty - 1.7, tv[0], 1.7, anchor="start"))
    s.append(text(tx + 9, ty + 1.6, tv[-1], 1.7, anchor="start"))
    # inner dia leader
    ai = math.radians(-70)
    s.append(_leader(cx + rI * math.cos(ai), cy + rI * math.sin(ai), tx, cy - rO * 0.30, f"Ø{_n(g.inner_dia)}"))

    # angle between two adjacent cuts (TYP) — kept inside the inward rectangles
    rA = max((rI - Dp) * 0.6, rI * 0.22)
    b0, b1 = a0, a0 + step
    for b in (b0, b1):
        s.append(line(cx, cy, cx + rA * 1.12 * math.cos(math.radians(b)),
                      cy + rA * 1.12 * math.sin(math.radians(b)), THIN, dash=C_LINE))
    arc = _arc(cx, cy, rA, b0, b1, n=10)
    s.append(_poly(arc, THIN))
    s.append(arrow(arc[0][0], arc[0][1], math.sin(math.radians(b0)), -math.cos(math.radians(b0))))
    s.append(arrow(arc[-1][0], arc[-1][1], -math.sin(math.radians(b1)), math.cos(math.radians(b1))))
    bm = math.radians((b0 + b1) / 2)
    s.append(text(cx + (rA + 6) * math.cos(bm), cy + (rA + 6) * math.sin(bm) + 1,
                  f"{_n(g.angle)}° (TYP)", 2.3, weight="bold"))
    return s


def _section_dd(g: BracePlateGeom, p: BracePlateParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    sc = 7.0
    cx = ax0 + 52
    base = ay0 + 116
    halfW = g.plate_width / 2 * sc
    halfBW = g.bump_width / 2 * sc
    tpx = max(g.plate_thickness * sc, 3.0)
    bumprise = max((g.bump_height + g.plate_thickness) * sc, 9.0)  # base->top = total height
    rpx = max(g.bump_radius * sc * 0.18, 2.0)
    bump, y = _solid_bump(cx, base, halfW, halfBW, tpx, bumprise, rpx)
    s += bump

    # plate thickness (left, at the flat)
    xt = cx - halfW - 6
    s.append(line(cx - halfW, y["yPlateTop"], xt - 2, y["yPlateTop"], THIN))
    s.append(line(cx - halfW, y["base"], xt - 2, y["base"], THIN))
    s += _dim_v_small(xt, y["yPlateTop"], y["base"], f"{_n(g.plate_thickness)}", side="left")
    # total height (further left): plate bottom -> bump top
    xH = cx - halfW - 16
    s.append(line(cx - halfW, y["base"], xH - 2, y["base"], THIN))
    s.append(line(cx - halfBW + y["r"], y["yTop"], xH - 2, y["yTop"], THIN))
    s += _dim_v_small(xH, y["yTop"], y["base"], f"{_n(g.total_height)}", side="left")
    # bump height (right): plate top -> bump top
    xb = cx + halfW + 8
    s.append(line(cx + halfW, y["yPlateTop"], xb + 2, y["yPlateTop"], THIN))
    s.append(line(cx + halfBW - y["r"], y["yTop"], xb + 2, y["yTop"], THIN))
    s += _dim_v_small(xb, y["yTop"], y["yPlateTop"], f"{_n(g.bump_height)}", side="right")
    # bump radius leader onto the rounded top corner
    s.append(_leader(cx - halfBW + y["r"] * 0.3, y["yTop"] + y["r"] * 0.3,
                     cx - halfBW - 7, y["yTop"] - 6, f"R{_n(g.bump_radius)}"))

    s.append(text(cx, base + 13, "SECTION D-D", 2.8, weight="bold"))
    return s


def _detail_a(g: BracePlateGeom, p: BracePlateParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    bx0, by0, bx1, by1 = ax1 - 100, ay0 + 96, ax1, ay1
    s.append(rect(bx0, by0, bx1 - bx0, by1 - by0, MED))
    s.append(text((bx0 + bx1) / 2, by0 + 6, "DETAIL- A", 2.6, weight="bold"))

    cx = (bx0 + bx1) / 2 - 2
    base = by1 - 26
    sc = min(6.5, ((bx1 - bx0) - 46) / max(g.plate_width, 0.1))
    halfW = g.plate_width / 2 * sc
    halfBW = g.bump_width / 2 * sc
    tpx = max(g.plate_thickness * sc, 3.0)
    bumprise = max((g.bump_height + g.plate_thickness) * sc, 9.0)
    rpx = max(g.bump_radius * sc * 0.18, 2.0)
    # scalloped cloud boundary behind the bump
    s.append(_cloud(cx, base - bumprise * 0.4, max(halfW, bumprise) + 5))
    bump, y = _solid_bump(cx, base, halfW, halfBW, tpx, bumprise, rpx)
    s += bump

    # total length (horizontal, above the crown)
    yTL = y["yTop"] - 8
    s.append(line(cx - halfW, y["yPlateTop"], cx - halfW, yTL - 2, THIN))
    s.append(line(cx + halfW, y["yPlateTop"], cx + halfW, yTL - 2, THIN))
    s += _dim_h_small(yTL, cx - halfW, cx + halfW, f"{_n(g.plate_width)} {p.len_tol}")
    # bump width (horizontal, just above crown)
    yBW = y["yTop"] - 3.2
    s += _dim_h_small(yBW, cx - halfBW, cx + halfBW, f"{_n(g.bump_width)} {p.bw_tol}")
    # total height (vertical, left): plate bottom -> bump top
    xH = cx - halfW - 9
    s.append(line(cx - halfW, y["base"], xH - 2, y["base"], THIN))
    s.append(line(cx - halfBW + y["r"], y["yTop"], xH - 2, y["yTop"], THIN))
    s += _dim_v_small(xH, y["yTop"], y["base"], f"{_n(g.total_height)} {p.h_tol}", side="left")
    # bump height (vertical, right): plate top -> bump top
    xb = cx + halfW + 9
    s.append(line(cx + halfW, y["yPlateTop"], xb + 2, y["yPlateTop"], THIN))
    s.append(line(cx + halfBW - y["r"], y["yTop"], xb + 2, y["yTop"], THIN))
    s += _dim_v_small(xb, y["yTop"], y["yPlateTop"], f"{_n(g.bump_height)} {p.bh_tol}", side="right")

    s.append(text((bx0 + bx1) / 2, by1 - 6, f"CLEARANCE AREA {_n(p.clearance_per_side)} mm", 2.0))
    s.append(text((bx0 + bx1) / 2, by1 - 3, "PER SIDE", 2.0))
    return s


def _views(g: BracePlateGeom, p: BracePlateParams) -> list[str]:
    return _top_view(g, p) + _section_dd(g, p) + _detail_a(g, p)


def render_brace_plate_svg(g: BracePlateGeom, p: BracePlateParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>']
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
