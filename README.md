# CAD-BOM V1 — Input Layer

Clean V1 rebuild. This step implements the **three software inputs** and turns each
into structured data, combined into one battery "job".

## The three inputs

| # | Input | Files | How it's parsed |
|---|-------|-------|-----------------|
| 1 | **Customer package** | customer drawing (any format) **+ optional tech spec** | Gemini vision → key dimensions + tech-spec rows |
| 2 | **PID** | `RES-DD-RC-03` Production Initiation Document (PDF) | Gemini vision → title block, electrode table, raw materials, tech spec |
| 3 | **Design document** | Excel: `S.No \| Parameter \| Unit \| Value` (`.xlsx`) | Deterministic `openpyxl` parse (no AI) |

The tech spec is optional — if the customer doesn't provide it, leave it empty.

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

## Run

```bash
pip install -r requirements.txt
cp .env.example .env          # then put your GOOGLE_API_KEY in .env
python run.py                 # serves http://127.0.0.1:8020
```

Open the URL, upload one or more inputs, click **Ingest & Extract**. Results are
stored under `data/jobs/<id>/` (result.json + the uploaded source files) and listed
in the sidebar.

## API

- `GET  /api/health` — status, model, whether the API key is set
- `POST /api/ingest` — multipart: `customer_files[]`, `tech_spec_file?`, `pid_file?`, `design_file?` → `IngestResult` (includes `validation` + `table1`)
- `GET  /api/jobs` — list stored jobs
- `GET  /api/jobs/{id}` — one job's full result
- `PUT  /api/jobs/{id}/table1` — save edited Table 1 rows (re-applies IS 2102)
- `POST /api/jobs/{id}/table1/add` — add a custom component `{component, value, unit, kind}`
- `DELETE /api/jobs/{id}` — delete a job

## Layout

```
backend/
  config.py            # .env loader, model, port, paths
  schemas.py           # pydantic models for the 3 inputs + IngestResult
  parsers/
    vision.py          # shared: render PDF/img → Gemini structured call
    customer_parser.py # input 1 (vision)
    pid_parser.py      # input 2 (vision)
    design_parser.py   # input 3 (deterministic Excel)
  store/local_json.py  # data/jobs/<id>/ store (swap for a DB later)
  main.py              # FastAPI app + ingest endpoint + serves frontend/
frontend/              # no-build React SPA (upload + view)
run.py
```

## Notes / next

- Vision uses `gemini-2.5-pro` (set `EXTRACTION_MODEL=gemini-2.5-flash` for free tier).
- Customer PCD / pin-count on ambiguous drawings can vary between runs — the parser is
  instructed not to guess and records ambiguity in `customer.notes`.
- Next steps beyond the input layer: reconcile the three sources → CAD component
  generation → BOM.
```
