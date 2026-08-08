"""A CAD sheet whose body is a supplied picture, on the standard RES format.

Some assemblies are not worth generating from parameters — the STACK ASSEMBLY,
for instance, is a general-arrangement view with no dimensions on it, and which
of its variants applies depends only on how many stacks the battery has. For
those, the drawing office supplies one picture per variant and this module drops
it onto the normal sheet: the same border, revision table, allowable-deviations
table and title block as every other drawing, so the sheet still carries the
battery's own project name, code, drawing number, date and revision history.

The picture is embedded as a base64 `data:` URI rather than linked, so a saved
SVG is self-contained; that also survives the SVG -> PDF export used by
/api/cad/pdf (verified with reportlab's inline-image path).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .container import AREA, PW, PH, MED, _n, text, _header, _footer


@dataclass
class ImageSheetParams:
    image_data: str = ""                 # base64 payload, no data: prefix
    image_media: str = "image/png"
    image_px_w: int = 0                  # natural pixel size, for the aspect ratio
    image_px_h: int = 0
    caption: str = ""                    # e.g. "ONE STACK"
    frame: bool = False                  # outline around the picture
    # Never print coarser than this. Artwork exported at a sensible size lands
    # around 110-135 dpi filling the sheet, and reads cleanly; the floor is set
    # just under that so it only bites on genuinely poor artwork (a screenshot,
    # say) rather than shrinking good drawings for no gain.
    min_dpi: float = 110.0
    component_name: str = "DRAWING"
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
class ImageSheetGeom:
    image_px_w: int
    image_px_h: int
    draw_w: float                        # placed size on the sheet, mm
    draw_h: float
    dpi: float = 0.0                     # how densely it lands on the paper
    caption: str = ""
    warnings: list = field(default_factory=list)


def compute_image_sheet(p: ImageSheetParams) -> ImageSheetGeom:
    """Place the picture keeping its aspect ratio, as large as it can be drawn
    without going soft.

    Blowing a small picture up to fill the sheet is what makes it look blurred:
    each source pixel is smeared over a large patch of paper. So the placed size
    is capped at whatever keeps it at `min_dpi` — the picture comes out smaller
    but sharp, which is the right trade for a drawing that has to be read. A
    picture with pixels to spare simply fills the area as before.
    """
    w: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    avail_w = (ax1 - ax0) - 4.0
    avail_h = (ay1 - ay0) - (9.0 if p.caption else 4.0)

    iw, ih = float(p.image_px_w or 0), float(p.image_px_h or 0)
    if iw <= 0 or ih <= 0:
        w.append("Picture size could not be read; it is fitted to the drawing area "
                 "and may be stretched.")
        return ImageSheetGeom(image_px_w=0, image_px_h=0, draw_w=round(avail_w, 2),
                              draw_h=round(avail_h, 2), caption=p.caption, warnings=w)

    k_fit = min(avail_w / iw, avail_h / ih)              # mm per px, filling the area
    k_sharp = 25.4 / max(p.min_dpi, 1.0)                 # mm per px at the sharpness floor
    k = min(k_fit, k_sharp)
    dw, dh = iw * k, ih * k
    dpi = 25.4 / k

    if k_sharp < k_fit:
        # capped for sharpness — say what a bigger source would buy
        need_w = int(round(avail_w / k_sharp))
        need_h = int(round(avail_h / k_sharp))
        w.append(f"The picture is {int(iw)}x{int(ih)} px, so it is drawn "
                 f"{dw:.0f}x{dh:.0f} mm to keep it sharp at {dpi:.0f} dpi rather than "
                 f"being enlarged and going blurred. Supply it at about "
                 f"{need_w:,}x{need_h:,} px to fill the sheet at this quality.")
    return ImageSheetGeom(image_px_w=int(iw), image_px_h=int(ih),
                          draw_w=round(dw, 2), draw_h=round(dh, 2),
                          dpi=round(dpi, 1), caption=p.caption, warnings=w)


def _picture(g: ImageSheetGeom, p: ImageSheetParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    top = ay0 + 2.0
    band_bot = ay1 - (9.0 if g.caption else 4.0)
    cx = (ax0 + ax1) / 2
    x = cx - g.draw_w / 2
    # Centred across, but sitting near the top rather than floating in the middle
    # — a picture placed small for sharpness would otherwise hang in white space.
    y = top + min(6.0, max(band_bot - top - g.draw_h, 0.0))

    if not p.image_data:
        s.append(text(cx, (ay0 + ay1) / 2, "NO PICTURE SET FOR THIS VARIANT", 4.0,
                      weight="bold"))
        s.append(text(cx, (ay0 + ay1) / 2 + 6,
                      "Upload it in the CAD Drawing module, then generate again.", 2.8))
        return s

    # xlink:href as well as href — svglib reads the former, browsers read either
    href = f"data:{p.image_media};base64,{p.image_data}"
    s.append(f'<image x="{_n(x)}" y="{_n(y)}" width="{_n(g.draw_w)}" '
             f'height="{_n(g.draw_h)}" preserveAspectRatio="xMidYMid meet" '
             f'href="{href}" xlink:href="{href}"/>')
    if p.frame:
        s.append(f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(g.draw_w)}" '
                 f'height="{_n(g.draw_h)}" fill="none" stroke="#111" '
                 f'stroke-width="{MED}"/>')
    if g.caption:
        s.append(text(cx, min(y + g.draw_h + 6.5, ay1 - 1), g.caption, 3.4, weight="bold"))
    return s


def render_image_sheet_svg(g: ImageSheetGeom, p: ImageSheetParams) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" '
             f'xmlns:xlink="http://www.w3.org/1999/xlink" '
             f'viewBox="0 0 {int(PW)} {int(PH)}" font-family="Arial, sans-serif">',
             '<rect x="0" y="0" width="210" height="297" fill="#fff"/>']
    parts += _header(g, p)
    parts += _picture(g, p)
    parts += _footer(g, p)
    parts.append("</svg>")
    return "".join(parts)
