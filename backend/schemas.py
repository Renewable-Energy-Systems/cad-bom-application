"""Pydantic schemas for the three software inputs, the cross-validation report,
and Table 1 (extracted from the customer drawing).

Three inputs (per product spec):
  1. Customer package  -> customer drawing(s) + OPTIONAL tech spec  (free format)
  2. PID               -> RES-DD-RC-03 Production Initiation Document (PDF form)
  3. Design document   -> Excel key/value sheet (S.No | Parameter | Unit | Value)
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 1. Customer package  ->  Table 1 fields (vision extraction)
# --------------------------------------------------------------------------- #
class DrawingTable1(BaseModel):
    """The 13 Table-1 components, as read from the customer drawing.

    Values are strings so we preserve exactly what the drawing shows (e.g.
    "Ø2.0", "18 ±0.2", "4 x M3"). Blank = not dimensioned on the drawing.
    """
    has_flange: Optional[bool] = Field(None, description="Whether the battery/container has a mounting flange")
    height_of_container: Optional[str] = Field(None, description="Height of Container (Battery Height / Shoulder)")
    diameter_of_battery: Optional[str] = Field(None, description="Diameter of Battery")
    pin_pcd: Optional[str] = Field(None, description="Pin PCD (terminal-pin pitch circle dia)")
    diameter_of_pin: Optional[str] = Field(None, description="Diameter of the Pin")
    number_of_holes: Optional[str] = Field(None, description="Number of Holes (+ve, -ve, EI1, EI2)")
    angle_between_holes: Optional[str] = Field(None, description="Angle between the Holes (deg)")
    mounting_holes_pcd: Optional[str] = Field(None, description="Mounting Holes PCD")
    upper_part_of_pin: Optional[str] = Field(None, description="Upper Part of the Pin (pin height above lid)")
    mounting_hole_spacing: Optional[str] = Field(None, description="Mounting Hole Spacing (Horizontal and Vertical)")
    flange_width: Optional[str] = Field(None, description="Flange Width")
    flange_thickness: Optional[str] = Field(None, description="Flange Thickness")
    pin_hole_spec: Optional[str] = Field(None, description="Pin Hole Spec")
    mounting_hole_spec: Optional[str] = Field(None, description="Mounting Hole Spec")


class TechSpecItem(BaseModel):
    parameter: str
    value: Optional[str] = None
    unit: Optional[str] = None


class CustomerExtraction(BaseModel):
    battery_name: Optional[str] = None
    customer_drawing_no: Optional[str] = None
    table1: DrawingTable1 = Field(default_factory=DrawingTable1)
    tech_spec: List[TechSpecItem] = Field(default_factory=list)
    tech_spec_provided: bool = False
    notes: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 2. PID (RES-DD-RC-03)
# --------------------------------------------------------------------------- #
class ElectrodeRow(BaseModel):
    electrode: str
    dia_mm: Optional[float] = None
    weight_g: Optional[float] = None
    thickness_mm: Optional[float] = None
    density_g_cc: Optional[float] = None
    numbers_per_bty: Optional[str] = None
    oil_pressure_time: Optional[str] = None


class RawMaterialRow(BaseModel):
    raw_material: str
    batch_number: Optional[str] = None
    qty_kgs: Optional[str] = None
    gin_number: Optional[str] = None
    remarks: Optional[str] = None


class KeyValue(BaseModel):
    key: str
    value: Optional[str] = None
    unit: Optional[str] = None


class PIDExtraction(BaseModel):
    form_id: Optional[str] = None
    date: Optional[str] = None
    battery_code: Optional[str] = None
    battery_number: Optional[str] = None
    pid_number: Optional[str] = None
    battery_configuration: Optional[str] = None
    no_of_batteries: Optional[str] = None
    electrode_table: List[ElectrodeRow] = Field(default_factory=list)
    configuration_data: List[KeyValue] = Field(default_factory=list)
    raw_materials: List[RawMaterialRow] = Field(default_factory=list)
    technical_spec: List[KeyValue] = Field(default_factory=list)
    special_instructions: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 3. Design document — Excel
# --------------------------------------------------------------------------- #
class DesignParam(BaseModel):
    s_no: Optional[int] = None
    parameter: str
    unit: Optional[str] = None
    value: Optional[str] = None


class DesignDocExtraction(BaseModel):
    battery_code: Optional[str] = None
    build_no: Optional[str] = None
    design_version: Optional[str] = None
    params: List[DesignParam] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Cross-validation: PID vs Design document
# --------------------------------------------------------------------------- #
class CompareRow(BaseModel):
    parameter: str
    pid_value: Optional[str] = None
    design_value: Optional[str] = None
    status: str  # "match" | "mismatch" | "missing"


class ValidationReport(BaseModel):
    comparison: List[CompareRow] = Field(default_factory=list)
    matched: int = 0
    mismatched: int = 0
    missing: int = 0
    all_matched: bool = False          # every comparable pair matched
    customer_drawing_provided: bool = False
    blocked: bool = False              # True => customer drawing missing => STOP
    proceed: bool = False              # True => cleared to continue downstream
    flags: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Table 1 (final, display/edit form — 13 fixed rows + any user-added rows)
# --------------------------------------------------------------------------- #
class Table1Row(BaseModel):
    s_no: int
    component: str
    value: Optional[str] = None        # nominal value as read (may include on-drawing tol)
    unit: Optional[str] = None
    tolerance: Optional[str] = None    # applied IS 2102 tol, or "as specified on drawing"
    kind: str = "linear"               # linear | angular | count | spec
    source: str = "customer_drawing"   # customer_drawing | user
    note: Optional[str] = None         # e.g. "N/A — no flange on this battery"


# --------------------------------------------------------------------------- #
# Combined ingest result (one per battery job)
# --------------------------------------------------------------------------- #
class SourceFile(BaseModel):
    role: str  # customer_drawing | tech_spec | pid | design_doc
    filename: str


class Revision(BaseModel):
    """One row of the drawing's revision table (header, left side)."""
    rev: str                   # "01", "02", ...
    date: str                  # DD/MM/YYYY (day the change was made)
    description: str = ""       # what changed / modification done


class CadComponent(BaseModel):
    """A generated CAD component drawing, numbered sequentially per battery."""
    no: int                    # 1, 2, 3 ... (container generated first = 1)
    name: str                  # e.g. CONTAINER
    ctype: str = ""            # container | lid | disc ...
    qty: str = "01"
    drawing_no: str = ""       # RES-<code>-<no>
    revisions: List[Revision] = Field(default_factory=list)   # rev history
    params: dict = Field(default_factory=dict)                # last-used input dims
    geometry: dict = Field(default_factory=dict)              # last computed geometry


class SavedDrawing(BaseModel):
    """A drawing saved into Data View (from CAD Drawing or CAD Revision)."""
    kind: str                  # "cad" | "revision"
    no: int
    name: str
    ctype: str = ""
    drawing_no: str = ""
    rev: str = "01"
    svg: str = ""
    saved_at: str = ""


class IngestResult(BaseModel):
    job_id: str
    battery_name: Optional[str] = None
    created_at: str
    sources: List[SourceFile] = Field(default_factory=list)
    customer: Optional[CustomerExtraction] = None
    pid: Optional[PIDExtraction] = None
    design_doc: Optional[DesignDocExtraction] = None
    validation: Optional[ValidationReport] = None
    table1: List[Table1Row] = Field(default_factory=list)
    cad_components: List[CadComponent] = Field(default_factory=list)
    saved_drawings: List[SavedDrawing] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
