"""Top / Bottom Assembly stack drawing (RES format).

An exploded vertical stack of the discs/pellets that make up the cell. Each piece
is drawn as a 3-D disc with a leader carrying its serial no + component name. The
stack order (top -> bottom) is the placing order the user enters per component
(a component may sit at several positions, e.g. "2,4").

  * TOP assembly    : "CELL SIDE" above the first piece, "LID SIDE" below the last.
  * BOTTOM assembly : "CELL SIDE" below the last piece.

A BOM table (S.No | COMPONENT | QTY/NoS | REF. DRG. NO) sits just above the footer,
one row per distinct component with its total quantity and reference drawing no.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .container import (PW, PH, AREA, FOOT_TOP, BORDER_L, BORDER_R, THICK, MED,
                        THIN, _n, line, rect, text, arrow, _header, _footer)

_SHADES = ["#d9d9d9", "#c2c2c2", "#a8a8a8", "#8f8f8f", "#767676", "#5f5f5f", "#b0b0b0"]


@dataclass
class AssemblyPiece:
    sno: int
    name: str
    dia: float = 0.0            # actual pellet diameter (for relative sizing)
    thickness: float = 0.0      # actual pellet thickness (for relative sizing)


@dataclass
class AssemblyParams:
    pieces: list                      # ordered AssemblyPiece, position 1..N (top->bottom)
    bom: list                         # [(sno, name, qty, ref_drg), ...]
    assembly_type: str = "top"        # top | bottom | cell
    show_sno: bool = True             # leader shows "01 Name" (top/bottom) vs just "Name" (cell)
    component_name: str = "TOP ASSEMBLY"
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
class AssemblyGeom:
    pieces: list
    bom: list
    assembly_type: str
    show_sno: bool = True
    warnings: list = field(default_factory=list)


def compute_assembly(p: AssemblyParams) -> AssemblyGeom:
    return AssemblyGeom(pieces=p.pieces, bom=p.bom, assembly_type=p.assembly_type,
                        show_sno=p.show_sno, warnings=[])


def _pellet(cx, y, rx, ry, fill):
    """A flat 2-D pellet: a filled ellipse sized by the pellet's dia (width) and
    thickness (height) — a bigger/thicker pellet draws bigger."""
    return [f'<ellipse cx="{_n(cx)}" cy="{_n(y)}" rx="{_n(rx)}" ry="{_n(ry)}" '
            f'fill="{fill}" stroke="#111" stroke-width="{MED}"/>']


def _bom_table(g: AssemblyGeom) -> list[str]:
    s: list[str] = []
    cols = [("S.No", 12), ("COMPONENT", 56), ("QTY", 16), ("REF. DRG. NO", 40)]
    tw = sum(w for _, w in cols)
    x0 = BORDER_R - tw
    rh = 5.6
    nrows = len(g.bom)
    y0 = FOOT_TOP - (nrows + 1) * rh - 2
    s.append(rect(x0, y0, tw, (nrows + 1) * rh, MED))
    cxs = [x0]
    for _, w in cols:
        cxs.append(cxs[-1] + w)
    for i, (name, w) in enumerate(cols):
        s.append(line(cxs[i], y0, cxs[i], y0 + (nrows + 1) * rh, THIN))
        s.append(text((cxs[i] + cxs[i + 1]) / 2, y0 + rh - 2.0, name, 2.2, weight="bold"))
    s.append(line(x0, y0 + rh, x0 + tw, y0 + rh, THIN))
    for ri, (sno, nm, qty, ref) in enumerate(g.bom):
        ry = y0 + (ri + 1) * rh
        if ri:
            s.append(line(x0, ry, x0 + tw, ry, THIN))
        s.append(text((cxs[0] + cxs[1]) / 2, ry + rh - 2.0, f"{int(sno):02d}", 2.1))
        s.append(text(cxs[1] + 1.5, ry + rh - 2.0, str(nm), 2.0, anchor="start"))
        s.append(text((cxs[2] + cxs[3]) / 2, ry + rh - 2.0, str(qty), 2.1))
        s.append(text((cxs[3] + cxs[4]) / 2, ry + rh - 2.0, ref or "—", 2.0))
    return s, y0


def _views(g: AssemblyGeom, p: AssemblyParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    bom_svg, bom_top = _bom_table(g)
    n = max(len(g.pieces), 1)
    cx = ax0 + 46
    top = g.assembly_type == "top"
    cell = g.assembly_type == "cell"

    # vertical band for the stack (leave room for the side labels + BOM table)
    y0 = ay0 + 16
    y_end = bom_top - 12
    availH = max(y_end - y0, 30)
    spacing = availH / n

    # relative sizing: width from diameter, height from thickness (to scale)
    dias = [pc.dia for pc in g.pieces if pc.dia] or [30.0]
    thks = [pc.thickness for pc in g.pieces if pc.thickness] or [1.0]
    max_dia, max_thk = max(dias), max(thks)
    sc_w = 26.0 / (max_dia / 2)                 # widest pellet -> rx 26
    sc_h = (spacing * 0.62) / max_thk           # thickest pellet -> ~0.62 of the row

    # side labels
    if top:
        s.append(text(cx, y0 - 4, "CELL SIDE", 3.0, weight="bold"))
        s.append(text(cx, y_end + 9, "LID SIDE", 3.0, weight="bold"))
    elif cell:
        s.append(text(cx, y_end + 9, "SINGLE CELL", 3.0, weight="bold"))
    else:
        s.append(text(cx, y_end + 9, "CELL SIDE", 3.0, weight="bold"))

    for i, pc in enumerate(g.pieces):
        yc = y0 + spacing * (i + 0.5)
        rx = max((pc.dia or max_dia) / 2 * sc_w, 6.0)
        ry = max((pc.thickness or 1.0) * sc_h / 2, 1.4)
        fill = _SHADES[(int(pc.sno) - 1) % len(_SHADES)]
        s += _pellet(cx, yc, rx, ry, fill)
        # leader: from the right of the pellet to the label
        lx0 = cx + rx
        lx1 = cx + max_dia / 2 * sc_w + 12
        s.append(line(lx0, yc, lx1, yc, THIN))
        s.append(arrow(lx0, yc, -1, 0))
        label = pc.name if not g.show_sno else f"{int(pc.sno):02d}  {pc.name}"
        s.append(text(lx1 + 2, yc + 0.9, label, 2.4, anchor="start"))

    # SINGLE CELL (Battery Building Block): stacked rectangle, one band per pellet
    if cell and g.pieces:
        bw = 36.0
        cxb = ax1 - 42
        x0b = cxb - bw / 2
        wts = [max(pc.thickness or 1.0, 0.3) for pc in g.pieces]
        sw = sum(wts)
        avail_block = min(46.0, (y_end - y0) - 16)
        hs = [max(avail_block * w / sw, 4.0) for w in wts]
        Hb = sum(hs)
        yb = (y0 + y_end) / 2 - Hb / 2 - 6
        yy = yb
        for pc, h in zip(g.pieces, hs):
            fill = _SHADES[(int(pc.sno) - 1) % len(_SHADES)]
            s.append(rect(x0b, yy, bw, h, THICK, fill=fill))
            yy += h
        s.append(rect(x0b, yb, bw, Hb, THICK))            # outer border
        s.append(text(cxb, yb + Hb + 7, "SINGLE CELL", 2.6, weight="bold"))
        s.append(text(cxb, yb + Hb + 11.5, "(Battery Building Block)", 2.1))

    s += bom_svg
    return s


def render_assembly_svg(g: AssemblyGeom, p: AssemblyParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(PW)} {int(PH)}" '
             f'font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>']
    parts += _header(g, p)
    parts += _views(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
