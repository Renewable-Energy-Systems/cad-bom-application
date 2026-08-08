"""FastAPI app — three-input ingestion + validation layer.

Inputs:
  1. Customer package : customer_files[] (drawing) + optional tech_spec_file
  2. PID              : pid_file
  3. Design document  : design_file (.xlsx)

Pipeline on POST /api/ingest:
  - parse whatever was uploaded
  - cross-validate PID vs Design (flag mismatches; all match => proceed)
  - customer-drawing gate: if the customer drawing is missing => flag and STOP
  - if the customer drawing is present => extract Table 1 (+ IS 2102 tolerances)
"""
from __future__ import annotations

import base64
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, config
from .parsers.customer_parser import parse_customer
from .parsers.design_parser import parse_design_doc
from .parsers.pid_parser import parse_pid
from .schemas import (CadComponent, DesignDocExtraction, DesignParam,
                      IngestResult, Revision, SavedDrawing, SourceFile, Table1Row)
from .store import local_json as store
from .validation.compare import compare_pid_design
from .validation.table1 import add_row, build_table1
from .validation.tolerances import apply_general_tolerance, nominal_of
from .cad.container import ContainerParams, compute_geometry, render_container_svg
from .cad.lid import LidParams, compute_lid_geometry, render_lid_svg
from .cad.lid_assembly import (LidAssemblyParams, compute_lid_assembly,
                               render_lid_assembly_svg, DEFAULT_NOTES)
from .cad.tie_wire import TieWireParams, compute_tie_wire, render_tie_wire_svg
from .cad.teflon_disc import TeflonParams, compute_teflon, render_teflon_svg
from .cad.pellet import (PelletParams, compute_pellet, render_pellet_svg,
                         DIA_TOL, THK_TOL)
from .cad.mica_holes import (MicaHolesParams, compute_mica_holes, render_mica_holes_svg)
from .cad.housing_a import (HousingAParams, compute_housing_a, render_housing_a_svg)
from .cad.housing_b import (HousingBParams, compute_housing_b, render_housing_b_svg)
from .cad.silicon_ring_a import (SiliconRingAParams, compute_silicon_ring_a, render_silicon_ring_a_svg)
from .cad.silicon_ring_b import (SiliconRingBParams, compute_silicon_ring_b, render_silicon_ring_b_svg)
from .cad.pyro_wick import (PyroWickParams, compute_pyro_wick, render_pyro_wick_svg)
from .cad.glass_cloth_tape import (GlassClothTapeParams, compute_glass_cloth_tape, render_glass_cloth_tape_svg)
from .cad.samica_wrap import (SamicaWrapParams, compute_samica_wrap, render_samica_wrap_svg)
from .cad.fiberfrax_sheet import (FiberfraxSheetParams, compute_fiberfrax_sheet, render_fiberfrax_sheet_svg)
from .cad.current_collector import (CurrentCollectorParams, compute_current_collector, render_current_collector_svg)
from .cad.brace_plate import (BracePlateParams, compute_brace_plate, render_brace_plate_svg)
from .cad.squib import (SquibParams, compute_squib, render_squib_svg, SQUIB_TYPES)
from .cad.mica_disc_cuts import (MicaDiscCutsParams, compute_mica_disc_cuts,
                                 render_mica_disc_cuts_svg)
from .cad.lid_tie_wire import (LidTieWireParams, compute_lid_tie_wire,
                               render_lid_tie_wire_svg)
from .cad.deliver_pin import (DeliverPinParams, compute_deliver_pin, render_deliver_pin_svg)
from .cad.assembly import (AssemblyParams, AssemblyPiece, compute_assembly, render_assembly_svg)
from .cad.stack import (StackParams, compute_stack, render_stack_svg)
from .cad.image_sheet import (ImageSheetParams, compute_image_sheet,
                              render_image_sheet_svg)
from .cad.tables import container_wall, pyro_wick_dims, fiberfrax_thickness, tie_wire_width, lid_blank_thickness

app = FastAPI(title="CAD-BOM V1 — Input + Validation Layer")


@app.middleware("http")
async def _no_cache_frontend(request, call_next):
    resp = await call_next(request)
    path = request.url.path
    if path.startswith("/vendor/"):
        # pinned third-party libs (React/Babel) — cache hard, they never change
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path == "/" or path.endswith((".js", ".css", ".html")):
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


# ---- authentication --------------------------------------------------------
_seeded = auth.ensure_seed_user()
if _seeded:
    print(f"  [auth] created default user: {_seeded[0]} / {_seeded[1]}  (change it in the app)")


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    username: str
    old_password: str
    new_password: str


