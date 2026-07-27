const { useState, useEffect } = React;

// --------------------------------------------------------------------------- //
// auth-aware fetch
// --------------------------------------------------------------------------- //
const AUTH = {
  token: localStorage.getItem("cadbom_token") || "",
  user: localStorage.getItem("cadbom_user") || "",
  onFail: null,
};

async function api(url, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  if (AUTH.token) headers["Authorization"] = "Bearer " + AUTH.token;
  if (opts.body && !(opts.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const r = await fetch(url, Object.assign({}, opts, { headers }));
  if (r.status === 401) {
    AUTH.token = ""; localStorage.removeItem("cadbom_token");
    if (AUTH.onFail) AUTH.onFail();
    throw new Error("Session expired — please log in again");
  }
  return r;
}
const detail = async (r) => { try { return (await r.json()).detail || r.statusText; } catch (e) { return r.statusText; } };

async function saveDrawings(jobId, kind, items) {
  const r = await api(`/api/jobs/${jobId}/drawings`, { method: "POST", body: JSON.stringify({ kind, drawings: items }) });
  if (!r.ok) throw new Error(await detail(r));
  return await r.json();
}
async function downloadSvgsPdf(svgs, fname) {
  const r = await api("/api/cad/pdf", { method: "POST", body: JSON.stringify({ svgs, filename: fname }) });
  if (!r.ok) throw new Error(await detail(r));
  const blob = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = fname; a.click();
}
// frontend component key -> backend ctype
const CTYPE_OF = { container: "container", lid: "lid_blank", tie_wire: "tie_wire", teflon: "teflon_disc" };

// --------------------------------------------------------------------------- //
// shared bits
// --------------------------------------------------------------------------- //
function Section({ title, right, children }) {
  return <div className="section"><div className="st">{title}{right}</div>{children}</div>;
}

function KV({ rows }) {
  return (
    <div className="kv">
      {rows.map(([k, v], i) => (
        <React.Fragment key={i}>
          <div className="k">{k}</div>
          <div>{v === null || v === undefined || v === "" ? "—" : String(v)}</div>
        </React.Fragment>
      ))}
    </div>
  );
}

function Table({ cols, rows }) {
  if (!rows || !rows.length) return <div className="k">—</div>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table>
        <thead><tr>{cols.map(c => <th key={c.k}>{c.label}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={i}>{cols.map(c => <td key={c.k}>{r[c.k] == null ? "" : String(r[c.k])}</td>)}</tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function statusBadge(v) {
  if (!v) return null;
  let text, cls;
  if (v.blocked) { text = "⛔ blocked — no customer drawing"; cls = "bad"; }
  else if (v.mismatched > 0) { text = `⚠ ${v.mismatched} PID/Design mismatch`; cls = "warnb"; }
  else if (v.proceed) { text = "✓ PID & Design match"; cls = "good"; }
  else { text = "PID/Design check incomplete"; cls = "warnb"; }
  return <span className={"statban " + cls}>{text}</span>;
}

function ValidationDetails({ v }) {
  if (!v) return null;
  return (
    <details className="section det">
      <summary>Validation — PID ↔ Design cross-check</summary>
      <div style={{ marginTop: 12 }}>
        {v.flags && v.flags.length > 0 && <ul className="flags">{v.flags.map((f, i) => <li key={i}>{f}</li>)}</ul>}
        {v.comparison && v.comparison.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <div className="k" style={{ marginBottom: 6 }}>
              PID ↔ Design ({v.matched} matched · {v.mismatched} mismatched · {v.missing} missing)
            </div>
            <div style={{ overflowX: "auto" }}>
              <table>
                <thead><tr><th>Parameter</th><th>PID</th><th>Design</th><th>Status</th></tr></thead>
                <tbody>{v.comparison.map((r, i) => (
                  <tr key={i}>
                    <td>{r.parameter}</td><td>{r.pid_value ?? ""}</td><td>{r.design_value ?? ""}</td>
                    <td className={"cs-" + r.status}>
                      {r.status === "match" ? "✓ match" : r.status === "mismatch" ? "✗ mismatch" : "– missing"}
                    </td>
                  </tr>))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </details>
  );
}

function flangePill(f) {
  return f === true ? <span className="pill">flange: present</span>
    : f === false ? <span className="pill warn">flange: none</span>
    : <span className="pill mut">flange: unknown</span>;
}

const FLANGE_SNOS = new Set([7, 9, 10, 11, 13]);

// --------------------------------------------------------------------------- //
// Table 1
// --------------------------------------------------------------------------- //
function Table1Editor({ rows, flange, onChange }) {
  const [comp, setComp] = useState("");
  const [val, setVal] = useState("");
  const noFlange = flange !== true;
  const edit = (i, f, nv) => onChange(rows.map((r, k) => k === i ? { ...r, [f]: nv } : r));
  const del = (i) => onChange(rows.filter((_, k) => k !== i));
  const add = () => {
    if (!comp.trim()) return;
    const next = rows.reduce((m, r) => Math.max(m, r.s_no || 0), 0) + 1;
    onChange([...rows, { s_no: next, component: comp.trim(), value: val || null, unit: "mm", tolerance: null, kind: "linear", source: "user", note: null }]);
    setComp(""); setVal("");
  };
  return (
    <div>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead><tr>
            <th style={{ width: 34 }}>S.No</th><th>Component Name</th>
            <th style={{ width: 150 }}>Value</th><th style={{ width: 55 }}>Unit</th>
            <th style={{ width: 175 }}>Tolerance</th><th style={{ width: 36 }}></th>
          </tr></thead>
          <tbody>{rows.map((r, i) => {
            const na = FLANGE_SNOS.has(r.s_no) && noFlange && r.source !== "user";
            return (
              <tr key={i} className={na ? "na" : ""}>
                <td>{r.s_no}</td>
                <td><input className="cell" value={r.component ?? ""} onChange={e => edit(i, "component", e.target.value)} />
                  {r.source === "user" && <span className="badge">added</span>}</td>
                <td><input className="cell" value={r.value ?? ""} placeholder={na ? "no flange" : "—"} disabled={na}
                  onChange={e => edit(i, "value", e.target.value)} /></td>
                <td>{r.unit || ""}</td>
                <td className="tol">{na ? "N/A — no flange" : (r.tolerance || "—")}</td>
                <td><button className="del-btn" title="Delete row" onClick={() => del(i)}>🗑</button></td>
              </tr>);
          })}</tbody>
        </table>
      </div>
      <div className="addrow">
        <input placeholder="New component name" value={comp} onChange={e => setComp(e.target.value)} />
        <input placeholder="Value (e.g. 12.5)" value={val} onChange={e => setVal(e.target.value)} />
        <button className="mini" onClick={add}>+ Add component</button>
      </div>
      <div className="k" style={{ marginTop: 8, fontSize: 12 }}>
        Tolerances (GEN Tol: IS 2102 medium) applied on <b>Save</b>. Flange rows apply only when a flange is present.
      </div>
    </div>
  );
}

function Table1Display({ rows, flange }) {
  const noFlange = flange !== true;
  if (!rows || !rows.length) return <div className="k">No Table 1 data.</div>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table>
        <thead><tr><th style={{ width: 34 }}>S.No</th><th>Component Name</th><th>Value</th><th style={{ width: 55 }}>Unit</th><th>Tolerance</th></tr></thead>
        <tbody>{rows.map((r, i) => {
          const na = FLANGE_SNOS.has(r.s_no) && noFlange && r.source !== "user";
          return (
            <tr key={i} className={na ? "na" : ""}>
              <td>{r.s_no}</td>
              <td>{r.component}{r.source === "user" && <span className="badge">added</span>}</td>
              <td>{na ? "—" : (r.value ?? "—")}</td><td>{na ? "" : (r.unit || "")}</td>
              <td className="tol">{na ? "N/A — no flange" : (r.tolerance || "—")}</td>
            </tr>);
        })}</tbody>
      </table>
    </div>
  );
}

function DesignEditor({ params, onChange }) {
  const [pname, setPname] = useState("");
  const [pval, setPval] = useState("");
  const rows = params || [];
  const edit = (i, f, nv) => onChange(rows.map((r, k) => k === i ? { ...r, [f]: nv } : r));
  const del = (i) => onChange(rows.filter((_, k) => k !== i));
  const add = () => {
    if (!pname.trim()) return;
    const next = rows.reduce((m, r) => Math.max(m, r.s_no || 0), 0) + 1;
    onChange([...rows, { s_no: next, parameter: pname.trim(), unit: "mm", value: pval || null }]);
    setPname(""); setPval("");
  };
  return (
    <div>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead><tr>
            <th style={{ width: 34 }}>S.No</th><th>Parameter</th>
            <th style={{ width: 150 }}>Value</th><th style={{ width: 70 }}>Unit</th><th style={{ width: 36 }}></th>
          </tr></thead>
          <tbody>{rows.map((r, i) => (
            <tr key={i}>
              <td>{r.s_no ?? i + 1}</td>
              <td><input className="cell" value={r.parameter ?? ""} onChange={e => edit(i, "parameter", e.target.value)} /></td>
              <td><input className="cell" value={r.value ?? ""} onChange={e => edit(i, "value", e.target.value)} /></td>
              <td><input className="cell" value={r.unit ?? ""} onChange={e => edit(i, "unit", e.target.value)} /></td>
              <td><button className="del-btn" title="Delete" onClick={() => del(i)}>🗑</button></td>
            </tr>))}</tbody>
        </table>
      </div>
      <div className="addrow">
        <input placeholder="New parameter (e.g. Container OD)" value={pname} onChange={e => setPname(e.target.value)} />
        <input placeholder="Value" value={pval} onChange={e => setPval(e.target.value)} />
        <button className="mini" onClick={add}>+ Add parameter</button>
      </div>
    </div>
  );
}

function Upload({ title, hint, badge, badgeOpt, multiple, accept, files, onPick }) {
  return (
    <div className="card">
      <h3>{title}{badge && <span className={"badge" + (badgeOpt ? " opt" : "")}>{badge}</span>}</h3>
      <div className="hint">{hint}</div>
      <input type="file" multiple={multiple} accept={accept} onChange={e => onPick(Array.from(e.target.files))} />
      {files && files.length > 0 && <div className="picked">{files.map(f => f.name).join(", ")}</div>}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Data Entry
// --------------------------------------------------------------------------- //
function DataEntry({ health, jobs, onSaved }) {
  const [customer, setCustomer] = useState([]);
  const [techspec, setTechspec] = useState([]);
  const [pid, setPid] = useState([]);
  const [design, setDesign] = useState([]);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [result, setResult] = useState(null);
  const [loadId, setLoadId] = useState("");
  const [loading, setLoading] = useState(false);

  const canIngest = customer.length || techspec.length || pid.length || design.length;
  const flange = result && result.customer && result.customer.table1 ? result.customer.table1.has_flange : null;
  const clearAll = () => { setCustomer([]); setTechspec([]); setPid([]); setDesign([]); setResult(null); setSaved(false); setLoadId(""); };

  const loadExisting = async (id) => {
    setLoadId(id);
    if (!id) { setResult(null); return; }
    setLoading(true); setSaved(false);
    try {
      const r = await api(`/api/jobs/${id}`);
      if (!r.ok) throw new Error(await detail(r));
      setResult(await r.json());
    } catch (e) { alert("Load failed: " + e.message); }
    setLoading(false);
  };

  const ingest = async () => {
    setBusy(true); setResult(null); setSaved(false); setLoadId("");
    const fd = new FormData();
    customer.forEach(f => fd.append("customer_files", f));
    if (techspec[0]) fd.append("tech_spec_file", techspec[0]);
    if (pid[0]) fd.append("pid_file", pid[0]);
    if (design[0]) fd.append("design_file", design[0]);
    try {
      const r = await api("/api/ingest", { method: "POST", body: fd });
      if (!r.ok) throw new Error(await detail(r));
      setResult(await r.json());
    } catch (e) { alert("Ingest failed: " + e.message); }
    setBusy(false);
  };

  const setRows = (rows) => { setResult({ ...result, table1: rows }); setSaved(false); };
  const setParams = (params) => {
    setResult({ ...result, design_doc: { ...(result.design_doc || {}), params } }); setSaved(false);
  };

  const save = async () => {
    setSaving(true);
    try {
      let r = await api(`/api/jobs/${result.job_id}/table1`, { method: "PUT", body: JSON.stringify({ rows: result.table1 }) });
      if (!r.ok) throw new Error(await detail(r));
      let updated = await r.json();
      if (result.design_doc && result.design_doc.params) {
        r = await api(`/api/jobs/${result.job_id}/design`, { method: "PUT", body: JSON.stringify({ params: result.design_doc.params }) });
        if (!r.ok) throw new Error(await detail(r));
        updated = await r.json();
      }
      setResult(updated); setSaved(true); onSaved();
    } catch (e) { alert("Save failed: " + e.message); }
    setSaving(false);
  };

  const blocked = result && result.validation && result.validation.blocked;

  return (
    <div>
      <h2 className="modtitle">Data Entry</h2>
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="row" style={{ margin: 0, alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <label className="fl" style={{ margin: 0 }}>Load existing battery</label>
          <select value={loadId} onChange={e => loadExisting(e.target.value)} style={{ minWidth: 240 }}>
            <option value="">— new (upload files below) —</option>
            {(jobs || []).map(j => <option key={j.job_id} value={j.job_id}>{j.battery_name}</option>)}
          </select>
          {loading && <span className="spin">loading…</span>}
          <span className="k" style={{ fontSize: 12 }}>Load a saved battery to review/edit its values, then <b>Save</b>. CAD Drawing regenerates with the updated values.</span>
        </div>
      </div>
      <div className="uploads">
        <Upload title="Customer drawing" badge="input 1" hint="Customer's outline/envelope drawing (any format). Required to build Table 1."
          multiple accept=".pdf,.png,.jpg,.jpeg" files={customer} onPick={setCustomer} />
        <Upload title="Tech spec" badge="optional" badgeOpt hint="Customer tech-spec document. Sometimes not provided — leave empty if so."
          accept=".pdf,.png,.jpg,.jpeg" files={techspec} onPick={setTechspec} />
        <Upload title="PID" badge="input 2" hint="RES-DD-RC-03 Production Initiation Document (PDF)."
          accept=".pdf" files={pid} onPick={setPid} />
      </div>
      <div className="uploads" style={{ gridTemplateColumns: "1fr 2fr" }}>
        <Upload title="Design document" badge="input 3" hint="Design Excel — S.No | Parameter | Unit | Value (.xlsx)."
          accept=".xlsx,.xls" files={design} onPick={setDesign} />
        <div className="card" style={{ display: "flex", alignItems: "center" }}>
          <div className="row" style={{ margin: 0 }}>
            <button onClick={ingest} disabled={!canIngest || busy}>{busy ? "Extracting…" : "Ingest & Extract"}</button>
            <button className="ghost" onClick={clearAll}>Clear</button>
            {busy && <span className="spin">calling {health && health.model}… (~30–90s)</span>}
          </div>
        </div>
      </div>

      {!result && <div className="empty">Load an existing battery above, or upload inputs and click <b>Ingest &amp; Extract</b>.</div>}

      {result && (
        <div className="result">
          <h2>{result.battery_name} {statusBadge(result.validation)}
            <span style={{ display: "inline-flex", gap: 8, marginLeft: 12, alignItems: "center", verticalAlign: "middle" }}>
              {saved && <span className="pill">saved ✓</span>}
              <button className="mini" onClick={save} disabled={saving}>{saving ? "Saving…" : (saved ? "Save changes" : "Save all")}</button>
            </span>
          </h2>
          {result.warnings && result.warnings.length > 0 && <div className="warns">⚠ {result.warnings.join(" · ")}</div>}
          {blocked ? (
            <div className="warns" style={{ fontSize: 14 }}>
              ⛔ Customer drawing not provided — extraction stopped. Upload the customer drawing to build Table 1.
            </div>
          ) : (
            <div className="section">
              <div className="st">Table 1 — Extracted From Customer Drawing
                <span style={{ display: "flex", gap: 8, marginLeft: "auto", alignItems: "center" }}>
                  {flangePill(flange)}
                  <button className="mini" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
                </span>
              </div>
              <Table1Editor rows={result.table1} flange={flange} onChange={setRows} />
            </div>
          )}
          {result.design_doc && (
            <div className="section">
              <div className="st">Design Parameters — used by CAD drawings
                <span style={{ display: "flex", gap: 8, marginLeft: "auto", alignItems: "center" }}>
                  {result.design_doc.battery_code && <span className="pill">{result.design_doc.battery_code}</span>}
                  <button className="mini" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
                </span>
              </div>
              <DesignEditor params={result.design_doc.params} onChange={setParams} />
            </div>
          )}
          {saved && <div className="k" style={{ marginTop: 6, color: "var(--ok)" }}>
            Saved. CAD Drawing will now generate with these updated values. Open <b>Data View</b> to review.</div>}
          <ValidationDetails v={result.validation} />
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Data View
// --------------------------------------------------------------------------- //
function batteryCodeOf(job) {
  return (job && ((job.pid && job.pid.battery_code) || (job.design_doc && job.design_doc.battery_code))) || "";
}

function SavedDrawings({ job, kind, title, onPromoted }) {
  const [busy, setBusy] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const items = (job.saved_drawings || []).filter(d => d.kind === kind);
  if (!items.length) return null;
  const bcode = batteryCodeOf(job);
  const dl = async () => {
    setBusy(true);
    try { await downloadSvgsPdf(items.map(i => i.svg), `RES-${bcode || "battery"}_${kind}.pdf`); }
    catch (e) { alert("PDF export failed: " + e.message); }
    setBusy(false);
  };
  const promote = async () => {
    setPromoting(true);
    try {
      await saveDrawings(job.job_id, "cad", items.map(d => ({
        ctype: d.ctype, name: d.name, no: d.no, drawing_no: d.drawing_no, rev: d.rev, svg: d.svg })));
      if (onPromoted) await onPromoted();
      alert("CAD Drawings updated with these revised versions.");
    } catch (e) { alert("Update failed: " + e.message); }
    setPromoting(false);
  };
  return (
    <div className="section">
      <div className="st">{title}
        <span style={{ display: "flex", gap: 8, marginLeft: "auto", alignItems: "center" }}>
          <span className="pill">RES-{bcode || "—"}</span>
          {kind === "revision" && onPromoted &&
            <button className="mini" onClick={promote} disabled={promoting}>{promoting ? "Updating…" : "⬆ Update to CAD Drawings"}</button>}
          <button className="mini" onClick={dl} disabled={busy}>{busy ? "PDF…" : `⬇ Download PDF (${items.length})`}</button>
        </span>
      </div>
      {items.map((d, i) => (
        <details key={i} className="det" style={{ marginBottom: 8 }}>
          <summary>{String(d.no).padStart(2, "0")} · {d.name} — {d.drawing_no} · Rev {d.rev}
            {d.saved_at && <span className="jm" style={{ marginLeft: 8 }}>saved {d.saved_at}</span>}
            <button className="mini" style={{ marginLeft: 8 }} onClick={(e) => { e.preventDefault();
              downloadSvgsPdf([d.svg], (d.drawing_no || d.name || "drawing") + ".pdf").catch(er => alert("PDF export failed: " + er.message)); }}>⬇ PDF</button>
          </summary>
          <div className="svgwrap" style={{ marginTop: 8 }} dangerouslySetInnerHTML={{ __html: d.svg }} />
        </details>
      ))}
    </div>
  );
}

function DataView({ jobs, selectedId, onSelect, refresh }) {
  const [detailJob, setDetailJob] = useState(null);
  const reloadDetail = () => selectedId
    ? api("/api/jobs/" + selectedId).then(r => r.json()).then(setDetailJob).catch(() => {})
    : Promise.resolve();
  useEffect(() => {
    if (selectedId) api("/api/jobs/" + selectedId).then(r => r.json()).then(setDetailJob).catch(() => {});
    else setDetailJob(null);
  }, [selectedId]);

  const del = (id, e) => {
    e.stopPropagation();
    api("/api/jobs/" + id, { method: "DELETE" }).then(() => { refresh(); if (id === selectedId) onSelect(null); }).catch(() => {});
  };
  const flange = detailJob && detailJob.customer && detailJob.customer.table1 ? detailJob.customer.table1.has_flange : null;

  return (
    <div>
      <h2 className="modtitle">Data View</h2>
      <div className="viewgrid">
        <div className="vlist">
          <div className="sub" style={{ textTransform: "uppercase", letterSpacing: ".5px" }}>Saved batteries ({jobs.length})</div>
          <ul className="joblist">
            {jobs.map(j => (
              <li key={j.job_id} className={selectedId === j.job_id ? "active" : ""} onClick={() => onSelect(j.job_id)}>
                <span className="del" onClick={e => del(j.job_id, e)}>🗑</span>
                <div className="jn">{j.battery_name || "Untitled"}</div>
                <div className="jm">{(j.sources || []).join(" · ")}</div>
              </li>))}
            {!jobs.length && <li style={{ background: "transparent", color: "var(--muted)" }}>No saved batteries yet — add one in Data Entry.</li>}
          </ul>
        </div>
        <div className="vdetail">
          {!detailJob && <div className="empty">Select a saved battery.</div>}
          {detailJob && (
            <div className="result">
              <h2>{detailJob.battery_name} <span className="badge">{detailJob.job_id}</span> {statusBadge(detailJob.validation)}</h2>
              <details className="section det">
                <summary className="st">Table 1 — Values extracted from Data Entry
                  <span style={{ marginLeft: "auto" }}>{flangePill(flange)}</span></summary>
                <div style={{ marginTop: 10 }}>
                  <Table1Display rows={detailJob.table1} flange={flange} />
                </div>
              </details>
              {detailJob.cad_components && detailJob.cad_components.length > 0 && (
                <details className="section det">
                  <summary className="st">Generated CAD components</summary>
                  <div style={{ marginTop: 10 }}>
                    <Table cols={[{ k: "no", label: "#" }, { k: "name", label: "Component" }, { k: "qty", label: "Qty" }, { k: "drawing_no", label: "Drawing No." }]}
                      rows={detailJob.cad_components} />
                  </div>
                </details>
              )}
              <SavedDrawings job={detailJob} kind="cad" title="CAD Drawings (from CAD Drawing)" />
              <SavedDrawings job={detailJob} kind="revision" title="CAD Revisions (from CAD Revision)" onPromoted={reloadDetail} />
              <ValidationDetails v={detailJob.validation} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// CAD Drawing — multi-select
// --------------------------------------------------------------------------- //
const PELLETS = [
  ["cathode_pellet", "Cathode Pellet"], ["anode_pellet", "Anode Pellet"],
  ["electrolyte_pellet", "Electrolyte Pellet"], ["heat_pellet_1", "Heat Pellet 1"],
  ["heat_pellet_2", "Heat Pellet 2"], ["heat_pellet_3", "Heat Pellet 3"],
  ["heat_pellet_1b", "Heat Pellet 1B"], ["ss_disc", "SS Disc"],
  ["ss_disc_005", "SS Disc (0.05)"], ["mica_disc", "Mica Disc"],
  ["samica_disc", "Samica Disc"], ["silicon_mica_disc", "Silicon Bonded Mica Disc"],
];
const PELLET_KEYS = new Set(PELLETS.map(([k]) => k));
const COMPONENTS = [
  { key: "container", label: "Container", url: "/api/cad/container", group: "Assembly" },
  { key: "lid", label: "Lid Blank", url: "/api/cad/lid", group: "Assembly" },
  { key: "tie_wire", label: "Tie Wire", url: "/api/cad/tie_wire", group: "Assembly" },
  { key: "teflon", label: "Teflon Disc", url: "/api/cad/teflon_disc", group: "Assembly" },
  ...PELLETS.map(([k, l]) => ({ key: k, label: l, url: "/api/cad/pellet", ctype: k, group: "Pellets & Discs" })),
  { key: "mica_disc_holes", label: "Mica Disc (Holes)", url: "/api/cad/mica_holes", group: "Pellets & Discs" },
  { key: "housing_a", label: "Housing - A", url: "/api/cad/housing_a", group: "Housings" },
  { key: "housing_b", label: "Housing - B", url: "/api/cad/housing_b", group: "Housings" },
  { key: "silicon_ring_a", label: "Silicon Bonded Mica Ring (Housing A)", url: "/api/cad/silicon_ring_a", group: "Housings" },
  { key: "silicon_ring_b", label: "Silicon Bonded Mica Ring (Housing B)", url: "/api/cad/silicon_ring_b", group: "Housings" },
  { key: "mica_ring", label: "Mica Ring", url: "/api/cad/mica_ring", group: "Housings" },
  { key: "pyro_wick", label: "Pyro Wick - 01", url: "/api/cad/pyro_wick", group: "Wicks & Strips" },
  { key: "pyro_wick_02", label: "Pyro Wick - 02", url: "/api/cad/pyro_wick_02", group: "Wicks & Strips" },
  { key: "samica_strip", label: "Samica Strip", url: "/api/cad/samica_strip", group: "Wicks & Strips" },
  { key: "mica_strip", label: "Mica Strip", url: "/api/cad/mica_strip", group: "Wicks & Strips" },
  { key: "glass_cloth_tape", label: "Glass Cloth Tape", url: "/api/cad/glass_cloth_tape", group: "Wicks & Strips" },
  { key: "adhesive_tape", label: "Adhesive Tape", url: "/api/cad/adhesive_tape", group: "Wicks & Strips" },
  { key: "samica_wrap", label: "Samica Wrap", url: "/api/cad/samica_wrap", group: "Wicks & Strips" },
  { key: "mica_wrap", label: "Mica Wrap", url: "/api/cad/mica_wrap", group: "Wicks & Strips" },
  { key: "fiberfrax_stack_wrap", label: "FiberFrax Stack Wrap", url: "/api/cad/fiberfrax_stack_wrap", group: "FiberFrax" },
  { key: "fiberfrax_container_insulation", label: "FiberFrax Container Insulation", url: "/api/cad/fiberfrax_container_insulation", group: "FiberFrax" },
  { key: "squib_terminal", label: "Squib Terminal", url: "/api/cad/squib_terminal", group: "Terminals & Misc" },
  { key: "current_collector_anode", label: "Current Collector (Anode)", url: "/api/cad/current_collector_anode", group: "Terminals & Misc" },
  { key: "current_collector_cathode", label: "Current Collector (Cathode)", url: "/api/cad/current_collector_cathode", group: "Terminals & Misc" },
  { key: "brace_plate", label: "Brace Plate", url: "/api/cad/brace_plate", group: "Terminals & Misc" },
  { key: "deliver_pin", label: "Deliver Pin", url: "/api/cad/deliver_pin", group: "Terminals & Misc" },
  { key: "cell_assembly", label: "Cell Assembly", url: "/api/cad/cell_assembly", group: "Assemblies" },
  { key: "top_assembly", label: "Top Assembly", url: "/api/cad/top_assembly", group: "Assemblies" },
  { key: "bottom_assembly", label: "Bottom Assembly", url: "/api/cad/bottom_assembly", group: "Assemblies" },
  { key: "stack", label: "Stack", url: "/api/cad/stack", group: "Assemblies" },
];

// Cell assembly: fixed order, bottom (S.No 1) -> top (S.No 6)
const CELL_ASSEMBLY_ROWS = [
  { sno: 1, name: "SS Disc – 0.05", qty: "1", placing_order: "1" },
  { sno: 2, name: "Anode Pellet", qty: "1", placing_order: "2" },
  { sno: 3, name: "Electrolyte Pellet", qty: "1", placing_order: "3" },
  { sno: 4, name: "Cathode Pellet", qty: "1", placing_order: "4" },
  { sno: 5, name: "SS Disc – 0.05", qty: "1", placing_order: "5" },
  { sno: 6, name: "Heat Pellet – 1", qty: "1", placing_order: "6" },
];

const TOP_ASSEMBLY_ROWS = [
  { sno: 1, name: "Mica Disc", qty: "", placing_order: "" },
  { sno: 2, name: "Heat Pellet - 2", qty: "", placing_order: "" },
  { sno: 3, name: "FiberFrax Disc - B", qty: "", placing_order: "" },
  { sno: 4, name: "SS Disc", qty: "", placing_order: "" },
];
const BOTTOM_ASSEMBLY_ROWS = [
  { sno: 1, name: "Mica Disc", qty: "", placing_order: "" },
  { sno: 2, name: "FiberFrax Disc - B", qty: "", placing_order: "" },
  { sno: 3, name: "Heat Pellet - 3", qty: "", placing_order: "" },
  { sno: 4, name: "SS Disc", qty: "", placing_order: "" },
  { sno: 5, name: "FiberFrax Disc - E", qty: "", placing_order: "" },
  { sno: 6, name: "Brace Plate", qty: "", placing_order: "" },
];

function AssemblyTable({ title, rows, onChange, onSave, saved }) {
  const edit = (i, f, v) => onChange(rows.map((r, k) => k === i ? { ...r, [f]: v } : r));
  const del = (i) => onChange(rows.filter((_, k) => k !== i).map((r, k) => ({ ...r, sno: k + 1 })));
  const add = () => onChange([...rows, { sno: rows.length + 1, name: "", qty: "", placing_order: "" }]);
  return (
    <details className="det optgrp" open>
      <summary>{title} — components
        <span style={{ display: "inline-flex", gap: 8, marginLeft: 10, alignItems: "center" }}>
          {saved && <span className="pill">saved ✓</span>}
          <button className="mini" onClick={(e) => { e.preventDefault(); onSave && onSave(); }}>💾 Save</button>
        </span>
      </summary>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead><tr>
            <th style={{ width: 30 }}>S.No</th><th style={{ width: "42%" }}>Component</th>
            <th style={{ width: 44 }}>Qty</th><th style={{ width: 74 }}>Order</th><th style={{ width: 28 }}></th>
          </tr></thead>
          <tbody>{rows.map((r, i) => (
            <tr key={i}>
              <td>{r.sno}</td>
              <td><input className="cell" style={{ fontSize: 12 }} value={r.name} onChange={e => edit(i, "name", e.target.value)} /></td>
              <td><input className="cell" value={r.qty} onChange={e => edit(i, "qty", e.target.value)} placeholder="—" /></td>
              <td><input className="cell" value={r.placing_order} onChange={e => edit(i, "placing_order", e.target.value)} placeholder="2,4" /></td>
              <td><button className="del-btn" title="Delete" onClick={() => del(i)}>🗑</button></td>
            </tr>))}</tbody>
        </table>
      </div>
      <div className="addrow"><button className="mini" onClick={add}>+ Add component</button></div>
      <div className="k" style={{ fontSize: 11, marginTop: 6 }}>
        Placing Order = the stack position(s) of that component, top→bottom. Repeated pieces take several
        positions, e.g. <b>2,4</b> = 2nd and 4th. Qty = total number of that piece.
      </div>
    </details>
  );
}

function CadDrawing({ jobs }) {
  const [jobId, setJobId] = useState("");
  const [sel, setSel] = useState(["container"]);
  const [ctype, setCtype] = useState("deep_drawn");
  const [bottomR, setBottomR] = useState("2");
  const [flangeKind, setFlangeKind] = useState("integral");
  const [flangePos, setFlangePos] = useState("top");
  const [clearance, setClearance] = useState("1.0");
  const [pinDia, setPinDia] = useState("1.6");
  const [numWires, setNumWires] = useState("");
  const [holeDia, setHoleDia] = useState("1.8");
  // Deliver Pin inputs — only pin type + bottom side of lid (the rest is data-driven)
  const [dpType, setDpType] = useState("round");
  const [dpBottom, setDpBottom] = useState("");
  // Assembly input tables (persisted per battery)
  const [topRows, setTopRows] = useState(TOP_ASSEMBLY_ROWS.map(r => ({ ...r })));
  const [bottomRows, setBottomRows] = useState(BOTTOM_ASSEMBLY_ROWS.map(r => ({ ...r })));
  const [cellRows, setCellRows] = useState(CELL_ASSEMBLY_ROWS.map(r => ({ ...r })));
  const [asmSaved, setAsmSaved] = useState({});

  // load stored assembly rows whenever a battery is selected
  useEffect(() => {
    if (!jobId) return;
    const norm = (rows, def) => (rows && rows.length ? rows.map(r =>
      ({ sno: r.sno, name: r.name, qty: r.qty == null ? "" : String(r.qty), placing_order: r.placing_order || "" })) : def);
    api(`/api/jobs/${jobId}`).then(r => r.ok ? r.json() : null).then(job => {
      const cc = (job && job.cad_components) || [];
      const find = (ct) => cc.find(c => c.ctype === ct);
      const ta = find("top_assembly"), ba = find("bottom_assembly"), ce = find("cell_assembly");
      setTopRows(norm(ta && ta.params && ta.params.rows, TOP_ASSEMBLY_ROWS.map(r => ({ ...r }))));
      setBottomRows(norm(ba && ba.params && ba.params.rows, BOTTOM_ASSEMBLY_ROWS.map(r => ({ ...r }))));
      setCellRows(norm(ce && ce.params && ce.params.rows, CELL_ASSEMBLY_ROWS.map(r => ({ ...r }))));
      setAsmSaved({});
    }).catch(() => {});
  }, [jobId]);

  const setTopRowsS = (rows) => { setTopRows(rows); setAsmSaved(s => ({ ...s, top_assembly: false })); };
  const setBottomRowsS = (rows) => { setBottomRows(rows); setAsmSaved(s => ({ ...s, bottom_assembly: false })); };
  const setCellRowsS = (rows) => { setCellRows(rows); setAsmSaved(s => ({ ...s, cell_assembly: false })); };
  const [section, setSection] = useState(true);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState([]);
  const [skipped, setSkipped] = useState([]);

  const has = (k) => sel.indexOf(k) >= 0;
  const toggle = (k) => setSel(has(k) ? sel.filter(x => x !== k) : [...sel, k]);
  const chosen = COMPONENTS.filter(c => has(c.key));   // fixed order = drawing order

  const paramsFor = (k) => {
    if (PELLET_KEYS.has(k)) return { ctype: k };   // pellets: all values from data
    if (k === "container") {
      const b = { container_type: ctype, include_section: section };
      const br = parseFloat(bottomR); if (!isNaN(br) && br > 0) b.bottom_radius = br;
      if (ctype === "flanged") { b.flange_kind = flangeKind; b.flange_position = flangePos; }
      return b;
    }
    if (k === "lid") {
      const b = { container_type: ctype, include_section: section, clearance: parseFloat(clearance) || 1.0 };
      const pd = parseFloat(pinDia); if (!isNaN(pd) && pd > 0) b.pin_diameter = pd;
      return b;
    }
    if (k === "tie_wire") return { container_type: ctype };
    // teflon: no UI inputs — tie-wire count from PID, hole dia from Table 1
    if (k === "teflon") return { container_type: ctype };
    if (k === "deliver_pin") {
      const b = { pin_type: dpType };
      const bs = parseFloat(dpBottom); if (!isNaN(bs)) b.bottom_side = bs;
      return b;
    }
    if (k === "top_assembly" || k === "bottom_assembly" || k === "cell_assembly") {
      const src = k === "top_assembly" ? topRows : (k === "bottom_assembly" ? bottomRows : cellRows);
      return { rows: src.map(r => ({ sno: r.sno, name: r.name,
        qty: r.qty === "" ? null : parseInt(r.qty), placing_order: r.placing_order || "" })) };
    }
    // stack: all values come from the PID / input data (no manual inputs)
    return {};
  };

  const saveAssembly = async (k) => {
    if (!jobId) { alert("Select a saved battery first."); return; }
    const url = "/api/cad/" + k;
    try {
      const body = Object.assign({ job_id: jobId }, paramsFor(k));
      const r = await api(url, { method: "POST", body: JSON.stringify(body) });
      if (!r.ok) throw new Error(await detail(r));
      await r.json();
      setAsmSaved(s => ({ ...s, [k]: true }));
    } catch (e) { alert("Save failed: " + e.message); }
  };

  const generate = async () => {
    if (!jobId) { alert("Select a saved battery first."); return; }
    if (!chosen.length) { alert("Select at least one component."); return; }
    setBusy(true); setResults([]); setSkipped([]);
    const out = [], skip = [];
    let n = 0;                                    // running drawing number (only counts successes)
    for (const c of chosen) {
      n += 1;
      try {
        const body = Object.assign({ job_id: jobId, seq: n }, paramsFor(c.key));
        const r = await api(c.url, { method: "POST", body: JSON.stringify(body) });
        if (!r.ok) {                              // no data (or other issue) — skip, keep going
          skip.push({ label: c.label, msg: await detail(r) }); setSkipped([...skip]); n -= 1; continue;
        }
        out.push(Object.assign({ label: c.label, key: c.key }, await r.json()));
        setResults([...out]); setSaved(false);
      } catch (e) {
        skip.push({ label: c.label, msg: e.message }); setSkipped([...skip]); n -= 1;
      }
    }
    setBusy(false);
  };

  const [dlOne, setDlOne] = useState("");
  const download = async (res) => {
    setDlOne(res.key || res.drawing_no || res.label);
    try { await downloadSvgsPdf([res.svg], (res.drawing_no || res.label || "drawing") + ".pdf"); }
    catch (e) { alert("PDF export failed: " + e.message); }
    setDlOne("");
  };

  const [pdfBusy, setPdfBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [savingD, setSavingD] = useState(false);
  const baseName = () => (results[0] && results[0].drawing_no || "battery").replace(/-\d+$/, "");
  const downloadPdf = async () => {
    if (!results.length) return;
    setPdfBusy(true);
    try { await downloadSvgsPdf(results.map(x => x.svg), baseName() + "_drawings.pdf"); }
    catch (e) { alert("PDF export failed: " + e.message); }
    setPdfBusy(false);
  };
  const [updBusy, setUpdBusy] = useState(false);
  const [updNonce, setUpdNonce] = useState(0);
  const updateFromRevision = async () => {
    if (!results.length || !jobId) return;
    setUpdBusy(true);
    try {
      const out = [];
      for (const res of results) {
        const ct = CTYPE_OF[res.key] || res.key;
        const r = await api(`/api/jobs/${jobId}/regenerate`, { method: "POST", body: JSON.stringify({ ctype: ct }) });
        if (!r.ok) throw new Error(res.label + ": " + (await detail(r)));
        out.push(Object.assign({ label: res.label, key: res.key }, await r.json()));
      }
      setResults(out); setSaved(false); setUpdNonce(n => n + 1);   // force fresh render
    } catch (e) { alert("Update failed: " + e.message); }
    setUpdBusy(false);
  };
  const saveToData = async () => {
    if (!results.length || !jobId) return;
    setSavingD(true);
    try {
      const items = results.map(r => ({
        ctype: CTYPE_OF[r.key] || r.key, name: r.label, no: parseInt(r.component_no) || 0,
        drawing_no: r.drawing_no, rev: (r.revisions && r.revisions.length) ? r.revisions[r.revisions.length - 1].rev : "01",
        svg: r.svg,
      }));
      await saveDrawings(jobId, "cad", items); setSaved(true);
    } catch (e) { alert("Save failed: " + e.message); }
    setSavingD(false);
  };

  const geomPill = (g) => {
    if (!g) return null;
    if (g.outer_dia !== undefined && g.inner_dia !== undefined) return `OD Ø${g.outer_dia} · ID Ø${g.inner_dia} · t ${g.thickness}${g.num_cuts !== undefined ? " · " + g.num_cuts + " cuts × " + g.cut_width : ""}`;
    if (g.num_holes !== undefined && g.pcd !== undefined && g.dia !== undefined && g.lid_od === undefined && g.disc_dia === undefined)
      return `Ø${g.dia} · t ${g.thickness} · ${g.num_holes} holes B @ ${g.theta}° on PCD ${g.pcd}`;
    if (g.dia !== undefined && g.od === undefined && g.disc_dia === undefined) return `Ø${g.dia} ${g.dia_tol || ""} · t ${g.thickness} ${g.thk_tol || ""}`;
    if (g.disc_dia !== undefined) return `Ø${g.disc_dia} · t ${g.thickness} · ${g.num_cuts} cuts @ ${g.cut_angle}° · slot ${g.cut_length}×${g.cut_width}`;
    if (g.length !== undefined) return `${g.length} × ${g.width} × t ${g.thickness}`;
    if (g.lid_od !== undefined) return `Ø${g.lid_od} · t ${g.thickness} · PCD ${g.pcd} · ${g.num_holes} holes @ ${g.theta}°`;
    return `OD Ø${g.od} · ID Ø${g.id} · wall ${g.wall} · H ${g.height}`;
  };

  return (
    <div>
      <h2 className="modtitle">CAD Drawing</h2>
      <div className="viewgrid">
        <div className="vlist">
          <label className="fl">Battery</label>
          <select value={jobId} onChange={e => setJobId(e.target.value)}>
            <option value="">— select saved battery —</option>
            {jobs.map(j => <option key={j.job_id} value={j.job_id}>{j.battery_name}</option>)}
          </select>

          <label className="fl">Components (select one or more)</label>
          <div className="selbar">
            <button type="button" className="mini" onClick={() => setSel(COMPONENTS.map(c => c.key))}>Select all</button>
            <button type="button" className="mini" onClick={() => setSel([])}>Clear</button>
            <span className="k" style={{ fontSize: 12 }}>{sel.length} / {COMPONENTS.length} selected</span>
          </div>
          <div className="complist">
            {COMPONENTS.map((c, idx) => {
              const i = chosen.findIndex(x => x.key === c.key);
              const showGroup = idx === 0 || COMPONENTS[idx - 1].group !== c.group;
              return (
                <React.Fragment key={c.key}>
                  {showGroup && <div className="grpttl">{c.group}</div>}
                  <label className={"cchk" + (has(c.key) ? " on" : "")}>
                    <input type="checkbox" checked={has(c.key)} onChange={() => toggle(c.key)} />
                    <span>{c.label}</span>
                    {i >= 0 && <span className="seqno">{String(i + 1).padStart(2, "0")}</span>}
                  </label>
                </React.Fragment>);
            })}
          </div>

          {has("container") && (
            <details className="det optgrp" open>
              <summary>Container — inputs</summary>
              <label className="fl">Container type</label>
              <select value={ctype} onChange={e => setCtype(e.target.value)}>
                <option value="deep_drawn">Deep drawn</option>
                <option value="flanged">Flanged</option>
              </select>
              {ctype === "flanged" && <>
                <label className="fl">Flange type</label>
                <select value={flangeKind} onChange={e => setFlangeKind(e.target.value)}>
                  <option value="integral">Integral</option><option value="welded">Welded</option>
                </select>
                <label className="fl">Flange position</label>
                <select value={flangePos} onChange={e => setFlangePos(e.target.value)}>
                  <option value="top">Top</option><option value="middle">Middle</option><option value="bottom">Bottom</option>
                </select>
              </>}
              <label className="fl">Bottom radius (mm) — optional</label>
              <input value={bottomR} onChange={e => setBottomR(e.target.value)} placeholder="blank = sharp corner" />
            </details>
          )}

          {has("lid") && (
            <details className="det optgrp" open>
              <summary>Lid Blank — inputs</summary>
              <label className="fl">Hole PCD clearance (mm)</label>
              <input value={clearance} onChange={e => setClearance(e.target.value)} placeholder="e.g. 1.0" />
              <label className="fl">Pin diameter (mm)</label>
              <input value={pinDia} onChange={e => setPinDia(e.target.value)} placeholder="e.g. 1.6 (hole = pin × 2.5)" />
            </details>
          )}

          {has("teflon") && (
            <div className="k" style={{ fontSize: 12, marginTop: 12 }}>
              <b>Teflon Disc</b> — no inputs needed: tie-wire count comes from the PID and the pin-hole dia from Table 1.
            </div>
          )}

          {has("deliver_pin") && (
            <details className="det optgrp" open>
              <summary>Deliver Pin — inputs</summary>
              <label className="fl">Pin type</label>
              <select value={dpType} onChange={e => setDpType(e.target.value)}>
                <option value="round">Round</option>
                <option value="top_flat_bottom_round">Top Flat, Bottom Round</option>
                <option value="bottom_flat_top_round">Bottom Flat, Top Round</option>
              </select>
              <label className="fl">Bottom Side of Lid (mm)</label>
              <input value={dpBottom} onChange={e => setDpBottom(e.target.value)} placeholder="bottom part height — given by user" />
              <div className="k" style={{ fontSize: 11, marginTop: 6 }}>
                Pin dia &amp; upper part come from Table 1; lid thickness is calculated.
                Deliver Pin Height = Upper part + Lid thickness + Bottom Side of Lid.
              </div>
            </details>
          )}

          {has("cell_assembly") && <AssemblyTable title="Cell Assembly" rows={cellRows} onChange={setCellRowsS}
            onSave={() => saveAssembly("cell_assembly")} saved={asmSaved.cell_assembly} />}
          {has("top_assembly") && <AssemblyTable title="Top Assembly" rows={topRows} onChange={setTopRowsS}
            onSave={() => saveAssembly("top_assembly")} saved={asmSaved.top_assembly} />}
          {has("bottom_assembly") && <AssemblyTable title="Bottom Assembly" rows={bottomRows} onChange={setBottomRowsS}
            onSave={() => saveAssembly("bottom_assembly")} saved={asmSaved.bottom_assembly} />}

          {has("stack") && (
            <div className="k" style={{ fontSize: 12, marginTop: 12 }}>
              <b>Stack</b> — no inputs needed: the number of cells (N) and stacks-in-parallel come from the PID / input data.
              (Override in <b>CAD Revision</b> if required.)
            </div>
          )}

          <button style={{ marginTop: 14, width: "100%" }} onClick={generate} disabled={busy}>
            {busy ? "Generating…" : `Generate ${chosen.length || ""} drawing${chosen.length === 1 ? "" : "s"}`}
          </button>
        </div>

        <div className="vdetail">
          {!results.length && !skipped.length && <div className="empty">Pick a battery and components, then <b>Generate</b>.</div>}
          {skipped.length > 0 && (
            <div className="warns" style={{ marginBottom: 14 }}>
              ⚠ Skipped (no data in the inputs): {skipped.map(s => s.label).join(", ")}.
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {skipped.map((s, i) => <li key={i} style={{ fontSize: 12 }}>{s.label} — {s.msg}</li>)}
              </ul>
            </div>
          )}
          {results.length > 0 && (
            <div className="row" style={{ marginBottom: 14, alignItems: "center", flexWrap: "wrap" }}>
              <button onClick={downloadPdf} disabled={pdfBusy}>
                {pdfBusy ? "Building PDF…" : `⬇ Download combined PDF (${results.length})`}
              </button>
              <button className="ghost" onClick={updateFromRevision} disabled={updBusy}>
                {updBusy ? "Updating…" : "🔄 Update from CAD Revision"}
              </button>
              <button className="ghost" onClick={saveToData} disabled={savingD}>
                {savingD ? "Saving…" : (saved ? "Saved ✓ — update Data View" : "💾 Save to Data View")}
              </button>
              {saved && <span className="pill">visible in Data View</span>}
            </div>
          )}
          {results.map((res, i) => {
            const rv = (res.revisions && res.revisions.length) ? res.revisions[res.revisions.length - 1].rev : null;
            return (
            <div key={i + "-" + updNonce} className="section">
              <div className="st">{res.component_no} · {res.label}
                <span style={{ display: "flex", gap: 8, marginLeft: "auto", alignItems: "center" }}>
                  {rv && <span className="pill">Rev {rv}</span>}
                  <span className="pill">{res.drawing_no}</span>
                  <button className="mini" onClick={() => download(res)} disabled={!!dlOne}>
                    {dlOne === (res.key || res.drawing_no || res.label) ? "PDF…" : "⬇ PDF"}</button>
                </span>
              </div>
              <div className="k" style={{ marginBottom: 8, fontSize: 12 }}>{geomPill(res.geometry)}</div>
              {res.warnings && res.warnings.length > 0 && <div className="warns">⚠ {res.warnings.join(" · ")}</div>}
              <div className="svgwrap" dangerouslySetInnerHTML={{ __html: res.svg }} />
            </div>);
          })}
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// CAD Revision — edit a generated drawing's dimensions & bump the revision
// --------------------------------------------------------------------------- //
const REV_SPECS = {
  container: {
    url: "/api/cad/container", label: "Container",
    selects: [
      ["container_type", "Container type", [["deep_drawn", "Deep drawn"], ["flanged", "Flanged"]],
        "Deep drawn or flanged. Deep drawn uses OD / height / ID / thickness / bottom radius; flanged adds a mounting flange."],
    ],
    deepFields: [
      ["od", "Container OD (mm)", "Container outer diameter = battery diameter. Wall thickness is looked up from this per Table 2."],
      ["height", "Container height (mm)", "Container height (can body / shoulder). Not the full battery height."],
      ["container_id", "Container ID (mm)", "Container inner diameter. Default = OD − 2 × wall; set here to override."],
      ["wall", "Container thickness (mm)", "Wall thickness (Table 2 by OD, or set here). Container ID = OD − 2 × wall."],
      ["bottom_radius", "Bottom radius (mm)", "Corner / bottom fillet radius of the can. Leave blank for a sharp corner."],
    ],
    flangeSelects: [
      ["flange_kind", "Flange type", [["integral", "Integral"], ["welded", "Welded"]],
        "Integral (formed from the can) or welded-on flange."],
      ["flange_position", "Flange position", [["top", "Top"], ["middle", "Middle"], ["bottom", "Bottom"]],
        "Where the flange sits along the can — top, middle or bottom."],
    ],
    flangeNote: "Flange dimension inputs will be added later.",
  },
  lid_blank: {
    url: "/api/cad/lid", label: "Lid Blank",
    selects: [],
    fields: [
      ["container_id", "Lid blank dia / Container ID (mm)", "Container inner diameter (lid seats inside it). Lid blank OD = container ID − 0.05 (Table 4a)."],
      ["thickness", "Lid blank thickness (mm)", "Lid blank thickness (Table 4b by container OD, or set your own here)."],
      ["cathode_dia", "Cathode / Stack dia (mm)", "Cathode = stack diameter. Sets the back groove circle and pin-hole layout."],
      ["pcd", "Pin PCD (mm)", "Pitch-circle diameter on which the terminal pin holes sit."],
      ["num_holes", "Number of holes", "Number of terminal pin holes (+ve, −ve, EI1, EI2) around the PCD."],
      ["hole_start_angle", "Hole position — start angle (°)", "Angle of the first hole (measured CCW from the 3-o'clock axis; 90 = top). The rest step by 360/N."],
      ["pin_diameter", "Pin diameter (mm)", "Terminal pin diameter. Hole Ø = pin × 2.5 unless you set the hole dia below."],
      ["hole_dia", "Hole dia (mm)", "Terminal pin-hole diameter. Overrides pin × 2.5 when set."],
      ["hole_chamfer", "Hole chamfer (both faces)", "Chamfer on the pin holes, top & bottom faces, e.g. 0.3×45°."],
      ["edge_chamfer", "Edge chamfer", "Chamfer on the lid outer edge, e.g. 0.5×45°."],
      ["edge_angle", "Edge taper angle (°)", "Taper angle of the lid edge so it fits inside the container (default 6°)."],
      ["weld_space", "Weld space from OD (mm)", "Land left in from the OD for welding (default = container wall thickness)."],
      ["groove_depth", "Groove depth (mm)", "Sealing-groove depth (Table 3 by container OD, or set here)."],
      ["groove_width", "Groove width (mm)", "Sealing-groove width (Table 3 by container OD, or set here)."],
      ["back_groove", "Back groove deep × wide (mm)", "Depth & width of the back-side groove circle (default 0.3)."],
      ["letter_size", "Marking letter size (mm)", "Font size of the +, −, EI1, EI2 terminal markings."],
      ["visual_criteria", "Visual criteria (note)", "Free-text acceptance note printed on the sheet, e.g. 'No burrs or edge cuts on sealing face.'"],
    ],
    checks: [
      ["include_section", "Include sectional view (Section X-X)", "Show the Section X-X cross-section on the sheet."],
      ["include_detail", "Include detail view (Detail 'A')", "Show the enlarged Detail 'A' of the edge/groove."],
    ],
  },
  tie_wire: {
    url: "/api/cad/tie_wire", label: "Tie Wire",
    selects: [],
    fields: [
      ["width", "Width (mm)", "Tie-wire strip width (Table by OD, or set here)."],
      ["thickness", "Thickness (mm)", "Tie-wire strip thickness."],
      ["container_height", "Height (mm)", "Container height — sets the tie-wire developed length."],
    ],
  },
  teflon_disc: {
    url: "/api/cad/teflon_disc", label: "Teflon Disc",
    selects: [],
    fields: [
      ["disc_dia", "Teflon disc dia (mm)", "Outer diameter of the teflon disc (default = lid diameter − 2 mm)."],
      ["thickness", "Thickness (mm)", "Teflon disc thickness (STD 0.2 mm)."],
      ["pcd", "Pin PCD (mm)", "Pitch-circle diameter of the pin holes."],
      ["hole_dia", "Pin dia on PCD (mm)", "Diameter of each pin hole placed on the PCD (callout A)."],
      ["num_holes", "Number of pins", "Number of pin holes on the PCD."],
      ["hole_angle", "Angle between pins (°)", "Angular spacing between adjacent pins (360 / number of pins)."],
      ["cathode_dia", "Stack dia — reference (mm)", "Stack diameter, shown as reference; the radial cuts start at this diameter."],
      ["num_wires", "Number of cuts", "Number of radial cuts = number of tie wires."],
      ["cut_length", "Cut length (mm)", "Radial length of each cut (from stack dia out to the disc OD)."],
      ["cut_width", "Cut width (mm)", "Width of each radial cut (= tie-wire width + 1 by default)."],
      ["cut_angle", "Angle between cuts (°)", "Angular spacing between adjacent cuts (360 / number of cuts)."],
    ],
  },
};
// every pellet / disc shares the same editable set: Ø + tolerance, thickness + tolerance
PELLETS.forEach(([ct, label]) => {
  REV_SPECS[ct] = {
    url: "/api/cad/pellet", label,
    selects: [],
    fields: [
      ["dia", "Diameter Ø (mm)", "Pellet diameter. Comes from the input data (cathode/anode dia or container ID); override here."],
      ["dia_tol", "Diameter tolerance", "Shown stacked under Ø on the drawing, e.g. +0.0/−0.2."],
      ["thickness", "Thickness (mm)", "Pellet thickness. Comes from the input data (PID) or a fixed value; override here."],
      ["thk_tol", "Thickness tolerance", "Shown beside the thickness, e.g. ±0.05."],
    ],
  };
});
REV_SPECS["mica_disc_holes"] = {
  url: "/api/cad/mica_holes", label: "Mica Disc (Holes)",
  selects: [],
  fields: [
    ["dia", "Diameter Ø (mm)", "Mica disc diameter = stack diameter. Override here."],
    ["dia_tol", "Diameter tolerance", "Shown stacked under Ø, e.g. +0.0/−0.2."],
    ["thickness", "Thickness (mm)", "Mica disc thickness (0.15 mm)."],
    ["thk_tol", "Thickness tolerance", "e.g. ±0.05."],
    ["pcd", "PCD (mm)", "Pitch-circle diameter of the B holes (Table 1 or calculated)."],
    ["num_holes", "Number of holes", "Number of B holes (Table 1)."],
    ["hole_dia", "Hole dia B (mm)", "Diameter of each hole — callout B = Ø… ON PCD …."],
    ["hole_start_angle", "Hole position — start angle (°)", "Angle of the first hole; the rest step by 360/N."],
  ],
};
REV_SPECS["housing_a"] = {
  url: "/api/cad/housing_a", label: "Housing - A",
  selects: [],
  fields: [
    ["outer_dia", "Outer Ø (mm)", "Outer diameter = stack diameter."],
    ["dia_tol_out", "Outer Ø tolerance", "e.g. +0.0/−0.2"],
    ["inner_dia", "Inner Ø (mm)", "Inner diameter = PCD + 2 mm."],
    ["dia_tol_in", "Inner Ø tolerance", "e.g. +0.2/−0.0"],
    ["squib_width", "Squib width (mm)", "Each cut width = squib width + 2 mm. Default 5."],
    ["mica_thk", "Mica Ring thickness (mm)", "Middle layer thickness (default 0.15)."],
    ["silicon_thk", "Silicon Bonded Mica Ring thickness (mm)", "Top & bottom layer thickness (default 1.0). Total = mica + 2×silicon."],
  ],
};
REV_SPECS["housing_b"] = {
  url: "/api/cad/housing_b", label: "Housing - B",
  selects: [],
  fields: [
    ["outer_dia", "Outer Ø (mm)", "Outer diameter = Container ID − 1."],
    ["inner_dia", "Inner Ø (mm)", "Inner diameter = stack diameter − 2."],
    ["thickness", "Thickness (mm)", "= Silicon Bonded Mica Ring (Housing - B) thickness (default 1.0)."],
  ],
};
REV_SPECS["silicon_ring_a"] = {
  url: "/api/cad/silicon_ring_a", label: "Silicon Bonded Mica Ring (Housing A)",
  selects: [],
  fields: [
    ["outer_dia", "Outer Ø (mm)", "Outer diameter = stack diameter."],
    ["dia_tol_out", "Outer Ø tolerance", "e.g. +0.0/−0.2"],
    ["inner_dia", "Inner Ø (mm)", "Inner diameter = PCD + 2 mm."],
    ["dia_tol_in", "Inner Ø tolerance", "e.g. +0.2/−0.0"],
    ["squib_width", "Squib width (mm)", "Each cut width = squib width + 2 mm. Default 5."],
    ["thickness", "Thickness (mm)", "STD 1.0 mm."],
  ],
};
REV_SPECS["silicon_ring_b"] = {
  url: "/api/cad/silicon_ring_b", label: "Silicon Bonded Mica Ring (Housing B)",
  selects: [],
  fields: [
    ["outer_dia", "Outer Ø (mm)", "Outer diameter = Container ID − 1."],
    ["dia_tol_out", "Outer Ø tolerance", "e.g. +0.0/−0.2"],
    ["inner_dia", "Inner Ø (mm)", "Inner diameter = stack diameter − 2."],
    ["dia_tol_in", "Inner Ø tolerance", "e.g. +0.2/−0.0"],
    ["thickness", "Thickness (mm)", "STD 1.0 mm."],
  ],
};
REV_SPECS["mica_ring"] = {
  url: "/api/cad/mica_ring", label: "Mica Ring",
  selects: [],
  fields: [
    ["outer_dia", "Outer Ø (mm)", "Outer diameter = stack diameter."],
    ["dia_tol_out", "Outer Ø tolerance", "e.g. +0.0/−0.2"],
    ["inner_dia", "Inner Ø (mm)", "Inner diameter = PCD + 2 mm."],
    ["dia_tol_in", "Inner Ø tolerance", "e.g. +0.2/−0.0"],
    ["thickness", "Thickness (mm)", "STD 0.15 mm."],
  ],
};
REV_SPECS["pyro_wick"] = {
  url: "/api/cad/pyro_wick", label: "Pyro Wick - 01",
  selects: [],
  fields: [
    ["length", "Length (mm)", "= Stack (cathode) diameter + 10."],
    ["width", "Width (mm)", "From the table by container OD (30–70 → 3, >70 → 6)."],
    ["thickness", "Thickness (mm)", "From the table by container OD (30–70 → 0.3, >70 → 0.7)."],
  ],
};
REV_SPECS["pyro_wick_02"] = {
  url: "/api/cad/pyro_wick_02", label: "Pyro Wick - 02",
  selects: [],
  fields: [
    ["length", "Length (mm)", "= Container height + 20."],
    ["width", "Width (mm)", "From the table by container OD (30–70 → 3, >70 → 6)."],
    ["thickness", "Thickness (mm)", "From the table by container OD (30–70 → 0.3, >70 → 0.7)."],
  ],
};
REV_SPECS["samica_strip"] = {
  url: "/api/cad/samica_strip", label: "Samica Strip",
  selects: [],
  fields: [
    ["length", "Length (mm)", "= Container height + 20."],
    ["width", "Width (mm)", "STD 6 mm."],
    ["thickness", "Thickness (mm)", "0.1 mm."],
  ],
};
REV_SPECS["mica_strip"] = {
  url: "/api/cad/mica_strip", label: "Mica Strip",
  selects: [],
  fields: [
    ["length", "Length (mm)", "= Battery height + 20."],
    ["width", "Width (mm)", "STD 10 mm."],
    ["thickness", "Thickness (mm)", "0.15 mm."],
  ],
};
REV_SPECS["glass_cloth_tape"] = {
  url: "/api/cad/glass_cloth_tape", label: "Glass Cloth Tape",
  selects: [],
  fields: [
    ["length", "Length (mm)", "= (Container height ÷ width) × π × (stack dia + 2×FiberFrax wrap)."],
    ["width", "Width (mm)", "STD 25 mm."],
    ["thickness", "Thickness (mm)", "STD 0.2 mm."],
    ["fiberfrax_wrap_thickness", "FiberFrax wrap thickness (mm)", "Wrap thickness used in the length calc (default 1.0). Clear the length to recompute."],
  ],
};
REV_SPECS["adhesive_tape"] = {
  url: "/api/cad/adhesive_tape", label: "Adhesive Tape",
  selects: [],
  fields: [
    ["length", "Length (mm)", "Default 100 mm."],
    ["width", "Width (mm)", "Default 12.5 mm."],
    ["thickness", "Thickness (mm)", "Default 0.2 mm."],
  ],
};
REV_SPECS["samica_wrap"] = {
  url: "/api/cad/samica_wrap", label: "Samica Wrap",
  selects: [],
  fields: [
    ["length", "Length (mm)", "= π × (stack dia + 2×FiberFrax wrap) + 10."],
    ["width", "Width (mm)", "= Container height − 3."],
    ["thickness", "Thickness (mm)", "STD 0.1 mm."],
    ["fiberfrax_wrap_thickness", "FiberFrax wrap thickness (mm)", "Used in the length calc (default 1.0). Clear the length to recompute."],
  ],
};
REV_SPECS["mica_wrap"] = {
  url: "/api/cad/mica_wrap", label: "Mica Wrap",
  selects: [],
  fields: [
    ["length", "Length (mm)", "= π × Container ID + 10 (inner circumference + 10)."],
    ["width", "Width (mm)", "= Container height − 3."],
    ["thickness", "Thickness (mm)", "STD 0.1 mm."],
  ],
};
REV_SPECS["fiberfrax_stack_wrap"] = {
  url: "/api/cad/fiberfrax_stack_wrap", label: "FiberFrax Stack Wrap",
  selects: [],
  fields: [
    ["base_length", "Length (mm)", "= stack circumference (2πr)."],
    ["width", "Width (mm)", "= Container height − 3."],
    ["thickness", "Thickness (mm)", "From table by container OD (30–70 → 1, >70 → 1.6)."],
  ],
};
REV_SPECS["fiberfrax_container_insulation"] = {
  url: "/api/cad/fiberfrax_container_insulation", label: "FiberFrax Container Insulation",
  selects: [],
  fields: [
    ["base_length", "A — base length (mm)", "= container circumference (2πr). Each piece adds +10."],
    ["width", "B — width (mm)", "= Container height − 3."],
    ["thickness", "C — thickness (mm)", "From table by container OD (30–70 → 1, >70 → 1.6)."],
    ["qty", "Quantity (rows)", "Number of pieces / table rows."],
  ],
};
REV_SPECS["squib_terminal"] = {
  url: "/api/cad/squib_terminal", label: "Squib Terminal",
  selects: [],
  fields: [
    ["length", "Length (mm)", "Default 50 mm."],
    ["width", "Width (mm)", "Default 3 mm."],
    ["width_tol", "Width tolerance", "e.g. ±0.4"],
    ["thickness", "Thickness (mm)", "Default 0.2 mm."],
    ["thk_tol", "Thickness tolerance", "e.g. +0.000/−0.020"],
  ],
};
REV_SPECS["current_collector_anode"] = {
  url: "/api/cad/current_collector_anode", label: "Current Collector (Anode)",
  selects: [],
  fields: [
    ["disc_dia", "Disc dia (mm)", "SS disc dia = cathode diameter."],
    ["disc_tol", "Disc dia tolerance", "Shown as ØdiaX<tol>, e.g. 0.05."],
    ["disc_thickness", "Disc thickness (mm)", "SS disc/foil thickness."],
    ["lead_length", "Lead length (mm)", "Nickel Lead length (from Lead drawing)."],
    ["lead_width", "Lead width (mm)", "Nickel Lead width (from Lead drawing)."],
    ["lead_thickness", "Lead thickness (mm)", "Nickel Lead thickness (from Lead drawing)."],
    ["gap", "Edge gap (mm)", "Gap from disc edge on the starting side (default 2)."],
    ["cc_type", "Collector type", "Type letter, e.g. B."],
  ],
};
REV_SPECS["current_collector_cathode"] = {
  url: "/api/cad/current_collector_cathode", label: "Current Collector (Cathode)",
  selects: [],
  fields: [
    ["disc_dia", "Disc dia (mm)", "SS disc dia = cathode diameter."],
    ["disc_tol", "Disc dia tolerance", "Shown as ØdiaX<tol>, e.g. 0.05."],
    ["disc_thickness", "Disc thickness (mm)", "SS disc/foil thickness."],
    ["lead_length", "Lead length (mm)", "Nickel Lead length (from Lead drawing)."],
    ["lead_width", "Lead width (mm)", "Nickel Lead width (from Lead drawing)."],
    ["lead_thickness", "Lead thickness (mm)", "Nickel Lead thickness (from Lead drawing)."],
    ["gap", "Edge gap (mm)", "Gap from disc edge on the starting side (default 2)."],
    ["cc_type", "Collector type", "Type letter, e.g. B."],
  ],
};
REV_SPECS["brace_plate"] = {
  url: "/api/cad/brace_plate", label: "Brace Plate",
  selects: [],
  fields: [
    ["cathode_dia", "Cathode dia (mm)", "Outer circle = Brace Plate Dia."],
    ["radial_clearance", "Radial clearance (mm)", "Inner circle = cathode − 2×clearance (default 6)."],
    ["num_tie_wires", "No. of tie wires", "Angle between cuts = 360 ÷ this."],
    ["tie_wire_width", "Tie-wire width (mm)", "From Tie Wire drawing."],
    ["tie_wire_thickness", "Tie-wire thickness (mm)", "From Tie Wire drawing."],
    ["plate_thickness", "Brace plate thickness (mm)", "Blank = auto (0.5 small / 1.0 large battery)."],
    ["plate_width", "Plate width (mm)", "Blank = auto (tie-wire width × 3 or × 2)."],
    ["bump_width", "Bump width (mm)", "Blank = auto (tie-wire width + 2)."],
    ["bump_height", "Bump height (mm)", "Blank = auto (tie-wire thickness × 4)."],
    ["bump_radius", "Bump radius R (mm)", "Radius on the bump top edges (default 3)."],
  ],
};
REV_SPECS["deliver_pin"] = {
  url: "/api/cad/deliver_pin", label: "Deliver Pin",
  selects: [
    ["pin_type", "Pin type", [["round", "Round"], ["top_flat_bottom_round", "Top Flat, Bottom Round"], ["bottom_flat_top_round", "Bottom Flat, Top Round"]],
      "Choose the pin type — the parameters below change to match it."],
  ],
  condKey: "pin_type",
  condFields: {
    round: [
      ["pin_dia", "Pin dia (mm)", "Table 1 'Diameter of the Pin'; else calculated."],
      ["dia_tol", "Dia tolerance", "e.g. ±0.1"],
      ["upper_part", "Upper part of pin (mm)", "From Table 1."],
      ["lid_thickness", "Lid Blank thickness (mm)", "Table 4b by OD; override here."],
      ["bottom_side", "Bottom Side of Lid (mm)", "Given by the user."],
      ["pin_length", "Pin length (mm)", "Blank = Upper part + Lid thickness + Bottom Side."],
    ],
    top_flat_bottom_round: [
      ["pin_dia", "Pin dia (mm)", "Table 1 'Diameter of the Pin'; else calculated."],
      ["dia_tol", "Dia tolerance", "e.g. ±0.1"],
      ["flat_length", "Top flat length (mm)", "Length of the flat portion at the top."],
      ["upper_part", "Upper part of pin (mm)", "From Table 1."],
      ["lid_thickness", "Lid Blank thickness (mm)", "Table 4b by OD; override here."],
      ["bottom_side", "Bottom Side of Lid (mm)", "Given by the user."],
      ["pin_length", "Pin length (mm)", "Blank = Upper part + Lid thickness + Bottom Side."],
    ],
    bottom_flat_top_round: [
      ["pin_dia", "Pin dia (mm)", "Table 1 'Diameter of the Pin'; else calculated."],
      ["dia_tol", "Dia tolerance", "e.g. ±0.1"],
      ["flat_length", "Bottom flat length (mm)", "Length of the flat portion at the bottom."],
      ["upper_part", "Upper part of pin (mm)", "From Table 1."],
      ["lid_thickness", "Lid Blank thickness (mm)", "Table 4b by OD; override here."],
      ["bottom_side", "Bottom Side of Lid (mm)", "Given by the user."],
      ["pin_length", "Pin length (mm)", "Blank = Upper part + Lid thickness + Bottom Side."],
    ],
  },
};
REV_SPECS["stack"] = {
  url: "/api/cad/stack", label: "Stack",
  selects: [],
  fields: [
    ["num_cells", "No. of cells N", "Total cells (from PID); override here."],
    ["num_stacks", "No. of stacks (parallel)", "Stacks in parallel (from PID; default 1)."],
  ],
};
const STRING_KEYS = new Set(["container_type", "flange_kind", "flange_position",
  "edge_chamfer", "hole_chamfer", "visual_criteria", "dia_tol", "thk_tol", "ctype",
  "dia_tol_out", "dia_tol_in", "width_tol", "disc_tol", "cc_type", "is_small", "pin_type"]);
const INT_KEYS = new Set(["num_holes", "num_wires", "qty", "num_tie_wires", "num_cells", "num_stacks"]);

function InfoLabel({ text, info }) {
  return (
    <label className="fl" style={{ display: "flex", alignItems: "center", gap: 6 }}>
      {text}
      {info && <span className="infoi" title={info}>i</span>}
    </label>
  );
}

// Fields that are always CALCULATED from other inputs (read-only in the form).
const DERIVED_FIELDS = new Set(["container_id", "cut_length", "hole_angle", "cut_angle"]);
const _num = (v) => { const n = Number(v); return (v === "" || v === null || v === undefined || isNaN(n)) ? null : n; };
const _r2 = (n) => Math.round(n * 100) / 100;

// Recompute derived values from their drivers (auto-update on any change / load).
function normalizeForm(ctype, form) {
  const f = Object.assign({}, form);
  if (ctype === "container") {
    const od = _num(f.od), wall = _num(f.wall);
    if (od != null && wall != null) f.container_id = _r2(od - 2 * wall);
  }
  if (ctype === "teflon_disc") {
    const disc = _num(f.disc_dia), stack = _num(f.cathode_dia);
    if (disc != null && stack != null) f.cut_length = _r2((disc - (stack + 5)) / 2);
    const nh = _num(f.num_holes); if (nh) f.hole_angle = _r2(360 / nh);
    const nw = _num(f.num_wires); if (nw) f.cut_angle = _r2(360 / nw);
  }
  return f;
}

function coerceBody(form) {
  const body = {};
  for (const k of Object.keys(form)) {
    const v = form[k];
    if (v === null || v === undefined || v === "") continue;
    if (typeof v === "boolean") { body[k] = v; continue; }
    if (STRING_KEYS.has(k)) { body[k] = v; continue; }
    if (INT_KEYS.has(k)) { const n = parseInt(v); if (!isNaN(n)) body[k] = n; continue; }
    const n = Number(v); body[k] = isNaN(n) ? v : n;
  }
  return body;
}

function ParamControls({ spec, form, onChange }) {
  const flanged = form.container_type === "flanged";
  const field = ([k, lbl, info]) => {
    const derived = DERIVED_FIELDS.has(k);
    return (
      <React.Fragment key={k}>
        <InfoLabel text={derived ? lbl + " — auto" : lbl} info={derived ? info + " (calculated automatically)" : info} />
        <input value={form[k] ?? ""} placeholder="—" readOnly={derived}
          className={derived ? "calc" : ""} title={derived ? "Calculated automatically from the other values" : undefined}
          onChange={derived ? undefined : (e => onChange(k, e.target.value))} />
      </React.Fragment>
    );
  };
  const select = ([k, lbl, opts, info]) => (
    <React.Fragment key={k}>
      <InfoLabel text={lbl} info={info} />
      <select value={form[k] ?? ""} onChange={e => onChange(k, e.target.value)}>
        {opts.map(([ov, ol]) => <option key={ov} value={ov}>{ol}</option>)}
      </select>
    </React.Fragment>
  );
  const condFields = (spec.condKey && spec.condFields)
    ? (spec.condFields[form[spec.condKey]] || spec.condFields[Object.keys(spec.condFields)[0]] || [])
    : [];
  return (
    <div style={{ marginTop: 10 }}>
      {(spec.selects || []).map(select)}
      {spec.deepFields && !flanged && spec.deepFields.map(field)}
      {flanged && (spec.flangeSelects || []).map(select)}
      {flanged && spec.flangeNote && <div className="k" style={{ fontSize: 11, marginTop: 6 }}>{spec.flangeNote}</div>}
      {condFields.map(field)}
      {(spec.fields || []).map(field)}
      {(spec.checks || []).map(([k, lbl, info]) => (
        <label key={k} className="fl" style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <input type="checkbox" style={{ width: "auto" }} checked={form[k] !== false} onChange={e => onChange(k, e.target.checked)} />
          {lbl}<span className="infoi" title={info}>i</span>
        </label>
      ))}
    </div>
  );
}

function CadRevision({ jobs, refresh }) {
  const [jobId, setJobId] = useState("");
  const [job, setJob] = useState(null);
  const [sel, setSel] = useState([]);          // selected ctypes (multi)
  const [forms, setForms] = useState({});      // ctype -> form dict
  const [previews, setPreviews] = useState({});// ctype -> generate response
  const [notes, setNotes] = useState({});      // ctype -> revision note
  const [busy, setBusy] = useState({});        // ctype -> live-update in flight
  const [applying, setApplying] = useState({});// ctype -> logging a revision

  const formsRef = React.useRef(forms); formsRef.current = forms;
  const timers = React.useRef({});

  const loadJob = (id) => {
    Object.values(timers.current).forEach(clearTimeout); timers.current = {};
    setJobId(id); setSel([]); setForms({}); setPreviews({}); setNotes({}); setBusy({}); setApplying({}); setJob(null);
    if (id) api("/api/jobs/" + id).then(r => r.json()).then(setJob).catch(() => {});
  };

  const comps = (job && job.cad_components) ? job.cad_components.filter(c => REV_SPECS[c.ctype]) : [];
  const compOf = (ct) => comps.find(c => c.ctype === ct);

  // regenerate a component's drawing. note omitted => live preview (no new rev);
  // note present => log a revision (bumps Rev + date, refreshes job).
  const regen = async (ct, note, formOverride) => {
    const comp = compOf(ct); const spec = REV_SPECS[ct];
    if (!comp || !spec) return;
    const setFlag = note ? setApplying : setBusy;
    setFlag(s => Object.assign({}, s, { [ct]: true }));
    try {
      const f = formOverride || formsRef.current[ct] || {};
      const body = Object.assign(coerceBody(f), { job_id: jobId, seq: comp.no });
      if (note) body.revision_note = note;
      const r = await api(spec.url, { method: "POST", body: JSON.stringify(body) });
      if (!r.ok) throw new Error(await detail(r));
      const d = await r.json();
      setPreviews(s => Object.assign({}, s, { [ct]: d }));
      if (note) {
        setNotes(s => Object.assign({}, s, { [ct]: "" }));
        const jr = await api("/api/jobs/" + jobId); setJob(await jr.json()); refresh();
      }
    } catch (e) { if (note) alert("Revision failed: " + e.message); }
    setFlag(s => Object.assign({}, s, { [ct]: false }));
  };

  const scheduleLive = (ct) => {
    clearTimeout(timers.current[ct]);
    timers.current[ct] = setTimeout(() => regen(ct, null), 450);   // debounce live update
  };

  const toggle = (ct) => {
    if (sel.includes(ct)) {
      clearTimeout(timers.current[ct]);
      setSel(sel.filter(x => x !== ct));
    } else {
      const comp = compOf(ct);
      const initForm = normalizeForm(ct, Object.assign({}, (comp && comp.params) || {}));
      setForms(s => Object.assign({}, s, { [ct]: initForm }));
      setSel([...sel, ct]);
      regen(ct, null, initForm);   // show the initial generated drawing right away
    }
  };

  const setField = (ct, k, v) => {
    setForms(s => Object.assign({}, s, { [ct]: normalizeForm(ct, Object.assign({}, s[ct], { [k]: v })) }));
    scheduleLive(ct);            // live update — recompute dependents, no clicks
  };

  const [savingR, setSavingR] = useState(false);
  const [savedR, setSavedR] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const revItems = () => sel.map(ct => {
    const pv = previews[ct]; const comp = compOf(ct);
    if (!pv || !comp) return null;
    const revs = pv.revisions || comp.revisions || [];
    return { ctype: ct, name: comp.name, no: comp.no, drawing_no: pv.drawing_no || comp.drawing_no,
      rev: revs.length ? revs[revs.length - 1].rev : "01", svg: pv.svg };
  }).filter(Boolean);
  const saveRev = async () => {
    const items = revItems();
    if (!items.length) { alert("No previews to save yet."); return; }
    setSavingR(true);
    try { await saveDrawings(jobId, "revision", items); setSavedR(true); refresh(); }
    catch (e) { alert("Save failed: " + e.message); }
    setSavingR(false);
  };
  const updateToCad = async () => {
    const items = revItems();
    if (!items.length) { alert("No revised drawings to push."); return; }
    setPromoting(true);
    try {
      await saveDrawings(jobId, "revision", items);  // keep the revision record
      await saveDrawings(jobId, "cad", items);        // replace the original CAD drawing
      refresh();
      alert("CAD drawings updated — the revised versions now replace the originals in Data View → CAD Drawings.");
    } catch (e) { alert("Update failed: " + e.message); }
    setPromoting(false);
  };

  return (
    <div>
      <h2 className="modtitle">CAD Revision</h2>
      <div className="viewgrid">
        <div className="vlist">
          <label className="fl">Battery</label>
          <select value={jobId} onChange={e => loadJob(e.target.value)}>
            <option value="">— select saved battery —</option>
            {jobs.map(j => <option key={j.job_id} value={j.job_id}>{j.battery_name}</option>)}
          </select>

          {job && !comps.length && <div className="k" style={{ marginTop: 14 }}>
            No generated drawings for this battery yet. Generate them in <b>CAD Drawing</b> first.</div>}

          {comps.length > 0 && <>
            <label className="fl">Drawings to revise (select one or more)</label>
            <div className="complist">
              {comps.map(c => (
                <label key={c.ctype} className={"cchk" + (sel.includes(c.ctype) ? " on" : "")}>
                  <input type="checkbox" checked={sel.includes(c.ctype)} onChange={() => toggle(c.ctype)} />
                  <span>{String(c.no).padStart(2, "0")} · {c.name}</span>
                  <span className="seqno">Rev {(c.revisions && c.revisions.length) ? c.revisions[c.revisions.length - 1].rev : "01"}</span>
                </label>))}
            </div>
            <div className="k" style={{ fontSize: 11, marginTop: 10 }}>
              Open a drawing's <b>Parameters</b> and edit any value — the diagram updates live on the right.
              Use <b>Log revision</b> to record the change (bumps Rev + today's date).
            </div>
          </>}
        </div>

        <div className="vdetail">
          {!sel.length && <div className="empty">&nbsp;</div>}
          {sel.length > 0 && (
            <div className="row" style={{ marginBottom: 14, alignItems: "center", flexWrap: "wrap" }}>
              <button className="ghost" onClick={saveRev} disabled={savingR}>
                {savingR ? "Saving…" : (savedR ? "Saved ✓ — update Data View" : "💾 Save revised drawings to Data View")}
              </button>
              <button onClick={updateToCad} disabled={promoting}>
                {promoting ? "Updating…" : "⬆ Update to CAD (replace original)"}
              </button>
              {savedR && <span className="pill">visible in Data View → CAD Revisions</span>}
            </div>
          )}
          {sel.map(ct => {
            const comp = compOf(ct); const spec = REV_SPECS[ct];
            if (!comp || !spec) return null;
            const form = forms[ct] || {};
            const pv = previews[ct];
            const revs = (pv && pv.revisions) || comp.revisions || [];
            return (
              <div className="section" key={ct}>
                <div className="st">{String(comp.no).padStart(2, "0")} · {comp.name}
                  <span style={{ display: "flex", gap: 8, marginLeft: "auto", alignItems: "center" }}>
                    {busy[ct] && <span className="k" style={{ fontSize: 11 }}>updating…</span>}
                    <span className="pill">Rev {revs.length ? revs[revs.length - 1].rev : "01"}</span>
                    <span className="pill">{(pv && pv.drawing_no) || comp.drawing_no}</span>
                    {pv && <button className="mini" onClick={() => downloadSvgsPdf([pv.svg],
                      ((pv && pv.drawing_no) || comp.drawing_no || "drawing") + ".pdf").catch(er => alert("PDF export failed: " + er.message))}>⬇ PDF</button>}
                  </span>
                </div>
                <details className="det" open>
                  <summary>Parameters — {spec.label}</summary>
                  <ParamControls spec={spec} form={form} onChange={(k, v) => setField(ct, k, v)} />
                </details>
                {pv
                  ? <div className="svgwrap" style={{ marginTop: 12 }} dangerouslySetInnerHTML={{ __html: pv.svg }} />
                  : <div className="k" style={{ marginTop: 12 }}>Generating…</div>}
                {pv && pv.warnings && pv.warnings.length > 0 && <div className="warns">⚠ {pv.warnings.join(" · ")}</div>}
                <details className="det" style={{ marginTop: 10 }}>
                  <summary>Revision history</summary>
                  <div style={{ marginTop: 8 }}>
                    {revs.length
                      ? <Table cols={[{ k: "rev", label: "Rev" }, { k: "date", label: "Date" }, { k: "description", label: "Description" }]} rows={revs} />
                      : <div className="k">No revisions yet.</div>}
                  </div>
                </details>
                <div className="addrow" style={{ marginTop: 10 }}>
                  <input placeholder="Describe the change to log it as a new revision"
                    value={notes[ct] || ""} onChange={e => setNotes(s => Object.assign({}, s, { [ct]: e.target.value }))} />
                  <button className="mini" disabled={applying[ct]} onClick={() => {
                    if (!(notes[ct] || "").trim()) { alert("Enter a description to log the revision."); return; }
                    regen(ct, (notes[ct] || "").trim());
                  }}>{applying[ct] ? "Logging…" : "Log revision"}</button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Login
// --------------------------------------------------------------------------- //
function Login({ onLogin }) {
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async (e) => {
    if (e) e.preventDefault();
    setBusy(true); setErr("");
    try {
      const r = await fetch("/api/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: u, password: p }),
      });
      if (!r.ok) throw new Error(await detail(r));
      const d = await r.json();
      AUTH.token = d.token; AUTH.user = d.username;
      localStorage.setItem("cadbom_token", d.token);
      localStorage.setItem("cadbom_user", d.username);
      onLogin(d.username);
    } catch (ex) { setErr(ex.message); }
    setBusy(false);
  };

  return (
    <div className="loginwrap">
      <form className="loginbox" onSubmit={submit}>
        <div className="lbrand">CAD-BOM <span>V1</span></div>
        <div className="lsub">Sign in to continue</div>
        <label className="fl">Username</label>
        <input value={u} onChange={e => setU(e.target.value)} autoFocus />
        <label className="fl">Password</label>
        <input type="password" value={p} onChange={e => setP(e.target.value)} />
        {err && <div className="lerr">{err}</div>}
        <button type="submit" style={{ width: "100%", marginTop: 16 }} disabled={busy || !u || !p}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// App shell — LEFT sidebar nav
// --------------------------------------------------------------------------- //
const NAV = [
  { key: "entry", label: "Data Entry", icon: "📝" },
  { key: "view", label: "Data View", icon: "📊" },
  { key: "cad", label: "CAD Drawing", icon: "📐" },
  { key: "revision", label: "CAD Revision", icon: "✏️" },
];

function App() {
  const [user, setUser] = useState(AUTH.token ? AUTH.user : "");
  const [tab, setTab] = useState("entry");
  const [jobs, setJobs] = useState([]);
  const [health, setHealth] = useState(null);
  const [selectedId, setSelectedId] = useState(null);

  const refresh = () => api("/api/jobs").then(r => r.json()).then(setJobs).catch(() => {});
  useEffect(() => { AUTH.onFail = () => setUser(""); }, []);
  useEffect(() => {
    if (!user) return;
    refresh();
    fetch("/api/health").then(r => r.json()).then(setHealth).catch(() => {});
  }, [user]);

  const logout = () => {
    AUTH.token = ""; AUTH.user = "";
    localStorage.removeItem("cadbom_token"); localStorage.removeItem("cadbom_user");
    setUser(""); setJobs([]);
  };

  if (!user) return <Login onLogin={setUser} />;

  return (
    <div className="shell2">
      <aside className="sidenav">
        <div className="navbrand">CAD-BOM <span>V1</span></div>
        <div className="navmodel">{health ? (health.api_key_configured ? health.model : "no API key") : "…"}</div>
        <nav className="navitems">
          {NAV.map(n => (
            <button key={n.key} className={"navitem" + (tab === n.key ? " on" : "")}
              onClick={() => { setTab(n.key); if (n.key !== "entry") refresh(); }}>
              <span className="ni">{n.icon}</span>{n.label}
              {n.key === "view" && <span className="count">{jobs.length}</span>}
            </button>))}
        </nav>
        <div className="navfoot">
          <div className="navuser">👤 {user}</div>
          <button className="ghost mini" onClick={logout}>Log out</button>
        </div>
      </aside>
      <main className="content2">
        {tab === "entry" && <DataEntry health={health} jobs={jobs} onSaved={refresh} />}
        {tab === "view" && <DataView jobs={jobs} selectedId={selectedId} onSelect={setSelectedId} refresh={refresh} />}
        {tab === "cad" && <CadDrawing jobs={jobs} />}
        {tab === "revision" && <CadRevision jobs={jobs} refresh={refresh} />}
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
