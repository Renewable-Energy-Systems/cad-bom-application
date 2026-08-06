"""Lid with Tie Wire CAD drawing — RES format.

The back side of the LID BLANK with the nickel tie wires spot-welded onto it.
Everything is taken from drawings this application already generated, so the
sheet changes from battery to battery:

  * LID BLANK -> lid OD, thickness, PCD, hole count and dia, back groove circle
  * TIE WIRE  -> strip width and thickness
  * battery   -> stack (cathode) diameter, number of tie wires

The wires are spaced equally (360/N) and the whole set is rotated to whichever
position clears the terminal holes by the widest margin — so a wire is never
laid over a hole, whatever the hole and wire counts happen to be.

Each wire starts a set distance in from the stack diameter towards the centre
and runs radially out past the lid edge; that offset is dimensioned TYP.

Views: the back side of the lid, and SECTION X-X across it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, BORDER_L, FOOT_TOP, THICK, MED, THIN,
                        C_LINE, C_HID, _n, line, rect, circle, text, arrow,
                        _hatch_defs, _header, _footer)
from .lid import _markings, _mark_rot, _leader
from .lid_assembly import GM_SEAL_BLUE


@dataclass
class LidTieWireParams:
    lid_od: float
    lid_thickness: float
    pcd: float
    num_holes: int
    hole_dia: float
    stack_dia: float
    num_tie_wires: int = 3
    wire_width: float = 3.0
    wire_thickness: float = 0.3
    start_offset: float = 5.0            # wires begin this far radially inside
                                         # the stack dia, towards the centre
    groove_depth: float = 1.0
    groove_width: float = 1.0
    weld_space: float = 1.1
    edge_angle: float = 6.0
    pin_dia: Optional[float] = None
    pin_upper: float = 0.0               # pin projection above the lid, if known
    weld_length: float = 5.0             # length welded down on the lid (TYP)
    groove_circle_dia: Optional[float] = None   # back-side groove, else PCD + 10
    hole_markings: Optional[list] = None
    hole_start_angle: float = 90.0
    weld_strength: str = "25kgf"
    lid_drg: str = ""                    # REF.DRG.NO of the lid
    tie_wire_drg: str = ""               # REF.DRG.NO of the tie wire
    component_name: str = "LID WITH TIE WIRE"
    material: str = "AS LISTED"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    quantity: str = "01"
    date: str = ""
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class LidTieWireGeom:
    lid_od: float
    lid_thickness: float
    pcd: float
    num_holes: int
    hole_dia: float
    theta: float                     # angle between holes
    stack_dia: float
    num_tie_wires: int
    wire_angle: float                # angle between tie wires
    wire_width: float
    wire_thickness: float
    wire_start_dia: float            # derived: stack dia + offset
    weld_length: float
    groove_depth: float
    groove_width: float
    weld_space: float
    edge_angle: float
    pin_dia: float
    pin_upper: float
    groove_circle_dia: float
    hole_angles: list
    wire_angles: list
    hole_clearance: float            # smallest angle between any wire and any hole
    wire_anchor: float = 0.0         # bearing the first wire ended up on
    warnings: list = field(default_factory=list)


def _angsep(a, b):
    """Smallest absolute angle between two bearings, in degrees."""
    return abs(((a - b + 180.0) % 360.0) - 180.0)


def _place_wires(n: int, hole_angles: list) -> tuple:
    """Equally-spaced wire bearings, rotated to sit as far off the terminal holes
    as possible — so a wire is never laid over a hole, whatever the hole and wire
    counts happen to be. Returns (angles, clearance in degrees, first angle)."""
    step = 360.0 / n
    best_a0, best_clear = 0.0, -1.0
    a0 = 0.0
    while a0 < step:
        wires = [a0 + i * step for i in range(n)]
        clear = min((_angsep(w, h) for w in wires for h in hole_angles), default=180.0)
        if clear > best_clear:
            best_clear, best_a0 = clear, a0
        a0 += 0.5
    return ([best_a0 + i * step for i in range(n)], round(best_clear, 1), best_a0)


def compute_lid_tie_wire(p: LidTieWireParams) -> LidTieWireGeom:
    w: list[str] = []
    nh = max(int(p.num_holes or 1), 1)
    nw = max(int(p.num_tie_wires or 3), 1)
    theta = round(360.0 / nh, 2)
    hole_angles = [p.hole_start_angle + i * theta for i in range(nh)]
    wire_angles, clear, anchor = _place_wires(nw, hole_angles)

    # The wires begin `start_offset` in from the stack diameter TOWARDS THE
    # CENTRE — a radial measurement, so it comes off the diameter twice.
    start_dia = round(p.stack_dia - 2 * p.start_offset, 2)
    if start_dia <= 0:
        start_dia = round(p.stack_dia * 0.6, 2)
        w.append("Tie-wire start offset is larger than the stack; assumed 60% of it.")
    # a wire is 'clear' when its edge misses the hole edge — check in degrees
    r_start = start_dia / 2
    need = math.degrees(math.atan2((p.wire_width / 2 + p.hole_dia / 2), max(p.pcd / 2, 0.1)))
    if clear < need:
        w.append(f"Tie wires pass within {clear}° of a terminal hole "
                 f"({need:.1f}° needed to clear it) — check the hole and wire counts.")
    groove = p.groove_circle_dia if p.groove_circle_dia else round(p.pcd + 10, 2)
    pin_d = p.pin_dia if p.pin_dia else round(p.hole_dia / 2.5, 2)
    return LidTieWireGeom(
        lid_od=round(p.lid_od, 2), lid_thickness=round(p.lid_thickness, 2),
        pcd=round(p.pcd, 2), num_holes=nh, hole_dia=round(p.hole_dia, 2), theta=theta,
        stack_dia=round(p.stack_dia, 2), num_tie_wires=nw,
        wire_angle=round(360.0 / nw, 2), wire_width=round(p.wire_width, 2),
        wire_thickness=round(p.wire_thickness, 3), wire_start_dia=start_dia,
        weld_length=round(p.weld_length, 2),
        groove_depth=round(p.groove_depth, 2), groove_width=round(p.groove_width, 2),
        weld_space=round(p.weld_space, 2), edge_angle=float(p.edge_angle),
        pin_dia=round(pin_d, 2), pin_upper=round(p.pin_upper, 2),
        groove_circle_dia=groove,
        hole_angles=[round(a % 360, 2) for a in hole_angles],
        wire_angles=[round(a % 360, 2) for a in wire_angles],
        hole_clearance=clear, wire_anchor=anchor, warnings=w)


def _poly(pts, w=MED, fill="none", dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<polygon points="{" ".join(f"{_n(x)},{_n(y)}" for x, y in pts)}" '
            f'fill="{fill}" stroke="#111" stroke-width="{w}"{d}/>')


# BOM sits in the left column band, directly above the title block. The shared
# footer is called with show_bom=False so it only draws the material strip.
_BOM_COLS = [("S.No", BORDER_L, 26.0), ("COMPONENT", 26.0, 62.0),
             ("QTY/NOS", 62.0, 78.0), ("REF.DRG. NO", 78.0, 100.0)]
_BOM_RH = 5.6


def _bom_table(g: LidTieWireGeom, p: LidTieWireParams) -> tuple:
    """Parts list. Returns (svg, top y) so the views know where to stop."""
    rows = [("01", "LID", "01", p.lid_drg or "—"),
            ("02", "NICKEL TIE WIRE", f"{g.num_tie_wires:02d}", p.tie_wire_drg or "—")]
    s: list[str] = []
    hdr_top, hdr_bot = FOOT_TOP + 5.5, FOOT_TOP + 11.0
    x0, x1 = BORDER_L, _BOM_COLS[-1][2]
    top = hdr_top - len(rows) * _BOM_RH

    s.append(rect(x0, top, x1 - x0, hdr_bot - top, MED))
    s.append(line(x0, hdr_top, x1, hdr_top, MED))
    for _, a, b in _BOM_COLS:
        s.append(line(b, top, b, hdr_bot, THIN))
    for name, a, b in _BOM_COLS:
        s.append(text((a + b) / 2, hdr_bot - 1.7, name, 2.1, weight="bold"))
    for i, vals in enumerate(rows):
        ry = hdr_top - (i + 1) * _BOM_RH
        if i:
            s.append(line(x0, ry + _BOM_RH, x1, ry + _BOM_RH, THIN))
        for (_, a, b), v in zip(_BOM_COLS, vals):
            anc = "start" if b == 62.0 else "middle"
            xx = a + 1.5 if anc == "start" else (a + b) / 2
            s.append(text(xx, ry + _BOM_RH - 1.8, v, 2.0, anchor=anc))
    return s, top


def _views(g: LidTieWireGeom, p: LidTieWireParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = ax0 + (ax1 - ax0) * 0.44

    bom_svg, bom_top = _bom_table(g, p)
    ay1 = bom_top - 4                             # views must finish above the table

    # Size the top view from the height that is actually left once the section
    # and its note are accounted for, so nothing runs into the parts list.
    over = 18.0                                   # how far a wire runs past the rim
    PAD, GAP, SEC = 6.0, 12.0, 54.0
    avail = (ay1 - ay0) - PAD - GAP - SEC
    reach = g.lid_od / 2 + over * 0.6             # radius out to the wire tips
    sc = min((avail / 2) / max(reach, 0.1),       # fits the height
             76.0 / max(g.lid_od / 2 + over, 0.1),  # fits the width
             2.4)
    r = g.lid_od * sc / 2
    r_grv = g.groove_circle_dia * sc / 2
    r_pcd = g.pcd * sc / 2
    r_hole = max(g.hole_dia * sc / 2, 1.2)
    r_start = g.wire_start_dia * sc / 2
    r_out = r + over * sc * 0.6
    hww = max(g.wire_width * sc / 2, 1.0)
    cy = ay0 + PAD + r_out

    marks = (p.hole_markings if (p.hole_markings and len(p.hole_markings) == g.num_holes)
             else _markings(g.num_holes))

    # ---------------- BACK SIDE OF LID ----------------
    s.append(line(cx - r - 10, cy, cx + r + 10, cy, THIN, dash=C_LINE))
    s.append(line(cx, cy - r - 10, cx, cy + r + 10, THIN, dash=C_LINE))
    s.append(circle(cx, cy, r, THICK))                       # lid OD
    # The inner circle is the STACK diameter — it is the datum the wire start is
    # measured in from, so it has to be on the drawing or the 5 has nothing to
    # sit against. (The back groove circle is left off; it would sit close by and
    # read as the stack.)
    r_stack = g.stack_dia * sc / 2
    s.append(circle(cx, cy, r_stack, MED))

    for i, a in enumerate(g.hole_angles):                    # terminal holes + marks
        ar = math.radians(a)
        hx, hy = cx + r_pcd * math.cos(ar), cy - r_pcd * math.sin(ar)
        s.append(circle(hx, hy, r_hole, MED))
        s.append(circle(hx, hy, r_hole * 0.45, THIN))
        rm = r_pcd - r_hole - 4.0
        s.append(text(cx + rm * math.cos(ar), cy - rm * math.sin(ar) + 1.1,
                      marks[i], 3.6, weight="bold", rot=_mark_rot(a)))

    # ---------------- tie wires ----------------
    weld_r = r_start + g.weld_length * sc            # welded length, from the start
    for a in g.wire_angles:
        ar = math.radians(a)
        u = (math.cos(ar), -math.sin(ar))
        t = (-math.sin(ar), -math.cos(ar))

        def P(d, s_):
            return (cx + d * u[0] + s_ * t[0], cy + d * u[1] + s_ * t[1])
        s.append(_poly([P(r_start, -hww), P(r_out, -hww), P(r_out, hww), P(r_start, hww)]))
        s.append(line(*P(r_start, -hww), *P(r_start, hww), MED))
        # the welded stretch — spot welds, drawn as dots
        s.append(line(*P(weld_r, -hww), *P(weld_r, hww), THIN))
        nd = max(int((weld_r - r_start) / 2.4), 2)
        for k in range(nd):
            d = r_start + (weld_r - r_start) * (k + 0.5) / nd
            for lat in (-hww * 0.42, hww * 0.42):
                wx, wy = P(d, lat)
                s.append(circle(wx, wy, 0.45, THIN, fill="#111"))

    # ---------------- callouts ----------------
    # leader lands in the middle of the welded stretch, not past the end of it
    a0 = math.radians(g.wire_angles[0])
    rmid = (r_start + weld_r) / 2
    s.append(_leader(cx + rmid * math.cos(a0), cy - rmid * math.sin(a0),
                     cx + r * 0.55, cy - r - 16, "NICKEL TIE WIRE"))
    s.append(text(cx + r * 0.55 + 1.5, cy - r - 12.2, "SPOT WELDING", 2.8, anchor="start"))
    s.append(text(cx + r * 0.55 + 1.5, cy - r - 8.4, "ON LID", 2.8, anchor="start"))
    aL = math.radians(g.wire_angles[-1])
    s.append(_leader(cx + (r + 4) * math.cos(aL), cy - (r + 4) * math.sin(aL),
                     cx + r * 0.78, cy + r_out + 11,
                     f"NICKEL TIE WIRE - {g.num_tie_wires} NOs"))
    # Angle between the wires. Swept across the pair furthest from the callouts
    # at the top right, so the label cannot land on the leader text.
    if g.num_tie_wires >= 3:
        b0, b1 = g.wire_angles[1], g.wire_angles[2]
    else:
        b0, b1 = g.wire_angles[0], g.wire_angles[-1]
    rA = r + 10
    for b in (b0, b1):
        br = math.radians(b)
        s.append(line(cx, cy, cx + rA * math.cos(br), cy - rA * math.sin(br), THIN, dash=C_LINE))
    arc = [(cx + rA * math.cos(math.radians(b0 + (b1 - b0) * k / 14)),
            cy - rA * math.sin(math.radians(b0 + (b1 - b0) * k / 14))) for k in range(15)]
    s.append('<polyline points="' + " ".join(f"{_n(x)},{_n(y)}" for x, y in arc) +
             f'" fill="none" stroke="#111" stroke-width="{THIN}"/>')
    bm = math.radians((b0 + b1) / 2)
    s.append(text(cx + (rA + 7) * math.cos(bm), cy - (rA + 7) * math.sin(bm),
                  f"{_n(g.wire_angle)}° (TYP)", 2.8, weight="bold"))
    # Start offset, TYP — from the stack diameter in to where the wire begins.
    # The stack circle itself is not drawn; a short witness tick marks it on the
    # wire so the dimension still has something to measure from.
    aW = math.radians(g.wire_angles[0])
    uW = (math.cos(aW), -math.sin(aW))
    tW = (-math.sin(aW), -math.cos(aW))
    off = 10.0
    pA = (cx + r_stack * uW[0], cy + r_stack * uW[1])
    pB = (cx + r_start * uW[0], cy + r_start * uW[1])
    nrm = (-uW[1], uW[0])
    qA = (pA[0] + nrm[0] * off, pA[1] + nrm[1] * off)
    qB = (pB[0] + nrm[0] * off, pB[1] + nrm[1] * off)
    s.append(line(*pA, qA[0] + nrm[0] * 2, qA[1] + nrm[1] * 2, THIN))
    s.append(line(*pB, qB[0] + nrm[0] * 2, qB[1] + nrm[1] * 2, THIN))
    s.append(line(*qA, *qB, THIN))
    s.append(arrow(qA[0], qA[1], uW[0], uW[1]))
    s.append(arrow(qB[0], qB[1], -uW[0], -uW[1]))
    # the span IS the offset — measured radially in from the stack diameter
    s.append(text((qA[0] + qB[0]) / 2 + nrm[0] * 3.2, (qA[1] + qB[1]) / 2 + nrm[1] * 3.2,
                  f"{_n(p.start_offset)} (TYP)", 2.8))
    # tie wire width, taken from the TIE WIRE drawing
    aX = math.radians(g.wire_angles[-1])
    uX = (math.cos(aX), -math.sin(aX))
    tX = (-math.sin(aX), -math.cos(aX))
    rw = r_out - 2.0

    def W(lat, ext=0.0):
        d = rw + ext
        return (cx + d * uX[0] + lat * tX[0], cy + d * uX[1] + lat * tX[1])
    s.append(line(*W(-hww), *W(-hww, 7), THIN))
    s.append(line(*W(hww), *W(hww, 7), THIN))
    s.append(line(*W(-hww, 5), *W(hww, 5), THIN))
    s.append(arrow(*W(-hww, 5), -tX[0], -tX[1]))
    s.append(arrow(*W(hww, 5), tX[0], tX[1]))
    wlx, wly = W(0, 11)
    s.append(text(wlx, wly, f"{_n(g.wire_width)}", 2.8))
    # lid outside diameter and stack diameter — short leaders, close to the line
    ao = math.radians(152)
    s.append(_leader(cx + r * math.cos(ao), cy - r * math.sin(ao),
                     cx + (r + 9) * math.cos(ao), cy - (r + 9) * math.sin(ao),
                     f"Ø{_n(g.lid_od)}"))
    asd = math.radians(203)
    s.append(_leader(cx + r_stack * math.cos(asd), cy - r_stack * math.sin(asd),
                     cx + (r + 11) * math.cos(asd), cy - (r + 11) * math.sin(asd),
                     f"Ø{_n(g.stack_dia)}"))
    # section markers X-X, arrows up
    for sgn in (-1, 1):
        xX = cx + sgn * (r + 6)
        s.append(line(xX, cy, xX, cy + 8, THIN))
        s.append(arrow(xX, cy, 0, -1))
        s.append(text(xX, cy + 12, "X", 2.8, weight="bold"))

    # ---------------- SECTION X-X ----------------
    # The lid is cut as it is on the LID BLANK — sealing grooves set in from each
    # edge and the 6° tapered rim — with the terminal pins and their G.M. seal
    # passing through, and the tie wires standing on the face.
    tp = max(g.lid_thickness * sc * 1.8, 5.0)
    wt = max(g.wire_thickness * sc * 3.0, 1.2)
    wh = 15.0
    sy = cy + r_out + GAP + wh
    yT, yB = sy, sy + tp
    xL, xR = cx - r, cx + r
    gdp = min(g.groove_depth * sc * 1.8, tp * 0.45)
    gwp = max(g.groove_width * sc, 2.0)
    wsp = max(g.weld_space * sc, 2.0)
    taper = tp * math.tan(math.radians(g.edge_angle))
    ch = min(1.4, tp * 0.20)

    prof = [(xL, yT), (xL + wsp, yT), (xL + wsp, yT + gdp),
            (xL + wsp + gwp, yT + gdp), (xL + wsp + gwp, yT),
            (xR - wsp - gwp, yT), (xR - wsp - gwp, yT + gdp),
            (xR - wsp, yT + gdp), (xR - wsp, yT), (xR, yT),
            (xR - taper, yB - ch), (xR - taper - ch, yB),
            (xL + taper + ch, yB), (xL + taper, yB - ch)]
    # This is the BACK of the lid, so the section is flipped top for bottom —
    # the sealing grooves face down and the tapered rim is uppermost.
    mid = (yT + yB) / 2
    prof = [(x, 2 * mid - y) for x, y in prof]
    dpr = "M " + " L ".join(f"{_n(x)} {_n(y)}" for x, y in prof) + " Z"
    s.append(f'<path d="{dpr}" fill="url(#hatch)" stroke="none"/>')
    s.append(f'<path d="{dpr}" fill="none" stroke="#111" stroke-width="{THICK}"/>')

    # terminal pins, where the cutting plane crosses the PCD, each in its seal
    r_hp = max(g.hole_dia * sc / 2, 1.0)
    r_pp = max(g.pin_dia * sc / 2, 0.5)
    up = max(g.pin_upper * sc, 5.0)
    for px in sorted({round(r_pcd * math.cos(math.radians(a)), 2) for a in g.hole_angles}):
        x = cx + px
        s.append(f'<rect x="{_n(x - r_hp)}" y="{_n(yT)}" width="{_n(2 * r_hp)}" '
                 f'height="{_n(tp)}" fill="{GM_SEAL_BLUE}" stroke="none"/>')
        # flipped with the lid, so the pin stands proud on the underside here
        s.append(rect(x - r_pp, yT - up * 0.4, 2 * r_pp, tp + up * 0.4 + up, MED))
        for sgn in (-1, 1):
            s.append(line(x + sgn * r_hp, yT, x + sgn * r_hp, yB, THIN))

    s.append(text(cx, yB + up + 8, "SECTION X-X", 3.0, weight="bold"))
    s.append(text(cx, yB + up + 17,
                  f"NOTE : MINIMUM WELD STRENGTH = {p.weld_strength}", 2.8, weight="bold"))
    s += bom_svg
    return s


def render_lid_tie_wire_svg(g: LidTieWireGeom, p: LidTieWireParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>',
             _hatch_defs()]
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
