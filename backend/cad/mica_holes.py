"""Mica Disc (with holes) CAD drawing — RES format.

A flat circular disc (dia = stack diameter, thk = 0.15) carrying a ring of
holes on a PCD, each labelled "B", exactly like the reference:
  * TOP view: OD circle + PCD + holes (B) + centre lines through the holes,
    angle dimensions between adjacent holes (arc + arrows), and a
    "B = Ø<hole> ON PCD <pcd>" leader.
  * SECTION Y-Y: thin bar with the hole positions ticked, Ø (with tolerance)
    and thickness (with tolerance).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, THICK, MED, THIN, C_LINE, C_HID, _n, line,
                        rect, circle, text, arrow, _hatch_defs, _header, _footer)
from .lid import _leader

DIA_TOL = "+0.0/-0.2"
THK_TOL = "±0.05"
MICA_THK = 0.15


@dataclass
class MicaHolesParams:
    dia: float                     # = stack (cathode) diameter
    pcd: float
    num_holes: int
    hole_dia: float
    thickness: float = MICA_THK
    hole_start_angle: float = 90.0
    hole_angles: Optional[list] = None
    dia_tol: str = DIA_TOL
    thk_tol: str = THK_TOL
    component_name: str = "MICA DISC"
    material: str = "MICA"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    quantity: str = "01"
    date: str = ""
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class MicaHolesGeom:
    dia: float
    thickness: float
    pcd: float
    num_holes: int
    theta: float
    hole_dia: float
    hole_start_angle: float
    dia_tol: str
    thk_tol: str
    warnings: list = field(default_factory=list)


def compute_mica_holes(p: MicaHolesParams) -> MicaHolesGeom:
    w: list[str] = []
    n = int(p.num_holes) if p.num_holes else 6
    if not p.num_holes:
        w.append("Number of holes not found; assumed 6.")
    return MicaHolesGeom(dia=round(p.dia, 2), thickness=round(p.thickness, 2),
                         pcd=round(p.pcd, 2), num_holes=n, theta=round(360.0 / n, 2),
                         hole_dia=round(p.hole_dia, 2),
                         hole_start_angle=p.hole_start_angle if p.hole_start_angle is not None else 90.0,
                         dia_tol=p.dia_tol or DIA_TOL, thk_tol=p.thk_tol or THK_TOL, warnings=w)


def _polyline(pts, w=THIN):
    return ('<polyline points="' + " ".join(f"{_n(x)},{_n(y)}" for x, y in pts) +
            f'" fill="none" stroke="#111" stroke-width="{w}"/>')


def _arc_dim(cx, cy, R, a0, a1, label):
    """Angle dimension: an arc from a0..a1 with an arrowhead at each end and the
    angle value just outside the mid-point. (No radial lines — the dash-dot
    centre lines through the holes serve as the extension lines.)"""
    out = []
    steps = max(4, int(abs(a1 - a0) / 5))
    pts = [(cx + R * math.cos(math.radians(a0 + (a1 - a0) * k / steps)),
            cy - R * math.sin(math.radians(a0 + (a1 - a0) * k / steps))) for k in range(steps + 1)]
    out.append(_polyline(pts, THIN))
    a0r, a1r = math.radians(a0), math.radians(a1)
    # arrowheads point along the arc, outward from the span
    out.append(arrow(cx + R * math.cos(a0r), cy - R * math.sin(a0r), math.sin(a0r), math.cos(a0r)))
    out.append(arrow(cx + R * math.cos(a1r), cy - R * math.sin(a1r), -math.sin(a1r), -math.cos(a1r)))
    am = math.radians((a0 + a1) / 2)
    lr = R + 4.5
    out.append(text(cx + lr * math.cos(am), cy - lr * math.sin(am) + 0.8, label, 2.0))
    return out


def _views(g: MicaHolesGeom, p: MicaHolesParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = (ax0 + ax1) / 2 - 4
    outer = max(g.dia, g.pcd)                       # PCD may exceed the disc dia
    sv = min((ax1 - ax0 - 92) / outer, (ay1 - ay0 - 88) / outer)
    r = g.dia * sv / 2                              # disc OD radius
    r_pcd = g.pcd * sv / 2                          # hole PCD radius
    r_out = max(r, r_pcd)
    r_hole = max(g.hole_dia * sv / 2, 1.2)
    if r_out > 46:                                  # keep the drawing on the sheet
        k = 46 / r_out; r *= k; r_pcd *= k; r_hole *= k; r_out = 46; sv *= k
    angs = (p.hole_angles if (p.hole_angles and len(p.hole_angles) == g.num_holes)
            else [g.hole_start_angle + i * g.theta for i in range(g.num_holes)])

    # ---------------- TOP VIEW ----------------
    cy1 = ay0 + 8 + 16 + r_out
    ext = 8
    s.append(circle(cx, cy1, r, THICK))                          # disc OD
    s.append(circle(cx, cy1, r_pcd, THIN, dash=C_LINE))          # PCD
    # main centre lines + a dash-dot radial line through every hole
    s.append(line(cx - r_out - ext, cy1, cx + r_out + ext, cy1, THIN, dash=C_LINE))
    s.append(line(cx, cy1 - r_out - ext, cx, cy1 + r_out + ext, THIN, dash=C_LINE))
    for a in angs:
        ar = math.radians(a)
        s.append(line(cx, cy1, cx + (r_out + ext) * math.cos(ar), cy1 - (r_out + ext) * math.sin(ar), THIN, dash=C_LINE))
    # holes + "B" label just outside each
    for a in angs:
        ar = math.radians(a)
        hx, hy = cx + r_pcd * math.cos(ar), cy1 - r_pcd * math.sin(ar)
        s.append(circle(hx, hy, r_hole, MED))
        lx, ly = cx + (r_pcd + r_hole + 2.6) * math.cos(ar), cy1 - (r_pcd + r_hole + 2.6) * math.sin(ar)
        s.append(text(lx, ly + 0.9, "B", 2.3, weight="bold"))
    # angle dimensions between adjacent holes (arc + arrows)
    order = sorted(angs)
    for i in range(len(order)):
        a0 = order[i]
        a1 = order[(i + 1) % len(order)] + (360 if i == len(order) - 1 else 0)
        s += _arc_dim(cx, cy1, r_out + 10, a0, a1, f"{_n((a1 - a0) % 360 or g.theta)}°")
    # Y-Y section markers at the horizontal centre line (left & right)
    for sx, d in ((cx - r_out - ext, -1), (cx + r_out + ext, 1)):
        s.append(line(sx, cy1, sx, cy1 + 7, THIN))
        s.append(arrow(sx, cy1 - 1, 0, -1))
        s.append(text(sx + d * 2.2, cy1 + 5.5, "Y", 2.6, weight="bold"))
    s.append(line(cx - r_out - ext - 3, cy1, cx + r_out + ext + 3, cy1, THIN, dash=C_LINE))
    # B = Ø<hole> ON PCD <pcd> leader (to a hole on the right)
    hb = math.radians(angs[0])
    s.append(_leader(cx + (r_pcd + r_hole) * math.cos(hb), cy1 - (r_pcd + r_hole) * math.sin(hb),
                     cx + r_out + 22, cy1 - r_out + 4, f"B = Ø{_n(g.hole_dia)} ON PCD {_n(g.pcd)}"))

    # ---------------- SECTION Y-Y ----------------
    hbh = 2.4
    cy2 = cy1 + r_out + 30
    yT, yB = cy2 - hbh / 2, cy2 + hbh / 2
    s.append(rect(cx - r, yT, 2 * r, hbh, THICK))
    # holes shown as openings through the disc — two hidden (dashed) walls each,
    # like the lid-blank section but WITHOUT the chamfer.
    xs = sorted({round(cx + r_pcd * math.cos(math.radians(a)), 2) for a in angs})
    for hx in xs:
        if cx - r - 0.5 <= hx <= cx + r + 0.5:
            for sgn in (-1, 1):
                wx = hx + sgn * r_hole
                s.append(line(wx, yT, wx, yB, THIN, dash=C_HID))
    # thickness dimension (right, arrows pointing in)
    xr = cx + r
    xt = xr + 13
    s.append(line(xr, yT, xt + 3, yT, THIN))
    s.append(line(xr, yB, xt + 3, yB, THIN))
    s.append(line(xt, yT - 6, xt, yB + 6, THIN))
    s.append(arrow(xt, yT, 0, 1)); s.append(arrow(xt, yB, 0, -1))
    # value and tolerance read as one entry, not two stacked notes
    s.append(text(xt + 2.5, cy2 + 1.2, f"{_n(g.thickness)} {g.thk_tol}", 3.2, anchor="start"))
    # diameter dimension (bottom, arrows pointing out)
    yd = cy2 + 15
    s.append(line(cx - r, yB, cx - r, yd + 2, THIN))
    s.append(line(cx + r, yB, cx + r, yd + 2, THIN))
    s.append(line(cx - r, yd, cx + r, yd, THIN))
    s.append(arrow(cx - r, yd, -1, 0)); s.append(arrow(cx + r, yd, 1, 0))
    # diameter and its tolerance on one line, as on the ring and housing sheets
    s.append(text(cx, yd + 5.2, f"Ø{_n(g.dia)}  {g.dia_tol}", 3.8))
    s.append(text(cx, yd + 10.5, "SECTION Y-Y", 2.6, weight="bold"))
    return s


def render_mica_holes_svg(g: MicaHolesGeom, p: MicaHolesParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>', _hatch_defs()]
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
