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
    # Plan-view widths (across the strip). The reference sheet dimensions these
    # in DETAIL-A as 2.1 and 1.5 for a 3 mm tie wire; both are editable.
    strip_width: Optional[float] = None      # across the plate; else total height
    bump_plan_width: Optional[float] = None  # across the bump;  else Ww / 2
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
    strip_width: float = 0.0
    bump_plan_width: float = 0.0
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
    sw = p.strip_width if p.strip_width else H              # across the plate
    bpl = p.bump_plan_width if p.bump_plan_width else round(Ww / 2.0, 2)
    if bpl >= sw:
        bpl = round(sw * 0.7, 2)
        w.append("Bump plan width was wider than the plate; reduced to fit.")
    return BracePlateGeom(outer_dia=outer, inner_dia=inner, num_tie_wires=n,
                          angle=round(360.0 / n, 2), plate_width=round(bpw, 2),
                          plate_thickness=round(t, 2), bump_width=round(bw, 2),
                          bump_height=round(bh, 2), total_height=H,
                          bump_radius=p.bump_radius, tie_wire_thickness=round(Wt, 3),
                          strip_width=round(sw, 2), bump_plan_width=round(bpl, 2), warnings=w)


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


def _dim_v_small(x, y1, y2, label, size=3.5, side="left", tdy=0.0):
    """Vertical dimension. `tdy` slides the label along the line so two dims on
    the same side can sit close together without their text colliding."""
    s = [line(x, y1, x, y2, THIN), arrow(x, y1, 0, -1), arrow(x, y2, 0, 1)]
    tx = x - 1.2 if side == "left" else x + 1.2
    anc = "end" if side == "left" else "start"
    s.append(text(tx, (y1 + y2) / 2 + 0.7 + tdy, label, size, anchor=anc))
    return s


def _dim_h_small(y, x1, x2, label, size=3.5, above=True):
    s = [line(x1, y, x2, y, THIN), arrow(x1, y, -1, 0), arrow(x2, y, 1, 0)]
    s.append(text((x1 + x2) / 2, y - 1.1 if above else y + 2.6, label, size))
    return s


# --------------------------------------------------------------------------- #
def _plate_plan(cx, cy, ang_deg, rI, L, W, bl, bw) -> list[str]:
    """One brace plate seen from above: a thin strip (L along the circle x W across)
    straddling the inner diameter, with the formed bump drawn inside it."""
    a = math.radians(ang_deg)
    ru = (math.cos(a), -math.sin(a))           # outward radial (screen y is down)
    tu = (-math.sin(a), -math.cos(a))          # tangential
    mx, my = cx + rI * ru[0], cy + rI * ru[1]

    def box(halfL, halfW, w):
        pts = [(mx + halfL * tu[0] + halfW * ru[0], my + halfL * tu[1] + halfW * ru[1]),
               (mx - halfL * tu[0] + halfW * ru[0], my - halfL * tu[1] + halfW * ru[1]),
               (mx - halfL * tu[0] - halfW * ru[0], my - halfL * tu[1] - halfW * ru[1]),
               (mx + halfL * tu[0] - halfW * ru[0], my + halfL * tu[1] - halfW * ru[1])]
        return [_poly(pts + [pts[0]], w)]

    return box(L / 2, W / 2, MED) + box(bl / 2, bw / 2, THIN)


