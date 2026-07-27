"""Container CAD drawing — geometry + RES-format SVG generator.

Container types (user-selected):
  - deep_drawn : plain deep-drawn cup.
  - flanged    : cup with a mounting flange; flange_kind = integral | welded,
                 flange_position = top | middle | bottom.

Bottom radius is OPTIONAL for BOTH types: if given it is applied (bottom corners
are actually rounded + an R note is shown); if not given the corners stay sharp.

Dimensions:
  OD  = Container OD = battery / container diameter
  wall = from Table 2 by OD band and container type
  ID  = OD - 2*wall
  H   = height (from Table 1 "Height of Container")
Drawn third-angle: TOP view above, SECTION A-A below (section optional), RES sheet.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .tables import container_wall
from .res_logo import RES_LOGO_B64, RES_LOGO_W, RES_LOGO_H

# ----- sheet layout constants (mm on an A4 portrait sheet) ----------------- #
PW, PH = 210.0, 297.0
M = 6.0
BORDER_L, BORDER_R = M + 2, PW - M - 2
HEAD_BOT = 24.0                    # header band bottom
FOOT_TOP = 206.0                   # footer (title block) top
AREA = (BORDER_L, HEAD_BOT + 2, BORDER_R, FOOT_TOP - 3)

THICK, MED, THIN = 0.45, 0.28, 0.16
C_LINE = "3,1,0.8,1"
C_HID = "2,1.5"


# --------------------------------------------------------------------------- #
@dataclass
class ContainerParams:
    od: float
    height: float
    container_type: str                    # deep_drawn | flanged
    container_id: Optional[float] = None    # override; else od - 2*wall
    wall: Optional[float] = None            # container thickness override (Table 2)
    bottom_radius: Optional[float] = None  # optional for both types
    flange_kind: Optional[str] = None      # integral | welded
    flange_position: Optional[str] = None  # top | middle | bottom
    flange_width: float = 6.0
    flange_thickness: Optional[float] = None
    include_section: bool = True
    component_name: str = "CONTAINER"
    project: str = ""
    drawing_no: str = "RES-__-36"
    battery_code: str = ""
    weight: str = ""
    date: str = ""                      # generation date, Indian format DD/MM/YYYY
    show_bom: bool = False              # CODE NO/COMPONENT sub-table only if >2 CAD drawings
    revisions: list = field(default_factory=list)   # header revision table rows


@dataclass
class ContainerGeom:
    od: float
    id: float
    wall: float
    height: float
    wall_tol: str
    wall_min: float
    wall_max: float
    od_band: str
    bottom_radius: Optional[float]
    container_type: str
    flange_kind: Optional[str]
    flange_position: Optional[str]
    flange_width: float
    flange_thickness: Optional[float]
    warnings: list = field(default_factory=list)


def compute_geometry(p: ContainerParams) -> ContainerGeom:
    warnings: list[str] = []
    w = container_wall(p.od, p.container_type)
    if not w:
        warnings.append(f"Container OD {p.od} mm is outside Table 2 (30-150 mm); wall assumed 1.0.")
        w = {"wall": 1.0, "tolerance": "±0.10", "min": 0.9, "max": 1.1, "od_band": "?"}
    wall = p.wall if p.wall else w["wall"]
    inner = p.container_id if p.container_id else round(p.od - 2 * wall, 3)
    ft = p.flange_thickness if p.flange_thickness else round(wall + 1.0, 2)
    br = p.bottom_radius if (p.bottom_radius and p.bottom_radius > 0) else None
    return ContainerGeom(
        od=p.od, id=inner, wall=wall, height=p.height,
        wall_tol=w["tolerance"], wall_min=w["min"], wall_max=w["max"], od_band=w["od_band"],
        bottom_radius=br, container_type=p.container_type,
        flange_kind=p.flange_kind, flange_position=p.flange_position,
        flange_width=p.flange_width, flange_thickness=ft, warnings=warnings,
    )


# ----- tiny SVG helpers ---------------------------------------------------- #
def _n(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def line(x1, y1, x2, y2, w=MED, dash=None, color="#111"):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}" stroke="{color}" stroke-width="{w}"{d}/>'


def rect(x, y, w_, h_, w=MED, fill="none", color="#111"):
    return f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w_)}" height="{_n(h_)}" fill="{fill}" stroke="{color}" stroke-width="{w}"/>'


def circle(cx, cy, r, w=MED, dash=None, fill="none", color="#111"):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r)}" fill="{fill}" stroke="{color}" stroke-width="{w}"{d}/>'


def text(x, y, s, size=2.4, anchor="middle", color="#111", weight="normal", rot=None):
    tr = f' transform="rotate({rot} {_n(x)} {_n(y)})"' if rot is not None else ""
    return (f'<text x="{_n(x)}" y="{_n(y)}" font-family="Arial, sans-serif" font-size="{size}" '
            f'fill="{color}" text-anchor="{anchor}" font-weight="{weight}"{tr}>{s}</text>')


def arrow(x, y, dx, dy, size=1.6):
    a = math.atan2(dy, dx)
    x1 = x - size * math.cos(a - 0.4); y1 = y - size * math.sin(a - 0.4)
    x2 = x - size * math.cos(a + 0.4); y2 = y - size * math.sin(a + 0.4)
    return f'<polygon points="{_n(x)},{_n(y)} {_n(x1)},{_n(y1)} {_n(x2)},{_n(y2)}" fill="#111"/>'


def dim_h(x1, x2, y, label, size=3.5):
    return "".join([line(x1, y, x2, y, THIN), arrow(x1, y, -1, 0), arrow(x2, y, 1, 0),
                    text((x1 + x2) / 2, y - 1.5, label, size)])


def dim_v(y1, y2, x, label, size=3.5):
    return "".join([line(x, y1, x, y2, THIN), arrow(x, y1, 0, -1), arrow(x, y2, 0, 1),
                    text(x + 1.8, (y1 + y2) / 2, label, size, rot=90)])


def _arc(cx, cy, r, d0, d1, n=8):
    pts = []
    for i in range(n + 1):
        a = math.radians(d0 + (d1 - d0) * i / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


# --------------------------------------------------------------------------- #
def _header(g: ContainerGeom, p: ContainerParams) -> list[str]:
    s = []
    s.append(rect(M, M, PW - 2 * M, PH - 2 * M, THICK))
    s.append(rect(M + 1.2, M + 1.2, PW - 2 * M - 2.4, PH - 2 * M - 2.4, THIN))
    y0, y1 = 8.0, HEAD_BOT
    xsplit = 118.0
    # revision table (left): 5 columns — widths sum to (xsplit - BORDER_L) = 110
    rev_cols = [("REV.No", 15), ("DESCRIPTION", 39), ("DATE", 16), ("CHECKED", 20), ("APPROVED", 20)]
    x = BORDER_L
    colx = {}
    s.append(line(BORDER_L, y0, xsplit, y0, MED))
    s.append(line(BORDER_L, y0 + 5, xsplit, y0 + 5, THIN))
    for name, w in rev_cols:
        s.append(text(x + w / 2, y0 + 3.4, name, 1.6, weight="bold"))
        s.append(line(x, y0, x, y1, THIN))
        colx[name] = (x, w)
        x += w
    s.append(line(xsplit, y0, xsplit, y1, MED))
    # revision rows (latest few) — REV.No / DESCRIPTION / DATE
    revs = getattr(p, "revisions", None) or []
    show = revs[-3:]
    if show:
        row_h = (y1 - (y0 + 5)) / 3
        for i, rv in enumerate(show):
            ry = y0 + 5 + i * row_h
            if i:
                s.append(line(BORDER_L, ry, xsplit, ry, THIN))
            rno = rv.rev if hasattr(rv, "rev") else rv.get("rev", "")
            rdt = rv.date if hasattr(rv, "date") else rv.get("date", "")
            rds = rv.description if hasattr(rv, "description") else rv.get("description", "")
            cy = ry + row_h / 2 + 1.0
            s.append(text(colx["REV.No"][0] + colx["REV.No"][1] / 2, cy, rno, 1.7, weight="bold"))
            s.append(text(colx["DESCRIPTION"][0] + 1.5, cy, (rds or "")[:34], 1.5, anchor="start"))
            s.append(text(colx["DATE"][0] + colx["DATE"][1] / 2, cy, rdt, 1.5))
    # allowable deviations table (right)
    s.append(text((xsplit + BORDER_R) / 2, y0 + 3.4,
                  "ALLOWABLE DEVIATIONS FOR DIMENSIONS WITHOUT SPECIFIED TOLERANCES", 1.7, weight="bold"))
    s.append(line(xsplit, y0 + 5, BORDER_R, y0 + 5, THIN))
    s.append(line(xsplit, y0 + 5 + 4.75, BORDER_R, y0 + 5 + 4.75, THIN))
    lblw = 22.0
    colw = (BORDER_R - xsplit - lblw) / 4
    for r, (lbl, vals) in enumerate([("DIMENSIONS", ["0.5-6", "6-30", "30-120", "120-315"]),
                                     ("TOLERANCES", ["±0.1", "±0.2", "±0.3", "±0.5"])]):
        yy = y0 + 5 + r * 4.75
        s.append(text(xsplit + lblw / 2, yy + 3.2, lbl, 1.9))
        for i, v in enumerate(vals):
            s.append(text(xsplit + lblw + colw * (i + 0.5), yy + 3.2, v, 1.9))
    for i in range(5):
        s.append(line(xsplit + lblw + colw * i, y0 + 5, xsplit + lblw + colw * i, y1, THIN))
    s.append(line(xsplit + lblw, y0 + 5, xsplit + lblw, y1, THIN))
    s.append(line(BORDER_L, y1, BORDER_R, y1, MED))
    return s


def _res_logo(cx, cy, box_w=16.0) -> list[str]:
    """Real RES logo (extracted from the drawings), embedded as a PNG."""
    w = box_w
    h = w * RES_LOGO_H / RES_LOGO_W
    return [f'<image x="{_n(cx - w/2)}" y="{_n(cy - h/2)}" width="{_n(w)}" height="{_n(h)}" '
            f'preserveAspectRatio="xMidYMid meet" '
            f'href="data:image/png;base64,{RES_LOGO_B64}"/>']


def _proj_symbol(cx, cy) -> list[str]:
    """Projection symbol as on RES sheets: end-view circle + frustum."""
    s = [circle(cx - 4, cy, 2.0, MED), circle(cx - 4, cy, 0.7, MED),
         line(cx - 6.2, cy, cx - 1.8, cy, THIN), line(cx - 4, cy - 2.2, cx - 4, cy + 2.2, THIN),
         line(cx - 6.5, cy, cx + 6.5, cy, THIN)]
    fp = [(cx - 0.5, cy - 2.6), (cx + 5.5, cy - 1.3), (cx + 5.5, cy + 1.3), (cx - 0.5, cy + 2.6)]
    s.append(f'<polygon points="{" ".join(f"{_n(x)},{_n(y)}" for x,y in fp)}" fill="none" stroke="#111" stroke-width="{MED}"/>')
    return s


def _footer(g: ContainerGeom, p: ContainerParams) -> list[str]:
    """Footer laid out per Guidelines-for-Drawings.docx (9-column grid)."""
    s = []
    bot = PH - M - 2
    # column boundaries (9 columns)
    x1, x2, x3, x4, x5 = BORDER_L, 24.0, 56.0, 66.0, 80.0     # BOM / PROJECT block cols
    x6, x7, x8, x9, x10 = 96.0, 116.0, 145.0, 174.0, BORDER_R  # RES, DRAWN-lbl, DATE, NAME, SIGN
    # vertical rows
    strip_top = FOOT_TOP
    strip_mid = strip_top + 5.5
    tt = strip_top + 11               # title block top
    r_sc, r_dm, r_hdr = tt + 6, tt + 12, tt + 18
    comp_y = bot - 9                  # company / drawing-no row top
    ty = tt + 31                      # PROJECT|TITLE divider

    # main title block box
    s.append(rect(BORDER_L, tt, BORDER_R - BORDER_L, bot - tt, MED))

    # ---- top strip ----
    # BOM sub-table (CODE NO/COMPONENT/QTY/REF.DRG) shown ONLY when the drawing
    # covers more than 2 CAD drawings (assemblies); a single part shows only the
    # material block (per the guidelines).
    if p.show_bom:
        s.append(rect(BORDER_L, strip_top, BORDER_R - BORDER_L, tt - strip_top, MED))
        s.append(line(x1, strip_mid, x5, strip_mid, THIN))
        s.append(line(x5, strip_top, x5, tt, MED))
        s.append(line(x7, strip_top, x7, tt, MED))
        bom = [("CODE NO.", x1, x2, "01"), ("COMPONENT", x2, x3, p.component_name),
               ("QTY/NOS", x3, x4, "01"), ("REF.DRG.NO", x4, x5, p.drawing_no)]
        for name, a, b, val in bom:
            s.append(line(b, strip_top, b, tt, THIN))
            s.append(text((a + b) / 2, strip_mid - 1.5, val, 1.8))
            s.append(text((a + b) / 2, strip_mid + 3.6, name, 1.7, weight="bold"))
    else:
        s.append(rect(x7, strip_top, x10 - x7, tt - strip_top, MED))
    s.append(line(x7, strip_mid, x10, strip_mid, THIN))
    material = getattr(p, "material", None) or "SS 304"
    quantity = getattr(p, "quantity", None) or "01"
    mat = [("MATERIAL", x7, x8, material), ("QUANTITY (Nos)", x8, x9, quantity),
           ("WEIGHT (Grams)", x9, x10, p.weight or "—")]
    for name, a, b, val in mat:
        s.append(line(b, strip_top, b, tt, THIN))
        s.append(text((a + b) / 2, strip_mid - 1.5, val, 1.9))
        s.append(text((a + b) / 2, strip_mid + 3.6, name, 1.6, weight="bold"))

    # ---- title block dividers ----
    s.append(line(x5, tt, x5, ty, MED))          # PROJECT | RES (upper only)
    s.append(line(x6, tt, x6, comp_y, MED))      # left block | grid
    s.append(line(BORDER_L, tt, BORDER_R, tt, MED))

    # Col 1-4: PROJECT
    s.append(text(x1 + 2, tt + 4, "PROJECT", 2.0, anchor="start"))
    s.append(text((x1 + x5) / 2, tt + 13, p.project or "—", 3.8, weight="bold"))
    if p.battery_code:
        s.append(text((x1 + x5) / 2, tt + 19, f"({p.battery_code})", 2.4, weight="bold"))
    # Col 5: RES logo (real, embedded)
    s += _res_logo((x5 + x6) / 2, (tt + ty) / 2, box_w=x6 - x5 - 2)
    # TITLE block spans cols 1-5 (below PROJECT/RES)
    s.append(line(x1, ty, x6, ty, MED))
    s.append(text(x1 + 2, ty + 4, "TITLE", 2.0, anchor="start"))
    s.append(text((x1 + x6) / 2, ty + 16, p.component_name, 4.4, weight="bold"))

    # ---- right grid (cols 6-9) ----
    # SCALE (6-7 span) / ALL DIMNS ; REV (col8) ; projection symbol (col9)
    s.append(line(x6, r_sc, x8, r_sc, THIN))
    s.append(line(x6, r_dm, x8, r_dm, MED))
    s.append(text(x6 + 2, r_sc - 2, "SCALE : NTS", 2.1, anchor="start"))
    s.append(text(x6 + 2, r_dm - 2, 'ALL DIMNS. ARE IN "mm"', 2.0, anchor="start"))
    s.append(line(x8, tt, x8, r_dm, MED))
    s.append(line(x9, tt, x9, r_dm, MED))
    s.append(line(x8, r_sc, x9, r_sc, THIN))
    s.append(text((x8 + x9) / 2, r_sc - 2, "REV.No", 1.9))
    _revs = getattr(p, "revisions", None) or []
    _last = _revs[-1] if _revs else None
    _lastrev = (_last.rev if hasattr(_last, "rev") else _last.get("rev", "")) if _last else ""
    s.append(text((x8 + x9) / 2, r_dm - 2, _lastrev, 2.4, weight="bold"))
    s += _proj_symbol((x9 + x10) / 2, (tt + r_dm) / 2)
    s.append(line(x6, r_dm, x10, r_dm, MED))
    # DATE | NAME | SIGN header (col7=DATE, col8=NAME, col9=SIGN; col6=label)
    for xd in (x7, x8, x9):
        s.append(line(xd, r_dm, xd, comp_y, THIN))
    s.append(text((x7 + x8) / 2, r_hdr - 1.6, "DATE", 1.9))
    s.append(text((x8 + x9) / 2, r_hdr - 1.6, "NAME", 1.9))
    s.append(text((x9 + x10) / 2, r_hdr - 1.6, "SIGN.", 1.9))
    s.append(line(x6, r_hdr, x10, r_hdr, THIN))
    rows = ["DRAWN", "DESIGN", "PRODUCTION", "QUALITY"]
    rh = (comp_y - r_hdr) / 4
    for i, rl in enumerate(rows):
        ry = r_hdr + i * rh
        s.append(text(x6 + 2, ry + rh / 2 + 1, rl, 1.9, anchor="start"))
        if i:
            s.append(line(x6, ry, x10, ry, THIN))
        if p.date:      # generation date on every sign-off row (DD/MM/YYYY)
            s.append(text((x7 + x8) / 2, ry + rh / 2 + 1, p.date, 2.0))

    # ---- bottom: company (cols 1-5) + DRAWING NO (cols 6-9) ----
    s.append(line(BORDER_L, comp_y, BORDER_R, comp_y, MED))
    s.append(line(x6, comp_y, x6, bot, MED))
    s.append(text((x1 + x6) / 2, comp_y + 4, "RENEWABLE ENERGY SYSTEMS LIMITED", 2.0, weight="bold"))
    s.append(text((x1 + x6) / 2, comp_y + 7, "HYDERABAD, INDIA.", 2.0, weight="bold"))
    s.append(text((x6 + BORDER_R) / 2, comp_y + 5.6, f"DRAWING NO. :  {p.drawing_no}", 2.6, weight="bold"))
    return s


def _hatch_defs() -> str:
    return ('<defs><pattern id="hatch" width="1.4" height="1.4" patternTransform="rotate(45)" '
            'patternUnits="userSpaceOnUse"><line x1="0" y1="0" x2="0" y2="1.4" stroke="#111" '
            'stroke-width="0.12"/></pattern></defs>')


def _views(g: ContainerGeom, p: ContainerParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    cx = (ax0 + ax1) / 2
    OD, ID, H, wall = g.od, g.id, g.height, g.wall
    flanged = g.container_type == "flanged"
    fw = g.flange_width if flanged else 0.0
    span = OD + 2 * fw
    show_sec = p.include_section

    avail_w = (ax1 - ax0) - 44
    if show_sec:
        avail_h = (ay1 - ay0) - 34
        s_ = min(avail_w / span, avail_h / (span + H + 22))
    else:
        s_ = min(avail_w / span, ((ay1 - ay0) - 20) / span)
    s_ = max(0.35, min(s_, 3.2))

    r_od, r_id, r_fl = OD * s_ / 2, ID * s_ / 2, span * s_ / 2

    # ---------- TOP VIEW ----------
    tv_cy = ay0 + 8 + r_fl
    if flanged:
        s.append(circle(cx, tv_cy, r_fl, THICK))
    s.append(circle(cx, tv_cy, r_od, THICK))
    s.append(circle(cx, tv_cy, r_id, MED, dash=C_HID))
    s.append(line(cx - r_fl - 4, tv_cy, cx + r_fl + 4, tv_cy, THIN, dash=C_LINE))
    s.append(line(cx, tv_cy - r_fl - 4, cx, tv_cy + r_fl + 4, THIN, dash=C_LINE))
    lx, ly = cx + r_od * 0.707, tv_cy - r_od * 0.707
    s.append(line(lx, ly, cx + r_fl + 9, tv_cy - r_fl - 2, THIN))
    s.append(text(cx + r_fl + 10, tv_cy - r_fl - 3, f"Ø{_n(OD)}", 4.0, anchor="start"))
    if flanged:
        s.append(text(cx, tv_cy - r_fl - 5, f"Ø{_n(span)} FLANGE", 2.1))

    if not show_sec:
        return s

    # ---------- SECTION A-A ----------
    sec_top = tv_cy + r_fl + 20
    yT, yB = sec_top, sec_top + H * s_
    xoL, xoR = cx - r_od, cx + r_od
    xiL, xiR = cx - r_id, cx + r_id
    wp = wall * s_
    yBin = yB - wp
    # fillet radii (applied only if bottom_radius given)
    Ri = min(g.bottom_radius * s_, (xiR - xiL) / 2 - 0.5, (yBin - yT) * 0.4) if g.bottom_radius else 0.0
    Ri = max(Ri, 0.0)
    Ro = Ri + wp if Ri > 0 else 0.0

    # build closed U-band path (outer boundary + inner boundary)
    pts: list[tuple] = []
    pts.append((xoL, yT))
    if Ro > 0:
        pts.append((xoL, yB - Ro)); pts += _arc(xoL + Ro, yB - Ro, Ro, 180, 90)
        pts.append((xoR - Ro, yB)); pts += _arc(xoR - Ro, yB - Ro, Ro, 90, 0)
    else:
        pts.append((xoL, yB)); pts.append((xoR, yB))
    pts.append((xoR, yT))
    pts.append((xiR, yT))
    if Ri > 0:
        pts.append((xiR, yBin - Ri)); pts += _arc(xiR - Ri, yBin - Ri, Ri, 0, 90)
        pts.append((xiL + Ri, yBin)); pts += _arc(xiL + Ri, yBin - Ri, Ri, 90, 180)
    else:
        pts.append((xiR, yBin)); pts.append((xiL, yBin))
    pts.append((xiL, yT))
    dpath = "M " + " L ".join(f"{_n(x)} {_n(y)}" for x, y in pts) + " Z"
    s.append(f'<path d="{dpath}" fill="url(#hatch)" stroke="#111" stroke-width="{THICK}"/>')
    s.append(line(cx, yT - 4, cx, yB + 4, THIN, dash=C_LINE))

    # bottom radius leader
    if g.bottom_radius:
        s.append(line(xoL + 1, yB - Ro + 1, xoL - 9, yB + 6, THIN))
        s.append(text(xoL - 10, yB + 7, f"R{_n(g.bottom_radius)}", 2.4, anchor="end"))

    # flange in section
    if flanged:
        ftp = (g.flange_thickness or wall) * s_
        fwp = fw * s_
        pos = g.flange_position or "top"
        fy = {"top": yT, "middle": (yT + yB) / 2 - ftp / 2, "bottom": yB - ftp}[pos]
        for side in (-1, 1):
            fx0 = (xoR if side > 0 else xoL - fwp)
            s.append(f'<rect x="{_n(fx0)}" y="{_n(fy)}" width="{_n(fwp)}" height="{_n(ftp)}" fill="url(#hatch)" stroke="#111" stroke-width="{MED}"/>')
            if g.flange_kind == "welded":
                wx = xoR if side > 0 else xoL
                s.append(f'<polygon points="{_n(wx)},{_n(fy)} {_n(wx+side*2.2)},{_n(fy)} {_n(wx)},{_n(fy+2.2)}" fill="#111"/>')
        s.append(text(cx, yB + 16, f"FLANGE: {(g.flange_kind or '').upper()} · {pos.upper()}", 2.1))

    # dimensions
    s.append(dim_h(xoL, xoR, yB + 9, f"Ø{_n(OD)}"))
    s.append(line(xoL, yB, xoL, yB + 10, THIN)); s.append(line(xoR, yB, xoR, yB + 10, THIN))
    s.append(dim_v(yT, yB, xoR + 12, f"{_n(H)}"))
    s.append(line(xoR, yT, xoR + 13, yT, THIN)); s.append(line(xoR, yB, xoR + 13, yB, THIN))
    s.append(dim_h(xiL, xiR, yT + 5, f"Ø{_n(ID)}"))  # inner dia (mouth)
    # wall thickness callout
    s.append(line(xoL, yT - 6, xiL + 12, yT - 10, THIN))
    s.append(text(xiL + 13, yT - 10, f"WALL t {_n(wall)} {g.wall_tol}", 3.5, anchor="start"))
    s.append(line(xoL, yT, xoL, yT - 6, THIN)); s.append(line(xiL, yT, xiL, yT - 6, THIN))
    s.append(dim_h(xoL, xiL, yT - 6, ""))
    s.append(text(cx, yB + (22 if flanged else 16), "SECTION A-A", 3.0, weight="bold"))
    return s


def render_container_svg(g: ContainerGeom, p: ContainerParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>',
             _hatch_defs()]
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
