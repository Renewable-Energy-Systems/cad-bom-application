"""Silicon Bonded Mica Ring (Housing - A) CAD drawing (RES format).

Housing-A ring geometry (OD = stack dia, ID = PCD + 2, two 180° cuts of width
squib+2) but the cuts are OPEN — the outer and inner walls are removed at each
cut, so the part is two C-shaped halves. Thickness 1.0 (STD). SECTION A-A only:
the two walls (OD->ID) are hatched; the hole and the cut openings are empty.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, THICK, MED, THIN, C_LINE, _n, line, rect,
                        circle, text, arrow, _header, _footer)
from .lid import _leader
from .housing_a import _hatch_lines, _arc


@dataclass
class SiliconRingAParams:
    outer_dia: float                # = stack diameter
    inner_dia: float                # = PCD + 2
    squib_width: float = 5.0
    thickness: float = 1.0
    num_cuts: int = 2
    dia_tol_out: str = "+0.0/-0.2"
    dia_tol_in: str = "+0.2/-0.0"
    component_name: str = "SILICON BONDED MICA RING (HOUSING - A)"
    material: str = "SILICON BONDED MICA"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    quantity: str = "02"
    date: str = ""
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class SiliconRingAGeom:
    outer_dia: float
    inner_dia: float
    thickness: float
    cut_width: float
    num_cuts: int
    dia_tol_out: str
    dia_tol_in: str
    warnings: list = field(default_factory=list)


def compute_silicon_ring_a(p: SiliconRingAParams) -> SiliconRingAGeom:
    w: list[str] = []
    outer = round(p.outer_dia, 2)
    inner = round(p.inner_dia, 2)
    if inner >= outer:
        inner = round(outer * 0.68, 2)
        w.append(f"Inner dia (PCD+2) exceeded the outer dia; using calculated Ø{inner}.")
    return SiliconRingAGeom(outer_dia=outer, inner_dia=inner, thickness=round(p.thickness, 2),
                            cut_width=round(p.squib_width + 2.0, 2), num_cuts=max(int(p.num_cuts or 2), 1),
                            dia_tol_out=p.dia_tol_out or "+0.0/-0.2", dia_tol_in=p.dia_tol_in or "+0.2/-0.0",
                            warnings=w)


def _views(g: SiliconRingAGeom, p: SiliconRingAParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = ax0 + (ax1 - ax0) * 0.46
    sv = min((ax1 - ax0 - 96) / g.outer_dia, (ay1 - ay0 - 66) / g.outer_dia)
    r = max(22.0, min(g.outer_dia * sv / 2, 50.0))
    ri = g.inner_dia / g.outer_dia * r
    cw = g.cut_width * sv
    cut_angles = [90 + i * (360 / g.num_cuts) for i in range(g.num_cuts)]

    # ---------------- TOP VIEW (open cuts) ----------------
    cy1 = ay0 + 8 + r
    dpo = math.degrees(math.asin(min((cw / 2) / r, 0.99)))
    dpi = math.degrees(math.asin(min((cw / 2) / ri, 0.99)))
    ca = sorted(cut_angles)
    for i in range(len(ca)):                       # OUTER arcs (broken at cuts)
        a0 = ca[i] + dpo
        a1 = (ca[(i + 1) % len(ca)] + (360 if i == len(ca) - 1 else 0)) - dpo
        s.append(_arc(cx, cy1, r, a0, a1, THICK))
    for i in range(len(ca)):                       # INNER arcs (broken at cuts)
        a0 = ca[i] + dpi
        a1 = (ca[(i + 1) % len(ca)] + (360 if i == len(ca) - 1 else 0)) - dpi
        s.append(_arc(cx, cy1, ri, a0, a1, THICK))
    # cut side walls (inner arc edge -> outer arc edge)
    for a in cut_angles:
        ar = math.radians(a)
        rx, ry = math.cos(ar), -math.sin(ar)
        px, py = -math.sin(ar), -math.cos(ar)
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
    # OD / ID leaders with tolerance
    ao = math.radians(40)
    s.append(_leader(cx + r * math.cos(ao), cy1 - r * math.sin(ao), cx + r + 22, cy1 - r * 0.6,
                     f"Ø{_n(g.outer_dia)} {g.dia_tol_out}"))
    ai = math.radians(-18)
    s.append(_leader(cx + ri * math.cos(ai), cy1 - ri * math.sin(ai), cx + r + 22, cy1 - r * 0.1,
                     f"Ø{_n(g.inner_dia)} {g.dia_tol_in}"))
    # A-A markers (horizontal, arrows up)
    for sx, d in ((cx - r - 8, -1), (cx + r + 8, 1)):
        s.append(arrow(sx, cy1 - 2, 0, -1))
        s.append(line(sx, cy1 - 2, sx, cy1 + 4, THIN))
        s.append(text(sx + d * 3, cy1 + 3, "A", 2.8, weight="bold"))
    # cut width dim at the bottom cut: "<w> CUT"
    ycut = cy1 + (ri + r) / 2
    s.append(line(cx - cw / 2, ycut, cx + cw / 2, ycut, THIN))
    s.append(arrow(cx - cw / 2, ycut, -1, 0)); s.append(arrow(cx + cw / 2, ycut, 1, 0))
    # The cut is narrow and sits inside the annulus, so its value goes OUTSIDE
    # the ring on a leader rather than printing on top of the circles.
    s.append(line(cx + cw / 2, ycut, cx + r + 5, ycut, THIN))
    s.append(text(cx + r + 7, ycut + 1.1, f"{_n(g.cut_width)} CUT", 3.2, anchor="start"))

    # ---------------- SECTION A-A (upper part) ----------------
    sec_cy = cy1 + r + 26
    tp = max(g.thickness * 3.2, 4.4)
    yT, yB = sec_cy - tp / 2, sec_cy + tp / 2
    # walls (OD -> ID): hatched, solid outline
    for (bx0, bx1) in ((cx - r, cx - ri), (cx + ri, cx + r)):
        s.append(rect(bx0, yT, bx1 - bx0, tp, THICK))
        s += _hatch_lines(bx0, yT, bx1 - bx0, tp, 1)
    # inner dia -> cut: solid material (solid outline, no hatch)
    for (bx0, bx1) in ((cx - ri, cx - cw / 2), (cx + cw / 2, cx + ri)):
        if bx1 > bx0:
            s.append(rect(bx0, yT, bx1 - bx0, tp, THICK))
    # only the CUT (centre) is empty space
    # thickness dim (right) with (STD)
    xtd = cx + r + 12
    s.append(line(cx + r, yT, xtd + 3, yT, THIN)); s.append(line(cx + r, yB, xtd + 3, yB, THIN))
    s.append(line(xtd, yT, xtd, yB, THIN))
    s.append(arrow(xtd, yT, 0, -1)); s.append(arrow(xtd, yB, 0, 1))
    s.append(text(xtd + 3, sec_cy + 1, f"{_n(g.thickness)}", 3.5, anchor="start"))
    s.append(text(xtd + 3, yT - 1.5, "(STD)", 3.0, anchor="start"))
    s.append(text(cx, yB + 9, "SECTION A-A", 2.6, weight="bold"))
    return s


def render_silicon_ring_a_svg(g: SiliconRingAGeom, p: SiliconRingAParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>']
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
