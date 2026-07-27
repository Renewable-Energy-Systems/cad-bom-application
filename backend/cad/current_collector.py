"""Current Collector (Anode / Cathode) CAD drawing (RES format).

An SS disc (dia = cathode diameter) with a Nickel Lead welded on centrally.
  * TOP view: the disc (open circle) + the Nickel Lead strip placed 2 mm in from
    the disc edge on the starting side, running centrally across the disc and
    extending outside it; the overlap zone carries the SPOT WELD dot pattern.
    Callouts: SS DISC (ØdiaXtol), SPOT WELD, NICKEL LEAD; the 2 mm gap and the
    lead width are dimensioned.
  * SIDE view: the disc as a hatched bar and the Nickel Lead as a second bar in a
    DIFFERENT colour sitting on the disc; balloon 1 -> disc, balloon 2 -> lead.

Disc dia, lead length/width/thickness and the 2 mm gap are all data-driven.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, FOOT_TOP, BORDER_L, BORDER_R, THICK, MED,
                        THIN, C_LINE, _n, line, rect, circle, text, arrow,
                        dim_h, dim_v, _header, _footer)
from .housing_a import _balloon, _hatch_lines
from .lid import _leader

LEAD_COLOR = "#1560bd"                 # distinct colour for the Nickel Lead


@dataclass
class CurrentCollectorParams:
    disc_dia: float                    # = cathode diameter
    lead_length: float                 # from the Lead drawing
    lead_width: float                  # from the Lead drawing
    lead_thickness: float              # from the Lead drawing
    disc_thickness: float = 0.1        # SS disc / foil thickness
    disc_tol: str = "0.05"             # tolerance shown as ØdiaXtol
    gap: float = 2.0                   # gap from the disc edge on the starting side
    kind: str = "anode"                # anode | cathode
    cc_type: str = "B"                 # current-collector type letter
    lead_label: str = "NICKEL LEAD-A"
    qty: int = 1
    component_name: str = "CURRENT COLLECTOR - ANODE"
    material: str = "SS 304 / NICKEL"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    quantity: str = "01"
    date: str = ""
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class CurrentCollectorGeom:
    disc_dia: float
    disc_thickness: float
    lead_length: float
    lead_width: float
    lead_thickness: float
    gap: float
    warnings: list = field(default_factory=list)


def compute_current_collector(p: CurrentCollectorParams) -> CurrentCollectorGeom:
    w: list[str] = []
    if p.gap >= p.disc_dia:
        w.append(f"Gap {p.gap} mm >= disc dia {p.disc_dia} mm; lead start clamped to the disc.")
    return CurrentCollectorGeom(
        disc_dia=round(p.disc_dia, 2), disc_thickness=round(p.disc_thickness, 2),
        lead_length=round(p.lead_length, 2), lead_width=round(p.lead_width, 2),
        lead_thickness=round(p.lead_thickness, 2), gap=round(p.gap, 2), warnings=w)


def _hatch(x0, y0, w, h, sign=1, color="#111", step=1.5):
    """Diagonal hatch segments (like housing_a._hatch_lines) but colour-aware."""
    x1, y1 = x0 + w, y0 + h
    out: list[str] = []
    if sign > 0:
        c = y0 - x1
        while c <= y1 - x0:
            pts = []
            yy = x0 + c
            if y0 <= yy <= y1: pts.append((x0, yy))
            yy = x1 + c
            if y0 <= yy <= y1: pts.append((x1, yy))
            xx = y0 - c
            if x0 < xx < x1: pts.append((xx, y0))
            xx = y1 - c
            if x0 < xx < x1: pts.append((xx, y1))
            if len(pts) >= 2:
                out.append(line(pts[0][0], pts[0][1], pts[1][0], pts[1][1], THIN, color=color))
            c += step
    else:
        c = y0 + x0
        while c <= y1 + x1:
            pts = []
            yy = c - x0
            if y0 <= yy <= y1: pts.append((x0, yy))
            yy = c - x1
            if y0 <= yy <= y1: pts.append((x1, yy))
            xx = c - y0
            if x0 < xx < x1: pts.append((xx, y0))
            xx = c - y1
            if x0 < xx < x1: pts.append((xx, y1))
            if len(pts) >= 2:
                out.append(line(pts[0][0], pts[0][1], pts[1][0], pts[1][1], THIN, color=color))
            c += step
    return out


def _views(g: CurrentCollectorGeom, p: CurrentCollectorParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    D, LL, LW, G = g.disc_dia, g.lead_length, g.lead_width, min(g.gap, g.disc_dia * 0.9)

    span = max(D, G + LL)                      # left edge of disc -> right end of lead
    avail_w = (ax1 - ax0) - 34                 # room for the right-hand width dim
    sh = min(avail_w / span, 70.0 / D)
    sh = max(0.4, min(sh, 2.2))

    rD = D * sh / 2
    disc_left = ax0 + 10
    cx = disc_left + rD
    cy = ay0 + 30 + rD                         # top pad for the callouts
    disc_right = cx + rD

    lead_start = disc_left + G * sh
    lead_end = lead_start + LL * sh
    LWp = max(LW * sh, 5.0)
    lead_top, lead_bot = cy - LWp / 2, cy + LWp / 2

    # ---------- TOP VIEW ----------
    # centre lines
    s.append(line(disc_left - 4, cy, max(disc_right, lead_end) + 4, cy, THIN, dash=C_LINE))
    s.append(line(cx, cy - rD - 5, cx, cy + rD + 12, THIN, dash=C_LINE))
    # disc
    s.append(circle(cx, cy, rD, THICK))
    # nickel lead (open rectangle running across + beyond the disc)
    s.append(rect(lead_start, lead_top, lead_end - lead_start, LWp, THICK))

    # spot-weld dots over the overlap (from lead start into the disc)
    weld_end = min(lead_end, disc_right - 1.0)
    if weld_end > lead_start + 1:
        cols = max(int((weld_end - lead_start) / 2.4), 2)
        dxs = [lead_start + 2.0 + i * (weld_end - lead_start - 3.0) / max(cols - 1, 1) for i in range(cols)]
        for j, ry in enumerate((cy - LWp * 0.22, cy + LWp * 0.22)):
            for dx in dxs:
                s.append(circle(dx, ry, 0.3, THIN, fill="#111"))

    # SS DISC callout (Ø dia X tol) — leader to the disc upper-left edge
    a = math.radians(133)
    fdx, fdy = cx + rD * math.cos(a), cy - rD * math.sin(a)
    tdx, tdy = cx + rD * 0.25, ay0 + 5
    s.append(_leader(fdx, fdy, tdx, tdy, "SS DISC"))
    s.append(text(tdx + 1.5, tdy + 3.2, f"Ø{_n(g.disc_dia)}X{p.disc_tol}", 3.5, anchor="start"))

    # SPOT WELD callout — arrow lands ON a weld dot (not on the lead edge)
    wcx = (lead_start + weld_end) / 2
    s.append(_leader(wcx, cy - LWp * 0.22, wcx + 12, ay0 + 14, "SPOT WELD"))

    # NICKEL LEAD callout — leader up to the lead lower edge past the disc
    nlx = disc_right + (lead_end - disc_right) * 0.28
    s.append(_leader(nlx, lead_bot, nlx + 20, lead_bot + 14, p.lead_label))

    # 2 mm gap dim (below the disc, start side)
    yg = cy + rD + 9
    s.append(line(disc_left, cy, disc_left, yg + 2, THIN))
    s.append(line(lead_start, lead_bot, lead_start, yg + 2, THIN))
    s.append(dim_h(disc_left, lead_start, yg, f"{_n(g.gap)}"))

    # lead width dim (right end)
    xw = lead_end + 8
    s.append(line(lead_end, lead_top, xw + 2, lead_top, THIN))
    s.append(line(lead_end, lead_bot, xw + 2, lead_bot, THIN))
    s.append(dim_v(lead_top, lead_bot, xw, f"{_n(g.lead_width)}"))

    # ---------- SIDE VIEW ----------
    y_side = yg + 26
    DTp = max(g.disc_thickness * sh, 2.4)
    LTp = max(g.lead_thickness * sh, 1.6)
    # disc bar (black hatch)
    s.append(rect(disc_left, y_side, D * sh, DTp, THICK))
    s += _hatch_lines(disc_left, y_side, D * sh, DTp, 1)
    # nickel lead bar sitting on top of the disc (distinct colour + opposite hatch)
    lb_y = y_side - LTp
    s.append(rect(lead_start, lb_y, lead_end - lead_start, LTp, THICK, color=LEAD_COLOR))
    s += _hatch(lead_start, lb_y, lead_end - lead_start, LTp, -1, color=LEAD_COLOR)

    # balloon 1 -> disc
    b1x, b1y = disc_left - 5, y_side + DTp + 15
    f1x, f1y = disc_left + 4, y_side + DTp
    s.append(arrow(f1x, f1y, f1x - b1x, f1y - b1y))
    s.append(line(f1x, f1y, b1x, b1y, THIN))
    s.append(_balloon(b1x, b1y, 1))
    # balloon 2 -> nickel lead
    b2x, b2y = lead_end + 6, lb_y - 14
    f2x, f2y = lead_end - 10, lb_y
    s.append(arrow(f2x, f2y, f2x - b2x, f2y - b2y))
    s.append(line(f2x, f2y, b2x, b2y, THIN))
    s.append(_balloon(b2x, b2y, 2))
    return s


def render_current_collector_svg(g: CurrentCollectorGeom, p: CurrentCollectorParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>']
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