def require_auth(authorization: Optional[str] = Header(None)) -> str:
    """Bearer-token guard for all data/CAD endpoints."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = auth.check_token(authorization.split(" ", 1)[1].strip())
    if not user:
        raise HTTPException(status_code=401, detail="Session expired — please log in again")
    return user


@app.post("/api/login")
def login(req: LoginRequest):
    if not auth.verify(req.username, req.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"token": auth.make_token(req.username), "username": req.username}


@app.post("/api/change-password")
def change_password(req: PasswordChange, user: str = Depends(require_auth)):
    if not auth.verify(req.username, req.old_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if len(req.new_password) < 4:
        raise HTTPException(status_code=400, detail="New password is too short")
    auth.set_password(req.username, req.new_password)
    return {"ok": True}


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "model": config.EXTRACTION_MODEL,
        "api_key_configured": config.has_api_key(),
    }


def _save_upload(job_id: str, upload: UploadFile) -> Path:
    dest = store.sources_dir(job_id) / Path(upload.filename).name
    dest.write_bytes(upload.file.read())
    return dest


@app.post("/api/ingest", response_model=IngestResult)
def ingest(
    customer_files: List[UploadFile] = File(default=[]),
    tech_spec_file: Optional[UploadFile] = File(default=None),
    pid_file: Optional[UploadFile] = File(default=None),
    design_file: Optional[UploadFile] = File(default=None),
    user: str = Depends(require_auth),
):
    if not (customer_files or tech_spec_file or pid_file or design_file):
        raise HTTPException(status_code=400, detail="No input files provided.")

    job_id = uuid.uuid4().hex[:12]
    sources: list[SourceFile] = []
    warnings: list[str] = []
    result = IngestResult(job_id=job_id, created_at=datetime.now().isoformat(timespec="seconds"))

    # ---- Input 1: customer package (drawing + optional tech spec) ----------
    customer_paths: list[Path] = []
    has_customer_drawing = False
    for f in customer_files:
        if f and f.filename:
            p = _save_upload(job_id, f)
            customer_paths.append(p)
            has_customer_drawing = True
            sources.append(SourceFile(role="customer_drawing", filename=p.name))
    tech_provided = False
    if tech_spec_file and tech_spec_file.filename:
        p = _save_upload(job_id, tech_spec_file)
        customer_paths.append(p)
        tech_provided = True
        sources.append(SourceFile(role="tech_spec", filename=p.name))
    if customer_paths:
        try:
            result.customer = parse_customer(customer_paths, tech_spec_provided=tech_provided)
        except Exception as e:
            warnings.append(f"Customer extraction failed: {e}")

    # ---- Input 2: PID ------------------------------------------------------
    if pid_file and pid_file.filename:
        p = _save_upload(job_id, pid_file)
        sources.append(SourceFile(role="pid", filename=p.name))
        try:
            result.pid = parse_pid(p)
        except Exception as e:
            warnings.append(f"PID extraction failed: {e}")

    # ---- Input 3: design document (Excel) ----------------------------------
    if design_file and design_file.filename:
        p = _save_upload(job_id, design_file)
        sources.append(SourceFile(role="design_doc", filename=p.name))
        try:
            result.design_doc = parse_design_doc(p)
        except Exception as e:
            warnings.append(f"Design-document parse failed: {e}")

    # ---- Validation: PID vs Design cross-check -----------------------------
    report = compare_pid_design(result.pid, result.design_doc)

    # ---- Customer-drawing gate --------------------------------------------
    report.customer_drawing_provided = has_customer_drawing
    if not has_customer_drawing:
        report.blocked = True
        report.flags.insert(0, "Customer drawing not provided — STOPPED. Provide the customer drawing to extract Table 1.")
    else:
        # extract Table 1 only when the customer drawing exists
        result.table1 = build_table1(result.customer.table1 if result.customer else None)

    comparison_ran = result.pid is not None and result.design_doc is not None
    report.proceed = (not report.blocked) and comparison_ran and report.all_matched
    result.validation = report

    # ---- battery name resolution ------------------------------------------
    name = None
    if result.customer and result.customer.battery_name:
        name = result.customer.battery_name
    elif result.pid and result.pid.battery_number:
        name = result.pid.battery_number
    if not name:
        code = (
            (result.pid and result.pid.battery_code)
            or (result.design_doc and result.design_doc.battery_code)
        )
        name = f"Battery {code}" if code else "Untitled Battery"

    result.battery_name = name
    result.sources = sources
    result.warnings = warnings
    store.save(result)
    return result


# ---- Table 1 editing (save edits + add custom components) ------------------
class Table1Save(BaseModel):
    rows: List[Table1Row]


class AddComponent(BaseModel):
    component: str
    value: Optional[str] = None
    unit: Optional[str] = "mm"
    kind: str = "linear"


@app.put("/api/jobs/{job_id}/table1", response_model=IngestResult)
def save_table1(job_id: str, payload: Table1Save, user: str = Depends(require_auth)):
    r = store.load(job_id)
    if not r:
        raise HTTPException(status_code=404, detail="Job not found")
    # re-apply IS 2102 tolerance to each row based on its (possibly edited) value
    for row in payload.rows:
        row.tolerance = apply_general_tolerance(row.value, row.kind)
    r.table1 = payload.rows
    store.save(r)
    return r


class DesignSave(BaseModel):
    params: List[DesignParam]


@app.put("/api/jobs/{job_id}/design", response_model=IngestResult)
def save_design(job_id: str, payload: DesignSave, user: str = Depends(require_auth)):
    """Update the design-document parameters of an existing battery. CAD drawings
    read these (Container OD, Cathode Dia, Container ID/Height, PCD, …), so edits
    here flow straight into regenerated drawings."""
    r = store.load(job_id)
    if not r:
        raise HTTPException(status_code=404, detail="Job not found")
    if r.design_doc is None:
        r.design_doc = DesignDocExtraction()
    r.design_doc.params = payload.params
    store.save(r)
    return r


@app.post("/api/jobs/{job_id}/table1/add", response_model=IngestResult)
def add_component(job_id: str, payload: AddComponent, user: str = Depends(require_auth)):
    r = store.load(job_id)
    if not r:
        raise HTTPException(status_code=404, detail="Job not found")
    if not payload.component.strip():
        raise HTTPException(status_code=400, detail="Component name is required.")
    r.table1 = add_row(list(r.table1), payload.component.strip(), payload.value, payload.unit, payload.kind)
    store.save(r)
    return r


# ---- CAD: container drawing -----------------------------------------------
class ContainerRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    od: Optional[float] = None
    height: Optional[float] = None
    container_id: Optional[float] = None
    wall: Optional[float] = None              # container thickness override
    container_type: str = "deep_drawn"      # deep_drawn | flanged
    bottom_radius: Optional[float] = None    # optional for both types
    flange_kind: Optional[str] = None        # integral | welded
    flange_position: Optional[str] = None    # top | middle | bottom
    flange_width: float = 6.0
    include_section: bool = True
    revision_note: Optional[str] = None      # set from CAD Revision -> new rev row


def _table1_value(job, component_contains: str) -> Optional[float]:
    if not job:
        return None
    for r in job.table1:
        if component_contains.lower() in (r.component or "").lower():
            return nominal_of(r.value)
    return None


def _design_value(job, name: str) -> Optional[float]:
    if not job or not job.design_doc:
        return None
    key = name.lower().strip()
    for prm in job.design_doc.params:
        if key == (prm.parameter or "").lower().strip():
            return nominal_of(prm.value)
    return None


def _pid_electrode_dia(job, needle: str) -> Optional[float]:
    if not job or not job.pid:
        return None
    for e in job.pid.electrode_table:
        if needle.lower() in (e.electrode or "").lower():
            return e.dia_mm
    return None


def _pid_electrode_thk(job, needle: str) -> Optional[float]:
    if not job or not job.pid:
        return None
    for e in job.pid.electrode_table:
        if needle.lower() in (e.electrode or "").lower():
            return e.thickness_mm
    return None


def _pid_config_float(job, needle: str) -> Optional[float]:
    if not job or not job.pid:
        return None
    for kv in job.pid.configuration_data:
        if needle.lower() in (kv.key or "").lower():
            v = nominal_of(kv.value)
            if v is not None:
                return v
    return None


def _find_drg(job, *needles) -> str:
    """Drawing number of the first generated component whose name contains all needles."""
    if not job:
        return ""
    for c in job.cad_components:
        nm = (c.name or "").lower()
        if all(nd.lower() in nm for nd in needles):
            return c.drawing_no or ""
    return ""


def _find_drg_ctype(job, *ctypes) -> str:
    """Drawing number of the first generated component matching one of these ctypes."""
    if not job:
        return ""
    for c in job.cad_components:
        if c.ctype in ctypes:
            return c.drawing_no or ""
    return ""


def _battery_height(job) -> Optional[float]:
    """Full battery height: from PID tech-spec 'Dimensions (Dia * Ht)', else container height."""
    import re
    if job and job.pid:
        for kv in (job.pid.technical_spec or []):
            if "dimension" in (kv.key or "").lower() and kv.value:
                nums = re.findall(r"[0-9]+(?:\.[0-9]+)?", kv.value)
                if len(nums) >= 2:
                    try:
                        return float(nums[1])
                    except ValueError:
                        pass
    return _table1_value(job, "Height of Container")


def _container_id_value(job) -> Optional[float]:
    """Container ID from the container drawing / design doc (OD - 2*wall)."""
    cid = _design_value(job, "Container ID")
    if cid:
        return cid
    od = _design_value(job, "Container OD") or _table1_value(job, "Diameter of Battery")
    if od:
        cw = container_wall(od, "deep_drawn")
        if cw:
            return round(od - 2 * cw["wall"], 2)
    return None


def _pid_config_int(job, needle: str) -> Optional[int]:
    if not job or not job.pid:
        return None
    for kv in job.pid.configuration_data:
        if needle.lower() in (kv.key or "").lower():
            v = nominal_of(kv.value)
            if v:
                return int(v)
    return None


def _lid_diameter(job, od, cid, ctype="deep_drawn") -> Optional[float]:
    """Lid blank OD = container ID - 0.05 (Table 4a)."""
    if cid is None and od is not None:
        cw = container_wall(od, ctype)
        if cw:
            cid = od - 2 * cw["wall"]
    return round(cid - 0.05, 2) if cid is not None else None


def _next_component(job, ctype: str, name: str, forced_seq: Optional[int] = None) -> tuple[int, str, str]:
    """Return (seq, code, drawing_no); register/reuse the component on the job."""
    bc = (job and ((job.pid and job.pid.battery_code) or (job.design_doc and job.design_doc.battery_code)))
    code = f"BATTERY CODE - {bc}" if bc else ""
    seq = 1
    if forced_seq:
        seq = int(forced_seq)          # numbering driven by the user's selection order
    elif job:
        existing = next((c for c in job.cad_components if c.ctype == ctype), None)
        seq = existing.no if existing else len(job.cad_components) + 1
    drawing_no = f"RES-{bc if bc else '__'}-{seq:02d}"
    if job:
        existing = next((c for c in job.cad_components if c.ctype == ctype), None)
        if existing:
            existing.no, existing.drawing_no = seq, drawing_no
        else:
            job.cad_components.append(CadComponent(no=seq, name=name, ctype=ctype, qty="01", drawing_no=drawing_no))
        store.save(job)
    return seq, code, drawing_no


def _bump_revision(job, ctype: str, note: Optional[str], params: dict, geometry: dict) -> list:
    """Persist a component's inputs and manage its revision history.

    The FIRST generation (from CAD Drawing, no note) leaves the header revision
    table EMPTY. Only the CAD Revision module (which sends a `note`) creates rows:
    the first note -> Rev 01, the next -> Rev 02, etc., each stamped with today's
    date + the description of what changed. Returns the revision list.
    """
    if not job:
        today = datetime.now().strftime("%d/%m/%Y")
        return [Revision(rev="01", date=today, description=note.strip())] if (note and note.strip()) else []
    comp = next((c for c in job.cad_components if c.ctype == ctype), None)
    if not comp:
        return []
    if note and note.strip():
        today = datetime.now().strftime("%d/%m/%Y")
        nxt = f"{len(comp.revisions) + 1:02d}"
        comp.revisions.append(Revision(rev=nxt, date=today, description=note.strip()))
    comp.params = {k: v for k, v in params.items() if v is not None}
    comp.geometry = geometry
    store.save(job)
    return comp.revisions


@app.post("/api/cad/container")
def cad_container(req: ContainerRequest, user: str = Depends(require_auth)):
    project = code = ""
    bc = None
    od, height = req.od, req.height
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job:
        if od is None:
            od = _table1_value(job, "Diameter of Battery")
        if height is None:
            height = _table1_value(job, "Height of Container")
        project = job.battery_name or ""
        bc = (job.pid and job.pid.battery_code) or (job.design_doc and job.design_doc.battery_code)
        if bc:
            code = f"BATTERY CODE - {bc}"

    # drawing number follows the user's selection order (req.seq), else auto
    if job:
        seq, code, drawing_no = _next_component(job, "container", "CONTAINER", req.seq)
    else:
        seq = int(req.seq) if req.seq else 1
        drawing_no = f"RES-{bc if bc else '__'}-{seq:02d}"

    if od is None:
        raise HTTPException(status_code=400, detail="Container OD (battery diameter) is required — not found in the battery data; enter it manually.")
    if height is None:
        raise HTTPException(status_code=400, detail="Container height is required — not found in the battery data; enter it manually.")

    p = ContainerParams(
        od=float(od), height=float(height), container_type=req.container_type,
        container_id=req.container_id, wall=req.wall,
        bottom_radius=req.bottom_radius, flange_kind=req.flange_kind,
        flange_position=req.flange_position, flange_width=req.flange_width,
        include_section=req.include_section,
        project=project, battery_code=code, drawing_no=drawing_no,
        date=datetime.now().strftime("%d/%m/%Y"),   # Indian standard date, generation day
        show_bom=False,                              # single-part container => no BOM sub-table
    )
    g = compute_geometry(p)
    geom = {
        "od": g.od, "id": g.id, "wall": g.wall, "wall_tolerance": g.wall_tol,
        "wall_min": g.wall_min, "wall_max": g.wall_max, "od_band": g.od_band,
        "height": g.height, "bottom_radius": g.bottom_radius,
        "container_type": g.container_type, "flange_kind": g.flange_kind,
        "flange_position": g.flange_position,
    }
    params_used = {
        # container_id is DERIVED (od - 2*wall) — never frozen, so editing the
        # wall/OD recomputes the side walls automatically.
        "od": od, "height": height, "wall": g.wall,
        "container_type": req.container_type,
        "bottom_radius": req.bottom_radius, "flange_kind": req.flange_kind,
        "flange_position": req.flange_position, "flange_width": req.flange_width,
        "include_section": req.include_section,
    }
    p.revisions = _bump_revision(job, "container", req.revision_note, params_used, geom)
    svg = render_container_svg(g, p)
    return {
        "svg": svg,
        "geometry": geom,
        "params": params_used,
        "revisions": [r.dict() for r in p.revisions],
        "drawing_no": drawing_no,
        "component_no": f"{seq:02d}",
        "warnings": g.warnings,
    }


class LidRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    container_od: Optional[float] = None
    container_id: Optional[float] = None
    container_type: str = "deep_drawn"
    clearance: float = 1.0
    pin_diameter: Optional[float] = None
    num_holes: Optional[int] = None
    pcd: Optional[float] = None
    cathode_dia: Optional[float] = None
    hole_dia: Optional[float] = None
    thickness: Optional[float] = None
    groove_depth: Optional[float] = None
    groove_width: Optional[float] = None
    weld_space: Optional[float] = None
    edge_chamfer: Optional[str] = None
    hole_chamfer: Optional[str] = None
    edge_angle: Optional[float] = None
    letter_size: Optional[float] = None
    back_groove: Optional[float] = None
    hole_start_angle: Optional[float] = None
    visual_criteria: Optional[str] = None
    include_section: bool = True
    include_detail: bool = True
    revision_note: Optional[str] = None


@app.post("/api/cad/lid")
def cad_lid(req: LidRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    od, cid = req.container_od, req.container_id
    cathode = req.cathode_dia
    pcd, num_holes = req.pcd, req.num_holes
    pin = req.pin_diameter
    project = ""
    if job:
        od = od or _design_value(job, "Container OD") or _table1_value(job, "Diameter of Battery")
        cid = cid or _design_value(job, "Container ID")
        cathode = cathode or _design_value(job, "Cathode Dia") or _pid_electrode_dia(job, "cathode")
        pcd = pcd or _table1_value(job, "Pin PCD")
        num_holes = num_holes or _table1_value(job, "Number of Holes")
        # pin dia: Table 1 first, else the UI input
        pin = _table1_value(job, "Diameter of the Pin") or req.pin_diameter
        project = job.battery_name or ""
    if od is None:
        raise HTTPException(status_code=400, detail="Container OD required — not found in the battery data; enter it manually.")

    seq, code, drawing_no = _next_component(job, "lid_blank", "LID BLANK", req.seq) if job else (1, "", "RES-__-01")
    p = LidParams(
        container_od=float(od), container_id=cid, container_type=req.container_type,
        cathode_dia=cathode, pcd=pcd, num_holes=int(num_holes) if num_holes else None,
        pin_dia=pin, hole_dia=req.hole_dia, clearance=req.clearance,
        thickness=req.thickness, groove_depth=req.groove_depth, groove_width=req.groove_width,
        weld_space=req.weld_space, edge_chamfer=req.edge_chamfer, hole_chamfer=req.hole_chamfer,
        edge_angle=req.edge_angle, letter_size=req.letter_size, back_groove=req.back_groove,
        hole_start_angle=req.hole_start_angle, visual_criteria=req.visual_criteria,
        include_section=req.include_section, include_detail=req.include_detail,
        project=project, battery_code=code, drawing_no=drawing_no,
        date=datetime.now().strftime("%d/%m/%Y"),
    )
    g = compute_lid_geometry(p)
    geom = {
        "lid_od": g.lid_od, "thickness": g.thickness, "groove_depth": g.groove_depth,
        "groove_width": g.groove_width, "pcd": g.pcd, "num_holes": g.num_holes,
        "theta": g.theta, "hole_dia": g.hole_dia, "pin_dia": g.pin_dia,
        "weld_space": g.weld_space, "edge_angle": g.edge_angle,
    }
    params_used = {
        "container_od": od, "container_id": cid, "cathode_dia": cathode, "pcd": pcd,
        "num_holes": int(num_holes) if num_holes else None, "pin_diameter": pin,
        "hole_dia": req.hole_dia or g.hole_dia, "clearance": req.clearance,
        "thickness": g.thickness, "groove_depth": g.groove_depth, "groove_width": g.groove_width,
        "weld_space": g.weld_space, "edge_chamfer": g.edge_chamfer, "hole_chamfer": g.hole_chamfer,
        "edge_angle": g.edge_angle, "letter_size": g.letter_size, "back_groove": g.back_groove,
        "hole_start_angle": g.hole_start_angle, "visual_criteria": g.visual_criteria,
        "include_section": req.include_section, "include_detail": req.include_detail,
    }
    p.revisions = _bump_revision(job, "lid_blank", req.revision_note, params_used, geom)
    return {
        "svg": render_lid_svg(g, p),
        "drawing_no": drawing_no,
        "component_no": f"{seq:02d}",
        "geometry": geom,
        "params": params_used,
        "revisions": [r.dict() for r in p.revisions],
        "warnings": g.warnings,
    }


# ---- CAD: LID assembly (lid blank + deliver pins + G.M. seal) --------------
def _component_geom(job, ctype: str) -> dict:
    """Geometry stored on an already-generated component (empty if not made yet)."""
    if not job:
        return {}
    c = next((c for c in job.cad_components if c.ctype == ctype), None)
    return dict(c.geometry or {}) if c else {}


class LidAssemblyRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    lid_od: Optional[float] = None
    lid_thickness: Optional[float] = None
    pcd: Optional[float] = None
    num_holes: Optional[int] = None
    hole_dia: Optional[float] = None
    pin_dia: Optional[float] = None
    pin_length: Optional[float] = None
    upper_part: Optional[float] = None
    bottom_side: Optional[float] = None
    groove_depth: Optional[float] = None
    groove_width: Optional[float] = None
    weld_space: Optional[float] = None
    edge_angle: Optional[float] = None
    lid_od_tol: Optional[str] = None
    pin_dia_tol: Optional[str] = None
    pin_length_tol: Optional[str] = None
    thickness_tol: Optional[str] = None
    hole_start_angle: Optional[float] = None
    notes: Optional[List[str]] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/lid_assembly")
def cad_lid_assembly(req: LidAssemblyRequest, user: str = Depends(require_auth)):
    """The finished LID: the LID BLANK with a DELIVER PIN seated in each pin hole
    and the surrounding annulus filled with G.M. seal.

    Dimensions are taken from the two child drawings this app already generated
    (so a CAD Revision to either flows straight through); anything not generated
    yet is derived from the battery data exactly as those endpoints would."""
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")

    lid_g = _component_geom(job, "lid_blank")
    pin_g = _component_geom(job, "deliver_pin")

    lid_od = req.lid_od or lid_g.get("lid_od")
    thickness = req.lid_thickness or lid_g.get("thickness")
    pcd = req.pcd or lid_g.get("pcd")
    num_holes = req.num_holes or lid_g.get("num_holes")
    hole_dia = req.hole_dia or lid_g.get("hole_dia")
    pin_dia = req.pin_dia or pin_g.get("pin_dia") or lid_g.get("pin_dia")
    # pin_length is DERIVED (upper part + lid thickness + bottom side) further
    # down — only an explicit override is taken here, so editing the upper part
    # in CAD Revision actually moves the total length.
    pin_length = req.pin_length
    upper = req.upper_part if req.upper_part is not None else pin_g.get("upper_part")
    bottom = req.bottom_side if req.bottom_side is not None else pin_g.get("bottom_side")
    # edge features, so Section A-A reproduces the LID BLANK's own section
    groove_depth = req.groove_depth or lid_g.get("groove_depth")
    groove_width = req.groove_width or lid_g.get("groove_width")
    weld_space = req.weld_space or lid_g.get("weld_space")
    edge_angle = req.edge_angle or lid_g.get("edge_angle")

    project = ""
    if job:
        project = job.battery_name or ""
        # Fall back to the battery data for anything the child drawings don't
        # supply — same resolution order the LID BLANK / DELIVER PIN endpoints use.
        od = _design_value(job, "Container OD") or _table1_value(job, "Diameter of Battery")
        if (lid_od is None or thickness is None or hole_dia is None or pcd is None
                or not num_holes or groove_depth is None or weld_space is None):
            cid = _design_value(job, "Container ID")
            cathode = _design_value(job, "Cathode Dia") or _pid_electrode_dia(job, "cathode")
            lp = LidParams(
                container_od=float(od) if od else 0.0, container_id=cid, cathode_dia=cathode,
                pcd=pcd or _table1_value(job, "Pin PCD"),
                num_holes=int(num_holes) if num_holes else (
                    int(_table1_value(job, "Number of Holes"))
                    if _table1_value(job, "Number of Holes") else None),
                pin_dia=pin_dia or _table1_value(job, "Diameter of the Pin"),
                hole_dia=hole_dia, thickness=thickness)
            if od:
                lg = compute_lid_geometry(lp)
                lid_od = lid_od or lg.lid_od
                thickness = thickness or lg.thickness
                pcd = pcd or lg.pcd
                num_holes = num_holes or lg.num_holes
                hole_dia = hole_dia or lg.hole_dia
                pin_dia = pin_dia or lg.pin_dia
                groove_depth = groove_depth or lg.groove_depth
                groove_width = groove_width or lg.groove_width
                weld_space = weld_space or lg.weld_space
                edge_angle = edge_angle or lg.edge_angle
        if pin_dia is None:
            pin_dia = _table1_value(job, "Diameter of the Pin")
        if upper is None:
            upper = (_table1_value(job, "Upper Part of the Pin")
                     or _table1_value(job, "Upper Part of Pin"))

    # Total pin length = upper part + lid thickness + bottom side (the same rule
    # the DELIVER PIN drawing uses). Recomputed every time so a change to any of
    # the three drivers moves it; the child's own figure is only a last resort.
    if pin_length is None:
        if upper is not None and thickness is not None:
            pin_length = round(float(upper) + float(thickness) + float(bottom or 0), 2)
        else:
            pin_length = pin_g.get("pin_length")

    missing = [n for n, v in (("lid OD", lid_od), ("lid thickness", thickness),
                              ("pin PCD", pcd), ("number of holes", num_holes),
                              ("hole dia", hole_dia), ("pin dia", pin_dia),
                              ("total pin length", pin_length),
                              ("upper part of the pin", upper)) if not v]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=("LID: " + ", ".join(missing) + " not found. Generate the LID BLANK "
                    "and DELIVER PIN drawings first, or set these in CAD Revision."))

    seq, code, drawing_no = _next_component(job, "lid_assembly", "LID", req.seq) if job else (1, "", "RES-__-01")
    p = LidAssemblyParams(
        lid_od=float(lid_od), lid_thickness=float(thickness), pcd=float(pcd),
        num_holes=int(num_holes), hole_dia=float(hole_dia), pin_dia=float(pin_dia),
        pin_length=float(pin_length), upper_part=float(upper),
        groove_depth=float(groove_depth or 0), groove_width=float(groove_width or 0),
        weld_space=float(weld_space or 0), edge_angle=float(edge_angle or 6.0),
        lid_od_tol=req.lid_od_tol or "+0.05 / -0.15",
        pin_dia_tol=req.pin_dia_tol or "±0.1",
        pin_length_tol=req.pin_length_tol or "±0.2",
        thickness_tol=req.thickness_tol or "",
        hole_start_angle=req.hole_start_angle if req.hole_start_angle is not None else 0.0,
        notes=req.notes if req.notes is not None else list(DEFAULT_NOTES),
        lid_blank_drg=_find_drg_ctype(job, "lid_blank"),
        deliver_pin_drg=_find_drg_ctype(job, "deliver_pin"),
        component_name="LID", material="AS LISTED", project=project,
        battery_code=code, drawing_no=drawing_no,
        date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_lid_assembly(p)
    geom = {"lid_od": g.lid_od, "lid_thickness": g.lid_thickness, "pcd": g.pcd,
            "num_holes": g.num_holes, "hole_dia": g.hole_dia, "pin_dia": g.pin_dia,
            "pin_length": g.pin_length, "upper_part": g.upper_part,
            "bottom_side": g.bottom_side, "seal_width": g.seal_width,
            "groove_depth": g.groove_depth, "groove_width": g.groove_width,
            "weld_space": g.weld_space, "edge_angle": g.edge_angle}
    # Every dimension on this sheet is DERIVED from the LID BLANK and DELIVER PIN
    # drawings, so none of it is frozen — it is read back from those components on
    # each render and a CAD Revision to either child flows straight through here.
    # Only values the user explicitly overrode are stored (plus the presentation
    # choices: tolerances, hole start angle and the notes).
    params_used = {k: v for k, v in (
        ("lid_od", req.lid_od), ("lid_thickness", req.lid_thickness),
        ("pcd", req.pcd), ("num_holes", req.num_holes), ("hole_dia", req.hole_dia),
        ("pin_dia", req.pin_dia), ("pin_length", req.pin_length),
        ("upper_part", req.upper_part), ("bottom_side", req.bottom_side),
        ("groove_depth", req.groove_depth), ("groove_width", req.groove_width),
        ("weld_space", req.weld_space), ("edge_angle", req.edge_angle),
    ) if v is not None}
    params_used.update({
        "lid_od_tol": p.lid_od_tol, "pin_dia_tol": p.pin_dia_tol,
        "pin_length_tol": p.pin_length_tol, "thickness_tol": p.thickness_tol,
        "hole_start_angle": p.hole_start_angle, "notes": p.notes})
    p.revisions = _bump_revision(job, "lid_assembly", req.revision_note, params_used, geom)
    return {"svg": render_lid_assembly_svg(g, p), "drawing_no": drawing_no,
            "component_no": f"{seq:02d}", "geometry": geom, "params": params_used,
            "revisions": [r.dict() for r in p.revisions], "warnings": g.warnings,
            "ctype": "lid_assembly", "name": "LID"}


class TieWireRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    container_od: Optional[float] = None
    container_height: Optional[float] = None
    width: Optional[float] = None
    thickness: Optional[float] = None
    length: Optional[float] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/tie_wire")
def cad_tie_wire(req: TieWireRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    od, height, project = req.container_od, req.container_height, ""
    if job:
        od = od or _design_value(job, "Container OD") or _table1_value(job, "Diameter of Battery")
        height = height or _table1_value(job, "Height of Container")
        project = job.battery_name or ""
    if od is None or height is None:
        raise HTTPException(status_code=400, detail="Container OD and height required — not found; enter manually.")
    seq, code, drawing_no = _next_component(job, "tie_wire", "TIE WIRE", req.seq) if job else (1, "", "RES-__-01")
    p = TieWireParams(container_od=float(od), container_height=float(height), width=req.width,
                      thickness=req.thickness, length=req.length,
                      project=project, battery_code=code, drawing_no=drawing_no,
                      date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_tie_wire(p)
    geom = {"length": g.length, "width": g.width, "thickness": g.thickness}
    params_used = {"container_od": od, "container_height": height, "width": g.width,
                   "thickness": g.thickness, "length": g.length}
    p.revisions = _bump_revision(job, "tie_wire", req.revision_note, params_used, geom)
    return {"svg": render_tie_wire_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings}


class TeflonRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    lid_diameter: Optional[float] = None
    num_wires: Optional[int] = None
    num_holes: Optional[int] = None
    pcd: Optional[float] = None
    hole_dia: float = 1.8
    cathode_dia: Optional[float] = None
    disc_dia: Optional[float] = None
    thickness: Optional[float] = None
    cut_length: Optional[float] = None
    cut_width: Optional[float] = None
    cut_angle: Optional[float] = None       # angle between cuts
    hole_angle: Optional[float] = None      # angle between pins
    container_type: str = "deep_drawn"
    revision_note: Optional[str] = None


@app.post("/api/cad/teflon_disc")
def cad_teflon(req: TeflonRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    od = cid = pcd = num_holes = None
    cathode = req.cathode_dia
    lid_dia, num_wires, project = req.lid_diameter, req.num_wires, ""
    hole_d = req.hole_dia
    if job:
        od = _design_value(job, "Container OD") or _table1_value(job, "Diameter of Battery")
        cid = _design_value(job, "Container ID")
        cathode = cathode or _design_value(job, "Cathode Dia") or _pid_electrode_dia(job, "cathode")
        pcd = req.pcd or _table1_value(job, "Pin PCD")
        num_holes = req.num_holes or _table1_value(job, "Number of Holes")
        num_wires = num_wires or _pid_config_int(job, "tie wire")     # tie-wire count from PID
        # pin-hole dia = the pin diameter (Table 1); the pin passes through the disc
        hole_d = req.hole_dia or _table1_value(job, "Diameter of the Pin") or 1.8
        project = job.battery_name or ""
    lid_dia = lid_dia or _lid_diameter(job, od, cid, req.container_type)
    if lid_dia is None or cathode is None:
        raise HTTPException(status_code=400, detail="Lid diameter and cathode dia required — not found; provide lid diameter manually.")
    seq, code, drawing_no = _next_component(job, "teflon_disc", "TEFLON DISC", req.seq) if job else (1, "", "RES-__-01")
    p = TeflonParams(lid_diameter=float(lid_dia), stack_diameter=float(cathode), cathode_dia=float(cathode),
                     pcd=pcd, num_holes=int(num_holes) if num_holes else None, num_wires=int(num_wires) if num_wires else 3,
                     container_od=od, hole_dia=hole_d, disc_dia=req.disc_dia, thickness=req.thickness,
                     cut_length=req.cut_length, cut_width=req.cut_width, cut_angle=req.cut_angle,
                     hole_angle=req.hole_angle, project=project, battery_code=code, drawing_no=drawing_no,
                     date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_teflon(p)
    geom = {"disc_dia": g.disc_dia, "thickness": g.thickness, "inner_dia": g.inner_dia,
            "num_cuts": g.num_cuts, "cut_angle": g.cut_angle, "cut_length": g.cut_length,
            "cut_width": g.cut_width, "pcd": g.pcd, "num_holes": g.num_holes, "theta": g.theta,
            "stack_dia": g.stack_dia}
    params_used = {
        # cut_length, cut_angle, hole_angle are DERIVED (from disc/stack and the
        # counts) — never frozen, so they always recompute from their drivers.
        "lid_diameter": lid_dia, "cathode_dia": cathode, "num_wires": int(num_wires) if num_wires else 3,
        "num_holes": int(num_holes) if num_holes else None, "pcd": pcd, "hole_dia": hole_d,
        "disc_dia": g.disc_dia, "thickness": g.thickness, "cut_width": g.cut_width,
        "container_type": req.container_type}
    p.revisions = _bump_revision(job, "teflon_disc", req.revision_note, params_used, geom)
    return {"svg": render_teflon_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings}


# ---- CAD: circular pellets / discs (one generic generator) ----------------
# dia:  "cathode" | "anode" | "container_id"
# thk:  fixed_thk (const) | thk_electrode (PID electrode row) | thk_config (PID config row)
PELLET_SPECS = {
    "cathode_pellet":     {"name": "CATHODE PELLET",           "material": "CATHODE",        "dia": "cathode",      "thk_electrode": "cathode"},
    "anode_pellet":       {"name": "ANODE PELLET",             "material": "ANODE",          "dia": "anode",        "thk_electrode": "anode"},
    "electrolyte_pellet": {"name": "ELECTROLYTE PELLET",       "material": "ELECTROLYTE",    "dia": "cathode",      "thk_electrode": "electrolyte"},
    "heat_pellet_1":      {"name": "HEAT PELLET - 1",          "material": "HEAT PELLET",    "dia": "cathode",      "thk_electrode": "heatpellet-1"},
    "heat_pellet_2":      {"name": "HEAT PELLET - 2",          "material": "HEAT PELLET",    "dia": "cathode",      "thk_electrode": "heatpellet-2"},
    "heat_pellet_3":      {"name": "HEAT PELLET - 3",          "material": "HEAT PELLET",    "dia": "cathode",      "thk_electrode": "heatpellet-3"},
    "heat_pellet_1b":     {"name": "HEAT PELLET - 1B",         "material": "HEAT PELLET",    "dia": "cathode",      "thk_electrode": "heatpellet-1b"},
    "ss_disc":            {"name": "SS DISC",                  "material": "SS 304",         "dia": "cathode",      "thk_config": "S.S Disc top"},
    "ss_disc_005":        {"name": "SS DISC (0.05)",           "material": "SS 304",         "dia": "cathode",      "fixed_thk": 0.05},
    "mica_disc":          {"name": "MICA DISC",                "material": "MICA",           "dia": "cathode",      "fixed_thk": 0.15},
    "samica_disc":        {"name": "SAMICA DISC",              "material": "SAMICA",         "dia": "container_id", "fixed_thk": 0.10},
    "silicon_mica_disc":  {"name": "SILICON BONDED MICA DISC", "material": "SILICON MICA",   "dia": "container_id", "fixed_thk": 1.0},
}


class PelletRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    ctype: str
    dia: Optional[float] = None
    thickness: Optional[float] = None
    dia_tol: Optional[str] = None
    thk_tol: Optional[str] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/pellet")
def cad_pellet(req: PelletRequest, user: str = Depends(require_auth)):
    spec = PELLET_SPECS.get(req.ctype)
    if not spec:
        raise HTTPException(status_code=400, detail="Unknown pellet type.")
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")

    dia = req.dia
    if dia is None and job:
        if spec["dia"] == "cathode":
            dia = _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")
        elif spec["dia"] == "anode":
            dia = _pid_electrode_dia(job, "anode") or _design_value(job, "Anode Dia")
        elif spec["dia"] == "container_id":
            dia = _container_id_value(job)

    thk = req.thickness
    if thk is None:
        if "fixed_thk" in spec:
            thk = spec["fixed_thk"]
        elif job and spec.get("thk_electrode"):
            thk = _pid_electrode_thk(job, spec["thk_electrode"])
        elif job and spec.get("thk_config"):
            thk = _pid_config_float(job, spec["thk_config"])

    project = job.battery_name if job else ""
    if dia is None:
        raise HTTPException(status_code=400, detail=f"{spec['name']}: diameter not found in the battery data — set it in CAD Revision.")
    if thk is None:
        raise HTTPException(status_code=400, detail=f"{spec['name']}: thickness not found in the battery data — set it in CAD Revision.")

    seq, code, drawing_no = _next_component(job, req.ctype, spec["name"], req.seq) if job else (1, "", "RES-__-01")
    p = PelletParams(dia=float(dia), thickness=float(thk), dia_tol=req.dia_tol or DIA_TOL,
                     thk_tol=req.thk_tol or THK_TOL, component_name=spec["name"], material=spec["material"],
                     project=project or "", battery_code=code, drawing_no=drawing_no,
                     date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_pellet(p)
    geom = {"dia": g.dia, "thickness": g.thickness, "dia_tol": g.dia_tol, "thk_tol": g.thk_tol}
    params_used = {"ctype": req.ctype, "dia": g.dia, "thickness": g.thickness,
                   "dia_tol": g.dia_tol, "thk_tol": g.thk_tol}
    p.revisions = _bump_revision(job, req.ctype, req.revision_note, params_used, geom)
    return {"svg": render_pellet_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": req.ctype, "name": spec["name"]}


# ---- CAD: Mica Disc with holes --------------------------------------------
class MicaHolesRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    dia: Optional[float] = None
    thickness: Optional[float] = None
    pcd: Optional[float] = None
    num_holes: Optional[int] = None
    hole_dia: Optional[float] = None
    hole_start_angle: Optional[float] = None
    dia_tol: Optional[str] = None
    thk_tol: Optional[str] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/mica_holes")
def cad_mica_holes(req: MicaHolesRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    dia, pcd = req.dia, req.pcd
    num_holes, hole_dia = req.num_holes, req.hole_dia
    project = ""
    if job:
        dia = dia or _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")   # = stack dia
        pcd = pcd or _table1_value(job, "Pin PCD")
        num_holes = num_holes or _table1_value(job, "Number of Holes")
        hole_dia = hole_dia or _table1_value(job, "Diameter of the Pin")
        project = job.battery_name or ""
    if dia is None:
        raise HTTPException(status_code=400, detail="Mica Disc (holes): stack diameter not found — set it in CAD Revision.")
    # PCD = the teflon disc PCD (Table 1 Pin PCD, else cathode*0.55)
    pcd = pcd or _table1_value(job, "Pin PCD") or round(float(dia) * 0.55, 2)
    num_holes = int(num_holes) if num_holes else 6
    hole_dia = hole_dia or 2.0
    thk = req.thickness or 0.15

    seq, code, drawing_no = _next_component(job, "mica_disc_holes", "MICA DISC", req.seq) if job else (1, "", "RES-__-01")
    p = MicaHolesParams(dia=float(dia), pcd=float(pcd), num_holes=num_holes, hole_dia=float(hole_dia),
                        thickness=float(thk),
                        hole_start_angle=req.hole_start_angle if req.hole_start_angle is not None else 90.0,
                        dia_tol=req.dia_tol or DIA_TOL, thk_tol=req.thk_tol or THK_TOL,
                        component_name="MICA DISC", material="MICA", project=project,
                        battery_code=code, drawing_no=drawing_no, date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_mica_holes(p)
    geom = {"dia": g.dia, "thickness": g.thickness, "pcd": g.pcd, "num_holes": g.num_holes,
            "theta": g.theta, "hole_dia": g.hole_dia, "dia_tol": g.dia_tol, "thk_tol": g.thk_tol}
    params_used = {"dia": g.dia, "thickness": g.thickness, "pcd": g.pcd, "num_holes": g.num_holes,
                   "hole_dia": g.hole_dia, "hole_start_angle": g.hole_start_angle,
                   "dia_tol": g.dia_tol, "thk_tol": g.thk_tol}
    p.revisions = _bump_revision(job, "mica_disc_holes", req.revision_note, params_used, geom)
    return {"svg": render_mica_holes_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "mica_disc_holes", "name": "MICA DISC"}


# ---- CAD: Housing - A (annular ring assembly) -----------------------------
class HousingARequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    outer_dia: Optional[float] = None
    inner_dia: Optional[float] = None
    squib_width: Optional[float] = None
    mica_thk: Optional[float] = None
    silicon_thk: Optional[float] = None
    dia_tol_out: Optional[str] = None
    dia_tol_in: Optional[str] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/housing_a")
def cad_housing_a(req: HousingARequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    outer = req.outer_dia
    inner = req.inner_dia
    project = ""
    if job:
        outer = outer or _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")   # stack dia
        if inner is None:
            pcd = _table1_value(job, "Pin PCD") or (round(float(outer) * 0.55, 2) if outer else None)
            inner = round(pcd + 2.0, 2) if pcd else None
        project = job.battery_name or ""
    if outer is None:
        raise HTTPException(status_code=400, detail="Housing - A: stack diameter not found — set it in CAD Revision.")
    if inner is None:
        inner = round(float(outer) * 0.68, 2)
    squib = req.squib_width if req.squib_width else 5.0
    mica_thk = req.mica_thk if req.mica_thk else 0.15
    silicon_thk = req.silicon_thk if req.silicon_thk else 1.0
    bom_rows = [
        (1, "MICA RING", "01", _find_drg_ctype(job, "mica_ring")),
        (2, "SILICON BONDED MICA RING (HOUSING - A)", "02", _find_drg_ctype(job, "silicon_ring_a")),
        (3, "FIBERFRAX DISC", "02", _find_drg_ctype(job, "fiberfrax_disc")),
    ]
    seq, code, drawing_no = _next_component(job, "housing_a", "HOUSING - A", req.seq) if job else (1, "", "RES-__-01")
    p = HousingAParams(outer_dia=float(outer), inner_dia=float(inner), squib_width=float(squib),
                       mica_thk=float(mica_thk), silicon_thk=float(silicon_thk),
                       dia_tol_out=req.dia_tol_out or "+0.0/-0.2", dia_tol_in=req.dia_tol_in or "+0.2/-0.0",
                       bom_rows=bom_rows, component_name="HOUSING - A", material="ASSY",
                       project=project, battery_code=code, drawing_no=drawing_no,
                       date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_housing_a(p)
    geom = {"outer_dia": g.outer_dia, "inner_dia": g.inner_dia, "thickness": g.thickness,
            "cut_width": g.cut_width, "num_cuts": g.num_cuts}
    params_used = {"outer_dia": g.outer_dia, "inner_dia": g.inner_dia, "squib_width": squib,
                   "mica_thk": mica_thk, "silicon_thk": silicon_thk,
                   "dia_tol_out": p.dia_tol_out, "dia_tol_in": p.dia_tol_in}
    p.revisions = _bump_revision(job, "housing_a", req.revision_note, params_used, geom)
    return {"svg": render_housing_a_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "housing_a", "name": "HOUSING - A"}


# ---- CAD: Housing - B (ring + inner disc assembly) ------------------------
class HousingBRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    outer_dia: Optional[float] = None
    inner_dia: Optional[float] = None
    thickness: Optional[float] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/housing_b")
def cad_housing_b(req: HousingBRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    outer, inner = req.outer_dia, req.inner_dia
    project = ""
    if job:
        if outer is None:
            cid = _design_value(job, "Container ID")
            if cid is None:
                od = _design_value(job, "Container OD") or _table1_value(job, "Diameter of Battery")
                cw = container_wall(od, "deep_drawn") if od else None
                cid = round(od - 2 * cw["wall"], 2) if cw else None
            outer = round(cid - 1.0, 2) if cid else None
        if inner is None:
            stack = _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")
            inner = round(stack - 2.0, 2) if stack else None
        project = job.battery_name or ""
    if outer is None:
        raise HTTPException(status_code=400, detail="Housing - B: container ID not found — set the outer dia in CAD Revision.")
    if inner is None:
        inner = round(float(outer) * 0.72, 2)
    thk = req.thickness if req.thickness else 1.0
    bom_rows = [
        (1, "SILICON BONDED MICA RING (HOUSING - B)", "01", _find_drg_ctype(job, "silicon_ring_b")),
        (2, "FIBERFRAX DISC", "01", _find_drg_ctype(job, "fiberfrax_disc")),
    ]
    seq, code, drawing_no = _next_component(job, "housing_b", "HOUSING - B", req.seq) if job else (1, "", "RES-__-01")
    p = HousingBParams(outer_dia=float(outer), inner_dia=float(inner), thickness=float(thk),
                       bom_rows=bom_rows, component_name="HOUSING - B", material="ASSY",
                       project=project, battery_code=code, drawing_no=drawing_no,
                       date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_housing_b(p)
    geom = {"outer_dia": g.outer_dia, "inner_dia": g.inner_dia, "thickness": g.thickness}
    params_used = {"outer_dia": g.outer_dia, "inner_dia": g.inner_dia, "thickness": thk}
    p.revisions = _bump_revision(job, "housing_b", req.revision_note, params_used, geom)
    return {"svg": render_housing_b_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "housing_b", "name": "HOUSING - B"}


# ---- CAD: Silicon Bonded Mica Ring (Housing - A) --------------------------
class SiliconRingARequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    outer_dia: Optional[float] = None
    inner_dia: Optional[float] = None
    squib_width: Optional[float] = None
    thickness: Optional[float] = None
    dia_tol_out: Optional[str] = None
    dia_tol_in: Optional[str] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/silicon_ring_a")
def cad_silicon_ring_a(req: SiliconRingARequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    outer, inner = req.outer_dia, req.inner_dia
    project = ""
    if job:
        outer = outer or _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")
        if inner is None:
            pcd = _table1_value(job, "Pin PCD") or (round(float(outer) * 0.55, 2) if outer else None)
            inner = round(pcd + 2.0, 2) if pcd else None
        project = job.battery_name or ""
    if outer is None:
        raise HTTPException(status_code=400, detail="Silicon Bonded Mica Ring (A): stack diameter not found — set it in CAD Revision.")
    if inner is None:
        inner = round(float(outer) * 0.68, 2)
    squib = req.squib_width if req.squib_width else 5.0
    thk = req.thickness if req.thickness else 1.0
    seq, code, drawing_no = _next_component(job, "silicon_ring_a", "SILICON BONDED MICA RING (HOUSING - A)", req.seq) if job else (1, "", "RES-__-01")
    p = SiliconRingAParams(outer_dia=float(outer), inner_dia=float(inner), squib_width=float(squib),
                           thickness=float(thk), dia_tol_out=req.dia_tol_out or "+0.0/-0.2",
                           dia_tol_in=req.dia_tol_in or "+0.2/-0.0",
                           project=project, battery_code=code, drawing_no=drawing_no,
                           date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_silicon_ring_a(p)
    geom = {"outer_dia": g.outer_dia, "inner_dia": g.inner_dia, "thickness": g.thickness,
            "cut_width": g.cut_width, "num_cuts": g.num_cuts}
    params_used = {"outer_dia": g.outer_dia, "inner_dia": g.inner_dia, "squib_width": squib,
                   "thickness": thk, "dia_tol_out": p.dia_tol_out, "dia_tol_in": p.dia_tol_in}
    p.revisions = _bump_revision(job, "silicon_ring_a", req.revision_note, params_used, geom)
    return {"svg": render_silicon_ring_a_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "silicon_ring_a", "name": "SILICON BONDED MICA RING (HOUSING - A)"}


# ---- CAD: Silicon Bonded Mica Ring (Housing - B) --------------------------
class SiliconRingBRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    outer_dia: Optional[float] = None
    inner_dia: Optional[float] = None
    thickness: Optional[float] = None
    dia_tol_out: Optional[str] = None
    dia_tol_in: Optional[str] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/silicon_ring_b")
def cad_silicon_ring_b(req: SiliconRingBRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    outer, inner = req.outer_dia, req.inner_dia
    project = ""
    if job:
        if outer is None:
            cid = _design_value(job, "Container ID")
            if cid is None:
                od = _design_value(job, "Container OD") or _table1_value(job, "Diameter of Battery")
                cw = container_wall(od, "deep_drawn") if od else None
                cid = round(od - 2 * cw["wall"], 2) if cw else None
            outer = round(cid - 1.0, 2) if cid else None
        if inner is None:
            stack = _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")
            inner = round(stack - 2.0, 2) if stack else None
        project = job.battery_name or ""
    if outer is None:
        raise HTTPException(status_code=400, detail="Silicon Bonded Mica Ring (B): container ID not found — set the outer dia in CAD Revision.")
    if inner is None:
        inner = round(float(outer) * 0.72, 2)
    thk = req.thickness if req.thickness else 1.0
    seq, code, drawing_no = _next_component(job, "silicon_ring_b", "SILICON BONDED MICA RING (HOUSING - B)", req.seq) if job else (1, "", "RES-__-01")
    p = SiliconRingBParams(outer_dia=float(outer), inner_dia=float(inner), thickness=float(thk),
                           dia_tol_out=req.dia_tol_out or "+0.0/-0.2", dia_tol_in=req.dia_tol_in or "+0.2/-0.0",
                           project=project, battery_code=code, drawing_no=drawing_no,
                           date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_silicon_ring_b(p)
    geom = {"outer_dia": g.outer_dia, "inner_dia": g.inner_dia, "thickness": g.thickness}
    params_used = {"outer_dia": g.outer_dia, "inner_dia": g.inner_dia, "thickness": thk,
                   "dia_tol_out": p.dia_tol_out, "dia_tol_in": p.dia_tol_in}
    p.revisions = _bump_revision(job, "silicon_ring_b", req.revision_note, params_used, geom)
    return {"svg": render_silicon_ring_b_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "silicon_ring_b", "name": "SILICON BONDED MICA RING (HOUSING - B)"}


# ---- CAD: Mica Ring (plain ring; reuses the ring-B renderer) ---------------
class MicaRingRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    outer_dia: Optional[float] = None
    inner_dia: Optional[float] = None
    thickness: Optional[float] = None
    dia_tol_out: Optional[str] = None
    dia_tol_in: Optional[str] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/mica_ring")
def cad_mica_ring(req: MicaRingRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    outer, inner = req.outer_dia, req.inner_dia
    project = ""
    if job:
        outer = outer or _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")   # stack dia
        if inner is None:
            pcd = _table1_value(job, "Pin PCD") or (round(float(outer) * 0.55, 2) if outer else None)
            inner = round(pcd + 2.0, 2) if pcd else None
        project = job.battery_name or ""
    if outer is None:
        raise HTTPException(status_code=400, detail="Mica Ring: stack diameter not found — set the outer dia in CAD Revision.")
    if inner is None:
        inner = round(float(outer) * 0.68, 2)
    thk = req.thickness if req.thickness else 0.15
    seq, code, drawing_no = _next_component(job, "mica_ring", "MICA RING", req.seq) if job else (1, "", "RES-__-01")
    p = SiliconRingBParams(outer_dia=float(outer), inner_dia=float(inner), thickness=float(thk),
                           dia_tol_out=req.dia_tol_out or "+0.0/-0.2", dia_tol_in=req.dia_tol_in or "+0.2/-0.0",
                           component_name="MICA RING", material="MICA", quantity="01",
                           project=project, battery_code=code, drawing_no=drawing_no,
                           date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_silicon_ring_b(p)
    geom = {"outer_dia": g.outer_dia, "inner_dia": g.inner_dia, "thickness": g.thickness}
    params_used = {"outer_dia": g.outer_dia, "inner_dia": g.inner_dia, "thickness": thk,
                   "dia_tol_out": p.dia_tol_out, "dia_tol_in": p.dia_tol_in}
    p.revisions = _bump_revision(job, "mica_ring", req.revision_note, params_used, geom)
    return {"svg": render_silicon_ring_b_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "mica_ring", "name": "MICA RING"}


# ---- CAD: Pyro Wick - 01 (rectangular strip) ------------------------------
class PyroWickRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    length: Optional[float] = None
    width: Optional[float] = None
    thickness: Optional[float] = None
    container_od: Optional[float] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/pyro_wick")
def cad_pyro_wick(req: PyroWickRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    length, width, thickness = req.length, req.width, req.thickness
    od = req.container_od
    project = ""
    if job:
        cathode = _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")
        if length is None and cathode:
            length = round(float(cathode) + 10.0, 2)              # stack dia + 10
        od = od or _design_value(job, "Container OD") or _table1_value(job, "Diameter of Battery")
        project = job.battery_name or ""
    if length is None:
        raise HTTPException(status_code=400, detail="Pyro Wick-01: stack diameter not found — set the length in CAD Revision.")
    dims = pyro_wick_dims(od)                                     # width & thickness by container OD
    width = width or dims["width"]
    thickness = thickness or dims["thickness"]
    seq, code, drawing_no = _next_component(job, "pyro_wick", "PYRO WICK - 01", req.seq) if job else (1, "", "RES-__-01")
    p = PyroWickParams(length=float(length), width=float(width), thickness=float(thickness),
                       container_od=od, component_name="PYRO WICK - 01", material="PYRO WICK",
                       project=project, battery_code=code, drawing_no=drawing_no,
                       date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_pyro_wick(p)
    geom = {"length": g.length, "width": g.width, "thickness": g.thickness}
    params_used = {"length": length, "width": width, "thickness": thickness, "container_od": od}
    p.revisions = _bump_revision(job, "pyro_wick", req.revision_note, params_used, geom)
    return {"svg": render_pyro_wick_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "pyro_wick", "name": "PYRO WICK - 01"}


# ---- CAD: Pyro Wick - 02 (strip; length = container height + 20) ----------
class PyroWick02Request(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    length: Optional[float] = None
    width: Optional[float] = None
    thickness: Optional[float] = None
    container_od: Optional[float] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/pyro_wick_02")
def cad_pyro_wick_02(req: PyroWick02Request, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    length, width, thickness = req.length, req.width, req.thickness
    od = req.container_od
    project = ""
    if job:
        height = _table1_value(job, "Height of Container") or _design_value(job, "Container Height")
        if length is None and height:
            length = round(float(height) + 20.0, 2)              # container height + 20
        od = od or _design_value(job, "Container OD") or _table1_value(job, "Diameter of Battery")
        project = job.battery_name or ""
    if length is None:
        raise HTTPException(status_code=400, detail="Pyro Wick-02: container height not found — set the length in CAD Revision.")
    dims = pyro_wick_dims(od)
    width = width or dims["width"]
    thickness = thickness or dims["thickness"]
    seq, code, drawing_no = _next_component(job, "pyro_wick_02", "PYRO WICK - 02", req.seq) if job else (1, "", "RES-__-01")
    p = PyroWickParams(length=float(length), width=float(width), thickness=float(thickness),
                       container_od=od, component_name="PYRO WICK - 02", material="PYRO WICK",
                       project=project, battery_code=code, drawing_no=drawing_no,
                       date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_pyro_wick(p)
    geom = {"length": g.length, "width": g.width, "thickness": g.thickness}
    params_used = {"length": length, "width": width, "thickness": thickness, "container_od": od}
    p.revisions = _bump_revision(job, "pyro_wick_02", req.revision_note, params_used, geom)
    return {"svg": render_pyro_wick_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "pyro_wick_02", "name": "PYRO WICK - 02"}


# ---- CAD: Samica Strip / Mica Strip (strips) ------------------------------
class StripRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    length: Optional[float] = None
    width: Optional[float] = None
    thickness: Optional[float] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/samica_strip")
def cad_samica_strip(req: StripRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    length, width, thickness, project = req.length, req.width, req.thickness, ""
    if job:
        height = _table1_value(job, "Height of Container") or _design_value(job, "Container Height")
        if length is None and height:
            length = round(float(height) + 20.0, 2)              # container height + 20
        project = job.battery_name or ""
    if length is None:
        raise HTTPException(status_code=400, detail="Samica Strip: container height not found — set the length in CAD Revision.")
    width = width or 6.0
    thickness = thickness or 0.1
    seq, code, drawing_no = _next_component(job, "samica_strip", "SAMICA STRIP", req.seq) if job else (1, "", "RES-__-01")
    p = PyroWickParams(length=float(length), width=float(width), thickness=float(thickness),
                       width_note="(STD)", thk_note="(STD)", component_name="SAMICA STRIP", material="SAMICA",
                       quantity="02", project=project, battery_code=code, drawing_no=drawing_no,
                       date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_pyro_wick(p)
    geom = {"length": g.length, "width": g.width, "thickness": g.thickness}
    params_used = {"length": length, "width": width, "thickness": thickness}
    p.revisions = _bump_revision(job, "samica_strip", req.revision_note, params_used, geom)
    return {"svg": render_pyro_wick_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "samica_strip", "name": "SAMICA STRIP"}


@app.post("/api/cad/mica_strip")
def cad_mica_strip(req: StripRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    length, width, thickness, project = req.length, req.width, req.thickness, ""
    if job:
        bh = _battery_height(job)
        if length is None and bh:
            length = round(float(bh) + 20.0, 2)                  # battery height + 20
        project = job.battery_name or ""
    if length is None:
        raise HTTPException(status_code=400, detail="Mica Strip: battery height not found — set the length in CAD Revision.")
    width = width or 10.0
    thickness = thickness or 0.15
    vc = ["FREE FROM BURRS", "EDGE CUTS ARE NOT ALLOWED", "BLACK SPOTS ARE NOT ALLOWED."]
    seq, code, drawing_no = _next_component(job, "mica_strip", "MICA STRIP", req.seq) if job else (1, "", "RES-__-01")
    p = PyroWickParams(length=float(length), width=float(width), thickness=float(thickness),
                       width_note="(STD)", thk_note="(STD)", visual_criteria=vc,
                       component_name="MICA STRIP", material="CLEAR MICA", quantity="06",
                       project=project, battery_code=code, drawing_no=drawing_no,
                       date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_pyro_wick(p)
    geom = {"length": g.length, "width": g.width, "thickness": g.thickness}
    params_used = {"length": length, "width": width, "thickness": thickness}
    p.revisions = _bump_revision(job, "mica_strip", req.revision_note, params_used, geom)
    return {"svg": render_pyro_wick_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "mica_strip", "name": "MICA STRIP"}


# ---- CAD: Glass Cloth Tape (long tape with break) -------------------------
class GlassClothTapeRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    length: Optional[float] = None
    width: Optional[float] = None
    thickness: Optional[float] = None
    fiberfrax_wrap_thickness: Optional[float] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/glass_cloth_tape")
def cad_glass_cloth_tape(req: GlassClothTapeRequest, user: str = Depends(require_auth)):
    import math
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    length = req.length
    width = req.width if req.width else 25.0
    thickness = req.thickness if req.thickness else 0.2
    ff = req.fiberfrax_wrap_thickness if req.fiberfrax_wrap_thickness else 1.0
    project = ""
    if job:
        stack = _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")
        height = _table1_value(job, "Height of Container") or _design_value(job, "Container Height")
        if length is None and stack and height:
            circ = math.pi * (float(stack) + 2 * ff)             # stack + FiberFrax wrap both sides
            length = round((float(height) / width) * circ, 2)
        project = job.battery_name or ""
    if length is None:
        raise HTTPException(status_code=400, detail="Glass Cloth Tape: stack dia / container height not found — set the length in CAD Revision.")
    seq, code, drawing_no = _next_component(job, "glass_cloth_tape", "GLASS CLOTH TAPE", req.seq) if job else (1, "", "RES-__-01")
    p = GlassClothTapeParams(length=float(length), width=float(width), thickness=float(thickness),
                             component_name="GLASS CLOTH TAPE", material="GLASS CLOTH",
                             project=project, battery_code=code, drawing_no=drawing_no,
                             date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_glass_cloth_tape(p)
    geom = {"length": g.length, "width": g.width, "thickness": g.thickness}
    params_used = {"length": length, "width": width, "thickness": thickness,
                   "fiberfrax_wrap_thickness": ff}
    p.revisions = _bump_revision(job, "glass_cloth_tape", req.revision_note, params_used, geom)
    return {"svg": render_glass_cloth_tape_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "glass_cloth_tape", "name": "GLASS CLOTH TAPE"}


# ---- CAD: Adhesive Tape (plain strip with break, no hatch) ----------------
class AdhesiveTapeRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    length: Optional[float] = None
    width: Optional[float] = None
    thickness: Optional[float] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/adhesive_tape")
def cad_adhesive_tape(req: AdhesiveTapeRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    length = req.length if req.length else 100.0
    width = req.width if req.width else 12.5
    thickness = req.thickness if req.thickness else 0.2
    project = job.battery_name if job else ""
    seq, code, drawing_no = _next_component(job, "adhesive_tape", "ADHESIVE TAPE", req.seq) if job else (1, "", "RES-__-01")
    p = GlassClothTapeParams(length=float(length), width=float(width), thickness=float(thickness),
                             hatched=False, component_name="ADHESIVE TAPE", material="ADHESIVE TAPE",
                             project=project, battery_code=code, drawing_no=drawing_no,
                             date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_glass_cloth_tape(p)
    geom = {"length": g.length, "width": g.width, "thickness": g.thickness}
    params_used = {"length": length, "width": width, "thickness": thickness}
    p.revisions = _bump_revision(job, "adhesive_tape", req.revision_note, params_used, geom)
    return {"svg": render_glass_cloth_tape_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "adhesive_tape", "name": "ADHESIVE TAPE"}


# ---- CAD: Samica Wrap (plain rectangle) -----------------------------------
class SamicaWrapRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    length: Optional[float] = None
    width: Optional[float] = None
    thickness: Optional[float] = None
    fiberfrax_wrap_thickness: Optional[float] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/samica_wrap")
def cad_samica_wrap(req: SamicaWrapRequest, user: str = Depends(require_auth)):
    import math
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    length, width, thickness = req.length, req.width, req.thickness
    thickness = thickness if thickness else 0.1
    ff = req.fiberfrax_wrap_thickness if req.fiberfrax_wrap_thickness else 1.0
    project = ""
    if job:
        stack = _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")
        height = _table1_value(job, "Height of Container") or _design_value(job, "Container Height")
        if length is None and stack:
            length = round(math.pi * (float(stack) + 2 * ff) + 10.0, 2)   # circumference + 10
        if width is None and height:
            width = round(float(height) - 3.0, 2)                          # container height - 3
        project = job.battery_name or ""
    if length is None or width is None:
        raise HTTPException(status_code=400, detail="Samica Wrap: stack dia / container height not found — set length & width in CAD Revision.")
    seq, code, drawing_no = _next_component(job, "samica_wrap", "SAMICA WRAP", req.seq) if job else (1, "", "RES-__-01")
    p = SamicaWrapParams(length=float(length), width=float(width), thickness=float(thickness),
                         component_name="SAMICA WRAP", material="SAMICA",
                         project=project, battery_code=code, drawing_no=drawing_no,
                         date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_samica_wrap(p)
    geom = {"length": g.length, "width": g.width, "thickness": g.thickness}
    params_used = {"length": length, "width": width, "thickness": thickness,
                   "fiberfrax_wrap_thickness": ff}
    p.revisions = _bump_revision(job, "samica_wrap", req.revision_note, params_used, geom)
    return {"svg": render_samica_wrap_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "samica_wrap", "name": "SAMICA WRAP"}


# ---- CAD: Mica Wrap (plain rectangle; length = inner circumference + 10) ---
class MicaWrapRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    length: Optional[float] = None
    width: Optional[float] = None
    thickness: Optional[float] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/mica_wrap")
def cad_mica_wrap(req: MicaWrapRequest, user: str = Depends(require_auth)):
    import math
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    length, width, thickness = req.length, req.width, req.thickness
    thickness = thickness if thickness else 0.1
    project = ""
    if job:
        cid = _design_value(job, "Container ID")
        if cid is None:
            od = _design_value(job, "Container OD") or _table1_value(job, "Diameter of Battery")
            cw = container_wall(od, "deep_drawn") if od else None
            cid = round(od - 2 * cw["wall"], 2) if cw else None
        height = _table1_value(job, "Height of Container") or _design_value(job, "Container Height")
        if length is None and cid:
            length = round(math.pi * float(cid) + 10.0, 2)               # inner circumference + 10
        if width is None and height:
            width = round(float(height) - 3.0, 2)                        # container height - 3
        project = job.battery_name or ""
    if length is None or width is None:
        raise HTTPException(status_code=400, detail="Mica Wrap: container ID / height not found — set length & width in CAD Revision.")
    seq, code, drawing_no = _next_component(job, "mica_wrap", "MICA WRAP", req.seq) if job else (1, "", "RES-__-01")
    p = SamicaWrapParams(length=float(length), width=float(width), thickness=float(thickness),
                         component_name="MICA WRAP", material="MICA",
                         project=project, battery_code=code, drawing_no=drawing_no,
                         date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_samica_wrap(p)
    geom = {"length": g.length, "width": g.width, "thickness": g.thickness}
    params_used = {"length": length, "width": width, "thickness": thickness}
    p.revisions = _bump_revision(job, "mica_wrap", req.revision_note, params_used, geom)
    return {"svg": render_samica_wrap_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "mica_wrap", "name": "MICA WRAP"}


# ---- CAD: FiberFrax Stack Wrap / Container Insulation ---------------------
class FiberfraxSheetRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    base_length: Optional[float] = None
    width: Optional[float] = None
    thickness: Optional[float] = None
    qty: Optional[int] = None
    revision_note: Optional[str] = None


def _fiberfrax_common(job, req, kind: str):
    """Resolve (base_length, width, thickness, qty) for a FiberFrax sheet."""
    import math
    width, thickness, qty = req.width, req.thickness, req.qty
    base = req.base_length
    od = None
    if job:
        stack = _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")
        od = _design_value(job, "Container OD") or _table1_value(job, "Diameter of Battery")
        height = _table1_value(job, "Height of Container") or _design_value(job, "Container Height")
        cid = _design_value(job, "Container ID")
        if cid is None and od:
            cw = container_wall(od, "deep_drawn")
            cid = round(od - 2 * cw["wall"], 2) if cw else None
        if base is None:
            r = (float(stack) / 2) if (kind == "stack" and stack) else ((float(cid) / 2) if cid else None)
            if r is not None:
                base = round(2 * math.pi * r, 2)
        if width is None and height:
            width = round(float(height) - 3.0, 2)
    if thickness is None:
        thickness = fiberfrax_thickness(od)
    qty = int(qty) if qty else 2
    return base, width, thickness, qty


def _fiberfrax_endpoint(job, req, ctype, name, kind):
    base, width, thickness, qty = _fiberfrax_common(job, req, kind)
    if base is None or width is None:
        raise HTTPException(status_code=400, detail=f"{name}: required battery data not found — set the values in CAD Revision.")
    project = job.battery_name if job else ""
    b_note = "(Based on stack height)" if kind == "stack" else "(Based on container height)"
    seq, code, drawing_no = _next_component(job, ctype, name, req.seq) if job else (1, "", "RES-__-01")
    p = FiberfraxSheetParams(base_length=float(base), width=float(width), thickness=float(thickness),
                             qty=int(qty), b_note=b_note, component_name=name, material="FIBERFRAX",
                             project=project, battery_code=code, drawing_no=drawing_no,
                             date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_fiberfrax_sheet(p)
    geom = {"base_length": g.base_length, "width": g.width, "thickness": g.thickness, "qty": g.qty}
    params_used = {"base_length": base, "width": width, "thickness": thickness, "qty": qty}
    p.revisions = _bump_revision(job, ctype, req.revision_note, params_used, geom)
    return {"svg": render_fiberfrax_sheet_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": ctype, "name": name}


@app.post("/api/cad/fiberfrax_stack_wrap")
def cad_fiberfrax_stack_wrap(req: FiberfraxSheetRequest, user: str = Depends(require_auth)):
    import math
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    length = req.base_length            # the base_length field carries the length
    width, thickness = req.width, req.thickness
    od = None
    project = ""
    if job:
        stack = _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")
        od = _design_value(job, "Container OD") or _table1_value(job, "Diameter of Battery")
        height = _table1_value(job, "Height of Container") or _design_value(job, "Container Height")
        if length is None and stack:
            length = round(2 * math.pi * (float(stack) / 2), 2)      # stack circumference (2 pi r)
        if width is None and height:
            width = round(float(height) - 3.0, 2)                    # container height - 3
        project = job.battery_name or ""
    if thickness is None:
        thickness = fiberfrax_thickness(od)
    if length is None or width is None:
        raise HTTPException(status_code=400, detail="FiberFrax Stack Wrap: stack dia / container height not found — set length & width in CAD Revision.")
    seq, code, drawing_no = _next_component(job, "fiberfrax_stack_wrap", "FIBERFRAX STACK WRAP", req.seq) if job else (1, "", "RES-__-01")
    p = SamicaWrapParams(length=float(length), width=float(width), thickness=float(thickness),
                         component_name="FIBERFRAX STACK WRAP", material="FIBERFRAX",
                         project=project, battery_code=code, drawing_no=drawing_no,
                         date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_samica_wrap(p)
    geom = {"length": g.length, "width": g.width, "thickness": g.thickness}
    params_used = {"base_length": length, "width": width, "thickness": thickness}
    p.revisions = _bump_revision(job, "fiberfrax_stack_wrap", req.revision_note, params_used, geom)
    return {"svg": render_samica_wrap_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "fiberfrax_stack_wrap", "name": "FIBERFRAX STACK WRAP"}


@app.post("/api/cad/fiberfrax_container_insulation")
def cad_fiberfrax_container_insulation(req: FiberfraxSheetRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _fiberfrax_endpoint(job, req, "fiberfrax_container_insulation", "FIBERFRAX CONTAINER INSULATION", "container")


# ---- CAD: Squib Terminal (strip with tolerances) --------------------------
class SquibTerminalRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    length: Optional[float] = None
    width: Optional[float] = None
    thickness: Optional[float] = None
    width_tol: Optional[str] = None
    thk_tol: Optional[str] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/squib_terminal")
def cad_squib_terminal(req: SquibTerminalRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    length = req.length if req.length else 50.0
    width = req.width if req.width else 3.0
    thickness = req.thickness if req.thickness else 0.2
    wtol = req.width_tol if req.width_tol else "±0.4"
    ttol = req.thk_tol if req.thk_tol else "+0.0/-0.02"
    project = job.battery_name if job else ""
    seq, code, drawing_no = _next_component(job, "squib_terminal", "SQUIB TERMINAL", req.seq) if job else (1, "", "RES-__-01")
    p = PyroWickParams(length=float(length), width=float(width), thickness=float(thickness),
                       width_note=wtol, thk_note=ttol, hatched=False,
                       component_name="SQUIB TERMINAL", material="NICKEL",
                       project=project, battery_code=code, drawing_no=drawing_no,
                       date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_pyro_wick(p)
    geom = {"length": g.length, "width": g.width, "thickness": g.thickness}
    params_used = {"length": length, "width": width, "thickness": thickness,
                   "width_tol": wtol, "thk_tol": ttol}
    p.revisions = _bump_revision(job, "squib_terminal", req.revision_note, params_used, geom)
    return {"svg": render_pyro_wick_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "squib_terminal", "name": "SQUIB TERMINAL"}


# ---- CAD: Current Collector (Anode / Cathode) -----------------------------
class CurrentCollectorRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    disc_dia: Optional[float] = None
    disc_thickness: Optional[float] = None
    disc_tol: Optional[str] = None
    lead_length: Optional[float] = None
    lead_width: Optional[float] = None
    lead_thickness: Optional[float] = None
    gap: Optional[float] = None
    cc_type: Optional[str] = None
    revision_note: Optional[str] = None


def _current_collector_endpoint(job, req, ctype: str, kind: str):
    # disc dia = cathode diameter (both anode & cathode collectors per spec)
    disc_dia = req.disc_dia
    if disc_dia is None and job:
        disc_dia = _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")
    # Nickel Lead dims come from the Lead (Anode/Cathode) drawing; defaults match
    # the reference until a Lead drawing is generated / values are set.
    lead_length = req.lead_length if req.lead_length else 115.0
    lead_width = req.lead_width if req.lead_width else 6.0
    lead_thickness = req.lead_thickness if req.lead_thickness else 0.1
    disc_thickness = req.disc_thickness if req.disc_thickness else 0.1
    disc_tol = req.disc_tol if req.disc_tol else "0.05"
    gap = req.gap if req.gap is not None else 2.0
    cc_type = req.cc_type if req.cc_type else "B"
    if disc_dia is None:
        raise HTTPException(status_code=400, detail="Current Collector: cathode diameter not found — set disc dia in CAD Revision.")
    name = f"CURRENT COLLECTOR - {kind.upper()}"
    lead_label = "NICKEL LEAD-A" if kind == "anode" else "NICKEL LEAD-C"
    project = job.battery_name if job else ""
    seq, code, drawing_no = _next_component(job, ctype, name, req.seq) if job else (1, "", "RES-__-01")
    p = CurrentCollectorParams(
        disc_dia=float(disc_dia), lead_length=float(lead_length), lead_width=float(lead_width),
        lead_thickness=float(lead_thickness), disc_thickness=float(disc_thickness),
        disc_tol=str(disc_tol), gap=float(gap), kind=kind, cc_type=str(cc_type),
        lead_label=lead_label, component_name=name, material="SS 304 / NICKEL",
        project=project, battery_code=code, drawing_no=drawing_no,
        date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_current_collector(p)
    geom = {"disc_dia": g.disc_dia, "lead_length": g.lead_length, "lead_width": g.lead_width,
            "lead_thickness": g.lead_thickness, "disc_thickness": g.disc_thickness, "gap": g.gap}
    params_used = {"disc_dia": disc_dia, "disc_thickness": disc_thickness, "disc_tol": disc_tol,
                   "lead_length": lead_length, "lead_width": lead_width, "lead_thickness": lead_thickness,
                   "gap": gap, "cc_type": cc_type}
    p.revisions = _bump_revision(job, ctype, req.revision_note, params_used, geom)
    return {"svg": render_current_collector_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": ctype, "name": name}


@app.post("/api/cad/current_collector_anode")
def cad_current_collector_anode(req: CurrentCollectorRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _current_collector_endpoint(job, req, "current_collector_anode", "anode")


@app.post("/api/cad/current_collector_cathode")
def cad_current_collector_cathode(req: CurrentCollectorRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _current_collector_endpoint(job, req, "current_collector_cathode", "cathode")


# ---- CAD: Brace Plate (top view + section D-D + detail A) ------------------
# ---- CAD: Squib (electro-explosive igniter) -------------------------------
class SquibRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    squib_type: str = "single_head"     # single_head | single_head_wired | double_head_igniter
    total_length: Optional[float] = None
    head_length: Optional[float] = None
    head_width: Optional[float] = None
    head_thickness: Optional[float] = None
    head_corner_radius: Optional[float] = None
    head_end_radius: Optional[float] = None
    strip_width: Optional[float] = None
    strip_narrow_width: Optional[float] = None
    strip_thickness: Optional[float] = None
    body_height: Optional[float] = None
    charge_height: Optional[float] = None
    body_width: Optional[float] = None
    base_width: Optional[float] = None
    body_depth: Optional[float] = None
    wire_length: Optional[float] = None
    wire_dia: Optional[float] = None
    wire_spacing: Optional[float] = None
    wire_span_inner: Optional[float] = None
    wire_span_outer: Optional[float] = None
    pellet_width_top: Optional[float] = None
    pellet_width_bottom: Optional[float] = None
    body_width_tol: Optional[str] = None
    base_width_tol: Optional[str] = None
    body_depth_tol: Optional[str] = None
    body_height_tol: Optional[str] = None
    wire_length_tol: Optional[str] = None
    note_label: Optional[str] = None
    resistance_min: Optional[float] = None
    resistance_max: Optional[float] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/squib")
def cad_squib(req: SquibRequest, user: str = Depends(require_auth)):
    """The squib is a standard bought-in part, so the dimensions are fixed
    defaults rather than derived from the battery — all editable in CAD Revision.
    Single Head and Single Head with Wired are both titled SQUIB."""
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    st = req.squib_type if req.squib_type in SQUIB_TYPES else "single_head"
    name = SQUIB_TYPES[st]
    project = job.battery_name if job else ""
    seq, code, drawing_no = _next_component(job, "squib", name, req.seq) if job else (1, "", "RES-__-01")
    defaults = SquibParams()
    p = SquibParams(
        squib_type=st,
        total_length=req.total_length or defaults.total_length,
        head_length=req.head_length or defaults.head_length,
        head_width=req.head_width or defaults.head_width,
        head_thickness=req.head_thickness or defaults.head_thickness,
        head_corner_radius=req.head_corner_radius,
        head_end_radius=req.head_end_radius,
        strip_width=req.strip_width or defaults.strip_width,
        strip_narrow_width=req.strip_narrow_width,
        strip_thickness=req.strip_thickness or defaults.strip_thickness,
        body_height=req.body_height or getattr(defaults, 'body_height'),
        charge_height=req.charge_height or getattr(defaults, 'charge_height'),
        body_width=req.body_width or getattr(defaults, 'body_width'),
        base_width=req.base_width or getattr(defaults, 'base_width'),
        body_depth=req.body_depth or getattr(defaults, 'body_depth'),
        wire_length=req.wire_length or getattr(defaults, 'wire_length'),
        wire_dia=req.wire_dia or getattr(defaults, 'wire_dia'),
        wire_spacing=req.wire_spacing or getattr(defaults, 'wire_spacing'),
        wire_span_inner=req.wire_span_inner or getattr(defaults, 'wire_span_inner'),
        wire_span_outer=req.wire_span_outer or getattr(defaults, 'wire_span_outer'),
        pellet_width_top=req.pellet_width_top or getattr(defaults, 'pellet_width_top'),
        pellet_width_bottom=req.pellet_width_bottom or getattr(defaults, 'pellet_width_bottom'),
        body_width_tol=req.body_width_tol or getattr(defaults, 'body_width_tol'),
        base_width_tol=req.base_width_tol or getattr(defaults, 'base_width_tol'),
        body_depth_tol=req.body_depth_tol or getattr(defaults, 'body_depth_tol'),
        body_height_tol=req.body_height_tol or getattr(defaults, 'body_height_tol'),
        wire_length_tol=req.wire_length_tol or getattr(defaults, 'wire_length_tol'),
        note_label=req.note_label or defaults.note_label,
        resistance_min=req.resistance_min if req.resistance_min is not None else defaults.resistance_min,
        resistance_max=req.resistance_max if req.resistance_max is not None else defaults.resistance_max,
        component_name=name, material="AS LISTED", project=project,
        battery_code=code, drawing_no=drawing_no,
        date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_squib(p)
    geom = {"squib_type": g.squib_type, "total_length": g.total_length,
            "strip_length": g.strip_length, "head_length": g.head_length,
            "head_width": g.head_width, "head_thickness": g.head_thickness,
            "head_corner_radius": g.head_corner_radius,
        "head_end_radius": g.head_end_radius,
            "head_end_radius": g.head_end_radius,
            "strip_width": g.strip_width, "strip_narrow_width": g.strip_narrow_width,
            "strip_thickness": g.strip_thickness,
            "body_height": g.body_height,
            "charge_height": g.charge_height,
            "body_width": g.body_width,
            "base_width": g.base_width,
            "body_depth": g.body_depth,
            "wire_length": g.wire_length,
            "wire_dia": g.wire_dia,
            "wire_spacing": g.wire_spacing,
            "wire_span_inner": g.wire_span_inner,
            "wire_span_outer": g.wire_span_outer,
        "pellet_width_top": g.pellet_width_top,
        "pellet_width_bottom": g.pellet_width_bottom,
            "pellet_width_top": g.pellet_width_top,
            "pellet_width_bottom": g.pellet_width_bottom,
            "base_height": g.base_height,
            "body_height": g.body_height,
        "charge_height": g.charge_height,
        "body_width": g.body_width,
        "base_width": g.base_width,
        "body_depth": g.body_depth,
        "wire_length": g.wire_length,
        "wire_dia": g.wire_dia,
        "wire_spacing": g.wire_spacing,
        "wire_span_inner": g.wire_span_inner,
        "wire_span_outer": g.wire_span_outer,
        "body_width_tol": p.body_width_tol,
        "base_width_tol": p.base_width_tol,
        "body_depth_tol": p.body_depth_tol,
        "body_height_tol": p.body_height_tol,
        "wire_length_tol": p.wire_length_tol,
        "note_label": p.note_label,
        "resistance_min": g.resistance_min, "resistance_max": g.resistance_max}
    params_used = {
        # strip_length is DERIVED (overall - head) — never frozen, so changing
        # either driver recomputes it.
        "squib_type": st, "total_length": g.total_length, "head_length": g.head_length,
        "head_width": g.head_width, "head_thickness": g.head_thickness,
        "head_corner_radius": g.head_corner_radius,
        "strip_width": g.strip_width, "strip_narrow_width": g.strip_narrow_width,
        "strip_thickness": g.strip_thickness,
        "resistance_min": g.resistance_min, "resistance_max": g.resistance_max}
    p.revisions = _bump_revision(job, "squib", req.revision_note, params_used, geom)
    return {"svg": render_squib_svg(g, p), "drawing_no": drawing_no,
            "component_no": f"{seq:02d}", "geometry": geom, "params": params_used,
            "revisions": [r.dict() for r in p.revisions], "warnings": g.warnings,
            "ctype": "squib", "name": name}


# ---- CAD: Lid with Tie Wire -----------------------------------------------
class LidTieWireRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    lid_od: Optional[float] = None
    lid_thickness: Optional[float] = None
    pcd: Optional[float] = None
    num_holes: Optional[int] = None
    hole_dia: Optional[float] = None
    stack_dia: Optional[float] = None
    num_tie_wires: Optional[int] = None
    wire_width: Optional[float] = None
    wire_thickness: Optional[float] = None
    start_offset: Optional[float] = None
    weld_length: Optional[float] = None
    groove_circle_dia: Optional[float] = None
    hole_start_angle: Optional[float] = None
    weld_strength: Optional[str] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/lid_tie_wire")
def cad_lid_tie_wire(req: LidTieWireRequest, user: str = Depends(require_auth)):
    """Back side of the LID BLANK with the nickel tie wires welded on.

    Everything is read from the drawings already generated for this battery, so
    the sheet is specific to it — the lid from LID BLANK, the strip from TIE
    WIRE, the stack diameter and wire count from the battery data."""
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")

    lid_g = _component_geom(job, "lid_blank")
    tw_g = _component_geom(job, "tie_wire")

    lid_od = req.lid_od or lid_g.get("lid_od")
    lid_t = req.lid_thickness or lid_g.get("thickness")
    pcd = req.pcd or lid_g.get("pcd")
    n_holes = req.num_holes or lid_g.get("num_holes")
    hole_dia = req.hole_dia or lid_g.get("hole_dia")
    start_ang = req.hole_start_angle
    if start_ang is None:
        start_ang = lid_g.get("hole_start_angle", 90.0)
    stack = req.stack_dia
    n_wires = req.num_tie_wires
    ww = req.wire_width or tw_g.get("width")
    wt = req.wire_thickness or tw_g.get("thickness")
    project = ""

    if job:
        project = job.battery_name or ""
        stack = stack or _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")
        n_wires = n_wires or _pid_config_int(job, "tie wire")
        od = _design_value(job, "Container OD") or _table1_value(job, "Diameter of Battery")
        if ww is None and od:
            ww = tie_wire_width(od)
        # fall back to the lid geometry the LID BLANK endpoint would have derived
        if lid_od is None or pcd is None or not n_holes or hole_dia is None or lid_t is None:
            cid = _design_value(job, "Container ID")
            lp = LidParams(
                container_od=float(od) if od else 0.0, container_id=cid,
                cathode_dia=stack, pcd=pcd or _table1_value(job, "Pin PCD"),
                num_holes=int(n_holes) if n_holes else (
                    int(_table1_value(job, "Number of Holes"))
                    if _table1_value(job, "Number of Holes") else None),
                pin_dia=_table1_value(job, "Diameter of the Pin"),
                hole_dia=hole_dia, thickness=lid_t)
            if od:
                lg = compute_lid_geometry(lp)
                lid_od = lid_od or lg.lid_od
                lid_t = lid_t or lg.thickness
                pcd = pcd or lg.pcd
                n_holes = n_holes or lg.num_holes
                hole_dia = hole_dia or lg.hole_dia

    missing = [n for n, v in (("lid OD", lid_od), ("lid thickness", lid_t),
                              ("pin PCD", pcd), ("number of holes", n_holes),
                              ("hole dia", hole_dia), ("stack (cathode) dia", stack))
               if not v]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=("Lid with Tie Wire: " + ", ".join(missing) + " not found. Generate "
                    "the LID BLANK and TIE WIRE drawings first, or set these in CAD Revision."))

    n_wires = int(n_wires) if n_wires else 3
    p = LidTieWireParams(
        lid_od=float(lid_od), lid_thickness=float(lid_t), pcd=float(pcd),
        num_holes=int(n_holes), hole_dia=float(hole_dia), stack_dia=float(stack),
        num_tie_wires=n_wires, wire_width=float(ww) if ww else 3.0,
        wire_thickness=float(wt) if wt else 0.3,
        start_offset=req.start_offset if req.start_offset is not None else 5.0,
        weld_length=req.weld_length if req.weld_length is not None else 5.0,
        # section detail, straight off the LID BLANK / DELIVER PIN drawings
        groove_depth=lid_g.get("groove_depth") or 1.0,
        groove_width=lid_g.get("groove_width") or 1.0,
        weld_space=lid_g.get("weld_space") or 1.1,
        edge_angle=lid_g.get("edge_angle") or 6.0,
        pin_dia=lid_g.get("pin_dia") or _component_geom(job, "deliver_pin").get("pin_dia"),
        pin_upper=_component_geom(job, "deliver_pin").get("upper_part") or 0.0,
        groove_circle_dia=req.groove_circle_dia,
        hole_start_angle=float(start_ang) if start_ang is not None else 90.0,
        weld_strength=req.weld_strength or "25kgf",
        # prefer the finished LID; fall back to the LID BLANK if it isn't drawn yet
        lid_drg=(_find_drg_ctype(job, "lid_assembly")
                 or _find_drg_ctype(job, "lid_blank")),
        tie_wire_drg=_find_drg_ctype(job, "tie_wire"),
        component_name="LID WITH TIE WIRE", material="AS LISTED", project=project,
        battery_code="", drawing_no="RES-__-01", quantity="01",
        date=datetime.now().strftime("%d/%m/%Y"))
    seq, code, drawing_no = _next_component(
        job, "lid_tie_wire", "LID WITH TIE WIRE", req.seq) if job else (1, "", "RES-__-01")
    p.battery_code, p.drawing_no = code, drawing_no
    g = compute_lid_tie_wire(p)
    geom = {"lid_od": g.lid_od, "lid_thickness": g.lid_thickness, "pcd": g.pcd,
            "num_holes": g.num_holes, "hole_dia": g.hole_dia, "theta": g.theta,
            "stack_dia": g.stack_dia, "num_tie_wires": g.num_tie_wires,
            "wire_angle": g.wire_angle, "wire_width": g.wire_width,
            "wire_thickness": g.wire_thickness, "wire_start_dia": g.wire_start_dia,
            "weld_length": g.weld_length, "groove_circle_dia": g.groove_circle_dia,
            "groove_depth": g.groove_depth, "groove_width": g.groove_width,
            "weld_space": g.weld_space, "edge_angle": g.edge_angle,
            "pin_dia": g.pin_dia, "pin_upper": g.pin_upper,
            "hole_angles": g.hole_angles, "wire_angles": g.wire_angles,
            "hole_clearance": g.hole_clearance, "wire_anchor": g.wire_anchor}
    params_used = {
        # Dimensions come from the LID BLANK / TIE WIRE drawings and are NOT
        # frozen — revising either flows through. Only explicit entries persist.
        k: v for k, v in (
            ("lid_od", req.lid_od), ("lid_thickness", req.lid_thickness),
            ("pcd", req.pcd), ("num_holes", req.num_holes), ("hole_dia", req.hole_dia),
            ("stack_dia", req.stack_dia), ("num_tie_wires", req.num_tie_wires),
            ("wire_width", req.wire_width), ("wire_thickness", req.wire_thickness),
            ("groove_circle_dia", req.groove_circle_dia),
        ) if v is not None}
    params_used.update({"start_offset": p.start_offset, "weld_length": p.weld_length,
                        "hole_start_angle": p.hole_start_angle,
                        "weld_strength": p.weld_strength})
    p.revisions = _bump_revision(job, "lid_tie_wire", req.revision_note, params_used, geom)
    return {"svg": render_lid_tie_wire_svg(g, p), "drawing_no": drawing_no,
            "component_no": f"{seq:02d}", "geometry": geom, "params": params_used,
            "revisions": [r.dict() for r in p.revisions], "warnings": g.warnings,
            "ctype": "lid_tie_wire", "name": "LID WITH TIE WIRE"}


# ---- CAD: Silicon Bonded Mica Disc (2 Cuts) -------------------------------
class MicaDiscCutsRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    disc_dia: Optional[float] = None
    num_cuts: Optional[int] = None
    cut_length: Optional[float] = None
    cut_width: Optional[float] = None
    cut_clearance: Optional[float] = None      # added to the squib head size
    thickness: Optional[float] = None
    dia_tol: Optional[str] = None
    cut_start_angle: Optional[float] = None
    revision_note: Optional[str] = None


def _squib_head_size(job) -> tuple:
    """(length, width, how) of the generated SQUIB, for sizing the cuts it sits in.

    Whatever type is currently generated governs — the values are read from that
    drawing every time, never fixed.

      Single Head       -> total length 12.5, head width 3.8
      Single Head Wired -> body height 11 (leads excluded), body width 4
    """
    sg = _component_geom(job, "squib")
    if not sg:
        return None, None, ""
    if sg.get("squib_type") == "single_head_wired":
        ln, wd = sg.get("body_height"), sg.get("body_width")
        how = (f"Single Head with Wired — body {_n2(ln)} long (leads excluded), "
               f"{_n2(wd)} wide")
    else:
        ln, wd = sg.get("total_length"), sg.get("head_width")
        how = f"Single Head — {_n2(ln)} long, {_n2(wd)} wide"
    return ln, wd, how


def _n2(v):
    return "?" if v is None else (f"{float(v):g}")


def _disc_cuts_endpoint(req: "MicaDiscCutsRequest", ctype: str, name: str,
                        material: str, std_thickness: float):
    """Disc at cathode diameter with equally-spaced radial cuts, each sized from
    the SQUIB drawing: squib length + clearance long, squib width + clearance
    wide. Shared by every disc of this form — only the material and the standard
    thickness differ."""
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")

    dia = req.disc_dia
    project = ""
    if job:
        dia = dia or _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")
        project = job.battery_name or ""
    if dia is None:
        raise HTTPException(
            status_code=400,
            detail=f"{name}: cathode diameter not found — set the disc dia in CAD Revision.")

    clr = req.cut_clearance if req.cut_clearance is not None else 2.0
    cut_len, cut_wid = req.cut_length, req.cut_width
    src = ""
    if cut_len is None or cut_wid is None:
        hl, hw, src = _squib_head_size(job)
        if cut_len is None:
            cut_len = round(float(hl) + clr, 2) if hl else None
        if cut_wid is None:
            cut_wid = round(float(hw) + clr, 2) if hw else None
    if cut_len is None or cut_wid is None:
        raise HTTPException(
            status_code=400,
            detail=f"{name}: the cuts are sized from the SQUIB — generate the Squib "
                   f"drawing first, or set the cut length and width in CAD Revision.")

    n = int(req.num_cuts) if req.num_cuts else 2
    seq, code, drawing_no = _next_component(job, ctype, name, req.seq) if job else (1, "", "RES-__-01")
    p = MicaDiscCutsParams(
        disc_dia=float(dia), num_cuts=n, cut_length=float(cut_len), cut_width=float(cut_wid),
        thickness=req.thickness or std_thickness, dia_tol=req.dia_tol or "+0.00 / -0.20",
        cut_start_angle=req.cut_start_angle if req.cut_start_angle is not None else 90.0,
        component_name=name, material=material, project=project, battery_code=code,
        drawing_no=drawing_no, quantity=f"{n:02d}",
        date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_mica_disc_cuts(p)
    geom = {"disc_dia": g.disc_dia, "num_cuts": g.num_cuts, "angle": g.angle,
            "cut_length": g.cut_length, "cut_width": g.cut_width,
            "cut_gap": g.cut_gap, "thickness": g.thickness,
            "cut_start_angle": g.cut_start_angle, "cut_source": src}
    params_used = {
        # cut_length / cut_width are DERIVED from the SQUIB drawing — not frozen,
        # so revising the squib resizes the cuts. Only explicit entries persist.
        "disc_dia": req.disc_dia, "num_cuts": n, "cut_length": req.cut_length,
        "cut_width": req.cut_width, "cut_clearance": clr, "thickness": g.thickness,
        "dia_tol": p.dia_tol, "cut_start_angle": g.cut_start_angle}
    params_used = {k: v for k, v in params_used.items() if v is not None}
    p.revisions = _bump_revision(job, ctype, req.revision_note, params_used, geom)
    return {"svg": render_mica_disc_cuts_svg(g, p), "drawing_no": drawing_no,
            "component_no": f"{seq:02d}", "geometry": geom, "params": params_used,
            "revisions": [r.dict() for r in p.revisions], "warnings": g.warnings,
            "ctype": ctype, "name": name}


@app.post("/api/cad/mica_disc_cuts")
def cad_mica_disc_cuts(req: MicaDiscCutsRequest, user: str = Depends(require_auth)):
    return _disc_cuts_endpoint(req, "mica_disc_cuts",
                               "SILICON BONDED MICA DISC (2 CUTS)",
                               "SILICON BONDED MICA", 1.0)


@app.post("/api/cad/fiberfrax_disc_cuts")
def cad_fiberfrax_disc_cuts(req: MicaDiscCutsRequest, user: str = Depends(require_auth)):
    return _disc_cuts_endpoint(req, "fiberfrax_disc_cuts",
                               "FIBERFRAX DISC (2 CUTS)", "FIBERFRAX", 1.6)


class BracePlateRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    cathode_dia: Optional[float] = None
    radial_clearance: Optional[float] = None
    num_tie_wires: Optional[int] = None
    tie_wire_width: Optional[float] = None
    tie_wire_thickness: Optional[float] = None
    is_small: Optional[bool] = None
    plate_thickness: Optional[float] = None
    plate_width: Optional[float] = None
    bump_width: Optional[float] = None
    bump_height: Optional[float] = None
    bump_radius: Optional[float] = None
    strip_width: Optional[float] = None
    bump_plan_width: Optional[float] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/brace_plate")
def cad_brace_plate(req: BracePlateRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    cathode = req.cathode_dia
    od = None
    project = ""
    if job:
        cathode = cathode or _pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia")
        od = _design_value(job, "Container OD") or _table1_value(job, "Diameter of Battery")
        project = job.battery_name or ""
    if cathode is None:
        raise HTTPException(status_code=400, detail="Brace Plate: cathode diameter not found — set it in CAD Revision.")
    # small vs large battery: default from container OD (<=70 mm -> small)
    is_small = req.is_small if req.is_small is not None else (True if (od is None or float(od) <= 70) else False)
    # tie-wire width/thickness from the Tie Wire drawing (Table by OD); count from PID/Table 1
    ww = req.tie_wire_width if req.tie_wire_width else (tie_wire_width(od) if od else 3.0)
    wt = req.tie_wire_thickness if req.tie_wire_thickness else 0.3
    n = req.num_tie_wires or (job and (_pid_config_int(job, "tie wire") or _table1_value(job, "Number of Holes"))) or 3
    rc = req.radial_clearance if req.radial_clearance is not None else 6.0
    seq, code, drawing_no = _next_component(job, "brace_plate", "BRACE PLATE", req.seq) if job else (1, "", "RES-__-01")
    p = BracePlateParams(
        cathode_dia=float(cathode), radial_clearance=float(rc), num_tie_wires=int(n),
        tie_wire_width=float(ww), tie_wire_thickness=float(wt), is_small=bool(is_small),
        plate_thickness=req.plate_thickness, plate_width=req.plate_width,
        bump_width=req.bump_width, bump_height=req.bump_height,
        bump_radius=req.bump_radius if req.bump_radius else 3.0,
        strip_width=req.strip_width, bump_plan_width=req.bump_plan_width,
        component_name="BRACE PLATE", material="MS", project=project,
        battery_code=code, drawing_no=drawing_no, quantity=f"{int(n):02d}",
        date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_brace_plate(p)
    geom = {"outer_dia": g.outer_dia, "inner_dia": g.inner_dia, "num_tie_wires": g.num_tie_wires,
            "angle": g.angle, "plate_width": g.plate_width, "plate_thickness": g.plate_thickness,
            "bump_width": g.bump_width, "bump_height": g.bump_height, "total_height": g.total_height,
            "strip_width": g.strip_width, "bump_plan_width": g.bump_plan_width}
    params_used = {"cathode_dia": cathode, "radial_clearance": rc, "num_tie_wires": int(n),
                   "tie_wire_width": ww, "tie_wire_thickness": wt, "is_small": bool(is_small),
                   "plate_thickness": g.plate_thickness, "plate_width": g.plate_width,
                   "bump_width": g.bump_width, "bump_height": g.bump_height, "bump_radius": g.bump_radius,
                   "strip_width": g.strip_width, "bump_plan_width": g.bump_plan_width}
    p.revisions = _bump_revision(job, "brace_plate", req.revision_note, params_used, geom)
    return {"svg": render_brace_plate_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "brace_plate", "name": "BRACE PLATE"}


# ---- CAD: Deliver Pin (round; flat variants later) ------------------------
class DeliverPinRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    pin_type: Optional[str] = "round"
    pin_dia: Optional[float] = None
    upper_part: Optional[float] = None
    lid_thickness: Optional[float] = None
    bottom_side: Optional[float] = None
    pin_length: Optional[float] = None       # override the computed height
    dia_tol: Optional[str] = None
    flat_length: Optional[float] = None      # flat-portion length (flat pin types)
    revision_note: Optional[str] = None


@app.post("/api/cad/deliver_pin")
def cad_deliver_pin(req: DeliverPinRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    pin_dia = req.pin_dia
    upper = req.upper_part
    lid_t = req.lid_thickness
    bottom = req.bottom_side if req.bottom_side is not None else 0.0
    project = ""
    if job:
        # pin dia: Table 1, else calculated design value
        pin_dia = pin_dia or _table1_value(job, "Diameter of the Pin") or _design_value(job, "Pin Dia") \
            or _design_value(job, "Pin Diameter")
        # upper part of the pin from Table 1
        if upper is None:
            upper = _table1_value(job, "Upper Part of the Pin") or _table1_value(job, "Upper Part of Pin") \
                or _table1_value(job, "Upper")
        # lid blank thickness (Table 4b by container OD)
        if lid_t is None:
            od = _design_value(job, "Container OD") or _table1_value(job, "Diameter of Battery")
            lid_t = lid_blank_thickness(od) if od else None
        project = job.battery_name or ""
    if pin_dia is None:
        raise HTTPException(status_code=400, detail="Deliver Pin: pin dia not found — set it in CAD Revision.")
    # Deliver Pin Height = Upper part of pin + Lid Blank thickness + Bottom Side of Lid
    pin_length = req.pin_length
    if pin_length is None:
        parts = [upper, lid_t, bottom]
        if any(v is None for v in (upper, lid_t)):
            raise HTTPException(status_code=400,
                                detail="Deliver Pin: set Upper part of pin, Lid thickness and Bottom Side of Lid (CAD Revision).")
        pin_length = round(float(upper) + float(lid_t) + float(bottom), 2)
    dia_tol = req.dia_tol if req.dia_tol else "±0.1"
    pin_type = req.pin_type or "round"
    seq, code, drawing_no = _next_component(job, "deliver_pin", "DELIVER PIN", req.seq) if job else (1, "", "RES-__-01")
    p = DeliverPinParams(
        pin_dia=float(pin_dia), pin_length=float(pin_length), upper_part=float(upper or 0),
        lid_thickness=float(lid_t or 0), bottom_side=float(bottom or 0), dia_tol=dia_tol,
        pin_type=pin_type, component_name="DELIVER PIN", material="SS 304", project=project,
        battery_code=code, drawing_no=drawing_no, date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_deliver_pin(p)
    geom = {"pin_dia": g.pin_dia, "pin_length": g.pin_length, "pin_type": g.pin_type,
            "upper_part": p.upper_part, "lid_thickness": p.lid_thickness, "bottom_side": p.bottom_side}
    params_used = {"pin_dia": pin_dia, "upper_part": upper, "lid_thickness": lid_t, "bottom_side": bottom,
                   "pin_length": pin_length, "dia_tol": dia_tol, "pin_type": pin_type,
                   "flat_length": req.flat_length}
    p.revisions = _bump_revision(job, "deliver_pin", req.revision_note, params_used, geom)
    return {"svg": render_deliver_pin_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "deliver_pin", "name": "DELIVER PIN"}


# ---- CAD: Top / Bottom Assembly (stacked components) ----------------------
import re as _re


_STOP_TOK = {"mm", "of", "the", "no", "for", "and"}


def _tok(s):
    return set(t for t in _re.split(r"[^a-z0-9]+", (s or "").lower()) if t and t not in _STOP_TOK)


def _find_comp_by_name(job, name):
    """Generated component whose name token-matches `name` (subset either way)."""
    if not job:
        return None
    nt = _tok(name)
    if not nt:
        return None
    for c in job.cad_components:
        ct = _tok(c.name)
        if ct and (ct <= nt or nt <= ct):
            return c
    return None


def _find_drg_name(job, name: str) -> str:
    """Reference drawing no of a generated component matching this display name."""
    c = _find_comp_by_name(job, name)
    return (c.drawing_no or "") if c else ""


def _piece_size(job, name: str) -> tuple[float, float]:
    """(dia, thickness) of a piece from its generated drawing; sensible fallbacks."""
    dia = thk = None
    c = _find_comp_by_name(job, name)
    if c and c.geometry:
        g = c.geometry
        dia = g.get("dia") or g.get("outer_dia") or g.get("disc_dia")
        thk = g.get("thickness") or g.get("plate_thickness") or g.get("total_height")
    if dia is None:
        dia = (job and (_pid_electrode_dia(job, "cathode") or _design_value(job, "Cathode Dia"))) or 30.0
    if thk is None:
        thk = 1.0
    try:
        return float(dia), float(thk)
    except (TypeError, ValueError):
        return 30.0, 1.0


class AssemblyRow(BaseModel):
    sno: int
    name: str
    qty: Optional[int] = None
    placing_order: Optional[str] = None      # e.g. "2,4"


class AssemblyRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    rows: List[AssemblyRow] = []
    revision_note: Optional[str] = None


def _assembly_endpoint(job, req, ctype: str, name: str, atype: str):
    if not req.rows:
        raise HTTPException(status_code=400, detail=f"{name}: enter quantity and placing order for the components.")
    # build the position -> piece map from each row's placing order
    placed: dict[int, AssemblyRow] = {}
    bom = []
    warn = []
    for row in req.rows:
        order = [int(x) for x in _re.split(r"[^0-9]+", row.placing_order or "") if x]
        qty = row.qty if row.qty else (len(order) if order else 0)
        if not order and qty:
            warn.append(f"{row.name}: no placing order given.")
        for pos in order:
            if pos in placed:
                warn.append(f"Position {pos} used by more than one component.")
            placed[pos] = row
        ref = _find_drg_name(job, row.name) if job else ""
        bom.append((row.sno, row.name, qty or (len(order) or 1), ref))
    if not placed:
        raise HTTPException(status_code=400, detail=f"{name}: enter the placing order (e.g. 1 or 2,4) for at least one component.")
    total = max(placed)
    _size_cache: dict = {}

    def _size(nm):
        if nm not in _size_cache:
            _size_cache[nm] = _piece_size(job, nm)
        return _size_cache[nm]
    pieces = []
    for pos in range(1, total + 1):
        if pos in placed:
            row = placed[pos]
            d, t = _size(row.name)
            pieces.append(AssemblyPiece(sno=row.sno, name=row.name, dia=d, thickness=t))
    # cell assembly is specified bottom->top (position 1 = bottom): draw top->bottom
    if atype == "cell":
        pieces = list(reversed(pieces))
        bom = sorted(bom, key=lambda b: b[0], reverse=True)   # 06 at top, 01 at bottom
    else:
        bom = sorted(bom, key=lambda b: b[0])
    project = job.battery_name if job else ""
    seq, code, drawing_no = _next_component(job, ctype, name, req.seq) if job else (1, "", "RES-__-01")
    p = AssemblyParams(pieces=pieces, bom=bom, assembly_type=atype, show_sno=(atype != "cell"),
                       component_name=name, project=project, battery_code=code, drawing_no=drawing_no,
                       date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_assembly(p)
    g.warnings = warn
    geom = {"positions": total, "pieces": len(pieces),
            "bom": [{"sno": b[0], "name": b[1], "qty": b[2], "ref": b[3]} for b in bom]}
    params_used = {"rows": [row.dict() for row in req.rows]}
    p.revisions = _bump_revision(job, ctype, req.revision_note, params_used, geom)
    return {"svg": render_assembly_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": ctype, "name": name}


@app.post("/api/cad/top_assembly")
def cad_top_assembly(req: AssemblyRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _assembly_endpoint(job, req, "top_assembly", "TOP ASSEMBLY", "top")


@app.post("/api/cad/cell_assembly")
def cad_cell_assembly(req: AssemblyRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _assembly_endpoint(job, req, "cell_assembly", "CELL ASSEMBLY", "cell")


@app.post("/api/cad/bottom_assembly")
def cad_bottom_assembly(req: AssemblyRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _assembly_endpoint(job, req, "bottom_assembly", "BOTTOM ASSEMBLY", "bottom")


# ---- CAD: Stack (N single cells, S stacks in parallel) --------------------
class StackRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    num_cells: Optional[int] = None
    num_stacks: Optional[int] = None
    revision_note: Optional[str] = None


@app.post("/api/cad/stack")
def cad_stack(req: StackRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    num_cells = req.num_cells
    num_stacks = req.num_stacks
    project = ""
    if job:
        if num_cells is None:
            num_cells = (_pid_config_int(job, "number of cell") or _pid_config_int(job, "no of cell")
                         or _pid_config_int(job, "total cell") or _pid_config_int(job, "cells")
                         or _table1_value(job, "Number of Cells"))
        if num_stacks is None:
            num_stacks = (_pid_config_int(job, "stack") or _pid_config_int(job, "parallel"))
        project = job.battery_name or ""
    if not num_cells:
        raise HTTPException(status_code=400, detail="Stack: total number of cells (N) not found in PID — set it in CAD Revision.")
    num_stacks = int(num_stacks) if num_stacks else 1
    seq, code, drawing_no = _next_component(job, "stack", "STACK", req.seq) if job else (1, "", "RES-__-01")
    p = StackParams(num_cells=int(num_cells), num_stacks=num_stacks, component_name="STACK",
                    project=project, battery_code=code, drawing_no=drawing_no,
                    quantity=f"{num_stacks:02d}", date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_stack(p)
    geom = {"num_cells": g.num_cells, "num_stacks": g.num_stacks}
    params_used = {"num_cells": int(num_cells), "num_stacks": num_stacks}
    p.revisions = _bump_revision(job, "stack", req.revision_note, params_used, geom)
    return {"svg": render_stack_svg(g, p), "drawing_no": drawing_no, "component_no": f"{seq:02d}",
            "geometry": geom, "params": params_used, "revisions": [r.dict() for r in p.revisions],
            "warnings": g.warnings, "ctype": "stack", "name": "STACK"}


# ---- CAD: Stack Assembly (a bundled picture per stack count) ---------------
# The stack assembly is a general-arrangement view with no dimensions on it, and
# which variant applies depends only on how many stacks the battery has. So it
# is not generated from parameters and nothing is uploaded at run time: the
# artwork ships with the app in backend/assets/stack_assembly/ and the user just
# picks the variant. Adding a variant = dropping <key>.png in that folder.
STACK_ASSEMBLY_TYPES = {
    "one_stack": "ONE STACK",
    "two_stack": "TWO STACK",
    "three_stack": "THREE STACK",
}
_IMAGE_MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
ASSET_IMAGE_DIR = Path(__file__).resolve().parent / "assets"


def _image_path(group: str, key: str) -> Optional[Path]:
    """Bundled picture for a variant, whichever supported extension it uses."""
    base = ASSET_IMAGE_DIR / group
    if not base.is_dir():
        return None
    for ext in (".png", ".jpg", ".jpeg"):
        f = base / f"{key}{ext}"
        if f.is_file():
            return f
    return None


def _load_image(group: str, key: str) -> tuple:
    """(base64 payload, media type, pixel width, pixel height) — ("", ...) if absent."""
    f = _image_path(group, key)
    if not f:
        return "", "image/png", 0, 0
    raw = f.read_bytes()
    w = h = 0
    try:
        from PIL import Image
        with Image.open(BytesIO(raw)) as im:
            w, h = im.size
    except Exception:
        pass          # placed stretched, and compute_image_sheet warns about it
    return (base64.b64encode(raw).decode("ascii"),
            _IMAGE_MEDIA.get(f.suffix.lower(), "image/png"), w, h)


class StackAssemblyRequest(BaseModel):
    job_id: Optional[str] = None
    seq: Optional[int] = None
    stack_type: str = "one_stack"      # one_stack | two_stack | three_stack
    min_dpi: Optional[float] = None    # sharpness floor; higher = smaller, crisper
    revision_note: Optional[str] = None


@app.post("/api/cad/stack_assembly")
def cad_stack_assembly(req: StackAssemblyRequest, user: str = Depends(require_auth)):
    job = store.load(req.job_id) if req.job_id else None
    if req.job_id and not job:
        raise HTTPException(status_code=404, detail="Job not found")
    st = req.stack_type if req.stack_type in STACK_ASSEMBLY_TYPES else "one_stack"
    data, media, pw, ph = _load_image("stack_assembly", st)
    if not data:
        raise HTTPException(
            status_code=400,
            detail=(f"Stack Assembly: the {STACK_ASSEMBLY_TYPES[st]} drawing is not "
                    f"available yet — only ONE STACK has been added so far."))
    project = job.battery_name if job else ""
    seq, code, drawing_no = (_next_component(job, "stack_assembly", "STACK ASSEMBLY", req.seq)
                             if job else (1, "", "RES-__-01"))
    dpi_floor = float(req.min_dpi) if req.min_dpi else 120.0
    p = ImageSheetParams(
        image_data=data, image_media=media, image_px_w=pw, image_px_h=ph,
        caption=STACK_ASSEMBLY_TYPES[st], min_dpi=dpi_floor,
        component_name="STACK ASSEMBLY", material="AS LISTED", project=project or "",
        battery_code=code, drawing_no=drawing_no, quantity="01",
        date=datetime.now().strftime("%d/%m/%Y"))
    g = compute_image_sheet(p)
    geom = {"stack_type": st, "variant": STACK_ASSEMBLY_TYPES[st],
            "image_px_w": g.image_px_w, "image_px_h": g.image_px_h,
            "draw_w": g.draw_w, "draw_h": g.draw_h, "dpi": g.dpi}
    # only the variant is stored — the picture itself lives on disk, so replacing
    # it re-renders every battery that uses that variant
    params_used = {"stack_type": st, "min_dpi": dpi_floor}
    p.revisions = _bump_revision(job, "stack_assembly", req.revision_note, params_used, geom)
    return {"svg": render_image_sheet_svg(g, p), "drawing_no": drawing_no,
            "component_no": f"{seq:02d}", "geometry": geom, "params": params_used,
            "revisions": [r.dict() for r in p.revisions], "warnings": g.warnings,
            "ctype": "stack_assembly", "name": "STACK ASSEMBLY"}


# ---- Regenerate a component from its stored (revised) parameters -----------
_CAD_DISPATCH = {
    "container": (ContainerRequest, cad_container),
    "lid_blank": (LidRequest, cad_lid),
    "lid_assembly": (LidAssemblyRequest, cad_lid_assembly),
    "tie_wire": (TieWireRequest, cad_tie_wire),
    "teflon_disc": (TeflonRequest, cad_teflon),
    "mica_disc_holes": (MicaHolesRequest, cad_mica_holes),
    "housing_a": (HousingARequest, cad_housing_a),
    "housing_b": (HousingBRequest, cad_housing_b),
    "silicon_ring_a": (SiliconRingARequest, cad_silicon_ring_a),
    "silicon_ring_b": (SiliconRingBRequest, cad_silicon_ring_b),
    "mica_ring": (MicaRingRequest, cad_mica_ring),
    "pyro_wick": (PyroWickRequest, cad_pyro_wick),
    "pyro_wick_02": (PyroWick02Request, cad_pyro_wick_02),
    "samica_strip": (StripRequest, cad_samica_strip),
    "mica_strip": (StripRequest, cad_mica_strip),
    "glass_cloth_tape": (GlassClothTapeRequest, cad_glass_cloth_tape),
    "adhesive_tape": (AdhesiveTapeRequest, cad_adhesive_tape),
    "samica_wrap": (SamicaWrapRequest, cad_samica_wrap),
    "mica_wrap": (MicaWrapRequest, cad_mica_wrap),
    "fiberfrax_stack_wrap": (FiberfraxSheetRequest, cad_fiberfrax_stack_wrap),
    "fiberfrax_container_insulation": (FiberfraxSheetRequest, cad_fiberfrax_container_insulation),
    "squib_terminal": (SquibTerminalRequest, cad_squib_terminal),
    "current_collector_anode": (CurrentCollectorRequest, cad_current_collector_anode),
    "current_collector_cathode": (CurrentCollectorRequest, cad_current_collector_cathode),
    "brace_plate": (BracePlateRequest, cad_brace_plate),
    "squib": (SquibRequest, cad_squib),
    "mica_disc_cuts": (MicaDiscCutsRequest, cad_mica_disc_cuts),
    "fiberfrax_disc_cuts": (MicaDiscCutsRequest, cad_fiberfrax_disc_cuts),
    "lid_tie_wire": (LidTieWireRequest, cad_lid_tie_wire),
    "deliver_pin": (DeliverPinRequest, cad_deliver_pin),
    "top_assembly": (AssemblyRequest, cad_top_assembly),
    "bottom_assembly": (AssemblyRequest, cad_bottom_assembly),
    "cell_assembly": (AssemblyRequest, cad_cell_assembly),
    "stack": (StackRequest, cad_stack),
    "stack_assembly": (StackAssemblyRequest, cad_stack_assembly),
}
for _pct in PELLET_SPECS:
    _CAD_DISPATCH[_pct] = (PelletRequest, cad_pellet)


class RegenRequest(BaseModel):
    ctype: str


@app.post("/api/jobs/{job_id}/regenerate")
def regenerate(job_id: str, body: RegenRequest, user: str = Depends(require_auth)):
    """Re-render a component using the parameters currently stored on the job
    (i.e. whatever the CAD Revision module last changed) — used by the CAD
    Drawing module's 'Update from revision' button."""
    r = store.load(job_id)
    if not r:
        raise HTTPException(status_code=404, detail="Job not found")
    comp = next((c for c in r.cad_components if c.ctype == body.ctype), None)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not generated yet.")
    if body.ctype not in _CAD_DISPATCH:
        raise HTTPException(status_code=400, detail="Unknown component type.")
    Model, fn = _CAD_DISPATCH[body.ctype]
    params = dict(comp.params or {})
    params["job_id"] = job_id
    params["seq"] = comp.no
    try:
        req = Model(**params)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stored parameters invalid: {e}")
    out = fn(req, user)
    out["ctype"] = body.ctype
    out["name"] = comp.name
    return out


