"""Tie Wire CAD drawing — a thin nickel strip.

Guidelines:
  length    = Container Height + 30 mm
  thickness = 0.3 mm  (+0.000 / -0.030)
  width     = from table by container OD  (30-70 -> 3, >70 -> 6), +/-0.4
Two views: FRONT (width x length) + SIDE (thickness x length). Material NICKEL.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .tables import tie_wire_width
from .container import (PW, PH, AREA, THICK, MED, THIN, _n, line, rect, text,
                        arrow, dim_h, dim_v, _hatch_defs, _header, _footer)

THK = 0.30
LENGTH_ADD = 30.0


@dataclass
class TieWireParams:
    container_od: float
    container_height: float
    width: Optional[float] = None
    thickness: Optional[float] = None       # editable override
    length: Optional[float] = None          # editable override (else height + add)
    component_name: str = "TIE WIRE"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    date: str = ""
    material: str = "NICKEL"
    quantity: str = "03"
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class TieWireGeom:
    length: float
    width: float
    thickness: float
    warnings: list


def compute_tie_wire(p: TieWireParams) -> TieWireGeom:
    w = p.width if p.width else tie_wire_width(p.container_od)
    length = round(p.length, 2) if p.length else round(p.container_height + LENGTH_ADD, 2)
    thk = round(p.thickness, 2) if p.thickness else THK
    return TieWireGeom(length=length, width=w, thickness=thk, warnings=[])


def _views(g: TieWireGeom, p: TieWireParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = (ax0 + ax1) / 2
    # scale so the (tall) strip fits vertically
    sv = min((ay1 - ay0 - 24) / g.length, 3.0)
    sv = max(0.4, sv)
    Lp = g.length * sv
    wp = max(g.width * sv, 5)
    tp = max(g.thickness * sv, 1.6)
    yT = ay0 + 12
    yB = yT + Lp
    fx = cx - 34                       # front view centre x
    sx = cx + 30                       # side view centre x

    # FRONT VIEW (width x length)
    s.append(f'<rect x="{_n(fx - wp/2)}" y="{_n(yT)}" width="{_n(wp)}" height="{_n(Lp)}" fill="url(#hatch)" stroke="#111" stroke-width="{THICK}"/>')
    s.append(line(fx, yT - 3, fx, yB + 3, THIN, dash="3,1,0.8,1"))
    # length dim (left)
    s.append(dim_v(yT, yB, fx - wp / 2 - 8, f"{_n(g.length)}"))
    s.append(line(fx - wp / 2, yT, fx - wp / 2 - 9, yT, THIN))
    s.append(line(fx - wp / 2, yB, fx - wp / 2 - 9, yB, THIN))
    # width dim (top, +/-0.4)
    s.append(dim_h(fx - wp / 2, fx + wp / 2, yT - 5, f"{_n(g.width)} ±0.4"))
    s.append(line(fx - wp / 2, yT, fx - wp / 2, yT - 6, THIN))
    s.append(line(fx + wp / 2, yT, fx + wp / 2, yT - 6, THIN))

    # SIDE VIEW (thickness x length)
    s.append(f'<rect x="{_n(sx - tp/2)}" y="{_n(yT)}" width="{_n(tp)}" height="{_n(Lp)}" fill="url(#hatch)" stroke="#111" stroke-width="{THICK}"/>')
    s.append(line(sx, yT - 3, sx, yB + 3, THIN, dash="3,1,0.8,1"))
    # thickness dim (top)
    s.append(dim_h(sx - tp / 2, sx + tp / 2, yT - 5, ""))
    s.append(line(sx - tp / 2, yT, sx + 14, yT - 8, THIN))
    s.append(text(sx + 15, yT - 8, f"{_n(g.thickness)}", 3.5, anchor="start"))
    s.append(text(sx + 15, yT - 5, "+0.000/−0.030", 3.0, anchor="start"))

    s.append(text(cx, yB + 8, "VISUAL CRITERIA :  FREE FROM BURRS,  DENTS/SCRATCHES NOT ALLOWED", 2.0))
    return s


def render_tie_wire_svg(g: TieWireGeom, p: TieWireParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>', _hatch_defs()]
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
