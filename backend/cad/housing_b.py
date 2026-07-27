"""Housing - B CAD drawing (RES format).

A flat disc: outer ring (OD = container ID - 1) of one material and an inner
disc (ID = stack dia - 2) of another. Two views:
  * TOP: two concentric circles (OD + ID) with leaders, A-A section markers.
  * SECTION A-A: one continuous thin bar — the two outer-to-inner walls filled
    with single crossed lines (balloon ①), the middle inner-disc portion filled
    with double crossed lines (balloon ②); thickness on the right.
Thickness = Silicon Bonded Mica Ring (Housing - B) thickness.
BOM table sits just above the footer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, FOOT_TOP, BORDER_L, BORDER_R, THICK, MED,
                        THIN, C_LINE, _n, line, rect, circle, text, arrow,
                        _header, _footer)
from .lid import _leader
from .housing_a import _hatch_lines, _balloon, _bom_table


@dataclass
class HousingBParams:
    outer_dia: float                # = container ID - 1
    inner_dia: float                # = stack dia - 2
    thickness: float = 1.0          # = Silicon Bonded Mica Ring (Housing - B) thk
    bom_rows: Optional[list] = None
    component_name: str = "HOUSING - B"
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
class HousingBGeom:
    outer_dia: float
    inner_dia: float
    thickness: float
    warnings: list = field(default_factory=list)


def compute_housing_b(p: HousingBParams) -> HousingBGeom:
    w: list[str] = []
    outer = round(p.outer_dia, 2)
    inner = round(p.inner_dia, 2)
    if inner >= outer:
        inner = round(outer * 0.72, 2)
        w.append(f"Inner dia exceeded the outer dia; using calculated Ø{inner}.")
    return HousingBGeom(outer_dia=outer, inner_dia=inner, thickness=round(p.thickness, 2), warnings=w)


def _views(g: HousingBGeom, p: HousingBParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = (ax0 + ax1) / 2
    sv = min((ax1 - ax0 - 80) / g.outer_dia, (ay1 - ay0 - 96) / g.outer_dia)
    r = max(24.0, min(g.outer_dia * sv / 2, 46.0))
    ri = g.inner_dia / g.outer_dia * r

    # ---------------- TOP VIEW ----------------
    cy1 = ay0 + 8 + r
    ext = 8
    s.append(circle(cx, cy1, r, THICK))
    s.append(circle(cx, cy1, ri, THICK))
    s.append(line(cx - r - ext, cy1, cx + r + ext, cy1, THIN, dash=C_LINE))
    s.append(line(cx, cy1 - r - ext, cx, cy1 + r + ext, THIN, dash=C_LINE))
    # OD / ID leaders (value + symbol)
    import math
    ao = math.radians(50)
    s.append(_leader(cx + r * math.cos(ao), cy1 - r * math.sin(ao), cx + r + 20, cy1 - r * 0.6, f"Ø{_n(g.outer_dia)}"))
    ai = math.radians(-35)
    s.append(_leader(cx + ri * math.cos(ai), cy1 - ri * math.sin(ai), cx + r + 20, cy1 - r * 0.15, f"Ø{_n(g.inner_dia)}"))
    # A-A markers (left & right, arrows up)
    for sx, d in ((cx - r - ext, -1), (cx + r + ext, 1)):
        s.append(arrow(sx, cy1 - 2, 0, -1))
        s.append(line(sx, cy1 - 2, sx, cy1 + 4, THIN))
        s.append(text(sx + d * 3, cy1 + 3, "A", 2.8, weight="bold"))

    # ---------------- SECTION A-A ----------------
    sec_cy = cy1 + r + 32
    tp = max(g.thickness * 3.2, 4.4)
    yT, yB = sec_cy - tp / 2, sec_cy + tp / 2
    # continuous bar outline + segment boundaries at +-ri
    s.append(rect(cx - r, yT, 2 * r, tp, THICK))
    s.append(line(cx - ri, yT, cx - ri, yB, THICK))
    s.append(line(cx + ri, yT, cx + ri, yB, THICK))
    # outer walls (both sides): single crossed lines
    s += _hatch_lines(cx - r, yT, r - ri, tp, 1)
    s += _hatch_lines(cx + ri, yT, r - ri, tp, 1)
    # middle portion: double crossed lines (mesh)
    s += _hatch_lines(cx - ri, yT, 2 * ri, tp, 1)
    s += _hatch_lines(cx - ri, yT, 2 * ri, tp, -1)
    # balloon 1 -> outer wall (left);  balloon 2 -> middle
    s.append(line(cx - r + (r - ri) / 2, yT, cx - r - 8, yT - 6, THIN))
    s.append(_balloon(cx - r - 8, yT - 8.4, 1))
    s.append(line(cx + ri * 0.35, yT, cx + ri * 0.35 + 8, yT - 6, THIN))
    s.append(_balloon(cx + ri * 0.35 + 8, yT - 8.4, 2))
    # thickness dim (right) — compact, dimension line spans exactly the thickness
    xtd = cx + r + 12
    s.append(line(cx + r, yT, xtd + 3, yT, THIN)); s.append(line(cx + r, yB, xtd + 3, yB, THIN))
    s.append(line(xtd, yT, xtd, yB, THIN))
    s.append(arrow(xtd, yT, 0, -1)); s.append(arrow(xtd, yB, 0, 1))
    s.append(text(xtd + 3, sec_cy + 1, f"{_n(g.thickness)}", 3.5, anchor="start"))
    s.append(text(cx, yB + 9, "SECTION A-A", 2.6, weight="bold"))

    # ---------------- assembly BOM table ----------------
    s += _bom_table(g, p)
    return s


def render_housing_b_svg(g: HousingBGeom, p: HousingBParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>']
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
