# CAD-BOM V1

Turns thermal-battery paperwork into manufacturing drawings. Three documents go in;
the app extracts and cross-checks the data, then generates ~41 dimensioned A4
component drawings in RES title-block format, exportable as a single PDF.

```
3 inputs ──parse──> cross-validate ──gate──> Table 1 ──derive──> CAD components ──> PDF
```

## Run

```bash
pip install -r requirements.txt
cp .env.example .env          # then put your GOOGLE_API_KEY in .env
python run.py                 # serves http://127.0.0.1:8020
```

Log in with **`admin` / `admin123`** (seeded on first run — change it from the UI).
Then: **Data Entry** → upload inputs → *Ingest & Extract* → **CAD Drawing** → pick
components → *Generate*.

Everything is stored under `data/jobs/<id>/` (`result.json` + the uploaded source
files). That directory is gitignored — job data never leaves the machine.

## The three inputs

| # | Input | Files | How it's parsed |
|---|-------|-------|-----------------|
| 1 | **Customer package** | customer drawing (any format) **+ optional tech spec** | Gemini vision → key dimensions + tech-spec rows |
| 2 | **PID** | `RES-DD-RC-03` Production Initiation Document (PDF) | Gemini vision → title block, electrode table, raw materials, tech spec |
| 3 | **Design document** | Excel: `S.No \| Parameter \| Unit \| Value` (`.xlsx`) | Deterministic `openpyxl` parse (no AI) |

The tech spec is optional — if the customer doesn't provide it, leave it empty.
The design document is parsed deterministically because its layout is fixed; the
two PDFs use vision because their layout varies from battery to battery.

## Validation pipeline (on ingest)

1. **PID ↔ Design cross-check** — compares the overlapping values (battery code,
   series/parallel, anode/cathode dia, the 6 electrode weights & 6 thicknesses).
   Every comparable pair must match; each mismatch is flagged. All matched ⇒ *proceed*.
   Also checks the rule **Stack Diameter = Cathode Diameter**.
2. **Customer-drawing gate** — if the customer drawing is missing, the run is **blocked**
   (flag + stop, no Table 1). If present, Table 1 is extracted.
3. **Table 1 — Extracted From Customer Drawing** — the 13 fixed components, each stamped
   with a **GEN Tol: IS 2102** (medium) tolerance unless the drawing states a specific one.
   Users can **add components** and **edit values** in the UI; tolerances recompute on save.

`Diameter = Dia` and `Stack Diameter = Cathode Diameter` are applied as rules.
Row 4 (*Diameter of the Pin*) is always left blank for manual entry, and the five
flange rows blank out unless a flange is actually detected.

## CAD generation

Each drawing is an SVG laid out on a 210 × 297 **millimetre** coordinate grid, so the
sheet is 1:1 A4. `cad/container.py` owns the shared sheet — border, revision table,
allowable-deviations table and the 9-column RES title block (logo, projection symbol,
DRAWN/DESIGN/PRODUCTION/QUALITY sign-off grid) — and every other component module
imports those helpers, so all drawings share one identity.

`cad/tables.py` holds the design lookups: Table 2 (container wall by OD band), Table 3
(groove), Table 4a/4b (lid OD and thickness), tie-wire width, FiberFrax thickness.

Dimensions resolve in priority order:

```
explicit request value → PID → design document → Table 1 → lookup table → default
```

If a value can't be resolved the endpoint returns **400 with a specific message**
naming what is missing and where to set it — it never silently guesses.

Components are numbered per battery in the order you select them, giving drawing
numbers `RES-<battery code>-<NN>`.

**Derived values are never frozen.** Fields like container ID, cut length and cut
angle are recomputed from their drivers on every render, so changing the wall
thickness or OD updates them instead of leaving a stale number behind.

**Revisions are explicit.** Generating a drawing leaves the revision table empty.
Only *CAD Revision* — which sends a change note — appends Rev 01, 02, … each stamped
with the date and description.

### The ~41 components

