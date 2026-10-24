// Officer desk: queue, case view, live agent run, note for sanction and the officer's decision.
const STEP_DEFS = [
  ["open", "Open the file", "Lakehouse"],
  ["documents", "Read and cross-check documents", "Gemini"],
  ["verify", "Verify with external sources", "CIBIL, CERSAI, PAN/CKYC, AA, EPFO, GST"],
  ["policy", "Apply credit policy", "Policy pack v4.2 and RBI rules"],
  ["recommend", "Recommend and route", "Delegation of powers"],
  ["note", "Draft the note for sanction", "Gemini"],
  ["handoff", "Hand off to the credit officer", "Human decision"],
];
const STAGES = ["Login & KYC", "Credit appraisal", "Legal & technical", "Sanction", "Documentation", "Disbursed"];
const DEC_LABEL = { Sanction: "Sanction", Refer: "Refer to higher authority", Hold: "Hold", Decline: "Decline" };
let QUEUE = [], CASE = null, RUN = null, EVENTS = [], RESULT = null, CLAUSES = {}, TAB = "review", ES = null;

api("/api/policy/clauses").then(j => j.clauses.forEach(c => CLAUSES[c.clause_id] = c));

// ------------------------------------------------------------------ queue
async function loadQueue() {
  const j = await api("/api/queue");
  QUEUE = j.rows;
  renderQueue();
  const id = location.hash.slice(1) || QUEUE[0]?.application_id;
  if (id) openCase(id);
}
function renderQueue() {
  const q = document.getElementById("q-search").value.toLowerCase();
  const rows = QUEUE.filter(r => !q || r.full_name.toLowerCase().includes(q) || r.application_id.toLowerCase().includes(q));
  const demo = rows.filter(r => r.is_demo_case == 1), rest = rows.filter(r => r.is_demo_case != 1);
  document.getElementById("q-count").textContent = QUEUE.length;
  const item = r => `<button class="q-item" data-id="${r.application_id}" ${CASE?.app.application_id === r.application_id ? 'aria-current="true"' : ""}>
      <div class="n"><span>${esc(r.full_name)}</span><span class="num">${lakh(r.loan_amount)}</span></div>
      <div class="d"><span>${esc(r.city)}, ${esc(r.stage)}</span>${r.officer_decision ? `<span>${esc(r.officer_decision)}</span>` : statusPill(r.screening_result)}</div>
      ${r.is_demo_case == 1 ? `<div class="scn">${esc(SCEN[r.full_name] || "")}</div>` : ""}</button>`;
  document.getElementById("queue").innerHTML =
    (demo.length ? `<div class="q-group">Demo files with full documents</div>${demo.map(item).join("")}` : "") +
    (rest.length ? `<div class="q-group">Other files in progress (batch screening from the lakehouse)</div>${rest.map(item).join("")}` : "") ||
    `<div class="empty">No file matches “${esc(q)}”.</div>`;
}
document.getElementById("queue").addEventListener("click", e => { const b = e.target.closest(".q-item"); if (b) { location.hash = b.dataset.id; } });
document.getElementById("q-search").addEventListener("input", renderQueue);
window.addEventListener("hashchange", () => openCase(location.hash.slice(1)));

