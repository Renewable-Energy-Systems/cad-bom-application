"""LID assembly CAD drawing (RES format).

The finished lid: the LID BLANK with a DELIVER PIN seated in the centre of each
pin hole, the remaining annulus filled with glass-to-metal (G.M.) seal — drawn in
BLUE, per the shop note "G.M SEAL TO BE DONE IN BLUE COLOUR".

Both children are the drawings this application already generates, so every
dimension here is taken from them rather than re-derived:

  * LID BLANK   -> lid OD, thickness, PCD, hole count, hole dia
  * DELIVER PIN -> pin dia, total pin length, upper part above the lid

Views:
  * TOP VIEW    : lid OD + PCD; at each hole an outer circle (hole dia, filled
    blue = G.M. seal) with the pin circle concentric inside it, plus the terminal
    markings. Callouts for the lid OD and "Ø<pin> TERMINAL PINS <n> NOs, ON PCD
    <pcd>". Section A-A cutting plane across the centre.
  * SECTION A-A : the lid hatched, each pin passing through its hole with the
    seal either side of it. Dimensioned exactly as asked — pin Ø (with symbol),
    upper part of the pin, total pin length (with tolerance) and the lid blank
    thickness — plus the "TO BE FILLED WITH G.M SEAL AT <n> PLACES." note.

A two-row BOM (LID BLANK + DELIVER PIN, with their reference drawing numbers)
sits in the left column band directly above the title block. The shared footer is
called with show_bom=False so it contributes only the MATERIAL / QUANTITY /
WEIGHT strip on the right, matching the reference sheet.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, BORDER_L, FOOT_TOP, THICK, MED, THIN,
                        C_LINE, _n, line, rect, circle, text, arrow, dim_v,
                        _hatch_defs, _header, _footer)
from .lid import _markings, _mark_rot, _tol, _leader, _hline_break

# G.M. seal is filled blue on the sheet (note: "G.M SEAL TO BE DONE IN BLUE COLOR")
GM_SEAL_BLUE = "#2f6fd0"
PIN_FILL = "#ffffff"

# Standard acceptance notes carried on this sheet. Editable per battery.
DEFAULT_NOTES = [
    "LEAK RATE : ≤1.2 X 10⁻⁸ atm-cc/Sec.",
    "WITHSTANDING PRESSURE UPTO 12 BAR",
    "INSULATION RESISTANCE LID TO PINS >1000 MΩ",
    "BREAKDOWN TEST 0.5KVA AT 1 MINUTE EACH PIN TO LID",
    "CONVEX/CONCAVE FILLING OF GLASS SEAL IS NOT ACCEPTABLE",
    "CRACK AND BLOW HOLES OR PIN HOLES ARE NOT ACCEPTABLE",
    "G.M SEAL TO BE DONE IN BLUE COLOR",
    "SCRATCHES, MARKS, DENTS WITH A DEPTH OF UP TO 0.05mm ARE ALLOWED.",
]

# BOM column edges — the same x grid the shared footer uses for its BOM strip.
_BOM_COLS = [("CODE NO.", BORDER_L, 24.0), ("COMPONENT", 24.0, 56.0),
             ("QTY/NOS", 56.0, 66.0), ("REF.DRG.NO", 66.0, 80.0)]
_BOM_RH = 5.6


@dataclass
class LidAssemblyParams:
    lid_od: float
    lid_thickness: float
    pcd: float
    num_holes: int
    hole_dia: float
    pin_dia: float
    pin_length: float                     # total deliver-pin height
    upper_part: float                     # pin projection above the lid
    # lid-blank edge features, so the section here matches that drawing exactly
    groove_depth: float = 0.0
    groove_width: float = 0.0
    weld_space: float = 0.0
    edge_angle: float = 6.0
    lid_od_tol: str = "+0.05 / -0.15"
    pin_dia_tol: str = "±0.1"
    pin_length_tol: str = "±0.2"
    thickness_tol: str = ""               # blank => IS 2102 medium by size
    hole_markings: Optional[list] = None
    hole_start_angle: float = 0.0
    notes: Optional[list] = None
    lid_blank_drg: str = ""               # REF.DRG.NO of the LID BLANK
    deliver_pin_drg: str = ""             # REF.DRG.NO of the DELIVER PIN
    # sheet/footer meta (same attrs the shared _footer reads)
    component_name: str = "LID"
    material: str = "AS LISTED"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    quantity: str = "01"
    date: str = ""
    show_bom: bool = False                # our own 2-row BOM is drawn instead
    revisions: list = field(default_factory=list)


@dataclass
class LidAssemblyGeom:
    lid_od: float
    lid_thickness: float
    pcd: float
    num_holes: int
    hole_dia: float
    pin_dia: float
    pin_length: float
    upper_part: float
    bottom_side: float                    # pin below the lid = total - upper - thickness
    seal_width: float                     # radial width of the G.M. seal annulus
    theta: float
    groove_depth: float = 0.0
    groove_width: float = 0.0
    weld_space: float = 0.0
    edge_angle: float = 6.0
    warnings: list = field(default_factory=list)


def compute_lid_assembly(p: LidAssemblyParams) -> LidAssemblyGeom:
    w: list[str] = []
    n = max(int(p.num_holes), 1)
    hole, pin = float(p.hole_dia), float(p.pin_dia)
    if pin >= hole:
        w.append(f"Pin Ø{_n(pin)} is not smaller than hole Ø{_n(hole)} — no annulus "
                 f"left for the G.M. seal; check the pin/hole diameters.")
    seal = round((hole - pin) / 2, 3)
    bottom = round(float(p.pin_length) - float(p.upper_part) - float(p.lid_thickness), 2)
    if bottom < 0:
        w.append(f"Upper part {_n(p.upper_part)} + lid thickness {_n(p.lid_thickness)} "
                 f"exceeds the total pin length {_n(p.pin_length)}; the pin does not "
                 f"reach through the lid.")
    return LidAssemblyGeom(
        lid_od=round(float(p.lid_od), 2), lid_thickness=round(float(p.lid_thickness), 2),
        pcd=round(float(p.pcd), 2), num_holes=n, hole_dia=round(hole, 2),
        pin_dia=round(pin, 2), pin_length=round(float(p.pin_length), 2),
        upper_part=round(float(p.upper_part), 2), bottom_side=bottom,
        seal_width=seal, theta=round(360.0 / n, 2),
        groove_depth=round(float(p.groove_depth or 0), 2),
        groove_width=round(float(p.groove_width or 0), 2),
        weld_space=round(float(p.weld_space or 0), 2),
        edge_angle=float(p.edge_angle or 6.0), warnings=w)


def _bom_table(g: LidAssemblyGeom, p: LidAssemblyParams) -> tuple[list, float]:
    """Two-row BOM in the left column band, growing upward from the title block.

    Returns (svg parts, top y) so the views know where they have to stop.
    """
    s: list[str] = []
    rows = [                                       # drawn bottom-up: 01 then 02
        ("01", "LID BLANK", "01", p.lid_blank_drg or "—"),
        ("02", "DELIVER PIN", f"{g.num_holes:02d}", p.deliver_pin_drg or "—"),
    ]
    hdr_top = FOOT_TOP + 5.5                       # header labels sit in the lower band
    hdr_bot = FOOT_TOP + 11.0
    x0, x1 = BORDER_L, _BOM_COLS[-1][2]
    top = hdr_top - len(rows) * _BOM_RH

    s.append(rect(x0, top, x1 - x0, hdr_bot - top, MED))
    s.append(line(x0, hdr_top, x1, hdr_top, MED))          # rows | header divider
    for _, a, b in _BOM_COLS:                              # column rules
        s.append(line(b, top, b, hdr_bot, THIN))
    for name, a, b in _BOM_COLS:                           # header labels
        s.append(text((a + b) / 2, hdr_bot - 1.7, name, 2.1, weight="bold"))
    for i, (code, comp, qty, ref) in enumerate(rows):      # data rows, 01 nearest header
        ry = hdr_top - (i + 1) * _BOM_RH
        if i:
            s.append(line(x0, ry + _BOM_RH, x1, ry + _BOM_RH, THIN))
        vals = [code, comp, qty, ref]
        for (_, a, b), v in zip(_BOM_COLS, vals):
            anc = "start" if b == 56.0 else "middle"
            xx = a + 1.5 if anc == "start" else (a + b) / 2
            s.append(text(xx, ry + _BOM_RH - 1.8, v, 2.0, anchor=anc))
    return s, top


_NOTE_LH = 3.4                    # note line height
_NOTE_FS = 2.1                    # note font size


def _notes_block(g: LidAssemblyGeom, p: LidAssemblyParams, y_bot: float) -> tuple[list, float]:
    """Numbered acceptance notes, bottom-aligned just above `y_bot`."""
    notes = p.notes if p.notes is not None else DEFAULT_NOTES
    notes = [n for n in notes if str(n).strip()]
    if not notes:
        return [], y_bot
    s: list[str] = []
    top = y_bot - len(notes) * _NOTE_LH - 2.0
    ax0 = AREA[0]
    s.append(text(ax0 + 4, top + _NOTE_LH, "NOTES", _NOTE_FS + 0.2, anchor="start"))
    for i, n in enumerate(notes):
        y = top + (i + 1) * _NOTE_LH
        s.append(text(ax0 + 20, y, f"{i + 1})", _NOTE_FS, anchor="start"))
        s.append(text(ax0 + 25, y, str(n), _NOTE_FS, anchor="start"))
    return s, top


def _views(g: LidAssemblyGeom, p: LidAssemblyParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = (ax0 + ax1) / 2
    n = g.num_holes
    marks = (p.hole_markings if (p.hole_markings and len(p.hole_markings) == n)
             else _markings(n))
    angs = [p.hole_start_angle + i * g.theta for i in range(n)]

    bom_svg, bom_top = _bom_table(g, p)
    notes_svg, notes_top = _notes_block(g, p, bom_top - 3)
    y_limit = notes_top - 3                     # views must finish above the notes

    # ---------------- vertical budget ----------------
    # Both views are sized from the height that is actually left after the BOM
    # and the notes, so nothing has to be nudged afterwards. The section keeps
    # its own (exaggerated) vertical scale so the thin lid still reads.
    PAD_TOP, GAP = 6.0, 13.0
    SEC_ABOVE, SEC_BELOW = 18.0, 17.0           # room for leaders / the view label
    avail_h = y_limit - ay0

    pin_paper = 38.0                            # target pin height on paper
    vscale = pin_paper / max(g.pin_length, 0.1)
    tp = g.lid_thickness * vscale
    if tp < 6.0:                                # lid too thin to read -> stretch
        vscale = 6.0 / max(g.lid_thickness, 0.1)
    elif tp > 16.0:                             # lid dominating -> compress
        vscale = 16.0 / max(g.lid_thickness, 0.1)

    def _sec_h(vs):
        return SEC_ABOVE + g.pin_length * vs + SEC_BELOW

    # top-view radius from whatever height remains, also bounded by the width
    avail_w = (ax1 - ax0) - 78
    r = min((avail_h - PAD_TOP - GAP - _sec_h(vscale)) / 2, avail_w / 2, 46.0)
    if r < 15.0:                                # not enough height: shrink the section
        r = 15.0
        room = avail_h - PAD_TOP - GAP - 2 * r - SEC_ABOVE - SEC_BELOW
        vscale = max(room, 12.0) / max(g.pin_length, 0.1)
    tp = g.lid_thickness * vscale               # lid thickness on paper
    up_p = max(g.upper_part, 0) * vscale
    bot_p = max(g.bottom_side, 0) * vscale

    sv = 2 * r / g.lid_od                       # horizontal scale follows the radius
    r_pcd = g.pcd * sv / 2
    r_hole = max(g.hole_dia * sv / 2, 1.5)
    r_pin = max(g.pin_dia * sv / 2, 0.6)
    if r_pin >= r_hole - 0.45:                  # keep the seal annulus visible
        r_pin = max(r_hole - 0.8, 0.4)

    # lid-blank edge features (same construction the LID BLANK top view uses)
    r_weld = (g.lid_od - 2 * g.weld_space) * sv / 2 if g.weld_space else 0.0
    r_grv = (r_weld - max(g.groove_width * sv, 1.4)) if (r_weld and g.groove_width) else 0.0

    # ---------------- TOP VIEW ----------------
    tv_cy = ay0 + PAD_TOP + r
    s.append(circle(cx, tv_cy, r, THICK))                        # lid OD
    if r_weld > r_pcd:
        s.append(circle(cx, tv_cy, r_weld, THIN))                # welding-space circle
    if r_grv > r_pcd:
        s.append(circle(cx, tv_cy, r_grv, THIN))                 # groove circle
    s.append(circle(cx, tv_cy, r_pcd, THIN, dash=C_LINE))        # PCD
    s.append(line(cx - r - 8, tv_cy, cx + r + 8, tv_cy, THIN, dash=C_LINE))
    s.append(line(cx, tv_cy - r - 8, cx, tv_cy + r + 8, THIN, dash=C_LINE))

    for i in range(n):
        ar = math.radians(angs[i])
        hx, hy = cx + r_pcd * math.cos(ar), tv_cy - r_pcd * math.sin(ar)
        s.append(circle(hx, hy, r_hole, MED, fill=GM_SEAL_BLUE))   # G.M. seal annulus
        s.append(circle(hx, hy, r_pin, MED, fill=PIN_FILL))        # pin
        rm = r_pcd + r_hole + 3.0
        s.append(text(cx + rm * math.cos(ar), tv_cy - rm * math.sin(ar) + 0.9,
                      marks[i], 2.7, weight="bold", rot=_mark_rot(angs[i])))

    # section A-A cutting plane (horizontal, arrows pointing up)
    for sx in (cx - r - 6, cx + r + 6):
        s.append(line(sx, tv_cy, sx, tv_cy + 8, THIN))
        s.append(arrow(sx, tv_cy - 1, 0, -1))
        s.append(text(sx, tv_cy + 12, "A", 2.8, weight="bold"))

    # callouts on the right
    tx = cx + r + 16
    s.append(_leader(cx + r * math.cos(math.radians(62)), tv_cy - r * math.sin(math.radians(62)),
                     tx, tv_cy - r + 2, f"Ø{_n(g.lid_od)}"))
    s.append(text(tx + 1.5, tv_cy - r - 2.6, p.lid_od_tol, 2.4, anchor="start"))
    pa = math.radians(angs[0] + g.theta) if n > 1 else math.radians(45)
    s.append(_leader(cx + (r_pcd + r_hole) * math.cos(pa), tv_cy - (r_pcd + r_hole) * math.sin(pa),
                     tx, tv_cy - r + 13, f"Ø{_n(g.pin_dia)} TERMINAL PINS"))
    s.append(text(tx + 1.5, tv_cy - r + 17, f"{n} NOs, ON PCD {_n(g.pcd)}", 2.6, anchor="start"))

    # ---------------- SECTION A-A ----------------
    # pin x-positions = the PCD projected onto the cutting plane
    proj = sorted({round(r_pcd * math.cos(math.radians(a)), 3) for a in angs})
    hxs = [cx + px for px in proj]

    pin_top = tv_cy + r + GAP + SEC_ABOVE         # top of the projecting pin
    yT = pin_top + up_p                           # lid top face
    yB = yT + tp                                  # lid bottom face
    pin_bot = pin_top + g.pin_length * vscale
    xL, xR = cx - r, cx + r

    # ---- lid material profile, taken from the LID BLANK section --------------
    # Same construction as lid.py's SECTION X-X: a sealing groove set in from
    # each edge by the weld space, and edges tapered by the 6° fit angle with a
    # chamfer at the bottom. Widths use the horizontal scale, the groove depth
    # the (exaggerated) vertical one, so the angle still reads correctly.
    gdp = min(g.groove_depth * vscale, tp * 0.55) if g.groove_depth else 0.0
    gwp = max(g.groove_width * sv, 2.6) if g.groove_width else 0.0
    wp = max(g.weld_space * sv, 2.2) if g.weld_space else 0.0
    ch = min(1.6, tp * 0.18)                       # bottom edge chamfer on paper
    taper = tp * math.tan(math.radians(g.edge_angle or 0))
    has_groove = gdp > 0 and gwp > 0 and (2 * (wp + gwp) < (xR - xL) * 0.8)
    gL0, gL1 = xL + wp, xL + wp + gwp               # left groove opening
    gR0, gR1 = xR - wp - gwp, xR - wp               # right groove opening

    prof = [(xL, yT)]
    if has_groove:
        prof += [(gL0, yT), (gL0, yT + gdp), (gL1, yT + gdp), (gL1, yT),
                 (gR0, yT), (gR0, yT + gdp), (gR1, yT + gdp), (gR1, yT)]
    prof += [(xR, yT),
             (xR - taper, yB - ch), (xR - taper - ch, yB),
             (xL + taper + ch, yB), (xL + taper, yB - ch)]
    dprof = "M " + " L ".join(f"{_n(x)} {_n(y)}" for x, y in prof) + " Z"
    s.append(f'<path d="{dprof}" fill="url(#hatch)" stroke="none"/>')
    for h in hxs:
        # G.M. seal fills the full hole width through the lid ...
        s.append(f'<rect x="{_n(h - r_hole)}" y="{_n(yT)}" width="{_n(2 * r_hole)}" '
                 f'height="{_n(tp)}" fill="{GM_SEAL_BLUE}" stroke="none"/>')
        # ... and the pin sits in the middle of it, running the full pin length
        s.append(f'<rect x="{_n(h - r_pin)}" y="{_n(pin_top)}" width="{_n(2 * r_pin)}" '
                 f'height="{_n(pin_bot - pin_top)}" fill="{PIN_FILL}" stroke="#111" '
                 f'stroke-width="{MED}"/>')
        # hole walls (lid material -> seal boundary)
        for sgn in (-1, 1):
            s.append(line(h + sgn * r_hole, yT, h + sgn * r_hole, yB, MED))
    # Lid outline. The faces are BROKEN at every hole (the pin and its seal pass
    # through there) and at the groove openings, whose notch is drawn separately.
    holes = [(h - r_hole, h + r_hole) for h in hxs]
    top_gaps = holes + ([(gL0, gL1), (gR0, gR1)] if has_groove else [])
    s.append(_hline_break(yT, xL, xR, top_gaps, THICK))
    s.append(_hline_break(yB, xL + taper + ch, xR - taper - ch, holes, THICK))
    if has_groove:                                  # the two sealing-groove notches
        for a, b in ((gL0, gL1), (gR0, gR1)):
            s.append(line(a, yT, a, yT + gdp, THICK))
            s.append(line(a, yT + gdp, b, yT + gdp, THICK))
            s.append(line(b, yT + gdp, b, yT, THICK))
    # tapered edges (6° fit angle) with the bottom chamfer
    s.append(line(xL, yT, xL + taper, yB - ch, THICK))
    s.append(line(xL + taper, yB - ch, xL + taper + ch, yB, THICK))
    s.append(line(xR, yT, xR - taper, yB - ch, THICK))
    s.append(line(xR - taper, yB - ch, xR - taper - ch, yB, THICK))
    s.append(line(cx, pin_top - 6, cx, pin_bot + 6, THIN, dash=C_LINE))

    # ---- dimensions the LID sheet must carry ----
    h0, hN = hxs[0], hxs[-1]
    # pin Ø, with symbol — leader off the projecting part of the first pin
    s.append(_leader(h0 - r_pin, pin_top + 3, xL + 4, pin_top - 6, f"Ø{_n(g.pin_dia)}"))
    # upper part of the pin (immediately left of the lid)
    xu = xL - 9
    s.append(line(h0 - r_pin, pin_top, xu - 2, pin_top, THIN))
    s.append(line(xL, yT, xu - 2, yT, THIN))
    s.append(dim_v(pin_top, yT, xu, f"{_n(g.upper_part)}"))
    # total deliver-pin length, with tolerance (further left again)
    xt = xL - 22
    s.append(line(h0 - r_pin, pin_top, xt - 2, pin_top, THIN))
    s.append(line(h0 - r_pin, pin_bot, xt - 2, pin_bot, THIN))
    s.append(dim_v(pin_top, pin_bot, xt, f"{_n(g.pin_length)} {p.pin_length_tol}"))
    # lid blank thickness (right)
    thk_tol = p.thickness_tol or _tol(g.lid_thickness)
    s.append(line(xR, yT, xR + 13, yT, THIN))
    s.append(line(xR - taper - ch, yB, xR + 13, yB, THIN))
    s.append(dim_v(yT, yB, xR + 12, f"{_n(g.lid_thickness)} {thk_tol}".strip()))
    # G.M. seal note — leader off a seal band, text stepping out to the right so
    # the label anchors left (both lines share the same x).
    ntx, nty = cx - r * 0.10, pin_top - 13.0
    s.append(_leader(h0 + (r_pin + r_hole) / 2, yT + tp * 0.5, ntx, nty,
                     "TO BE FILLED WITH G.M SEAL"))
    s.append(text(ntx + 1.5, nty + 3.2, f"AT {g.num_holes} PLACES.", 2.6, anchor="start"))
    # PIN leader off the part below the lid
    s.append(_leader(hN + r_pin, yB + max(bot_p * 0.5, 2), hN + 15, pin_bot + 3, "PIN"))
    s.append(text(cx, pin_bot + 13, "SECTION A-A", 3.0, weight="bold"))

    s += notes_svg
    s += bom_svg
    return s


def render_lid_assembly_svg(g: LidAssemblyGeom, p: LidAssemblyParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>',
             _hatch_defs()]
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
