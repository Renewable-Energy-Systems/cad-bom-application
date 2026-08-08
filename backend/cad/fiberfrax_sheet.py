"""FiberFrax sheet (Stack Wrap / Container Insulation) CAD drawing (RES format).

A plain rectangular sheet dimensioned with SYMBOLS:
  A = length, B = width, C = thickness.
A "FIBERFRAX SHEET SIZES" table sits above the footer with one row per piece
(rows = qty); B and C are constant, A increases by 10 mm per successive piece.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, FOOT_TOP, BORDER_L, BORDER_R, THICK, MED,
                        THIN, _n, line, rect, text, arrow, dim_h, dim_v,
                        _header, _footer)


@dataclass
class FiberfraxSheetParams:
    base_length: float              # A of the first piece
    width: float                    # B
    thickness: float                # C
    qty: int = 2
    b_note: str = "(Based on stack height)"
    component_name: str = "FIBERFRAX SHEET"
    material: str = "FIBERFRAX"
    project: str = ""
    drawing_no: str = "RES-__-__"
    battery_code: str = ""
    weight: str = ""
    quantity: str = "01"
    date: str = ""
    show_bom: bool = False
    revisions: list = field(default_factory=list)


@dataclass
class FiberfraxSheetGeom:
    base_length: float
    width: float
    thickness: float
    qty: int
    rows: list                      # [(sno, A, B, C), ...]
    warnings: list = field(default_factory=list)


def compute_fiberfrax_sheet(p: FiberfraxSheetParams) -> FiberfraxSheetGeom:
    n = max(int(p.qty or 1), 1)
    rows = [(i + 1, round(p.base_length + i * 10.0, 2), round(p.width, 2), round(p.thickness, 2))
            for i in range(n)]
    return FiberfraxSheetGeom(base_length=round(p.base_length, 2), width=round(p.width, 2),
                              thickness=round(p.thickness, 2), qty=n, rows=rows, warnings=[])


def _table(g: FiberfraxSheetGeom) -> list[str]:
    s: list[str] = []
    cols = [("S.NO.", 16), ("A", 44), ("B", 30), ("C", 30)]
    tw = sum(w for _, w in cols)
    x0 = BORDER_L
    rh = 5.0
    nrows = len(g.rows)
    y0 = FOOT_TOP - (nrows + 2) * rh - 2
    s.append(rect(x0, y0, tw, (nrows + 2) * rh, MED))
    s.append(text(x0 + tw / 2, y0 + rh - 1.6, "FIBERFRAX SHEET SIZES", 2.3, weight="bold"))
    s.append(line(x0, y0 + rh, x0 + tw, y0 + rh, THIN))
    cxs = [x0]
    for _, w in cols:
        cxs.append(cxs[-1] + w)
    for i, (name, w) in enumerate(cols):
        s.append(line(cxs[i], y0 + rh, cxs[i], y0 + (nrows + 2) * rh, THIN))
        s.append(text((cxs[i] + cxs[i + 1]) / 2, y0 + 2 * rh - 1.6, name, 2.2, weight="bold"))
    s.append(line(x0, y0 + 2 * rh, x0 + tw, y0 + 2 * rh, THIN))
    for ri, row in enumerate(g.rows):
        ry = y0 + (ri + 2) * rh
        if ri:
            s.append(line(x0, ry, x0 + tw, ry, THIN))
        vals = [str(row[0]), _n(row[1]), _n(row[2]), _n(row[3])]
        for ci, v in enumerate(vals):
            s.append(text((cxs[ci] + cxs[ci + 1]) / 2, ry + rh - 1.7, v, 2.1))
    return s


def _views(g: FiberfraxSheetGeom, p: FiberfraxSheetParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    availH = (FOOT_TOP - (g.qty + 2) * 5 - 12) - (ay0 + 22)
    sv = min(((ax1 - ax0) - 96) / g.base_length, availH / g.width)
    sv = max(0.2, sv)
    Lp = g.base_length * sv
    Wp = g.width * sv
    lx0 = ax0 + 10
    yT = ay0 + 22
    yB = yT + Wp

    # MAIN view (A x B)
    s.append(rect(lx0, yT, Lp, Wp, THICK))
    # A dim (top)
    s.append(line(lx0, yT, lx0, yT - 10, THIN)); s.append(line(lx0 + Lp, yT, lx0 + Lp, yT - 10, THIN))
    s.append(dim_h(lx0, lx0 + Lp, yT - 7, "A", size=4.0))

    # CROSS-SECTION (C x B)
    tp = max(g.thickness * sv, 3.0)
    sx = lx0 + Lp + 34
    s.append(rect(sx, yT, tp, Wp, THICK))
    # C dim (top) — compact, arrows stay at the two faces
    s.append(line(sx, yT, sx, yT - 10, THIN)); s.append(line(sx + tp, yT, sx + tp, yT - 10, THIN))
    s.append(line(sx, yT - 6, sx + tp, yT - 6, THIN))
    s.append(arrow(sx, yT - 6, -1, 0)); s.append(arrow(sx + tp, yT - 6, 1, 0))
    s.append(text(sx + tp / 2, yT - 8.5, "C", 4.0, weight="bold"))
    # B dim (right of the section, vertical) + note
    xb = sx + tp + 14
    s.append(line(sx + tp, yT, xb + 2, yT, THIN)); s.append(line(sx + tp, yB, xb + 2, yB, THIN))
    s.append(dim_v(yT, yB, xb, "B", size=4.0))
    # clear of the B value, which is rotated on the same dimension line
    s.append(text(xb + 17, (yT + yB) / 2, p.b_note, 2.8, rot=90))

    s += _table(g)
    return s


def render_fiberfrax_sheet_svg(g: FiberfraxSheetGeom, p: FiberfraxSheetParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>']
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
