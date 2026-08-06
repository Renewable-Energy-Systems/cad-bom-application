"""Silicon Bonded Mica Disc (2 Cuts) CAD drawing — RES format.

A flat disc the size of the cathode, with radial slots cut in from the rim so
the squib heads can pass through. The cuts are equally spaced (two cuts => 180°
apart) and are sized from the SQUIB drawing:

    cut length = squib head length + clearance      (radially in from the rim)
    cut width  = squib head width  + clearance

Two views:
  * TOP VIEW  : the disc with its slots, dimensioned cut length and cut width
    (TYP, since the cuts are identical).
  * SIDE VIEW : the disc on edge — thickness (standard) and the disc diameter
    with its tolerance.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, THICK, MED, THIN, C_LINE, _n, line, rect,
                        circle, text, arrow, _header, _footer)

STD_THICKNESS = 1.0
DIA_TOL = "+0.00 / -0.20"


@dataclass
class MicaDiscCutsParams:
    disc_dia: float                       # = cathode diameter
    num_cuts: int = 2
    cut_length: float = 6.0               # radially in from the rim
    cut_width: float = 5.8
    thickness: float = STD_THICKNESS
    dia_tol: str = DIA_TOL
    cut_start_angle: float = 90.0         # first cut at 12 o'clock
    component_name: str = "SILICON BONDED MICA DISC (2 CUTS)"
    material: str = "SILICON BONDED MICA"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    quantity: str = "01"
    date: str = ""
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class MicaDiscCutsGeom:
    disc_dia: float
    num_cuts: int
    angle: float
    cut_length: float
    cut_width: float
    cut_gap: float               # derived: across the disc, far end to far end
    thickness: float
    cut_start_angle: float
    warnings: list = field(default_factory=list)


def compute_mica_disc_cuts(p: MicaDiscCutsParams) -> MicaDiscCutsGeom:
    w: list[str] = []
    n = max(int(p.num_cuts or 2), 1)
    r = p.disc_dia / 2
    cw = p.cut_width
    if cw >= p.disc_dia:
        cw = round(p.disc_dia * 0.3, 2)
        w.append("Cut width is wider than the disc; reduced to 30% of the diameter.")
    cl = p.cut_length
    if cl >= r:
        cl = round(r * 0.8, 2)
        w.append("Cut length reaches past the centre; limited to 80% of the radius.")
    gap = round(p.disc_dia - 2 * cl, 2)          # across the disc between the cuts
    if n == 2 and gap <= 0:
        w.append("The two cuts meet in the middle — no material left between them.")
    return MicaDiscCutsGeom(
        disc_dia=round(p.disc_dia, 2), num_cuts=n, angle=round(360.0 / n, 2),
        cut_length=round(cl, 2), cut_width=round(cw, 2), cut_gap=gap,
        thickness=round(p.thickness, 2),
        cut_start_angle=float(p.cut_start_angle), warnings=w)


def _dim_h(y, x1, x2, label, size=3.4, above=True):
    """Horizontal dimension. On a narrow span the arrows go OUTSIDE the extension
    lines pointing in at them — there is no room for them between."""
    if (x2 - x1) < size * 3.0:
        ext = 7.0
        s = [line(x1 - ext, y, x2 + ext, y, THIN),
             arrow(x1, y, 1, 0), arrow(x2, y, -1, 0)]
    else:
        s = [line(x1, y, x2, y, THIN), arrow(x1, y, -1, 0), arrow(x2, y, 1, 0)]
    s.append(text((x1 + x2) / 2, y - 1.6 if above else y + size + 0.4, label, size))
    return s


def _dim_v(x, y1, y2, label, size=3.4, side="right"):
    tx = x + 1.5 if side == "right" else x - 1.5
    return [line(x, y1, x, y2, THIN), arrow(x, y1, 0, -1), arrow(x, y2, 0, 1),
            text(tx, (y1 + y2) / 2, label, size, rot=90)]


def _disc_outline(cx, cy, r, hw, L, n, start_angle, step) -> str:
    """Disc boundary with a radial slot at each cut position.

    Each slot is a rectangle: `hw` half-width across, `L` in from the rim, so its
    mouth corners sit on the circle and its far end stops short of centre.
    Every argument is already in PAPER units — mixing them with millimetres
    would leave the drawn slot the same size whatever the dimensions say.
    """
    half_ang = math.degrees(math.asin(min(hw / r, 0.999)))
    d_mouth = math.sqrt(max(r * r - hw * hw, 0.0))     # axial depth of the mouth
    d_in = max(r - L, 0.5)                             # far end of the slot
    angles = [start_angle + i * step for i in range(n)]

    def P(ang_deg, rad):
        a = math.radians(ang_deg)
        return cx + rad * math.cos(a), cy - rad * math.sin(a)

    pts: list[tuple] = []
    for i, a in enumerate(angles):
        prev_ap = (angles[i - 1] + half_ang) if i else (angles[-1] + half_ang - 360.0)
        am = a - half_ang
        steps = max(int(abs(am - prev_ap) / 3.0), 6)
        for k in range(steps + 1):                     # rim between the slots
            pts.append(P(prev_ap + (am - prev_ap) * k / steps, r))
        ar = math.radians(a)
        u = (math.cos(ar), -math.sin(ar))              # radial, outward
        t = (-math.sin(ar), -math.cos(ar))             # tangential
        for d, s in ((d_in, -hw), (d_in, hw), (d_mouth, hw)):
            pts.append((cx + d * u[0] + s * t[0], cy + d * u[1] + s * t[1]))
    return ('<polygon points="' + " ".join(f"{_n(x)},{_n(y)}" for x, y in pts) +
            f'" fill="none" stroke="#111" stroke-width="{THICK}"/>')


def _views(g: MicaDiscCutsGeom, p: MicaDiscCutsParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = (ax0 + ax1) / 2

    sc = min(88.0 / max(g.disc_dia, 0.1), 2.6)
    r = g.disc_dia * sc / 2
    cy = ay0 + 14 + r
    hw = g.cut_width * sc / 2
    L = g.cut_length * sc

    # ---------------- TOP VIEW ----------------
    s.append(line(cx - r - 10, cy, cx + r + 10, cy, THIN, dash=C_LINE))
    s.append(line(cx, cy - r - 10, cx, cy + r + 12, THIN, dash=C_LINE))
    s.append(_disc_outline(cx, cy, r, hw, L, g.num_cuts, g.cut_start_angle, g.angle))

    # Distance between the two cuts — from the far end of one to the far end of
    # the other. The cut length itself is not dimensioned; this is what matters
    # for fitting the squibs, and it falls out of the cut length automatically.
    if g.num_cuts == 2 and g.cut_gap > 0:
        xL = cx + r + 16
        yA, yB = cy - r + L, cy + r - L
        s.append(line(cx + hw, yA, xL + 2, yA, THIN))
        s.append(line(cx + hw, yB, xL + 2, yB, THIN))
        s += _dim_v(xL, yA, yB, f"{_n(g.cut_gap)}")
    # cut width — TYP, taken on the 6 o'clock cut
    yW = cy + r + 14
    s.append(line(cx - hw, cy + r - L, cx - hw, yW + 2, THIN))
    s.append(line(cx + hw, cy + r - L, cx + hw, yW + 2, THIN))
    s += _dim_h(yW, cx - hw, cx + hw, f"{_n(g.cut_width)}  (TYP)")

    # ---------------- SIDE VIEW ----------------
    tp = max(g.thickness * sc, 2.0)
    sy = cy + r + 46
    s.append(rect(cx - r, sy, 2 * r, tp, MED))
    for sgn in (-1, 1):                       # the slots, seen on edge
        s.append(line(cx + sgn * hw, sy, cx + sgn * hw, sy + tp, THIN))
    s.append(line(cx, sy - 8, cx, sy + tp + 4, THIN, dash=C_LINE))
    xt = cx + r + 14
    s.append(line(cx + r, sy, xt + 2, sy, THIN))
    s.append(line(cx + r, sy + tp, xt + 2, sy + tp, THIN))
    s += _dim_v(xt, sy, sy + tp, f"{_n(g.thickness)}")
    s.append(text(xt + 8, (sy + sy + tp) / 2, "(STANDARD)", 2.6, rot=90))
    # disc diameter with its tolerance stacked above
    yD = sy + tp + 18
    s.append(line(cx - r, sy + tp, cx - r, yD + 2, THIN))
    s.append(line(cx + r, sy + tp, cx + r, yD + 2, THIN))
    s += _dim_h(yD, cx - r, cx + r, f"Ø{_n(g.disc_dia)}", 3.8)
    s.append(text(cx, yD - 6.2, p.dia_tol, 2.6))
    return s


def render_mica_disc_cuts_svg(g: MicaDiscCutsGeom, p: MicaDiscCutsParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>']
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
