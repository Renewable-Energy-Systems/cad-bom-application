"""Brace Plate CAD drawing (RES format).

Laid out like the reference sheet (RES-44-29):

  * TOP VIEW  : outer circle (Brace Plate Dia = cathode dia) + inner dashed circle
    (outer - 2 x 6 mm radial clearance). A crimping slot sits on the inner circle at
    each tie-wire position (360/N apart), drawn tangentially with the crimp inside
    it. One slot carries the DETAIL-A cloud; the horizontal D-D cutting plane runs
    across the part with both arrows pointing up. Dimensioned: outer dia (Ø + tol),
    inner dia (Ø), the TYP angle between slots.
  * SECTION D-D : the whole plate cut across, at the SAME width and scale as the top
    view — a thin hatched sliver with the crimp drawn as a formed arch on top of it.
    Heights are exaggerated so 0.5 mm sheet stays readable. Dimensioned (values read
    bottom-up, as on the reference): total height and plate thickness on the left,
    the clear height under the crimp on the right, R on the crimp shoulder.
  * DETAIL - A : the crimping slot enlarged inside a scalloped cloud, on the same
    diagonal it sits at in the top view. Toleranced: slot length and crimp length
    along it, slot width and crimp width across it, plus the clearance note.

Formulas (all data-driven from the battery + Tie Wire drawing):
  outer         = cathode diameter
  inner         = cathode diameter - 2 x radial_clearance (6 mm)
  angle         = 360 / number of tie wires
  plate width   = tie-wire width x 3 (small battery) / x 2 (large battery)
  plate thick   = 0.5 (small) / 1.0 (large)
  bump width    = tie-wire width + 2
  bump height   = tie-wire thickness x 4      (the CLEAR gap under the crimp)
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
    # Sheet notes, printed bottom-left exactly as on the reference drawing.
    visual_criteria: Optional[list] = None   # else the reference wording
    finish: Optional[str] = None             # else the reference wording
    dia_tol: str = "+0.0/-0.2"
    len_tol: str = "±0.5"
    bw_tol: str = "±0.5"
    h_tol: str = "±0.25"
    bh_tol: str = "±0.2"
    component_name: str = "BRACE PLATE"
    material: str = "MS"                     # zinc plated, per the reference sheet
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


# ---- sheet layout (paper mm, shared by the top view and the section) ------- #
_RO = 27.0          # top-view outer radius
_CX_OFF = 70.0      # top-view / section centre, right of the drawing-area left edge
_CY_OFF = 34.0      # top-view centre, below the drawing-area top
_BASE_OFF = 102.0   # section: bottom face of the plate, below the drawing-area top
_SECT_H = 5.5       # section: drawn height of the whole formed section
_DET_W = 80.0       # DETAIL-A box, width and height
_DET_H = 56.0

DEFAULT_VISUAL = ["PUNCHING EDGE CUTS AND BURRS ARE NOT ALLOWED",
                  "& SMOOTH FINISHING AT CRIMPING SLOTS"]
DEFAULT_FINISH = "ZINC PLATING 12.5 MICRONS MIN."


def _poly(pts, w=THICK, color="#111", dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<polyline points="{" ".join(f"{_n(x)},{_n(y)}" for x, y in pts)}" '
            f'fill="none" stroke="{color}" stroke-width="{w}"{d}/>')


def _hatch_band(x0, x1, ytop, ybot, step=1.1):
    """45° section hatch inside a thin horizontal band, clipped to it.

    The band is only a millimetre or two deep, so the lines are generated and
    trimmed directly rather than going through an SVG pattern — pattern fills do
    not survive the SVG -> PDF export.
    """
    out = []
    h = ybot - ytop
    if h <= 0 or x1 <= x0:
        return out
    x = x0 - h
    while x <= x1:
        xa, ya, xb, yb = x, ybot, x + h, ytop     # 45°, up to the right
        if xb >= x0 and xa <= x1:
            if xa < x0:
                ya, xa = ybot - (x0 - xa), x0
            if xb > x1:
                yb, xb = ytop + (xb - x1), x1
            out.append(line(xa, ya, xb, yb, THIN))
        x += step
    return out


def _dim_v_rot(x, y1, y2, label, size=2.8, ext=3.6):
    """Vertical dimension whose value reads bottom-up, sitting above the top
    arrow — the way the reference sheet dimensions the section. The spans here
    are fractions of a millimetre, so the arrows go outside and point in."""
    return [line(x, y1 - ext, x, y2 + ext, THIN),
            arrow(x, y1, 0, -1), arrow(x, y2, 0, 1),
            text(x + 1.0, y1 - ext - 1.0, label, size, anchor="start", rot=-90)]


def _crimp_arch(cx, yPlateTop, halfBW, tpx, clear, rpx):
    """The crimp seen in SECTION D-D: a formed arch standing on the plate's top
    face, drawn as an outer and an inner profile (it is thin sheet, so the two
    are one sheet-thickness apart). Nothing is hatched inside it — on the
    reference sheet the cutting plane misses the slot, so the arch is an outline
    seen beyond the plane while the plate itself is the cut face.

    clear = the free height under the arch (the gap the tie wire passes through).
    Returns (svg parts, y-levels dict).
    """
    yInner = yPlateTop - clear              # underside of the arch crown
    yOuter = yInner - tpx                   # top of the arch crown
    ri = max(min(rpx, halfBW * 0.55, clear * 0.85), 0.35)
    ro = ri + tpx

    outer = [(cx - halfBW, yPlateTop), (cx - halfBW, yOuter + ro)]
    outer += _arc(cx - halfBW + ro, yOuter + ro, ro, 180, 270, n=6)
    outer += [(cx + halfBW - ro, yOuter)]
    outer += _arc(cx + halfBW - ro, yOuter + ro, ro, 270, 360, n=6)
    outer += [(cx + halfBW, yOuter + ro), (cx + halfBW, yPlateTop)]

    hbi = halfBW - tpx
    inner = [(cx - hbi, yPlateTop), (cx - hbi, yInner + ri)]
    inner += _arc(cx - hbi + ri, yInner + ri, ri, 180, 270, n=6)
    inner += [(cx + hbi - ri, yInner)]
    inner += _arc(cx + hbi - ri, yInner + ri, ri, 270, 360, n=6)
    inner += [(cx + hbi, yInner + ri), (cx + hbi, yPlateTop)]

    s = [_poly(outer, MED), _poly(inner, MED)]
    return s, dict(yInner=yInner, yOuter=yOuter, hbi=hbi, ro=ro)


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
    rO = _RO
    cx = ax0 + _CX_OFF
    cy = ay0 + _CY_OFF
    sc = rO / (g.outer_dia / 2)
    rI = g.inner_dia / 2 * sc

    # centre lines + circles
    s.append(line(cx - rO - 16, cy, cx + rO + 16, cy, THIN, dash=C_LINE))
    s.append(line(cx, cy - rO - 10, cx, cy + rO + 10, THIN, dash=C_LINE))
    s.append(circle(cx, cy, rO, THICK))
    s.append(circle(cx, cy, rI, MED, dash=C_HID))

    n = g.num_tie_wires
    step = 360.0 / n
    a0 = 90.0                                  # first slot at 12 o'clock
    L = g.plate_width * sc                     # along the circle
    W = g.strip_width * sc                     # across the strip
    bl = g.bump_width * sc                     # crimp along
    bw = g.bump_plan_width * sc                # crimp across
    for i in range(n):
        s += _plate_plan(cx, cy, a0 + i * step, rI, L, W, bl, bw)

    # DETAIL-A cloud around the lower-right slot (as on the reference sheet)
    ad = math.radians(a0 + (2 % n) * step)
    dcx, dcy = cx + rI * math.cos(ad), cy - rI * math.sin(ad)
    dr = max(L, W) / 2 + 3.5
    s.append(_cloud(dcx, dcy, dr, bumps=9))
    s.append(_leader(dcx + dr * 0.80, dcy - dr * 0.22, cx + rO + 14, dcy - dr * 0.55, "DETAIL- A", size=2.8))

    # D-D cutting plane on the horizontal centre line — arrows point UP, the
    # letter beside each arrow line (outboard) the way the reference has it
    for sgn in (-1, 1):
        xD = cx + sgn * (rO + 9)
        s.append(line(xD, cy, xD, cy + 15, THIN))
        s.append(arrow(xD, cy, 0, -1))
        s.append(text(xD + sgn * 3.2, cy + 13, "D", 3.0, weight="bold"))

    # outer / inner diameter leaders, stacked at the upper right
    tx = cx + rO + 12
    ty = cy - rO * 0.72
    ao = math.radians(52)
    s.append(_leader(cx + rO * math.cos(ao), cy - rO * math.sin(ao), tx, ty, f"Ø{_n(g.outer_dia)}"))
    tv = [t for t in p.dia_tol.replace(" ", "").split("/") if t]
    s.append(text(tx + 2, ty - 7.2, tv[0], 2.1, anchor="start"))
    s.append(text(tx + 2, ty - 3.8, tv[-1], 2.1, anchor="start"))
    ai = math.radians(38)
    s.append(_leader(cx + rI * math.cos(ai), cy - rI * math.sin(ai), tx, ty + 7, f"Ø{_n(g.inner_dia)}"))

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
    """The whole plate cut across on D-D, drawn at the top view's width and scale.

    The plate itself is the cut face, so it is hatched; the crimp is an outline
    seen beyond the cutting plane, so it is not. Heights use their own (much
    larger) scale — at true scale 0.5 mm of sheet on a 37 mm disc is a hairline.
    """
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = ax0 + _CX_OFF
    base = ay0 + _BASE_OFF
    hs = _RO / (g.outer_dia / 2)                         # same as the top view
    vs = _SECT_H / max(g.total_height, 0.1)              # heights, exaggerated

    halfW = g.outer_dia / 2 * hs                         # the section is the disc
    halfBW = max(g.plate_width / 2 * hs, 3.0)            # crimp, over the slot
    tpx = g.plate_thickness * vs
    clear = g.bump_height * vs
    yTop = base - tpx                                    # plate top face

    # the cut plate: a thin hatched band right across the disc
    s.append(rect(cx - halfW, yTop, 2 * halfW, tpx, MED))
    s += _hatch_band(cx - halfW, cx + halfW, yTop, base)

    arch, y = _crimp_arch(cx, yTop, halfBW, tpx, clear, g.bump_radius * vs * 0.5)
    s += arch
    # centre line through the crimp
    s.append(line(cx, y["yOuter"] - 9, cx, base + 6, THIN, dash=C_LINE))

    # ---- dimensions ------------------------------------------------------- #
    xH = cx - halfW - 16                                 # total height, far left
    xt = cx - halfW - 7                                  # plate thickness, inside it
    xb = cx + halfW + 9                                  # clear height, right
    # extension lines: crown level runs the full width, the two plate faces
    # reach out to whichever dimension needs them
    s.append(line(xH - 2, y["yOuter"], xb + 2, y["yOuter"], THIN))
    s.append(line(xH - 2, base, cx - halfW, base, THIN))
    s.append(line(xt - 2, yTop, cx - halfW, yTop, THIN))
    s.append(line(cx + halfW, base, xb + 2, base, THIN))
    s.append(line(cx + halfW, yTop, xb + 2, yTop, THIN))
    s.append(line(cx + y["hbi"] - y["ro"], y["yInner"], xb + 2, y["yInner"], THIN))

    s += _dim_v_rot(xH, y["yOuter"], base, _n(g.total_height))
    s += _dim_v_rot(xt, yTop, base, _n(g.plate_thickness))
    # the right-hand figure is the CLEAR height under the crimp — the gap the tie
    # wire passes through — measured from the plate top to the arch's underside
    s += _dim_v_rot(xb, y["yInner"], yTop, _n(g.bump_height))

    # R on the crimp shoulder, leader down to the right as on the reference
    s.append(_leader(cx + halfBW * 0.62, yTop - 0.6,
                     cx + halfBW * 0.62 + 5, base + 8, f"R{_n(g.bump_radius)}", size=2.8))
    s.append(text(cx, base + 15, "SECTION D-D", 3.0, weight="bold"))
    return s


def _sheet_notes(g: BracePlateGeom, p: BracePlateParams) -> list[str]:
    """VISUAL CRITERIA / FINISH block, bottom-left, as on the reference sheet."""
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    vc = p.visual_criteria if p.visual_criteria else DEFAULT_VISUAL
    x, xv = ax0 + 3, ax0 + 33
    y = ay1 - 26
    s.append(text(x, y, "VISUAL CRITERIA :", 2.6, anchor="start"))
    for i, ln in enumerate(vc):
        s.append(text(xv, y + i * 3.4, ln, 2.6, anchor="start"))
    y2 = y + max(len(vc), 1) * 3.4 + 1.4
    s.append(text(x, y2, "FINISH :", 2.6, anchor="start"))
    s.append(text(xv, y2, p.finish if p.finish else DEFAULT_FINISH, 2.6, anchor="start"))
    return s


def _detail_a(g: BracePlateGeom, p: BracePlateParams) -> list[str]:
    """Enlarged PLAN of one brace plate inside the scalloped clearance cloud,
    laid on the diagonal as on the reference sheet: the strip (length x width)
    with the bump inside it, all four sizes toleranced."""
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    bx0, by0, bx1, by1 = ax1 - _DET_W, ay1 - 1 - _DET_H, ax1, ay1 - 1
    s.append(rect(bx0, by0, bx1 - bx0, by1 - by0, MED))
    s.append(text((bx0 + bx1) / 2, by0 + 7, "DETAIL- A", 3.0, weight="bold"))

    cx, cy = (bx0 + bx1) / 2 - 3, (by0 + by1) / 2 + 2
    # The slot is shown on the diagonal it actually sits at in the top view (the
    # lower-right position, so its long axis runs up to the right at 60°). Tilted
    # that far it is mostly TALL, so the box height is what limits the scale.
    rot = 60.0
    L = min(20.0, max((by1 - by0 - 30) / 0.494, 8.0))
    sc = L / max(g.plate_width, 0.1)
    W = max(g.strip_width * sc, 2.2)
    bl = g.bump_width * sc
    bw = max(g.bump_plan_width * sc, 1.5)

    s.append(_cloud(cx, cy, max(L, W) * 0.42 + 3.0, bumps=11))

    # everything below is drawn axis-aligned, then rotated onto the diagonal
    d: list[str] = []
    d.append(_poly([(cx - L / 2, cy - W / 2), (cx + L / 2, cy - W / 2),
                    (cx + L / 2, cy + W / 2), (cx - L / 2, cy + W / 2),
                    (cx - L / 2, cy - W / 2)], MED))
    d.append(_poly([(cx - bl / 2, cy - bw / 2), (cx + bl / 2, cy - bw / 2),
                    (cx + bl / 2, cy + bw / 2), (cx - bl / 2, cy + bw / 2),
                    (cx - bl / 2, cy - bw / 2)], THIN))
    # lengths ALONG the strip — stacked off one long side, so after the rotation
    # they end up on the lower-left of the slot exactly as on the reference
    y1 = cy - W / 2 - 4.4
    y2 = cy - W / 2 - 1.5
    d.append(line(cx - L / 2, cy - W / 2, cx - L / 2, y1 - 1.5, THIN))
    d.append(line(cx + L / 2, cy - W / 2, cx + L / 2, y1 - 1.5, THIN))
    d += _dim_h_small(y1, cx - L / 2, cx + L / 2, f"{_n(g.plate_width)}{p.len_tol}", size=2.3)
    d += _dim_h_small(y2, cx - bl / 2, cx + bl / 2, f"{_n(g.bump_width)}{p.bw_tol}", size=2.3)
    # widths ACROSS the strip — stacked beyond the far end, landing on the upper
    # right after the rotation
    x1 = cx + L / 2 + 5.0
    d.append(line(cx + L / 2, cy - W / 2, x1 + 1.5, cy - W / 2, THIN))
    d.append(line(cx + L / 2, cy + W / 2, x1 + 1.5, cy + W / 2, THIN))
    d += _dim_v_small(x1, cy - W / 2, cy + W / 2, f"{_n(g.strip_width)}{p.h_tol}",
                      size=2.3, side="right", tdy=-2.6)
    x2 = cx + L / 2 + 1.6
    d.append(line(cx + bl / 2, cy - bw / 2, x2 + 1.5, cy - bw / 2, THIN))
    d.append(line(cx + bl / 2, cy + bw / 2, x2 + 1.5, cy + bw / 2, THIN))
    d += _dim_v_small(x2, cy - bw / 2, cy + bw / 2, f"{_n(g.bump_plan_width)}{p.bh_tol}",
                      size=2.3, side="right", tdy=4.4)
    s.append(f'<g transform="rotate({_n(-rot)} {_n(cx)} {_n(cy)})">' + "".join(d) + "</g>")

    # clearance note, with the leader running up to the cloud as on the reference
    ncy = by1 - 6.6
    s.append(line(bx0 + 40, ncy - 1.0, bx1 - 2.5, by1 - 17, THIN))
    s.append(text(bx0 + 3, ncy, f"CLEARANCE AREA {_n(p.clearance_per_side)} mm",
                  2.4, anchor="start"))
    s.append(text(bx0 + 3, ncy + 3.3, "PER SIDE", 2.4, anchor="start"))
    return s


def _views(g: BracePlateGeom, p: BracePlateParams) -> list[str]:
    return (_top_view(g, p) + _section_dd(g, p) + _sheet_notes(g, p)
            + _detail_a(g, p))


def render_brace_plate_svg(g: BracePlateGeom, p: BracePlateParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>']
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
