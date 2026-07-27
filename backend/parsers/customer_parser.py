"""Customer-package parser — Input #1.

Reads the customer drawing (free format) + OPTIONAL tech spec and extracts the
13 Table-1 components using precise engineering definitions. Reads only what is
on the drawing — never invents a dimension; the IS 2102 tolerance is applied
downstream by the Table-1 builder.
"""
from __future__ import annotations

from pathlib import Path

from ..schemas import CustomerExtraction
from .vision import extract_structured

_CUSTOMER_PROMPT = """You are a mechanical-drawing analyst reading a CUSTOMER thermal-battery drawing (an
outline/envelope drawing) and possibly a separate TECH SPEC document.

IMPORTANT — read ALL sheets. The customer file often contains SEVERAL drawings/sheets (e.g. an
assembly sheet plus separate DETAIL/COMPONENT sheets). The precise TERMINAL-PIN and
MOUNTING-HOLE data is given in a DETAIL or SECTION view (e.g. "SECTION A-A") that shows the
holes on a bolt circle labelled "N Nos EQUI SPACED" together with a "PCD ⌀". You MUST take the
pin/hole data from that detail/section view — NOT from the multi-pin electrical CONNECTOR drawn
in the assembly top-view, and NOT from the tech-spec text.

Read values EXACTLY as dimensioned. If the drawing shows a tolerance (e.g. "18 ±0.2"), keep it.
Leave a field null if it is genuinely not dimensioned anywhere — NEVER guess. Put anything you
had to resolve in `notes`.

There are usually TWO different bolt circles — keep them separate:
  • TERMINAL PINS  = the electrical terminals (+ve, -ve, EI/squib). In the section/detail view
    they appear as N equi-spaced holes (often ⌀8-ish, "X DEEP") on their own PCD.
  • MOUNTING HOLES = threaded/clearance screw holes to fasten the battery down (often "M3",
    "⌀4.2 thru"), on a DIFFERENT PCD.

FLANGE: If the battery has mounting screw holes to fasten it to another part, treat it as having
a mounting flange → set has_flange = true and fill the mounting_* fields. Only when there are NO
mounting holes at all, set has_flange = false and leave flange_width, flange_thickness,
mounting_holes_pcd, mounting_hole_spacing, mounting_hole_spec all null.

Extract table1 (lengths in mm) using these EXACT definitions:

- height_of_container: Height of Container (Battery Height / Shoulder) = the height of the main
  CONTAINER CAN body (the largest-diameter cylindrical body, ⌀ = battery diameter), measured
  from the BOTTOM up to its SHOULDER, EXCLUDING the narrower lid/connector/pin assembly that sits
  above the shoulder. This is NOT the overall battery height and NOT the height that includes the
  pins/connector. Among several heights dimensioned, it is the one measuring just the can body to
  its shoulder (e.g. if 150 overall / 127 / 73 / 69 are shown, the can-body/shoulder height ≈ 69).
- diameter_of_battery: the overall DIAMETER (width) of the battery container body.
- pin_pcd: Pin PCD = the diameter of the circle passing through the centres of ALL the TERMINAL
  pins (from the section/detail view's "PCD ⌀", e.g. PCD 35.00). NOT the mounting-hole PCD.
- diameter_of_pin: LEAVE THIS null (it is entered manually later; do not fill it).
- number_of_holes: No. of Holes in the PCD = the count of equi-spaced TERMINAL holes on the pin
  PCD, taken from the section/detail view (e.g. "⌀8.00 X 10 DEEP EQUI SPACED 6 Nos" → 6). Do NOT
  count connector pins. Add labels if shown, e.g. "6 (+ve, -ve, EI1, EI2, ...)".
- angle_between_holes: Angle Between the Holes = the angular pitch at the CENTRE of the pin PCD
  between adjacent terminal holes (deg). If holes are equi-spaced and the angle is not printed,
  compute 360 / number_of_holes (e.g. 6 holes → 60°).
- upper_part_of_pin: Upper Part of the Pin = the height/length of the pin that projects ABOVE the
  lid.
- pin_hole_spec: Pin Hole Specification = the full callout for the terminal pin holes — size,
  depth, quantity, PCD, tolerance (e.g. "⌀8.00 X 10.0 DEEP, EQUI SPACED, 6 Nos, PCD 35.00").
- mounting_holes_pcd: [mounting] Mounting Holes PCD = the diameter of the circle through the
  centres of the MOUNTING screw holes (e.g. PCD 37.50). NOT the terminal-pin PCD.
- mounting_hole_spacing: [mounting] Mounting Hole Spacing = centre-to-centre distance between two
  adjacent mounting holes, Horizontal (X) and Vertical (Y), reported "H x V" — ONLY if the holes
  are on a rectangular/grid pattern. If the mounting holes are on a circular PCD, leave null.
- mounting_hole_spec: [mounting] Mounting Hole Specification = the full callout for the mounting
  holes — diameter/thread, depth, quantity, PCD, hole type (e.g. "M3 X 8.0 DEEP, EQUI SPACED,
  4 Nos, PCD 37.50" plus any "⌀4.20 Thru 2 Nos").
- flange_thickness: [flange] Flange Thickness = the axial thickness of the flange (top face to
  bottom face). Null if no distinct flange thickness is dimensioned.
- flange_width: [flange] Flange Width = the radial distance from the outer edge of the container
  body to the outer edge of the flange. Null if not dimensioned.

Also extract:
- battery_name / customer_drawing_no from the title block if shown.
- tech_spec: if a tech-spec document/table is present, capture rows as parameter/value/unit and
  set tech_spec_provided = true; otherwise leave empty and tech_spec_provided = false.
"""


def parse_customer(files: list[str | Path], tech_spec_provided: bool | None = None) -> CustomerExtraction:
    """`files` = customer drawing(s) and optionally the tech spec (1-3 files)."""
    result = extract_structured(_CUSTOMER_PROMPT, list(files), CustomerExtraction)
    if tech_spec_provided is not None:
        result.tech_spec_provided = tech_spec_provided
    return result