# ---- Save generated / revised drawings into Data View ---------------------
class SaveDrawingItem(BaseModel):
    ctype: str
    name: str
    no: int
    drawing_no: str
    rev: str = "01"
    svg: str


class SaveDrawingsRequest(BaseModel):
    kind: str                       # "cad" | "revision"
    drawings: List[SaveDrawingItem]


@app.post("/api/jobs/{job_id}/drawings", response_model=IngestResult)
def save_drawings(job_id: str, payload: SaveDrawingsRequest, user: str = Depends(require_auth)):
    r = store.load(job_id)
    if not r:
        raise HTTPException(status_code=404, detail="Job not found")
    if payload.kind not in ("cad", "revision"):
        raise HTTPException(status_code=400, detail="kind must be 'cad' or 'revision'.")
    if not payload.drawings:
        raise HTTPException(status_code=400, detail="No drawings to save.")
    saved_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    # upsert by (kind, ctype) — keep everything else untouched
    incoming = {(payload.kind, it.ctype) for it in payload.drawings}
    r.saved_drawings = [d for d in r.saved_drawings if (d.kind, d.ctype) not in incoming]
    for it in payload.drawings:
        r.saved_drawings.append(SavedDrawing(
            kind=payload.kind, no=it.no, name=it.name, ctype=it.ctype,
            drawing_no=it.drawing_no, rev=it.rev, svg=it.svg, saved_at=saved_at))
    r.saved_drawings.sort(key=lambda d: (0 if d.kind == "cad" else 1, d.no))
    store.save(r)
    return r


