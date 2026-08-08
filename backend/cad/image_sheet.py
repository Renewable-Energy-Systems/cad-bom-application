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
    caption: str = ""
    warnings: list = field(default_factory=list)


def compute_image_sheet(p: ImageSheetParams) -> ImageSheetGeom:
    """Fit the picture inside the drawing area, keeping its aspect ratio."""
    w: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    avail_w = (ax1 - ax0) - 4.0
    avail_h = (ay1 - ay0) - (9.0 if p.caption else 4.0)

    iw, ih = float(p.image_px_w or 0), float(p.image_px_h or 0)
    if iw <= 0 or ih <= 0:
        w.append("Picture size could not be read; it is fitted to the drawing area "
                 "and may be stretched.")
        dw, dh = avail_w, avail_h
    else:
        k = min(avail_w / iw, avail_h / ih)      # mm per pixel
        dw, dh = iw * k, ih * k
        # What matters for the print is how many pixels land per inch of paper.
        # A small picture stretched over an A4 sheet prints soft and blocky, so
        # say so rather than silently upscaling it.
        dpi = 25.4 / k if k > 0 else 0
        if dpi < 120:
            w.append(f"The picture is {int(iw)}x{int(ih)} px, which works out at about "
                     f"{dpi:.0f} dpi at this size — it will print soft. A scan of "
                     f"around {int(iw * 200 / max(dpi, 1)):,}x{int(ih * 200 / max(dpi, 1)):,} px "
                     f"or larger would print cleanly.")
    return ImageSheetGeom(image_px_w=int(iw), image_px_h=int(ih),
                          draw_w=round(dw, 2), draw_h=round(dh, 2),
                          caption=p.caption, warnings=w)


def _picture(g: ImageSheetGeom, p: ImageSheetParams) -> list[str]:
    s: list[str] = []
    ax0, ay0, ax1, ay1 = AREA
    top = ay0 + 2.0
    cx = (ax0 + ax1) / 2
    x = cx - g.draw_w / 2
    y = top + max(((ay1 - (9.0 if g.caption else 4.0)) - top - g.draw_h) / 2, 0.0)

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