// ------------------------------------------------------------------ case
async function openCase(id) {
  if (!id || CASE?.app.application_id === id) return;
  if (ES) { ES.close(); ES = null; }
  document.getElementById("case").innerHTML = `<div class="empty">Opening ${esc(id)}…</div>`;
  CASE = await api("/api/case/" + id);
  EVENTS = []; RESULT = CASE.last_result; RUN = RESULT ? { run_id: RESULT.run_id } : null; TAB = "review";
  if (RESULT) EVENTS = null; // previous run: show result summary only
  renderCase();
  renderQueue();
}
function renderCase() {
  const a = CASE.app, p = CASE.property;
  const si = STAGES.indexOf(a.stage);
  document.getElementById("case").innerHTML = `
    <div class="case-head">
      <div>
        <h1>${esc(a.full_name)}</h1>
        <div class="case-sub"><span class="mono">${esc(a.application_id)}</span><span>${lakh(a.loan_amount)} over ${a.tenor_months / 12} years</span><span>${esc(a.purpose)}</span><span>${esc(a.occupation_type)}, ${esc(a.employer_name)}</span><span>${esc(a.assigned_officer)}</span></div>
        <div class="case-sub"><span>${esc(p.address)}</span>${p.builder ? `<span>${esc(p.builder)}${p.rera_number ? ", " + esc(p.rera_number) : ""}</span>` : ""}</div>
      </div>
      <div><button class="btn primary" id="run-btn">${RESULT ? "Run the review again" : "Run agent review"}</button></div>
    </div>
    <ol class="tracker" aria-label="Loan stage">${STAGES.map((s, i) => `<li class="${i < si ? "done" : i === si ? "now" : ""}"><span>${i + 1}</span>${s}</li>`).join("")}</ol>
    <div class="case-body">
      <div>
        <div class="tabs" role="tablist">
          ${[["review", "Agent review"], ["evidence", "Evidence by source"], ["docs", "Documents"], ["note", "Note for sanction"]].map(([k, t]) => `<button role="tab" data-tab="${k}" aria-selected="${TAB === k}">${t}</button>`).join("")}
        </div>
        <div class="tabpanel" id="tabpanel"></div>
      </div>
      <aside class="rail" id="rail"></aside>
    </div>`;
  document.getElementById("run-btn").onclick = startRun;
  document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => { TAB = b.dataset.tab; document.querySelectorAll(".tabs button").forEach(x => x.setAttribute("aria-selected", x === b)); renderTab(); });
  renderTab(); renderRail();
}
function renderTab() {
  const el = document.getElementById("tabpanel");
  if (!el) return;
  if (TAB === "review") el.innerHTML = reviewHTML();
  if (TAB === "evidence") el.innerHTML = evidenceHTML();
  if (TAB === "docs") { el.innerHTML = docsHTML(); bindDocs(); }
  if (TAB === "note") { el.innerHTML = noteHTML(); bindNote(); }
}

// ------------------------------------------------------------------ run
async function startRun() {
  const btn = document.getElementById("run-btn");
  btn.disabled = true; btn.textContent = "Agent working…";
  RESULT = null; EVENTS = []; TAB = "review";
  document.querySelectorAll(".tabs button").forEach(x => x.setAttribute("aria-selected", x.dataset.tab === "review"));
  const r = await api("/api/run/" + CASE.app.application_id, { method: "POST" });
  RUN = r;
  renderTab(); renderRail();
  ES = new EventSource(`/api/run/${r.run_id}/events`);
  ES.onmessage = m => {
    const e = JSON.parse(m.data);
    EVENTS.push(e);
    if (e.type === "done") { RESULT = e.result; }
    scheduleRender();
  };
  ES.addEventListener("end", () => { ES.close(); ES = null; btn.disabled = false; btn.textContent = "Run the review again"; renderRail(); renderTab(); });
  ES.onerror = () => { if (ES) { ES.close(); ES = null; } btn.disabled = false; btn.textContent = "Run agent review"; };
}
let pending = false;
function scheduleRender() { if (pending) return; pending = true; requestAnimationFrame(() => { pending = false; if (TAB === "review") renderTab(); renderRail(); }); }

function stepState(key) {
  if (!EVENTS) return "done";
  const s = EVENTS.filter(e => e.step === key);
  if (s.some(e => e.type === "step_end")) return "done";
  if (s.some(e => e.type === "step_start")) return "running";
  return "waiting";
}
function stepTime(key) {
  if (!EVENTS) return "";
  const s = EVENTS.filter(e => e.step === key);
  const a = s.find(e => e.type === "step_start"), b = s.find(e => e.type === "step_end");
  if (!a || !b) return "";
  const ms = new Date(b.ts) - new Date(a.ts);
  return ms >= 1000 ? (ms / 1000).toFixed(0) + "s" : "<1s";
}

