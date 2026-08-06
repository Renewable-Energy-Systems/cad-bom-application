"""Squib (electro-explosive igniter) CAD drawing — RES format.

A standard bought-in part, so every dimension is a fixed default rather than
something derived from the battery; all of them are editable in CAD Revision.

Types (user-selected):
  * single_head        -> titled "SQUIB"        (implemented)
  * single_head_wired  -> titled "SQUIB"        (added later)
  * double_head_igniter-> titled "DOUBLE HEAD IGNITER"   (added later)

Single Head — two views, both at the same scale:
  * TOP VIEW  : the substrate strip, tapering from its free end towards the head,
    with the EXPLOSIVE COMPOUND bead (D-shaped in plan) on the end. Dimensioned
    overall length, strip width, head width and head length.
  * SIDE VIEW : the strip on edge (thickness) with the bead as an ellipse.
    Dimensioned strip thickness and head thickness.

The squib resistance range is printed underneath, as on the standard sheet.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, THICK, MED, THIN, _n, line, rect, circle,
                        text, arrow, _hatch_defs, _header, _footer)
from .lid import _leader

# Colours taken from the standard sheet: kraft substrate + explosive bead.
STRIP_FILL = "#E3A24A"
HEAD_FILL = "#C0392B"
HEAD_FILL_SIDE = "#8E2820"

# type -> the TITLE that goes in the title block
SQUIB_TYPES = {
    "single_head": "SQUIB",
    "single_head_wired": "SQUIB",
    "double_head_igniter": "DOUBLE HEAD IGNITER",
}
# type -> how it is named to the user
SQUIB_TYPE_LABELS = {
    "single_head": "Single Head",
    "single_head_wired": "Single Head with Wired",
    "double_head_igniter": "Double Head Igniter",
}
IMPLEMENTED = {"single_head", "single_head_wired"}

# Single Head with Wired — body colours (charge body / base ferrule)
BODY_FILL = "#B5326A"
BASE_FILL = "#E3A24A"
CHARGE_FILL = "#A62A55"


@dataclass
class SquibParams:
    squib_type: str = "single_head"
    total_length: float = 12.50          # strip + head, overall
    head_length: float = 4.0             # explosive bead, along the axis
    head_width: float = 3.8              # bead across, in plan
    head_thickness: float = 2.23         # bead across, on edge
    head_corner_radius: Optional[float] = None   # strip-side corners; else 12% of width
    head_end_radius: Optional[float] = None      # free end; else half the width (full dome)
    strip_width: float = 3.9             # substrate at the free (wide) end
    strip_narrow_width: Optional[float] = None   # at the head; else 0.85 x wide
    strip_thickness: float = 0.7
    resistance_min: float = 0.80
    resistance_max: float = 1.20
    # ---- Single Head with Wired (standard sheet values) --------------------
    body_height: float = 11.0            # dome top -> bottom of the base
    charge_height: float = 8.0           # dome top -> charge/base joint
    body_width: float = 4.0              # front view, charge body
    base_width: float = 3.8              # front view, base ferrule
    body_depth: float = 3.2              # side view, charge body
    wire_length: float = 80.0            # leads, below the body
    wire_dia: float = 0.6
    wire_spacing: float = 1.5            # front view, centre to centre
    wire_span_inner: float = 1.4         # side view, inner width of the pair
    wire_span_outer: float = 1.8         # side view, outer width of the pair
    pellet_width_top: float = 3.4        # charge pellet, at the top
    pellet_width_bottom: float = 3.6     # charge pellet, where the ferrule starts
    body_width_tol: str = "±0.3"
    base_width_tol: str = "±0.2"
    body_depth_tol: str = "±0.2"
    body_height_tol: str = "±0.2"
    wire_length_tol: str = "±5"
    note_label: str = "NOTE - A"
    component_name: str = "SQUIB"
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
class SquibGeom:
    squib_type: str
    total_length: float
    strip_length: float
    head_length: float
    head_width: float
    head_thickness: float
    head_corner_radius: float
    head_end_radius: float
    strip_width: float
    strip_narrow_width: float
    strip_thickness: float
    resistance_min: float
    resistance_max: float
    # Single Head with Wired
    body_height: float = 0.0
    charge_height: float = 0.0
    base_height: float = 0.0             # derived: body_height - charge_height
    body_width: float = 0.0
    base_width: float = 0.0
    body_depth: float = 0.0
    wire_length: float = 0.0
    wire_dia: float = 0.0
    wire_spacing: float = 0.0
    wire_span_inner: float = 0.0
    wire_span_outer: float = 0.0
    pellet_width_top: float = 0.0
    pellet_width_bottom: float = 0.0
    warnings: list = field(default_factory=list)


def compute_squib(p: SquibParams) -> SquibGeom:
    w: list[str] = []
    st = p.squib_type if p.squib_type in SQUIB_TYPES else "single_head"
    if p.squib_type not in SQUIB_TYPES:
        w.append(f"Unknown squib type '{p.squib_type}'; drawing Single Head.")
    elif st not in IMPLEMENTED:
        w.append(f"'{SQUIB_TYPE_LABELS[st]}' is not drawn yet — showing the "
                 f"Single Head geometry on a '{SQUIB_TYPES[st]}' sheet.")
    strip_len = round(p.total_length - p.head_length, 2)
    if strip_len <= 0:
        strip_len = round(p.total_length * 0.6, 2)
        w.append("Head length is not shorter than the overall length; strip assumed 60%.")
    narrow = p.strip_narrow_width if p.strip_narrow_width else round(p.strip_width * 0.85, 2)
    if narrow > p.strip_width:
        narrow = p.strip_width
        w.append("Strip narrow end was wider than the free end; taper removed.")
    corner = (p.head_corner_radius if p.head_corner_radius is not None
              else round(p.head_width * 0.12, 2))
    if corner > p.head_width / 2:
        corner = round(p.head_width / 2, 2)
        w.append("Head corner radius was larger than half the head width; clamped.")
    # Free end is a full dome by default (radius = half the head width). The
    # straight on that end of the bead is the short run of top and bottom edge
    # before the dome starts, not a flat across the tip.
    end_r = (p.head_end_radius if p.head_end_radius is not None
             else round(p.head_width / 2, 2))
    if end_r > p.head_width / 2:
        end_r = round(p.head_width / 2, 2)
        w.append("Head end radius was larger than half the head width; clamped "
                 "to a full dome (no straight left on the free end).")
    # Wired type: the base ferrule is what's left of the body under the charge.
    base_h = round(p.body_height - p.charge_height, 2)
    if st == "single_head_wired" and base_h <= 0:
        base_h = round(p.body_height * 0.25, 2)
        w.append("Charge height is not shorter than the body height; base "
                 "ferrule assumed 25% of the body.")
    return SquibGeom(
        squib_type=st, total_length=round(p.total_length, 2), strip_length=strip_len,
        head_length=round(p.head_length, 2), head_width=round(p.head_width, 2),
        head_thickness=round(p.head_thickness, 2), head_corner_radius=round(corner, 2),
        head_end_radius=round(end_r, 2),
        body_height=round(p.body_height, 2), charge_height=round(p.charge_height, 2),
        base_height=base_h, body_width=round(p.body_width, 2),
        base_width=round(p.base_width, 2), body_depth=round(p.body_depth, 2),
        wire_length=round(p.wire_length, 2), wire_dia=round(p.wire_dia, 2),
        wire_spacing=round(p.wire_spacing, 2),
        wire_span_inner=round(p.wire_span_inner, 2),
        wire_span_outer=round(p.wire_span_outer, 2),
        pellet_width_top=round(p.pellet_width_top, 2),
        pellet_width_bottom=round(p.pellet_width_bottom, 2),
        strip_width=round(p.strip_width, 2),
        strip_narrow_width=round(narrow, 2), strip_thickness=round(p.strip_thickness, 2),
        resistance_min=p.resistance_min, resistance_max=p.resistance_max, warnings=w)


def _poly_fill(pts, fill, w=MED):
    return (f'<polygon points="{" ".join(f"{_n(x)},{_n(y)}" for x, y in pts)}" '
            f'fill="{fill}" stroke="#111" stroke-width="{w}"/>')


def _head(xj, x1, cy, half, fill, corner=0.0, end=0.0):
    """The explosive bead in plan — a rounded rectangle.

    Both ends are square with filleted corners, so the free end keeps a short
    STRAIGHT section between its two radii rather than being one continuous
    dome; that is how it is drawn on the standard sheet. The strip-side corners
    take their own (smaller) radius.
    """
    L = x1 - xj
    er = max(0.0, min(end, half))
    cr = max(0.0, min(corner, half))
    if cr + er > L:                       # never let the two ends overlap
        k = L / (cr + er)
        cr, er = cr * k * 0.98, er * k * 0.98

    def arc(r, x, y):
        return f"A {_n(r)} {_n(r)} 0 0 1 {_n(x)} {_n(y)}"

    d = [f"M {_n(xj + cr)} {_n(cy - half)}", f"L {_n(x1 - er)} {_n(cy - half)}"]
    d += [arc(er, x1, cy - half + er)] if er > 0 else [f"L {_n(x1)} {_n(cy - half)}"]
    d += [f"L {_n(x1)} {_n(cy + half - er)}"]          # straight free end
    d += [arc(er, x1 - er, cy + half)] if er > 0 else [f"L {_n(x1)} {_n(cy + half)}"]
    d += [f"L {_n(xj + cr)} {_n(cy + half)}"]
    if cr > 0:
        d += [arc(cr, xj, cy + half - cr), f"L {_n(xj)} {_n(cy - half + cr)}",
              arc(cr, xj + cr, cy - half)]
    else:
        d += [f"L {_n(xj)} {_n(cy + half)}", f"L {_n(xj)} {_n(cy - half)}"]
    return (f'<path d="{" ".join(d)} Z" fill="{fill}" stroke="#111" '
            f'stroke-width="{MED}"/>')


def _dim_h(y, x1, x2, label, size=3.2, above=True):
    return [line(x1, y, x2, y, THIN), arrow(x1, y, -1, 0), arrow(x2, y, 1, 0),
            text((x1 + x2) / 2, y - 1.6 if above else y + 3.4, label, size)]


def _dim_v(x, y1, y2, label, size=3.2, side="left"):
    """Vertical dimension. On a short span (a thin strip) the label would sit on
    top of its own arrows, so it moves outside the extension instead."""
    tx = x - 1.4 if side == "left" else x + 1.4
    span = abs(y2 - y1)
    ty = (y1 + y2) / 2 if span >= size * 3.2 else min(y1, y2) - 3.0
    return [line(x, y1, x, y2, THIN), arrow(x, y1, 0, -1), arrow(x, y2, 0, 1),
            text(tx, ty, label, size, rot=90)]


def _views(g: SquibGeom, p: SquibParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA

    # one scale for both views so they stay in true proportion
    sc = min(112.0 / max(g.total_length, 0.1),
             30.0 / max(g.head_width, 0.1),
             24.0 / max(g.head_thickness, 0.1))
    L = g.total_length * sc
    SL = g.strip_length * sc
    HL = g.head_length * sc
    hw, nw = g.strip_width * sc / 2, g.strip_narrow_width * sc / 2
    hh = g.head_width * sc / 2
    ht = g.head_thickness * sc / 2
    tt = g.strip_thickness * sc / 2

    x0 = ax0 + ((ax1 - ax0) - L) / 2
    xj = x0 + SL                      # strip -> head junction
    x1 = x0 + L

    # ---------------- TOP VIEW ----------------
    cy = ay0 + 34 + hh
    s.append(_poly_fill([(x0, cy - hw), (xj, cy - nw), (xj, cy + nw), (x0, cy + hw)],
                        STRIP_FILL))
    er = g.head_end_radius * sc
    s.append(_head(xj, x1, cy, hh, HEAD_FILL,
                   corner=g.head_corner_radius * sc, end=er))

    yTop = cy - hh - 14
    s.append(line(x0, cy - hw, x0, yTop - 2, THIN))
    s.append(line(x1, cy - hh, x1, yTop - 2, THIN))
    s += _dim_h(yTop, x0, x1, f"{_n(g.total_length)}", 3.4)
    xw = x0 - 10
    s.append(line(x0, cy - hw, xw - 2, cy - hw, THIN))
    s.append(line(x0, cy + hw, xw - 2, cy + hw, THIN))
    s += _dim_v(xw, cy - hw, cy + hw, f"{_n(g.strip_width)}", 3.4, side="left")
    xh = x1 + 11
    # The bead's flat sides lie on the same line as these extension lines, so if
    # they started at the dome they would join up into one long straight edge and
    # the bead would read as part-straight. Start them clear of the tip instead.
    s.append(line(x1 + 2.5, cy - hh, xh + 2, cy - hh, THIN))
    s.append(line(x1 + 2.5, cy + hh, xh + 2, cy + hh, THIN))
    s += _dim_v(xh, cy - hh, cy + hh, f"{_n(g.head_width)}", 3.4, side="right")
    yBot = cy + hh + 13
    s.append(line(xj, cy + hh, xj, yBot + 2, THIN))
    s.append(line(x1, cy + hh, x1, yBot + 2, THIN))
    s += _dim_h(yBot, xj, x1, f"{_n(g.head_length)}", 3.4, above=False)
    # EXPLOSIVE COMPOUND leader
    s.append(_leader(x1 - er * 0.7, cy - hh * 0.55, x1 + 6, yTop + 3, "EXPLOSIVE"))
    s.append(text(x1 + 7.5, yTop + 7, "COMPOUND", 3.2, anchor="start"))

    # ---------------- SIDE VIEW ----------------
    sy = cy + hh + 42 + ht
    # On edge the bead is a full oval, rounded at both ends (the plan view keeps
    # its D form). Run the strip in only as far as the point where the oval is
    # exactly as tall as the strip, so the two meet flush — stopping it at the
    # oval's leftmost tangent instead leaves the cusp between a straight edge and
    # a near-vertical curve.
    k = min(tt / ht, 1.0) if ht > 0 else 1.0
    inset = (HL / 2) * (1 - math.sqrt(max(0.0, 1 - k * k)))
    s.append(rect(x0, sy - tt, SL + inset, 2 * tt, MED, fill=STRIP_FILL))
    s.append(f'<ellipse cx="{_n(xj + HL / 2)}" cy="{_n(sy)}" rx="{_n(HL / 2)}" '
             f'ry="{_n(ht)}" fill="{HEAD_FILL_SIDE}" stroke="#111" stroke-width="{MED}"/>')
    xt = x0 - 10
    s.append(line(x0, sy - tt, xt - 2, sy - tt, THIN))
    s.append(line(x0, sy + tt, xt - 2, sy + tt, THIN))
    s += _dim_v(xt, sy - tt, sy + tt, f"{_n(g.strip_thickness)}", 3.4, side="left")
    xe = x1 + 11
    s.append(line(x1 + 2.5, sy - ht, xe + 2, sy - ht, THIN))
    s.append(line(x1 + 2.5, sy + ht, xe + 2, sy + ht, THIN))
    s += _dim_v(xe, sy - ht, sy + ht, f"{_n(g.head_thickness)}", 3.4, side="right")

    # resistance note
    s.append(text((ax0 + ax1) / 2, sy + ht + 30,
                  f"SQUIB RESISTANCE: {g.resistance_min:.2f} TO {g.resistance_max:.2f}Ω",
                  4.0, weight="bold"))
    return s


# --------------------------------------------------------------------------- #
# Single Head with Wired
# --------------------------------------------------------------------------- #
def _vt_h(x1, x2, y, val, tol, size=3.8, above=True, tdx=0.0):
    """Horizontal dimension with the tolerance set as a superscript, as on the
    standard sheet (e.g. 4 with ±0.3 above and to the right of it). `tdx` slides
    the label sideways so it can clear whatever the dimension spans."""
    s = [line(x1, y, x2, y, THIN), arrow(x1, y, -1, 0), arrow(x2, y, 1, 0)]
    cx = (x1 + x2) / 2 + tdx
    if tdx:
        # carry the dimension line out to the offset label so the two read as one
        s.append(line(x2 if tdx > 0 else x1, y,
                      cx - size * 0.8 if tdx > 0 else cx + size * 0.8, y, THIN))
    ty = y - 2.0 if above else y + size + 0.6
    s.append(text(cx - size * 0.35, ty, val, size))
    if tol:
        s.append(text(cx + size * 0.45, ty - size * 0.55, tol, size * 0.62, anchor="start"))
    return s


def _vt_v(y1, y2, x, val, tol, size=3.8, side="left"):
    """Vertical (rotated) dimension, tolerance as a superscript on the value."""
    s = [line(x, y1, x, y2, THIN), arrow(x, y1, 0, -1), arrow(x, y2, 0, 1)]
    cy = (y1 + y2) / 2
    tx = x - 1.6 if side == "left" else x + 1.6
    s.append(text(tx, cy + size * 0.4, val, size, rot=90))
    if tol:
        s.append(text(tx - size * 0.5, cy - size * 0.9, tol, size * 0.62, rot=90))
    return s


def _wire_break(x, w, y):
    """Conventional break across a lead."""
    return [line(x - w * 0.9, y + 1.5, x + w * 0.9, y - 1.5, THIN),
            line(x - w * 0.9, y + 4.0, x + w * 0.9, y + 1.0, THIN)]


TAPER_DEG = 25.0        # side taper below the top radius — short, so the shoulder
TOP_RATIO = 0.88        # stays narrow and the taper reads as a chamfer, not a cone
CLEARANCE = 0.10        # pellet-to-wall gap, as a fraction of the body width


def _cap(yTop, w):
    """Top-cap construction: small side tapers running into a tangent arc.

    Returns (R, yc, yT, wt, yS) — the arc radius and centre, the height and
    half-width of the tangent point, and the shoulder where the taper starts.
    The arc is tangent to the taper, so the two meet without a kink and the
    widest point of the body is still the dimensioned width.
    """
    a = math.radians(TAPER_DEG)
    wt = TOP_RATIO * w
    R = wt / math.cos(a)
    yc = yTop + R                       # arc centre, on the axis
    yT = yc - R * math.sin(a)           # tangent point
    yS = yT + (w - wt) / math.tan(a)    # shoulder
    return R, yc, yT, wt, yS


def _half_width(y, w, R, yc, yT, yS):
    """Outer half-width of the body at height y."""
    if y >= yS:
        return w
    if y >= yT:
        return w - (yS - y) * math.tan(math.radians(TAPER_DEG))
    d = yc - y
    return math.sqrt(max(R * R - d * d, 0.0))


def _wired_body(cx, yTop, W, Wb, H, Hc, offsets, pel_top, pel_bot, lead_w) -> list[str]:
    """The capsule: domed charge body over a straight base ferrule.

    The internals are schematic — they show how the device is built rather than
    exact geometry: a bridge wire strung between the two leads at the top of the
    dome, the pyrotechnic charge packed around it, and the leads carried down
    through the charge and out of the ferrule.
    """
    s: list[str] = []
    w, wb = W / 2, Wb / 2
    yj = yTop + Hc                     # charge -> ferrule joint
    yb = yTop + H
    R, yc, yT, wt, yS = _cap(yTop, w)

    # ---- outer encapsulation: tapered shoulders into a tangent top arc ----
    s.append(f'<path d="M {_n(cx - w)} {_n(yj)} L {_n(cx - w)} {_n(yS)} '
             f'L {_n(cx - wt)} {_n(yT)} '
             f'A {_n(R)} {_n(R)} 0 0 1 {_n(cx + wt)} {_n(yT)} '
             f'L {_n(cx + w)} {_n(yS)} L {_n(cx + w)} {_n(yj)} Z" '
             f'fill="{BODY_FILL}" stroke="#111" stroke-width="{MED}"/>')

    # ---- resin ferrule: starts exactly where the encapsulation ends ----
    # It is narrower than the body, so it leaves the encapsulation at full width
    # for a short collar and then steps in. Without that the outline would not
    # close at the corner and a notch of white would show through the joint.
    col = min(1.8, (yb - yj) * 0.22)
    s.append(f'<polygon points="{_n(cx - w)},{_n(yj)} {_n(cx - w)},{_n(yj + col)} '
             f'{_n(cx - wb)},{_n(yj + col)} {_n(cx - wb)},{_n(yb)} '
             f'{_n(cx + wb)},{_n(yb)} {_n(cx + wb)},{_n(yj + col)} '
             f'{_n(cx + w)},{_n(yj + col)} {_n(cx + w)},{_n(yj)}" '
             f'fill="{BASE_FILL}" stroke="#111" stroke-width="{MED}"/>')

    # ---- charge pellet: straight-sided, no chamfers on its edges ----
    # Its top sits at the shoulder, where the cap curve runs into the parallel
    # sides, so the two outlines meet. Narrower at the top than at the ferrule.
    ptw, pbw = pel_top / 2, pel_bot / 2
    pel = (f"M {_n(cx - ptw)} {_n(yS)} L {_n(cx + ptw)} {_n(yS)} "
           f"L {_n(cx + pbw)} {_n(yj)} L {_n(cx - pbw)} {_n(yj)} Z")
    s.append(f'<path d="{pel}" fill="{CHARGE_FILL}" stroke="none"/>')
    # hatch is the pellet path's own fill, so it cannot reach the encapsulation
    # or any of the metallic parts
    s.append(f'<path d="{pel}" fill="url(#hatch)" stroke="none"/>')
    s.append(f'<path d="{pel}" fill="none" stroke="#111" stroke-width="{THIN}"/>')

    # ---- leads: shown only where they enter, at the top of the pellet. They
    # ---- are not drawn through the pellet or the ferrule.
    yStub0 = yTop + R * 0.34
    yStub1 = yS + (yj - yS) * 0.05
    for off in offsets:
        s.append(rect(cx + off - lead_w / 2, yStub0, lead_w, yStub1 - yStub0, MED))
    # the connection across them sits at MID height of the stubs, not at the top
    yBridge = (yStub0 + yStub1) / 2
    s.append(line(cx + offsets[0], yBridge, cx + offsets[-1], yBridge, MED))

    # ---- centre line between the leads: runs past the pink at the top and past
    # ---- the orange at the bottom, carrying three points across the pellet
    ext = max(W * 0.28, 2.5)
    s.append(line(cx, yTop - ext, cx, yb + ext, THIN))
    for k in (1, 2, 3):
        s.append(circle(cx, yS + (yj - yS) * k / 4,
                        max(W * 0.032, 0.32), THIN, fill="#111"))
    return s, yBridge


def _views_wired(g: SquibGeom, p: SquibParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA

    sc = 3.6                                     # body scale (mm -> paper)
    H = g.body_height * sc
    Hc = g.charge_height * sc
    Wf, Wfb = g.body_width * sc, g.base_width * sc
    Ws = g.body_depth * sc
    Wsb = max(Ws - (g.body_width - g.base_width) * sc, Ws * 0.8)
    wd = max(g.wire_dia * sc, 1.2)
    # Leads run unbroken — no conventional break across them. They are not to
    # scale against the body; the 80 dimension states the true length.
    RUN = 84.0

    # Pellet widths: the front view's are given, and the side view keeps the same
    # wall thickness top and bottom so the encapsulation is consistent.
    pTopF, pBotF = g.pellet_width_top * sc, g.pellet_width_bottom * sc
    wallT = (g.body_width - g.pellet_width_top) / 2
    wallB = (g.body_width - g.pellet_width_bottom) / 2
    pTopS = max(g.body_depth - 2 * wallT, g.body_depth * 0.4) * sc
    pBotS = max(g.body_depth - 2 * wallB, g.body_depth * 0.45) * sc

    cxF = ax0 + 46
    cxS = ax0 + 132
    yTop = ay0 + 22
    yBase = yTop + H
    yEnd = yBase + RUN

    # ---------------- FRONT VIEW ----------------
    half = g.wire_spacing * sc / 2
    body, yBridgeF = _wired_body(cxF, yTop, Wf, Wfb, H, Hc, (-half, half), pTopF, pBotF, wd)
    s += body
    for sgn in (-1, 1):
        s.append(rect(cxF + sgn * half - wd / 2, yBase, wd, yEnd - yBase, MED))
    # dims — the width extension lines run the length of the encapsulation, down
    # to where the pellet ends, so the 4 reads against the 3.6 below it
    s += _vt_h(cxF - Wf / 2, cxF + Wf / 2, yTop - 12, f"{_n(g.body_width)}", p.body_width_tol)
    s.append(line(cxF - Wf / 2, yTop + Hc, cxF - Wf / 2, yTop - 14, THIN))
    s.append(line(cxF + Wf / 2, yTop + Hc, cxF + Wf / 2, yTop - 14, THIN))
    x11 = cxF - Wf / 2 - 22
    s.append(line(cxF - Wf / 2, yTop, x11 - 2, yTop, THIN))
    s.append(line(cxF - Wfb / 2, yBase, x11 - 2, yBase, THIN))
    s += _vt_v(yTop, yBase, x11, f"{_n(g.body_height)}", "")
    x8 = cxF - Wf / 2 - 11
    s.append(line(cxF - Wf / 2, yTop + Hc, x8 - 2, yTop + Hc, THIN))
    s += _vt_v(yTop, yTop + Hc, x8, f"{_n(g.charge_height)}", "")
    # base width — label pushed right so it clears the leads it spans
    s += _vt_h(cxF - Wfb / 2, cxF + Wfb / 2, yBase + 13, f"{_n(g.base_width)}",
               p.base_width_tol, tdx=Wf / 2 + 13)
    s.append(line(cxF - Wfb / 2, yBase, cxF - Wfb / 2, yBase + 15, THIN))
    s.append(line(cxF + Wfb / 2, yBase, cxF + Wfb / 2, yBase + 15, THIN))
    s += _vt_h(cxF - half, cxF + half, yEnd + 10, f"{_n(g.wire_spacing)}", "", size=3.4)
    s.append(line(cxF - half, yEnd, cxF - half, yEnd + 12, THIN))
    s.append(line(cxF + half, yEnd, cxF + half, yEnd + 12, THIN))
    # NOTE - A calls out the connection across the leads
    s.append(_leader(cxF + half * 0.55, yBridgeF, cxF + Wf / 2 + 12, yTop - 3,
                     p.note_label))

    # ---------------- SIDE VIEW ----------------
    # Edge-on, 1.4 is the CLEAR gap between the two leads and 1.8 the overall
    # width across them, so each lead shows (1.8 - 1.4)/2 wide.
    inner = g.wire_span_inner * sc / 2           # half the clear gap
    outer = g.wire_span_outer * sc / 2           # half the overall width
    lw = max(outer - inner, 0.5)                 # apparent width of one lead
    body, _yBridgeS = _wired_body(cxS, yTop, Ws, Wsb, H, Hc,
                                  (-(inner + outer) / 2, (inner + outer) / 2),
                                  pTopS, pBotS, lw)
    s += body
    for sgn in (-1, 1):
        x = cxS + sgn * outer - (lw if sgn > 0 else 0)
        s.append(rect(x, yBase, lw, yEnd - yBase, MED))
    # dims
    s += _vt_h(cxS - Ws / 2, cxS + Ws / 2, yTop - 12, f"{_n(g.body_depth)}", p.body_depth_tol)
    s.append(line(cxS - Ws / 2, yTop + Hc, cxS - Ws / 2, yTop - 14, THIN))
    s.append(line(cxS + Ws / 2, yTop + Hc, cxS + Ws / 2, yTop - 14, THIN))
    xh = cxS - Ws / 2 - 12
    s.append(line(cxS - Ws / 2, yTop, xh - 2, yTop, THIN))
    s.append(line(cxS - Wsb / 2, yBase, xh - 2, yBase, THIN))
    s += _vt_v(yTop, yBase, xh, f"{_n(g.body_height)}", p.body_height_tol)
    xw = cxS - Ws / 2 - 26
    s.append(line(cxS - outer, yEnd, xw - 2, yEnd, THIN))
    s += _vt_v(yBase, yEnd, xw, f"{_n(g.wire_length)}", p.wire_length_tol)
    # Lead spans. Extension lines stop on the surfaces each dimension refers to:
    # the INNER faces for the clear gap, the OUTER faces for the overall width.
    y14, y18 = yBase + 9, yBase + 18
    for sgn in (-1, 1):
        s.append(line(cxS + sgn * inner, yBase, cxS + sgn * inner, y14 + 2, THIN))
        s.append(line(cxS + sgn * outer, yBase, cxS + sgn * outer, y18 + 2, THIN))
    s += _vt_h(cxS - inner, cxS + inner, y14, f"{_n(g.wire_span_inner)}", "",
               size=3.4, tdx=outer + 11)
    s += _vt_h(cxS - outer, cxS + outer, y18, f"{_n(g.wire_span_outer)}", "",
               size=3.4, tdx=outer + 11)
    s += _vt_h(cxS - outer, cxS + outer, yEnd + 10, f"Ø{_n(g.wire_dia)}", "", size=3.4)
    s.append(line(cxS - outer, yEnd, cxS - outer, yEnd + 12, THIN))
    s.append(line(cxS + outer, yEnd, cxS + outer, yEnd + 12, THIN))
    return s


def render_squib_svg(g: SquibGeom, p: SquibParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>',
             _hatch_defs()]
    parts += _header(g, p)
    parts += _views_wired(g, p) if g.squib_type == "single_head_wired" else _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
