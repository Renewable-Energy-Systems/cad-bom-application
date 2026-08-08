"""Glass Cloth Tape CAD drawing (RES format).

A long thin tape shown with a conventional (necked) break in the length view,
plus a separate cross-section (width x thickness):
  * LENGTH view: two cross-hatched sections split by a break symbol; length dim.
  * CROSS-SECTION: thin bar; thickness (STD) at top, width at the right.
Dimensions:
  width      = 25 mm (STD),  thickness = 0.2 mm (STD)
  length     = (Container Height / Width) x pi x (Stack Dia + 2 x FiberFrax wrap thk)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, THICK, MED, THIN, _n, line, rect, text,
                        arrow, dim_h, dim_v, _header, _footer)
from .housing_a import _hatch_lines


@dataclass
class GlassClothTapeParams:
    length: float
    width: float = 25.0
    thickness: float = 0.2
    hatched: bool = True            # False -> plain outlines (e.g. Adhesive Tape)
    component_name: str = "GLASS CLOTH TAPE"
    material: str = "GLASS CLOTH"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    quantity: str = "01"
    date: str = ""
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class GlassClothTapeGeom:
    length: float
    width: float
    thickness: float
    warnings: list = field(default_factory=list)


def compute_glass_cloth_tape(p: GlassClothTapeParams) -> GlassClothTapeGeom:
    return GlassClothTapeGeom(length=round(p.length, 2), width=round(p.width, 2),
                              thickness=round(p.thickness, 2), warnings=[])


def _break_edge(x, yT, yB):
    """Conventional break edge points at x (the original S-zigzag), top -> bottom."""
    ym = (yT + yB) / 2
    return [(x, yT), (x, ym - 3), (x - 2.6, ym - 1), (x + 2.6, ym + 1), (x, ym + 3), (x, yB)]


def _poly_outline(pts, w=THICK):
    return ('<polyline points="' + " ".join(f"{_n(x)},{_n(y)}" for x, y in list(pts) + [pts[0]]) +
            f'" fill="none" stroke="#111" stroke-width="{w}"/>')


def _hatch_polygon(pts, sign=1, step=1.5):
    """Diagonal hatch segments clipped to the polygon (fills exactly up to its edges)."""
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    corners = [(min(xs), min(ys)), (max(xs), min(ys)), (min(xs), max(ys)), (max(xs), max(ys))]
    cvals = [cy - sign * cx for cx, cy in corners]
    cmin, cmax = min(cvals), max(cvals)
    n = len(pts)
    out = []
    c = cmin
    while c <= cmax:
        xints = []
        for i in range(n):
            x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % n]
            dx = x2 - x1; dy = y2 - y1
            denom = dy - sign * dx
            if abs(denom) < 1e-9:
                continue
            t = (c - (y1 - sign * x1)) / denom
            if 0 <= t <= 1:
                xints.append(x1 + t * dx)
        xints.sort()
        for j in range(0, len(xints) - 1, 2):
            x_a, x_b = xints[j], xints[j + 1]
            out.append(line(x_a, sign * x_a + c, x_b, sign * x_b + c, THIN))
        c += step
    return out


def _views(g: GlassClothTapeGeom, p: GlassClothTapeParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    # The tape is shown with a conventional break, so the length is not to
    # scale; the drawn size is chosen to use the sheet rather than sit small in
    # the top corner.
    cy = ay0 + 60
    wv = 58.0                                 # width (paper, not to scale)
    yT, yB = cy - wv / 2, cy + wv / 2
    lx0, lx1 = ax0 + 8, ax0 + 146
    xm = (lx0 + lx1) / 2
    gap = 5

    # ---------------- LENGTH VIEW (two hatched sections + break) ----------------
    # each section is a polygon whose inner edge is the conventional break; the
    # crossed hatch is clipped to that polygon so it fills right up to the break.
    left_poly = [(lx0, yT)] + _break_edge(xm - gap, yT, yB) + [(lx0, yB)]
    right_poly = _break_edge(xm + gap, yT, yB) + [(lx1, yB), (lx1, yT)]
    for poly in (left_poly, right_poly):
        s.append(_poly_outline(poly, THICK))
        if p.hatched:
            s += _hatch_polygon(poly, 1)
            s += _hatch_polygon(poly, -1)
    # length dimension across the top
    s.append(line(lx0, yT, lx0, yT - 10, THIN)); s.append(line(lx1, yT, lx1, yT - 10, THIN))
    s.append(dim_h(lx0, lx1, yT - 7, f"{_n(g.length)}"))

    # ---------------- CROSS-SECTION (thickness x width) ----------------
    tp = max(g.thickness * 2.0, 3.0)
    cx0 = ax0 + 150
    s.append(rect(cx0, yT, tp, wv, THICK))
    if p.hatched:
        s += _hatch_lines(cx0, yT, tp, wv, 1)
    # thickness dim (top) — compact, arrows stay at the two faces
    s.append(line(cx0, yT, cx0, yT - 9, THIN)); s.append(line(cx0 + tp, yT, cx0 + tp, yT - 9, THIN))
    s.append(line(cx0, yT - 6, cx0 + tp, yT - 6, THIN))
    s.append(arrow(cx0, yT - 6, -1, 0)); s.append(arrow(cx0 + tp, yT - 6, 1, 0))
    s.append(text(cx0 + tp + 7, yT - 7, f"{_n(g.thickness)}", 3.5, anchor="start"))
    s.append(text(cx0 + tp + 7, yT - 11, "(STANDARD)", 3.0, anchor="start"))
    # width dim (right, vertical)
    xw = cx0 + tp + 22
    s.append(line(cx0 + tp, yT, xw + 2, yT, THIN)); s.append(line(cx0 + tp, yB, xw + 2, yB, THIN))
    s.append(dim_v(yT, yB, xw, f"{_n(g.width)}"))
    return s


def render_glass_cloth_tape_svg(g: GlassClothTapeGeom, p: GlassClothTapeParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>']
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