function reviewHTML() {
  if (!EVENTS && RESULT) return `<p class="muted">Showing the last review of this file (${esc(RESULT.run_id)}). Run it again to watch each step live.</p>` + checksTable(RESULT.checks) + findingsHTML(RESULT.doc_findings);
  if (!EVENTS || (!EVENTS.length && !RUN)) return `<div class="empty"><p>The agent has not reviewed this file yet.</p><p>Run the review to see it open the file, read the documents, call each external check, apply policy with clause references and draft the note for sanction. About 20 seconds.</p></div>`;
  return `<ol class="steps">${STEP_DEFS.map(([k, t, u], i) => {
    const st = stepState(k);
    const evs = EVENTS.filter(e => e.step === k && !["step_start", "step_end", "done"].includes(e.type));
    return `<li class="step ${st}"><span class="no">${i + 1}</span>
      <div class="st"><h3>${t}</h3><span class="uses">${u}</span><span class="uses num">${stepTime(k)}</span></div>
      <div class="ev">${dbLine(evs)}${k === "policy" ? checksTable(evs.filter(e => e.type === "check")) : ""}${evs.filter(e => !(k === "policy" && e.type === "check") && e.tool !== "read_database").map(evHTML).join("")}</div></li>`;
  }).join("")}</ol>`;
}
function evHTML(e) {
  if (e.type === "tool" && e.tool === "read_database") return `<div class="ev-tool"><span class="src">Read ${esc(e.target)}</span><span>${esc(e.purpose)}</span><span class="ms">${e.rows} row${e.rows === 1 ? "" : "s"}, ${e.ms} ms, ${esc(e.engine)}</span></div>`;
  if (e.type === "tool") return `<div class="ev-tool"><span class="src">${esc(e.source)}</span><span>${esc(e.who)}: ${esc(e.summary)}</span><span class="ms">${(e.ms / 1000).toFixed(1)}s, ₹${e.cost_inr}</span></div>`;
  if (e.type === "document") return `<div class="ev-doc"><span class="src" style="font-weight:500">${esc(e.doc_type)}</span><span class="muted">${howText(e.how)}</span><button class="linkish" onclick="gotoDoc('${esc(e.file)}')">See fields</button></div>`;
  if (e.type === "finding") return `<div class="ev-find"><span class="dot ${e.status === "info" ? "" : e.status}"></span><span>${esc(e.text)} ${e.clause ? cite(e.clause) : ""}</span></div>`;
  if (e.type === "recommendation") return `<div class="ev-find"><span class="dot ${e.decision === "Sanction" ? "pass" : e.decision === "Refer" ? "flag" : "fail"}"></span><span><strong>${esc(e.label)}.</strong> Sanctioning authority: ${esc(e.authority)}. ${e.passed} of ${e.checks_total} checks passed.</span></div>`;
  if (e.type === "note") return `<div class="ev-find"><span class="dot pass"></span><span>Draft note ready (${howText(e.how)}). <button class="linkish" onclick="showTab('note')">Open the note for sanction</button></span></div>`;
  if (e.type === "handoff") return `<div class="ev-find"><span class="dot"></span><span>${esc(e.text)}</span></div>`;
  if (e.type === "error") return `<div class="msg err">${esc(e.message)}</div>`;
  return "";
}
function dbLine(evs) {
  const db = evs.filter(e => e.tool === "read_database");
  if (!db.length) return "";
  const ms = db.reduce((t, e) => t + e.ms, 0);
  return `<div class="ev-tool"><span class="src">Read ${db.length} lakehouse ${db.length === 1 ? "table" : "tables"}</span><span>${db.map(e => esc(e.target)).join(", ")}</span><span class="ms">${ms} ms, ${esc(db[0].engine)}</span><button class="linkish" onclick="showTab('evidence')">SQL</button></div>`;
}
function howText(h) {
  if (!h) return "";
  if (h.mode === "gemini") return `read by ${esc(h.model)} in ${(h.ms / 1000).toFixed(1)}s`;
  if (h.mode === "fallback") return "AI unavailable, used pre-extracted values";
  return "offline mode: pre-extracted values";
}
function cite(id) { return `<button class="clause cite" data-clause="${esc(id)}">${esc(id)}</button>`; }
function checksTable(checks) {
  if (!checks.length) return "";
  return `<div class="tbl-scroll"><table class="t checks"><thead><tr><th>Check</th><th>Result and policy</th><th>Status</th></tr></thead><tbody>
    ${checks.map(c => `<tr><td>${esc(c.label)}<div class="detail">${esc(c.evidence.join(", "))}</div></td><td>${esc(c.value)}${c.detail ? `<div class="detail">${esc(c.detail)}</div>` : ""}<div class="detail">Policy: ${esc(c.threshold)} ${cite(c.clause)}</div></td><td>${statusPill(c.status)}</td></tr>`).join("")}
  </tbody></table></div>`;
}
function findingsHTML(f) { return f?.length ? `<h4 style="margin:16px 0 6px">Document cross-checks</h4>` + f.map(x => evHTML({ type: "finding", ...x })).join("") : ""; }
function showTab(k) { TAB = k; document.querySelectorAll(".tabs button").forEach(x => x.setAttribute("aria-selected", x.dataset.tab === k)); renderTab(); }
let DOC_SEL = null;
function gotoDoc(file) { DOC_SEL = file; showTab("docs"); }

