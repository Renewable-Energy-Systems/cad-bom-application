"""Silicon Bonded Mica Ring (Housing - B) CAD drawing (RES format).

A plain annular ring (the ring part of Housing B): OD = container ID - 1,
ID = stack dia - 2, thickness 1.0 (STD). Two views:
  * TOP: two concentric circles with OD/ID leaders (value + symbol + tolerance)
    and A-A section markers.
  * SECTION A-A: the two walls (ID -> OD) filled with crossed (hatched) lines,
    the hole empty; thickness dimension on the right.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, THICK, MED, THIN, C_LINE, _n, line, rect,
                        circle, text, arrow, _header, _footer)
from .lid import _leader
from .housing_a import _hatch_lines


@dataclass
class SiliconRingBParams:
    outer_dia: float                # = container ID - 1
    inner_dia: float                # = stack dia - 2
    thickness: float = 1.0
    dia_tol_out: str = "+0.0/-0.2"
    dia_tol_in: str = "+0.2/-0.0"
    component_name: str = "SILICON BONDED MICA RING (HOUSING - B)"
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
class SiliconRingBGeom:
    outer_dia: float
    inner_dia: float
    thickness: float
    dia_tol_out: str
    dia_tol_in: str
    warnings: list = field(default_factory=list)


def compute_silicon_ring_b(p: SiliconRingBParams) -> SiliconRingBGeom:
    w: list[str] = []
    outer = round(p.outer_dia, 2)
    inner = round(p.inner_dia, 2)
    if inner >= outer:
        inner = round(outer * 0.72, 2)
        w.append(f"Inner dia exceeded the outer dia; using calculated Ø{inner}.")
    return SiliconRingBGeom(outer_dia=outer, inner_dia=inner, thickness=round(p.thickness, 2),
                            dia_tol_out=p.dia_tol_out or "+0.0/-0.2", dia_tol_in=p.dia_tol_in or "+0.2/-0.0",
                            warnings=w)


def _views(g: SiliconRingBGeom, p: SiliconRingBParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = (ax0 + ax1) / 2
    sv = min((ax1 - ax0 - 84) / g.outer_dia, (ay1 - ay0 - 96) / g.outer_dia)
    r = max(24.0, min(g.outer_dia * sv / 2, 46.0))
    ri = g.inner_dia / g.outer_dia * r

    # ---------------- TOP VIEW ----------------
    cy1 = ay0 + 8 + r
    ext = 8
    s.append(circle(cx, cy1, r, THICK))
    s.append(circle(cx, cy1, ri, THICK))
    s.append(line(cx - r - ext, cy1, cx + r + ext, cy1, THIN, dash=C_LINE))
    s.append(line(cx, cy1 - r - ext, cx, cy1 + r + ext, THIN, dash=C_LINE))
    # OD / ID leaders (value + symbol + tolerance)
    ao = math.radians(50)
    s.append(_leader(cx + r * math.cos(ao), cy1 - r * math.sin(ao), cx + r + 22, cy1 - r * 0.62,
                     f"Ø{_n(g.outer_dia)} {g.dia_tol_out}"))
    ai = math.radians(-32)
    s.append(_leader(cx + ri * math.cos(ai), cy1 - ri * math.sin(ai), cx + r + 22, cy1 - r * 0.12,
                     f"Ø{_n(g.inner_dia)} {g.dia_tol_in}"))
    # A-A markers (left & right, arrows up)
    for sx, d in ((cx - r - ext, -1), (cx + r + ext, 1)):
        s.append(arrow(sx, cy1 - 2, 0, -1))
        s.append(line(sx, cy1 - 2, sx, cy1 + 4, THIN))
        s.append(text(sx + d * 3, cy1 + 3, "A", 2.8, weight="bold"))

    # ---------------- SECTION A-A ----------------
    sec_cy = cy1 + r + 30
    tp = max(g.thickness * 3.2, 4.4)
    yT, yB = sec_cy - tp / 2, sec_cy + tp / 2
    # continuous bar (solid outline) with the inner-dia boundary lines; the two
    # walls (ID -> OD) are crossed (hatched), the middle is empty space bounded
    # by solid lines
    s.append(rect(cx - r, yT, 2 * r, tp, THICK))
    s.append(line(cx - ri, yT, cx - ri, yB, THICK))
    s.append(line(cx + ri, yT, cx + ri, yB, THICK))
    s += _hatch_lines(cx - r, yT, r - ri, tp, 1)
    s += _hatch_lines(cx + ri, yT, r - ri, tp, 1)
    # thickness dim (right) — spans exactly the thickness
    xtd = cx + r + 12
    s.append(line(cx + r, yT, xtd + 3, yT, THIN)); s.append(line(cx + r, yB, xtd + 3, yB, THIN))
    s.append(line(xtd, yT, xtd, yB, THIN))
    s.append(arrow(xtd, yT, 0, -1)); s.append(arrow(xtd, yB, 0, 1))
    s.append(text(xtd + 3, sec_cy + 1, f"{_n(g.thickness)}", 3.5, anchor="start"))
    s.append(text(xtd + 3, yT - 1.5, "(STD)", 3.0, anchor="start"))
    s.append(text(cx, yB + 9, "SECTION A-A", 2.6, weight="bold"))
    return s


def render_silicon_ring_b_svg(g: SiliconRingBGeom, p: SiliconRingBParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>']
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
