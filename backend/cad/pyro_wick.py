"""Pyro Wick - 01 CAD drawing (RES format).

A thin rectangular strip. Two views:
  * FRONT (width x length) and SIDE (thickness x length), both hatched.
Dimensions: width (top of front), length (right of front), thickness (top of side).
  length    = Stack (Cathode) diameter + 10
  width/thk = from the guideline table by container OD (30-70 -> 3/0.3, >70 -> 6/0.7)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, THICK, MED, THIN, _n, line, rect, text,
                        arrow, dim_h, dim_v, _header, _footer)
from .housing_a import _hatch_lines


@dataclass
class PyroWickParams:
    length: float
    width: float
    thickness: float
    container_od: Optional[float] = None
    width_note: str = ""            # e.g. "(STD)" shown under the width value
    thk_note: str = ""              # e.g. "(STD)" shown under the thickness value
    visual_criteria: Optional[list] = None   # list of note lines under the views
    hatched: bool = True            # False -> plain outlines (e.g. Squib Terminal)
    component_name: str = "PYRO WICK - 01"
    material: str = "PYRO WICK"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    quantity: str = "02"
    date: str = ""
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class PyroWickGeom:
    length: float
    width: float
    thickness: float
    warnings: list = field(default_factory=list)


def compute_pyro_wick(p: PyroWickParams) -> PyroWickGeom:
    return PyroWickGeom(length=round(p.length, 2), width=round(p.width, 2),
                        thickness=round(p.thickness, 2), warnings=[])


def _views(g: PyroWickGeom, p: PyroWickParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = (ax0 + ax1) / 2
    sv = min((ay1 - ay0 - 40) / g.length, 3.4)
    sv = max(0.4, sv)
    Lp = g.length * sv
    wp = max(g.width * sv, 6.0)
    tp = max(g.thickness * sv, 1.6)
    yT = ay0 + 16
    yB = yT + Lp
    fx = cx - 34                          # front view centre x
    sx = cx + 26                          # side view centre x

    # FRONT VIEW (width x length)
    s.append(rect(fx - wp / 2, yT, wp, Lp, THICK))
    if p.hatched:
        s += _hatch_lines(fx - wp / 2, yT, wp, Lp, 1)
    # width dim (top)
    s.append(line(fx - wp / 2, yT, fx - wp / 2, yT - 7, THIN))
    s.append(line(fx + wp / 2, yT, fx + wp / 2, yT - 7, THIN))
    s.append(line(fx - wp / 2, yT - 5, fx + wp / 2, yT - 5, THIN))
    s.append(arrow(fx - wp / 2, yT - 5, -1, 0)); s.append(arrow(fx + wp / 2, yT - 5, 1, 0))
    s.append(text(fx, yT - 6, f"{_n(g.width)}", 3.5))
    if p.width_note:
        s.append(text(fx, yT - 2.6, p.width_note, 3.0))
    # length dim (right of front view)
    xdl = fx + wp / 2 + 12
    s.append(line(fx + wp / 2, yT, xdl + 2, yT, THIN))
    s.append(line(fx + wp / 2, yB, xdl + 2, yB, THIN))
    s.append(dim_v(yT, yB, xdl, f"{_n(g.length)}"))

    # SIDE VIEW (thickness x length)
    s.append(rect(sx - tp / 2, yT, tp, Lp, THICK))
    if p.hatched:
        s += _hatch_lines(sx - tp / 2, yT, tp, Lp, 1)
    # thickness dim (top) — compact, arrows stay at the two faces
    s.append(line(sx - tp / 2, yT, sx - tp / 2, yT - 7, THIN))
    s.append(line(sx + tp / 2, yT, sx + tp / 2, yT - 7, THIN))
    s.append(line(sx - tp / 2, yT - 5, sx + tp / 2, yT - 5, THIN))
    s.append(arrow(sx - tp / 2, yT - 5, -1, 0)); s.append(arrow(sx + tp / 2, yT - 5, 1, 0))
    s.append(text(sx + tp / 2 + 8, yT - 6, f"{_n(g.thickness)}", 3.5, anchor="start"))
    if p.thk_note:
        s.append(text(sx + tp / 2 + 8, yT - 2.6, p.thk_note, 3.0, anchor="start"))

    # visual criteria (under the views)
    if p.visual_criteria:
        vy = max(yB, ay0 + (ay1 - ay0) * 0.5) + 14
        s.append(text(ax0 + 4, vy, "VISUAL CRITERIA :", 2.1, anchor="start", weight="bold"))
        for i, ln in enumerate(p.visual_criteria):
            s.append(text(ax0 + 40, vy + i * 3.4, ln, 2.0, anchor="start"))
    return s


def render_pyro_wick_svg(g: PyroWickGeom, p: PyroWickParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>']
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