// ------------------------------------------------------------------ evidence
function evidenceHTML() {
  const evs = EVENTS || [];
  const db = evs.filter(e => e.type === "tool" && e.tool === "read_database");
  const ext = evs.filter(e => e.type === "tool" && e.tool !== "read_database");
  const docs = evs.filter(e => e.type === "document");
  const f = CASE.features;
  let h = `<p class="muted">Everything the agent relied on, grouped by where it came from. Numbers in the note can be traced back to a query, an API response or a document.</p>`;
  h += `<div class="src-block"><header><strong>Lakehouse: decision-ready row</strong><span class="muted">${esc(CASE.engine)}, lending_gold.application_features</span></header><div class="b">
    <dl class="fig" style="grid-template-columns: repeat(2, max-content 1fr); max-width: 720px">
      <dt>Income assessed</dt><dd>${inr(f.income_assessed)}</dd><dt>Existing EMIs</dt><dd>${inr(f.obligations)}</dd>
      <dt>Rate at login / now</dt><dd>${f.rate_at_login}% / ${f.rate_now}%</dd><dt>FOIR at login / now</dt><dd>${f.foir_at_login}% / ${f.foir_now}%</dd>
      <dt>LTV</dt><dd>${f.ltv}% (cap ${f.ltv_cap}%)</dd><dt>Batch screening</dt><dd>${esc(f.screening_result)}</dd></dl>
    <details><summary>SQL</summary><pre class="sql">${esc(CASE.sql.features)}</pre></details></div></div>`;
  if (!evs.length) return h + `<div class="empty">Run the agent review to see the live calls to each source.</div>`;
  h += `<div class="src-block"><header><strong>Lakehouse queries during this review</strong><span class="muted">${db.length} queries</span></header><div class="b">${db.map(e => `
    <div style="padding:6px 0;border-bottom:1px solid var(--line-2)"><div class="ev-tool"><span class="src">${esc(e.target)}</span><span>${esc(e.purpose)}</span><span class="ms">${e.rows} rows, ${e.ms} ms${e.bytes_processed != null ? ", " + (e.bytes_processed / 1024).toFixed(0) + " KB scanned" : ""}</span></div>
    <details><summary>SQL</summary><pre class="sql">${esc(e.sql)}</pre></details></div>`).join("")}</div></div>`;
  h += `<div class="src-block"><header><strong>External checks (mock services)</strong><span class="muted">${ext.length} calls in parallel, ₹${ext.reduce((s, e) => s + e.cost_inr, 0)} illustrative cost</span></header><div class="b">${ext.map(e => `
    <div style="padding:6px 0;border-bottom:1px solid var(--line-2)"><div class="ev-tool"><span class="src">${esc(e.source)}</span><span>${esc(e.who)}: ${esc(e.summary)}</span><span class="ms">${esc(e.target)}, ${(e.ms / 1000).toFixed(2)}s</span></div>
    <details><summary>Response</summary><pre class="json">${esc(JSON.stringify(e.response, null, 2))}</pre></details></div>`).join("")}</div></div>`;
  h += `<div class="src-block"><header><strong>Documents read</strong><span class="muted">${docs.length} documents</span></header><div class="b">${docs.length ? docs.map(e => `<div class="ev-doc"><span style="font-weight:500">${esc(e.doc_type)}</span><span class="muted">${howText(e.how)}</span><button class="linkish" onclick="gotoDoc('${esc(e.file)}')">See fields</button></div>`).join("") : '<span class="muted">This synthetic file has no document images; values come from the loan system.</span>'}</div></div>`;
  return h;
}

