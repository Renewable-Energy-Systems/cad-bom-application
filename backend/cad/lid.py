"""Lid Blank CAD drawing — geometry + RES-format SVG generator.

Reuses the RES sheet frame/header/footer helpers from `container.py`.

Dimensions (per Guidelines):
  Lid Blank OD   = Container ID - 0.05            (Table 4a)
  Thickness      = Table 4b by container OD
  Groove W/D     = Table 3 by container OD
  PCD, N holes, hole dia, pin dia  = Table 1 (customer) else formulas:
     PCD (holes)  = cathode dia - clearance (clearance from UI)
     N holes      = number of leads (+ve,-ve,EI1,EI2)
     angle theta  = 360 / N
     hole dia     = pin dia * 2.5
  Welding space  = container wall thickness (left in from the OD)
  Edge: 6 deg taper (fits inside container) + 0.5x45 chamfer + chamfer all over.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .tables import (groove_dims, lid_blank_od, lid_blank_thickness,
                     lid_finished_od, container_wall)
from .container import (PW, PH, AREA, BORDER_L, BORDER_R, THICK, MED, THIN,
                        C_LINE, C_HID, _n, line, rect, circle, text, arrow,
                        dim_h, dim_v, _arc, _hatch_defs, _header, _footer)

# Per guidelines: "Take the 6° angle and use a 0.5 × 45° chamfer."
CHAMFER_EDGE = "0.5×45°"
HOLE_CHAMFER = "0.3×45°"        # pin-hole chamfer (top & bottom)
EDGE_ANGLE = 6.0
LETTER_SIZE = 2.5
MARK_SIZE = 2.7                 # terminal marking font (bigger, radial)
BACK_GROOVE = 0.3              # back-side groove depth & width (mm)


def _mark_rot(ar_deg: float) -> float:
    """Rotation so a terminal marking stands RADIALLY (top of the letters points
    outward): top hole upright, bottom upside-down, sides rotated 90°."""
    return -ar_deg + 90


def _markings(n: int) -> list[str]:
    """Terminal markings: +ve and -ve are DIAMETRICALLY OPPOSITE. The holes on
    ONE side (going + -> -) are all EI1; the holes on the OTHER side (- -> +) are
    all EI2. (EI1/EI2 = electrical igniter 1/2.)"""
    m: list[str] = [""] * n
    half = n // 2
    m[0] = "+"
    m[half] = "−"
    for i in range(1, half):
        m[i] = "EI1"          # + -> - side
    for i in range(half + 1, n):
        m[i] = "EI2"          # - -> + side
    return m


def _tol(nom: float, is_od: bool = False) -> str:
    """IS 2102 (medium) tolerance string '±x'; lid-blank OD uses ±0.05 (Table 4a)."""
    if is_od:
        return "±0.05"
    n = abs(nom)
    for lo, hi, d in [(0.5, 6, 0.1), (6, 30, 0.2), (30, 120, 0.3), (120, 400, 0.5)]:
        if (lo <= n <= hi) if lo == 0.5 else (lo < n <= hi):
            return f"±{d}"
    return ""


@dataclass
class LidParams:
    container_od: float
    container_id: Optional[float] = None
    container_wall: Optional[float] = None
    container_type: str = "deep_drawn"
    cathode_dia: Optional[float] = None
    pcd: Optional[float] = None
    num_holes: Optional[int] = None
    pin_dia: Optional[float] = None
    hole_dia: Optional[float] = None
    clearance: float = 1.0
    hole_markings: Optional[list] = None   # from customer drawing if given
    hole_angles: Optional[list] = None     # per-hole angle (deg) if non-uniform
    # editable overrides (CAD Revision) — blank => computed/default
    thickness: Optional[float] = None
    groove_depth: Optional[float] = None
    groove_width: Optional[float] = None
    weld_space: Optional[float] = None
    edge_chamfer: Optional[str] = None     # e.g. "0.5×45°"
    hole_chamfer: Optional[str] = None     # e.g. "0.3×45°"
    edge_angle: Optional[float] = None     # taper angle, deg (default 6)
    letter_size: Optional[float] = None    # marking letter size, mm
    back_groove: Optional[float] = None    # back groove deep/wide, mm
    hole_start_angle: Optional[float] = None  # position of first hole, deg
    visual_criteria: Optional[str] = None  # note printed on the sheet
    include_section: bool = True
    include_detail: bool = True
    # sheet/footer meta (same attrs _footer reads)
    component_name: str = "LID BLANK"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    date: str = ""
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class LidGeom:
    lid_od: float
    thickness: float
    groove_depth: float
    groove_width: float
    groove_band: str
    wall: float
    weld_space: float
    groove_circle_dia: float       # back-side groove circle (~cathode/stack dia)
    pcd: float
    num_holes: int
    theta: float
    hole_dia: float
    pin_dia: Optional[float]
    edge_chamfer: str = CHAMFER_EDGE
    hole_chamfer: str = HOLE_CHAMFER
    edge_angle: float = EDGE_ANGLE
    letter_size: float = LETTER_SIZE
    back_groove: float = BACK_GROOVE
    hole_start_angle: float = 90.0
    visual_criteria: str = ""
    warnings: list = field(default_factory=list)


def compute_lid_geometry(p: LidParams) -> LidGeom:
    w: list[str] = []
    od = p.container_od
    wall = p.container_wall
    if wall is None:
        cw = container_wall(od, p.container_type)
        wall = cw["wall"] if cw else 1.0
    cid = p.container_id if p.container_id is not None else round(od - 2 * wall, 2)

    lid_od = lid_blank_od(cid)                  # Table 4a
    thk = p.thickness if p.thickness else lid_blank_thickness(od)   # Table 4b (or override)
    if thk is None:
        thk = 2.5; w.append(f"OD {od} outside Table 4(b); thickness assumed 2.5.")
    gr = groove_dims(od)                        # Table 3
    gdepth = p.groove_depth if p.groove_depth else gr["depth"]
    gwidth = p.groove_width if p.groove_width else gr["width"]

    # number of holes / leads
    n = p.num_holes
    if not n:
        n = 4; w.append("Number of holes not found (Table 1); assumed 4 leads.")
    n = int(n)
    theta = round(360.0 / n, 2)

    # PCD: Table 1 else cathode dia - clearance
    pcd = p.pcd
    if not pcd:
        if p.cathode_dia:
            pcd = round(p.cathode_dia - p.clearance, 2)
        else:
            pcd = round(cid * 0.5, 2); w.append("PCD not found and no cathode dia; approximated.")

    # pin dia + hole dia
    pin = p.pin_dia
    hole = p.hole_dia
    if not hole:
        if pin:
            hole = round(pin * 2.5, 2)          # hole = pin * 2.5
        else:
            hole = round(0.075 * lid_od, 2); w.append("Pin/hole dia not given; approximated (enter pin dia).")

    groove_circle = p.cathode_dia if p.cathode_dia else round(lid_od - 2 * wall, 2)
    weld = p.weld_space if p.weld_space else wall

    return LidGeom(lid_od=lid_od, thickness=thk, groove_depth=gdepth, groove_width=gwidth,
                   groove_band=gr["band"], wall=wall, weld_space=weld, groove_circle_dia=groove_circle,
                   pcd=pcd, num_holes=n, theta=theta, hole_dia=hole, pin_dia=pin,
                   edge_chamfer=p.edge_chamfer or CHAMFER_EDGE,
                   hole_chamfer=p.hole_chamfer or HOLE_CHAMFER,
                   edge_angle=p.edge_angle if p.edge_angle else EDGE_ANGLE,
                   letter_size=p.letter_size if p.letter_size else LETTER_SIZE,
                   back_groove=p.back_groove if p.back_groove else BACK_GROOVE,
                   hole_start_angle=p.hole_start_angle if p.hole_start_angle is not None else 90.0,
                   visual_criteria=p.visual_criteria or "", warnings=w)


def _arc_up(cx, cy, R, d0, d1, n=12):
    return [(cx + R * math.cos(math.radians(d0 + (d1 - d0) * i / n)),
             cy - R * math.sin(math.radians(d0 + (d1 - d0) * i / n))) for i in range(n + 1)]


def _dia_dim(cx, cy, R, ang, label):
    """Diameter dimension line through the centre at `ang` (deg), arrows + Ø label."""
    a = math.radians(ang)
    dx, dy = math.cos(a), -math.sin(a)
    x1, y1, x2, y2 = cx - R * dx, cy - R * dy, cx + R * dx, cy + R * dy
    end = "start" if dx >= 0 else "end"
    return "".join([line(x1, y1, x2, y2, THIN), arrow(x1, y1, -dx, -dy), arrow(x2, y2, dx, dy),
                    text(x2 + dx * 2.5, y2 + dy * 2.5 + 0.8, label, 2.2, anchor=end)])


def _angle_dim(cx, cy, r_lines, r_arc, a0, a1, label):
    """Angular dimension between two radii a0..a1 (deg, y-up)."""
    out = []
    for ad in (a0, a1):
        a = math.radians(ad)
        out.append(line(cx, cy, cx + r_lines * math.cos(a), cy - r_lines * math.sin(a), THIN))
    pts = _arc_up(cx, cy, r_arc, a0, a1, 14)
    out.append('<polyline points="' + " ".join(f"{_n(x)},{_n(y)}" for x, y in pts) +
               f'" fill="none" stroke="#111" stroke-width="{THIN}"/>')
    a0r, a1r = math.radians(a0), math.radians(a1)
    out.append(arrow(cx + r_arc * math.cos(a0r), cy - r_arc * math.sin(a0r), math.sin(a0r), math.cos(a0r)))
    out.append(arrow(cx + r_arc * math.cos(a1r), cy - r_arc * math.sin(a1r), -math.sin(a1r), -math.cos(a1r)))
    am = math.radians((a0 + a1) / 2)
    out.append(text(cx + (r_arc + 3) * math.cos(am), cy - (r_arc + 3) * math.sin(am) + 0.8, label, 2.1))
    return "".join(out)


def _hline_break(y, xa, xb, gaps, w=THICK):
    xa, xb = min(xa, xb), max(xa, xb)
    segs = [(xa, xb)]
    for g0, g1 in gaps:
        g0, g1 = min(g0, g1), max(g0, g1)
        new = []
        for s0, s1 in segs:
            if g1 <= s0 or g0 >= s1:
                new.append((s0, s1)); continue
            if g0 > s0:
                new.append((s0, g0))
            if g1 < s1:
                new.append((g1, s1))
        segs = new
    return "".join(line(a, y, b, y, w) for a, b in segs)


def _leader(fx, fy, tx, ty, label, size=3.2, above=True):
    """Leader: arrow at the feature (fx,fy), elbow to text at (tx,ty)."""
    anchor = "start" if tx >= fx else "end"
    return "".join([arrow(fx, fy, (fx - tx), (fy - ty)),
                    line(fx, fy, tx, ty, THIN),
                    text(tx + (1.5 if anchor == "start" else -1.5), ty - (0.5 if above else -2.5),
                         label, size, anchor=anchor)])


def _lid_views(g: LidGeom, p: LidParams) -> list[str]:
    """TOP view + SECTION X-X + DETAIL 'A' + BACK SIDE view."""
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = (ax0 + ax1) / 2
    show_sec = p.include_section
    n = g.num_holes
    marks = p.hole_markings if (p.hole_markings and len(p.hole_markings) == n) else _markings(n)
    angs = (p.hole_angles if (p.hole_angles and len(p.hole_angles) == n)
            else [g.hole_start_angle + i * g.theta for i in range(n)])
    uniform = all(abs(((angs[(i + 1) % n] - angs[i]) % 360) - g.theta) < 0.01 for i in range(n))

    avail_w = (ax1 - ax0) - 90
    avail_h = (ay1 - ay0)
    # room for TWO circle views (top + back) plus the thin section band
    sv = min(avail_w / g.lid_od, (avail_h - 66) / (2 * g.lid_od))
    sv = max(0.42, min(sv, 2.3))
    r = g.lid_od * sv / 2
    r_pcd = g.pcd * sv / 2
    r_hole = max(g.hole_dia * sv / 2, 1.1)
    r_weld = (g.lid_od - 2 * g.weld_space) * sv / 2
    r_grv = r_weld - max(g.groove_width * sv, 1.4)
    cxL = cx - 6

    def holes_at(ccy, mark=False):
        out = []
        for i in range(n):
            ar = math.radians(angs[i])
            hx, hy = cxL + r_pcd * math.cos(ar), ccy - r_pcd * math.sin(ar)
            out.append(circle(hx, hy, r_hole, MED))
            if mark:
                rm = r_pcd + r_hole + 2.4
                mx, my = cxL + rm * math.cos(ar), ccy - rm * math.sin(ar)
                out.append(text(mx, my + 0.9, marks[i], MARK_SIZE, weight="bold", rot=_mark_rot(angs[i])))
        return out

    # ---------------- TOP VIEW ----------------
    tv_cy = ay0 + 6 + r
    s.append(circle(cxL, tv_cy, r, THICK))                 # lid OD
    s.append(circle(cxL, tv_cy, r_weld, THIN))             # welding-space circle
    s.append(circle(cxL, tv_cy, r_grv, THIN))              # groove circle
    s.append(circle(cxL, tv_cy, r_pcd, THIN, dash=C_LINE)) # PCD (chain)
    s.append(line(cxL - r - 7, tv_cy, cxL + r + 7, tv_cy, THIN, dash=C_LINE))
    s.append(line(cxL, tv_cy - r - 7, cxL, tv_cy + r + 7, THIN, dash=C_LINE))
    s += holes_at(tv_cy, mark=True)
    # section line X-X — arrows point UP
    for sx in (cxL - r - 5, cxL + r + 5):
        s.append(line(sx, tv_cy, sx, tv_cy + 7, THIN))
        s.append(arrow(sx, tv_cy - 1, 0, -1))
        s.append(text(sx, tv_cy + 11, "X", 2.6, weight="bold"))
    s.append(line(cxL - r - 9, tv_cy, cxL + r + 9, tv_cy, THIN, dash=C_LINE))
    # angle between holes
    if uniform:
        s.append(_angle_dim(cxL, tv_cy, r_pcd, r_pcd * 0.5, angs[0], angs[1], f"{_n(g.theta)}° (TYP)"))
    else:
        rr = r_pcd * 0.5
        for i in range(n):
            a0, a1 = angs[i], angs[(i + 1) % n]
            s.append(_angle_dim(cxL, tv_cy, r_pcd, rr, a0, a1, f"{_n((a1 - a0) % 360)}°"))
            rr = r_pcd * 0.38 if rr > r_pcd * 0.44 else r_pcd * 0.5
    # ---- right-side leader callouts ----
    tx = cxL + r + 20
    s.append(_leader(cxL + r * math.cos(math.radians(55)), tv_cy - r * math.sin(math.radians(55)),
                     tx, tv_cy - r + 2, f"Ø{_n(g.lid_od)} {_tol(g.lid_od, is_od=True)}"))
    ha = math.radians(g.hole_start_angle + g.theta)
    s.append(_leader(cxL + (r_pcd + r_hole) * math.cos(ha), tv_cy - (r_pcd + r_hole) * math.sin(ha),
                     tx, tv_cy - r + 12, f"HOLE Ø{_n(g.hole_dia)} {_tol(g.hole_dia)}, {g.num_holes} Nos"))
    # PCD as its own leader (like the reference); no "ON PCD" text, no groove/weld text
    s.append(_leader(cxL + r_pcd * math.cos(math.radians(45)), tv_cy - r_pcd * math.sin(math.radians(45)),
                     tx, tv_cy - r + 22, f"PCD {_n(g.pcd)} {_tol(g.pcd)}"))
    # letter size — leader arrow from an EI1 terminal marking (as sketched)
    ei1_ang = next((angs[i] for i, m in enumerate(marks) if m == "EI1"), angs[0])
    lmr = r_pcd + r_hole + 2.4
    s.append(_leader(cxL + lmr * math.cos(math.radians(ei1_ang)), tv_cy - lmr * math.sin(math.radians(ei1_ang)),
                     tx, tv_cy - r - 3, f"LETTER SIZE {_n(g.letter_size)}mm ON PCD"))
    # optional visual-criteria note (top-left of the drawing area)
    if g.visual_criteria:
        s.append(text(ax0 + 2, ay0 + 5, "VISUAL CRITERIA :", 2.0, anchor="start", weight="bold"))
        s.append(text(ax0 + 2, ay0 + 9, g.visual_criteria[:60], 1.8, anchor="start"))

    if not show_sec:
        s += _lid_back_view(g, p, cxL, tv_cy + r + 8 + r, r, r_pcd, r_hole, sv, angs)
        return s

    # ---------------- SECTION X-X ----------------
    sec_cy = tv_cy + r + 20
    tp = max(g.thickness * sv * 1.9, 13)
    gdp = tp * g.groove_depth / g.thickness
    gwp = max(g.groove_width * sv * 1.9, 5.5)
    wp = max(g.weld_space * sv * 1.9, 3.0)
    ch = 1.9                                            # edge chamfer (0.5x45) on paper
    chh = 1.3                                           # pin-hole chamfer (0.3x45) on paper
    taper = tp * math.tan(math.radians(g.edge_angle))
    xL, xR = cxL - r, cxL + r
    yT, yB = sec_cy - tp / 2, sec_cy + tp / 2
    proj = sorted({round(r_pcd * math.cos(math.radians(a)), 3) for a in angs})
    hxs = [cxL + px for px in proj]

    # material profile path (top face w/ groove notches, 6deg tapered+chamfered edges)
    def pth(pts):
        return "M " + " L ".join(f"{_n(x)} {_n(y)}" for x, y in pts) + " Z"
    prof = [(xL, yT),
            (xL + wp, yT), (xL + wp, yT + gdp), (xL + wp + gwp, yT + gdp), (xL + wp + gwp, yT),
            (xR - wp - gwp, yT), (xR - wp - gwp, yT + gdp), (xR - wp, yT + gdp), (xR - wp, yT),
            (xR, yT),
            (xR - taper, yB - ch), (xR - taper - ch, yB),
            (xL + taper + ch, yB), (xL + taper, yB - ch)]
    dprof = pth(prof)
    # hatch ONLY inside the profile (clipped), then the outline
    s.append(f'<path d="{dprof}" fill="url(#hatch)" stroke="none"/>')
    s.append(f'<path d="{dprof}" fill="none" stroke="#111" stroke-width="{THICK}"/>')
    # pin holes: DASHED profile with 0.3x45 chamfer at TOP and BOTTOM (hatch stays)
    for h in hxs:
        for sgn in (-1, 1):
            wx = h + sgn * r_hole
            s.append(line(wx + sgn * chh, yT, wx, yT + chh, THIN, dash=C_HID))   # top chamfer
            s.append(line(wx, yT + chh, wx, yB - chh, THIN, dash=C_HID))          # wall
            s.append(line(wx, yB - chh, wx + sgn * chh, yB, THIN, dash=C_HID))    # bottom chamfer
    # pin-hole chamfer — leader with value + "chamfer on holes both faces"
    hc = hxs[0] if hxs else cxL
    s.append(arrow(hc - r_hole - chh, yT, -1, -1))
    s.append(line(hc - r_hole - chh, yT, cxL - r * 0.35, yT - 10, THIN))
    s.append(text(cxL - r * 0.35, yT - 11, f"{g.hole_chamfer} CHAMFER ON HOLES BOTH FACES", 1.9, anchor="middle"))
    # 6deg angle: reference line + crossed-arrow angular dimension at the edge
    s.append(line(xL, yT, xL, yB + 7, THIN, dash=C_HID))          # vertical reference
    va, ea = 270.0, 270.0 + g.edge_angle                          # screen: down, then 6° toward taper
    s += _angle_dim(xL, yT, tp + 6, tp + 6, va, ea, f"{_n(g.edge_angle)}°")
    # thickness (kept)
    s.append(dim_v(yT, yB, xR + 9, f"{_n(g.thickness)} {_tol(g.thickness)}"))
    s.append(line(xR, yT, xR + 10, yT, THIN)); s.append(line(xR, yB, xR + 10, yB, THIN))
    s.append(text(cxL, yB + 13, "SECTION X-X", 3.0, weight="bold"))
    # DETAIL box with just "A" on the upper side
    bx0, bw = xR - wp - gwp - 2, wp + gwp + taper + 4
    s.append(rect(bx0, yT - 1.5, bw, tp + 3, THIN))
    s.append(text(bx0 + bw / 2, yT - 3, "A", 2.8, weight="bold"))

    # ---------------- DETAIL 'A' (edge zoom; groove W/D + space dims; chamfer) ------
    if not getattr(p, "include_detail", True):
        s += _lid_back_view(g, p, cxL, sec_cy + tp / 2 + 26 + r, r, r_pcd, r_hole, sv, angs)
        return s
    dax, day, dw, dh = xR + 20, sec_cy - 24, 40, 46
    s.append(text(dax + dw / 2, day - 1.5, "DETAIL 'A'", 2.3, weight="bold"))
    s.append(rect(dax, day, dw, dh, THIN))
    z = 8.0
    zdp, zgw, zwp, zch = g.groove_depth * z, g.groove_width * z, g.weld_space * z, 0.5 * z
    ztp = min(g.thickness * z, 22)
    ztaper = ztp * math.tan(math.radians(g.edge_angle))
    ox, oy = dax + dw - 11, day + 10          # top-outer corner of the edge
    yb2 = oy + ztp
    g0 = ox - zwp - zgw                         # groove inner edge
    g1 = ox - zwp                               # groove outer edge (weld land start)
    s.append(line(g0 - 6, oy, g0, oy, THICK))
    s.append(line(g0, oy, g0, oy + zdp, THICK))
    s.append(line(g0, oy + zdp, g1, oy + zdp, THICK))
    s.append(line(g1, oy + zdp, g1, oy, THICK))
    s.append(line(g1, oy, ox, oy, THICK))       # weld land (space)
    s.append(line(ox, oy, ox - ztaper, yb2 - zch, THICK))
    s.append(line(ox - ztaper, yb2 - zch, ox - ztaper - zch, yb2, THICK))
    s.append(line(g0 - 6, yb2, ox - ztaper - zch, yb2, THICK))
    # chamfer value (leader) + 6°
    s.append(line(ox - ztaper - zch * 0.5, yb2 - zch * 0.5, ox + 5, yb2 + 1, THIN))
    s.append(text(ox + 5.5, yb2 + 1.5, g.edge_chamfer, 1.8, anchor="start"))
    s.append(line(ox, oy, ox, yb2 + 3, THIN, dash=C_HID))
    s.append(text(ox + 0.6, yb2 + 3, f"{_n(g.edge_angle)}°", 1.7, anchor="start"))
    # groove DEPTH (vertical, arrows), WIDTH (horizontal, arrows), SPACE from OD (arrows)
    s.append(dim_v(oy, oy + zdp, g0 - 4, f"{_n(g.groove_depth)}", size=1.8))
    s.append(line(g0, oy, g0 - 5, oy, THIN)); s.append(line(g0, oy + zdp, g0 - 5, oy + zdp, THIN))
    s.append(dim_h(g0, g1, oy + zdp + 4, f"{_n(g.groove_width)}", size=1.8))
    s.append(line(g0, oy + zdp, g0, oy + zdp + 5, THIN)); s.append(line(g1, oy + zdp, g1, oy + zdp + 5, THIN))
    s.append(dim_h(g1, ox, oy - 4, f"{_n(g.weld_space)}", size=1.8))
    s.append(line(g1, oy, g1, oy - 5, THIN)); s.append(line(ox, oy, ox, oy - 5, THIN))

    # ---------------- BACK SIDE VIEW ----------------
    s += _lid_back_view(g, p, cxL, sec_cy + tp / 2 + 26 + r, r, r_pcd, r_hole, sv, angs)
    return s


def _lid_back_view(g, p, cxL, bv_cy, r, r_pcd, r_hole, sv, angs) -> list[str]:
    """Back view: OD circle (no dim) + a groove circle at (PCD+10) with its value
    and 0.3-deep/0.3-wide note; the ORIGINAL holes only (PCD line hidden)."""
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    if bv_cy + r > ay1:
        bv_cy = ay1 - r - 2
    r_bg = (g.pcd + 10) * sv / 2
    s.append(circle(cxL, bv_cy, r, THICK))               # OD (same as lid) — no dim
    s.append(circle(cxL, bv_cy, r_bg, THIN))             # groove circle at PCD+10
    s.append(line(cxL - r - 6, bv_cy, cxL + r + 6, bv_cy, THIN, dash=C_LINE))
    s.append(line(cxL, bv_cy - r - 6, cxL, bv_cy + r + 6, THIN, dash=C_LINE))
    # holes only (no PCD circle line)
    for i in range(g.num_holes):
        ar = math.radians(angs[i])
        s.append(circle(cxL + r_pcd * math.cos(ar), bv_cy - r_pcd * math.sin(ar), r_hole, MED))
    # groove circle dimension (value + 0.3 deep / 0.3 wide)
    ga = math.radians(40)
    tx = cxL + r + 16
    s.append(_leader(cxL + r_bg * math.cos(ga), bv_cy - r_bg * math.sin(ga), tx, bv_cy - 3,
                     f"Ø{_n(g.pcd + 10)} GROOVE"))
    s.append(text(tx + 1.5, bv_cy, f"{_n(g.back_groove)} DEEP × {_n(g.back_groove)} WIDE", 3.0, anchor="start"))
    s.append(text(cxL, bv_cy + r + 5, "BACK SIDE OF LID BLANK", 2.8, weight="bold"))
    return s


def render_lid_svg(g: LidGeom, p: LidParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>',
             _hatch_defs()]
    parts += _header(g, p)
    parts += _lid_views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