| Group | Components |
|---|---|
| Assembly | Container, Lid Blank, Tie Wire, Teflon Disc |
| Pellets & Discs | Cathode / Anode / Electrolyte pellets, Heat Pellets 1, 1B, 2, 3, SS Disc, SS Disc (0.05), Mica Disc, Samica Disc, Silicon Bonded Mica Disc, Mica Disc (Holes) |
| Housings | Housing A, Housing B, Silicon Bonded Mica Ring (A), Silicon Bonded Mica Ring (B), Mica Ring |
| Wicks & Strips | Pyro Wick 01/02, Samica Strip, Mica Strip, Glass Cloth Tape, Adhesive Tape, Samica Wrap, Mica Wrap |
| FiberFrax | Stack Wrap, Container Insulation |
| Terminals & Misc | Squib Terminal, Current Collector (Anode / Cathode), Brace Plate, Deliver Pin |
| Assemblies | Cell Assembly, Top Assembly, Bottom Assembly, Stack |

The twelve pellets/discs share one generic generator driven by the `PELLET_SPECS`
table in `main.py` — each entry declares where its diameter and thickness come from,
so adding a disc type is a dict entry rather than new code.

## UI modules

| Module | Purpose |
|---|---|
| **Data Entry** | Upload the three inputs, ingest, edit Table 1 and the design parameters |
| **Data View** | Browse stored batteries, review extractions and validation, view/download saved drawings, delete |
| **CAD Drawing** | Select components, generate, preview, save to Data View, export a combined PDF |
| **CAD Revision** | Per-component parameter forms with engineering notes; live re-render, revision notes |

## API

Everything except `/api/health` and `/api/login` requires
`Authorization: Bearer <token>`.

**Auth**
- `POST /api/login` — `{username, password}` → `{token, username}` (12 h expiry)
- `POST /api/change-password` — `{username, old_password, new_password}`

**Jobs & data**
- `GET  /api/health` — status, model, whether the API key is set *(open)*
- `POST /api/ingest` — multipart: `customer_files[]`, `tech_spec_file?`, `pid_file?`, `design_file?` → `IngestResult`
- `GET  /api/jobs` — list stored batteries
- `GET  /api/jobs/{id}` — one battery's full result
- `DELETE /api/jobs/{id}` — delete a battery
- `PUT  /api/jobs/{id}/table1` — save edited Table 1 rows (re-applies IS 2102)
- `POST /api/jobs/{id}/table1/add` — add a custom component
- `PUT  /api/jobs/{id}/design` — save edited design-document parameters

**CAD**
- `POST /api/cad/{component}` — generate one drawing → `{svg, drawing_no, component_no, geometry, params, revisions, warnings}`
- `POST /api/jobs/{id}/regenerate` — `{ctype}` — re-render from stored (revised) parameters
- `POST /api/jobs/{id}/drawings` — save generated drawings into Data View
- `POST /api/cad/pdf` — `{svgs[], filename}` → one multi-page A4 PDF

## Layout

```
backend/
  config.py            # .env loader, model, port, paths
  auth.py              # pbkdf2 users + HMAC bearer tokens
  schemas.py           # pydantic models for the 3 inputs + IngestResult
  main.py              # FastAPI app: ingest, validation, ~41 CAD endpoints, PDF
  parsers/
    vision.py          # shared: render PDF/img -> Gemini structured call
    customer_parser.py # input 1 (vision)
    pid_parser.py      # input 2 (vision)
    design_parser.py   # input 3 (deterministic Excel)
  validation/
    compare.py         # PID <-> design cross-check + domain rules
    tolerances.py      # IS 2102 medium general tolerances
    table1.py          # the 13 Table-1 rows
  store/local_json.py  # data/jobs/<id>/ store (swap for a DB later)
  cad/
    container.py       # RES sheet frame + SVG primitives (base for all others)
    tables.py          # design lookup tables (wall, groove, lid, tie wire, ...)
    *.py               # one module per component family
frontend/              # no-build React SPA (React + Babel vendored in vendor/)
run.py
```

`store/local_json.py` is deliberately swappable — replacing it with a DB-backed
module requires no changes to its callers.

## Notes

- Vision uses `gemini-2.5-pro` (set `EXTRACTION_MODEL=gemini-2.5-flash` for free tier).
- Customer PCD / pin-count on ambiguous drawings can vary between runs — the parser is
  instructed not to guess and records ambiguity in `customer.notes`.
- The frontend is intentionally build-free: React and Babel are **vendored** under
  `frontend/vendor/`, so the app needs no internet access at runtime. To upgrade them,
  replace those files and update the version comment in `index.html`.
- Next steps: BOM generation from the component set.
