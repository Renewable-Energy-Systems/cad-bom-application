"""Deliver Pin CAD drawing (RES format).

A round pin. Two views:
  * TOP (end) view : a small circle with a centre cross (round cross-section).
  * FRONT view     : a tall rectangle (the pin body) on the same vertical
    centreline; length dimensioned on the left, dia (Ø + tolerance) at the bottom.

  pin dia            = Table 1 "Diameter of the Pin" (else calculated)
  Deliver Pin Height = Upper part of pin + Lid Blank thickness + Bottom Side of Lid

Pin types (user-selected): round | top_flat_bottom_round | bottom_flat_top_round.
Only ROUND is implemented here; the other two are added later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, THICK, MED, THIN, C_LINE, _n, line, rect,
                        circle, text, arrow, dim_v, _header, _footer)


@dataclass
class DeliverPinParams:
    pin_dia: float
    pin_length: float                 # = Deliver Pin Height
    upper_part: float = 0.0           # from Table 1
    lid_thickness: float = 0.0        # Lid Blank thickness
    bottom_side: float = 0.0          # Bottom Side of Lid (user)
    dia_tol: str = "±0.1"
    pin_type: str = "round"           # round | top_flat_bottom_round | bottom_flat_top_round
    component_name: str = "DELIVER PIN"
    material: str = "SS 304"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    quantity: str = "01"
    date: str = ""
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class DeliverPinGeom:
    pin_dia: float
    pin_length: float
    pin_type: str
    warnings: list = field(default_factory=list)


def compute_deliver_pin(p: DeliverPinParams) -> DeliverPinGeom:
    w: list[str] = []
    if p.pin_type != "round":
        w.append(f"Pin type '{p.pin_type}' not yet implemented; showing ROUND.")
    return DeliverPinGeom(pin_dia=round(p.pin_dia, 2), pin_length=round(p.pin_length, 2),
                          pin_type=p.pin_type, warnings=w)


def _views(g: DeliverPinGeom, p: DeliverPinParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = (ax0 + ax1) / 2

    # scale: fit the length vertically, leaving room for the end-view circle + dims
    top_pad = 18.0                    # end-view circle region
    avail_h = (ay1 - 14) - (ay0 + top_pad + 14)
    # The pin is only a few mm long, so the cap is what governs, not the sheet.
    # At 9 it drew barely two thirds of the height available.
    sv = min(avail_h / max(g.pin_length, 0.1), 12.5)
    sv = max(0.6, sv)
    wp = max(g.pin_dia * sv, 6.0)     # body width (paper)
    Lp = g.pin_length * sv
    r = wp / 2

    # end-view circle (top)
    cyc = ay0 + top_pad
    rc = wp / 2
    s.append(circle(cx, cyc, rc, THICK))
    s.append(line(cx - rc - 3, cyc, cx + rc + 3, cyc, THIN, dash=C_LINE))   # cross (H)

    # front view rectangle (body)
    yT = cyc + rc + 12
    yB = yT + Lp
    s.append(rect(cx - r, yT, wp, Lp, THICK))
    # vertical centreline through circle + body
    s.append(line(cx, cyc - rc - 5, cx, yB + 9, THIN, dash=C_LINE))

    # length dimension (left) — value only
    xL = cx - r - 12
    s.append(line(cx - r, yT, xL - 2, yT, THIN))
    s.append(line(cx - r, yB, xL - 2, yB, THIN))
    s.append(dim_v(yT, yB, xL, f"{_n(g.pin_length)}"))

    # diameter dimension (bottom) — Ø value + tolerance
    yd = yB + 10
    s.append(line(cx - r, yB, cx - r, yd + 2, THIN))
    s.append(line(cx + r, yB, cx + r, yd + 2, THIN))
    s.append(line(cx - r, yd, cx + r, yd, THIN))
    s.append(arrow(cx - r, yd, -1, 0)); s.append(arrow(cx + r, yd, 1, 0))
    s.append(text(cx, yd + 3.4, f"Ø{_n(g.pin_dia)}", 4.0))
    s.append(text(cx + r + 3, yd - 2.6, p.dia_tol, 3.0, anchor="start"))
    return s


def render_deliver_pin_svg(g: DeliverPinGeom, p: DeliverPinParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>']
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
