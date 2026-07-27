"""Circular pellet / disc CAD drawing (RES format).

A single generic generator for all the flat circular parts (cathode/anode/
electrolyte/heat pellets, SS/mica/samica/silicon-bonded-mica discs). Each is
drawn exactly like the reference: a TOP view (circle + centre lines) and a
SIDE view (thin bar). Only two dimensions are shown — Ø diameter (with its
tolerance) and thickness (with its tolerance) — with clear arrows and no text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, THICK, MED, THIN, C_LINE, _n, line, rect,
                        circle, text, arrow, _hatch_defs, _header, _footer)

DIA_TOL = "+0.0/-0.2"     # default diameter tolerance (per reference drawing)
THK_TOL = "±0.05"          # default thickness tolerance


@dataclass
class PelletParams:
    dia: float
    thickness: float
    dia_tol: str = DIA_TOL
    thk_tol: str = THK_TOL
    component_name: str = "PELLET"
    material: str = "—"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    quantity: str = "01"
    date: str = ""
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class PelletGeom:
    dia: float
    thickness: float
    dia_tol: str
    thk_tol: str
    warnings: list = field(default_factory=list)


def compute_pellet(p: PelletParams) -> PelletGeom:
    return PelletGeom(dia=round(p.dia, 2), thickness=round(p.thickness, 2),
                      dia_tol=p.dia_tol or DIA_TOL, thk_tol=p.thk_tol or THK_TOL, warnings=[])


def _views(g: PelletGeom, p: PelletParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = (ax0 + ax1) / 2
    sv = min((ax1 - ax0 - 70) / g.dia, (ay1 - ay0 - 96) / g.dia)
    r = max(24.0, min(g.dia * sv / 2, 52.0))

    # ---------------- TOP VIEW: circle + centre lines ----------------
    cy1 = ay0 + 8 + r
    ext = 7
    s.append(circle(cx, cy1, r, THICK))
    s.append(line(cx - r - ext, cy1, cx + r + ext, cy1, THIN, dash=C_LINE))
    s.append(line(cx, cy1 - r - ext, cx, cy1 + r + ext, THIN, dash=C_LINE))

    # ---------------- SIDE VIEW: thin bar ----------------
    hb = 2.4
    cy2 = cy1 + r + 30
    yT, yB = cy2 - hb / 2, cy2 + hb / 2
    s.append(rect(cx - r, yT, 2 * r, hb, THICK))

    # thickness dimension (right side, arrows pointing IN toward the thin bar)
    xr = cx + r
    xt = xr + 13
    s.append(line(xr, yT, xt + 3, yT, THIN))
    s.append(line(xr, yB, xt + 3, yB, THIN))
    s.append(line(xt, yT - 6, xt, yB + 6, THIN))
    s.append(arrow(xt, yT, 0, 1))          # top arrow points down (into the gap)
    s.append(arrow(xt, yB, 0, -1))         # bottom arrow points up (into the gap)
    s.append(text(xt + 2.5, cy2 - 1.4, g.thk_tol, 3.0, anchor="start"))
    s.append(text(xt + 2.5, cy2 + 2.4, _n(g.thickness), 3.5, anchor="start"))

    # diameter dimension (bottom, arrows pointing OUT to the extension lines)
    yd = cy2 + 16
    s.append(line(cx - r, yB, cx - r, yd + 2, THIN))
    s.append(line(cx + r, yB, cx + r, yd + 2, THIN))
    s.append(line(cx - r, yd, cx + r, yd, THIN))
    s.append(arrow(cx - r, yd, -1, 0))
    s.append(arrow(cx + r, yd, 1, 0))
    tols = [t.strip() for t in g.dia_tol.split("/")] if "/" in g.dia_tol else None
    if tols and len(tols) == 2:
        s.append(text(cx, yd + 3.6, tols[0], 3.0))
        s.append(text(cx, yd + 6.5, tols[1], 3.0))
        s.append(text(cx, yd + 11.0, f"Ø{_n(g.dia)}", 4.0))
    else:
        s.append(text(cx, yd + 5.5, f"Ø{_n(g.dia)}  {g.dia_tol}", 4.0))
    return s


def render_pellet_svg(g: PelletGeom, p: PelletParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>', _hatch_defs()]
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