// ------------------------------------------------------------------ documents
function docsHTML() {
  const docs = CASE.documents;
  if (!docs.length) return `<p class="muted">Documents received for this file. Only the four demo files carry document images.</p><table class="t"><thead><tr><th>Document</th><th>Received</th><th>Pages</th><th>Source</th></tr></thead><tbody>${CASE.documents_index.map(d => `<tr><td>${esc(d.doc_type)}</td><td>${dmy(d.received_date)}</td><td>${d.pages}</td><td>${esc(d.source)}</td></tr>`).join("")}</tbody></table>`;
  const sel = DOC_SEL && docs.find(d => d.file === DOC_SEL) ? DOC_SEL : docs[0].file;
  const read = (EVENTS || []).find(e => e.type === "document" && e.file === sel);
  return `<div class="doclist"><div>
      ${docs.map(d => `<button class="q-item" data-file="${esc(d.file)}" ${d.file === sel ? 'aria-current="true"' : ""}><div class="n">${esc(d.doc_type)}</div></button>`).join("")}
      <div style="margin-top:14px">${read ? `<h4 style="margin-bottom:6px">Fields read <span class="muted" style="font-weight:400">${howText(read.how)}</span></h4>
        <table class="t"><tbody>${Object.entries(read.fields).map(([k, v]) => `<tr><td class="muted">${esc(k.replace(/_/g, " "))}</td><td>${esc(typeof v === "number" && v > 999 ? inr(v) : v)}</td></tr>`).join("")}</tbody></table>`
        : `<p class="muted">Run the agent review to see the fields Gemini reads from this document.</p>`}</div>
    </div><iframe title="Document" src="${esc(sel)}#view=FitH"></iframe></div>`;
}
function bindDocs() { document.querySelectorAll(".doclist .q-item").forEach(b => b.onclick = () => { DOC_SEL = b.dataset.file; renderTab(); }); }

