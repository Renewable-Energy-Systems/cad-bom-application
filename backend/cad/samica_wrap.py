"""Samica Wrap CAD drawing (RES format).

A plain rectangular wrap (no hatch, no break):
  * MAIN view: length (horizontal) x width (vertical) rectangle; length dim at
    the top, width dim at the right.
  * CROSS-SECTION: thin bar (thickness x width) with the thickness (STD) at top.
  length     = pi x (Stack Dia + 2 x FiberFrax wrap thk) + 10
  width      = Container Height - 3,   thickness = 0.1 mm (STD)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, THICK, MED, THIN, _n, line, rect, text,
                        arrow, dim_h, dim_v, _header, _footer)


@dataclass
class SamicaWrapParams:
    length: float
    width: float
    thickness: float = 0.1
    component_name: str = "SAMICA WRAP"
    material: str = "SAMICA"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    quantity: str = "01"
    date: str = ""
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class SamicaWrapGeom:
    length: float
    width: float
    thickness: float
    warnings: list = field(default_factory=list)


def compute_samica_wrap(p: SamicaWrapParams) -> SamicaWrapGeom:
    return SamicaWrapGeom(length=round(p.length, 2), width=round(p.width, 2),
                          thickness=round(p.thickness, 2), warnings=[])


def _views(g: SamicaWrapGeom, p: SamicaWrapParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    # Right-hand allowance: the gap to the edge view, the edge view itself, and
    # half of its centred label. 74 drew the wrap at under two thirds width.
    sv = min(((ax1 - ax0) - 56) / g.length, ((ay1 - ay0) - 62) / g.width)
    sv = max(0.2, sv)
    Lp = g.length * sv
    Wp = g.width * sv
    lx0 = ax0 + 10
    yT = ay0 + 22
    yB = yT + Wp

    # MAIN view (length x width), no hatch
    s.append(rect(lx0, yT, Lp, Wp, THICK))
    # length dim (top)
    s.append(line(lx0, yT, lx0, yT - 10, THIN)); s.append(line(lx0 + Lp, yT, lx0 + Lp, yT - 10, THIN))
    s.append(dim_h(lx0, lx0 + Lp, yT - 7, f"{_n(g.length)}"))
    # width dim (right of main view)
    xw = lx0 + Lp + 12
    s.append(line(lx0 + Lp, yT, xw + 2, yT, THIN)); s.append(line(lx0 + Lp, yB, xw + 2, yB, THIN))
    s.append(dim_v(yT, yB, xw, f"{_n(g.width)}"))

    # CROSS-SECTION (thickness x width)
    tp = max(g.thickness * 2.0, 3.0)
    sx = lx0 + Lp + 26
    s.append(rect(sx, yT, tp, Wp, THICK))
    # thickness dim (top) with (STD)
    s.append(line(sx, yT, sx, yT - 9, THIN)); s.append(line(sx + tp, yT, sx + tp, yT - 9, THIN))
    s.append(line(sx, yT - 6, sx + tp, yT - 6, THIN))
    s.append(arrow(sx, yT - 6, -1, 0)); s.append(arrow(sx + tp, yT - 6, 1, 0))
    # value and its (STD) note on one line, centred over the edge view, so the
    # label does not push the main view narrower
    s.append(text(sx + tp / 2, yT - 8.5, f"{_n(g.thickness)} (STD)", 3.0))
    return s


def render_samica_wrap_svg(g: SamicaWrapGeom, p: SamicaWrapParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>']
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
