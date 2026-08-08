"""Teflon Disc CAD drawing.

Guidelines:
  disc dia    = Lid diameter - 2 mm
  thickness   = 0.2 mm  (STD)
  inner circle dia = Stack diameter - space   (space from table by cathode dia)
  cuts        = N radial slots (N = number of tie wires) at 360/N, running from
                the STACK diameter to the disc OD (exactly touching both);
                slot width = tie-wire width + 1 mm
  holes       = PCD / number / angle from Table 1 (or calculated); all pins = "A"
Two views: TOP (disc + cuts + holes + inner/stack circle) + SIDE (with cuts).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .tables import teflon_inner_space, tie_wire_width
from .container import (PW, PH, AREA, THICK, MED, THIN, C_LINE, C_HID, _n, line,
                        rect, circle, text, arrow, dim_h, dim_v, _hatch_defs,
                        _header, _footer)
from .lid import _angle_dim, _hline_break, _leader

THK = 0.20
CUT_GAP = 5.0     # cuts run from the disc OD inward to (stack dia + this gap)


@dataclass
class TeflonParams:
    lid_diameter: float
    stack_diameter: float
    cathode_dia: float
    pcd: Optional[float] = None
    num_holes: Optional[int] = None
    num_wires: int = 3
    tie_width: Optional[float] = None
    container_od: Optional[float] = None
    hole_dia: float = 2.0
    # editable overrides (CAD Revision) — blank => computed
    disc_dia: Optional[float] = None
    thickness: Optional[float] = None
    cut_length: Optional[float] = None
    cut_width: Optional[float] = None
    cut_angle: Optional[float] = None       # angle between cuts
    hole_angle: Optional[float] = None      # angle between pins
    component_name: str = "TEFLON DISC"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    date: str = ""
    material: str = "TEFLON"
    quantity: str = "01"
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class TeflonGeom:
    disc_dia: float
    thickness: float
    inner_dia: float
    stack_dia: float
    space: float
    num_cuts: int
    cut_angle: float
    cut_length: float
    cut_width: float
    cut_inner_dia: float
    pcd: float
    num_holes: int
    theta: float
    hole_dia: float
    warnings: list = field(default_factory=list)


def compute_teflon(p: TeflonParams) -> TeflonGeom:
    w: list[str] = []
    disc = round(p.disc_dia, 2) if p.disc_dia else round(p.lid_diameter - 2.0, 2)
    space = teflon_inner_space(p.cathode_dia)
    inner = round(p.stack_diameter - space, 2)
    n_wires = max(int(p.num_wires or 3), 1)
    tw = p.tie_width if p.tie_width else (tie_wire_width(p.container_od) if p.container_od else 3.0)
    cut_w = round(p.cut_width, 2) if p.cut_width else round(tw + 1.0, 2)   # slot width
    cut_inner = round(p.stack_diameter + CUT_GAP, 2)      # cuts stop 5 mm out from stack dia
    cut_len = round(p.cut_length, 2) if p.cut_length else round((disc - cut_inner) / 2, 2)
    nh = int(p.num_holes) if p.num_holes else 4
    if not p.num_holes:
        w.append("Number of holes not found; assumed 4.")
    pcd = p.pcd if p.pcd else round(p.cathode_dia * 0.55, 2)
    cut_ang = round(p.cut_angle, 2) if p.cut_angle else round(360 / n_wires, 2)
    theta = round(p.hole_angle, 2) if p.hole_angle else round(360 / nh, 2)
    thk = round(p.thickness, 2) if p.thickness else THK
    return TeflonGeom(disc_dia=disc, thickness=thk, inner_dia=inner, stack_dia=p.stack_diameter,
                      space=space, num_cuts=n_wires, cut_angle=cut_ang,
                      cut_length=cut_len, cut_width=cut_w, cut_inner_dia=cut_inner, pcd=pcd, num_holes=nh,
                      theta=theta, hole_dia=p.hole_dia, warnings=w)


def _slot_pts(cx, cy, ri, ro, ang, wdt):
    a = math.radians(ang)
    rad = (math.cos(a), -math.sin(a))
    per = (-math.sin(a), -math.cos(a))
    out = []
    for R, sgn in [(ri, 1), (ro, 1), (ro, -1), (ri, -1)]:
        out.append((cx + R * rad[0] + sgn * (wdt / 2) * per[0],
                    cy + R * rad[1] + sgn * (wdt / 2) * per[1]))
    return out


def _arc(cx, cy, R, a0, a1):
    """Polyline arc a0->a1 (deg, CCW, y-up screen)."""
    steps = max(3, int(abs(a1 - a0) / 5))
    pts = [(cx + R * math.cos(math.radians(a0 + (a1 - a0) * k / steps)),
            cy - R * math.sin(math.radians(a0 + (a1 - a0) * k / steps))) for k in range(steps + 1)]
    return ('<polyline points="' + " ".join(f"{_n(x)},{_n(y)}" for x, y in pts) +
            f'" fill="none" stroke="#111" stroke-width="{THICK}"/>')


def _views(g: TeflonGeom, p: TeflonParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = (ax0 + ax1) / 2 - 6
    sv = min(((ax1 - ax0) - 74) / g.disc_dia, ((ay1 - ay0) - 44) / g.disc_dia)
    sv = max(0.5, min(sv, 3.4))
    r = g.disc_dia * sv / 2
    r_stk = g.stack_dia * sv / 2
    r_cin = g.cut_inner_dia * sv / 2       # cut inner boundary (stack dia + 5)
    r_pcd = g.pcd * sv / 2
    r_hole = max(g.hole_dia * sv / 2, 1.0)
    cw = g.cut_width * sv
    # cuts sit in the GAPS between holes (offset by half the hole pitch)
    cut_start = 90 + g.theta / 2
    cut_angles = [cut_start + i * g.cut_angle for i in range(g.num_cuts)]

    # ---------------- TOP VIEW (no hatching) ----------------
    cy = ay0 + 8 + r
    dphi = math.degrees(math.asin(min((cw / 2) / r, 0.99)))
    # OD drawn as arcs BETWEEN the cut mouths (so the slots open at the edge)
    ca = sorted(cut_angles)
    for i in range(len(ca)):
        a0 = ca[i] + dphi
        a1 = (ca[(i + 1) % len(ca)] + (360 if i == len(ca) - 1 else 0)) - dphi
        s.append(_arc(cx, cy, r, a0, a1))
    # stack circle (cuts begin here) + PCD + centre lines  (no innermost circle)
    s.append(circle(cx, cy, r_stk, THIN, dash=C_HID))
    s.append(circle(cx, cy, r_pcd, THIN, dash=C_LINE))
    s.append(line(cx - r - 6, cy, cx + r + 6, cy, THIN, dash=C_LINE))
    s.append(line(cx, cy - r - 6, cx, cy + r + 6, THIN, dash=C_LINE))
    # cuts: from (stack dia + 5) to OD (walls + inner end; outer end open at OD)
    for a in cut_angles:
        pts = _slot_pts(cx, cy, r_cin, r, a, cw)
        s.append(line(pts[0][0], pts[0][1], pts[1][0], pts[1][1], THICK))  # wall 1
        s.append(line(pts[3][0], pts[3][1], pts[2][0], pts[2][1], THICK))  # wall 2
        s.append(line(pts[0][0], pts[0][1], pts[3][0], pts[3][1], THICK))  # inner end
    # holes on PCD — ALL labelled "A"
    for i in range(g.num_holes):
        ar = math.radians(90 + i * g.theta)
        hx, hy = cx + r_pcd * math.cos(ar), cy - r_pcd * math.sin(ar)
        s.append(circle(hx, hy, r_hole, MED))
        s.append(text(hx, hy - r_hole - 0.8, "A", 2.2, weight="bold"))

    # ---- callouts ----
    # SLOT dimension — leader at a cut: "SLOT <cut length> × <cut width>"
    a0 = math.radians(cut_angles[0])
    smx = cx + (r_cin + r) / 2 * math.cos(a0) + (cw / 2) * -math.sin(a0)
    smy = cy - (r_cin + r) / 2 * math.sin(a0) - (cw / 2) * math.cos(a0)
    # Callout text is pulled back inside the sheet when the disc is large enough
    # that the usual stand-off would run it off the edge.
    lbl = f"SLOT {_n(g.cut_length)} × {_n(g.cut_width)}"
    s.append(_leader(smx, smy, max(cx - r - 14, ax0 + len(lbl) * 1.8), cy - r * 0.45, lbl))
    # cut WIDTH "<n> (TYP)" — leader arrow at the cut, across its width
    aw = math.radians(cut_angles[-1])
    wmx = cx + (r - 4) * math.cos(aw) + (cw / 2) * -math.sin(aw)
    wmy = cy - (r - 4) * math.sin(aw) - (cw / 2) * math.cos(aw)
    s.append(_leader(wmx, wmy, cx + r + 14, cy + r * 0.5, f"{_n(g.cut_width)} (TYP)"))
    # A = pin dia ON pcd — leader to a hole
    ha = math.radians(90)
    lbl_a = f"A = Ø{_n(g.hole_dia)} ON PCD {_n(g.pcd)}"
    s.append(_leader(cx + (r_pcd + r_hole) * math.cos(ha), cy - (r_pcd + r_hole) * math.sin(ha),
                     min(cx + r + 14, ax1 - len(lbl_a) * 1.8), cy - r + 6, lbl_a))
    # angle: cut-to-cut AND hole-to-hole
    if g.num_cuts > 1:
        s.append(_angle_dim(cx, cy, r + 2, r + 4, cut_angles[0], cut_angles[1], f"{_n(g.cut_angle)}° (TYP)"))
    if g.num_holes > 1:
        s.append(_angle_dim(cx, cy, r_pcd, r_pcd * 0.5, 90, 90 + g.theta, f"{_n(g.theta)}° (TYP)"))

    # ---------------- SECTION X-X (hatched material, cuts dotted) ----------------
    sy = cy + r + 30
    tp = max(g.thickness * sv * 6, 3.0)
    yT2, yB2 = sy - tp / 2, sy + tp / 2
    s.append(text(cx, yT2 - 4, "SECTION  X-X", 2.6, weight="bold"))
    # solid material bar filled with hatching
    s.append(rect(cx - r, yT2, 2 * r, tp, THICK, fill="url(#hatch)"))
    # each cut reflected as dotted (hidden) lines at its projected position
    for a in cut_angles:
        xi = cx + r_cin * math.cos(math.radians(a))
        xo = cx + r * math.cos(math.radians(a))
        lo, hi = sorted((xi, xo))
        if hi - lo < cw:
            mid = (lo + hi) / 2; lo, hi = mid - cw / 2, mid + cw / 2
        s.append(line(lo, yT2, lo, yB2, THIN, dash=C_HID))
        s.append(line(hi, yT2, hi, yB2, THIN, dash=C_HID))
    # thickness + disc dia dims
    s.append(line(cx + r, yT2, cx + r + 9, yT2, THIN)); s.append(line(cx + r, yB2, cx + r + 9, yB2, THIN))
    s.append(dim_v(yT2, yB2, cx + r + 8, f"{_n(g.thickness)}"))
    # above the thickness value rather than beside it — the section is only a
    # couple of millimetres deep, so side by side they touch
    s.append(text(cx + r + 8, yT2 - 4.5, "(STD)", 2.8))
    s.append(line(cx - r, yB2, cx - r, yB2 + 9, THIN)); s.append(line(cx + r, yB2, cx + r, yB2 + 9, THIN))
    s.append(dim_h(cx - r, cx + r, yB2 + 8, ""))
    s.append(text(cx, yB2 + 7, f"Ø{_n(g.disc_dia)}  +0.2/−0.0", 3.5))
    return s


def render_teflon_svg(g: TeflonGeom, p: TeflonParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>', _hatch_defs()]
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