// ------------------------------------------------------------------ note for sanction
function noteHTML() {
  if (!RESULT) return `<div class="empty">The note is drafted at the end of the agent review.</div>`;
  const a = CASE.app, p = CASE.property, r = RESULT.recommendation, d = CASE.decision;
  const today = new Date().toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  return `<div class="note stamp-wrap">
    ${d ? stampHTML(d) : ""}
    <div class="note-head"><div><h2>Note for sanction: home loan</h2><div class="muted">${esc(a.application_id)}, prepared ${today} by the credit case agent for ${esc(a.assigned_officer)}</div></div></div>
    <h3>Proposal</h3>
    <dl class="kv"><dt>Applicant</dt><dd>${esc(a.full_name)}, ${a.applicant_age} years, ${esc(a.occupation_type.toLowerCase())}, ${esc(a.employer_name)}</dd>
      <dt>Loan</dt><dd>${lakh(r.loan_amount)} for ${r.tenor_months / 12} years at ${r.rate.toFixed(2)}% floating (repo-linked); EMI ${inr(r.emi)}</dd>
      <dt>Purpose</dt><dd>${esc(a.purpose)}</dd><dt>Property</dt><dd>${esc(p.address)}</dd>
      <dt>Income assessed</dt><dd>${inr(r.income)} a month; existing EMIs ${inr(r.obligations)}</dd>
      <dt>FOIR / LTV</dt><dd>${r.foir}% / ${r.ltv}%</dd></dl>
    <h3>Summary</h3>
    <p class="muted" style="font-size:12.5px;margin-bottom:6px">${howText(RESULT.note_how) ? "Drafted by the agent (" + howText(RESULT.note_how).replace("read by", "") + "). Edit before you decide; your version is what gets recorded." : ""}</p>
    <textarea id="note-text" rows="9">${esc(RESULT.note)}</textarea>
    <h3>Policy checks</h3>${checksTable(RESULT.checks)}
    ${r.deviations.length ? `<h3>Deviations</h3><ul>${r.deviations.map(x => `<li>${esc(x.text)} ${cite(x.clause)}</li>`).join("")}</ul>` : ""}
    ${r.holds.length ? `<h3>Why the file is on hold</h3><ul>${r.holds.map(x => `<li>${esc(x.text)} ${cite(x.clause)}</li>`).join("")}</ul>` : ""}
    ${r.options.length ? `<h3>Ways to bring it within policy</h3><ul>${r.options.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    ${r.mitigants.length ? `<h3>Mitigants</h3><ul>${r.mitigants.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    ${r.conditions.length ? `<h3>Conditions</h3><ol>${r.conditions.map(x => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}
    <h3>Recommendation</h3><p><strong>${esc(r.label)}.</strong> Sanctioning authority: ${esc(r.authority)} ${cite("HLP-9.1")}</p>
  </div>`;
}
function stampHTML(d, press) {
  const word = { Sanction: "SANCTIONED", Refer: "REFERRED", Hold: "ON HOLD", Decline: "DECLINED" }[d.officer_decision];
  return `<div class="stamp ${d.officer_decision} ${press ? "press" : ""}"><div class="big">${word}</div><div class="sm">${esc(d.decided_by)}<br>${new Date(d.decided_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</div></div>`;
}
function bindNote() {}

// ------------------------------------------------------------------ rail
function renderRail() {
  const el = document.getElementById("rail");
  if (!el) return;
  const f = CASE.features;
  if (!RESULT) {
    const running = EVENTS && EVENTS.length && !RESULT;
    el.innerHTML = `<div class="rec"><div class="rec-h"><div class="lbl">Agent recommendation</div><div class="dec" style="color:var(--ink-3)">${running ? "Working on it…" : "Not reviewed yet"}</div></div>
      <div class="rec-b"><p class="muted" style="margin:0 0 10px">Batch screening from the lakehouse, before the agent looks at documents and live checks:</p>
      <dl class="fig"><dt>Screening</dt><dd>${statusPill(f.screening_result)}</dd><dt>FOIR now</dt><dd>${f.foir_now}% <span class="muted">/ ${f.foir_cap}%</span></dd><dt>LTV</dt><dd>${f.ltv}% <span class="muted">/ ${f.ltv_cap}%</span></dd><dt>Bureau score</dt><dd>${f.bureau_score}</dd></dl></div></div>
      <h4>What stays with people</h4><ul><li>Sanction, decline and any override: the credit officer and the authority in the delegation of powers.</li><li>Title opinion and valuation: panel advocate and empanelled valuer.</li><li>Fraud verification: Risk Containment Unit.</li></ul>`;
    return;
  }
  const r = RESULT.recommendation, d = CASE.decision;
  el.innerHTML = `<div class="rec ${r.decision}"><div class="rec-h"><div class="lbl">Agent recommendation</div><div class="dec">${esc(r.label)}</div></div>
    <div class="rec-b"><dl class="fig">
      <dt>Loan</dt><dd>${lakh(r.loan_amount)}</dd><dt>Rate, EMI</dt><dd>${r.rate.toFixed(2)}%, ${inr(r.emi)}</dd>
      <dt>FOIR</dt><dd>${r.foir}%</dd><dt>LTV</dt><dd>${r.ltv}%</dd><dt>Checks passed</dt><dd>${r.passed} of ${r.checks_total}</dd></dl>
      <p style="margin:10px 0 0;font-size:13px">Routes to: <strong>${esc(r.authority)}</strong></p></div></div>
    ${r.holds.length ? `<h4>On hold because</h4><ul>${r.holds.map(x => `<li>${esc(x.text)}</li>`).join("")}</ul>` : ""}
    ${r.deviations.length ? `<h4>Deviation</h4><ul>${r.deviations.map(x => `<li>${esc(x.text)}</li>`).join("")}</ul>` : ""}
    ${r.options.length ? `<h4>Options</h4><ul>${r.options.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    <div class="decide" id="decide">${d ? decidedHTML(d) : decideHTML(r)}</div>`;
  bindDecide(r);
}
function decideHTML(r) {
  return `<strong>Your decision</strong>
    <div class="row"><button class="btn primary" data-d="${r.decision}">${r.decision === "Sanction" ? "Sanction" : "Accept: " + DEC_LABEL[r.decision].toLowerCase()}</button>
    <button class="btn" id="other">Decide differently</button></div>
    <div id="other-box" hidden style="margin-top:10px">
      <label class="f" for="dec-sel">Decision</label>
      <select id="dec-sel">${Object.entries(DEC_LABEL).filter(([k]) => k !== r.decision).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
      <label class="f" for="dec-reason" style="margin-top:8px">Reason (recorded, and used to improve the agent)</label>
      <textarea id="dec-reason" rows="3" placeholder="For example: long salary relationship; co-owner to be added at sanction"></textarea>
      <div class="row"><button class="btn primary" id="dec-submit">Record decision</button></div></div>
    <div id="dec-msg"></div>`;
}
function decidedHTML(d) {
  return `<strong>Decision recorded</strong>${d.referred_by ? `<p style="margin:6px 0 0;font-size:13px">Referred by ${esc(d.referred_by.decided_by)}.</p>` : ""}<p style="margin:6px 0 0;font-size:13px">${esc(DEC_LABEL[d.officer_decision])} by ${esc(d.decided_by)}${d.override ? `, overriding the agent. Reason: ${esc(d.override_reason)}` : d.referred_by ? (d.override_reason ? `. Note: ${esc(d.override_reason)}` : "") : ", in line with the agent's recommendation"}.</p>
    ${d.kfs ? `<p style="font-size:13px;margin:8px 0 0">Key Facts Statement issued: APR ${d.kfs.apr}%, EMI ${inr(d.kfs.emi)}. <a href="/applicant#${esc(CASE.app.application_id)}">See what the applicant sees</a></p>` : ""}
    ${d.officer_decision === "Refer" && !d.referred_by ? `<div style="margin-top:12px;border-top:1px dashed var(--line);padding-top:12px"><strong>${esc(RESULT.recommendation.authority)}</strong>
      <p style="font-size:13px;margin:4px 0 8px">The referral now sits with the higher authority. Switch roles to approve the deviation.</p>
      <textarea id="auth-reason" rows="2" placeholder="Approval note, e.g. deviation of 0.5 pp approved given 16-year relationship"></textarea>
      <div class="row"><button class="btn primary" id="auth-ok">Approve and sanction</button><button class="btn" id="auth-no">Send back</button></div></div>` : ""}
    <p class="muted" style="font-size:12.5px;margin-top:8px">Written to lending_gold.officer_decisions with the agent's run id.</p>`;
}
function bindDecide(r) {
  const box = document.getElementById("decide");
  const ok = document.getElementById("auth-ok");
  if (ok) {
    ok.onclick = () => submitDecision("Sanction", document.getElementById("auth-reason").value, true);
    document.getElementById("auth-no").onclick = () => submitDecision("Hold", document.getElementById("auth-reason").value || "Sent back by the higher authority for more information", true);
  }
  if (!box || CASE.decision) return;
  box.querySelector("[data-d]").onclick = () => submitDecision(r.decision, "");
  document.getElementById("other").onclick = () => { document.getElementById("other-box").hidden = false; };
  document.getElementById("dec-submit").onclick = () => submitDecision(document.getElementById("dec-sel").value, document.getElementById("dec-reason").value);
}
async function submitDecision(dec, reason, asAuthority = false) {
  const msg = document.getElementById("dec-msg");
  try {
    const note = document.getElementById("note-text")?.value;
    const d = await api("/api/decision", { method: "POST", body: JSON.stringify({ application_id: CASE.app.application_id, run_id: RESULT.run_id, decision: dec, reason, note, officer: CASE.app.assigned_officer, as_authority: asAuthority }) });
    CASE.decision = d;
    const q = QUEUE.find(x => x.application_id === CASE.app.application_id); if (q) q.officer_decision = d.officer_decision;
    renderQueue(); renderRail(); showTab("note");
    const s = document.querySelector(".note .stamp"); if (s) s.classList.add("press");
    window.scrollTo({ top: document.getElementById("case").offsetTop - 70, behavior: "smooth" });
  } catch (e) { msg.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; }
}

// ------------------------------------------------------------------ clause popover
document.addEventListener("click", e => {
  const pop = document.getElementById("pop");
  const b = e.target.closest(".cite");
  if (!b) { if (!e.target.closest("#pop")) pop.hidden = true; return; }
  const c = CLAUSES[b.dataset.clause];
  if (!c) return;
  pop.innerHTML = `<div class="doc">${esc(c.document)}</div><strong>${esc(c.clause_id)} ${esc(c.title)}</strong><p style="margin:6px 0 0">${esc(c.text)}</p>${c.source_url ? `<p style="margin:6px 0 0"><a href="${esc(c.source_url)}" target="_blank" rel="noopener">Source</a></p>` : ""}`;
  pop.hidden = false;
  const rc = b.getBoundingClientRect();
  pop.style.top = Math.min(rc.bottom + 6, innerHeight - pop.offsetHeight - 10) + "px";
  pop.style.left = Math.max(10, Math.min(rc.left, innerWidth - pop.offsetWidth - 10)) + "px";
});

const SCEN = {
  "Priya Raghavan": "Clean salaried file",
  "Arjun Mehta": "Self-employed; the 7 Oct repo hike pushed FOIR over the cap",
  "Sunita Yadav": "Resale house; CERSAI shows the seller's old mortgage",
  "Vikram Sethi": "Payslip doesn't match bank credits",
};
loadQueue();