# ---- CAD: combine generated drawings into one PDF -------------------------
class PdfRequest(BaseModel):
    svgs: List[str]
    filename: Optional[str] = "drawings.pdf"


@app.post("/api/cad/pdf")
def cad_pdf(req: PdfRequest, user: str = Depends(require_auth)):
    """Merge the selected components' SVG drawings into a single multi-page PDF
    (one drawing per A4 page, in the order supplied)."""
    if not req.svgs:
        raise HTTPException(status_code=400, detail="No drawings to export.")
    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPDF
        import fitz  # PyMuPDF
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF export libraries unavailable: {e}")

    out = fitz.open()
    try:
        for svg in req.svgs:
            drawing = svg2rlg(BytesIO(svg.encode("utf-8")))
            if drawing is None:
                continue
            page_pdf = renderPDF.drawToString(drawing)
            src = fitz.open(stream=page_pdf, filetype="pdf")
            out.insert_pdf(src)
            src.close()
        data = out.tobytes()
    finally:
        out.close()

    fname = (req.filename or "drawings.pdf").strip() or "drawings.pdf"
    if not fname.lower().endswith(".pdf"):
        fname += ".pdf"
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.get("/api/jobs")
def jobs(user: str = Depends(require_auth)):
    return store.list_jobs()


@app.get("/api/jobs/{job_id}", response_model=IngestResult)
def get_job(job_id: str, user: str = Depends(require_auth)):
    r = store.load(job_id)
    if not r:
        raise HTTPException(status_code=404, detail="Job not found")
    return r


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, user: str = Depends(require_auth)):
    if not store.delete(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse({"deleted": job_id})


# ---- serve the no-build React frontend ------------------------------------
if config.FRONTEND_DIR.exists():
    @app.get("/")
    def index():
        return FileResponse(config.FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR)), name="frontend")
