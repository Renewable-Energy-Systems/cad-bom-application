"""PID parser — Input #2.

The PID is a RES-DD-RC-03 "Production Initiation Document": an Excel-origin
tabular form exported to PDF (NOT a piping & instrumentation diagram). Sections
are detected by header text, and the same content packs into 3-5 pages, so we
extract by meaning rather than by fixed page position. Vision extraction is used
because layout/packing varies between batteries.
"""
from __future__ import annotations

from pathlib import Path

from ..schemas import PIDExtraction
from .vision import extract_structured

_PID_PROMPT = """You are reading a thermal-battery "Production Initiation Document" (form RES-DD-RC-03).
It is a tabular datasheet, NOT a piping diagram. The pages may be in any order and the
same content can be spread across several pages. Extract the following into the schema:

- form_id: the form code (e.g. "RES-DD-RC-03").
- Title block: date, battery_code, battery_number, pid_number,
  battery_configuration (the series/parallel string like "(14S 1P)"), no_of_batteries.
- electrode_table: one row per electrode/pellet. Rows are typically Anode (or "Anode
  without Cup"), Cathode, Electrolyte, Heatpellet-1, Heatpellet-1A (only if present),
  Heatpellet-2, Heatpellet-3, SS Plate at Cathode, SS Plate at Anode. Columns:
  dia_mm, weight_g, thickness_mm, density_g_cc, numbers_per_bty, oil_pressure_time
  (keep "Oil Pressure & Time" as printed text, e.g. "175 & 6").
- configuration_data: the "Battery Configuration Data" key/value block (No of cells in
  series, No of stacks, Stack weight, Uncompressed/compressed stack height, compression
  & crimping pressures, FX-70 layers, leads, tie wires, SS disc thickness, etc.).
  Put each as key/value/unit.
- raw_materials: the raw-material batch table. Fixed chemicals in order: LiCl, KCl, MgO,
  FeS2, Li2S, Fe, KClO4, Li-Si. Capture batch_number, and qty_kgs / gin_number / remarks
  when those columns exist.
- technical_spec: the "Battery Technical Specification" rows (Description / Unit /
  Parameter) as key/value/unit.
- special_instructions: the numbered free-text instruction list.

Rules: transcribe values exactly as printed. Use null for blank cells. Do not invent
values. Keep multi-line cell text as a single string. Numbers must be numeric where the
schema field is numeric; keep ratio/compound values (e.g. "175 & 6") as strings.
"""


def parse_pid(path: str | Path) -> PIDExtraction:
    return extract_structured(_PID_PROMPT, [path], PIDExtraction)