def _top_view(g: BracePlateGeom, p: BracePlateParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    rO = 34.0
    cx = ax0 + (ax1 - ax0) * 0.40
    cy = ay0 + rO + 12
    sc = rO / (g.outer_dia / 2)
    rI = g.inner_dia / 2 * sc

    # centre lines + circles
    s.append(line(cx - rO - 12, cy, cx + rO + 12, cy, THIN, dash=C_LINE))
    s.append(line(cx, cy - rO - 12, cx, cy + rO + 12, THIN, dash=C_LINE))
    s.append(circle(cx, cy, rO, THICK))
    s.append(circle(cx, cy, rI, MED, dash=C_HID))

    n = g.num_tie_wires
    step = 360.0 / n
    a0 = 90.0                                  # first plate at 12 o'clock
    L = g.plate_width * sc                     # along the circle
    W = g.strip_width * sc                     # across the strip
    bl = g.bump_width * sc                     # bump along
    bw = g.bump_plan_width * sc                # bump across
    for i in range(n):
        s += _plate_plan(cx, cy, a0 + i * step, rI, L, W, bl, bw)

    # DETAIL-A cloud around the lower-right plate (as on the reference sheet)
    ad = math.radians(a0 + (2 % n) * step)
    dcx, dcy = cx + rI * math.cos(ad), cy - rI * math.sin(ad)
    dr = max(L, W) / 2 + 4
    s.append(_cloud(dcx, dcy, dr, bumps=9))
    s.append(_leader(dcx + dr * 0.72, dcy - dr * 0.30, cx + rO + 15, dcy - dr * 0.30, "DETAIL- A"))

    # D-D cutting plane on the horizontal centre line — arrows point UP
    for sgn in (-1, 1):
        xD = cx + sgn * (rO + 6)
        s.append(line(xD, cy, xD, cy + 9, THIN))
        s.append(arrow(xD, cy, 0, -1))
        s.append(text(xD, cy + 13, "D", 2.8, weight="bold"))

    # outer / inner diameter leaders, stacked at the upper right
    tx = cx + rO + 10
    ty = cy - rO * 0.80
    ao = math.radians(38)
    s.append(_leader(cx + rO * math.cos(ao), cy - rO * math.sin(ao), tx, ty, f"Ø{_n(g.outer_dia)}"))
    tv = [t for t in p.dia_tol.replace(" ", "").split("/") if t]
    s.append(text(tx + 2, ty - 7.2, tv[0], 2.1, anchor="start"))
    s.append(text(tx + 2, ty - 3.8, tv[-1], 2.1, anchor="start"))
    ai = math.radians(20)
    s.append(_leader(cx + rI * math.cos(ai), cy - rI * math.sin(ai), tx, ty + 8, f"Ø{_n(g.inner_dia)}"))

    # angle between adjacent plates (TYP) — arc swept BELOW the part
    rA = rO + 8
    b0, b1 = a0 + step, a0 + 2 * step          # the two lower positions
    for b in (b0, b1):
        br = math.radians(b)
        s.append(line(cx, cy, cx + rA * math.cos(br), cy - rA * math.sin(br), THIN))
    arc = [(cx + rA * math.cos(math.radians(b0 + (b1 - b0) * k / 16)),
            cy - rA * math.sin(math.radians(b0 + (b1 - b0) * k / 16))) for k in range(17)]
    s.append(_poly(arc, THIN))
    s.append(arrow(arc[0][0], arc[0][1], -math.sin(math.radians(b0)), -math.cos(math.radians(b0))))
    s.append(arrow(arc[-1][0], arc[-1][1], math.sin(math.radians(b1)), math.cos(math.radians(b1))))
    s.append(text(cx, cy + rA + 6, f"{_n(g.angle)}° (TYP)", 2.8, weight="bold"))
    return s


def _section_dd(g: BracePlateGeom, p: BracePlateParams) -> list[str]:
    """Formed-sheet cross-section: wide and flat, with the raised centre bump.

    Horizontal and vertical scales differ (as on the reference sheet) — at true
    scale a 9 x 2.1 strip would be an unreadable sliver.
    """
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    hs = 60.0 / max(g.plate_width, 0.1)                  # along the strip
    vs = 11.0 / max(g.total_height, 0.1)                 # exaggerated height
    vs = max(vs, 1.5 / max(g.plate_thickness, 0.1))      # keep the sheet visible
    cx = ax0 + 52
    base = ay0 + 116
    halfW = g.plate_width / 2 * hs
    halfBW = g.bump_width / 2 * hs
    tpx = g.plate_thickness * vs
    bumprise = (g.bump_height + g.plate_thickness) * vs  # base -> outer top = total
    rpx = max(g.bump_radius * vs * 0.25, 1.4)
    bump, y = _solid_bump(cx, base, halfW, halfBW, tpx, bumprise, rpx)
    s += bump

    # total height (far left): plate bottom -> bump outer top
    xH = cx - halfW - 15
    s.append(line(cx - halfW, y["base"], xH - 2, y["base"], THIN))
    s.append(line(cx - halfBW + y["r"], y["yTop"], xH - 2, y["yTop"], THIN))
    s += _dim_v_small(xH, y["yTop"], y["base"], f"{_n(g.total_height)}", side="left")
    # plate thickness (just inside it)
    xt = cx - halfW - 5
    s.append(line(cx - halfW, y["yPlateTop"], xt - 2, y["yPlateTop"], THIN))
    s += _dim_v_small(xt, y["yPlateTop"], y["base"], f"{_n(g.plate_thickness)}", side="left")
    # bump height (right) — the CLEAR height under the bump, i.e. plate top to the
    # bump's inner surface. That is the gap the tie wire passes through.
    xb = cx + halfW + 9
    s.append(line(cx + halfW, y["yPlateTop"], xb + 2, y["yPlateTop"], THIN))
    s.append(line(cx + y["hbi"] - 1, y["yTopInner"], xb + 2, y["yTopInner"], THIN))
    s += _dim_v_small(xb, y["yTopInner"], y["yPlateTop"], f"{_n(g.bump_height)}", side="right")
    # bump radius leader onto the rounded shoulder, from below-left
    s.append(_leader(cx - halfBW + y["r"] * 0.4, y["yTop"] + y["r"] * 0.5,
                     cx - halfBW * 0.4, base + 6, f"R{_n(g.bump_radius)}"))

    s.append(text(cx, base + 15, "SECTION D-D", 2.8, weight="bold"))
    return s


def _detail_a(g: BracePlateGeom, p: BracePlateParams) -> list[str]:
    """Enlarged PLAN of one brace plate inside the scalloped clearance cloud,
    laid on the diagonal as on the reference sheet: the strip (length x width)
    with the bump inside it, all four sizes toleranced."""
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    bx0, by0, bx1, by1 = ax1 - 92, ay0 + 100, ax1, ay1 - 2
    s.append(rect(bx0, by0, bx1 - bx0, by1 - by0, MED))
    s.append(text((bx0 + bx1) / 2, by0 + 7, "DETAIL- A", 2.8, weight="bold"))

    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2 + 2
    # rotated 45°, the strip spans L/sqrt(2) each way, so keep it well inside the box
    room = min(bx1 - bx0, by1 - by0) - 26
    sc = min(4.6, (room * 1.414) / max(g.plate_width, 0.1))
    L = g.plate_width * sc
    W = max(g.strip_width * sc, 4.0)
    bl = g.bump_width * sc
    bw = max(g.bump_plan_width * sc, 2.4)

    s.append(_cloud(cx, cy, max(L, W) * 0.42 + 4, bumps=11))

    # everything below is drawn axis-aligned, then rotated onto the diagonal
    d: list[str] = []
    d.append(_poly([(cx - L / 2, cy - W / 2), (cx + L / 2, cy - W / 2),
                    (cx + L / 2, cy + W / 2), (cx - L / 2, cy + W / 2),
                    (cx - L / 2, cy - W / 2)], MED))
    d.append(_poly([(cx - bl / 2, cy - bw / 2), (cx + bl / 2, cy - bw / 2),
                    (cx + bl / 2, cy + bw / 2), (cx - bl / 2, cy + bw / 2),
                    (cx - bl / 2, cy - bw / 2)], THIN))
    # lengths along the strip (left of it)
    y1 = cy - W / 2 - 5
    d.append(line(cx - L / 2, cy - W / 2, cx - L / 2, y1 - 2, THIN))
    d.append(line(cx + L / 2, cy - W / 2, cx + L / 2, y1 - 2, THIN))
    d += _dim_h_small(y1, cx - L / 2, cx + L / 2, f"{_n(g.plate_width)} {p.len_tol}", size=2.4)
    y2 = cy - W / 2 - 1.6
    d += _dim_h_small(y2, cx - bl / 2, cx + bl / 2, f"{_n(g.bump_width)} {p.bw_tol}", size=2.4)
    # widths across the strip — both beyond the far end as on the reference, the
    # plate outboard of the bump and their labels slid apart so they stay clear
    x1 = cx + L / 2 + 8
    d.append(line(cx + L / 2, cy - W / 2, x1 + 2, cy - W / 2, THIN))
    d.append(line(cx + L / 2, cy + W / 2, x1 + 2, cy + W / 2, THIN))
    d += _dim_v_small(x1, cy - W / 2, cy + W / 2, f"{_n(g.strip_width)} {p.h_tol}",
                      size=2.4, side="right", tdy=-3.0)
    x2 = cx + L / 2 + 2.5
    d.append(line(cx + bl / 2, cy - bw / 2, x2 + 2, cy - bw / 2, THIN))
    d.append(line(cx + bl / 2, cy + bw / 2, x2 + 2, cy + bw / 2, THIN))
    d += _dim_v_small(x2, cy - bw / 2, cy + bw / 2, f"{_n(g.bump_plan_width)} {p.bh_tol}",
                      size=2.4, side="right", tdy=5.0)
    s.append(f'<g transform="rotate(-45 {_n(cx)} {_n(cy)})">' + "".join(d) + "</g>")

    s.append(text(bx0 + 3, by1 - 6, f"CLEARANCE AREA {_n(p.clearance_per_side)} mm",
                  2.2, anchor="start"))
    s.append(text(bx0 + 3, by1 - 2.6, "PER SIDE", 2.2, anchor="start"))
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
